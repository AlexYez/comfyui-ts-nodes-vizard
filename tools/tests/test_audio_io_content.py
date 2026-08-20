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
    "core.load-audio": {
        "directory": "load-audio",
        "classType": "LoadAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:491299352b2854e4515d49ad290212903b3bb853b303d6b4c129f3d510b992f4",
        "recipe": "recipe.load-audio-for-preview",
    },
    "core.preview-audio": {
        "directory": "preview-audio",
        "classType": "PreviewAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:01ab10078d102983846813625c4cda17156b8e411c91de55c0aa78acf89c680d",
        "recipe": "recipe.load-audio-for-preview",
    },
    "core.save-audio-advanced": {
        "directory": "save-audio-advanced",
        "classType": "SaveAudioAdvanced",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:4161e0e67516eb2cda31011008c8602f0ef4cad7d9b3b6e8e5edcbd9b64d4940",
        "recipe": "recipe.save-audio-mp3-v0",
    },
    "core.audio-merge": {
        "directory": "audio-merge",
        "classType": "AudioMerge",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:1bb5719abeb962b4a9a5bd29fd023b4ef309ca65a669efbfb8f26ff3a20f4d68",
        "recipe": "recipe.merge-audio-add",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-audio-for-preview": "load-audio-for-preview",
    "recipe.save-audio-mp3-v0": "save-audio-mp3-v0",
    "recipe.merge-audio-add": "merge-audio-add",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.load-audio-for-preview": [
        ("LoadAudio", {"audio": "voice_demo.mp3"}),
        ("PreviewAudio", {}),
    ],
    "recipe.save-audio-mp3-v0": [
        (
            "SaveAudioAdvanced",
            {
                "filename_prefix": "audio/ComfyUI",
                "format": {"format": "mp3", "quality": "V0"},
            },
        )
    ],
    "recipe.merge-audio-add": [
        ("AudioMerge", {"merge_method": "add"})
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
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
SYNTHETIC_PROBE = Path(__file__).with_name("audio_io_synthetic_probe.py")


def article_path(spec: dict[str, str]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


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


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    workflow_id = payload.get("id")
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": workflow_id,
                "scope": "root",
                "node": node,
                "graph": payload,
            }
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph_index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": workflow_id,
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "node": node,
                    "graph": subgraph,
                }


def load_official_workflows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workflows: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        members = sorted(
            member
            for member in archive.namelist()
            if "/templates/" in member and member.endswith(".json")
        )
        for member in members:
            payload = json.loads(archive.read(member).decode("utf-8"))
            workflows[member] = payload
            if isinstance(payload, dict):
                records.extend(workflow_node_records(payload, member))
    return workflows, records


def connected_types(
    graph: dict[str, Any], node_id: Any
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    nodes = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    }
    links: dict[Any, list[Any]] = {}
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            links[link[0]] = link
        elif isinstance(link, dict) and "id" in link:
            links[link["id"]] = [
                link["id"],
                link["origin_id"],
                link["origin_slot"],
                link["target_id"],
                link["target_slot"],
                link.get("type"),
            ]
    node = nodes[node_id]
    incoming: list[tuple[str, str]] = []
    outgoing: list[tuple[str, str]] = []
    for input_value in node.get("inputs", []) or []:
        link = links.get(input_value.get("link"))
        if link is not None:
            incoming.append((str(nodes[link[1]].get("type")), input_value["name"]))
    for output_value in node.get("outputs", []) or []:
        for link_id in output_value.get("links") or []:
            link = links[link_id]
            target = nodes[link[3]]
            target_name = next(
                item["name"]
                for item in target.get("inputs", []) or []
                if item.get("link") == link_id
            )
            outgoing.append((str(target.get("type")), target_name))
    return incoming, outgoing


class AudioIOContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_cross_links_validate(self) -> None:
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

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
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
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|в современном мире|"
                r"революционн|является незаменим|является мощн|\bдавайте\b|"
                r"глубже погруз|открывает новые|может показаться|позволяет вам|"
                r"подводя итог|в заключение",
            )

            record_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, schemas["research"]))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            recipe_body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            prose_without_code = re.sub(
                r"`[^`]+`|https?://\S+", "", recipe_body
            ).casefold()
            for untranslated in (
                " workflow",
                " fragment",
                " runtime-",
                " batch",
                " waveform",
                " resample",
                " subgraph",
                " encoder helper",
                " bundle",
                " full census",
            ):
                self.assertNotIn(untranslated, prose_without_code, recipe_id)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_identity_fingerprints_ports_and_dynamic_settings(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            runtime = runtime_nodes[spec["classType"]]
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertFalse(runtime.get("deprecated", False))
            self.assertFalse(runtime.get("experimental", False))
            self.assertFalse(runtime.get("dev_only", False))
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied: dict[str, set[str]] = {
                ref: set(node["settings"]) for ref, node in node_by_ref.items()
            }

            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(runtime_nodes[target["classType"]])[
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for connection in fragment["connections"]:
                origin = node_by_ref[connection["from"]]
                target = node_by_ref[connection["to"]]
                origin_runtime = runtime_nodes[origin["classType"]]
                target_runtime = runtime_nodes[target["classType"]]
                output_index = origin_runtime["output_name"].index(connection["output"])
                self.assertEqual(
                    origin_runtime["output"][output_index],
                    descriptor_type(
                        runtime_input_specs(target_runtime)[connection["input"]]
                    ),
                )
                supplied[connection["to"]].add(connection["input"])

            for ref, node in node_by_ref.items():
                runtime = runtime_nodes[node["classType"]]
                specs = runtime_input_specs(runtime)
                required = set(runtime.get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = specs[name]
                    input_type = descriptor_type(descriptor)
                    constraints = (
                        descriptor[1]
                        if len(descriptor) > 1 and isinstance(descriptor[1], dict)
                        else {}
                    )
                    if input_type == "STRING":
                        self.assertIsInstance(value, str)
                    elif input_type == "COMBO":
                        self.assertIsInstance(value, str)
                        options = constraints.get("options", [])
                        if options:
                            self.assertIn(value, options)
                    elif input_type == "COMFY_DYNAMICCOMBO_V3":
                        self.assertIsInstance(value, dict)
                        self.assertIsInstance(value.get("format"), str)
                        option = next(
                            item
                            for item in constraints["options"]
                            if item["key"] == value["format"]
                        )
                        nested_required = option["inputs"].get("required", {})
                        self.assertTrue(set(nested_required).issubset(value))
                        for nested_name, nested_descriptor in nested_required.items():
                            nested_options = nested_descriptor[1].get("options", [])
                            self.assertIn(value[nested_name], nested_options)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations(self) -> None:
        audio = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(
            encoding="utf-8"
        )
        ui = (SOURCE / "comfy_api" / "latest" / "_ui.py").read_text(
            encoding="utf-8"
        )
        folder_paths = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")

        self.assertIn("stream = af.streams.audio[0]", audio)
        self.assertIn("waveform.unsqueeze(0)", audio)
        self.assertIn("m.update(f.read())", audio)
        self.assertIn('IO.DynamicCombo.Option("flac", [])', audio)
        self.assertIn('options=["V0", "128k", "320k"]', audio)
        self.assertIn('options=["64k", "96k", "128k", "192k", "320k"]', audio)
        self.assertIn('outputs=[IO.Audio.Output("audio")]', audio)
        self.assertIn("waveform_2 = waveform_2[..., :length_1]", audio)
        self.assertIn("waveform = (waveform_1 + waveform_2) / 2", audio)
        self.assertIn("waveform = waveform / max_val", audio)

        self.assertIn("for batch_number, waveform in enumerate(audio[\"waveform\"].cpu())", ui)
        self.assertIn('layout = "mono" if waveform.shape[0] == 1 else "stereo"', ui)
        self.assertIn("_OPUS_RATES = [8000, 12000, 16000, 24000, 48000]", ui)
        self.assertIn('out_stream.codec_context.qscale = 1', ui)
        self.assertIn('folder_type=FolderType.temp', ui)
        self.assertIn('format="flac"', ui)

        self.assertIn("if not is_within_directory(base_dir, filepath):", folder_paths)
        self.assertIn('filename.replace("%batch_num%", str(batch_number))', ui)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_paths_and_known_omissions(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        names = ["LoadAudio", "PreviewAudio", "SaveAudioAdvanced", "AudioMerge"]
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            docs = {
                name: archive.read(
                    f"comfyui_embedded_docs/docs/{name}/en.md"
                ).decode("utf-8")
                for name in names
            }
        self.assertTrue(
            all("This documentation was AI-generated" in value for value in docs.values())
        )
        self.assertNotIn("first audio stream", docs["LoadAudio"].lower())
        self.assertNotIn("batch", docs["PreviewAudio"].lower())
        self.assertNotIn("| `audio` |", docs["PreviewAudio"].split("## Outputs", 1)[1])
        self.assertNotIn("batch", docs["SaveAudioAdvanced"].lower())
        self.assertNotIn(
            "| `audio` |", docs["SaveAudioAdvanced"].split("## Outputs", 1)[1]
        )
        self.assertNotIn("audio1 determines", docs["AudioMerge"].lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_counts_widgets_and_topologies(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        workflows, records = load_official_workflows()
        self.assertEqual(512, len(workflows))
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        targets = [record for record in records if record["node"].get("type") in target_types]
        self.assertEqual(
            {"LoadAudio": 23, "SaveAudioAdvanced": 6, "AudioMerge": 1},
            dict(Counter(record["node"]["type"] for record in targets)),
        )
        self.assertFalse(any(record["node"].get("type") == "PreviewAudio" for record in records))

        load_records = [record for record in targets if record["node"]["type"] == "LoadAudio"]
        self.assertTrue(all(record["scope"] == "root" for record in load_records))
        self.assertEqual(Counter({0: 18, 4: 4, 2: 1}), Counter(record["node"].get("mode") for record in load_records))
        self.assertEqual(20, len({record["member"] for record in load_records}))

        save_records = [record for record in targets if record["node"]["type"] == "SaveAudioAdvanced"]
        self.assertTrue(all(record["scope"] == "root" for record in save_records))
        self.assertTrue(all(record["node"].get("mode") == 0 for record in save_records))
        self.assertTrue(all(record["node"].get("widgets_values", [])[-2:] == ["mp3", "V0"] for record in save_records))

        merge_records = [record for record in targets if record["node"]["type"] == "AudioMerge"]
        self.assertEqual(1, len(merge_records))
        self.assertEqual("subgraph", merge_records[0]["scope"])
        self.assertEqual(["add"], merge_records[0]["node"]["widgets_values"])

        humo_member = next(name for name in workflows if name.endswith("/video_humo.json"))
        humo = workflows[humo_member]
        self.assertEqual("428ebf59-f870-43e5-b3a9-ad0c0b7b33f4", humo["id"])
        humo_nodes = {node["id"]: node for node in humo["nodes"]}
        self.assertEqual("LoadAudio", humo_nodes[58]["type"])
        self.assertEqual(
            ["video_humo_input_audio.wav", None, None],
            humo_nodes[58]["widgets_values"],
        )
        _, humo_outgoing = connected_types(humo, 58)
        self.assertEqual(
            {("CreateVideo", "audio"), ("AudioEncoderEncode", "audio")},
            set(humo_outgoing),
        )

        sonilo_member = next(
            name for name in workflows if name.endswith("/api_sonilo_v2m.json")
        )
        sonilo = workflows[sonilo_member]
        self.assertEqual("9132f036-0cbe-44bb-9948-c8d1348ec66b", sonilo["id"])
        sonilo_nodes = {node["id"]: node for node in sonilo["nodes"]}
        self.assertEqual("SaveAudioAdvanced", sonilo_nodes[728]["type"])
        self.assertEqual(["audio/Sonilo", "mp3", "V0"], sonilo_nodes[728]["widgets_values"])
        save_incoming, save_outgoing = connected_types(sonilo, 728)
        self.assertEqual([("SoniloVideoToMusic", "audio")], save_incoming)
        self.assertEqual(1, len(save_outgoing))
        self.assertEqual("audio", save_outgoing[0][1])

        subgraphs = sonilo["definitions"]["subgraphs"]
        merger = next(
            graph
            for graph in subgraphs
            if graph.get("id") == "bb615e2f-2ea7-40b8-9419-f0206c2d60dd"
        )
        merger_nodes = {node["id"]: node for node in merger["nodes"]}
        self.assertEqual("AudioMerge", merger_nodes[721]["type"])
        self.assertEqual(["add"], merger_nodes[721]["widgets_values"])
        merge_incoming, merge_outgoing = connected_types(merger, 721)
        self.assertEqual(
            {("AudioAdjustVolume", "audio1"), ("AudioAdjustVolume", "audio2")},
            set(merge_incoming),
        )
        self.assertEqual([("CreateVideo", "audio")], merge_outgoing)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_synthetic_and_file_execution_without_models(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for the audio I/O probe")
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
            self.skipTest(f"audio I/O probe dependencies unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([1, 2, 800], payload["loadAudio"]["shape"])
        self.assertEqual(8000, payload["loadAudio"]["sampleRate"])
        self.assertEqual(1, payload["previewAudio"]["files"])
        self.assertEqual("temp", payload["previewAudio"]["folderType"])
        self.assertTrue(payload["previewAudio"]["passthroughIdentity"])
        self.assertEqual(2, payload["saveAudioAdvanced"]["batchFiles"])
        self.assertEqual([2, 120], payload["saveAudioAdvanced"]["multichannelDecodedShapes"]["3"])
        self.assertEqual([2, 160], payload["saveAudioAdvanced"]["multichannelDecodedShapes"]["4"])
        self.assertTrue(payload["saveAudioAdvanced"]["opus320kMonoRejected"])
        self.assertEqual(
            {
                "flac:-",
                "mp3:V0",
                "mp3:128k",
                "mp3:320k",
                "opus:64k",
                "opus:96k",
                "opus:128k",
                "opus:192k",
                "opus:320k",
            },
            set(payload["saveAudioAdvanced"]["formats"]),
        )
        self.assertTrue(
            all(
                shape == [2, 2, 4]
                for shape in payload["audioMerge"]["shapes"].values()
            )
        )
        self.assertEqual([1, 1, 8], payload["audioMerge"]["resampledShape"])
        self.assertEqual(8000, payload["audioMerge"]["resampledRate"])
        self.assertTrue(payload["audioMerge"]["incompatibleShapeRejected"])


if __name__ == "__main__":
    unittest.main()
