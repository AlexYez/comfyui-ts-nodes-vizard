from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import re
import struct
import tempfile
import unittest
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import torch
from PIL import Image, ImageSequence

from tools import catalog


ARTICLE_SPECS = {
    "core.load-image-output": {
        "directory": "load-image-output",
        "classType": "LoadImageOutput",
        "pythonModule": "nodes",
        "fingerprint": "sha256:f30dc346b1af24c02dd13b4b48190767830f0fca6aa7336f02eb06eae62f8762",
        "recipe": "recipe.reload-output-image",
        "experimental": True,
    },
    "core.save-animated-webp": {
        "directory": "save-animated-webp",
        "classType": "SaveAnimatedWEBP",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:6308b5dc7d89d50a30a3c3023e7a68d7043bbe1de12bea305aac5e0719b974da",
        "recipe": "recipe.save-animation-webp",
        "experimental": False,
    },
    "core.save-animated-png": {
        "directory": "save-animated-png",
        "classType": "SaveAnimatedPNG",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:30aaa2b472bac843a5665477e8ea2dd01fbc606bb04ddb07cd6f3e1b0e7ed0d6",
        "recipe": "recipe.save-animation-apng",
        "experimental": False,
    },
    "core.save-image-advanced": {
        "directory": "save-image-advanced",
        "classType": "SaveImageAdvanced",
        "pythonModule": "comfy_extras.nodes_images",
        "fingerprint": "sha256:4ae2d8026a72399b78a228b4312756984086c2080ccfe6712341ab6929ecdd09",
        "recipe": "recipe.save-image-advanced-png16",
        "experimental": False,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.reload-output-image": "reload-output-image",
    "recipe.save-animation-webp": "save-animation-webp",
    "recipe.save-animation-apng": "save-animation-apng",
    "recipe.save-image-advanced-png16": "save-image-advanced-png16",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.reload-output-image": [
        ("LoadImageOutput", {"image": "SELECT_OUTPUT_FILE"}),
        ("PreviewImage", {}),
        ("MaskToImage", {}),
        ("PreviewImage", {}),
    ],
    "recipe.save-animation-webp": [
        (
            "SaveAnimatedWEBP",
            {
                "filename_prefix": "ComfyUI",
                "fps": 16.0,
                "lossless": True,
                "quality": 80,
                "method": "default",
            },
        ),
    ],
    "recipe.save-animation-apng": [
        (
            "SaveAnimatedPNG",
            {"filename_prefix": "ComfyUI", "fps": 12.0, "compress_level": 4},
        ),
        ("PreviewImage", {}),
    ],
    "recipe.save-image-advanced-png16": [
        (
            "SaveImageAdvanced",
            {
                "filename_prefix": "ComfyUI_16bit",
                "format": "png",
                "bit_depth": "16-bit",
                "input_color_space": "sRGB",
            },
        ),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
TARGET_TYPES = {
    "LoadImageOutput",
    "SaveAnimatedWEBP",
    "SaveAnimatedPNG",
    "SaveImageAdvanced",
}


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def workflow_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": payload.get("id"),
                "scope": "root",
                "node": node,
            }
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": payload.get("id"),
                    "scope": "subgraph",
                    "subgraphId": subgraph.get("id"),
                    "node": node,
                }


def extract_advanced_helpers() -> dict[str, Any]:
    """Execute pinned pure helpers without importing the full ComfyUI runtime."""
    path = SOURCE / "comfy_extras" / "nodes_images.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments = {
        "_HLG_A",
        "_HLG_B",
        "_HLG_C",
        "_PNG_SIGNATURE",
        "_CHROMATICITIES",
    }
    functions = {
        "srgb_to_linear",
        "hlg_to_linear",
        "_png_chunk",
        "_png_text_chunk",
        "inject_png_metadata",
        "_pack_chromaticities",
        "_exr_attribute",
    }
    body: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                targets = [
                    target.id for target in node.targets if isinstance(target, ast.Name)
                ]
            elif isinstance(node.target, ast.Name):
                targets = [node.target.id]
            if any(target in assignments for target in targets):
                body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            body.append(node)
    namespace: dict[str, Any] = {
        "torch": torch,
        "json": json,
        "struct": struct,
        "zlib": zlib,
    }
    exec(
        compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace


class ImageOutputContentTests(unittest.TestCase):
    def test_articles_recipes_and_research_are_valid_and_honest(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article.schema.v1.json"
        )
        recipe_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
        )
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), article_id)

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            headings = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
            semantic_h2 = [heading for heading in headings if heading != "Источники"]
            self.assertEqual(10, len(semantic_h2), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"является незаменим|данная нода|давайте разбер|подводя итог|"
                r"мощный инструмент|не просто .{0,80}, а",
            )

            for source in article["sources"]:
                url = source["url"]
                if "github.com/Comfy-Org/ComfyUI/" in url:
                    self.assertIn(
                        "c2bcbecd82ec5ae66594340b395c24ef0217b238", url
                    )
                if "github.com/Comfy-Org/embedded-docs/" in url:
                    self.assertIn(
                        "1d258cf6e374d60d138a2bfcd273c7e11f750ef9", url
                    )
                if "github.com/Comfy-Org/workflow_templates/" in url:
                    self.assertIn(
                        "cca1ea5ea4560108ecc2f44dee951f41ea433062", url
                    )

            record = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(record, research_schema))
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])
            self.assertNotEqual("human_approved", record["state"])

        self.assertEqual([], errors)

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertTrue(set(recipe["articleIds"]).issubset(article_ids))
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(
                all(external["to"] in refs for external in fragment["externalInputs"])
            )
            self.assertTrue(
                all(
                    edge["from"] in refs and edge["to"] in refs
                    for edge in fragment["connections"]
                )
            )

    def test_runtime_contracts_and_fingerprints(self) -> None:
        inventory = catalog.load_json(FULL_INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["pythonModule"], definition["python_module"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], definition),
            )

        loader = inventory["LoadImageOutput"]
        remote = loader["input"]["required"]["image"][1]["remote"]
        self.assertEqual("/internal/files/output", remote["route"])
        self.assertTrue(remote["refresh_button"])
        self.assertEqual("first", remote["control_after_refresh"])
        self.assertTrue(loader["experimental"])
        self.assertEqual(["IMAGE", "MASK"], loader["output"])

        webp = inventory["SaveAnimatedWEBP"]["input"]["required"]
        self.assertEqual((0.01, 1000.0), (webp["fps"][1]["min"], webp["fps"][1]["max"]))
        self.assertEqual((0, 100), (webp["quality"][1]["min"], webp["quality"][1]["max"]))
        self.assertEqual(["default", "fastest", "slowest"], webp["method"][1]["options"])

        apng = inventory["SaveAnimatedPNG"]["input"]["required"]
        self.assertEqual((0, 9), (apng["compress_level"][1]["min"], apng["compress_level"][1]["max"]))
        self.assertTrue(apng["compress_level"][1]["advanced"])

        advanced = inventory["SaveImageAdvanced"]["input"]["required"]["format"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", advanced[0])
        options = {option["key"]: option for option in advanced[1]["options"]}
        self.assertEqual({"png", "exr"}, set(options))
        png_inputs = options["png"]["inputs"]["required"]
        exr_inputs = options["exr"]["inputs"]["required"]
        self.assertEqual(["8-bit", "16-bit"], png_inputs["bit_depth"][1]["options"])
        self.assertEqual(["32-bit float"], exr_inputs["bit_depth"][1]["options"])
        self.assertEqual(["sRGB", "HDR", "linear"], exr_inputs["input_color_space"][1]["options"])

    def test_pinned_source_and_docs_boundaries(self) -> None:
        nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        ui = (SOURCE / "comfy_api" / "latest" / "_ui.py").read_text(encoding="utf-8")
        images = (SOURCE / "comfy_extras" / "nodes_images.py").read_text(encoding="utf-8")
        self.assertIn("class LoadImageOutput(LoadImage):", nodes)
        self.assertIn('"route": "/internal/files/output"', nodes)
        self.assertIn('"control_after_refresh": "first"', nodes)
        self.assertIn("m.update(f.read())", nodes)
        self.assertIn("1. - torch.from_numpy(mask)", nodes)

        self.assertIn("class SaveAnimatedWEBP(IO.ComfyNode):", images)
        self.assertIn('{"default": 4, "fastest": 0, "slowest": 6}', images)
        self.assertIn("class SaveAnimatedPNG(IO.ComfyNode):", images)
        self.assertIn("class SaveImageAdvanced(IO.ComfyNode):", images)
        self.assertIn("supported channel counts are 1 (grayscale), 3 (RGB) and 4 (RGBA)", images)
        self.assertIn("scaled = (img_tensor * spec[\"scale\"]).clamp", images)
        self.assertIn("# EXR path: preserve full range, no clamp.", images)

        self.assertIn("duration=int(1000.0 / fps)", ui)
        self.assertIn("save_all=True", ui)
        self.assertIn("append_images=pil_images[1:]", ui)
        self.assertIn("astype(np.uint8)", ui)
        self.assertIn("exif_data[0x0110]", ui)
        self.assertIn("b\"comf\"", ui)

        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for class_type in ("LoadImageOutput", "SaveImageAdvanced"):
                path = f"comfyui_embedded_docs/docs/{class_type}/en.md"
                self.assertIn(path, names)
                self.assertIn(
                    "This documentation was AI-generated",
                    archive.read(path).decode("utf-8"),
                )
            self.assertNotIn(
                "comfyui_embedded_docs/docs/SaveAnimatedWEBP/en.md", names
            )
            self.assertNotIn(
                "comfyui_embedded_docs/docs/SaveAnimatedPNG/en.md", names
            )

    def test_workflow_wheel_integrity_census_widgets_and_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        counts: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        files: dict[str, set[str]] = defaultdict(set)
        workflow_ids: dict[str, set[str]] = defaultdict(set)
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        widgets: dict[str, list[Any]] = defaultdict(list)
        json_count = 0
        workflow_count = 0
        representative: dict[str, Any] | None = None

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(
                name for name in archive.namelist() if name.endswith(".dist-info/RECORD")
            )
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(
                archive.read(record_name).decode("utf-8").splitlines()
            ):
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                payload = archive.read(name)
                actual = base64.urlsafe_b64encode(
                    hashlib.new(algorithm, payload).digest()
                ).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual)
                self.assertEqual(int(size), len(payload))
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                workflow_count += 1
                for record in workflow_records(payload, member):
                    node_type = record["node"].get("type")
                    if node_type not in TARGET_TYPES:
                        continue
                    counts[node_type] += 1
                    scopes[(node_type, record["scope"])] += 1
                    files[node_type].add(member)
                    workflow_ids[node_type].add(str(record["workflowId"]))
                    modes[node_type][record["node"].get("mode", 0)] += 1
                    widgets[node_type].append(record["node"].get("widgets_values"))
                if member.endswith("/video_wan2.1_alpha_t2v_14B.json"):
                    representative = payload

        self.assertEqual((512, 496), (json_count, workflow_count))
        self.assertEqual(Counter({"SaveImageAdvanced": 20, "SaveAnimatedWEBP": 5}), counts)
        self.assertEqual(20, scopes[("SaveImageAdvanced", "root")])
        self.assertEqual(5, scopes[("SaveAnimatedWEBP", "root")])
        self.assertFalse(any(scope == "subgraph" for _, scope in scopes))
        self.assertEqual((20, 5), (len(files["SaveImageAdvanced"]), len(files["SaveAnimatedWEBP"])))
        self.assertEqual((13, 3), (len(workflow_ids["SaveImageAdvanced"]), len(workflow_ids["SaveAnimatedWEBP"])))
        self.assertEqual(Counter({0: 20}), modes["SaveImageAdvanced"])
        self.assertEqual(Counter({4: 4, 0: 1}), modes["SaveAnimatedWEBP"])
        self.assertTrue(
            all(values[1:] == ["png", "8-bit", "sRGB"] for values in widgets["SaveImageAdvanced"])
        )
        self.assertEqual(
            [["ComfyUI", 16, True, 80, "default"]],
            [values for values in widgets["SaveAnimatedWEBP"] if values[1] == 16],
        )

        self.assertIsNotNone(representative)
        assert representative is not None
        by_id = {node["id"]: node for node in representative["nodes"]}
        links = {link[0]: link for link in representative["links"]}
        self.assertEqual("JoinImageWithAlpha", by_id[86]["type"])
        self.assertEqual("SaveAnimatedWEBP", by_id[80]["type"])
        self.assertEqual([176, 86, 0, 80, 0, "IMAGE"], links[176])
        self.assertEqual(["ComfyUI", 16, True, 80, "default"], by_id[80]["widgets_values"])

    def test_local_apng_and_webp_encoding_branches(self) -> None:
        frames: list[Image.Image] = []
        expected_pixels = [(50, 0, 0, 255), (0, 130, 0, 128), (0, 0, 210, 0)]
        for pixel in expected_pixels:
            array = np.empty((8, 10, 4), dtype=np.uint8)
            array[...] = pixel
            frames.append(Image.fromarray(array, "RGBA"))

        with tempfile.TemporaryDirectory() as temp_dir:
            apng_path = Path(temp_dir) / "synthetic.png"
            frames[0].save(
                apng_path,
                format="PNG",
                save_all=True,
                duration=int(1000.0 / 12.0),
                append_images=frames[1:],
                compress_level=4,
            )
            self.assertTrue(apng_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(apng_path) as decoded_apng:
                self.assertEqual(3, decoded_apng.n_frames)
                self.assertEqual(83.0, decoded_apng.info["duration"])
                self.assertEqual(
                    expected_pixels,
                    [
                        frame.convert("RGBA").getpixel((0, 0))
                        for frame in ImageSequence.Iterator(decoded_apng)
                    ],
                )

            webp_path = Path(temp_dir) / "synthetic.webp"
            frames[0].save(
                webp_path,
                format="WEBP",
                save_all=True,
                duration=int(1000.0 / 16.0),
                append_images=frames[1:],
                lossless=True,
                quality=80,
                method=4,
            )
            webp_bytes = webp_path.read_bytes()
            self.assertEqual(b"RIFF", webp_bytes[:4])
            self.assertEqual(b"WEBP", webp_bytes[8:12])
            with Image.open(webp_path) as decoded_webp:
                self.assertEqual(3, decoded_webp.n_frames)
                decoded_pixels = [
                    frame.convert("RGBA").getpixel((0, 0))
                    for frame in ImageSequence.Iterator(decoded_webp)
                ]
            self.assertEqual(expected_pixels[:2], decoded_pixels[:2])
            self.assertEqual(0, decoded_pixels[2][3])

    def test_pinned_color_and_png_metadata_helpers_execute_without_pyav(self) -> None:
        helpers = extract_advanced_helpers()
        srgb = torch.tensor([[[0.0, 0.04045, 0.5, 0.25]]], dtype=torch.float32)
        srgb_linear = helpers["srgb_to_linear"](srgb)
        self.assertAlmostEqual(0.0, float(srgb_linear[0, 0, 0]), places=7)
        self.assertAlmostEqual(0.04045 / 12.92, float(srgb_linear[0, 0, 1]), places=7)
        self.assertAlmostEqual(((0.5 + 0.055) / 1.055) ** 2.4, float(srgb_linear[0, 0, 2]), places=7)
        self.assertAlmostEqual(0.25, float(srgb_linear[0, 0, 3]), places=7)

        hlg = torch.tensor([[[0.0, 0.5, 1.0, 0.75]]], dtype=torch.float32)
        hlg_linear = helpers["hlg_to_linear"](hlg)
        self.assertAlmostEqual(0.0, float(hlg_linear[0, 0, 0]), places=7)
        self.assertAlmostEqual(1.0 / 12.0, float(hlg_linear[0, 0, 1]), places=7)
        self.assertAlmostEqual(1.0, float(hlg_linear[0, 0, 2]), places=6)
        self.assertAlmostEqual(0.75, float(hlg_linear[0, 0, 3]), places=7)

        base = io.BytesIO()
        Image.new("RGB", (2, 2), (1, 2, 3)).save(base, format="PNG")
        injected = helpers["inject_png_metadata"](
            base.getvalue(), {"node": "test"}, {"workflow": {"id": 1}}
        )
        self.assertGreater(len(injected), len(base.getvalue()))
        self.assertIn(b"prompt\x00", injected)
        self.assertIn(b"workflow\x00", injected)
        self.assertEqual(base.getvalue(), helpers["inject_png_metadata"](base.getvalue(), None, None))

        requirements = (SOURCE / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("av>=16.0.0", requirements)
        try:
            import av  # type: ignore  # noqa: F401
        except ModuleNotFoundError:
            self.assertIsNone(__import__("importlib.util").util.find_spec("av"))
        else:
            self.skipTest(
                "PyAV is available: this environment can add a separate pinned _encode_image codec test; current evidence remains limited to helpers."
            )


if __name__ == "__main__":
    unittest.main()
