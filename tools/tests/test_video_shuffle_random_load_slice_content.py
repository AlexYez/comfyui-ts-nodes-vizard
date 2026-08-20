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
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.shuffle-video-dataset": {
        "directory": "shuffle-video-dataset",
        "classType": "ShuffleVideoDataset",
        "module": "comfy_extras.nodes_dataset",
        "category": "video/batch",
        "experimental": True,
        "fingerprint": "sha256:b41d6d392f5532ece76ea694e1a07436e4312ffbe13896aecf16a643ffb42638",
        "recipe": "recipe.shuffle-video-dataset-seed-7",
        "isInputList": True,
        "outputs": ["VIDEO"],
        "outputNames": ["videos"],
        "outputLists": [True],
        "required": ["videos", "seed"],
    },
    "core.video-random-temporal-crop": {
        "directory": "video-random-temporal-crop",
        "classType": "VideoRandomTemporalCrop",
        "module": "comfy_extras.nodes_dataset",
        "category": "video/transform",
        "experimental": True,
        "fingerprint": "sha256:584bfd9706db4ca8f1e840eca4d90372fe76cb370ee55f898e5517bc336657d5",
        "recipe": "recipe.video-random-temporal-crop-16-seed-7",
        "isInputList": False,
        "outputs": ["VIDEO"],
        "outputNames": ["video"],
        "outputLists": [False],
        "required": ["video", "length", "seed"],
    },
    "core.load-video": {
        "directory": "load-video",
        "classType": "LoadVideo",
        "module": "comfy_extras.nodes_video",
        "category": "video",
        "experimental": False,
        "fingerprint": "sha256:444e7dcce78c5cb866b26650edf804c3f7a4d58a67ff7e7a725f8f803acc63dd",
        "recipe": "recipe.load-video-basic",
        "isInputList": False,
        "outputs": ["VIDEO"],
        "outputNames": ["VIDEO"],
        "outputLists": [False],
        "required": ["file"],
    },
    "core.video-slice": {
        "directory": "video-slice",
        "classType": "Video Slice",
        "module": "comfy_extras.nodes_video",
        "category": "video",
        "experimental": False,
        "fingerprint": "sha256:557c21c6907520695f354631878db6d095b920f2d341a0d7086f54695af16384",
        "recipe": "recipe.video-slice-first-five-seconds",
        "isInputList": False,
        "outputs": ["VIDEO"],
        "outputNames": ["VIDEO"],
        "outputLists": [False],
        "required": ["video", "start_time", "duration", "strict_duration"],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.shuffle-video-dataset-seed-7": "shuffle-video-dataset-seed-7",
    "recipe.video-random-temporal-crop-16-seed-7": "video-random-temporal-crop-16-seed-7",
    "recipe.load-video-basic": "load-video-basic",
    "recipe.video-slice-first-five-seconds": "video-slice-first-five-seconds",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.shuffle-video-dataset-seed-7": [
        ("ShuffleVideoDataset", {"seed": 7})
    ],
    "recipe.video-random-temporal-crop-16-seed-7": [
        ("VideoRandomTemporalCrop", {"length": 16, "seed": 7})
    ],
    "recipe.load-video-basic": [
        ("LoadVideo", {"file": "SELECT_INPUT_VIDEO"})
    ],
    "recipe.video-slice-first-five-seconds": [
        (
            "Video Slice",
            {"start_time": 0.0, "duration": 5.0, "strict_duration": False},
        )
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = (
    catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
)
REPLACEMENTS_SHA256 = (
    "4d9e22176cbddd8c309707d434f011854cd768f92146586bf9e17c01e93ae5b6"
)
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
EMBEDDED_DOC_HASHES = {
    "ShuffleVideoDataset": {
        "en": "08655414a759493d39bcfa384a622896c12e2555a9208fc676552ceb1b5fa15f",
        "ru": "61d4bc6d0303daa3ca444be0f2e85cda1ce928127e6227e80b12212d806f5d8b",
    },
    "VideoRandomTemporalCrop": {
        "en": "a410acb6d8685d0f58f769bd3d183f1d2e69739a312c587f739aedbfda8f9188",
        "ru": "7fe7c895c25e0cdf8f118158469a8fae47ac2ccf57c4b65fd41d026e0fda3713",
    },
    "LoadVideo": {
        "en": "517f1d75d3968fab9ee3f80834cdea6d300d8851d6ad27c99893f728a1a222d2",
        "ru": "eda1c9ffa16bab86c48049395412865635a91ea6deefd0a202c9940f3e27f384",
    },
    "Video Slice": {
        "en": "74852b5b4f1ef46c74563c51dfe07665e542a40242ce3fc5943d5c6d8f6314e7",
        "ru": "d5a8fe6c3d7338831b6e234e774ad275d9488443e661e14038e7cbc8d91fd933",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "video_shuffle_random_load_slice_synthetic_probe.py"
)


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return (
        catalog.CONTENT
        / "recipes"
        / RECIPE_DIRECTORIES[recipe_id]
        / "recipe.json"
    )


def all_ids(root: Path, filename: str, field: str) -> list[str]:
    result: list[str] = []
    for path in root.rglob(filename):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get(field), str):
            result.append(payload[field])
    return result


def runtime_input_specs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def descriptor_type(descriptor: Any) -> Any:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    value = descriptor[0]
    return "COMBO" if isinstance(value, list) or value == "COMBO" else value


class VideoShuffleRandomLoadSliceContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_id_list = all_ids(
            catalog.CONTENT / "articles", "manifest.json", "articleId"
        )
        recipe_id_list = all_ids(
            catalog.CONTENT / "recipes", "recipe.json", "recipeId"
        )
        article_counts = Counter(article_id_list)
        recipe_counts = Counter(recipe_id_list)
        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, article_counts[article_id], article_id)
            self.assertEqual(1, recipe_counts[spec["recipe"]], spec["recipe"])
        article_ids = set(article_id_list)

        schemas = {
            "article": catalog.load_json(
                catalog.CONTENT / "schemas" / "article.schema.v1.json"
            ),
            "recipe": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
            ),
            "fragment": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
            ),
            "research": catalog.load_json(
                catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
            ),
        }
        banned = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является незаменим|является мощн|\bдавайте\b|"
            r"глубже погруз|открывает новые|может показаться|позволяет вам|"
            r"подводя итог|в заключение|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(
                {spec["recipe"]},
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                },
            )
            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id
            )
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), article_id)
            self.assertIn(spec["fingerprint"], body)
            self.assertRegex(body.lower(), r"официальн")

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertIn(
                "Статья ожидает человеческого утверждения.", research["knownGaps"]
            )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fail_closed_fragments(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["module"], runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["experimental"], runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("output_node", False))
            self.assertEqual(spec["isInputList"], runtime["is_input_list"])
            self.assertEqual(spec["outputs"], runtime["output"])
            self.assertEqual(spec["outputNames"], runtime["output_name"])
            self.assertEqual(spec["outputLists"], runtime["output_is_list"])
            self.assertEqual(spec["required"], runtime["input_order"]["required"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        shuffle = nodes["ShuffleVideoDataset"]
        self.assertEqual("VIDEO", descriptor_type(shuffle["input"]["required"]["videos"]))
        shuffle_seed = shuffle["input"]["required"]["seed"]
        self.assertEqual("INT", descriptor_type(shuffle_seed))
        self.assertEqual(
            {"default": 0, "min": 0, "max": 2**64 - 1},
            {key: shuffle_seed[1][key] for key in ("default", "min", "max")},
        )

        random_crop = nodes["VideoRandomTemporalCrop"]
        self.assertEqual("VIDEO", descriptor_type(random_crop["input"]["required"]["video"]))
        length = random_crop["input"]["required"]["length"]
        seed = random_crop["input"]["required"]["seed"]
        self.assertEqual(
            {"default": 16, "min": 1, "max": 99999},
            {key: length[1][key] for key in ("default", "min", "max")},
        )
        self.assertEqual(
            {"default": 0, "min": 0, "max": 2**64 - 1},
            {key: seed[1][key] for key in ("default", "min", "max")},
        )

        load = nodes["LoadVideo"]
        file_descriptor = load["input"]["required"]["file"]
        self.assertEqual("COMBO", descriptor_type(file_descriptor))
        self.assertEqual([], file_descriptor[1]["options"])
        self.assertTrue(file_descriptor[1]["video_upload"])

        video_slice = nodes["Video Slice"]
        start = video_slice["input"]["required"]["start_time"]
        duration = video_slice["input"]["required"]["duration"]
        strict = video_slice["input"]["required"]["strict_duration"]
        self.assertEqual(
            {"default": 0.0, "min": -100000.0, "max": 100000.0, "step": 0.001},
            {key: start[1][key] for key in ("default", "min", "max", "step")},
        )
        self.assertEqual(
            {"default": 0.0, "min": 0.0, "step": 0.001},
            {key: duration[1][key] for key in ("default", "min", "step")},
        )
        self.assertNotIn("max", duration[1])
        self.assertEqual("BOOLEAN", descriptor_type(strict))
        self.assertFalse(strict[1]["default"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in node_by_ref.items()}
            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(nodes[target["classType"]])[
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])
            for ref, node in node_by_ref.items():
                required = set(nodes[node["classType"]]["input"]["required"])
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))

        load_path = recipe_path("recipe.load-video-basic")
        load_recipe = catalog.load_json(load_path)
        load_fragment = catalog.load_json(load_path.parent / load_recipe["fragment"]["path"])
        self.assertEqual(
            "SELECT_INPUT_VIDEO", load_fragment["nodes"][0]["settings"]["file"]
        )
        self.assertNotIn("SELECT_INPUT_VIDEO", file_descriptor[1]["options"])
        self.assertTrue(any("Ручной выбор" in item for item in load_recipe["requirements"]))
        self.assertIn(
            "Служебное значение нельзя выполнять",
            (load_path.parent / load_recipe["body"]).read_text(encoding="utf-8"),
        )

    def test_exact_pinned_source_and_replacement_contracts(self) -> None:
        self.assertTrue(SOURCE.is_dir())
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )
        nodes_video = (SOURCE / "comfy_extras" / "nodes_video.py").read_text(
            encoding="utf-8"
        )
        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        video_types = (
            SOURCE / "comfy_api" / "latest" / "_input_impl" / "video_types.py"
        ).read_text(encoding="utf-8")

        random_start = dataset.index("class VideoRandomTemporalCropNode")
        shuffle_start = dataset.index("class ShuffleVideoDatasetNode")
        paired_start = dataset.index("class ShuffleVideoTextDatasetNode")
        random_block = dataset[random_start:shuffle_start]
        shuffle_block = dataset[shuffle_start:paired_start]
        self.assertIn("length = min(length, total_frames)", random_block)
        self.assertIn("max_start = total_frames - length", random_block)
        self.assertIn("np.random.RandomState(seed % (2**32 - 1))", random_block)
        self.assertIn("rng.randint(0, max_start + 1) if max_start > 0 else 0", random_block)
        self.assertIn("start / fps, length / fps, strict_duration=False", random_block)
        self.assertIn("seed = seed[0] if isinstance(seed, list) else seed", shuffle_block)
        self.assertIn("np.random.seed(seed % (2**32 - 1))", shuffle_block)
        self.assertIn("np.random.permutation(len(videos))", shuffle_block)
        self.assertIn("[videos[i] for i in indices]", shuffle_block)

        load_start = nodes_video.index("class LoadVideo(io.ComfyNode):")
        slice_start = nodes_video.index("class VideoSlice(io.ComfyNode):")
        extension_start = nodes_video.index("class VideoExtension", slice_start)
        load_block = nodes_video[load_start:slice_start]
        slice_block = nodes_video[slice_start:extension_start]
        self.assertIn("os.path.isfile(os.path.join(input_dir, f))", load_block)
        self.assertIn('filter_files_content_types(files, ["video"])', load_block)
        self.assertIn('io.Combo.Input("file", options=sorted(files), upload=io.UploadType.video)', load_block)
        self.assertIn("folder_paths.get_annotated_filepath(file)", load_block)
        self.assertIn("InputImpl.VideoFromFile(video_path)", load_block)
        self.assertIn("os.path.getmtime(video_path)", load_block)
        self.assertIn("folder_paths.exists_annotated_filepath(file)", load_block)
        self.assertIn('node_id="Video Slice"', slice_block)
        self.assertIn('"duration",\n                    default=0.0', slice_block)
        self.assertIn('"strict_duration",\n                    default=False', slice_block)
        self.assertIn("video.as_trimmed(start_time, duration, strict_duration=strict_duration)", slice_block)
        self.assertIn("if trimmed is not None:", slice_block)
        self.assertIn("Failed to slice video", slice_block)

        self.assertIn("mimetypes.guess_type(file, strict=False)", folder_paths)
        self.assertIn("filepath = os.path.abspath(os.path.join(base_dir, name))", folder_paths)
        self.assertIn("if not is_within_directory(base_dir, filepath):", folder_paths)
        self.assertIn("return os.path.exists(filepath)", folder_paths)
        self.assertIn("start_time=start_time + self.__start_time", video_types)
        self.assertIn("if trimmed.get_duration() < duration and strict_duration:", video_types)
        self.assertIn("if self.get_duration() < start_time + duration:", video_types)
        self.assertIn("return VideoFromFile(self.get_stream_source(), start_time=start_time, duration=duration)", video_types)

        self.assertTrue(REPLACEMENTS.is_file())
        self.assertEqual(
            REPLACEMENTS_SHA256, hashlib.sha256(REPLACEMENTS.read_bytes()).hexdigest()
        )
        replacement_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_text)

    def test_embedded_docs_case_sensitive_members_hashes_and_gaps(self) -> None:
        self.assertTrue(EMBEDDED_DOCS_WHEEL.is_file())
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            names = archive.namelist()
            for class_type, locales in EMBEDDED_DOC_HASHES.items():
                exact = [
                    name
                    for name in names
                    if re.search(rf"/{re.escape(class_type)}/(?:en|ru)\.md$", name)
                ]
                insensitive = [
                    name
                    for name in names
                    if re.search(
                        rf"/{re.escape(class_type)}/(?:en|ru)\.md$",
                        name,
                        flags=re.IGNORECASE,
                    )
                ]
                self.assertEqual(2, len(exact), class_type)
                self.assertEqual(exact, insensitive)
                for locale, expected_hash in locales.items():
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    payload = archive.read(member)
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in EMBEDDED_DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("experimental", docs[(class_type, "en")].lower())
        self.assertIn("| `seed` |", docs[("ShuffleVideoDataset", "en")])
        self.assertIn("| INT | No |", docs[("ShuffleVideoDataset", "en")])
        self.assertNotIn("2**32", docs[("ShuffleVideoDataset", "en")])
        self.assertIn("operates lazily", docs[("VideoRandomTemporalCrop", "en")])
        self.assertNotIn("max_start", docs[("VideoRandomTemporalCrop", "en")])
        self.assertIn("| STRING | Yes |", docs[("LoadVideo", "en")])
        self.assertNotIn("mtime", docs[("LoadVideo", "en")])
        self.assertIn("duration is longer", docs[("Video Slice", "en")])
        self.assertIn("| FLOAT | No |", docs[("Video Slice", "en")])
        self.assertNotIn("parent", docs[("Video Slice", "en")].lower())
        self.assertIn("`видео`", docs[("ShuffleVideoDataset", "ru")])
        self.assertIn("`файл`", docs[("LoadVideo", "ru")])
        self.assertIn("`время начала`", docs[("Video Slice", "ru")])

    def test_exhaustive_workflow_census_and_real_topologies(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file())
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        raw_members: dict[str, set[str]] = {target: set() for target in targets}
        root_hits: dict[str, list[tuple[str, dict[str, Any]]]] = {
            target: [] for target in targets
        }
        subgraph_hits: dict[str, list[tuple[str, dict[str, Any]]]] = {
            target: [] for target in targets
        }
        downstream = Counter()
        root_workflows = root_nodes = subgraph_count = subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                name
                for name in archive.namelist()
                if "/templates/" in name and name.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                raw = archive.read(member).decode("utf-8")
                for target in targets:
                    if target in raw:
                        raw_members[target].add(member)
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue

                nodes = payload.get("nodes")
                if isinstance(nodes, list):
                    root_workflows += 1
                    root_nodes += len(nodes)
                    by_id = {
                        node.get("id"): node
                        for node in nodes
                        if isinstance(node, dict)
                    }
                    links = payload.get("links", [])
                    link_by_id = {
                        link[0]: link
                        for link in links
                        if isinstance(link, list) and len(link) >= 6
                    }
                    for node in nodes:
                        if not isinstance(node, dict):
                            continue
                        node_type = node.get("type")
                        if node_type in targets:
                            root_hits[node_type].append((member, node))
                        if node_type == "LoadVideo":
                            for output in node.get("outputs", []) or []:
                                for link_id in output.get("links") or []:
                                    link = link_by_id.get(link_id)
                                    if link is not None:
                                        target_node = by_id.get(link[3], {})
                                        downstream[target_node.get("type")] += 1

                definitions = payload.get("definitions")
                subgraphs = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                for subgraph in subgraphs:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraph_count += 1
                    nodes = subgraph.get("nodes", []) or []
                    subgraph_nodes += len(nodes)
                    for node in nodes:
                        if isinstance(node, dict) and node.get("type") in targets:
                            subgraph_hits[node["type"]].append((member, node))

        self.assertEqual(
            (496, 4083, 272, 4037, 8120),
            (
                root_workflows,
                root_nodes,
                subgraph_count,
                subgraph_nodes,
                root_nodes + subgraph_nodes,
            ),
        )
        for absent in ("ShuffleVideoDataset", "VideoRandomTemporalCrop"):
            self.assertEqual(set(), raw_members[absent])
            self.assertEqual([], root_hits[absent])
            self.assertEqual([], subgraph_hits[absent])

        self.assertEqual(66, len(raw_members["LoadVideo"]))
        self.assertEqual(55, len(root_hits["LoadVideo"]))
        self.assertEqual(
            53, len({member for member, _node in root_hits["LoadVideo"]})
        )
        self.assertEqual([], subgraph_hits["LoadVideo"])
        type_members = {member for member, _node in root_hits["LoadVideo"]}
        self.assertEqual(13, len(raw_members["LoadVideo"] - type_members))
        self.assertTrue(
            all(
                "index" in Path(member).name
                for member in raw_members["LoadVideo"] - type_members
            )
        )
        self.assertEqual(16, downstream["GetVideoComponents"])
        self.assertEqual(6, downstream["Video Slice"])

        self.assertEqual(8, len(raw_members["Video Slice"]))
        self.assertEqual(6, len(root_hits["Video Slice"]))
        self.assertEqual(2, len(subgraph_hits["Video Slice"]))
        slice_nodes = [node for _member, node in root_hits["Video Slice"]]
        slice_nodes.extend(node for _member, node in subgraph_hits["Video Slice"])
        settings = Counter(tuple(node["widgets_values"]) for node in slice_nodes)
        self.assertEqual(
            Counter({(0, 5, False): 5, (0, 0, False): 2, (0, 15, False): 1}),
            settings,
        )
        for _member, node in subgraph_hits["Video Slice"]:
            linked = {
                item["name"]: item.get("link")
                for item in node["inputs"]
                if item["name"] in {"start_time", "duration"}
            }
            self.assertIsNotNone(linked["start_time"])
            self.assertIsNotNone(linked["duration"])

    def test_exact_source_synthetic_probe_without_fragment_execution(self) -> None:
        self.assertTrue(SYNTHETIC_PROBE.is_file())
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next(candidate for candidate in candidates if candidate.exists())
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        shuffle = payload["shuffle"]
        self.assertEqual([0, 3, 2, 1, 4], shuffle["orderSeed7"])
        self.assertEqual([], shuffle["empty"])
        self.assertTrue(shuffle["globalRngReset"])
        self.assertTrue(shuffle["referencesPreserved"])
        self.assertTrue(shuffle["seedModuloCollision"])
        self.assertTrue(shuffle["singletonPreserved"])

        random_crop = payload["randomCrop"]
        self.assertEqual([0.25, 0.75], random_crop["seed11Window"])
        self.assertEqual([1.25, 0.75], random_crop["endpointStartIncluded"])
        self.assertEqual([0.0, 2.0], random_crop["clampedToFullWindow"])
        self.assertTrue(random_crop["globalRngUntouched"])
        self.assertTrue(random_crop["seedModuloCollision"])

        load = payload["load"]
        self.assertEqual(["fingerprint.mp4", "signal.avi"], load["options"])
        self.assertTrue(load["directoryAcceptedByValidation"])
        self.assertTrue(load["fingerprintIsMtimeOnly"])
        self.assertTrue(load["sourceIsExactInputPath"])
        self.assertTrue(load["traversalExecuteRejected"])
        self.assertTrue(load["traversalValidateRejected"])
        self.assertTrue(load["uploadEnabled"])

        video_slice = payload["slice"]
        self.assertEqual(
            {"actualDuration": 2.0, "requestedWindow": [0.0, 5.0]},
            video_slice["officialFiveSecondPattern"],
        )
        self.assertTrue(video_slice["strictLongRequestRejected"])
        self.assertEqual(
            {"duration": 1.5, "window": [0.5, 0.0]},
            video_slice["durationZeroUnlimited"],
        )
        self.assertEqual(
            {"duration": 0.5, "window": [1.5, 0.0]},
            video_slice["negativeStartFromEnd"],
        )
        self.assertEqual(
            {"duration": 0.5, "window": [1.5, 1.0]},
            video_slice["nonStrictClipped"],
        )
        self.assertEqual(
            {
                "childDuration": 1.5,
                "childWindow": [0.5, 0.0],
                "parentDuration": 0.5,
                "parentWindow": [0.5, 0.5],
            },
            video_slice["chainedUnlimitedExtendsParent"],
        )

        for _article_id, spec in ARTICLE_SPECS.items():
            schema = payload["schemas"][spec["classType"]]
            self.assertEqual(spec["isInputList"], schema["inputIsList"])
            self.assertEqual(spec["outputLists"], schema["outputIsList"])
            self.assertEqual(spec["experimental"], schema["experimental"])
            self.assertFalse(schema["deprecated"])
            self.assertFalse(schema["devOnly"])
            self.assertFalse(schema["apiNode"])
            self.assertFalse(schema["outputNode"])


if __name__ == "__main__":
    unittest.main()
