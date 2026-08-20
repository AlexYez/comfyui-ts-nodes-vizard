from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from tools import catalog
from tools.tests.sdxl_ip2p_upscale_synthetic_probe import run_probe


SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"

BASELINE = {
    "comfyui": "0.32.0",
    "frontend": "1.48.7",
    "sourceCommit": "c2bcbecd82ec5ae66594340b395c24ef0217b238",
    "embeddedDocs": "0.5.9",
    "workflowTemplatesJson": "0.1.42",
}

ARTICLES = {
    "core.clip-text-encode-sdxl": {
        "directory": "clip-text-encode-sdxl",
        "classType": "CLIPTextEncodeSDXL",
        "module": "comfy_extras.nodes_clip_sdxl",
        "fingerprint": "sha256:ded531816d76344ccc417050017f43b483a798e8ee222993d8b0f439a7b2b8b3",
        "recipe": "recipe.sdxl-dual-text-conditioning",
    },
    "core.clip-text-encode-sdxl-refiner": {
        "directory": "clip-text-encode-sdxl-refiner",
        "classType": "CLIPTextEncodeSDXLRefiner",
        "module": "comfy_extras.nodes_clip_sdxl",
        "fingerprint": "sha256:34882974614510e24dd0b085484a86f1d0876f7c4aecbfe3c2c5eb367829b881",
        "recipe": "recipe.sdxl-refiner-text-conditioning",
    },
    "core.instruct-pix-to-pix-conditioning": {
        "directory": "instruct-pix-to-pix-conditioning",
        "classType": "InstructPixToPixConditioning",
        "module": "comfy_extras.nodes_ip2p",
        "fingerprint": "sha256:f9811246e63ab843a2f2104faefc90b88b994dd5e9021a1067944ec2af4ff1dc",
        "recipe": "recipe.instruct-pix-to-pix-conditioning",
    },
    "core.sd-4x-upscale-conditioning": {
        "directory": "sd-4x-upscale-conditioning",
        "classType": "SD_4XUpscale_Conditioning",
        "module": "comfy_extras.nodes_sdupscale",
        "fingerprint": "sha256:fefa8870b9ff721d3cc91bf7b409e9dd2cf6c8a5312ea2de18d8929f3aa183d5",
        "recipe": "recipe.sd-4x-upscale-conditioning",
    },
}
TARGET_TYPES = {value["classType"] for value in ARTICLES.values()}

RECIPES = {
    "recipe.sdxl-dual-text-conditioning": {
        "directory": "sdxl-dual-text-conditioning",
        "articles": {"core.clip-text-encode-sdxl"},
        "fragmentId": "fragment.sdxl-dual-text-conditioning",
        "nodes": {
            "CLIPTextEncodeSDXL": {
                "width": 1024,
                "height": 1024,
                "crop_w": 0,
                "crop_h": 0,
                "target_width": 1024,
                "target_height": 1024,
                "text_g": "a quiet forest clearing at dawn",
                "text_l": "quiet forest, dawn light",
            }
        },
    },
    "recipe.sdxl-refiner-text-conditioning": {
        "directory": "sdxl-refiner-text-conditioning",
        "articles": {"core.clip-text-encode-sdxl-refiner"},
        "fragmentId": "fragment.sdxl-refiner-text-conditioning",
        "nodes": {
            "CLIPTextEncodeSDXLRefiner": {
                "ascore": 6.0,
                "width": 1024,
                "height": 1024,
                "text": "fine natural detail, coherent lighting",
            }
        },
    },
    "recipe.instruct-pix-to-pix-conditioning": {
        "directory": "instruct-pix-to-pix-conditioning",
        "articles": {"core.instruct-pix-to-pix-conditioning", "core.ksampler"},
        "fragmentId": "fragment.instruct-pix-to-pix-conditioning",
        "nodes": {
            "InstructPixToPixConditioning": {},
            "KSampler": {
                "seed": 42,
                "steps": 20,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
    },
    "recipe.sd-4x-upscale-conditioning": {
        "directory": "sd-4x-upscale-conditioning",
        "articles": {"core.sd-4x-upscale-conditioning", "core.ksampler"},
        "fragmentId": "fragment.sd-4x-upscale-conditioning",
        "nodes": {
            "SD_4XUpscale_Conditioning": {"scale_ratio": 4.0, "noise_augmentation": 0.0},
            "KSampler": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
    },
}

EXPECTED_H2 = [
    "Что делает нода",
    "Место в графе",
    "Входы",
    "Выходы",
    "Как работает внутри",
    "Настройки",
    "Пример подключения",
    "Частые ошибки",
    "Ограничения и производительность",
    "Совместимость и источники",
]

SOURCE_HASHES = {
    "comfy_extras/nodes_clip_sdxl.py": "3c0db2d430d40b957be534590a9196783d381c89d066024b64dc4bbab0467895",
    "comfy_extras/nodes_ip2p.py": "a83a9ce6186bf6e429d1832d1ba4dfbc2b2bf4bd87255eb24e35082e8625da6b",
    "comfy_extras/nodes_sdupscale.py": "3bedfecd3c3560f23e4f108991268db13215ecdfb44852461c7c8e50c2abba3d",
    "comfy/model_base.py": "84c7756b4d2636cff80164ff73248068301e453fdd8631991007988203caa226",
    "comfy/utils.py": "339031b402739116941030f8c570a61a35a3e6e072e67eee96c084e125107803",
}

DOC_HASHES = {
    "comfyui_embedded_docs/docs/ClipTextEncodeSdxl/en.md": "ee30457fafa07098b10373af43150d761f8957124825cb882f3ba0e0763f56fc",
    "comfyui_embedded_docs/docs/ClipTextEncodeSdxl/ru.md": "4944b6e71e028c894059c8c8a0d8a1353e3f44792bf302f882beb056cf08da74",
    "comfyui_embedded_docs/docs/ClipTextEncodeSdxlRefiner/en.md": "607d3dee2a3155cb3a6f35696845da34c9fc9877f46cca1f46a4e52568278fff",
    "comfyui_embedded_docs/docs/ClipTextEncodeSdxlRefiner/ru.md": "33d13318fadd4cda2d7b0d110afdc3fd370c67297a10daf448b6926a2c2e15ca",
    "comfyui_embedded_docs/docs/InstructPixToPixConditioning/en.md": "95bd3bb29750d3782ef4d3722b97bb0cf5da2a3f2b6f948a6598ee1d682594f2",
    "comfyui_embedded_docs/docs/InstructPixToPixConditioning/ru.md": "81b74870bc369e9aecda8a57f7a47c6b71db8c695e41084cb5fba93f98332f2c",
    "comfyui_embedded_docs/docs/SD_4XUpscale_Conditioning/en.md": "d343c3cf6b9b56557989cc43d8ac16a1e17f73cdf50773f518e4461a88666210",
    "comfyui_embedded_docs/docs/SD_4XUpscale_Conditioning/ru.md": "ca0fb6f3270ea6b8456c0770c6de1cebe393bfe104d0f6d3da121072c54d31f1",
}


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_strings(nested)


def _subgraphs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = payload.get("definitions")
    values = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    if isinstance(values, dict):
        values = list(values.values())
    return [item for item in values if isinstance(item, dict)]


def _manifest_counts(root: Path, filename: str, field: str) -> Counter[str]:
    values: Counter[str] = Counter()
    for path in root.rglob(filename):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get(field), str):
            values[payload[field]] += 1
    return values


def _runtime_inputs(definition: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        entries = definition.get("input", {}).get(group, {})
        if isinstance(entries, dict):
            result.update(entries)
    return result


def _normalized_links(graph: dict[str, Any]) -> list[tuple[Any, ...]]:
    result: list[tuple[Any, ...]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(tuple(link[:6]))
        elif isinstance(link, dict):
            result.append(tuple(link.get(key) for key in ("id", "origin_id", "origin_slot", "target_id", "target_slot", "type")))
    return result


class SdxlIp2pUpscaleContentTests(unittest.TestCase):
    def test_articles_recipes_fragments_and_research_ledgers(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_counts = _manifest_counts(catalog.CONTENT / "articles", "manifest.json", "articleId")
        recipe_counts = _manifest_counts(catalog.CONTENT / "recipes", "recipe.json", "recipeId")
        all_article_ids = set(article_counts)
        all_recipe_ids = set(recipe_counts)
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        article_errors: list[str] = []
        recipe_errors: list[str] = []

        for article_id, spec in ARTICLES.items():
            self.assertEqual(1, article_counts[article_id], article_id)
            path = catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual(
                {
                    "classType": spec["classType"],
                    "pythonModule": spec["module"],
                    "packageId": "comfy-core",
                    "origin": "backend",
                    "aliases": [],
                },
                article["runtimeIdentity"],
            )
            self.assertEqual({spec["recipe"]}, {asset["id"] for asset in article["assets"]})
            self.assertTrue({asset["id"] for asset in article["assets"]}.issubset(all_recipe_ids))
            relation_targets = set(article["relations"]["related"] + article["relations"]["alternatives"])
            if article["relations"]["replacedBy"] is not None:
                relation_targets.add(article["relations"]["replacedBy"])
            self.assertTrue(relation_targets.issubset(all_article_ids), (article_id, relation_targets - all_article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_H2, re.findall(r"^## \d+\. (.+)$", body, flags=re.MULTILINE))
            self.assertEqual(10, len(re.findall(r"^## ", body, flags=re.MULTILINE)))
            self.assertIn(spec["classType"], body)
            self.assertNotIn("\ufffd", body)
            for cliché in ("важно отметить", "следует отметить", "мощный инструмент", "революцион", "подводя итог", "в современном мире"):
                self.assertNotIn(cliché, body.casefold(), (article_id, cliché))

            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual(article_id, ledger["articleId"])
            self.assertEqual(spec["classType"], ledger["node"]["classType"])
            self.assertEqual(spec["module"], ledger["node"]["pythonModule"])
            self.assertEqual(BASELINE, ledger["baseline"])
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertTrue(all(ledger["checks"][key] for key in (
                "implementationRead", "runtimeCompared", "officialCasesInspected",
                "exampleSchemaValidated", "russianEdited", "factsRecheckedAfterEditing",
            )))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertIn("pending", json.dumps(ledger["knownGaps"], ensure_ascii=False).casefold())
            self.assertEqual({"en", "ru"}, {entry["locale"] for entry in ledger["evidence"]["embeddedDocs"]})

        for recipe_id, spec in RECIPES.items():
            self.assertEqual(1, recipe_counts[recipe_id], recipe_id)
            path = catalog.CONTENT / "recipes" / spec["directory"] / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, all_article_ids, recipe_errors)
            self.assertEqual(spec["articles"], set(recipe["articleIds"]))
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual(
                {"id": spec["fragmentId"], "path": "fragment.json", "format": "nodes-wizard-fragment/1.0"},
                recipe["fragment"],
            )
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)
            self.assertEqual(spec["fragmentId"], fragment["fragmentId"])
            nodes = {node["classType"]: node for node in fragment["nodes"]}
            self.assertEqual(set(spec["nodes"]), set(nodes))
            self.assertEqual(len(nodes), len(fragment["nodes"]))
            for class_type, settings in spec["nodes"].items():
                self.assertEqual(settings, nodes[class_type]["settings"])
            for external in fragment["externalInputs"]:
                target = next(node for node in fragment["nodes"] if node["ref"] == external["to"])
                self.assertEqual(external["type"], _runtime_inputs(dict(runtime[target["classType"]]))[external["input"]][0])
            for edge in fragment["connections"]:
                source_node = next(node for node in fragment["nodes"] if node["ref"] == edge["from"])
                target_node = next(node for node in fragment["nodes"] if node["ref"] == edge["to"])
                source_runtime = dict(runtime[source_node["classType"]])
                output_index = source_runtime["output_name"].index(edge["output"])
                self.assertEqual(source_runtime["output"][output_index], _runtime_inputs(dict(runtime[target_node["classType"]]))[edge["input"]][0])

        self.assertEqual([], article_errors)
        self.assertEqual([], recipe_errors)

    def test_exact_runtime_schemas_fingerprints_flags_and_replacements(self) -> None:
        runtime = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        expected = {
            "CLIPTextEncodeSDXL": (
                ["clip", "width", "height", "crop_w", "crop_h", "target_width", "target_height", "text_g", "text_l"],
                ["CONDITIONING"], ["CONDITIONING"],
            ),
            "CLIPTextEncodeSDXLRefiner": (
                ["ascore", "width", "height", "text", "clip"],
                ["CONDITIONING"], ["CONDITIONING"],
            ),
            "InstructPixToPixConditioning": (
                ["positive", "negative", "vae", "pixels"],
                ["CONDITIONING", "CONDITIONING", "LATENT"], ["positive", "negative", "latent"],
            ),
            "SD_4XUpscale_Conditioning": (
                ["images", "positive", "negative", "scale_ratio", "noise_augmentation"],
                ["CONDITIONING", "CONDITIONING", "LATENT"], ["positive", "negative", "latent"],
            ),
        }
        for spec in ARTICLES.values():
            class_type = spec["classType"]
            definition = dict(runtime[class_type])
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, definition))
            self.assertEqual(expected[class_type][0], definition["input_order"]["required"])
            self.assertEqual(expected[class_type][1], definition["output"])
            self.assertEqual(expected[class_type][2], definition["output_name"])
            self.assertIsNone(definition["search_aliases"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node", "has_intermediate_output", "is_input_list"):
                self.assertFalse(definition[flag], (class_type, flag))

        sdxl = runtime["CLIPTextEncodeSDXL"]["input"]["required"]
        self.assertEqual(["CLIP", {}], sdxl["clip"])
        for key in ("width", "height", "target_width", "target_height"):
            self.assertEqual(["INT", {"default": 1024, "min": 0, "max": 16384}], sdxl[key])
        for key in ("crop_w", "crop_h"):
            self.assertEqual(["INT", {"default": 0, "min": 0, "max": 16384, "advanced": True}], sdxl[key])
        for key in ("text_g", "text_l"):
            self.assertEqual(["STRING", {"multiline": True, "dynamicPrompts": True}], sdxl[key])

        refiner = runtime["CLIPTextEncodeSDXLRefiner"]["input"]["required"]
        self.assertEqual(["FLOAT", {"default": 6.0, "min": 0.0, "max": 1000.0, "step": 0.01}], refiner["ascore"])
        for key in ("width", "height"):
            self.assertEqual(["INT", {"default": 1024, "min": 0, "max": 16384}], refiner[key])

        sd4x = runtime["SD_4XUpscale_Conditioning"]["input"]["required"]
        self.assertEqual(["FLOAT", {"default": 4.0, "min": 0.0, "max": 10.0, "step": 0.01}], sd4x["scale_ratio"])
        self.assertEqual(["FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001, "advanced": True}], sd4x["noise_augmentation"])

        replacement_strings = set(_walk_strings(catalog.load_json(REPLACEMENTS)))
        self.assertTrue(TARGET_TYPES.isdisjoint(replacement_strings))

    def test_pinned_source_and_embedded_docs_discrepancies(self) -> None:
        self.assertEqual(BASELINE["sourceCommit"], (SOURCE / ".git" / "HEAD").read_text(encoding="ascii").strip())
        for relative, digest in SOURCE_HASHES.items():
            self.assertEqual(digest, hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest(), relative)

        expected_ranges = {
            "comfy_extras/nodes_clip_sdxl.py": {"CLIPTextEncodeSDXLRefiner": (7, 27), "CLIPTextEncodeSDXL": (29, 60)},
            "comfy_extras/nodes_ip2p.py": {"InstructPixToPixConditioning": (7, 50)},
            "comfy_extras/nodes_sdupscale.py": {"SD_4XUpscale_Conditioning": (7, 50)},
        }
        source_text: dict[str, str] = {}
        for relative, ranges in expected_ranges.items():
            text = (SOURCE / relative).read_text(encoding="utf-8")
            source_text[relative] = text
            tree = ast.parse(text)
            actual = {node.name: (node.lineno, node.end_lineno) for node in tree.body if isinstance(node, ast.ClassDef) and node.name in ranges}
            self.assertEqual(ranges, actual)
        self.assertIn('tokens["l"] = clip.tokenize(text_l)["l"]', source_text["comfy_extras/nodes_clip_sdxl.py"])
        self.assertIn('empty = clip.tokenize("")', source_text["comfy_extras/nodes_clip_sdxl.py"])
        self.assertIn('"aesthetic_score": ascore', source_text["comfy_extras/nodes_clip_sdxl.py"])
        self.assertIn("pixels.shape[1] // 8", source_text["comfy_extras/nodes_ip2p.py"])
        self.assertIn('d["concat_latent_image"] = concat_latent', source_text["comfy_extras/nodes_ip2p.py"])
        self.assertIn("torch.zeros_like(concat_latent)", source_text["comfy_extras/nodes_ip2p.py"])
        self.assertIn('common_upscale((images.movedim(-1,1) * 2.0) - 1.0, width // 4, height // 4, "bilinear", "center")', source_text["comfy_extras/nodes_sdupscale.py"])
        self.assertIn("torch.zeros([images.shape[0], 4, height // 4, width // 4])", source_text["comfy_extras/nodes_sdupscale.py"])
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(encoding="utf-8")
        self.assertIn('aesthetic_score = kwargs.get("aesthetic_score", 2.5)', model_base)
        self.assertIn('aesthetic_score = kwargs.get("aesthetic_score", 6)', model_base)
        self.assertIn('image = kwargs.get("concat_latent_image", None)', model_base)
        self.assertIn('seed = kwargs["seed"] - 10', model_base)
        self.assertIn("noise_level = round((self.noise_augmentor.max_noise_level) * noise_augment)", model_base)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            pages: dict[str, str] = {}
            for member, digest in DOC_HASHES.items():
                raw = archive.read(member)
                self.assertEqual(digest, hashlib.sha256(raw).hexdigest(), member)
                pages[member] = raw.decode("utf-8")
        for member, text in pages.items():
            marker = "AI-generated" if member.endswith("/en.md") else "создана с помощью ИИ"
            self.assertIn(marker, text)
        self.assertIn("Global text description", pages["comfyui_embedded_docs/docs/ClipTextEncodeSdxl/en.md"])
        self.assertIn("Local text description", pages["comfyui_embedded_docs/docs/ClipTextEncodeSdxl/en.md"])
        refiner_en = pages["comfyui_embedded_docs/docs/ClipTextEncodeSdxlRefiner/en.md"]
        self.assertIn("High scores(7.5-8.5)", refiner_en)
        self.assertIn("must be multiple of 8", refiner_en)
        self.assertIn("64-16384", refiner_en)
        self.assertIn("nearest multiple of 8", pages["comfyui_embedded_docs/docs/InstructPixToPixConditioning/en.md"])
        self.assertIn("applies scaling and noise augmentation", pages["comfyui_embedded_docs/docs/SD_4XUpscale_Conditioning/en.md"])

    def test_workflow_wheel_exhaustive_census_and_all_direct_cases(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        json_count = root_count = subgraph_count = 0
        direct: list[dict[str, Any]] = []
        raw = Counter({class_type: 0 for class_type in TARGET_TYPES})
        exact_scalars = Counter({class_type: 0 for class_type in TARGET_TYPES})
        substring_scalars = Counter({class_type: 0 for class_type in TARGET_TYPES})
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json"):
                    continue
                json_count += 1
                raw_bytes = archive.read(member)
                payload = json.loads(raw_bytes)
                for class_type in TARGET_TYPES:
                    raw[class_type] += raw_bytes.count(class_type.encode("utf-8"))
                for scalar in _walk_strings(payload):
                    for class_type in TARGET_TYPES:
                        exact_scalars[class_type] += scalar == class_type
                        substring_scalars[class_type] += class_type in scalar
                if not isinstance(payload, dict):
                    continue
                subgraphs = _subgraphs(payload)
                subgraph_count += len(subgraphs)
                graphs: list[tuple[str, dict[str, Any]]] = [(f"subgraph:{index}", graph) for index, graph in enumerate(subgraphs)]
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                    graphs.insert(0, ("root", payload))
                for scope, graph in graphs:
                    for node in graph.get("nodes", []):
                        if isinstance(node, dict) and node.get("type") in TARGET_TYPES:
                            direct.append({"member": member, "root": payload, "scope": scope, "graph": graph, "node": node})

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual({"CLIPTextEncodeSDXL": 0, "CLIPTextEncodeSDXLRefiner": 0, "InstructPixToPixConditioning": 8, "SD_4XUpscale_Conditioning": 0}, dict(raw))
        self.assertEqual(dict(raw), dict(exact_scalars))
        self.assertEqual(dict(raw), dict(substring_scalars))
        self.assertEqual(4, len(direct))

        cases = {
            Path(item["member"]).stem: item for item in direct
        }
        self.assertEqual({"flux_canny_model_example", "flux_depth_lora_example", "hidream_e1_1", "hidream_e1_full"}, set(cases))
        expected = {
            "flux_canny_model_example": ("90469c7e-4751-418c-9bd5-e43b3745a118", "root", "90469c7e-4751-418c-9bd5-e43b3745a118", 35, "0.3.64"),
            "flux_depth_lora_example": ("d2d1faaf-2721-471e-a202-305446a968ee", "subgraph:1", "93bb962d-07fe-4a22-88e4-2df05e9caf80", 35, "0.3.63"),
            "hidream_e1_1": ("dbedd4b2-c963-475d-8057-72a15e532fd5", "root", "dbedd4b2-c963-475d-8057-72a15e532fd5", 52, "0.3.44"),
            "hidream_e1_full": ("dbedd4b2-c963-475d-8057-72a15e532fd5", "root", "dbedd4b2-c963-475d-8057-72a15e532fd5", 52, "0.3.44"),
        }
        for stem, item in cases.items():
            node = item["node"]
            self.assertEqual(expected[stem], (item["root"].get("id"), item["scope"], item["graph"].get("id"), node.get("id"), node.get("properties", {}).get("ver")))
            self.assertEqual((0, []), (node.get("mode"), node.get("widgets_values")))
            links = _normalized_links(item["graph"])
            incoming = [link for link in links if link[3] == node["id"]]
            outgoing = [link for link in links if link[1] == node["id"]]
            self.assertEqual({(0, "CONDITIONING"), (1, "CONDITIONING"), (2, "VAE"), (3, "IMAGE")}, {(link[4], link[5]) for link in incoming})
            self.assertEqual({(0, "CONDITIONING"), (1, "CONDITIONING"), (2, "LATENT")}, {(link[2], link[5]) for link in outgoing})
            nodes = {entry.get("id"): entry for entry in item["graph"].get("nodes", []) if isinstance(entry, dict)}
            sink_types = {nodes[link[3]]["type"] for link in outgoing}
            if stem.startswith("flux_"):
                self.assertEqual({"KSampler"}, sink_types)
                sampler = next(nodes[link[3]] for link in outgoing)
                self.assertEqual([20, 1, "euler", "normal", 1], sampler["widgets_values"][2:])
            else:
                self.assertEqual({"DualCFGGuider", "SamplerCustomAdvanced"}, sink_types)
        self.assertEqual([30], next(node for node in cases["flux_canny_model_example"]["graph"]["nodes"] if node.get("type") == "FluxGuidance")["widgets_values"])
        self.assertEqual([10], next(node for node in cases["flux_depth_lora_example"]["graph"]["nodes"] if node.get("type") == "FluxGuidance")["widgets_values"])
        self.assertEqual([3, 1.5, "regular"], next(node for node in cases["hidream_e1_1"]["graph"]["nodes"] if node.get("type") == "DualCFGGuider")["widgets_values"])
        self.assertEqual([5, 2, "regular"], next(node for node in cases["hidream_e1_full"]["graph"]["nodes"] if node.get("type") == "DualCFGGuider")["widgets_values"])

    def test_exact_source_model_free_probe(self) -> None:
        result = run_probe(SOURCE)
        self.assertEqual(3, result["sdxl"]["gLength"])
        self.assertEqual(3, result["sdxl"]["lLength"])
        self.assertEqual(["empty-l", "empty-l"], result["sdxl"]["lPadding"])
        self.assertEqual(["empty-g", "empty-g"], result["sdxl"]["reverseGPadding"])
        self.assertEqual({"aesthetic_score": 6.5, "width": 1216, "height": 832}, result["refiner"]["metadata"])
        self.assertEqual([2, 8, 8, 3], result["ip2p"]["croppedShape"])
        self.assertTrue(result["ip2p"]["cropMatchesCenter"])
        self.assertTrue(result["ip2p"]["metadataCopied"])
        self.assertTrue(result["ip2p"]["encodedLatentShared"])
        self.assertEqual([2, 4, 1, 1], result["ip2p"]["zeroLatentShape"])
        self.assertEqual([2, 4, 5, 7], result["sd4x"]["latentShape"])
        self.assertEqual("cpu", result["sd4x"]["latentDevice"])
        self.assertEqual("ZeroDivisionError", result["sd4x"]["zeroRatioError"])
        self.assertFalse(result["weightsLoaded"])
        self.assertFalse(result["workflowExampleExecuted"])


if __name__ == "__main__":
    unittest.main()
