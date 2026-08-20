from __future__ import annotations

import hashlib
import json
import os
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
    "core.stable-cascade-empty-latent-image": {
        "directory": "stable-cascade-empty-latent-image",
        "classType": "StableCascade_EmptyLatentImage",
        "fingerprint": "sha256:6d74438e305355693ec43e71e1c530cb5f4ce00858377f5f0233bd69fbc1b7ed",
        "recipe": "recipe.stable-cascade-official-two-stage",
        "experimental": False,
    },
    "core.stable-cascade-stage-b-conditioning": {
        "directory": "stable-cascade-stage-b-conditioning",
        "classType": "StableCascade_StageB_Conditioning",
        "fingerprint": "sha256:f037402f9354c527bbb9b7599fc88670300b7ddeb85d9b78caabcf32985ff2dc",
        "recipe": "recipe.stable-cascade-official-two-stage",
        "experimental": False,
    },
    "core.stable-cascade-stage-c-vae-encode": {
        "directory": "stable-cascade-stage-c-vae-encode",
        "classType": "StableCascade_StageC_VAEEncode",
        "fingerprint": "sha256:0281b1de297bfb71b2fc4f4e1d0912bb436bfec341ada1d2593efce89fc6d15b",
        "recipe": "recipe.stable-cascade-stage-c-img2img",
        "experimental": False,
    },
    "core.stable-cascade-super-resolution-controlnet": {
        "directory": "stable-cascade-super-resolution-controlnet",
        "classType": "StableCascade_SuperResolutionControlnet",
        "fingerprint": "sha256:d8289df9675a1aa69055e0537257d522eca4c14e3dca5acceaf71d20d11cee71",
        "recipe": "recipe.stable-cascade-super-resolution-source",
        "experimental": True,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.stable-cascade-official-two-stage": "stable-cascade-official-two-stage",
    "recipe.stable-cascade-stage-c-img2img": "stable-cascade-stage-c-img2img",
    "recipe.stable-cascade-super-resolution-source": "stable-cascade-super-resolution-source",
}

EXPECTED_HEADINGS = [
    "Что делает нода",
    "Когда использовать и когда не использовать",
    "Короткий рецепт подключения",
    "Входы, выходы и параметры",
    "Типовые связки",
    "Практический пример",
    "Частые ошибки и способы проверки",
    "Производительность и внутреннее поведение",
    "Совместимость, изменения и устаревание",
    "Связанные ноды и источники",
]

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("stable_cascade_nodes_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
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


def workflow_graphs(payload: dict[str, Any], path: str = "root") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield path, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph, f"{path}/subgraph[{index}]")


class StableCascadeContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_editorial_contract(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте|"
            r"вот перевод|ключевую роль|мощный инструмент",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            targets = (
                article["relations"]["related"]
                + article["relations"]["alternatives"]
                + ([article["relations"]["replacedBy"]] if article["relations"]["replacedBy"] else [])
            )
            self.assertTrue(set(targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_stable_cascade", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["officialCasesInspected"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("человечес" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche_pattern)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_contracts(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        expected_categories = {
            "StableCascade_EmptyLatentImage": "model/latent/stable cascade",
            "StableCascade_StageB_Conditioning": "model/conditioning/stable cascade",
            "StableCascade_StageC_VAEEncode": "model/latent/stable cascade",
            "StableCascade_SuperResolutionControlnet": "experimental/stable cascade",
        }
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_stable_cascade", runtime["python_module"])
            self.assertEqual(expected_categories[spec["classType"]], runtime["category"])
            self.assertFalse(runtime["deprecated"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))

        empty = nodes["StableCascade_EmptyLatentImage"]
        self.assertEqual(["width", "height", "compression", "batch_size"], empty["input_order"]["required"])
        self.assertEqual(["LATENT", "LATENT"], empty["output"])
        self.assertEqual(["stage_c", "stage_b"], empty["output_name"])
        for name in ("width", "height"):
            self.assertEqual(
                {"default": 1024, "min": 256, "max": 16384, "step": 8},
                empty["input"]["required"][name][1],
            )
        compression = {"advanced": True, "default": 42, "min": 4, "max": 128, "step": 1}
        self.assertEqual(compression, empty["input"]["required"]["compression"][1])
        self.assertEqual({"default": 1, "min": 1, "max": 4096}, empty["input"]["required"]["batch_size"][1])

        stage_b = nodes["StableCascade_StageB_Conditioning"]
        self.assertEqual(["conditioning", "stage_c"], stage_b["input_order"]["required"])
        self.assertEqual(["CONDITIONING"], stage_b["output"])
        self.assertEqual(["CONDITIONING"], stage_b["output_name"])

        stage_c = nodes["StableCascade_StageC_VAEEncode"]
        self.assertEqual(["image", "vae", "compression"], stage_c["input_order"]["required"])
        self.assertEqual(compression, stage_c["input"]["required"]["compression"][1])
        self.assertEqual(["LATENT", "LATENT"], stage_c["output"])
        self.assertEqual(["stage_c", "stage_b"], stage_c["output_name"])

        super_resolution = nodes["StableCascade_SuperResolutionControlnet"]
        self.assertEqual(["image", "vae"], super_resolution["input_order"]["required"])
        self.assertEqual(["IMAGE", "LATENT", "LATENT"], super_resolution["output"])
        self.assertEqual(["controlnet_input", "stage_c", "stage_b"], super_resolution["output_name"])

        fragments: dict[str, dict[str, Any]] = {}
        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            fragments[recipe_id] = fragment
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                self.assertTrue(set(node["settings"]).issubset(runtime_inputs(dict(nodes[node["classType"]]))))
            for external in fragment["externalInputs"]:
                target = refs[external["to"]]
                accepted = runtime_inputs(dict(nodes[target["classType"]]))[external["input"]][0]
                self.assertIn(external["type"], accepted.split(","))

        official = fragments["recipe.stable-cascade-official-two-stage"]
        self.assertEqual(
            ["StableCascade_EmptyLatentImage", "KSampler", "StableCascade_StageB_Conditioning", "KSampler"],
            [node["classType"] for node in official["nodes"]],
        )
        self.assertEqual(
            {"width": 1024, "height": 1024, "compression": 42, "batch_size": 1},
            official["nodes"][0]["settings"],
        )
        self.assertEqual(
            {"seed": 314307448448003, "steps": 20, "cfg": 4.0, "sampler_name": "euler_ancestral", "scheduler": "simple", "denoise": 1.0},
            official["nodes"][1]["settings"],
        )
        self.assertEqual(
            {"seed": 183495397600639, "steps": 10, "cfg": 1.1, "sampler_name": "euler_ancestral", "scheduler": "simple", "denoise": 1.0},
            official["nodes"][3]["settings"],
        )
        self.assertEqual(
            [
                ("empty", "stage_c", "sample_c", "latent_image"),
                ("empty", "stage_b", "sample_b", "latent_image"),
                ("sample_c", "LATENT", "prepare_b", "stage_c"),
                ("prepare_b", "CONDITIONING", "sample_b", "positive"),
            ],
            [(c["from"], c["output"], c["to"], c["input"]) for c in official["connections"]],
        )

        img2img = fragments["recipe.stable-cascade-stage-c-img2img"]
        self.assertEqual({"compression": 32}, img2img["nodes"][0]["settings"])
        self.assertEqual(0.6, img2img["nodes"][1]["settings"]["denoise"])
        self.assertEqual(1.0, img2img["nodes"][3]["settings"]["denoise"])
        self.assertEqual(4, len(img2img["connections"]))

        source_derived = fragments["recipe.stable-cascade-super-resolution-source"]
        self.assertEqual(["StableCascade_SuperResolutionControlnet"], [node["classType"] for node in source_derived["nodes"]])
        self.assertEqual({}, source_derived["nodes"][0]["settings"])
        self.assertEqual([], source_derived["connections"])

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_exact_source_docs_and_replacement_contracts(self) -> None:
        source = (SOURCE / "comfy_extras" / "nodes_stable_cascade.py").read_text(encoding="utf-8")
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(encoding="utf-8")
        stage_b = (SOURCE / "comfy" / "ldm" / "cascade" / "stage_b.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        for marker in (
            "c_latent = torch.zeros([batch_size, 16, height // compression, width // compression])",
            "b_latent = torch.zeros([batch_size, 4, height // 4, width // 4])",
            'd["stable_cascade_prior"] = stage_c["samples"]',
            'common_upscale(image.movedim(-1,1), out_width, out_height, "bicubic", "center")',
            "c_latent = vae.encode(s[:,:,:,:3])",
            "(height // 8) * 2, (width // 8) * 2",
            "is_experimental=True",
            "controlnet_input = vae.encode(image[:,:,:,:3]).movedim(1, -1)",
            "height // 16, width // 16",
            "height // 2, width // 2",
        ):
            self.assertIn(marker, source)
        self.assertIn('kwargs.get("stable_cascade_prior"', model_base)
        self.assertIn('out["effnet"] = comfy.conds.CONDRegular(prior.to(device=noise.device))', model_base)
        self.assertIn("nn.functional.interpolate(effnet, size=x.shape[-2:]", stage_b)
        self.assertIn("self.downscale_ratio = 32", sd)
        self.assertIn('if crop == "center":', utils)
        self.assertIn('mode=upscale_method', utils)

        replacements = catalog.load_json(REPLACEMENTS)
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        for records in replacements.values():
            for record in records:
                self.assertNotIn(record.get("old_node_id"), targets)
                self.assertNotIn(record.get("new_node_id"), targets)

        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for class_type in targets:
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    text = archive.read(member).decode("utf-8")
                    self.assertIn("Source fingerprint", text)

    def test_full_official_workflow_wheel_census_is_explicitly_empty(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        file_count = root_count = graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for _graph_path, graph in workflow_graphs(payload):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in targets:
                            counts[node["type"]] += 1

        self.assertEqual(512, file_count)
        self.assertEqual(496, root_count)
        self.assertEqual(768, graph_count)
        self.assertEqual(Counter(), counts)

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_safe_exact_source_stable_cascade_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no probe Python")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python == Path(sys.executable):
            self.skipTest(f"torch unavailable: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        empty = payload["empty"]
        self.assertEqual([2, 16, 18, 23], empty["stageCShape"])
        self.assertEqual([2, 4, 192, 250], empty["stageBShape"])
        self.assertEqual("torch.float32", empty["stageCDtype"])
        self.assertEqual("cpu", empty["stageCDevice"])
        self.assertTrue(empty["bothZero"])
        self.assertEqual([["samples"], ["samples"]], empty["onlySamplesKeys"])

        stage_b = payload["stageB"]
        self.assertEqual(2, stage_b["entryCount"])
        self.assertEqual([True, True], stage_b["embeddingsPreserved"])
        self.assertEqual([True, True], stage_b["metadataCopied"])
        self.assertEqual([True, True], stage_b["nestedMetadataIsShallow"])
        self.assertTrue(stage_b["sourceMetadataUnchanged"])
        self.assertTrue(stage_b["priorIdentityPreserved"])
        self.assertTrue(stage_b["nonSamplesStageCMetadataIgnored"])
        self.assertTrue(stage_b["missingSamplesRaises"])

        stage_c = payload["stageC"]
        self.assertEqual([2, 96, 128, 3], stage_c["vaeInputShape"])
        self.assertTrue(stage_c["centerCropAndBicubicMatch"])
        self.assertTrue(stage_c["alphaDropped"])
        self.assertEqual([2, 16, 3, 4], stage_c["stageCShape"])
        self.assertEqual([2, 4, 24, 38], stage_c["stageBShape"])
        self.assertTrue(stage_c["stageBZero"])

        super_resolution = payload["superResolution"]
        self.assertEqual([2, 33, 65, 3], super_resolution["vaeInputShape"])
        self.assertTrue(super_resolution["alphaDropped"])
        self.assertEqual([2, 1, 2, 16], super_resolution["controlShape"])
        self.assertTrue(super_resolution["controlMatchesEncodedNHWC"])
        self.assertEqual([2, 16, 2, 4], super_resolution["stageCShape"])
        self.assertEqual([2, 4, 16, 32], super_resolution["stageBShape"])
        self.assertTrue(super_resolution["latentsZero"])
        self.assertEqual("torch.float32", super_resolution["latentDtype"])
        self.assertEqual("cpu", super_resolution["latentDevice"])


if __name__ == "__main__":
    unittest.main()
