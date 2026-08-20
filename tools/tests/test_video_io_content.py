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


ROOT = catalog.ROOT
COMFYUI_SOURCE = ROOT / ".comfyui-source-0.32.0"
FRONTEND_SOURCE = ROOT / ".frontend-source-1.48.7"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOW_WHEEL = (
    ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
PROBE = ROOT / "tools" / "tests" / "video_io_synthetic_probe.py"

DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"

ARTICLE_SPECS = {
    "core.save-webm": {
        "directory": "save-webm",
        "classType": "SaveWEBM",
        "recipe": "recipe.save-transparent-webm",
        "fingerprint": "sha256:c364ee52241db7fb25cb1d4668eb3546b4b98be28899e09cecf7545b4c28d4d6",
        "experimental": True,
        "outputNode": True,
    },
    "core.save-video": {
        "directory": "save-video",
        "classType": "SaveVideo",
        "recipe": "recipe.save-video-mp4-auto",
        "fingerprint": "sha256:b421568a0299771758de4877730b9027faa4ece7f7085b5097eb4181b5487006",
        "experimental": False,
        "outputNode": True,
    },
    "core.create-video": {
        "directory": "create-video",
        "classType": "CreateVideo",
        "recipe": "recipe.create-video-with-audio",
        "fingerprint": "sha256:83a49dfffa5293faddb8ed1287f5d1a487cfd3c2676bb46857276b354b1eb1b7",
        "experimental": False,
        "outputNode": False,
    },
    "core.get-video-components": {
        "directory": "get-video-components",
        "classType": "GetVideoComponents",
        "recipe": "recipe.inspect-video-components",
        "fingerprint": "sha256:a9170e381913f3f62f44ce98fcc8749eda141bbf63217660f71846a4ebbed7b9",
        "experimental": False,
        "outputNode": False,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.save-transparent-webm": "save-transparent-webm",
    "recipe.save-video-mp4-auto": "save-video-mp4-auto",
    "recipe.create-video-with-audio": "create-video-with-audio",
    "recipe.inspect-video-components": "inspect-video-components",
}

DOC_HASHES = {
    ("SaveWEBM", "en"): "d1995969dfadfc2810c0dabcb2eea6284af67999f1dd5440d0edbed5f4f7484b",
    ("SaveWEBM", "ru"): "530596e1a0dde3e90a4061ddfbeedc39afc72ff25d4acc6205c3a31dc21af24f",
    ("SaveVideo", "en"): "fdbaff0406f7879e77699b6186634a255a92f9c90dd37e02144559a031154388",
    ("SaveVideo", "ru"): "376c977d15354468d46873cf2e231858081fc292e8424a96cbded817be877e52",
    ("CreateVideo", "en"): "b9b66324de91f48e83177586bd253d4de3d2cc7a00f6bd4ed70b063822dfabcc",
    ("CreateVideo", "ru"): "b7e434cbc873cde822b138c4d98186cacb1bf3bcedf22b105c33a78e610eb9d5",
    ("GetVideoComponents", "en"): "e8460b7b3c33a4b231948110c4b9e990d4c4b2e67f3679e2c6bc47f2e97fb899",
    ("GetVideoComponents", "ru"): "3925cdee6a1aba9b6667b6907040369bc37c54f5db11c86614b037c5ce35ab36",
}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        try:
            payload = catalog.load_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def workflow_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict):
            yield "subgraph", subgraph


def graph_links(graph: dict[str, Any]) -> list[tuple[Any, Any, Any, Any, Any, Any]]:
    result = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(tuple(link[:6]))
        elif isinstance(link, dict):
            result.append(
                (
                    link.get("id"),
                    link.get("origin_id"),
                    link.get("origin_slot"),
                    link.get("target_id"),
                    link.get("target_slot"),
                    link.get("type"),
                )
            )
    return result


class VideoIOContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
        )
        research_schema = catalog.load_json(
            catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
        )
        article_ids = all_article_ids()
        errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"является незаменим|данная нода|давайте разбер|подводя итог|"
            r"мощный инструмент|без лишних слов|коротко о главном",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy-core", article["runtimeIdentity"]["packageId"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), article_id)

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotRegex(body, cliches)
            self.assertNotIn("human approval pending", body.lower())
            self.assertIn("Редактор пока не проверил материал вручную.", body)

            record_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, research_schema), article_id)
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["checks"]["exampleSchemaValidated"])
            self.assertTrue(record["checks"]["russianEdited"])
            self.assertTrue(record["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(
                any("Редактор пока" in gap for gap in record["knownGaps"]),
                article_id,
            )
            self.assertNotIn("approved", record_path.read_text(encoding="utf-8").lower())

        self.assertEqual([], errors)

        expected_classes = {
            "recipe.save-transparent-webm": ["SaveWEBM"],
            "recipe.save-video-mp4-auto": ["SaveVideo"],
            "recipe.create-video-with-audio": ["CreateVideo"],
            "recipe.inspect-video-components": ["GetVideoComponents", "CreateVideo"],
        }
        for recipe_id, expected in expected_classes.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            self.assertEqual(expected, [node["classType"] for node in fragment["nodes"]])
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)
            for text_path in (path, path.parent / "ru.md", path.parent / "fragment.json"):
                self.assertNotIn("approved", text_path.read_text(encoding="utf-8").lower())
        self.assertEqual([], errors)

        save_fragment = catalog.load_json(
            catalog.CONTENT / "recipes" / "save-video-mp4-auto" / "fragment.json"
        )
        self.assertEqual({"codec": "auto"}, save_fragment["nodes"][0]["settings"]["codec"])
        roundtrip = catalog.load_json(
            catalog.CONTENT / "recipes" / "inspect-video-components" / "fragment.json"
        )
        self.assertEqual(
            {"images", "audio", "fps", "bit_depth"},
            {connection["output"] for connection in roundtrip["connections"]},
        )

    def test_runtime_contracts_and_fingerprints(self) -> None:
        runtime = catalog.load_json(catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json")
        for article_id, spec in ARTICLE_SPECS.items():
            class_type = spec["classType"]
            node = runtime[class_type]
            self.assertEqual("comfy_extras.nodes_video", node["python_module"])
            self.assertEqual("video", node["category"])
            self.assertEqual(spec["experimental"], node["experimental"])
            self.assertEqual(spec["outputNode"], node["output_node"])
            self.assertFalse(node["deprecated"])
            self.assertFalse(node["api_node"])
            self.assertFalse(node["dev_only"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, node), article_id)

        save_webm = runtime["SaveWEBM"]
        self.assertEqual(
            ["images", "filename_prefix", "codec", "fps", "crf"],
            save_webm["input_order"]["required"],
        )
        self.assertEqual(["vp9", "av1"], save_webm["input"]["required"]["codec"][1]["options"])
        self.assertEqual((0.01, 1000.0, 0.01), tuple(save_webm["input"]["required"]["fps"][1][key] for key in ("min", "max", "step")))
        self.assertEqual(["IMAGE"], save_webm["output"])
        self.assertEqual(["images"], save_webm["output_name"])

        save_video = runtime["SaveVideo"]
        self.assertEqual(["auto", "mp4"], save_video["input"]["required"]["format"][1]["options"])
        codec_spec = save_video["input"]["required"]["codec"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", codec_spec[0])
        self.assertEqual(["auto", "h264"], [item["key"] for item in codec_spec[1]["options"]])
        encoding = codec_spec[1]["options"][1]["inputs"]["optional"]["encoding"]
        self.assertEqual(["auto", "re-encode"], [item["key"] for item in encoding[1]["options"]])
        crf = encoding[1]["options"][1]["inputs"]["required"]["crf"][1]
        self.assertEqual((23.0, 0.0, 51.0, 1.0), (crf["default"], crf["min"], crf["max"], crf["step"]))
        self.assertEqual((["VIDEO"], ["video"]), (save_video["output"], save_video["output_name"]))

        create = runtime["CreateVideo"]
        self.assertEqual(["images", "fps"], create["input_order"]["required"])
        self.assertEqual(["audio", "bit_depth"], create["input_order"]["optional"])
        bit_depth = create["input"]["optional"]["bit_depth"][1]
        self.assertEqual((8, 8, 10, 2), (bit_depth["default"], bit_depth["min"], bit_depth["max"], bit_depth["step"]))
        self.assertEqual(["VIDEO"], create["output"])

        components = runtime["GetVideoComponents"]
        self.assertEqual(["video"], components["input_order"]["required"])
        self.assertEqual(["IMAGE", "AUDIO", "FLOAT", "INT"], components["output"])
        self.assertEqual(["images", "audio", "fps", "bit_depth"], components["output_name"])

    def test_pinned_backend_and_frontend_sources(self) -> None:
        expected_hashes = {
            COMFYUI_SOURCE / "comfy_extras" / "nodes_video.py": "0b3521047896a30e2699c9effa3840d78875fb11a205c53635a9b6950a3304dc",
            COMFYUI_SOURCE / "comfy_api" / "latest" / "_util" / "video_types.py": "e510af45acc7ccc01adc602d216cd7a32f61af8c8334984936185863e75ae89b",
            COMFYUI_SOURCE / "comfy_api" / "latest" / "_input_impl" / "video_types.py": "a57cef87aebffbcbb3363c48799a0939e1b365a0b8ad9af0d857899e6a1a5b09",
            COMFYUI_SOURCE / "comfy_api" / "latest" / "_ui.py": "ef5fb612305207d1673eda16172a82407e6657b958f85ad14d0d0272b0745d38",
            FRONTEND_SOURCE / "src" / "extensions" / "core" / "saveImageExtraOutput.ts": "2115ffeb31f3099e0e97b46304b802653c1ba58ad746323d1b094a1605265682",
            FRONTEND_SOURCE / "src" / "core" / "graph" / "widgets" / "dynamicWidgets.ts": "cb4119b8fc2561b3059f0ee6f450ec46e19df38652263870063af210b7369ec8",
            FRONTEND_SOURCE / "src" / "constants" / "essentialsNodes.ts": "2069a77c1edcee44e13eabd0f96749cd5b23695c7089595dd6ab32616bb93c2e",
            FRONTEND_SOURCE / "src" / "renderer" / "extensions" / "linearMode" / "getExecutionStatusMessage.ts": "423bbfb0e17e3aa85a81b89a7fc857b419399aaa2478d80f1f10336475cd8528",
        }
        for path, expected in expected_hashes.items():
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        nodes = (COMFYUI_SOURCE / "comfy_extras" / "nodes_video.py").read_text(encoding="utf-8")
        for marker in (
            'save_alpha = images.shape[-1] == 4 and codec == "vp9"',
            'codec_map = {"vp9": "libvpx-vp9", "av1": "libsvtav1"}',
            'Types.VideoContainer.get_extension(format)',
            'encoding.get("crf")',
            'Types.VideoComponents(images=images, audio=audio, frame_rate=Fraction(fps))',
            'components = video.get_components()',
            'video.get_bit_depth()',
        ):
            self.assertIn(marker, nodes)

        impl = (
            COMFYUI_SOURCE / "comfy_api" / "latest" / "_input_impl" / "video_types.py"
        ).read_text(encoding="utf-8")
        for marker in (
            "if crf is not None:\n                reuse_streams = False",
            "return self._save_transcoded",
            "pix_fmt = \"yuv420p10le\" if bit_depth >= 10 else \"yuv420p\"",
            "class VideoFromComponents(VideoInput):",
            "waveform = waveform[0, :, :math.ceil",
            "return VideoComponents(images=images, alpha=alphas, audio=audio, frame_rate=frame_rate, metadata=metadata)",
        ):
            self.assertIn(marker, impl)

        dynamic = (
            FRONTEND_SOURCE / "src" / "core" / "graph" / "widgets" / "dynamicWidgets.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("const updateWidgets = (value?: string) =>", dynamic)
        self.assertIn("COMFY_DYNAMICCOMBO_V3: dynamicComboWidget", dynamic)
        save_extra = (
            FRONTEND_SOURCE / "src" / "extensions" / "core" / "saveImageExtraOutput.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("'SaveVideo'", save_extra)
        self.assertIn("'SaveWEBM'", save_extra)
        self.assertIn("applyTextReplacements(app.graph, widget.value)", save_extra)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_embedded_docs_are_pinned_and_discrepancies_recorded(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for (class_type, locale), expected in DOC_HASHES.items():
                name = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                payload = archive.read(name)
                self.assertEqual(expected, hashlib.sha256(payload).hexdigest(), name)

            save_video_en = archive.read(
                "comfyui_embedded_docs/docs/SaveVideo/en.md"
            ).decode("utf-8")
            self.assertIn('`"webm"`', save_video_en)
            self.assertIn('`"prores"`', save_video_en)
            create_ru = archive.read(
                "comfyui_embedded_docs/docs/CreateVideo/ru.md"
            ).decode("utf-8")
            get_ru = archive.read(
                "comfyui_embedded_docs/docs/GetVideoComponents/ru.md"
            ).decode("utf-8")
            self.assertNotIn("bit_depth", create_ru)
            self.assertNotIn("bit_depth", get_ru)

        save_record = catalog.load_json(
            catalog.CONTENT / "research" / "reviews" / "core.save-video.json"
        )
        assessments = " ".join(
            item["assessment"] for item in save_record["evidence"]["embeddedDocs"]
        )
        for value in ("WebM", "ProRes", "возврат исходного VIDEO"):
            self.assertIn(value, assessments)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "pinned workflow wheel is absent")
    def test_workflow_wheel_integrity_full_census_and_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        files: dict[str, set[str]] = defaultdict(set)
        workflow_ids: dict[str, set[str]] = defaultdict(set)
        widget_patterns: dict[str, Counter[str]] = defaultdict(Counter)
        save_formats: Counter[str] = Counter()
        save_codecs: Counter[str] = Counter()
        json_count = root_count = subgraph_count = node_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(
                archive.read(record_name).decode("utf-8").splitlines()
            ):
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                payload = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, payload).digest()).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual)
                self.assertEqual(int(size), len(payload))
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            templates: dict[str, dict[str, Any]] = {}
            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if member.startswith("comfyui_workflow_templates_json/templates/"):
                    templates[member.rsplit("/", 1)[-1]] = payload
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for scope, graph in workflow_scopes(payload):
                    if scope == "subgraph":
                        subgraph_count += 1
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    node_count += len(nodes)
                    for node in nodes:
                        class_type = node.get("type")
                        if class_type not in targets:
                            continue
                        counts[class_type] += 1
                        scopes[(class_type, scope)] += 1
                        modes[class_type][node.get("mode", 0)] += 1
                        files[class_type].add(member)
                        workflow_ids[class_type].add(str(payload.get("id")))
                        widget_patterns[class_type][
                            json.dumps(node.get("widgets_values"), ensure_ascii=False, separators=(",", ":"))
                        ] += 1
                        if class_type == "SaveVideo":
                            widgets = node.get("widgets_values")
                            self.assertIsInstance(widgets, list)
                            self.assertEqual(3, len(widgets))
                            save_formats[widgets[1]] += 1
                            save_codecs[widgets[2]] += 1

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(
            Counter({"SaveVideo": 226, "CreateVideo": 102, "GetVideoComponents": 49, "SaveWEBM": 1}),
            counts,
        )
        self.assertEqual((1, 0), (scopes[("SaveWEBM", "root")], scopes[("SaveWEBM", "subgraph")]))
        self.assertEqual((226, 0), (scopes[("SaveVideo", "root")], scopes[("SaveVideo", "subgraph")]))
        self.assertEqual((51, 51), (scopes[("CreateVideo", "root")], scopes[("CreateVideo", "subgraph")]))
        self.assertEqual((24, 25), (scopes[("GetVideoComponents", "root")], scopes[("GetVideoComponents", "subgraph")]))
        self.assertEqual((1, 192, 79, 32), tuple(len(files[name]) for name in ("SaveWEBM", "SaveVideo", "CreateVideo", "GetVideoComponents")))
        self.assertEqual((1, 114, 42, 27), tuple(len(workflow_ids[name]) for name in ("SaveWEBM", "SaveVideo", "CreateVideo", "GetVideoComponents")))
        self.assertEqual(Counter({0: 1}), modes["SaveWEBM"])
        self.assertEqual(Counter({0: 213, 4: 13}), modes["SaveVideo"])
        self.assertEqual(Counter({0: 93, 4: 9}), modes["CreateVideo"])
        self.assertEqual(Counter({0: 48, 4: 1}), modes["GetVideoComponents"])
        self.assertEqual(Counter({"auto": 218, "mp4": 8}), save_formats)
        self.assertEqual(Counter({"auto": 216, "h264": 10}), save_codecs)
        self.assertEqual(Counter({'["ComfyUI","vp9",24,32]': 1}), widget_patterns["SaveWEBM"])
        self.assertEqual(
            Counter({"[16]": 27, "[24]": 22, "[24,8]": 13, "[30,8]": 11, "[25,8]": 10, "[30]": 8, "[16,8]": 7, "[25]": 2, "[10]": 1, "[8,8]": 1}),
            widget_patterns["CreateVideo"],
        )

        bria = templates["api_bria_remove_video_background_transparent.json"]
        bria_nodes = {node["id"]: node for node in bria["nodes"]}
        self.assertEqual("6874296f-e51d-46b4-9bf5-f70b6d81a9ce", bria["id"])
        self.assertEqual(["ComfyUI", "vp9", 24, 32], bria_nodes[7]["widgets_values"])
        self.assertEqual("JoinImageWithAlpha", bria_nodes[6]["type"])
        self.assertEqual("GetVideoComponents", bria_nodes[8]["type"])
        self.assertIn((4, 6, 0, 7, 0, "IMAGE"), graph_links(bria))
        self.assertIn((6, 8, 2, 7, 1, "FLOAT"), graph_links(bria))

        seedvr = templates["utility_seedvr2_3b_int8_upscale_video.json"]
        seed_root_nodes = {node["id"]: node for node in seedvr["nodes"]}
        self.assertEqual("SaveVideo", seed_root_nodes[76]["type"])
        self.assertEqual(["video/Upscaled_seedVR2", "auto", "auto"], seed_root_nodes[76]["widgets_values"])
        seed_sub = seedvr["definitions"]["subgraphs"][0]
        seed_nodes = {node["id"]: node for node in seed_sub["nodes"]}
        self.assertEqual("GetVideoComponents", seed_nodes[74]["type"])
        self.assertEqual("CreateVideo", seed_nodes[75]["type"])
        self.assertEqual([30, 8], seed_nodes[75]["widgets_values"])
        links = graph_links(seed_sub)
        for expected in (
            (68, 74, 1, 75, 1, "AUDIO"),
            (69, 74, 2, 75, 2, "FLOAT"),
            (70, 74, 3, 75, 3, "INT"),
        ):
            self.assertIn(expected, links)

        ltx = templates["video_ltx2_3_t2v.json"]
        ltx_sub = ltx["definitions"]["subgraphs"][0]
        self.assertEqual("b94257db-cdc1-45d3-8913-ca61e782d9c1", ltx_sub["id"])
        ltx_nodes = {node["id"]: node for node in ltx_sub["nodes"]}
        self.assertEqual(("CreateVideo", [24]), (ltx_nodes[242]["type"], ltx_nodes[242]["widgets_values"]))
        self.assertIn((538, 251, 0, 242, 0, "IMAGE"), graph_links(ltx_sub))
        self.assertIn((534, 220, 0, 242, 1, "AUDIO"), graph_links(ltx_sub))

    def test_safe_exact_source_probe(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(COMFYUI_SOURCE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(
            {
                "vp9PixelFormat": "yuva420p",
                "vp9FrameFormat": "rgba",
                "av1PixelFormat": "yuv420p10le",
                "av1FrameFormat": "rgb24",
                "fps": 23.976,
                "frameCount": 2,
            },
            result["saveWebm"],
        )
        self.assertEqual(
            {"extension": ".mp4", "codec": "h264", "crf": 19, "passthrough": True},
            result["saveVideo"],
        )
        self.assertEqual([3, 2, 4, 3], result["createAndExtract"]["frameShape"])
        self.assertEqual(10, result["createAndExtract"]["bitDepth"])
        self.assertTrue(result["createAndExtract"]["frameIdentity"])
        self.assertTrue(result["createAndExtract"]["audioIdentity"])
        self.assertFalse(result["realEncodingExecuted"])


if __name__ == "__main__":
    unittest.main()
