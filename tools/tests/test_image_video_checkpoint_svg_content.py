from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.save-svg-node": {
        "directory": "save-svg-node",
        "classType": "SaveSVGNode",
        "module": "comfy_extras.nodes_images",
        "fingerprint": "sha256:5cabbfa7fbf8ce1c956da359c650ba7e858b69194240d2fb1722426f14a81f86",
        "recipe": "recipe.save-svg-output",
        "category": "image",
        "outputNode": True,
        "aliases": [],
    },
    "core.image-only-checkpoint-loader": {
        "directory": "image-only-checkpoint-loader",
        "classType": "ImageOnlyCheckpointLoader",
        "module": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:89c4a6121c666156a50360c768dcc20b32a6a5814fd3e57497cc884e27528a51",
        "recipe": "recipe.svd-image-only-checkpoint-conditioning",
        "category": "model/loaders",
        "outputNode": False,
        "aliases": [],
    },
    "core.svd-img2vid-conditioning": {
        "directory": "svd-img2vid-conditioning",
        "classType": "SVD_img2vid_Conditioning",
        "module": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:64ebd3cf6e9501846f4e2007248cc3a6e9e781fb63c2a5349a142731168f67b5",
        "recipe": "recipe.svd-image-only-checkpoint-conditioning",
        "category": "model/conditioning/stable video",
        "outputNode": False,
        "aliases": ["SDV_img2vid_Conditioning"],
    },
    "core.image-only-checkpoint-save": {
        "directory": "image-only-checkpoint-save",
        "classType": "ImageOnlyCheckpointSave",
        "module": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:9e9d8fea9016defeda4f94d75ed33d69b1bdad2e72de94bdd093b4e4f5d1eed7",
        "recipe": "recipe.save-image-only-checkpoint",
        "category": "model/merging",
        "outputNode": True,
        "aliases": [],
    },
}

RECIPE_DIRS = {
    "recipe.save-svg-output": "save-svg-output",
    "recipe.svd-image-only-checkpoint-conditioning": "svd-image-only-checkpoint-conditioning",
    "recipe.save-image-only-checkpoint": "save-image-only-checkpoint",
}

EXPECTED_CENSUS = {
    "SaveSVGNode": {"root": 7, "subgraph": 0, "files": 7, "uuids": 5, "modes": Counter({0: 5, 4: 2})},
    "ImageOnlyCheckpointLoader": {"root": 5, "subgraph": 0, "files": 5, "uuids": 5, "modes": Counter({0: 5})},
    "SVD_img2vid_Conditioning": {"root": 1, "subgraph": 0, "files": 1, "uuids": 1, "modes": Counter({0: 1})},
    "ImageOnlyCheckpointSave": {"root": 0, "subgraph": 0, "files": 0, "uuids": 0, "modes": Counter()},
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
FRONTEND = ROOT / ".frontend-source-1.48.7"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = ROOT / "tools" / "tests" / "image_video_checkpoint_svg_synthetic_probe.py"

DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOC_HASHES = {
    "SaveSVGNode": {
        "en": "fa919fd197397218feb1256cfd614156fe25170df2c3d7b1f3c63b1fbdbe3925",
        "ru": "dae083881b7ffd61a62eba29b726e071e9946565f3c8e1a07271972937ac4517",
    },
    "ImageOnlyCheckpointLoader": {
        "en": "f63b047f5a7bbe58132136e794188f345482eba420d51baaf938719cfa3ca899",
        "ru": "50cfa90dc411b1785d37ddbbc9c64c68c2746af8e7e575811d1ddbc8685c2ed1",
    },
    "SVD_img2vid_Conditioning": {
        "en": "35ee8b4bc02668ba2ff72b04b8c6e4e88f0765da2faf17ea231a6c8f616713cb",
        "ru": "bf074caa02ca44a637332eb7c64a3d719538762f776af4e9a4876e7791139e6a",
    },
    "ImageOnlyCheckpointSave": {
        "en": "2a213c82c1d672a4812a58c2bbcd5ccbbd1c1f95a467f879b37e2b49add2d6f5",
        "ru": "e8649dbc5996219c220796dfba87a03178c6a32a2c49ff63e871a61921551590",
    },
}


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        data = catalog.load_json(path)
        if isinstance(data, dict) and isinstance(data.get("articleId"), str):
            result.add(data["articleId"])
    return result


def graph_scopes(payload: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield "subgraph", subgraph


class ImageVideoCheckpointSvgContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        ids = all_article_ids()
        article_errors: list[str] = []
        recipe_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
            r"не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(spec["aliases"], article["runtimeIdentity"]["aliases"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            self.assertNotIn("approved", json.dumps(article).lower())

            targets = list(article["relations"]["related"]) + list(article["relations"]["alternatives"])
            if article["relations"]["replacedBy"] is not None:
                targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(targets).issubset(ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)
            self.assertNotIn("Вот перевод", body)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))
            self.assertNotIn("human_approved", json.dumps(ledger).lower())

        self.assertEqual([], article_errors)

        for recipe_id, directory in RECIPE_DIRS.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            self.assertNotIn("approved", json.dumps(recipe).lower())
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body, cliches)
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_and_replacement(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual(spec["category"], definition["category"])
            self.assertEqual(spec["outputNode"], bool(definition.get("output_node", False)))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            self.assertFalse(bool(definition.get("deprecated", False)))
            self.assertFalse(bool(definition.get("experimental", False)))
            self.assertFalse(bool(definition.get("api_node", False)))

        svg = inventory["SaveSVGNode"]
        self.assertEqual(["svg", "filename_prefix"], svg["input_order"]["required"])
        self.assertEqual(["SVG"], svg["output"])
        self.assertEqual(["svg"], svg["output_name"])
        self.assertEqual("svg/ComfyUI", svg["input"]["required"]["filename_prefix"][1]["default"])

        loader = inventory["ImageOnlyCheckpointLoader"]
        self.assertEqual(["ckpt_name"], loader["input_order"]["required"])
        self.assertEqual(["MODEL", "CLIP_VISION", "VAE"], loader["output"])

        svd = inventory["SVD_img2vid_Conditioning"]
        self.assertEqual(
            ["clip_vision", "init_image", "vae", "width", "height", "video_frames", "motion_bucket_id", "fps", "augmentation_level"],
            svd["input_order"]["required"],
        )
        self.assertEqual(["CONDITIONING", "CONDITIONING", "LATENT"], svd["output"])
        self.assertEqual(["positive", "negative", "latent"], svd["output_name"])
        self.assertEqual(8, svd["input"]["required"]["width"][1]["step"])
        self.assertEqual(4096, svd["input"]["required"]["video_frames"][1]["max"])
        self.assertTrue(svd["input"]["required"]["motion_bucket_id"][1]["advanced"])

        save = inventory["ImageOnlyCheckpointSave"]
        self.assertEqual(["model", "clip_vision", "vae", "filename_prefix"], save["input_order"]["required"])
        self.assertEqual([], save["output"])
        self.assertEqual("checkpoints/ComfyUI", save["input"]["required"]["filename_prefix"][1]["default"])

        replacements = catalog.load_json(REPLACEMENTS)
        self.assertEqual(
            "SVD_img2vid_Conditioning",
            replacements["SDV_img2vid_Conditioning"][0]["new_node_id"],
        )
        for node_id in ("SaveSVGNode", "ImageOnlyCheckpointLoader", "ImageOnlyCheckpointSave"):
            self.assertNotIn(node_id, replacements)

    def test_pinned_source_contract_and_frontend_filename_scope(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        self.assertEqual(FRONTEND_COMMIT, (FRONTEND / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        video_source = (SOURCE / "comfy_extras" / "nodes_video_model.py").read_text(encoding="utf-8")
        images_source = (SOURCE / "comfy_extras" / "nodes_images.py").read_text(encoding="utf-8")
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(encoding="utf-8")
        folder_source = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        frontend_source = (FRONTEND / "src" / "extensions" / "core" / "saveImageExtraOutput.ts").read_text(encoding="utf-8")

        self.assertIn("output_clip=False, output_clipvision=True", video_source)
        self.assertIn("return (out[0], out[3], out[2])", video_source)
        self.assertIn("output = clip_vision.encode_image(init_image)", video_source)
        self.assertIn('common_upscale(init_image.movedim(-1,1), width, height, "bilinear", "center")', video_source)
        self.assertIn("encode_pixels += torch.randn_like(pixels) * augmentation_level", video_source)
        self.assertIn("torch.zeros([video_frames, 4, height // 8, width // 8])", video_source)
        self.assertIn("clip_vision=clip_vision, vae=vae", video_source)
        self.assertIn("fps_id = kwargs.get(\"fps\", 6) - 1", model_base)

        self.assertIn('filename.replace("%batch_num%", str(batch_number))', images_source)
        self.assertIn("re.sub(r'(<svg[^>]*>)'", images_source)
        self.assertNotIn("disable_metadata", images_source[images_source.index("class SaveSVGNode"):images_source.index("class GetImageSize")])
        self.assertIn("return IO.NodeOutput(svg, ui={\"images\": results})", images_source)
        self.assertIn("os.path.realpath(directory)", folder_source)
        self.assertIn("os.walk(directory, followlinks=True, topdown=True)", folder_source)

        save_set = frontend_source[frontend_source.index("const saveNodeTypes"):frontend_source.index("])", frontend_source.index("const saveNodeTypes"))]
        self.assertIn("'SaveSVGNode'", save_set)
        self.assertNotIn("'ImageOnlyCheckpointSave'", save_set)

    def test_embedded_docs_hashes_and_known_contract_gaps(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for node_id, by_locale in DOC_HASHES.items():
                prefix = f"comfyui_embedded_docs/docs/{node_id}/"
                files = [name for name in archive.namelist() if name.startswith(prefix) and name.endswith(".md")]
                self.assertEqual(12, len(files), node_id)
                for locale, expected in by_locale.items():
                    payload = archive.read(f"{prefix}{locale}.md")
                    self.assertEqual(expected, hashlib.sha256(payload).hexdigest(), (node_id, locale))

            svg_en = archive.read("comfyui_embedded_docs/docs/SaveSVGNode/en.md").decode("utf-8")
            self.assertIn("| `ui` |", svg_en)
            self.assertNotIn("cursor", svg_en.lower())
            loader_en = archive.read("comfyui_embedded_docs/docs/ImageOnlyCheckpointLoader/en.md").decode("utf-8")
            self.assertNotIn("Hunyuan", loader_en)
            svd_en = archive.read("comfyui_embedded_docs/docs/SVD_img2vid_Conditioning/en.md").decode("utf-8")
            self.assertNotIn("fps - 1", svd_en)
            save_en = archive.read("comfyui_embedded_docs/docs/ImageOnlyCheckpointSave/en.md").decode("utf-8")
            self.assertNotIn("modelspec", save_en)

    def test_workflow_wheel_record_full_census_and_exact_topologies(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        files: dict[str, set[str]] = defaultdict(set)
        uuids: dict[str, set[str]] = defaultdict(set)
        root_graphs = root_nodes = subgraphs = subgraph_nodes = 0
        targets = set(EXPECTED_CENSUS)

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            names = set(archive.namelist())
            record_name = next(name for name in names if name.endswith(".dist-info/RECORD"))
            rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
            self.assertEqual(len(names), len(rows))
            for name, encoded_hash, encoded_size in rows:
                self.assertIn(name, names)
                if name == record_name:
                    self.assertEqual(("", ""), (encoded_hash, encoded_size))
                    continue
                payload = archive.read(name)
                algorithm, digest = encoded_hash.split("=", 1)
                expected = base64.urlsafe_b64decode(digest + "=" * (-len(digest) % 4))
                self.assertEqual(hashlib.new(algorithm, payload).digest(), expected, name)
                self.assertEqual(len(payload), int(encoded_size), name)

            json_names = [name for name in names if name.endswith(".json")]
            self.assertEqual(512, len(json_names))
            for name in json_names:
                payload = json.loads(archive.read(name))
                for scope, graph in graph_scopes(payload):
                    graph_nodes = graph["nodes"]
                    if scope == "root":
                        root_graphs += 1
                        root_nodes += len(graph_nodes)
                    else:
                        subgraphs += 1
                        subgraph_nodes += len(graph_nodes)
                    for node in graph_nodes:
                        node_type = node.get("type")
                        if node_type not in targets:
                            continue
                        counts[node_type][scope] += 1
                        modes[node_type][int(node.get("mode", 0))] += 1
                        files[node_type].add(name)
                        root_uuid = payload.get("id") if isinstance(payload, dict) else None
                        if root_uuid is not None:
                            uuids[node_type].add(str(root_uuid))

            self.assertEqual((496, 4083, 272, 4037), (root_graphs, root_nodes, subgraphs, subgraph_nodes))
            for node_type, expected in EXPECTED_CENSUS.items():
                self.assertEqual(expected["root"], counts[node_type]["root"], node_type)
                self.assertEqual(expected["subgraph"], counts[node_type]["subgraph"], node_type)
                self.assertEqual(expected["files"], len(files[node_type]), node_type)
                self.assertEqual(expected["uuids"], len(uuids[node_type]), node_type)
                self.assertEqual(expected["modes"], modes[node_type], node_type)

            svd_graph = json.loads(archive.read("comfyui_workflow_templates_json/templates/txt_to_image_to_video.json"))
            by_id = {node["id"]: node for node in svd_graph["nodes"]}
            self.assertEqual(["svd_xt.safetensors"], by_id[15]["widgets_values"])
            self.assertEqual([1024, 576, 25, 127, 6, 0], by_id[12]["widgets_values"])
            self.assertEqual([1], by_id[14]["widgets_values"])
            self.assertEqual([237514639057514, "randomize", 20, 2.5, "euler", "karras", 1], by_id[3]["widgets_values"])
            self.assertEqual([10], by_id[25]["widgets_values"])
            links = {tuple(link[1:6]) for link in svd_graph["links"]}
            for exact_link in {
                (15, 0, 14, 0, "MODEL"),
                (15, 1, 12, 0, "CLIP_VISION"),
                (15, 2, 12, 2, "VAE"),
                (12, 0, 3, 1, "CONDITIONING"),
                (12, 1, 3, 2, "CONDITIONING"),
                (12, 2, 3, 3, "LATENT"),
            }:
                self.assertIn(exact_link, links)

            quiver = json.loads(archive.read("comfyui_workflow_templates_json/templates/api_quiver_image_to_svg.json"))
            quiver_nodes = {node["id"]: node for node in quiver["nodes"]}
            self.assertEqual("SaveSVGNode", quiver_nodes[3]["type"])
            self.assertEqual(["svg/Quiver"], quiver_nodes[3]["widgets_values"])
            self.assertIn((1, 0, 3, 0, "SVG"), {tuple(link[1:6]) for link in quiver["links"]})

            hunyuan = json.loads(archive.read("comfyui_workflow_templates_json/templates/3d_hunyuan3d-v2.1.json"))
            hnodes = {node["id"]: node for node in hunyuan["nodes"]}
            self.assertEqual("ImageOnlyCheckpointLoader", hnodes[1]["type"])
            self.assertEqual(["hunyuan_3d_v2.1.safetensors"], hnodes[1]["widgets_values"])

            raw_members = b"\n".join(archive.read(name) for name in names if not name.endswith("/"))
            self.assertNotIn(b"SDV_img2vid_Conditioning", raw_members)

    def test_exact_source_model_free_probe(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        result = json.loads(completed.stdout)
        self.assertFalse(result["workflowExampleExecuted"])

        svg = result["svg"]
        self.assertEqual(["wizard-0_00001_.svg", "wizard-1_00002_.svg"], svg["files"])
        self.assertTrue(svg["passthroughIdentity"])
        self.assertEqual([True, True], svg["cursorAtEof"])
        self.assertEqual([1, 2], svg["metadataCounts"])
        self.assertTrue(svg["extraPromptOverridesHiddenPrompt"])
        self.assertTrue(svg["noSvgTagStillWritten"])
        self.assertTrue(svg["cdataTerminatorUnescaped"])
        self.assertTrue(svg["invalidUtf8Rejected"])

        video = result["videoNodes"]
        self.assertEqual(["MODEL", "CLIP_VISION", "VAE"], video["loader"]["outputs"])
        self.assertFalse(video["loader"]["call"]["output_clip"])
        self.assertTrue(video["loader"]["call"]["output_clipvision"])
        self.assertTrue(video["loader"]["pathErrorPropagated"])
        self.assertTrue(video["conditioning"]["clipReceivesOriginalIdentity"])
        self.assertTrue(video["conditioning"]["centerCropMatchesExpected"])
        self.assertEqual([5, 4, 1, 2], video["conditioning"]["latentShape"])
        self.assertEqual([2, 4, 1, 2], video["conditioning"]["directNonMultipleOfEightShape"])
        self.assertTrue(video["conditioning"]["rgbaAlphaDroppedAtZeroAugmentation"])
        self.assertTrue(video["conditioning"]["rgbaAugmentationShapeError"])
        self.assertTrue(video["imageOnlySave"]["returnsEmptyObject"])
        self.assertEqual("CLIP_VISION", video["imageOnlySave"]["call"]["clip_vision"])

        checkpoint = result["sharedCheckpoint"]
        base = checkpoint["base"]
        collision = checkpoint["collision"]
        self.assertFalse(base["clip"])
        self.assertTrue(base["clipVision"] and base["vae"])
        self.assertEqual(["edm_vpred.sigma_max", "edm_vpred.sigma_min"], base["extraKeys"])
        self.assertNotIn("modelspec.predict_key", base["metadata"])
        self.assertEqual("stable-video-diffusion-img2vid-v1", base["metadata"]["modelspec.architecture"])
        self.assertEqual('"override"', collision["metadata"]["modelspec.architecture"])
        self.assertEqual('"extra"', collision["metadata"]["prompt"])


if __name__ == "__main__":
    unittest.main()
