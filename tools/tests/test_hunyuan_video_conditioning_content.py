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
    "core.hunyuan-video-15-image-to-video": {
        "directory": "hunyuan-video-15-image-to-video",
        "classType": "HunyuanVideo15ImageToVideo",
        "fingerprint": "sha256:f9e4e7a2c1996c07501c37b88b75848ecd8974419a0983065c21a0bb89f6418a",
        "recipe": "recipe.hunyuan-video-15-image-to-video-conditioning",
    },
    "core.hunyuan-video-15-super-resolution": {
        "directory": "hunyuan-video-15-super-resolution",
        "classType": "HunyuanVideo15SuperResolution",
        "fingerprint": "sha256:2d3f0e7ab79d39a8627276b4ec55786a06a4587e1ba4923c869f9d50cb306190",
        "recipe": "recipe.hunyuan-video-15-super-resolution-conditioning",
    },
    "core.hunyuan-image-to-video": {
        "directory": "hunyuan-image-to-video",
        "classType": "HunyuanImageToVideo",
        "fingerprint": "sha256:aca25341e4acb4f394c7adffa2a1f64dcc93570de7a03db7a8a4fbb6d37e051d",
        "recipe": "recipe.hunyuan-image-to-video-concat-guidance",
    },
    "core.hunyuan-refiner-latent": {
        "directory": "hunyuan-refiner-latent",
        "classType": "HunyuanRefinerLatent",
        "fingerprint": "sha256:ea0016fdefda0f879a133081a8e8297a8f9078e719cb892dcadaa574d21e547c",
        "recipe": "recipe.hunyuan-refiner-latent-conditioning",
    },
}

RECIPE_DIRS = {
    "recipe.hunyuan-video-15-image-to-video-conditioning": "hunyuan-video-15-image-to-video-conditioning",
    "recipe.hunyuan-video-15-super-resolution-conditioning": "hunyuan-video-15-super-resolution-conditioning",
    "recipe.hunyuan-image-to-video-concat-guidance": "hunyuan-image-to-video-concat-guidance",
    "recipe.hunyuan-refiner-latent-conditioning": "hunyuan-refiner-latent-conditioning",
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
PROBE = Path(__file__).with_name("hunyuan_video_conditioning_synthetic_probe.py")

SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
SOURCE_HASHES = {
    "comfy_extras/nodes_hunyuan.py": "97b684150cd18f9318d681abf4a4bc77929655d6f83ac49ad294ce913a60cc03",
    "comfy/model_base.py": "84c7756b4d2636cff80164ff73248068301e453fdd8631991007988203caa226",
    "comfy/supported_models.py": "827a21a2c9c2583f56e6ff8cecc46bfd8454808d741e7d688373a6795b3b7d42",
    "comfy/latent_formats.py": "3377e79659de42dd0f0a9850bd6b5cbfb4da737cb3d13a366f5566428bec52ab",
    "comfy/sample.py": "34a94286735b323b7c384d960b868752dbebacbc5b2eb04c09f99dd97ec7df5a",
    "comfy/samplers.py": "aabb644b0f864cd18110e64a9216701b8cbebec7a54c425477ae36a821a99e8e",
}
FRONTEND_ENUM_HASH = "74d106cbe62141f86991cd50aea7c341462933c4a5d7c66dd26d3764cba7fbe8"
DOC_HASHES = {
    "HunyuanVideo15ImageToVideo/en.md": "e60569c163c54c817594ca409d7e2fc57bd60ae6637392b989217bc566a5f4f6",
    "HunyuanVideo15ImageToVideo/ru.md": "2041bf5b726beaeaf20b6f876cc57268f6fa8d248cb4f7a452849f7d971cc266",
    "HunyuanVideo15SuperResolution/en.md": "865f03bbf77a1f2d6876204c0e566e1a9d3bca20f6cc3c023ff5107a9e46dd24",
    "HunyuanVideo15SuperResolution/ru.md": "ac4648e6ecfadc4d17c83b4fea0412903f163f5cba052766497aeab8f3e97eb1",
    "HunyuanImageToVideo/en.md": "a1f2d1a442aac9fe736e0d116a0f8a023c0b23bad02c136e968d00aa9e5eba18",
    "HunyuanImageToVideo/ru.md": "91745b9781c410c8c57be865e8d1c51e15d62f79ba9b861145f3bf6e01eab301",
    "HunyuanRefinerLatent/en.md": "3a3cac8daa96260522b77898854c6d876ef852890ee0813ca0c6f7d6f8a830c2",
    "HunyuanRefinerLatent/ru.md": "34f677973a4074e0a7dac326747e3003a839a76d8c379ebf862f9ffe636cc175",
}
WORKFLOW_MEMBER_HASHES = {
    "Image_capybara_v0_1_image_edit.json": "80e31cca9d819d144a570c349c0d20abdf8c8ba0bf5be672db333af0cd3cb41b",
    "video_capybara_v0_1_image_to_video.json": "9fa710ee75a352831f47e6aa36277bde3913daa57743de8c66915d8d6241cbbc",
    "video_capybara_v0_1_video_edit.json": "d202d82f4d0d89b5f19e50d00e37cec016e7b4bed06a8324be421f1972458e93",
    "video_hunyuan_video_1.5_720p_i2v.json": "4f6ab488b60f7b70f6501217c1ed697a366f29c3c36755e87ef76f6023676015",
    "video_hunyuan_video_1.5_720p_t2v.json": "b52ab35cd7f5253288d32ca2d18329607a0e5fb265886e234bae7b75deff8cfe",
}


def article_path(spec: dict[str, Any]) -> Path:
    return CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return CONTENT / "recipes" / RECIPE_DIRS[recipe_id] / "recipe.json"


def graph_scopes(payload: Any, scope: str = "root") -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield scope, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        yield from graph_scopes(subgraph, "subgraph")


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


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


class HunyuanVideoConditioningContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        all_article_ids = {
            catalog.load_json(path)["articleId"] for path in (CONTENT / "articles").rglob("manifest.json")
        }
        cliches = re.compile(
            r"важно отметить|стоит подчеркнуть|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
            r"не просто .{0,80}, а|без воды|коротко о главном|по-честному",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            manifest_path = article_path(spec)
            article = catalog.load_json(manifest_path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual("comfy_extras.nodes_hunyuan", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual({spec["recipe"]}, {asset["id"] for asset in article["assets"]})
            for relation in article["relations"]["related"] + article["relations"]["alternatives"]:
                self.assertIn(relation, all_article_ids | set(ARTICLE_SPECS), (article_id, relation))
            for source in article["sources"]:
                self.assertNotIn("/main/", source["url"])

            body = manifest_path.with_name(article["body"]).read_text(encoding="utf-8")
            headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
            self.assertEqual(EXPECTED_HEADINGS, headings, article_id)
            self.assertGreaterEqual(len(re.findall(r"[A-Za-zА-Яа-яЁё0-9][\w.-]*", body)), 500, article_id)
            self.assertIsNone(cliches.search(body), article_id)
            self.assertNotIn("Вот перевод документации", body)
            self.assertNotIn("human approval pending", body.lower())

            ledger_path = CONTENT / "research" / "reviews" / f"{article_id}.json"
            ledger = catalog.load_json(ledger_path)
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])

            recipe = catalog.load_json(recipe_path(spec["recipe"]))
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), spec["recipe"])
            self.assertEqual([article_id], recipe["articleIds"])
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path(spec["recipe"]).with_name(recipe["fragment"]["path"])
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), spec["recipe"])
            self.assertIn(spec["classType"], {node["classType"] for node in fragment["nodes"]})
            recipe_body = recipe_path(spec["recipe"]).with_name(recipe["body"]).read_text(encoding="utf-8")
            self.assertIsNone(cliches.search(recipe_body), spec["recipe"])
            self.assertIn("редактор пока не проверил материал вручную", recipe_body.lower())

        refiner_fragment = catalog.load_json(
            CONTENT / "recipes" / "hunyuan-refiner-latent-conditioning" / "fragment.json"
        )
        self.assertEqual([], refiner_fragment["connections"])
        sr_text = (CONTENT / "articles" / "core" / "hunyuan-video-15-super-resolution" / "ru.md").read_text("utf-8")
        self.assertIn("`BYPASS`", sr_text)
        self.assertIn("каналу `C + 1`", sr_text)
        refiner_text = (CONTENT / "articles" / "core" / "hunyuan-refiner-latent" / "ru.md").read_text("utf-8")
        self.assertIn("официальной топологии", refiner_text)
        self.assertIn("`[B, 32, C, H, W]`", refiner_text)
        self.assertIn("при `T > 1`", refiner_text)
        self.assertIn("при `T = 1`", refiner_text)
        self.assertIn("те же имена служебных ключей встречаются и у SR-модели", refiner_text)

    def test_runtime_identity_ports_options_flags_and_fingerprints(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        replacements = catalog.load_json(REPLACEMENTS)
        expected_required = {
            "HunyuanVideo15ImageToVideo": {"positive", "negative", "vae", "width", "height", "length", "batch_size"},
            "HunyuanVideo15SuperResolution": {"positive", "negative", "latent", "noise_augmentation"},
            "HunyuanImageToVideo": {"positive", "vae", "width", "height", "length", "batch_size", "guidance_type"},
            "HunyuanRefinerLatent": {"positive", "negative", "latent", "noise_augmentation"},
        }
        expected_optional = {
            "HunyuanVideo15ImageToVideo": {"start_image", "clip_vision_output"},
            "HunyuanVideo15SuperResolution": {"vae", "start_image", "clip_vision_output"},
            "HunyuanImageToVideo": {"start_image"},
            "HunyuanRefinerLatent": set(),
        }
        for spec in ARTICLE_SPECS.values():
            node_id = spec["classType"]
            runtime = inventory[node_id]
            self.assertEqual("comfy_extras.nodes_hunyuan", runtime["python_module"])
            self.assertEqual("model/conditioning/hunyuan video", runtime["category"])
            self.assertEqual(expected_required[node_id], set(runtime["input"].get("required", {})))
            self.assertEqual(expected_optional[node_id], set(runtime["input"].get("optional", {})))
            for flag in ("deprecated", "experimental", "dev_only", "api_node", "output_node", "is_input_list"):
                self.assertFalse(runtime[flag], (node_id, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(node_id, runtime))
            self.assertNotIn(node_id, replacements)

        i2v15 = runtime_inputs(inventory["HunyuanVideo15ImageToVideo"])
        self.assertEqual(["INT", {"default": 33, "max": 16384, "min": 1, "step": 4}], i2v15["length"])
        self.assertEqual(["CONDITIONING", "CONDITIONING", "LATENT"], inventory["HunyuanVideo15ImageToVideo"]["output"])
        self.assertEqual(["positive", "negative", "latent"], inventory["HunyuanVideo15ImageToVideo"]["output_name"])

        sr_noise = runtime_inputs(inventory["HunyuanVideo15SuperResolution"])["noise_augmentation"]
        self.assertEqual(["FLOAT", {"advanced": True, "default": 0.7, "max": 1.0, "min": 0.0, "step": 0.01}], sr_noise)
        old = runtime_inputs(inventory["HunyuanImageToVideo"])
        self.assertEqual(["v1 (concat)", "v2 (replace)", "custom"], old["guidance_type"][1]["options"])
        self.assertNotIn("default", old["guidance_type"][1])
        refiner_noise = runtime_inputs(inventory["HunyuanRefinerLatent"])["noise_augmentation"]
        self.assertEqual(0.1, refiner_noise[1]["default"])

    def test_pinned_sources_and_exact_source_probe(self) -> None:
        for relative, expected in SOURCE_HASHES.items():
            path = SOURCE / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), relative)

        node_source = (SOURCE / "comfy_extras" / "nodes_hunyuan.py").read_text("utf-8")
        self.assertIn("cond_latent[:, in_channels + 1, 0] = 1", node_source)
        self.assertIn("out_latent[\"samples\"] = torch.zeros([latent.shape[0], 32", node_source)
        self.assertIn("elif guidance_type == \"v2 (replace)\":", node_source)
        model_source = (SOURCE / "comfy" / "model_base.py").read_text("utf-8")
        self.assertIn("min(1.0 - noise_augmentation, 0.75) * image[:, lq_image_slice]", model_source)
        sampler_source = (SOURCE / "comfy" / "samplers.py").read_text("utf-8")
        self.assertIn("torch.count_nonzero(latent_image) > 0", sampler_source)

        enum_path = FRONTEND / "src" / "lib" / "litegraph" / "src" / "types" / "globalEnums.ts"
        self.assertEqual(FRONTEND_ENUM_HASH, hashlib.sha256(enum_path.read_bytes()).hexdigest())
        self.assertIn("BYPASS = 4", enum_path.read_text("utf-8"))

        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE), str(SOURCE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual([2, 32, 3, 3, 4], report["hunyuanVideo15ImageToVideo"]["latentShape"])
        self.assertEqual([0.0, 0.0, 1.0], report["hunyuanVideo15ImageToVideo"]["maskTemporalValues"])
        self.assertEqual([2, 66, 3, 3, 4], report["hunyuanVideo15SuperResolution"]["conditioningShape"])
        self.assertEqual(33, report["hunyuanVideo15SuperResolution"]["writtenMarkerChannel"])
        self.assertEqual("AttributeError", report["hunyuanVideo15SuperResolution"]["missingVaeWithStartImage"])
        self.assertEqual(["concat_latent_image", "concat_mask"], report["hunyuanImageToVideo"]["v1 (concat)"]["conditioningKeys"])
        self.assertEqual(["noise_mask", "samples"], report["hunyuanImageToVideo"]["v2 (replace)"]["latentKeys"])
        self.assertEqual([2, 32, 64, 4, 5], report["hunyuanRefinerLatent"]["fourDimensionalInputOutputShape"])
        consumer = report["hunyuanRefinerConsumerShape"]
        self.assertEqual([1, 64, 5, 2, 2], consumer["packedConditionT9"])
        self.assertEqual([1, 64, 9, 2, 2], consumer["blankAfterChannelFixT9"])
        self.assertEqual("RuntimeError: Sizes of tensors must match", consumer["temporalConcatT9"])
        self.assertEqual([1, 128, 1, 2, 2], consumer["joinedT1"])

    def test_embedded_docs_integrity_locales_and_exact_hashes(self) -> None:
        self.assertTrue(DOCS_WHEEL.is_file())
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        verify_wheel_record(DOCS_WHEEL)
        locales = {"ar", "en", "es", "fa", "fr", "ja", "ko", "pt-BR", "ru", "tr", "zh-TW", "zh"}
        base = "comfyui_embedded_docs/docs/"
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for directory in (
                "HunyuanVideo15ImageToVideo",
                "HunyuanVideo15SuperResolution",
                "HunyuanImageToVideo",
                "HunyuanRefinerLatent",
            ):
                found = {
                    Path(name).stem
                    for name in names
                    if name.startswith(base + directory + "/") and name.endswith(".md")
                }
                self.assertEqual(locales, found, directory)
            for relative, expected in DOC_HASHES.items():
                self.assertEqual(expected, hashlib.sha256(archive.read(base + relative)).hexdigest(), relative)

    def test_full_workflow_census_modes_widgets_and_topology(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file())
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        verify_wheel_record(WORKFLOW_WHEEL)
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: Counter() for target in targets}
        modes = {target: Counter() for target in targets}
        widgets = {target: Counter() for target in targets}
        files: dict[str, set[str]] = defaultdict(set)
        payloads: dict[str, dict[str, Any]] = {}
        json_count = root_count = graph_count = root_nodes = subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for suffix, expected in WORKFLOW_MEMBER_HASHES.items():
                member = next(name for name in archive.namelist() if name.endswith("/" + suffix))
                raw = archive.read(member)
                self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), suffix)
                payload = json.loads(raw.decode("utf-8"))
                self.assertIsInstance(payload, dict)
                payloads[suffix] = payload

            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                raw = archive.read(member)
                lowered = raw.lower()
                self.assertNotIn(b'"hunyuanimagetovideo"', lowered)
                self.assertNotIn(b'"hunyuanrefinerlatent"', lowered)
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
        self.assertEqual(Counter({"root": 1, "subgraph": 3}), counts["HunyuanVideo15ImageToVideo"])
        self.assertEqual(Counter({0: 4}), modes["HunyuanVideo15ImageToVideo"])
        self.assertEqual(
            Counter({(768, 1024, 1, 1): 1, (1280, 720, 81, 1): 1, (1280, 720, 121, 1): 2}),
            widgets["HunyuanVideo15ImageToVideo"],
        )
        self.assertEqual(Counter({"root": 2}), counts["HunyuanVideo15SuperResolution"])
        self.assertEqual(Counter({4: 2}), modes["HunyuanVideo15SuperResolution"])
        self.assertEqual(Counter({(0.7,): 2}), widgets["HunyuanVideo15SuperResolution"])
        self.assertEqual(Counter(), counts["HunyuanImageToVideo"])
        self.assertEqual(Counter(), counts["HunyuanRefinerLatent"])
        self.assertEqual(
            {
                "Image_capybara_v0_1_image_edit.json",
                "video_capybara_v0_1_image_to_video.json",
                "video_capybara_v0_1_video_edit.json",
                "video_hunyuan_video_1.5_720p_i2v.json",
            },
            files["HunyuanVideo15ImageToVideo"],
        )

        direct = payloads["video_hunyuan_video_1.5_720p_i2v.json"]
        nodes = {node["id"]: node for node in direct["nodes"]}
        self.assertEqual("HunyuanVideo15ImageToVideo", nodes[78]["type"])
        self.assertEqual([1280, 720, 121, 1], nodes[78]["widgets_values"])
        self.assertEqual(0, nodes[78]["mode"])
        self.assertIn([315, 78, 2, 125, 4, "LATENT"], direct["links"])
        self.assertIn([318, 78, 0, 129, 1, "CONDITIONING"], direct["links"])
        self.assertIn([319, 78, 1, 129, 2, "CONDITIONING"], direct["links"])
        self.assertEqual("HunyuanVideo15SuperResolution", nodes[113]["type"])
        self.assertEqual(4, nodes[113]["mode"])
        self.assertEqual([0.7], nodes[113]["widgets_values"])
        self.assertIn([280, 109, 0, 113, 2, "LATENT"], direct["links"])
        self.assertIn([327, 113, 2, 138, 4, "LATENT"], direct["links"])
        loader = next(node for node in direct["nodes"] if node["type"] == "DualCLIPLoader")
        self.assertIn("hunyuan_video_15", loader["widgets_values"])

        t2v = payloads["video_hunyuan_video_1.5_720p_t2v.json"]
        sr = next(node for node in t2v["nodes"] if node["type"] == "HunyuanVideo15SuperResolution")
        optional = {entry["name"]: entry.get("link") for entry in sr["inputs"]}
        self.assertIsNone(optional["vae"])
        self.assertIsNone(optional["start_image"])
        self.assertIsNone(optional["clip_vision_output"])


if __name__ == "__main__":
    unittest.main()
