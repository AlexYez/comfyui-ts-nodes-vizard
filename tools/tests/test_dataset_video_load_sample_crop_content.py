from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Any

from tools import catalog


ARTICLE_SPECS = {
    "core.load-video-data-set-from-folder": {
        "directory": "load-video-data-set-from-folder",
        "classType": "LoadVideoDataSetFromFolder",
        "fingerprint": "sha256:29d1442c4ecb134b0d192facbd1e7a13199d28b251ab8e8b23682d73686f39ce",
        "recipe": "recipe.load-video-data-set-folder",
        "outputs": ["VIDEO"],
        "outputNames": ["videos"],
        "outputLists": [True],
    },
    "core.load-video-text-data-set-from-folder": {
        "directory": "load-video-text-data-set-from-folder",
        "classType": "LoadVideoTextDataSetFromFolder",
        "fingerprint": "sha256:3d4b0d0219847f0750eb1c30040557ba37f561a0708f172f299a189135e82449",
        "recipe": "recipe.load-video-text-data-set-folder",
        "outputs": ["VIDEO", "STRING"],
        "outputNames": ["videos", "texts"],
        "outputLists": [True, True],
    },
    "core.video-frame-sample": {
        "directory": "video-frame-sample",
        "classType": "VideoFrameSample",
        "fingerprint": "sha256:c0e42cdd69b0d2929587ef5c6307457121dd374464c42635798fbccbbbff20ba",
        "recipe": "recipe.video-frame-sample-uniform-4",
        "outputs": ["VIDEO"],
        "outputNames": ["video"],
        "outputLists": [False],
    },
    "core.video-temporal-crop": {
        "directory": "video-temporal-crop",
        "classType": "VideoTemporalCrop",
        "fingerprint": "sha256:9a2f45fda52a569b84dcaa7beebc7313e939369e69b6f019b226f33193b24f2c",
        "recipe": "recipe.video-temporal-crop-frames-2-4",
        "outputs": ["VIDEO"],
        "outputNames": ["video"],
        "outputLists": [False],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-video-data-set-folder": "load-video-data-set-folder",
    "recipe.load-video-text-data-set-folder": "load-video-text-data-set-folder",
    "recipe.video-frame-sample-uniform-4": "video-frame-sample-uniform-4",
    "recipe.video-temporal-crop-frames-2-4": "video-temporal-crop-frames-2-4",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.load-video-data-set-folder": [
        ("LoadVideoDataSetFromFolder", {"folder": "3d"})
    ],
    "recipe.load-video-text-data-set-folder": [
        ("LoadVideoTextDataSetFromFolder", {"folder": "3d"})
    ],
    "recipe.video-frame-sample-uniform-4": [
        (
            "VideoFrameSample",
            {"num_frames": 4, "strategy": "uniform", "seed": 0},
        )
    ],
    "recipe.video-temporal-crop-frames-2-4": [
        ("VideoTemporalCrop", {"start_frame": 2, "length": 4})
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
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
EMBEDDED_DOC_HASHES = {
    "LoadVideoDataSetFromFolder": {
        "en": "812eb64fb108997168b2c6cafedddfb31ca0a380866f92214bcae99fd9d8273d",
        "ru": "31951a011409399cfe4c0d2bb15c883d28d91d2abe4222f15704f8c7caad85bc",
    },
    "LoadVideoTextDataSetFromFolder": {
        "en": "10572ed6274b73a43e0ad198ebbaa46a65d3125b082003d8b5268fb8ceaa11e3",
        "ru": "15add77a90901f60dbd54cb66021e6585e326fac86c6eebb72f861ae6af07ce9",
    },
    "VideoFrameSample": {
        "en": "fd74e5beaa59ad2448f6a3bb5e2784b7281f09d2cfd69e2ef1b17c819351bf86",
        "ru": "9d528e7099dfc4fce46594eb6093e367a7585d6aeaa0d348bdf02116b1bd0f3c",
    },
    "VideoTemporalCrop": {
        "en": "b87944c61be9a93962dbebfc3c0d34610aea3fcfc335934ecfba91b8c0cfd917",
        "ru": "25d6a31ec1ecc8e590ec446d50aa540efa05d4715b9de22c6105104d7f314d0d",
    },
}
SYNTHETIC_PROBE = Path(__file__).with_name(
    "dataset_video_load_sample_crop_synthetic_probe.py"
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


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
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
    return "COMBO" if isinstance(value, list) else value


class DatasetVideoLoadSampleCropContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_editorial_contracts(self) -> None:
        article_ids = all_article_ids()
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
        errors: list[str] = []
        banned = re.compile(
            r"важно отметить|стоит отметить|следует отметить|"
            r"в современном мире|революционн|является незаменим|"
            r"является мощн|\bдавайте\b|глубже погруз|"
            r"открывает новые|может показаться|позволяет вам|"
            r"подводя итог|в заключение|не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertTrue(article["experimental"])
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
                10,
                len(re.findall(r"^## .+$", body, flags=re.MULTILINE)),
                article_id,
            )
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), article_id)

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual(
                [], catalog.json_schema_errors(research, schemas["research"])
            )
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
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
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, schemas["fragment"])
            )
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual([], fragment["connections"])
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_settings(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = runtime_nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_dataset", runtime["python_module"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime["is_input_list"])
            self.assertEqual(spec["outputs"], runtime["output"])
            self.assertEqual(spec["outputNames"], runtime["output_name"])
            self.assertEqual(spec["outputLists"], runtime["output_is_list"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        for class_type in (
            "LoadVideoDataSetFromFolder",
            "LoadVideoTextDataSetFromFolder",
        ):
            runtime = runtime_nodes[class_type]
            self.assertEqual(["folder"], runtime["input_order"]["required"])
            folder = runtime["input"]["required"]["folder"]
            self.assertEqual("COMBO", descriptor_type(folder))
            self.assertEqual(["3d"], folder[1]["options"])

        sample = runtime_nodes["VideoFrameSample"]
        self.assertEqual(
            ["video", "num_frames", "strategy", "seed"],
            sample["input_order"]["required"],
        )
        self.assertEqual(
            ["uniform", "head", "tail", "random"],
            sample["input"]["required"]["strategy"][1]["options"],
        )
        self.assertEqual(
            {"default": 16, "min": 1, "max": 9999},
            {
                key: sample["input"]["required"]["num_frames"][1][key]
                for key in ("default", "min", "max")
            },
        )
        self.assertEqual(
            {"default": 0, "min": 0, "max": 2**64 - 1},
            {
                key: sample["input"]["required"]["seed"][1][key]
                for key in ("default", "min", "max")
            },
        )

        crop = runtime_nodes["VideoTemporalCrop"]
        self.assertEqual(
            ["video", "start_frame", "length"],
            crop["input_order"]["required"],
        )
        self.assertEqual(
            {"default": 0, "min": 0, "max": 99999},
            {
                key: crop["input"]["required"]["start_frame"][1][key]
                for key in ("default", "min", "max")
            },
        )
        self.assertEqual(
            {"default": 16, "min": 1, "max": 99999},
            {
                key: crop["input"]["required"]["length"][1][key]
                for key in ("default", "min", "max")
            },
        )

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            fragment = catalog.load_json(
                path.parent / catalog.load_json(path)["fragment"]["path"]
            )
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {
                ref: set(node["settings"]) for ref, node in node_by_ref.items()
            }
            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(
                    runtime_nodes[target["classType"]]
                )[external["input"]]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for ref, node in node_by_ref.items():
                runtime = runtime_nodes[node["classType"]]
                required = set(runtime.get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))
                descriptors = runtime_input_specs(runtime)
                for name, value in node["settings"].items():
                    descriptor = descriptors[name]
                    kind = descriptor_type(descriptor)
                    if kind == "COMBO":
                        self.assertIn(value, descriptor[1]["options"])
                    elif kind == "INT":
                        self.assertIsInstance(value, int)
                        constraints = descriptor[1]
                        self.assertGreaterEqual(value, constraints["min"])
                        self.assertLessEqual(value, constraints["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations_and_replacement_state(self) -> None:
        dataset = (SOURCE / "comfy_extras" / "nodes_dataset.py").read_text(
            encoding="utf-8"
        )
        video_types = (
            SOURCE / "comfy_api" / "latest" / "_input_impl" / "video_types.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'VALID_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".webm", ".mkv", ".flv"]',
            dataset,
        )
        self.assertIn("class LoadVideoDataSetFromFolderNode", dataset)
        self.assertIn("video_files = sorted([", dataset)
        self.assertIn("if any(f.lower().endswith(ext) for ext in VALID_VIDEO_EXTENSIONS)", dataset)
        self.assertIn("InputImpl.VideoFromFile(os.path.join(sub_input_dir, f))", dataset)
        self.assertIn("class LoadVideoTextDataSetFromFolderNode", dataset)
        self.assertIn('if item.split("_")[0].isdigit():', dataset)
        self.assertIn('repeat = int(item.split("_")[0])', dataset)
        self.assertIn("] * repeat)", dataset)
        self.assertIn('caption_path = os.path.splitext(vf)[0] + ".txt"', dataset)
        self.assertIn("captions.append(f.read().strip())", dataset)
        self.assertIn("indices_sorted = sorted(set(indices))", dataset)
        self.assertIn("source = video.get_stream_source()", dataset)
        self.assertIn("for frame_idx, frame in enumerate(container.decode(stream)):", dataset)
        self.assertIn(
            "Types.VideoComponents(images=stacked, frame_rate=video.get_frame_rate())",
            dataset,
        )
        self.assertIn("num_frames = min(num_frames, total_frames)", dataset)
        self.assertIn(
            "indices = [round(i * (total_frames - 1) / (num_frames - 1)) for i in range(num_frames)]",
            dataset,
        )
        self.assertIn("rng = np.random.RandomState(seed % (2**32 - 1))", dataset)
        self.assertIn(
            "indices = sorted(rng.choice(total_frames, size=num_frames, replace=False).tolist())",
            dataset,
        )
        self.assertIn(
            "start_frame = min(start_frame, max(total_frames - 1, 0))", dataset
        )
        self.assertIn("length = min(length, total_frames - start_frame)", dataset)
        self.assertIn(
            "video.as_trimmed(start_frame / fps, length / fps, strict_duration=False)",
            dataset,
        )
        self.assertIn("return self.__file", video_types)
        self.assertIn("start_time=start_time + self.__start_time", video_types)

        replacements_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements_text)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_hashes_and_known_gaps(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            for class_type, locales in EMBEDDED_DOC_HASHES.items():
                for locale, expected_hash in locales.items():
                    payload = archive.read(
                        f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    )
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in EMBEDDED_DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("experimental", docs[(class_type, "en")].lower())
        self.assertNotIn(
            "nested", docs[("LoadVideoDataSetFromFolder", "en")].lower()
        )
        self.assertNotIn(
            "No video files", docs[("LoadVideoDataSetFromFolder", "en")]
        )
        self.assertIn(
            "repeat\u2011count prefixes",
            docs[("LoadVideoTextDataSetFromFolder", "en")],
        )
        self.assertNotIn(
            "one level", docs[("LoadVideoTextDataSetFromFolder", "en")].lower()
        )
        self.assertNotIn("audio", docs[("VideoFrameSample", "en")].lower())
        self.assertNotIn("2**32", docs[("VideoFrameSample", "en")])
        self.assertNotIn("trim", docs[("VideoFrameSample", "en")].lower())
        self.assertNotIn("clamp", docs[("VideoTemporalCrop", "en")].lower())
        self.assertNotIn("frame rate", docs[("VideoTemporalCrop", "en")].lower())
        self.assertIn("`папка`", docs[("LoadVideoDataSetFromFolder", "ru")])
        self.assertIn("`количество_кадров`", docs[("VideoFrameSample", "ru")])
        self.assertIn("`начальный_кадр`", docs[("VideoTemporalCrop", "ru")])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_has_no_target_nodes(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        occurrences: list[tuple[str, str, str]] = []
        raw_occurrences: list[tuple[str, str]] = []
        root_workflows = 0
        root_nodes = 0
        subgraph_count = 0
        subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                member
                for member in archive.namelist()
                if "/templates/" in member and member.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                raw = archive.read(member).decode("utf-8")
                for target in target_types:
                    if target in raw:
                        raw_occurrences.append((member, target))
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_workflows += 1
                    root_nodes += len(payload["nodes"])
                    for node in payload["nodes"]:
                        if isinstance(node, dict) and node.get("type") in target_types:
                            occurrences.append(("root", member, node["type"]))
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
                        if isinstance(node, dict) and node.get("type") in target_types:
                            occurrences.append(("subgraph", member, node["type"]))

        self.assertEqual(496, root_workflows)
        self.assertEqual(4083, root_nodes)
        self.assertEqual(272, subgraph_count)
        self.assertEqual(4037, subgraph_nodes)
        self.assertEqual(8120, root_nodes + subgraph_nodes)
        self.assertEqual([], raw_occurrences)
        self.assertEqual([], occurrences)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_synthetic_execution_without_external_data(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for dataset video probe")
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"dataset video probe unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        loader = payload["loadVideo"]
        self.assertEqual(["a.mkv", "z.MP4"], loader["sortedSources"])
        self.assertTrue(loader["caseInsensitiveExtensions"])
        self.assertTrue(loader["nestedIgnored"])
        self.assertTrue(loader["emptyRejected"])
        self.assertTrue(loader["traversalRejected"])

        paired = payload["loadVideoText"]
        self.assertEqual(
            [
                "2_class/a.mkv",
                "2_class/c.WEBM",
                "2_class/a.mkv",
                "2_class/c.WEBM",
                "b.mov",
                "plain_class/d.avi",
            ],
            paired["sources"],
        )
        self.assertEqual(
            ["alpha", "", "alpha", "", "bravo", "delta"],
            paired["captions"],
        )
        self.assertEqual(1, paired["nestedDepth"])
        self.assertTrue(paired["repeatPrefixApplied"])
        self.assertTrue(paired["zeroRepeatDropsFolder"])
        self.assertTrue(paired["missingCaptionEmpty"])
        self.assertTrue(paired["whitespaceStripped"])

        sample = payload["sample"]
        self.assertEqual([0, 2, 5, 7], sample["uniformIds"])
        self.assertEqual(4, sample["middleId"])
        self.assertEqual(list(range(8)), sample["allRequestClamped"])
        self.assertEqual([2, 4, 5, 6], sample["randomIdsSeed11"])
        self.assertTrue(sample["randomModuloCollision"])
        self.assertTrue(sample["globalRngUntouched"])
        self.assertTrue(sample["selectedAudioAbsent"])
        self.assertEqual([0.0, 0.75], sample["headTrim"])
        self.assertEqual([1.25, 0.75], sample["tailTrim"])
        self.assertTrue(sample["trimmedInputOffsetIgnored"])
        self.assertTrue(sample["unknownStrategyRejected"])

        crop = payload["temporalCrop"]
        self.assertTrue(crop["fullyLazy"])
        self.assertEqual([0.5, 0.75], crop["requested"])
        self.assertEqual([1.5, 0.5], crop["tailLengthTruncated"])
        self.assertEqual([1.75, 0.25], crop["pastEndClampedToLast"])
        self.assertEqual([0.5, 0.5], crop["chainedLazyHeadAddsOffset"])


if __name__ == "__main__":
    unittest.main()
