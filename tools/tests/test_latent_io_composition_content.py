from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.latent-composite": {
        "directory": "latent-composite",
        "classType": "LatentComposite",
        "pythonModule": "nodes",
        "fingerprint": "sha256:e4ef563242305bba85371caa2327db0c06a947f50f4f27cc8ae611bcb7f7db92",
        "recipe": "recipe.composite-latents-with-feather",
    },
    "core.load-latent": {
        "directory": "load-latent",
        "classType": "LoadLatent",
        "pythonModule": "nodes",
        "fingerprint": "sha256:a3e54162b1ea53e9d1b7a63ef31ced76348e19c410798e9602b3d39745515a31",
        "recipe": "recipe.load-latent-preview",
    },
    "core.save-latent": {
        "directory": "save-latent",
        "classType": "SaveLatent",
        "pythonModule": "nodes",
        "fingerprint": "sha256:dc2ac40f84ee6776529071b553054d613b48f4d59f4a6658bcbe42b003a8f061",
        "recipe": "recipe.save-latent-file",
    },
    "core.trim-video-latent": {
        "directory": "trim-video-latent",
        "classType": "TrimVideoLatent",
        "pythonModule": "comfy_extras.nodes_wan",
        "fingerprint": "sha256:cfc5865170d2ef40ef70d67398f2f471cee79deb67cf782c49ce079cf89a8e78",
        "recipe": "recipe.trim-vace-latent-before-decode",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.composite-latents-with-feather": "composite-latents-with-feather",
    "recipe.load-latent-preview": "load-latent-preview",
    "recipe.save-latent-file": "save-latent-file",
    "recipe.trim-vace-latent-before-decode": "trim-vace-latent-before-decode",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.composite-latents-with-feather": [
        ("LatentComposite", {"x": 64, "y": 64, "feather": 32}),
        ("VAEDecode", {}),
        ("PreviewImage", {}),
    ],
    "recipe.load-latent-preview": [
        ("LoadLatent", {"latent": "выберите установленный .latent"}),
        ("VAEDecode", {}),
        ("PreviewImage", {}),
    ],
    "recipe.save-latent-file": [
        ("SaveLatent", {"filename_prefix": "latents/wizard-session"}),
    ],
    "recipe.trim-vace-latent-before-decode": [
        ("TrimVideoLatent", {"trim_amount": 0}),
        ("VAEDecode", {}),
        ("PreviewImage", {}),
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
SYNTHETIC_PROBE = Path(__file__).with_name(
    "latent_io_composition_synthetic_probe.py"
)
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def article_path(spec: dict[str, str]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def input_type(descriptor: Any) -> str:
    if isinstance(descriptor, (list, tuple)) and descriptor:
        first = descriptor[0]
        if isinstance(first, str):
            return first
        if isinstance(first, list):
            return "COMBO"
    raise AssertionError(f"unsupported runtime descriptor: {descriptor!r}")


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "scope": "root", "node": node, "graph": payload}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "scope": "subgraph",
                    "node": node,
                    "graph": subgraph,
                }


def normalized_link(link: Any) -> dict[str, Any]:
    if isinstance(link, list):
        return {
            "id": link[0],
            "origin_id": link[1],
            "origin_slot": link[2],
            "target_id": link[3],
            "target_slot": link[4],
            "type": link[5],
        }
    if isinstance(link, dict):
        return link
    raise AssertionError(f"unsupported workflow link: {link!r}")


class LatentIoCompositionContentTests(unittest.TestCase):
    def test_articles_and_fragment_only_recipes_validate(self) -> None:
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
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|мощн|революцион|уникальн|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"устали от|знакомо\?|успейте|не просто.+а|является незаменим|данная нода",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, re.MULTILINE)))
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(cliche_pattern.search(body))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("draft", recipe["editorial"]["state"])
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", recipe_body)
            self.assertIsNone(cliche_pattern.search(recipe_body))
            prose_without_code = re.sub(
                r"`[^`]+`|https?://\S+", "", recipe_body
            ).casefold()
            for untranslated in (
                " fragment",
                " workflow",
                " batch",
                " resize",
                " pinned",
                " runtime",
                " placeholder",
                " denoise",
                " legacy marker",
                " file branch",
                " exact-source",
                " sampled latent",
                " widget-",
                " output slot",
                " subgraph",
                " synthetic tensor",
            ):
                self.assertNotIn(untranslated, prose_without_code, recipe_id)

        self.assertEqual([], errors)

    def test_research_records_are_honest(self) -> None:
        schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        for article_id, spec in ARTICLE_SPECS.items():
            record = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(record, schema))
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["exampleSchemaValidated"])
            self.assertTrue(record["checks"]["russianEdited"])
            self.assertTrue(record["knownGaps"])
            self.assertTrue(any("human" in gap.lower() or "человечес" in gap.lower() for gap in record["knownGaps"]))

    def test_runtime_fingerprints_ports_settings_and_fragment_contracts(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual("model/latent", runtime["category"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("experimental", False))

        self.assertEqual(
            ["samples_to", "samples_from", "x", "y", "feather"],
            nodes["LatentComposite"]["input_order"]["required"],
        )
        for name in ("x", "y", "feather"):
            self.assertEqual(
                {"default": 0, "min": 0, "max": 16384, "step": 8},
                nodes["LatentComposite"]["input"]["required"][name][1],
            )
        self.assertEqual([[]], nodes["LoadLatent"]["input"]["required"]["latent"])
        self.assertEqual(
            {"default": "latents/ComfyUI"},
            nodes["SaveLatent"]["input"]["required"]["filename_prefix"][1],
        )
        self.assertTrue(nodes["SaveLatent"]["output_node"])
        self.assertEqual(["samples"], nodes["SaveLatent"]["output_name"])
        self.assertEqual(
            {"default": 0, "min": 0, "max": 99999},
            nodes["TrimVideoLatent"]["input"]["required"]["trim_amount"][1],
        )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = nodes[refs[external["to"]]["classType"]]
                descriptor = runtime_inputs(runtime)[external["input"]]
                self.assertEqual(external["type"], input_type(descriptor))
            for connection in fragment["connections"]:
                source = nodes[refs[connection["from"]]["classType"]]
                target = nodes[refs[connection["to"]]["classType"]]
                output_names = source.get("output_name") or source.get("output")
                output_index = output_names.index(connection["output"])
                self.assertEqual(
                    source["output"][output_index],
                    input_type(runtime_inputs(target)[connection["input"]]),
                )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_semantics_and_replacements(self) -> None:
        nodes_source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        wan_source = (SOURCE / "comfy_extras" / "nodes_wan.py").read_text(
            encoding="utf-8"
        )
        utils_source = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        paths_source = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)

        self.assertIn("x =  x // 8", nodes_source)
        self.assertIn("feather = feather // 8", nodes_source)
        self.assertIn("s = samples_to[\"samples\"].clone()", nodes_source)
        self.assertIn("mask = torch.ones_like(samples_from)", nodes_source)
        self.assertIn("samples_out[\"samples\"] = s", nodes_source)
        self.assertNotIn("common_upscale(samples_from", nodes_source)

        self.assertIn('output["latent_tensor"] = samples["samples"].contiguous()', nodes_source)
        self.assertIn('output["latent_format_version_0"] = torch.tensor([])', nodes_source)
        self.assertIn('return { "ui": { "latents": results }, "result": (samples,) }', nodes_source)
        self.assertIn('if "latent_format_version_0" not in latent:', nodes_source)
        self.assertIn("multiplier = 1.0 / 0.18215", nodes_source)
        self.assertIn('latent["latent_tensor"].float() * multiplier', nodes_source)
        self.assertIn("m.update(f.read())", nodes_source)
        self.assertIn("safetensors.torch.save_file", utils_source)
        self.assertIn("Saving image outside the output folder is not allowed", paths_source)

        self.assertIn('samples_out["samples"] = s1[:, :, trim_amount:]', wan_source)
        self.assertIn('io.Int.Output(display_name="trim_latent")', wan_source)
        self.assertIn("trim_latent = reference_image.shape[2]", wan_source)
        self.assertIn("class WanAnimate2ToVideo", wan_source)
        self.assertIn("trim_latent = ref_latent.shape[2]", wan_source)

        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_embedded_docs_discrepancies_are_recorded(self) -> None:
        self.assertEqual(
            DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest()
        )
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs = {
                class_type: archive.read(
                    f"comfyui_embedded_docs/docs/{class_type}/en.md"
                ).decode("utf-8")
                for class_type in TARGET_TYPES
            }
            load_ru = archive.read(
                "comfyui_embedded_docs/docs/LoadLatent/ru.md"
            ).decode("utf-8")

        self.assertTrue(
            all("This documentation was AI-generated" in docs[name] for name in TARGET_TYPES)
        )
        self.assertIn("A boolean indicating", docs["LatentComposite"])
        self.assertIn("preserving the latent data structure", docs["SaveLatent"])
        self.assertIn("applies any necessary scaling adjustments", docs["LoadLatent"])
        self.assertIn("number of frames to remove", docs["TrimVideoLatent"])
        self.assertIn("`скрытый`", load_ru)

        composite_article = (article_path(ARTICLE_SPECS["core.latent-composite"]).parent / "ru.md").read_text(encoding="utf-8")
        save_article = (article_path(ARTICLE_SPECS["core.save-latent"]).parent / "ru.md").read_text(encoding="utf-8")
        trim_article = (article_path(ARTICLE_SPECS["core.trim-video-latent"]).parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn("ошибочно назван логическим флагом resize", composite_article)
        self.assertIn("не сериализует весь словарь LATENT", save_article)
        self.assertIn("latent temporal slice", trim_article)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_trim_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        json_count = 0
        workflow_count = 0
        occurrences: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        trim_files: set[str] = set()
        vace_lengths: list[int] = []
        sample_origins: Counter[str] = Counter()
        amount_origins: Counter[str] = Counter()

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                workflow_count += 1
                for record in workflow_node_records(payload, member):
                    node_type = record["node"].get("type")
                    if node_type not in TARGET_TYPES:
                        continue
                    occurrences[node_type] += 1
                    scopes[(node_type, record["scope"])] += 1
                    if node_type != "TrimVideoLatent":
                        continue

                    trim = record["node"]
                    trim_files.add(Path(member).stem)
                    self.assertEqual(0, trim.get("mode", 0))
                    self.assertEqual([0], trim.get("widgets_values"))
                    graph = record["graph"]
                    by_id = {node["id"]: node for node in graph["nodes"]}
                    links = {
                        normalized_link(link)["id"]: normalized_link(link)
                        for link in graph["links"]
                    }
                    sample_link = links[trim["inputs"][0]["link"]]
                    amount_link = links[trim["inputs"][1]["link"]]
                    output_link = links[trim["outputs"][0]["links"][0]]
                    sample_type = by_id[sample_link["origin_id"]]["type"]
                    amount_type = by_id[amount_link["origin_id"]]["type"]
                    sample_origins[sample_type] += 1
                    amount_origins[amount_type] += 1
                    self.assertIn(sample_type, {"KSampler", "SamplerCustom"})
                    self.assertEqual(0, sample_link["origin_slot"])
                    self.assertIn(amount_type, {"WanVaceToVideo", "WanAnimate2ToVideo"})
                    self.assertEqual(3, amount_link["origin_slot"])
                    self.assertEqual("VAEDecode", by_id[output_link["target_id"]]["type"])
                    self.assertEqual(0, output_link["target_slot"])
                    vace_lengths.append(
                        by_id[amount_link["origin_id"]]["widgets_values"][2]
                    )

        self.assertEqual((512, 496), (json_count, workflow_count))
        self.assertEqual(Counter({"TrimVideoLatent": 8}), occurrences)
        self.assertEqual(4, scopes[("TrimVideoLatent", "root")])
        self.assertEqual(4, scopes[("TrimVideoLatent", "subgraph")])
        self.assertEqual(
            {
                "video_wan_animate2",
                "video_wan_vace_14B_ref2v",
                "video_wan_vace_14B_t2v",
                "video_wan_vace_14B_v2v",
                "video_wan_vace_flf2v",
                "video_wan_vace_inpainting",
                "video_wan_vace_outpainting",
            },
            trim_files,
        )
        self.assertEqual(Counter({"KSampler": 6, "SamplerCustom": 2}), sample_origins)
        self.assertEqual(
            Counter({"WanVaceToVideo": 6, "WanAnimate2ToVideo": 2}),
            amount_origins,
        )
        self.assertEqual([45, 45, 81, 81, 81, 81, 81, 81], sorted(vace_lengths))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_tensor_and_temp_file_probe(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        composite = report["latentComposite"]
        self.assertEqual([2, 4, 6, 7], composite["shape"])
        self.assertTrue(composite["broadcastSourceBatchOne"])
        self.assertEqual(32, composite["croppedNonzero"])
        self.assertEqual(0.25, composite["featherCorner"])
        self.assertEqual(1.0, composite["featherInner"])
        self.assertTrue(composite["metadataFromDestination"])
        self.assertTrue(composite["farOffsetError"])

        trim = report["trimVideoLatent"]
        self.assertEqual([2, 3, 4, 2, 2], trim["shape"])
        self.assertTrue(trim["sharesStorage"])
        self.assertEqual([2, 1, 6, 2, 2], trim["noiseMaskShapeUnchanged"])
        self.assertEqual([2, 3, 0, 2, 2], trim["oversizedTrimShape"])
        self.assertEqual([1, 4, 6, 8], trim["fourDimensionalInputShape"])

        file_roundtrip = report["fileRoundtrip"]
        self.assertEqual(
            ["latent_format_version_0", "latent_tensor"],
            file_roundtrip["savedKeys"],
        )
        self.assertEqual("torch.float16", file_roundtrip["savedDtype"])
        self.assertEqual("torch.float32", file_roundtrip["loadedDtype"])
        self.assertEqual(["prompt", "workflow"], file_roundtrip["metadataKeys"])
        self.assertAlmostEqual(1.0, file_roundtrip["legacyValue"], places=6)
        self.assertTrue(file_roundtrip["returnedOriginal"])
        self.assertTrue(file_roundtrip["pathTraversalBlocked"])


if __name__ == "__main__":
    unittest.main()
