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
    "core.clip-text-encode-hunyuan-dit": {
        "directory": "clip-text-encode-hunyuan-dit",
        "classType": "CLIPTextEncodeHunyuanDiT",
        "fingerprint": "sha256:3798da45982ac5e420daf43a5799164eb90ec8ad8bba6b987e6693e3e919f17e",
        "category": "model/conditioning/hunyuan image",
        "recipe": "recipe.encode-hunyuan-dit-dual-text",
    },
    "core.text-encode-hunyuan-video-image-to-video": {
        "directory": "text-encode-hunyuan-video-image-to-video",
        "classType": "TextEncodeHunyuanVideo_ImageToVideo",
        "fingerprint": "sha256:02e8cb641a61d19d358edba94d57a829650faaa27933247e4a78f6348c525516",
        "category": "model/conditioning/hunyuan video",
        "recipe": "recipe.encode-hunyuan-video-10-i2v-prompt",
    },
    "core.empty-hunyuan-latent-video": {
        "directory": "empty-hunyuan-latent-video",
        "classType": "EmptyHunyuanLatentVideo",
        "fingerprint": "sha256:fb4dc349a301147be23e4bc9e87f94b0918c6354eab6cfcafb6a4cecef1a7dd0",
        "category": "model/latent/hunyuan video",
        "recipe": "recipe.sample-empty-hunyuan-video-10-latent",
    },
    "core.empty-hunyuan-video-15-latent": {
        "directory": "empty-hunyuan-video-15-latent",
        "classType": "EmptyHunyuanVideo15Latent",
        "fingerprint": "sha256:2b41984ad1d47fdf8a49ab1b6c278c7c73e5fb5175b1608a84fa189d2101fb54",
        "category": "model/latent/hunyuan video",
        "recipe": "recipe.sample-empty-hunyuan-video-15-latent",
    },
}

RECIPE_DIRS = {
    "recipe.encode-hunyuan-dit-dual-text": "encode-hunyuan-dit-dual-text",
    "recipe.encode-hunyuan-video-10-i2v-prompt": "encode-hunyuan-video-10-i2v-prompt",
    "recipe.sample-empty-hunyuan-video-10-latent": "sample-empty-hunyuan-video-10-latent",
    "recipe.sample-empty-hunyuan-video-15-latent": "sample-empty-hunyuan-video-15-latent",
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

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
FRONTEND = ROOT / ".frontend-source-1.48.7"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = Path(__file__).with_name("hunyuan_text_latent_synthetic_probe.py")

SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
SOURCE_HASHES = {
    "comfy_extras/nodes_hunyuan.py": "97b684150cd18f9318d681abf4a4bc77929655d6f83ac49ad294ce913a60cc03",
    "comfy/text_encoders/hydit.py": "8113b04d7232a59aec3652ed3d4644089c7fc61ad3c07b66d92192f69be5c5d3",
    "comfy/text_encoders/hunyuan_video.py": "9c1c309de2014e899803094353110005307f15877c8cdc9dc49c2dc5f7393051",
    "comfy/text_encoders/qwen_image.py": "c77e85de2b451d76d8b07da32181518397d1447cec8a4c58abbd0da193675034",
    "comfy/sample.py": "34a94286735b323b7c384d960b868752dbebacbc5b2eb04c09f99dd97ec7df5a",
    "comfy_extras/nodes_custom_sampler.py": "13892ff513b2fce19d480cf5ed461d7619ab5b39e6915716ee6d21de05b81a28",
}
FRONTEND_HASH = "02226a0858ad4bf92e8341e0a1c9c62fa732f17dc04e43bf628298b2264d39e8"
DOC_HASHES = {
    "ClipTextEncodeHunyuanDit/en.md": "1ef0f3912db5b29c3c920ee6a17e9c96a405c8f3737c416751b98c356cb836ff",
    "ClipTextEncodeHunyuanDit/ru.md": "ff01700224c04a96ab6f89c4b1d1b395f82b1560b8c0eaeb575b583c4f8d0c87",
    "TextEncodeHunyuanVideo_ImageToVideo/en.md": "4e5ef2f4ea903b71a23f7414aca2901a6dd0d29008d9f2809cdbe3feeaf92ebb",
    "TextEncodeHunyuanVideo_ImageToVideo/ru.md": "490998fb4c48f930e22a8d9e9cec22dcdd62e715d5ad61b8671e1401d7751c24",
    "EmptyHunyuanLatentVideo/en.md": "afe821cfcd97b597b33621c2c73f3be1dafc670d99fba317d96958ddcf19ce89",
    "EmptyHunyuanLatentVideo/ru.md": "838013119f7af1f8307ea9dd900f3bcf0fd72581157f6ac3f642b7d85954cfe9",
    "EmptyHunyuanVideo15Latent/en.md": "18be381776da62e24ddd1de6eabb364c7149e8faca8e45f1b648070da1db9d08",
    "EmptyHunyuanVideo15Latent/ru.md": "3eb7f60a20635ca2df181efe627f0ce0e654cdbb1fa142c2464623d7c48c1115",
}
WORKFLOW_MEMBER_HASHES = {
    "Image_capybara_v0_1_text_to_image.json": "68d76c054291bf39a0fc3fd46bad4262f65763fe23543f0815239d2cad335846",
    "hunyuan_video_text_to_video.json": "3f221fb9cb178bf4e186410553b918604751deb58f61e03bebbcee64721e8744",
    "text_to_video_wan.json": "6cfcb2bcc842926d462667f1858651a7a73d698591013e4d0370bdc2984a6fea",
    "video_hunyuan_video_1.5_720p_t2v.json": "b52ab35cd7f5253288d32ca2d18329607a0e5fb265886e234bae7b75deff8cfe",
    "video_wan2.1_alpha_t2v_14B.json": "57b22a6cb4577473bfcd527f8d01a47c86d357acb263759828d4886a878d95e0",
    "video_wan2_2_14B_t2v.json": "c07feedfb87de638cb34bd517d916fc7afa7786be453e433a7bb49833a0c2801",
}


def article_path(spec: dict[str, Any]) -> Path:
    return CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return CONTENT / "recipes" / RECIPE_DIRS[recipe_id] / "recipe.json"


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


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def prose_without_code_or_urls(text: str) -> str:
    text = re.sub(r"`[^`]+`", " ", text)
    return re.sub(r"https?://\S+", " ", text)


def verify_wheel_record(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
        rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
        assert len(rows) == len(archive.namelist())
        assert {row[0] for row in rows} == set(archive.namelist())
        for name, digest_field, size_field in rows:
            if name == record_name:
                assert digest_field == "" and size_field == ""
                continue
            payload = archive.read(name)
            algorithm, encoded = digest_field.split("=", 1)
            assert algorithm == "sha256"
            expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            assert hashlib.sha256(payload).digest() == expected
            assert len(payload) == int(size_field)


class HunyuanTextLatentContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        all_manifests = list((CONTENT / "articles").rglob("manifest.json"))
        all_ids = {catalog.load_json(path)["articleId"] for path in all_manifests}
        self.assertEqual(len(all_manifests), len(all_ids))
        errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит подчеркнуть|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
            r"не просто .{0,80}, а|без воды|коротко о главном|по-честному",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual([spec["recipe"]], [asset["id"] for asset in article["assets"]])
            targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(targets).issubset(all_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(prose_without_code_or_urls(body), cliches)
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual(spec["classType"], ledger["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_hunyuan", ledger["node"]["pythonModule"])
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertTrue(ledger["checks"]["officialCasesInspected"])
            self.assertTrue(ledger["checks"]["exampleSchemaValidated"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))
            self.assertNotIn("human_approved", json.dumps(ledger).lower())

        for recipe_id in RECIPE_DIRS:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, all_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotRegex(prose_without_code_or_urls(body), cliches)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(path.parent / recipe["fragment"]["path"], fragment, errors)
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)

        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_flags_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            self.assertEqual("comfy_extras.nodes_hunyuan", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node", "is_input_list"):
                self.assertFalse(runtime[flag], (spec["classType"], flag))
            self.assertEqual([False], runtime["output_is_list"])

        hydit = nodes["CLIPTextEncodeHunyuanDiT"]
        self.assertEqual(["clip", "bert", "mt5xl"], hydit["input_order"]["required"])
        self.assertEqual(["CONDITIONING"], hydit["output"])
        self.assertEqual({"multiline": True, "dynamicPrompts": True}, hydit["input"]["required"]["bert"][1])
        self.assertEqual(hydit["input"]["required"]["bert"], hydit["input"]["required"]["mt5xl"])

        video_text = nodes["TextEncodeHunyuanVideo_ImageToVideo"]
        self.assertEqual(["clip", "clip_vision_output", "prompt", "image_interleave"], video_text["input_order"]["required"])
        self.assertEqual(["CONDITIONING"], video_text["output"])
        interleave = video_text["input"]["required"]["image_interleave"][1]
        self.assertEqual((2, 1, 512, True), (interleave["default"], interleave["min"], interleave["max"], interleave["advanced"]))

        expected_widgets = {
            "width": {"default": 848, "min": 16, "max": 16384, "step": 16},
            "height": {"default": 480, "min": 16, "max": 16384, "step": 16},
            "length": {"default": 25, "min": 1, "max": 16384, "step": 4},
            "batch_size": {"default": 1, "min": 1, "max": 4096},
        }
        for node_id in ("EmptyHunyuanLatentVideo", "EmptyHunyuanVideo15Latent"):
            runtime = nodes[node_id]
            self.assertEqual(list(expected_widgets), runtime["input_order"]["required"])
            self.assertEqual(["LATENT"], runtime["output"])
            for name, options in expected_widgets.items():
                self.assertEqual(options, runtime["input"]["required"][name][1])

        for recipe_id in RECIPE_DIRS:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {item["ref"]: item for item in fragment["nodes"]}
            for item in fragment["nodes"]:
                runtime = dict(nodes[item["classType"]])
                self.assertTrue(set(item["settings"]).issubset(runtime_inputs(runtime)))
            for external in fragment["externalInputs"]:
                accepted = runtime_inputs(dict(nodes[refs[external["to"]]["classType"]]))[external["input"]][0]
                self.assertIn(external["type"], accepted if isinstance(accepted, list) else str(accepted).split(","))
            for edge in fragment["connections"]:
                source = dict(nodes[refs[edge["from"]]["classType"]])
                target = dict(nodes[refs[edge["to"]]["classType"]])
                output_index = source["output_name"].index(edge["output"])
                self.assertEqual(source["output"][output_index], runtime_inputs(target)[edge["input"]][0])

    def test_pinned_sources_docs_replacements_and_help_path_are_exact(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        self.assertEqual(FRONTEND_COMMIT, (FRONTEND / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        for relative, expected in SOURCE_HASHES.items():
            self.assertEqual(expected, hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest(), relative)
        help_path = FRONTEND / "src" / "services" / "nodeHelpService.ts"
        self.assertEqual(FRONTEND_HASH, hashlib.sha256(help_path.read_bytes()).hexdigest())

        node_source = (SOURCE / "comfy_extras" / "nodes_hunyuan.py").read_text(encoding="utf-8")
        for snippet in (
            'tokens = clip.tokenize(bert)',
            'tokens["mt5xl"] = clip.tokenize(mt5xl)["mt5xl"]',
            '[batch_size, 16, ((length - 1) // 4) + 1, height // 8, width // 8]',
            '[batch_size, 32, ((length - 1) // 4) + 1, height // 16, width // 16]',
            'image_embeds=clip_vision_output.mm_projected, image_interleave=image_interleave',
        ):
            self.assertIn(snippet, node_source)

        video_encoder = (SOURCE / "comfy" / "text_encoders" / "hunyuan_video.py").read_text(encoding="utf-8")
        self.assertIn('r[i][0] == 128257', video_encoder)
        self.assertIn('llama_out[:, i[0]: i[1]: i[2]]', video_encoder)
        self.assertIn('class HunyuanVideo15Tokenizer(HunyuanImageTokenizer)', video_encoder)
        custom_sampler = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        self.assertIn('fix_empty_latent_channels(guider.model_patcher', custom_sampler)
        self.assertIn('out.pop("downscale_ratio_spacial", None)', custom_sampler)
        help_source = help_path.read_text(encoding="utf-8")
        self.assertIn('${node.name}/${locale}.md', help_source)

        replacements = catalog.load_json(REPLACEMENTS)
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        for old_id, records in replacements.items():
            self.assertNotIn(old_id, targets)
            for record in records:
                self.assertNotIn(record.get("new_node_id"), targets)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        verify_wheel_record(DOCS_WHEEL)
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            base = "comfyui_embedded_docs/docs/"
            names = set(archive.namelist())
            self.assertNotIn(base + "CLIPTextEncodeHunyuanDiT/en.md", names)
            self.assertIn(base + "ClipTextEncodeHunyuanDit/en.md", names)
            locales = {"ar", "en", "es", "fa", "fr", "ja", "ko", "pt-BR", "ru", "tr", "zh-TW", "zh"}
            for directory in (
                "ClipTextEncodeHunyuanDit",
                "TextEncodeHunyuanVideo_ImageToVideo",
                "EmptyHunyuanLatentVideo",
                "EmptyHunyuanVideo15Latent",
            ):
                found = {
                    Path(name).stem
                    for name in names
                    if name.startswith(base + directory + "/") and name.endswith(".md")
                }
                self.assertEqual(locales, found, directory)
            for relative, expected in DOC_HASHES.items():
                self.assertEqual(expected, hashlib.sha256(archive.read(base + relative)).hexdigest(), relative)

    def test_full_workflow_census_and_family_correct_topologies(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        verify_wheel_record(WORKFLOW_WHEEL)
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: dict[str, Counter[str]] = {target: Counter() for target in targets}
        modes: dict[str, Counter[int]] = {target: Counter() for target in targets}
        widgets: dict[str, Counter[tuple[Any, ...]]] = {target: Counter() for target in targets}
        files: dict[str, set[str]] = defaultdict(set)
        payloads: dict[str, dict[str, Any]] = {}
        json_count = root_count = graph_count = root_nodes = subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for suffix, expected in WORKFLOW_MEMBER_HASHES.items():
                member = next(name for name in archive.namelist() if name.endswith("/" + suffix))
                raw = archive.read(member)
                self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), suffix)
                payload = json.loads(raw.decode("utf-8"))
                if isinstance(payload, dict):
                    payloads[suffix] = payload

            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                raw = archive.read(member)
                lowered = raw.lower()
                self.assertNotIn(b'"cliptextencodehunyuandit"', lowered)
                self.assertNotIn(b'"textencodehunyuanvideo_imagetovideo"', lowered)
                payload = json.loads(raw.decode("utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    root_count += 1
                for scope, graph in graph_scopes(payload):
                    graph_count += 1
                    for node in graph["nodes"]:
                        if not isinstance(node, dict):
                            continue
                        if scope == "root":
                            root_nodes += 1
                        else:
                            subgraph_nodes += 1
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            modes[node_type][int(node.get("mode", 0))] += 1
                            widgets[node_type][tuple(node.get("widgets_values", []))] += 1
                            files[node_type].add(Path(member).name)

        self.assertEqual((512, 496, 768, 4083, 4037), (json_count, root_count, graph_count, root_nodes, subgraph_nodes))
        self.assertEqual(Counter(), counts["CLIPTextEncodeHunyuanDiT"])
        self.assertEqual(Counter(), counts["TextEncodeHunyuanVideo_ImageToVideo"])
        self.assertEqual(Counter({"root": 3, "subgraph": 1}), counts["EmptyHunyuanLatentVideo"])
        self.assertEqual(Counter({"root": 1, "subgraph": 1}), counts["EmptyHunyuanVideo15Latent"])
        self.assertEqual(Counter({0: 4}), modes["EmptyHunyuanLatentVideo"])
        self.assertEqual(Counter({0: 2}), modes["EmptyHunyuanVideo15Latent"])
        self.assertEqual(Counter({(848, 480, 73, 1): 1, (832, 480, 33, 1): 2, (640, 640, 81, 1): 1}), widgets["EmptyHunyuanLatentVideo"])
        self.assertEqual(Counter({(1280, 720, 121, 1): 1, (1280, 1280, 1, 1): 1}), widgets["EmptyHunyuanVideo15Latent"])
        self.assertEqual(
            {"hunyuan_video_text_to_video.json", "text_to_video_wan.json", "video_wan2.1_alpha_t2v_14B.json", "video_wan2_2_14B_t2v.json"},
            files["EmptyHunyuanLatentVideo"],
        )
        self.assertEqual(
            {"video_hunyuan_video_1.5_720p_t2v.json", "Image_capybara_v0_1_text_to_image.json"},
            files["EmptyHunyuanVideo15Latent"],
        )

        old = payloads["hunyuan_video_text_to_video.json"]
        old_nodes = {node["id"]: node for node in old["nodes"]}
        self.assertEqual("EmptyHunyuanLatentVideo", old_nodes[45]["type"])
        self.assertEqual([848, 480, 73, 1], old_nodes[45]["widgets_values"])
        self.assertIn([180, 45, 0, 13, 4, "LATENT"], old["links"])
        self.assertEqual("SamplerCustomAdvanced", old_nodes[13]["type"])
        self.assertEqual("hunyuan_video", next(node for node in old["nodes"] if node["type"] == "DualCLIPLoader")["widgets_values"][-2])

        video15 = payloads["video_hunyuan_video_1.5_720p_t2v.json"]
        video15_nodes = {node["id"]: node for node in video15["nodes"]}
        self.assertEqual("EmptyHunyuanVideo15Latent", video15_nodes[124]["type"])
        self.assertEqual([1280, 720, 121, 1], video15_nodes[124]["widgets_values"])
        self.assertIn([318, 124, 0, 127, 4, "LATENT"], video15["links"])
        self.assertEqual("SamplerCustomAdvanced", video15_nodes[127]["type"])
        self.assertEqual("hunyuan_video_15", next(node for node in video15["nodes"] if node["type"] == "DualCLIPLoader")["widgets_values"][-2])

    def test_safe_exact_source_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE), str(SOURCE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(["BERT description", "mT5 description"], payload["hydit"]["tokenizeCalls"])
        self.assertEqual("hydit:BERT description", payload["hydit"]["hyditStream"])
        self.assertEqual("mt5xl:mT5 description", payload["hydit"]["mt5xlStream"])

        video_text = payload["videoImageToVideoText"]
        self.assertTrue(video_text["templateHasImagePlaceholder"])
        self.assertTrue(video_text["projectedIdentityForwarded"])
        self.assertEqual(3, video_text["imageInterleave"])
        self.assertEqual([0, 2, 4, 6], video_text["retainedImageTokenIndices"]["2"])
        self.assertEqual([0], video_text["retainedImageTokenIndices"]["512"])

        old = payload["latents"]["hunyuanVideo10Default"]
        video15 = payload["latents"]["hunyuanVideo15Default"]
        self.assertEqual([1, 16, 7, 60, 106], old["shape"])
        self.assertEqual([1, 32, 7, 30, 53], video15["shape"])
        self.assertEqual((8, 16), (old["downscaleRatioSpacial"], video15["downscaleRatioSpacial"]))
        self.assertEqual((2849280, 1424640), (old["bytes"], video15["bytes"]))
        self.assertEqual(
            {"hunyuanVideo10": 2**52, "hunyuanVideo15": 2**51},
            payload["latents"]["maximumFloat32Bytes"],
        )
        self.assertEqual(["downscale_ratio_spacial", "samples"], old["keys"])
        self.assertTrue(old["allZero"] and video15["allZero"])
        self.assertEqual([2, 16, 2, 5, 3], payload["latents"]["directNonWidgetMultiple"]["hunyuanVideo10"]["shape"])
        self.assertEqual([2, 32, 2, 2, 1], payload["latents"]["directNonWidgetMultiple"]["hunyuanVideo15"]["shape"])
        self.assertEqual(
            {"1": 1, "2": 1, "4": 1, "5": 2, "8": 2, "9": 3},
            {key: value[2] for key, value in payload["latents"]["temporalShapes"].items()},
        )


if __name__ == "__main__":
    unittest.main()
