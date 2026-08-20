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
    "core.empty-latent-hunyuan3d-v2": {
        "directory": "empty-latent-hunyuan3d-v2",
        "classType": "EmptyLatentHunyuan3Dv2",
        "fingerprint": "sha256:b56efde6d1ad00a66d4d2c30df36de2c34c48ed2f065f6a11c90db13bb025f23",
        "recipes": {"recipe.hunyuan3d-v2-single-view-official", "recipe.hunyuan3d-v2-multiview-official"},
    },
    "core.hunyuan3d-v2-conditioning": {
        "directory": "hunyuan3d-v2-conditioning",
        "classType": "Hunyuan3Dv2Conditioning",
        "fingerprint": "sha256:246c9c7960f26e35b9f923d18bcc7d3f017e3be034c2f68abbd151be4ec808b8",
        "recipes": {"recipe.hunyuan3d-v2-single-view-official"},
    },
    "core.hunyuan3d-v2-conditioning-multiview": {
        "directory": "hunyuan3d-v2-conditioning-multiview",
        "classType": "Hunyuan3Dv2ConditioningMultiView",
        "fingerprint": "sha256:c45392034e5bb45cba8dfa6bd0ef8db2ef109ac08bacc80c378055c5b88a0f10",
        "recipes": {"recipe.hunyuan3d-v2-multiview-official"},
    },
    "core.vae-decode-hunyuan3d": {
        "directory": "vae-decode-hunyuan3d",
        "classType": "VAEDecodeHunyuan3D",
        "fingerprint": "sha256:be98ef9f5ec6c8b4093b8c1c36b85d40af2c464f2dce67aae16f79aeb0be186d",
        "recipes": {"recipe.hunyuan3d-v2-single-view-official", "recipe.hunyuan3d-v2-multiview-official"},
    },
}

RECIPE_DIRECTORIES = {
    "recipe.hunyuan3d-v2-single-view-official": "hunyuan3d-v2-single-view-official",
    "recipe.hunyuan3d-v2-multiview-official": "hunyuan3d-v2-multiview-official",
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
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = Path(__file__).with_name("hunyuan3d_v2_core_synthetic_probe.py")

DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
SOURCE_HASHES = {
    "comfy_extras/nodes_hunyuan3d.py": "818c71e7f1366f2072861b7d33ab91ce732cd9a0bbf7c5a92bcc2ebded0d04a7",
    "comfy/ldm/modules/diffusionmodules/mmdit.py": "7b167436c92ac811414fb384c65567e27a56b511ef28505ecdb25883f0c46328",
    "comfy/ldm/hunyuan3d/vae.py": "0a0b0c5f3745c0b87c49a9ecfbb26df3e780a92758194d5e32fda62e164198e9",
    "comfy/clip_vision.py": "f1141d835e9d7f8e963795964cb6f08dfbeba2c3e71e8f942a042caecb54c864",
}
DOC_HASHES = {
    "EmptyLatentHunyuan3Dv2/en.md": "c143567cd0a1220f35e5b123095f20081f6ae0871f0af47b89612eff9cfef310",
    "EmptyLatentHunyuan3Dv2/ru.md": "3095bcfd2534cd9329627670312e36ff4d18388f981ce4bec7397e1e702f86f6",
    "Hunyuan3Dv2Conditioning/en.md": "45935513e5e1a771520fa7d8f2b08264c090b6c629cc55d7557d1821017dcd28",
    "Hunyuan3Dv2Conditioning/ru.md": "85858f89931c3b0c32e7b9fd137970bfb5bcc1b25a41b9bcd7f3c24adafd1f48",
    "Hunyuan3Dv2ConditioningMultiView/en.md": "8167ed513a9b567792e3e94ddf271644fbd19e015d28b7f864e155c0bfdde35e",
    "Hunyuan3Dv2ConditioningMultiView/ru.md": "35b2e75ee52904f6160d735538043bb8a5a1714dd92e75f6892f36c9dce10a5a",
    "VAEDecodeHunyuan3D/en.md": "af0f561ff8599ca493419f0410fa118718ebdd7ac7b9df2910fd490ade7a126e",
    "VAEDecodeHunyuan3D/ru.md": "6e57458d693b050723a6e581acf8576d0c5a932771818529fc15b4dc0aba250b",
}
WORKFLOW_MEMBER_HASHES = {
    "3d_hunyuan3d-v2.1.json": "da13275369b31a6586f8238837f13f7166bdf5b8f0b109440c790453d6d8d1ac",
    "3d_hunyuan3d_image_to_model.json": "82d52b65205b8b6d12b1111bdbae6943db3c61cea0f4f7cba5ccd8c9aba9dd10",
    "3d_hunyuan3d_multiview_to_model.json": "edb1f3b00c56130b9fe87aab82c0eb8b041bc2df2c0c3ab7ae5de2c80848743b",
    "3d_hunyuan3d_multiview_to_model_turbo.json": "5a0aad5c7c2dbb06d939920967221e340e9027590d4b859ee475b7ff14d0d246",
}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


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


def prose_without_code_or_urls(text: str) -> str:
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text


class Hunyuan3DV2CoreContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        all_ids = {
            catalog.load_json(path)["articleId"]
            for path in (catalog.CONTENT / "articles").rglob("manifest.json")
        }
        self.assertEqual(len(all_ids), len(list((catalog.CONTENT / "articles").rglob("manifest.json"))))
        errors: list[str] = []
        cliche = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте|"
            r"вот перевод|ключевую роль|мощный инструмент",
            re.IGNORECASE,
        )
        ordinary_english = re.compile(
            r"\b(?:official cases?|source-derived|root workflows?|subgraphs?|widgets?|"
            r"runtime|frontend|workflow|input|output|metadata entries?|feature maps?|"
            r"model family|files?|branch)\b",
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
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["recipes"], {asset["id"] for asset in article["assets"]})
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            self.assertTrue(set(targets).issubset(all_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche)
            self.assertNotRegex(prose_without_code_or_urls(body), ordinary_english)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_hunyuan3d", research["node"]["pythonModule"])
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
            catalog.validate_recipe(path, recipe, all_ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("�", body)
            self.assertNotRegex(body, cliche)
            self.assertNotRegex(prose_without_code_or_urls(body), ordinary_english)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)

        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        expected_categories = {
            "EmptyLatentHunyuan3Dv2": "model/latent/hunyuan 3d",
            "Hunyuan3Dv2Conditioning": "model/conditioning/hunyuan 3d",
            "Hunyuan3Dv2ConditioningMultiView": "model/conditioning/hunyuan 3d",
            "VAEDecodeHunyuan3D": "model/latent/hunyuan 3d",
        }
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_hunyuan3d", runtime["python_module"])
            self.assertEqual(expected_categories[spec["classType"]], runtime["category"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node", "is_input_list"):
                self.assertFalse(runtime[flag])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))

        empty = nodes["EmptyLatentHunyuan3Dv2"]
        self.assertEqual(["resolution", "batch_size"], empty["input_order"]["required"])
        self.assertEqual({"default": 3072, "min": 1, "max": 8192}, empty["input"]["required"]["resolution"][1])
        self.assertEqual({"tooltip": "The number of latent images in the batch.", "default": 1, "min": 1, "max": 4096}, empty["input"]["required"]["batch_size"][1])
        self.assertEqual(["LATENT"], empty["output"])

        single = nodes["Hunyuan3Dv2Conditioning"]
        self.assertEqual(["clip_vision_output"], single["input_order"]["required"])
        self.assertEqual(["CONDITIONING", "CONDITIONING"], single["output"])
        self.assertEqual(["positive", "negative"], single["output_name"])

        multi = nodes["Hunyuan3Dv2ConditioningMultiView"]
        self.assertEqual([], multi["input_order"]["required"])
        self.assertEqual(["front", "left", "back", "right"], multi["input_order"]["optional"])
        self.assertTrue(all(multi["input"]["optional"][name][0] == "CLIP_VISION_OUTPUT" for name in ("front", "left", "back", "right")))

        decode = nodes["VAEDecodeHunyuan3D"]
        self.assertEqual(["samples", "vae", "num_chunks", "octree_resolution"], decode["input_order"]["required"])
        self.assertEqual({"advanced": True, "default": 8000, "min": 1000, "max": 500000}, decode["input"]["required"]["num_chunks"][1])
        self.assertEqual({"advanced": True, "default": 256, "min": 16, "max": 512}, decode["input"]["required"]["octree_resolution"][1])
        self.assertEqual(["VOXEL"], decode["output"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                runtime = dict(nodes[node["classType"]])
                self.assertTrue(set(node["settings"]).issubset(runtime_inputs(runtime)))
            for external in fragment["externalInputs"]:
                runtime = dict(nodes[refs[external["to"]]["classType"]])
                accepted = runtime_inputs(runtime)[external["input"]][0]
                self.assertIn(external["type"], accepted if isinstance(accepted, list) else str(accepted).split(","))
            for edge in fragment["connections"]:
                src_runtime = dict(nodes[refs[edge["from"]]["classType"]])
                dst_runtime = dict(nodes[refs[edge["to"]]["classType"]])
                out_index = src_runtime["output_name"].index(edge["output"])
                out_type = src_runtime["output"][out_index]
                in_type = runtime_inputs(dst_runtime)[edge["input"]][0]
                self.assertIn(out_type, in_type if isinstance(in_type, list) else str(in_type).split(","))

        single_fragment = catalog.load_json(recipe_path("recipe.hunyuan3d-v2-single-view-official").parent / "fragment.json")
        self.assertEqual(
            ["CLIPVisionEncode", "Hunyuan3Dv2Conditioning", "EmptyLatentHunyuan3Dv2", "ModelSamplingAuraFlow", "KSampler", "VAEDecodeHunyuan3D", "VoxelToMesh"],
            [node["classType"] for node in single_fragment["nodes"]],
        )
        self.assertEqual({"resolution": 3072, "batch_size": 1}, single_fragment["nodes"][2]["settings"])
        self.assertEqual({"num_chunks": 8000, "octree_resolution": 256}, single_fragment["nodes"][5]["settings"])

    def test_pinned_sources_docs_and_replacements_are_exact(self) -> None:
        self.assertTrue(SOURCE.is_dir(), "pinned ComfyUI source is required; clean CI must bootstrap it")
        for relative, expected in SOURCE_HASHES.items():
            path = SOURCE / relative
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), relative)

        node_source = (SOURCE / "comfy_extras" / "nodes_hunyuan3d.py").read_text(encoding="utf-8")
        for snippet in (
            "torch.zeros([batch_size, 64, resolution]",
            '"type": "hunyuan3dv2"',
            "embeds = clip_vision_output.last_hidden_state",
            "negative = [[torch.zeros_like(embeds), {}]]",
            "all_embeds = [front, left, back, right]",
            "torch.arange(4)",
            "torch.cat(out, dim=1)",
            'vae.decode(samples["samples"], vae_options={"num_chunks": num_chunks, "octree_resolution": octree_resolution})',
        ):
            self.assertIn(snippet, node_source)

        volume_source = (SOURCE / "comfy" / "ldm" / "hunyuan3d" / "vae.py").read_text(encoding="utf-8")
        for snippet in (
            "int(octree_resolution) + 1",
            "for start in tqdm(range(0, xyz.shape[0], num_chunks)",
            "chunk_queries = xyz[start: start + num_chunks, :]",
            "grid_logits = grid_logits.view((latents.shape[0], *grid_size)).float()",
        ):
            self.assertIn(snippet, volume_source)

        replacements = catalog.load_json(REPLACEMENTS)
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        for records in replacements.values():
            for record in records:
                self.assertNotIn(record.get("old_node_id"), targets)
                self.assertNotIn(record.get("new_node_id"), targets)

        self.assertTrue(DOCS_WHEEL.is_file(), "pinned embedded-docs wheel is required")
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            base = "comfyui_embedded_docs/docs/"
            for relative, expected in DOC_HASHES.items():
                data = archive.read(base + relative)
                self.assertEqual(expected, hashlib.sha256(data).hexdigest(), relative)
            multi_en = archive.read(base + "Hunyuan3Dv2ConditioningMultiView/en.md").decode("utf-8")
            self.assertIn("3D video generation", multi_en)
            self.assertIn("contrastive learning", multi_en)
            decode_en = archive.read(base + "VAEDecodeHunyuan3D/en.md").decode("utf-8")
            self.assertIn("number of chunks", decode_en)

    def test_full_workflow_census_and_exact_official_topologies(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file(), "pinned workflow wheel is required")
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        widgets: dict[str, Counter[tuple[Any, ...]]] = {target: Counter() for target in targets}
        target_modes: Counter[int] = Counter()
        payloads: dict[str, dict[str, Any]] = {}
        file_count = root_count = graph_count = node_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for suffix, expected in WORKFLOW_MEMBER_HASHES.items():
                member = next(name for name in archive.namelist() if name.endswith("/" + suffix))
                raw = archive.read(member)
                self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), suffix)
                payloads[suffix] = json.loads(raw.decode("utf-8"))

            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for _path, graph in workflow_graphs(payload):
                    graph_count += 1
                    for node in graph.get("nodes", []):
                        if not isinstance(node, dict):
                            continue
                        node_count += 1
                        if node.get("type") in targets:
                            counts[node["type"]] += 1
                            widgets[node["type"]][tuple(node.get("widgets_values", []))] += 1
                            target_modes[int(node.get("mode", 0))] += 1

        self.assertEqual((512, 496, 768, 8120), (file_count, root_count, graph_count, node_count))
        self.assertEqual(Counter({"EmptyLatentHunyuan3Dv2": 4, "VAEDecodeHunyuan3D": 4, "Hunyuan3Dv2Conditioning": 2, "Hunyuan3Dv2ConditioningMultiView": 2}), counts)
        self.assertEqual(Counter({0: 12}), target_modes)
        self.assertEqual(Counter({(3072, 1): 3, (4096, 1): 1}), widgets["EmptyLatentHunyuan3Dv2"])
        self.assertEqual(Counter({(): 2}), widgets["Hunyuan3Dv2Conditioning"])
        self.assertEqual(Counter({(): 2}), widgets["Hunyuan3Dv2ConditioningMultiView"])
        self.assertEqual(Counter({(8000, 256): 4}), widgets["VAEDecodeHunyuan3D"])

        def graph_details(suffix: str) -> tuple[dict[int, dict[str, Any]], set[tuple[str, int, str, int, str]]]:
            payload = payloads[suffix]
            nodes_by_id = {node["id"]: node for node in payload["nodes"]}
            edges = {
                (nodes_by_id[link[1]]["type"], link[2], nodes_by_id[link[3]]["type"], link[4], link[5])
                for link in payload.get("links", [])
            }
            return nodes_by_id, edges

        image_nodes, image_edges = graph_details("3d_hunyuan3d_image_to_model.json")
        self.assertEqual(
            {
                ("ImageOnlyCheckpointLoader", 1, "CLIPVisionEncode", 0, "CLIP_VISION"),
                ("LoadImage", 0, "CLIPVisionEncode", 1, "IMAGE"),
                ("CLIPVisionEncode", 0, "Hunyuan3Dv2Conditioning", 0, "CLIP_VISION_OUTPUT"),
                ("Hunyuan3Dv2Conditioning", 0, "KSampler", 1, "CONDITIONING"),
                ("Hunyuan3Dv2Conditioning", 1, "KSampler", 2, "CONDITIONING"),
                ("EmptyLatentHunyuan3Dv2", 0, "KSampler", 3, "LATENT"),
                ("ImageOnlyCheckpointLoader", 0, "ModelSamplingAuraFlow", 0, "MODEL"),
                ("ModelSamplingAuraFlow", 0, "KSampler", 0, "MODEL"),
                ("KSampler", 0, "VAEDecodeHunyuan3D", 0, "LATENT"),
                ("ImageOnlyCheckpointLoader", 2, "VAEDecodeHunyuan3D", 1, "VAE"),
                ("VAEDecodeHunyuan3D", 0, "VoxelToMesh", 0, "VOXEL"),
                ("VoxelToMesh", 0, "SaveGLB", 0, "MESH"),
            },
            image_edges,
        )
        self.assertEqual([3072, 1], next(node for node in image_nodes.values() if node["type"] == "EmptyLatentHunyuan3Dv2")["widgets_values"])
        self.assertEqual([242832339647017, "randomize", 20, 8, "euler", "normal", 1], next(node for node in image_nodes.values() if node["type"] == "KSampler")["widgets_values"])

        standard_nodes, standard_edges = graph_details("3d_hunyuan3d_multiview_to_model.json")
        condition = next(node for node in standard_nodes.values() if node["type"] == "Hunyuan3Dv2ConditioningMultiView")
        incoming = [link for link in payloads["3d_hunyuan3d_multiview_to_model.json"]["links"] if link[3] == condition["id"]]
        self.assertEqual({0, 1, 2, 3}, {link[4] for link in incoming})
        source_modes = {link[4]: standard_nodes[link[1]]["mode"] for link in incoming}
        self.assertEqual({0: 0, 1: 4, 2: 0, 3: 4}, source_modes)
        self.assertIn(("Hunyuan3Dv2ConditioningMultiView", 0, "KSampler", 1, "CONDITIONING"), standard_edges)
        self.assertIn(("Hunyuan3Dv2ConditioningMultiView", 1, "KSampler", 2, "CONDITIONING"), standard_edges)
        self.assertEqual([502126049100058, "randomize", 20, 7.5, "euler", "normal", 1], next(node for node in standard_nodes.values() if node["type"] == "KSampler")["widgets_values"])

        turbo_nodes, turbo_edges = graph_details("3d_hunyuan3d_multiview_to_model_turbo.json")
        self.assertIn(("Hunyuan3Dv2ConditioningMultiView", 0, "FluxGuidance", 0, "CONDITIONING"), turbo_edges)
        self.assertIn(("FluxGuidance", 0, "KSampler", 1, "CONDITIONING"), turbo_edges)
        self.assertIn(("Hunyuan3Dv2ConditioningMultiView", 1, "KSampler", 2, "CONDITIONING"), turbo_edges)
        self.assertEqual([3.5], next(node for node in turbo_nodes.values() if node["type"] == "FluxGuidance")["widgets_values"])
        self.assertEqual([528364197559477, "randomize", 20, 4, "euler", "normal", 1], next(node for node in turbo_nodes.values() if node["type"] == "KSampler")["widgets_values"])

    def test_safe_exact_source_probe(self) -> None:
        self.assertTrue(PROBE.is_file())
        candidates: list[Path] = []
        configured = os.environ.get("NODES_WIZARD_COMFYUI_PYTHON")
        if configured:
            candidates.append(Path(configured))
        candidates.extend(
            [
                Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
                catalog.ROOT / ".ci-comfyui-venv" / "Scripts" / "python.exe",
                catalog.ROOT / ".ci-comfyui-venv" / "bin" / "python",
                Path(sys.executable),
            ]
        )
        result: subprocess.CompletedProcess[str] | None = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            attempt = subprocess.run(
                [str(candidate), "-X", "utf8", str(PROBE)],
                cwd=catalog.ROOT,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if attempt.returncode == 0:
                result = attempt
                break
        self.assertIsNotNone(result, "a Python with torch is required for the exact-source probe")
        assert result is not None
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual([2, 64, 7], payload["empty"]["shape"])
        self.assertEqual("torch.float32", payload["empty"]["dtype"])
        self.assertEqual("cpu", payload["empty"]["device"])
        self.assertTrue(payload["empty"]["allZero"])
        self.assertEqual(["samples", "type"], payload["empty"]["keys"])
        self.assertEqual("hunyuan3dv2", payload["empty"]["typeMarker"])
        self.assertEqual(786432, payload["empty"]["bytesAtDefault"])
        self.assertEqual(8589934592, payload["empty"]["bytesAtSchemaMaximum"])

        self.assertTrue(payload["singleView"]["positiveIsOriginal"])
        self.assertEqual({}, payload["singleView"]["positiveMetadata"])
        self.assertEqual([2, 3, 8], payload["singleView"]["negativeShape"])
        self.assertTrue(payload["singleView"]["negativeAllZero"])
        self.assertTrue(payload["singleView"]["ignoredImageEmbeds"])

        self.assertEqual([1, 5, 8], payload["multiView"]["shape"])
        self.assertEqual("torch.float32", payload["multiView"]["dtype"])
        self.assertTrue(payload["multiView"]["frontThenBackExact"])
        self.assertEqual((0, 2), (payload["multiView"]["frontPositionIndex"], payload["multiView"]["backPositionIndex"]))
        self.assertTrue(payload["multiView"]["emptyRaises"])
        self.assertTrue(payload["multiView"]["oddWidthRaises"])
        self.assertTrue(payload["multiView"]["mismatchedBatchRaises"])

        self.assertTrue(payload["decodeWrapper"]["samplesIdentity"])
        self.assertEqual({"num_chunks": 1234, "octree_resolution": 48}, payload["decodeWrapper"]["options"])
        self.assertTrue(payload["decodeWrapper"]["voxelDataIdentity"])
        self.assertTrue(payload["decodeWrapper"]["missingSamplesRaises"])

        volume = payload["volumeDecoder"]
        self.assertEqual([2, 3, 3, 3], volume["shape"])
        self.assertEqual(7, volume["callCount"])
        self.assertEqual([4, 4, 4, 4, 4, 4, 3], volume["chunkSizes"])
        self.assertEqual((27, 2), (volume["queryCount"], volume["queryBatch"]))
        self.assertAlmostEqual(-1.01, volume["boundsMinimum"], places=5)
        self.assertAlmostEqual(1.01, volume["boundsMaximum"], places=5)
        self.assertEqual(16974593, volume["defaultResolutionQueryCount"])
        self.assertEqual(2122, volume["defaultChunkIterations"])
        self.assertEqual(135005697, volume["maximumResolutionQueryCount"])


if __name__ == "__main__":
    unittest.main()
