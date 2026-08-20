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
    "core.save-audio": {
        "directory": "save-audio",
        "classType": "SaveAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:78194763541a8d2f37ed547686c4c4680d6018224dbd6cdc5021be2db8a4b975",
        "deprecated": True,
        "outputNode": True,
        "outputName": "audio",
        "required": {
            "audio": ("AUDIO", {}),
            "filename_prefix": (
                "STRING",
                {"default": "audio/ComfyUI", "multiline": False},
            ),
        },
        "recipe": "recipe.replace-save-audio-flac",
    },
    "core.save-audio-mp3": {
        "directory": "save-audio-mp3",
        "classType": "SaveAudioMP3",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:6b831dbf8325bcd6a3471b857742220da599d19c30fa92e5a12d435962ca57d1",
        "deprecated": True,
        "outputNode": True,
        "outputName": "audio",
        "required": {
            "audio": ("AUDIO", {}),
            "filename_prefix": (
                "STRING",
                {"default": "audio/ComfyUI", "multiline": False},
            ),
            "quality": (
                "COMBO",
                {
                    "default": "V0",
                    "multiselect": False,
                    "options": ["V0", "128k", "320k"],
                },
            ),
        },
        "recipe": "recipe.replace-save-audio-mp3",
    },
    "core.save-audio-opus": {
        "directory": "save-audio-opus",
        "classType": "SaveAudioOpus",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:f31967e146ded9377a0bb5457336f32d8fa0e7e6ec354377b145d96f25ab4302",
        "deprecated": True,
        "outputNode": True,
        "outputName": "audio",
        "required": {
            "audio": ("AUDIO", {}),
            "filename_prefix": (
                "STRING",
                {"default": "audio/ComfyUI", "multiline": False},
            ),
            "quality": (
                "COMBO",
                {
                    "default": "128k",
                    "multiselect": False,
                    "options": ["64k", "96k", "128k", "192k", "320k"],
                },
            ),
        },
        "recipe": "recipe.replace-save-audio-opus",
    },
    "core.record-audio": {
        "directory": "record-audio",
        "classType": "RecordAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:1d908346073efcce2e7dc78d41319f288c2a77346923dc9126f9e1a735f6e234",
        "deprecated": False,
        "outputNode": False,
        "outputName": "AUDIO",
        "required": {"audio": ("AUDIO_RECORD", {})},
        "recipe": None,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.replace-save-audio-flac": "replace-save-audio-flac",
    "recipe.replace-save-audio-mp3": "replace-save-audio-mp3",
    "recipe.replace-save-audio-opus": "replace-save-audio-opus",
}

EXPECTED_FRAGMENT_SETTINGS = {
    "recipe.replace-save-audio-flac": {
        "filename_prefix": "audio/ComfyUI",
        "format": {"format": "flac"},
    },
    "recipe.replace-save-audio-mp3": {
        "filename_prefix": "audio/ComfyUI",
        "format": {"format": "mp3", "quality": "V0"},
    },
    "recipe.replace-save-audio-opus": {
        "filename_prefix": "audio/ComfyUI",
        "format": {"format": "opus", "quality": "128k"},
    },
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
SYNTHETIC_PROBE = Path(__file__).with_name("deprecated_audio_synthetic_probe.py")

FRONTEND_SOURCE = catalog.ROOT / ".frontend-source-1.48.7"
FRONTEND_COMMIT = "6d6af63c00f132cd25dc29307fc56bd2c094fa22"

FRONTEND_SITE = (
    Path(os.environ.get("TEMP", ""))
    / "nodes-wizard-comfyui-v0.32.0-venv"
    / "Lib"
    / "site-packages"
)
FRONTEND_PACKAGE = FRONTEND_SITE / "comfyui_frontend_package"
FRONTEND_DIST_INFO = FRONTEND_SITE / "comfyui_frontend_package-1.48.7.dist-info"
FRONTEND_CORE_MAP = (
    FRONTEND_PACKAGE / "static" / "assets" / "core-BIz9CJ30.js.map"
)
FRONTEND_AUDIO_SERVICE_MAP = (
    FRONTEND_PACKAGE
    / "static"
    / "assets"
    / "audioService-BqTlRGqJ.js.map"
)
FRONTEND_CORE_MAP_SHA256 = (
    "c384b4eb6d0cd96f29d609cd0b62d1d96769530fc259e73056261b4f7deac744"
)
FRONTEND_AUDIO_SERVICE_MAP_SHA256 = (
    "a4a7ecb6a0aa376d9a2cf852b6054a2238846227ad05e3e946622bf1cadb7991"
)

UPLOAD_AUDIO_CONTRACT = (
    "name: 'Comfy.RecordAudio'",
    "AUDIO_RECORD(node, inputName: string)",
    "audioUIWidget.serializeValue = async () => {",
    "mediaRecorder.stop()",
    "await stopPromise",
    "const blob = await fetch(audioSrc).then((r) => r.blob())",
    "return await useAudioService().convertBlobToFileAndSubmit(blob)",
    "currentStream = await navigator.mediaDevices.getUserMedia({",
    "audio: true",
    "mediaRecorder = new ExtendableMediaRecorder(currentStream, {",
    "mimeType: 'audio/wav'",
    "const audioBlob = new Blob(audioChunks, { type: 'audio/wav' })",
    "useAudioService().stopAllTracks(currentStream)",
    "URL.createObjectURL(audioBlob)",
    "node.onRemoved = function () {",
    "if (node.constructor.comfyClass !== 'RecordAudio') return",
    "await useAudioService().registerWavEncoder()",
)

AUDIO_SERVICE_CONTRACT = (
    "await register(await connect())",
    "currentStream.getTracks().forEach((track) => {",
    "track.stop()",
    "const name = `recording-${Date.now()}.wav`",
    "const file = new File([blob], name, { type: blob.type || 'audio/wav' })",
    "body.append('image', file)",
    "body.append('subfolder', 'audio')",
    "body.append('type', 'temp')",
    "const resp = await api.fetchApi('/upload/image', {",
    "method: 'POST'",
    "return `audio/${tempAudio.name} [temp]`",
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


def load_official_workflows(
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    workflows: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    subgraph_count = 0
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        members = sorted(
            member
            for member in archive.namelist()
            if "/templates/" in member and member.endswith(".json")
        )
        for member in members:
            payload = json.loads(archive.read(member).decode("utf-8"))
            workflows[member] = payload
            if not isinstance(payload, dict):
                continue
            definitions = payload.get("definitions")
            subgraphs = (
                definitions.get("subgraphs", [])
                if isinstance(definitions, dict)
                else []
            )
            subgraph_count += sum(isinstance(item, dict) for item in subgraphs)
            records.extend(workflow_node_records(payload, member))
    return workflows, records, subgraph_count


def connected_types(
    graph: dict[str, Any], node_id: Any
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    nodes = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    }
    links: dict[Any, list[Any]] = {}
    for link in graph.get("links", []) or []:
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
    incoming: list[tuple[str, str, str]] = []
    outgoing: list[tuple[str, str, str]] = []
    for input_value in node.get("inputs", []) or []:
        link = links.get(input_value.get("link"))
        if link is not None:
            incoming.append(
                (
                    str(nodes[link[1]].get("type")),
                    str(input_value.get("name")),
                    str(link[5]),
                )
            )
    for output_value in node.get("outputs", []) or []:
        for link_id in output_value.get("links") or []:
            link = links[link_id]
            target = nodes[link[3]]
            target_name = next(
                item["name"]
                for item in target.get("inputs", []) or []
                if item.get("link") == link_id
            )
            outgoing.append((str(target.get("type")), str(target_name), str(link[5])))
    return incoming, outgoing


def source_map_content(path: Path, suffix: str) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_index = next(
        index
        for index, source in enumerate(payload["sources"])
        if source.endswith(suffix)
    )
    content = payload["sourcesContent"][source_index]
    if not isinstance(content, str):
        raise AssertionError(f"source map has no text for {suffix}")
    return content


class DeprecatedAudioContentTests(unittest.TestCase):
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
            self.assertIn(
                "human approval pending", article["editorial"]["reviewedBy"]
            )
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["classType"], article["runtimeIdentity"]["classType"])
            self.assertEqual(
                spec["pythonModule"], article["runtimeIdentity"]["pythonModule"]
            )

            expected_assets = set() if spec["recipe"] is None else {spec["recipe"]}
            if article_id == "core.record-audio":
                expected_assets.add("recipe.record-audio-local-check")
            self.assertEqual(
                expected_assets,
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
                r"важно отметить|стоит отметить|следует отметить|"
                r"в современном мире|революционн|является мощн|"
                r"\bдавайте\b|глубже погруз|открывает новые|"
                r"может показаться|позволяет вам|подводя итог|"
                r"в заключение|не просто .{0,80},? а ",
            )

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual(
                [], catalog.json_schema_errors(research, schemas["research"])
            )
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["pythonModule"], research["node"]["pythonModule"])
            self.assertEqual("backend", research["node"]["origin"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual("0.32.0", research["baseline"]["comfyui"])
            self.assertEqual("1.48.7", research["baseline"]["frontend"])
            self.assertEqual("0.5.9", research["baseline"]["embeddedDocs"])
            self.assertEqual(
                "0.1.42", research["baseline"]["workflowTemplatesJson"]
            )
            self.assertTrue(research["checks"]["implementationRead"])
            self.assertTrue(research["checks"]["runtimeCompared"])
            self.assertTrue(research["checks"]["officialCasesInspected"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(research["knownGaps"])

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual(directory, path.parent.name)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn(
                "human approval pending", recipe["editorial"]["reviewedBy"]
            )

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, schemas["fragment"])
            )
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            self.assertEqual(
                [{"id": "audio", "type": "AUDIO", "to": "save", "input": "audio"}],
                fragment["externalInputs"],
            )
            self.assertEqual([], fragment["connections"])
            self.assertEqual(1, len(fragment["nodes"]))
            node = fragment["nodes"][0]
            self.assertEqual("save", node["ref"])
            self.assertEqual("SaveAudioAdvanced", node["classType"])
            self.assertEqual(EXPECTED_FRAGMENT_SETTINGS[recipe_id], node["settings"])

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_and_fragment_settings(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))

        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            runtime = runtime_nodes[spec["classType"]]
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual("audio", runtime["category"])
            self.assertEqual(spec["deprecated"], runtime["deprecated"])
            self.assertEqual(spec["outputNode"], runtime["output_node"])
            self.assertFalse(runtime["experimental"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertEqual(["AUDIO"], runtime["output"])
            self.assertEqual([spec["outputName"]], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertEqual(
                spec["required"],
                {
                    name: (descriptor[0], descriptor[1])
                    for name, descriptor in runtime["input"]["required"].items()
                },
            )
            if spec["classType"].startswith("SaveAudio"):
                self.assertEqual(
                    {"prompt": ["PROMPT"], "extra_pnginfo": ["EXTRA_PNGINFO"]},
                    runtime["input"]["hidden"],
                )
            else:
                self.assertNotIn("hidden", runtime["input"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        advanced = runtime_nodes["SaveAudioAdvanced"]
        advanced_specs = runtime_input_specs(advanced)
        self.assertEqual("AUDIO", descriptor_type(advanced_specs["audio"]))
        dynamic = advanced_specs["format"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", descriptor_type(dynamic))
        options = {item["key"]: item for item in dynamic[1]["options"]}
        self.assertEqual({"flac", "mp3", "opus"}, set(options))
        self.assertEqual({}, options["flac"]["inputs"]["required"])
        self.assertEqual(
            ["V0", "128k", "320k"],
            options["mp3"]["inputs"]["required"]["quality"][1]["options"],
        )
        self.assertEqual(
            ["64k", "96k", "128k", "192k", "320k"],
            options["opus"]["inputs"]["required"]["quality"][1]["options"],
        )

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(
                recipe_path(recipe_id).parent / recipe["fragment"]["path"]
            )
            node = fragment["nodes"][0]
            settings = node["settings"]
            self.assertEqual("SaveAudioAdvanced", node["classType"])
            self.assertEqual("audio/ComfyUI", settings["filename_prefix"])
            selected = settings["format"]
            option = options[selected["format"]]
            nested_required = option["inputs"]["required"]
            self.assertTrue(set(nested_required).issubset(selected))
            for nested_name, nested_descriptor in nested_required.items():
                self.assertIn(
                    selected[nested_name], nested_descriptor[1]["options"]
                )
            self.assertEqual(
                "AUDIO",
                descriptor_type(advanced_specs[fragment["externalInputs"][0]["input"]]),
            )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_backend_implementations_and_python_defaults(self) -> None:
        audio = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(
            encoding="utf-8"
        )
        ui = (SOURCE / "comfy_api" / "latest" / "_ui.py").read_text(
            encoding="utf-8"
        )
        requirements = (SOURCE / "requirements.txt").read_text(encoding="utf-8")

        save_audio = audio.split("class SaveAudio(IO.ComfyNode):", 1)[1].split(
            "class SaveAudioMP3(IO.ComfyNode):", 1
        )[0]
        save_mp3 = audio.split("class SaveAudioMP3(IO.ComfyNode):", 1)[1].split(
            "class SaveAudioOpus(IO.ComfyNode):", 1
        )[0]
        save_opus = audio.split("class SaveAudioOpus(IO.ComfyNode):", 1)[1].split(
            "class SaveAudioAdvanced(IO.ComfyNode):", 1
        )[0]
        record = audio.split("class RecordAudio(IO.ComfyNode):", 1)[1].split(
            "class TrimAudioDuration(IO.ComfyNode):", 1
        )[0]

        self.assertIn('IO.String.Input("filename_prefix", default="audio/ComfyUI")', save_audio)
        self.assertIn("is_deprecated=True", save_audio)
        self.assertIn("is_output_node=True", save_audio)
        self.assertIn('outputs=[IO.Audio.Output("audio")]', save_audio)
        self.assertIn(
            'def execute(cls, audio, filename_prefix="ComfyUI", format="flac")',
            save_audio,
        )
        self.assertIn("if audio is None:", save_audio)
        self.assertIn("return IO.NodeOutput(\n            audio,", save_audio)

        self.assertIn(
            'IO.Combo.Input("quality", options=["V0", "128k", "320k"], default="V0")',
            save_mp3,
        )
        self.assertIn(
            'def execute(cls, audio, filename_prefix="ComfyUI", format="mp3", quality="128k")',
            save_mp3,
        )
        self.assertIn("is_deprecated=True", save_mp3)
        self.assertIn('outputs=[IO.Audio.Output("audio")]', save_mp3)

        self.assertIn(
            'IO.Combo.Input("quality", options=["64k", "96k", "128k", "192k", "320k"], default="128k")',
            save_opus,
        )
        self.assertIn(
            'def execute(cls, audio, filename_prefix="ComfyUI", format="opus", quality="V3")',
            save_opus,
        )
        self.assertIn("is_deprecated=True", save_opus)
        self.assertIn('outputs=[IO.Audio.Output("audio")]', save_opus)

        self.assertIn('IO.Custom("AUDIO_RECORD").Input("audio")', record)
        self.assertIn("audio_path = folder_paths.get_annotated_filepath(audio)", record)
        self.assertIn("waveform, sample_rate = load(audio_path)", record)
        self.assertIn('audio = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}', record)
        self.assertIn("return IO.NodeOutput(audio)", record)

        self.assertIn(
            'for batch_number, waveform in enumerate(audio["waveform"].cpu())', ui
        )
        self.assertIn('filename.replace("%batch_num%", str(batch_number))', ui)
        self.assertIn('layout = "mono" if waveform.shape[0] == 1 else "stereo"', ui)
        self.assertIn("_OPUS_RATES = [8000, 12000, 16000, 24000, 48000]", ui)
        self.assertIn("torchaudio.functional.resample", ui)
        self.assertIn('out_stream.codec_context.qscale = 1', ui)
        self.assertIn('folder_type=FolderType.output', ui)
        self.assertIn("comfyui-frontend-package==1.48.7", requirements.splitlines())

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_hash_paths_and_known_omissions(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        names = ["SaveAudio", "SaveAudioMP3", "SaveAudioOpus", "RecordAudio"]
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            for name in names:
                for locale in ("en", "ru"):
                    archive_path = (
                        f"comfyui_embedded_docs/docs/{name}/{locale}.md"
                    )
                    self.assertIn(archive_path, archive.namelist())
                    docs[(name, locale)] = archive.read(archive_path).decode("utf-8")

        self.assertTrue(
            all(
                "This documentation was AI-generated" in docs[(name, "en")]
                for name in names
            )
        )
        for name in ("SaveAudio", "SaveAudioMP3", "SaveAudioOpus"):
            english_outputs = docs[(name, "en")].split("## Outputs", 1)[1]
            self.assertIn("does not return", english_outputs.lower())
            self.assertNotIn("| `audio` |", english_outputs.lower())
            russian_outputs = re.split(
                r"## Выходн(?:ые данные|ые параметры)", docs[(name, "ru")], maxsplit=1
            )[1]
            self.assertIn("не возвращает", russian_outputs.lower())

        # Runtime and source return AUDIO from all three savers; the pinned docs do not.
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        self.assertTrue(
            all(runtime_nodes[name]["output"] == ["AUDIO"] for name in names[:3])
        )

        record_doc = docs[("RecordAudio", "en")].lower()
        self.assertIn("audio_record", record_doc)
        self.assertIn("| `audio` |", record_doc)
        for omitted in (
            "getusermedia",
            "mediarecorder",
            "/upload/image",
            "[temp]",
            "microphone permission",
            "[1,c,t]",
        ):
            self.assertNotIn(omitted, record_doc)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_root_and_subgraph_census(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        workflows, records, subgraph_count = load_official_workflows()
        self.assertEqual(512, len(workflows))
        self.assertEqual(272, subgraph_count)

        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        targets = [record for record in records if record["node"].get("type") in target_types]
        self.assertEqual(
            {"SaveAudioMP3": 19, "SaveAudioOpus": 4, "RecordAudio": 11},
            dict(Counter(record["node"]["type"] for record in targets)),
        )
        self.assertFalse(
            any(record["node"].get("type") == "SaveAudio" for record in records)
        )
        self.assertTrue(all(record["scope"] == "root" for record in targets))

        mp3_records = [
            record for record in targets if record["node"]["type"] == "SaveAudioMP3"
        ]
        self.assertEqual(19, len({record["member"] for record in mp3_records}))
        self.assertEqual(6, len({record["workflowId"] for record in mp3_records}))
        self.assertEqual(Counter({0: 19}), Counter(r["node"].get("mode") for r in mp3_records))
        self.assertTrue(
            all(record["node"].get("widgets_values", [])[-1] == "V0" for record in mp3_records)
        )
        self.assertEqual(
            Counter(
                {
                    "audio/ComfyUI": 10,
                    "audio/stable_audio_3": 2,
                    "audio/ElevenLabs_sound_effects": 1,
                    "audio/11labs_voice_isolation": 1,
                    "audio/ace_step1.5_xl_base": 1,
                    "audio/shift6": 1,
                    "audio/ACE_Step1.5_xl_turbo": 1,
                    "audio/ace-step-1.5": 1,
                    "audio/text2speech2video": 1,
                }
            ),
            Counter(record["node"]["widgets_values"][0] for record in mp3_records),
        )
        mp3_incoming: list[tuple[str, str, str]] = []
        for record in mp3_records:
            incoming, outgoing = connected_types(
                record["graph"], record["node"]["id"]
            )
            self.assertEqual(1, len(incoming), record["member"])
            self.assertEqual("audio", incoming[0][1], record["member"])
            self.assertEqual("AUDIO", incoming[0][2], record["member"])
            self.assertEqual([], outgoing, record["member"])
            mp3_incoming.extend(incoming)
        upstream_types = Counter(item[0] for item in mp3_incoming)
        self.assertEqual(10, upstream_types["VAEDecodeAudio"])
        self.assertEqual(
            6,
            sum(
                count
                for node_type, count in upstream_types.items()
                if node_type.startswith("ElevenLabs")
            ),
        )
        self.assertEqual(
            3,
            sum(
                count
                for node_type, count in upstream_types.items()
                if re.fullmatch(r"[0-9a-f-]{36}", node_type)
            ),
        )

        stable_member = next(
            member
            for member in workflows
            if member.endswith("/audio_stable_audio_example.json")
        )
        stable_record = next(record for record in mp3_records if record["member"] == stable_member)
        self.assertEqual(
            "5fa61cc8-29d9-4deb-9f90-02d3c00b63b3",
            stable_record["workflowId"],
        )
        self.assertEqual(19, stable_record["node"]["id"])
        self.assertEqual(["audio/ComfyUI", "V0"], stable_record["node"]["widgets_values"])
        self.assertEqual(
            [("VAEDecodeAudio", "audio", "AUDIO")],
            connected_types(stable_record["graph"], 19)[0],
        )

        opus_records = [
            record for record in targets if record["node"]["type"] == "SaveAudioOpus"
        ]
        self.assertEqual(4, len({record["member"] for record in opus_records}))
        self.assertEqual(2, len({record["workflowId"] for record in opus_records}))
        self.assertEqual(Counter({4: 4}), Counter(r["node"].get("mode") for r in opus_records))
        self.assertTrue(
            all(
                record["node"].get("widgets_values")
                == ["audio/ComfyUI", "128k"]
                for record in opus_records
            )
        )
        self.assertEqual(
            {
                "api_elevenlabs_speech_to_speech.json",
                "api_elevenlabs_text_to_dialogue.json",
                "api_elevenlabs_text_to_sound_effects.json",
                "api_elevenlabs_text_to_speech.json",
            },
            {Path(record["member"]).name for record in opus_records},
        )
        for record in opus_records:
            self.assertEqual(
                ([], []), connected_types(record["graph"], record["node"]["id"])
            )

        record_records = [
            record for record in targets if record["node"]["type"] == "RecordAudio"
        ]
        self.assertEqual(11, len({record["member"] for record in record_records}))
        self.assertEqual(5, len({record["workflowId"] for record in record_records}))
        self.assertEqual(Counter({4: 11}), Counter(r["node"].get("mode") for r in record_records))
        self.assertTrue(
            all(record["node"].get("widgets_values") == ["", ""] for record in record_records)
        )
        for record in record_records:
            self.assertEqual(
                ([], []), connected_types(record["graph"], record["node"]["id"])
            )

    @unittest.skipUnless(
        FRONTEND_SOURCE.exists(), "pinned frontend 1.48.7 source checkout is absent"
    )
    def test_exact_pinned_frontend_record_audio_contract(self) -> None:
        self.assertEqual(
            FRONTEND_COMMIT,
            (FRONTEND_SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip(),
        )
        package = catalog.load_json(FRONTEND_SOURCE / "package.json")
        self.assertEqual("1.48.7", package["version"])
        upload_audio = (
            FRONTEND_SOURCE / "src" / "extensions" / "core" / "uploadAudio.ts"
        ).read_text(encoding="utf-8")
        audio_service = (
            FRONTEND_SOURCE / "src" / "services" / "audioService.ts"
        ).read_text(encoding="utf-8")
        for exact in UPLOAD_AUDIO_CONTRACT:
            self.assertIn(exact, upload_audio)
        for exact in AUDIO_SERVICE_CONTRACT:
            self.assertIn(exact, audio_service)

    @unittest.skipUnless(
        FRONTEND_CORE_MAP.exists() and FRONTEND_AUDIO_SERVICE_MAP.exists(),
        "installed pinned frontend 1.48.7 source maps are absent",
    )
    def test_installed_frontend_source_maps_independently_match_contract(self) -> None:
        metadata = (FRONTEND_DIST_INFO / "METADATA").read_text(encoding="utf-8")
        self.assertIn("Name: comfyui_frontend_package", metadata.splitlines())
        self.assertIn("Version: 1.48.7", metadata.splitlines())
        self.assertEqual(
            FRONTEND_CORE_MAP_SHA256,
            hashlib.sha256(FRONTEND_CORE_MAP.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            FRONTEND_AUDIO_SERVICE_MAP_SHA256,
            hashlib.sha256(FRONTEND_AUDIO_SERVICE_MAP.read_bytes()).hexdigest(),
        )

        upload_audio = source_map_content(FRONTEND_CORE_MAP, "src/extensions/core/uploadAudio.ts")
        audio_service = source_map_content(
            FRONTEND_AUDIO_SERVICE_MAP, "src/services/audioService.ts"
        )

        for exact in UPLOAD_AUDIO_CONTRACT:
            self.assertIn(exact, upload_audio)

        for exact in AUDIO_SERVICE_CONTRACT:
            self.assertIn(exact, audio_service)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_synthetic_execution_without_browser_or_models(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for the deprecated audio probe")
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
            self.skipTest(
                f"deprecated audio probe dependencies unavailable: {result.stderr}"
            )
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(2, payload["saveAudio"]["batchFiles"])
        self.assertTrue(payload["saveAudio"]["passthroughIdentity"])
        self.assertEqual(
            {"codec": "flac", "sampleRate": 8000, "layout": "stereo"},
            payload["saveAudio"]["stream"],
        )
        self.assertEqual(
            [2, 120], payload["saveAudio"]["threeChannelDecodedShape"]
        )
        self.assertEqual(
            {"V0", "128k", "320k"},
            set(payload["saveAudioMP3"]["qualities"]),
        )
        self.assertTrue(payload["saveAudioMP3"]["pythonDefaultFile"])
        for stream in payload["saveAudioMP3"]["qualities"].values():
            self.assertTrue(stream["codec"].startswith("mp3"))
            self.assertEqual(44100, stream["sampleRate"])
            self.assertEqual("mono", stream["layout"])

        self.assertEqual(
            {"64k", "96k", "128k", "192k", "320k"},
            set(payload["saveAudioOpus"]["qualities"]),
        )
        self.assertTrue(payload["saveAudioOpus"]["mono320kRejected"])
        self.assertTrue(payload["saveAudioOpus"]["pythonDefaultFile"])
        for quality, stream in payload["saveAudioOpus"]["qualities"].items():
            self.assertEqual("opus", stream["codec"])
            self.assertEqual(48000, stream["sampleRate"])
            self.assertEqual("stereo" if quality == "320k" else "mono", stream["layout"])

        self.assertEqual(
            {
                "SaveAudio": "SaveAudio: input audio is None (source video may have no audio track).",
                "SaveAudioMP3": "SaveAudioMP3: input audio is None (source video may have no audio track).",
                "SaveAudioOpus": "SaveAudioOpus: input audio is None (source video may have no audio track).",
            },
            payload["noneErrors"],
        )
        self.assertEqual([1, 1, 80], payload["recordAudio"]["shape"])
        self.assertEqual(8000, payload["recordAudio"]["sampleRate"])
        self.assertEqual(-1.0, payload["recordAudio"]["first"])
        self.assertAlmostEqual(32767 / 32768, payload["recordAudio"]["last"])
        self.assertFalse(payload["recordAudio"]["browserExecuted"])


if __name__ == "__main__":
    unittest.main()
