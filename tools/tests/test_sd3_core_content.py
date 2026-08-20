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
    "core.triple-clip-loader": {
        "directory": "triple-clip-loader",
        "classType": "TripleCLIPLoader",
        "fingerprint": "sha256:26d64bb3acdbb35e98830ddf74210fd53afc7b92217183b648341a68f76dec7c",
        "recipe": "recipe.triple-clip-loader-sd3-source",
        "deprecated": False,
    },
    "core.empty-sd3-latent-image": {
        "directory": "empty-sd3-latent-image",
        "classType": "EmptySD3LatentImage",
        "fingerprint": "sha256:f60b690d166d83891b4fe199a0cf9df92fb71a88542d0042b99c7f92619d80ba",
        "recipe": "recipe.empty-sd3-latent-official-sampler",
        "deprecated": False,
    },
    "core.clip-text-encode-sd3": {
        "directory": "clip-text-encode-sd3",
        "classType": "CLIPTextEncodeSD3",
        "fingerprint": "sha256:14507522c5f912faee4968c2e8b867ee700ef54b7a424510baa04dd658de003d",
        "recipe": "recipe.clip-text-encode-sd3-source",
        "deprecated": False,
    },
    "core.control-net-apply-sd3": {
        "directory": "control-net-apply-sd3",
        "classType": "ControlNetApplySD3",
        "fingerprint": "sha256:337f9dbc1a7d5d33ad187593cad2c74ac81d2a98fb0abd242b8fa31183affab0",
        "recipe": "recipe.control-net-apply-sd3-legacy",
        "deprecated": True,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.triple-clip-loader-sd3-source": "triple-clip-loader-sd3-source",
    "recipe.empty-sd3-latent-official-sampler": "empty-sd3-latent-official-sampler",
    "recipe.clip-text-encode-sd3-source": "clip-text-encode-sd3-source",
    "recipe.control-net-apply-sd3-legacy": "control-net-apply-sd3-legacy",
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
PROBE = Path(__file__).with_name("sd3_nodes_synthetic_probe.py")


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


class SD3CoreContentTests(unittest.TestCase):
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
            r"данная нода|является незаменим|устали от|знакомо\?|успейте",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertFalse(article["experimental"])
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
            self.assertEqual("comfy_extras.nodes_sd3", research["node"]["pythonModule"])
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

    def test_runtime_fingerprints_flags_ports_and_fragments(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        expected_categories = {
            "TripleCLIPLoader": "model/loaders",
            "EmptySD3LatentImage": "model/latent/stable diffusion",
            "CLIPTextEncodeSD3": "model/conditioning/stable diffusion",
            "ControlNetApplySD3": "model/conditioning/controlnet",
        }
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_sd3", runtime["python_module"])
            self.assertEqual(expected_categories[spec["classType"]], runtime["category"])
            self.assertEqual(spec["deprecated"], runtime["deprecated"])
            self.assertFalse(runtime["experimental"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))

        triple = nodes["TripleCLIPLoader"]
        self.assertEqual(["clip_name1", "clip_name2", "clip_name3"], triple["input_order"]["required"])
        self.assertEqual(["CLIP"], triple["output"])
        self.assertEqual("Recipes:\nsd3: clip-l, clip-g, t5", triple["description"])
        for name in triple["input_order"]["required"]:
            self.assertEqual("COMBO", triple["input"]["required"][name][0])
            self.assertEqual([], triple["input"]["required"][name][1]["options"])

        empty = nodes["EmptySD3LatentImage"]
        self.assertEqual(["width", "height", "batch_size"], empty["input_order"]["required"])
        self.assertEqual(["LATENT"], empty["output"])
        for name in ("width", "height"):
            opts = empty["input"]["required"][name][1]
            self.assertEqual({"default": 1024, "min": 16, "max": 16384, "step": 16}, opts)
        self.assertEqual(
            {"default": 1, "min": 1, "max": 4096},
            empty["input"]["required"]["batch_size"][1],
        )

        encode = nodes["CLIPTextEncodeSD3"]
        self.assertEqual(["clip", "clip_l", "clip_g", "t5xxl", "empty_padding"], encode["input_order"]["required"])
        self.assertEqual(["CONDITIONING"], encode["output"])
        self.assertEqual(["sd3 prompt"], encode["search_aliases"])
        padding = encode["input"]["required"]["empty_padding"]
        self.assertEqual("COMBO", padding[0])
        self.assertEqual(["none", "empty_prompt"], padding[1]["options"])
        self.assertNotIn("default", padding[1])
        for name in ("clip_l", "clip_g", "t5xxl"):
            self.assertTrue(encode["input"]["required"][name][1]["multiline"])
            self.assertTrue(encode["input"]["required"][name][1]["dynamicPrompts"])

        control = nodes["ControlNetApplySD3"]
        self.assertEqual(
            ["positive", "negative", "control_net", "vae", "image", "strength", "start_percent", "end_percent"],
            control["input_order"]["required"],
        )
        self.assertEqual(["CONDITIONING", "CONDITIONING"], control["output"])
        self.assertEqual(["positive", "negative"], control["output_name"])
        self.assertEqual({"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}, control["input"]["required"]["strength"][1])
        self.assertEqual({"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}, control["input"]["required"]["start_percent"][1])
        self.assertEqual({"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}, control["input"]["required"]["end_percent"][1])

        expected_fragment_nodes = {
            "recipe.triple-clip-loader-sd3-source": [
                ("TripleCLIPLoader", {"clip_name1", "clip_name2", "clip_name3"})
            ],
            "recipe.empty-sd3-latent-official-sampler": [
                ("EmptySD3LatentImage", {"width", "height", "batch_size"}),
                ("KSampler", {"seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"}),
            ],
            "recipe.clip-text-encode-sd3-source": [
                ("CLIPTextEncodeSD3", {"clip_l", "clip_g", "t5xxl", "empty_padding"})
            ],
            "recipe.control-net-apply-sd3-legacy": [
                ("ControlNetApplySD3", {"strength", "start_percent", "end_percent"})
            ],
        }
        for recipe_id, expected in expected_fragment_nodes.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual(
                expected,
                [(node["classType"], set(node["settings"])) for node in fragment["nodes"]],
            )
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                self.assertTrue(set(node["settings"]).issubset(runtime_inputs(dict(nodes[node["classType"]]))))
            for external in fragment["externalInputs"]:
                target = refs[external["to"]]
                accepted = runtime_inputs(dict(nodes[target["classType"]]))[external["input"]][0]
                self.assertIn(external["type"], accepted.split(","))

        empty_recipe = catalog.load_json(recipe_path("recipe.empty-sd3-latent-official-sampler"))
        empty_fragment = catalog.load_json(
            recipe_path("recipe.empty-sd3-latent-official-sampler").parent / empty_recipe["fragment"]["path"]
        )
        self.assertEqual(
            {"width": 1024, "height": 1024, "batch_size": 1},
            empty_fragment["nodes"][0]["settings"],
        )
        self.assertEqual(
            {
                "seed": 585483408983215,
                "steps": 20,
                "cfg": 4.01,
                "sampler_name": "euler",
                "scheduler": "sgm_uniform",
                "denoise": 1.0,
            },
            empty_fragment["nodes"][1]["settings"],
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_exact_source_docs_and_replacement_contracts(self) -> None:
        sd3_nodes = (SOURCE / "comfy_extras" / "nodes_sd3.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        sd3_clip = (SOURCE / "comfy" / "text_encoders" / "sd3_clip.py").read_text(encoding="utf-8")
        sample = (SOURCE / "comfy" / "sample.py").read_text(encoding="utf-8")
        controlnet = (SOURCE / "comfy" / "controlnet.py").read_text(encoding="utf-8")
        generic_nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        for marker in (
            'io.Combo.Input("clip_name1", options=folder_paths.get_filename_list("text_encoders"))',
            "ckpt_paths=[clip_path1, clip_path2, clip_path3]",
            '"samples": latent, "downscale_ratio_spacial": 8',
            'no_padding = empty_padding == "none"',
            'tokens = clip.tokenize(clip_g)',
            'tokens["l"] += empty["l"]',
            'tokens["g"] += empty["g"]',
            "is_deprecated=True",
            "control_hint = image.movedim(-1, 1)",
            "d['control_apply_to_uncond'] = False",
            "extra_concat=[]",
        ):
            self.assertIn(marker, sd3_nodes)
        self.assertIn("elif len(clip_data) == 3:", sd)
        self.assertIn("clip_target.clip = comfy.text_encoders.sd3_clip.sd3_clip", sd)
        self.assertIn('out["g"] = self.clip_g.tokenize_with_weights', sd3_clip)
        self.assertIn("out = torch.cat([lg_out, t5_out], dim=-2)", sd3_clip)
        self.assertIn("is_empty = torch.count_nonzero(latent_image) == 0", sample)
        self.assertIn("latent_image = comfy.utils.repeat_to_batch_size", sample)
        self.assertIn("self.vae = vae", controlnet)
        self.assertIn("self.timestep_percent_range = timestep_percent_range", controlnet)
        self.assertIn("class ControlNetApplyAdvanced", generic_nodes)
        self.assertIn('"optional": {"vae": ("VAE", )', generic_nodes)

        replacements = catalog.load_json(REPLACEMENTS)
        for records in replacements.values():
            for record in records:
                self.assertNotEqual("ControlNetApplySD3", record.get("old_node_id"))
                self.assertNotEqual("ControlNetApplySD3", record.get("new_node_id"))

        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for class_type in (spec["classType"] for spec in ARTICLE_SPECS.values()):
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    text = archive.read(member).decode("utf-8")
                    self.assertIn("Source fingerprint", text)

    def test_full_official_workflow_census_and_exact_sd35_branch(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        locations: Counter[str] = Counter()
        widgets: Counter[tuple[Any, ...]] = Counter()
        outgoing: Counter[tuple[str | None, str]] = Counter()
        member_names: set[str] = set()
        official: tuple[dict[str, Any], dict[str, Any], list[Any]] | None = None
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
                for graph_path, graph in workflow_graphs(payload):
                    graph_count += 1
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {str(node.get("id")): node for node in nodes}
                    links = [link for link in graph.get("links", []) if isinstance(link, list) and len(link) >= 6]
                    for node in nodes:
                        class_type = node.get("type")
                        if class_type not in targets:
                            continue
                        counts[class_type] += 1
                        member_names.add(member)
                        if class_type == "EmptySD3LatentImage":
                            locations["root" if graph_path == "root" else "subgraph"] += 1
                            widgets[tuple(node.get("widgets_values") or [])] += 1
                            for link in links:
                                if str(link[1]) == str(node.get("id")):
                                    outgoing[(by_id.get(str(link[3]), {}).get("type"), str(link[5]))] += 1
                                if (
                                    member.endswith("/sd3.5_simple_example.json")
                                    and str(link[1]) == str(node.get("id"))
                                    and by_id.get(str(link[3]), {}).get("type") == "KSampler"
                                ):
                                    official = (node, by_id[str(link[3])], link)

        self.assertEqual(512, file_count)
        self.assertEqual(496, root_count)
        self.assertEqual(768, graph_count)
        self.assertEqual(Counter({"EmptySD3LatentImage": 37}), counts)
        self.assertEqual(Counter({"subgraph": 24, "root": 13}), locations)
        self.assertEqual(
            Counter({
                (1024, 1024, 1): 29,
                (1328, 1328, 1): 5,
                (1024, 1536, 1): 1,
                (2048, 1024, 1): 1,
                (1088, 1920, 1): 1,
            }),
            widgets,
        )
        self.assertEqual(Counter({("KSampler", "LATENT"): 9, ("SamplerCustomAdvanced", "LATENT"): 3}), outgoing)
        self.assertEqual(37, len(member_names))
        self.assertIsNotNone(official)
        empty, sampler, link = official or ({}, {}, [])
        self.assertEqual(53, empty["id"])
        self.assertEqual([1024, 1024, 1], empty["widgets_values"])
        self.assertEqual(3, sampler["id"])
        self.assertEqual(
            [585483408983215, "randomize", 20, 4.01, "euler", "sgm_uniform", 1],
            sampler["widgets_values"],
        )
        self.assertEqual("LATENT", link[5])

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_safe_exact_source_sd3_probe(self) -> None:
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

        triple = payload["triple"]
        self.assertEqual(
            [
                "/models/text_encoders/clip_l.safetensors",
                "/models/text_encoders/clip_g.safetensors",
                "/models/text_encoders/t5xxl_fp16.safetensors",
            ],
            triple["loadCall"]["ckpt_paths"],
        )
        self.assertEqual(["/models/embeddings", "/extra/embeddings"], triple["loadCall"]["embedding_directory"])
        self.assertTrue(triple["resultIdentityPreserved"])
        self.assertTrue(triple["missingRaisesBeforeLoad"])

        empty = payload["empty"]
        self.assertEqual([2, 16, 12, 10], empty["shape"])
        self.assertEqual("torch.float16", empty["dtype"])
        self.assertEqual("cpu", empty["device"])
        self.assertTrue(empty["allZero"])
        self.assertEqual(8, empty["downscaleRatio"])
        self.assertEqual([1, 16, 9, 8], empty["directOddShape"])

        encode = payload["encode"]
        self.assertEqual(["G two chunks", "L one chunk", "T three chunks", ""], encode["alignedCalls"])
        self.assertEqual(["l1", "l-empty"], encode["alignedTokens"]["l"])
        self.assertEqual(["g1", "g2"], encode["alignedTokens"]["g"])
        self.assertEqual(["t1", "t2", "t3"], encode["alignedTokens"]["t5xxl"])
        self.assertTrue(encode["scheduledResultPreserved"])
        self.assertEqual({"l": [], "g": [], "t5xxl": []}, encode["noneTokens"])
        self.assertEqual([""], encode["noneCalls"])
        self.assertEqual(["", "", ""], encode["emptyPromptCalls"])
        self.assertEqual(["l-empty"], encode["emptyPromptTokens"]["l"])

        control = payload["control"]
        self.assertEqual(2, control["copyCountForTwoPreviousChains"])
        self.assertTrue(control["sharedPreviousReusesCopy"])
        self.assertTrue(control["sharedNoneReusesCopy"])
        self.assertTrue(control["differentPreviousUsesDifferentCopy"])
        self.assertEqual([2, 3, 4, 5], control["hintShape"])
        self.assertTrue(control["hintEqualsNCHW"])
        self.assertEqual(0.75, control["strength"])
        self.assertEqual([0.2, 0.8], control["percentRange"])
        self.assertTrue(control["vaeIdentityPreserved"])
        self.assertEqual([], control["extraConcat"])
        self.assertTrue(control["previousIdentityPreserved"])
        self.assertTrue(control["metadataNotMutated"])
        self.assertTrue(control["metadataCopied"])
        self.assertTrue(control["nestedMetadataIsShallow"])
        self.assertEqual([True, True, True, True], control["embeddingsPreserved"])
        self.assertEqual([False, False, False, False], control["applyToUncondFlags"])
        self.assertTrue(control["zeroReturnsOriginalLists"])
        self.assertTrue(control["zeroAvoidsCopy"])


if __name__ == "__main__":
    unittest.main()
