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


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.trim-audio-duration": {
        "directory": "trim-audio-duration",
        "classType": "TrimAudioDuration",
        "fingerprint": "sha256:9b9ef762c2dc65ac82e23107e7e1890225328c7300afb0fced9da45768de3542",
        "experimental": False,
        "recipes": ["recipe.trim-audio-window"],
        "docs": {"en": "f7aabba56ca5c32a6da443827c952c1fcef38e335c48ad75ed2da6cde1e3f8aa", "ru": "3645d50962b56bffcb07eb494ab76e5d4d3633fb5371bbdcffc50ff28a384904"},
    },
    "core.split-audio-channels": {
        "directory": "split-audio-channels",
        "classType": "SplitAudioChannels",
        "fingerprint": "sha256:7d609cd94824adca79e82db3b1c2f48273da9f191be3c0a0f5fbb2557fb49e86",
        "experimental": False,
        "recipes": ["recipe.split-balance-rejoin-stereo"],
        "docs": {"en": "8153756284afc6158a12b3c2d3db195f19dbfa23590d5f392d1ae43ac9a455e9", "ru": "0ad110bd8474c3d3e9efbcacd348ef4ae3debf024a0c312e55e598b5d6fc9e1d"},
    },
    "core.join-audio-channels": {
        "directory": "join-audio-channels",
        "classType": "JoinAudioChannels",
        "fingerprint": "sha256:79b2da9020db8e8fb302d6950438f095466af3b9a24d379d58d5e0c61c72dc06",
        "experimental": False,
        "recipes": ["recipe.split-balance-rejoin-stereo"],
        "docs": {"en": "b0c5bbabae36b35a006cf51ce5de781b731995998522aef7f44f89a6ce4feebe", "ru": "df1966e0063a0d7b946445559f15b2a00cb98670c2be8b7c463fa82598665aee"},
    },
    "core.audio-adjust-volume": {
        "directory": "audio-adjust-volume",
        "classType": "AudioAdjustVolume",
        "fingerprint": "sha256:d6a6988892d7fd934fc4d6b6aac084551a1033c15f86a10fcf3de764f00a8e7d",
        "experimental": False,
        "recipes": ["recipe.adjust-audio-before-merge", "recipe.split-balance-rejoin-stereo"],
        "docs": {"en": "a31fb1094d279e6041d653013e9b5e80947e6ed77264299f3a7378e7e5ba3334", "ru": "2dde9b1053a2037346757b8d3ffb8afd1475ac9e25282ef60641295111d06b63"},
    },
    "core.audio-equalizer-3-band": {
        "directory": "audio-equalizer-3-band",
        "classType": "AudioEqualizer3Band",
        "fingerprint": "sha256:594a025a0ac83cf2ca0c2fe1120261e3e4409353357272218bc8b6ebe7799edc",
        "experimental": True,
        "recipes": ["recipe.equalize-three-bands"],
        "docs": {"en": "f0945dd3ff4892c90d85591b5b6a28c3ec38b7a9f2322f967e5986e301e45891", "ru": "59ab659419d805ca9811e70d0fd1bcb2f26c6e99e3ee12e7805dc7cda99a8298"},
    },
}

RECIPE_DIRECTORIES = {
    "recipe.trim-audio-window": "trim-audio-window",
    "recipe.split-balance-rejoin-stereo": "split-balance-rejoin-stereo",
    "recipe.adjust-audio-before-merge": "adjust-audio-before-merge",
    "recipe.equalize-three-bands": "equalize-three-bands",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("audio_editing_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    return {
        catalog.load_json(path)["articleId"]
        for path in (catalog.CONTENT / "articles").rglob("manifest.json")
    }


def descriptor_type(descriptor: Any) -> Any:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    return "COMBO" if isinstance(descriptor[0], list) else descriptor[0]


def graph_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield "subgraph", subgraph


def link_fields(link: Any) -> tuple[Any, int, Any, int, Any] | None:
    if isinstance(link, list) and len(link) >= 6:
        return link[1], link[2], link[3], link[4], link[5]
    if isinstance(link, dict):
        return (
            link.get("origin_id"),
            link.get("origin_slot", 0),
            link.get("target_id"),
            link.get("target_slot", 0),
            link.get("type"),
        )
    return None


class AudioEditingContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_honesty_and_natural_russian(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        errors: list[str] = []
        seen_class_types: dict[str, str] = {}
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            manifest = catalog.load_json(path)
            class_type = manifest.get("runtimeIdentity", {}).get("classType")
            if class_type in {spec["classType"] for spec in ARTICLE_SPECS.values()}:
                self.assertNotIn(class_type, seen_class_types, class_type)
                seen_class_types[class_type] = str(path)

        cliché = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является мощн|давайте|глубже погруз|открывает новые|"
            r"может показаться|позволяет вам|подводя итог|в заключение|данная нода",
            re.IGNORECASE,
        )
        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(spec["recipes"], [item["id"] for item in article["assets"]])

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)), article_id)
            self.assertIsNone(cliché.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            for mojibake_marker in ("Рџ", "РЎ", "Р’", "СЃ", "С‚", "вЂ"):
                self.assertNotIn(mojibake_marker, body)

            research_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]), article_id)
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(any("human" in gap.lower() for gap in research["knownGaps"]))

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIsNone(cliché.search(recipe_body), recipe_id)
            self.assertNotIn("\ufffd", recipe_body)
            prose_without_code = re.sub(r"`[^`]+`|https?://\S+", "", recipe_body)
            for untranslated in (
                " subgraph",
                " workflow",
                " video-разбор",
                " formula gain",
                " template census",
                " tensor-вызов",
                " mono-сигнал",
                " stereo",
                " editorial fragment",
            ):
                self.assertNotIn(untranslated, prose_without_code.casefold(), recipe_id)
        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_ports_settings_and_fragments(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_audio", runtime["python_module"])
            self.assertEqual("audio", runtime["category"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["output_node"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        trim = nodes["TrimAudioDuration"]["input"]["required"]
        self.assertEqual((0.0, 0.01), (trim["start_index"][1]["default"], trim["start_index"][1]["step"]))
        self.assertEqual((60.0, 0.0), (trim["duration"][1]["default"], trim["duration"][1]["min"]))
        self.assertEqual(["left", "right"], nodes["SplitAudioChannels"]["output_name"])
        self.assertEqual(["AUDIO", "AUDIO"], nodes["SplitAudioChannels"]["output"])
        self.assertEqual(["audio"], nodes["JoinAudioChannels"]["output_name"])
        volume = nodes["AudioAdjustVolume"]["input"]["required"]["volume"]
        self.assertEqual(["INT", {"tooltip": "Volume adjustment in decibels (dB). 0 = no change, +6 = double, -6 = half, etc", "default": 1, "min": -100, "max": 100}], volume)
        eq = nodes["AudioEqualizer3Band"]["input"]["required"]
        self.assertEqual((-24.0, 24.0, 0.1), (eq["low_gain_dB"][1]["min"], eq["low_gain_dB"][1]["max"], eq["low_gain_dB"][1]["step"]))
        self.assertEqual((0.1, 10.0, 0.707), (eq["mid_q"][1]["min"], eq["mid_q"][1]["max"], eq["mid_q"][1]["default"]))
        self.assertEqual((1000, 15000, 5000), (eq["high_freq"][1]["min"], eq["high_freq"][1]["max"], eq["high_freq"][1]["default"]))

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            for external in fragment["externalInputs"]:
                runtime = nodes[by_ref[external["to"]]["classType"]]
                descriptor = runtime["input"]["required"][external["input"]]
                self.assertEqual(external["type"], descriptor_type(descriptor), (recipe_id, external))
            for connection in fragment["connections"]:
                source = nodes[by_ref[connection["from"]]["classType"]]
                target = nodes[by_ref[connection["to"]]["classType"]]
                output_type = source["output"][source["output_name"].index(connection["output"])]
                input_type = descriptor_type(target["input"]["required"][connection["input"]])
                self.assertEqual(output_type, input_type, (recipe_id, connection))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_and_replacement_contracts(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(encoding="utf-8")
        for snippet in (
            "audio_length + int(round(start_index * sample_rate))",
            "waveform[..., start_frame:end_frame]",
            "if waveform.shape[1] != 2:",
            "left_channel = waveform[..., 0:1, :]",
            "right_channel = waveform[..., 1:2, :]",
            "if waveform_left.shape[1] != 1 or waveform_right.shape[1] != 1:",
            "output_sample_rate = sample_rate_1",
            "output_sample_rate = sample_rate_2",
            "min_length = min(length_left, length_right)",
            "stereo_waveform = torch.cat([left_channel, right_channel], dim=1)",
            "gain = 10 ** (volume / 20)",
            "eq_waveform = waveform.clone()",
            "eq_waveform = torchaudio.functional.bass_biquad",
            "eq_waveform = torchaudio.functional.equalizer_biquad",
            "eq_waveform = torchaudio.functional.treble_biquad",
        ):
            self.assertIn(snippet, source)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_hashes(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            for spec in ARTICLE_SPECS.values():
                for locale, expected in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    self.assertEqual(expected, hashlib.sha256(archive.read(name)).hexdigest(), name)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: Counter() for target in targets}
        widgets: dict[str, list[Any]] = {target: [] for target in targets}
        outgoing = Counter()
        files: dict[str, set[str]] = {target: set() for target in targets}
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")):
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                if isinstance(definitions, dict):
                    subgraph_count += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope_kind, graph in graph_scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope_kind] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            widgets[node_type].append(node.get("widgets_values", []))
                            files[node_type].add(member)
                    for link in graph.get("links", []):
                        fields = link_fields(link)
                        if fields is None:
                            continue
                        origin_id, _, target_id, _, link_type = fields
                        source_type = nodes.get(origin_id, {}).get("type")
                        target_type = nodes.get(target_id, {}).get("type")
                        if source_type in targets:
                            outgoing[(source_type, target_type, link_type)] += 1

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((0, 4, 4), (counts["TrimAudioDuration"]["root"], counts["TrimAudioDuration"]["subgraph"], counts["TrimAudioDuration"]["mode:0"]))
        self.assertEqual(Counter({json.dumps([0, 60]): 3, json.dumps([0, 25]): 1}), Counter(json.dumps(item) for item in widgets["TrimAudioDuration"]))
        self.assertEqual(4, len(files["TrimAudioDuration"]))
        self.assertEqual((0, 2, 2), (counts["AudioAdjustVolume"]["root"], counts["AudioAdjustVolume"]["subgraph"], counts["AudioAdjustVolume"]["mode:0"]))
        self.assertEqual([[1], [1]], widgets["AudioAdjustVolume"])
        self.assertEqual(1, len(files["AudioAdjustVolume"]))
        for class_type in ("SplitAudioChannels", "JoinAudioChannels", "AudioEqualizer3Band"):
            self.assertEqual(0, sum(counts[class_type].values()), class_type)
        self.assertEqual(2, outgoing[("AudioAdjustVolume", "AudioMerge", "AUDIO")])
        self.assertEqual(2, outgoing[("TrimAudioDuration", "LTXVAudioVAEEncode", "AUDIO")])
        self.assertEqual(3, outgoing[("TrimAudioDuration", "CreateVideo", "AUDIO")])
        self.assertEqual(1, outgoing[("TrimAudioDuration", "WanDancerEncodeAudio", "AUDIO")])
        self.assertEqual(1, outgoing[("TrimAudioDuration", "WanDancerPadKeyframesList", "AUDIO")])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_class_audio_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(executable)
        result = subprocess.run(
            [str(executable), "-X", "utf8", str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(["low", "mid", "high"], report["equalizer"]["order"])
        self.assertTrue(report["equalizer"]["torchaudio"].startswith("2.11."))
        self.assertEqual([1, 2, 8], report["join"]["resampled"])
        self.assertTrue(report["trim"]["sharesStorage"])


if __name__ == "__main__":
    unittest.main()
