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
    "core.vae-encode-audio": {
        "directory": "vae-encode-audio",
        "classType": "VAEEncodeAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:79b40b34b464c25243174eaa37324cf92f2adef42842436da047fc2a8f54cd0b",
        "recipes": ["recipe.encode-audio-ace-latent"],
        "docs": {
            "en": "468585af70048b163b827e2d335834be57c60b910cef3b70273e097b45cfbfb9",
            "ru": "286613e48a1aa6a15a1e5ca70520be156f774b7b4515bf6960ba9599bc4f4d2a",
        },
    },
    "core.vae-decode-audio-tiled": {
        "directory": "vae-decode-audio-tiled",
        "classType": "VAEDecodeAudioTiled",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:7b778a1c2dea5519345b08497ffe6bc9a7f633a8aa4f752b8c9350bf8220e2d4",
        "recipes": ["recipe.decode-audio-tiled-512"],
        "docs": {
            "en": "3879faddd0f459c67542faa921129a0b0ca028160e7ce6969eb85aee6a483d84",
            "ru": "6200b8353f8cce514a0ad6b4d75a61a93a13eda99377c2ec4801f947bbe44b02",
        },
    },
    "core.ltxv-audio-vae-encode": {
        "directory": "ltxv-audio-vae-encode",
        "classType": "LTXVAudioVAEEncode",
        "pythonModule": "comfy_extras.nodes_lt_audio",
        "fingerprint": "sha256:1241bc4cb583386420ed3718a53e9820b423c58aa648606d834198f2a26bdaf3",
        "recipes": ["recipe.ltxv-audio-conditioning-encode"],
        "docs": {
            "en": "5515f563d16a4a36a7f2906d4a7a7daf0478b9d05203ae72a6a69182007ab454",
            "ru": "24e420358f6f28a1f5d82c8dc1c76c9ebff861942394b30a9ca6c79d029be4e2",
        },
    },
    "core.ltxv-audio-vae-decode": {
        "directory": "ltxv-audio-vae-decode",
        "classType": "LTXVAudioVAEDecode",
        "pythonModule": "comfy_extras.nodes_lt_audio",
        "fingerprint": "sha256:8e75992d4ea4cf77781d6adea98ec3fd339e3f0f0c23865802e88ca1321f50ca",
        "recipes": ["recipe.ltxv-audio-decode-to-video"],
        "docs": {
            "en": "a224532f44201e533603f067a63e4832b04e6684f92315d5099fe5bf905ead11",
            "ru": "6b35443bb5a9b15c0abc73275a5c221f5dc26358cfda676aef0eeb5b29e44201",
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.encode-audio-ace-latent": "encode-audio-ace-latent",
    "recipe.decode-audio-tiled-512": "decode-audio-tiled-512",
    "recipe.ltxv-audio-conditioning-encode": "ltxv-audio-conditioning-encode",
    "recipe.ltxv-audio-decode-to-video": "ltxv-audio-decode-to-video",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("audio_vae_latent_synthetic_probe.py")


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


def input_descriptors(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        result.update(runtime.get("input", {}).get(group, {}))
    return result


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


class AudioVaeLatentContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_honesty_and_natural_russian(self) -> None:
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        article_ids = all_article_ids()
        errors: list[str] = []
        cliche = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является мощн|давайте|глубже погруз|открывает новые|"
            r"может показаться|позволяет вам|подводя итог|в заключение|данная нода",
            re.IGNORECASE,
        )
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        seen: dict[str, str] = {}
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            manifest = catalog.load_json(path)
            class_type = manifest.get("runtimeIdentity", {}).get("classType")
            if class_type in target_types:
                self.assertNotIn(class_type, seen, class_type)
                seen[class_type] = str(path)

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]), article_id)
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["recipes"], [asset["id"] for asset in article["assets"]])
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            self.assertNotIn("\ufffd", body)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]), article_id)
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(any("человечес" in gap.lower() for gap in research["knownGaps"]), article_id)

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
            self.assertIsNone(cliche.search(recipe_body), recipe_id)
            self.assertNotIn("\ufffd", recipe_body)
        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertFalse(runtime["experimental"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["output_node"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime), article_id)
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        tiled = nodes["VAEDecodeAudioTiled"]["input"]["required"]
        self.assertEqual(["INT", {"default": 512, "min": 32, "max": 8192, "step": 8}], tiled["tile_size"])
        self.assertEqual(["INT", {"default": 64, "min": 0, "max": 1024, "step": 8}], tiled["overlap"])
        self.assertEqual(["LATENT"], nodes["VAEEncodeAudio"]["output"])
        self.assertEqual(["Audio Latent"], nodes["LTXVAudioVAEEncode"]["output_name"])
        self.assertEqual(["Audio"], nodes["LTXVAudioVAEDecode"]["output_name"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                target = by_ref[external["to"]]
                descriptor = input_descriptors(nodes[target["classType"]])[external["input"]]
                self.assertEqual(external["type"], descriptor_type(descriptor), (recipe_id, external))
                supplied[external["to"]].add(external["input"])
            for connection in fragment["connections"]:
                source = nodes[by_ref[connection["from"]]["classType"]]
                target = nodes[by_ref[connection["to"]]["classType"]]
                output_type = source["output"][source["output_name"].index(connection["output"])]
                input_type = descriptor_type(input_descriptors(target)[connection["input"]])
                self.assertEqual(output_type, input_type, (recipe_id, connection))
                supplied[connection["to"]].add(connection["input"])
            for ref, node in by_ref.items():
                required = set(nodes[node["classType"]].get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_and_replacement_contracts(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        audio = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(encoding="utf-8")
        ltx = (SOURCE / "comfy_extras" / "nodes_lt_audio.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        for snippet in (
            'raise ValueError("VAEEncodeAudio: input audio is None',
            'getattr(vae, "audio_sample_rate", 44100)',
            "torchaudio.functional.resample(audio[\"waveform\"], sample_rate, vae_sample_rate)",
            "vae.encode(waveform.movedim(1, -1))",
            'return IO.NodeOutput({"samples": t})',
            'latent = latent.unbind()[-1]',
            "vae.decode_tiled(latent, tile_x=tile, tile_y=tile, overlap=overlap)",
            "torch.std(audio, dim=[1, 2], keepdim=True) * 5.0",
            'vae_sample_rate if "sample_rate" not in samples else samples["sample_rate"]',
        ):
            self.assertIn(snippet, audio)
        for snippet in (
            "class LTXVAudioVAEEncode(VAEEncodeAudio):",
            "return super().execute(audio_vae, audio)",
            'audio_latent = audio_latent.unbind()[-1]',
            "audio_vae.decode(audio_latent).movedim(-1, 1).to(audio_latent.device)",
            "audio_vae.first_stage_model.output_sample_rate",
        ):
            self.assertIn(snippet, ltx)
        self.assertIn('args.pop("tile_y")', sd)
        self.assertIn("output = self.decode_tiled_1d(samples, **args)", sd)
        self.assertIn("self.audio_sample_rate_output = self.first_stage_model.output_sample_rate", sd)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_hashes_and_known_discrepancy(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs: dict[tuple[str, str], str] = {}
            for spec in ARTICLE_SPECS.values():
                for locale, expected in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    raw = archive.read(name)
                    self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), name)
                    docs[(spec["classType"], locale)] = raw.decode("utf-8")
        ltx_encode = docs[("LTXVAudioVAEEncode", "en")]
        self.assertIn("sample rate", ltx_encode.lower())
        self.assertIn("type identifier", ltx_encode.lower())
        implementation = (SOURCE / "comfy_extras" / "nodes_audio.py").read_text(encoding="utf-8") if SOURCE.exists() else ""
        self.assertIn('return IO.NodeOutput({"samples": t})', implementation)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: Counter() for target in targets}
        files: dict[str, set[str]] = {target: set() for target in targets}
        outgoing = Counter()
        incoming = Counter()
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
                for scope, graph in graph_scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
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
                        if target_type in targets:
                            incoming[(source_type, target_type, link_type)] += 1

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((1, 0, 1), (counts["VAEEncodeAudio"]["root"], counts["VAEEncodeAudio"]["subgraph"], len(files["VAEEncodeAudio"])))
        self.assertEqual((0, 0, 0), (counts["VAEDecodeAudioTiled"]["root"], counts["VAEDecodeAudioTiled"]["subgraph"], len(files["VAEDecodeAudioTiled"])))
        self.assertEqual((0, 2, 2), (counts["LTXVAudioVAEEncode"]["root"], counts["LTXVAudioVAEEncode"]["subgraph"], len(files["LTXVAudioVAEEncode"])))
        self.assertEqual((0, 21, 19), (counts["LTXVAudioVAEDecode"]["root"], counts["LTXVAudioVAEDecode"]["subgraph"], len(files["LTXVAudioVAEDecode"])))
        self.assertEqual((20, 1), (counts["LTXVAudioVAEDecode"]["mode:0"], counts["LTXVAudioVAEDecode"]["mode:4"]))
        self.assertEqual(1, incoming[("LoadAudio", "VAEEncodeAudio", "AUDIO")])
        self.assertEqual(1, outgoing[("VAEEncodeAudio", "KSampler", "LATENT")])
        self.assertEqual(2, incoming[("TrimAudioDuration", "LTXVAudioVAEEncode", "AUDIO")])
        self.assertEqual(2, outgoing[("LTXVAudioVAEEncode", "SetLatentNoiseMask", "LATENT")])
        self.assertEqual(21, incoming[("LTXVSeparateAVLatent", "LTXVAudioVAEDecode", "LATENT")])
        self.assertEqual(21, outgoing[("LTXVAudioVAEDecode", "CreateVideo", "AUDIO")])
        self.assertEqual(18, incoming[("LTXVAudioVAELoader", "LTXVAudioVAEDecode", "VAE")])
        self.assertEqual(3, incoming[("VAELoader", "LTXVAudioVAEDecode", "VAE")])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_model_independent_exact_class_probe(self) -> None:
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
        self.assertEqual([1, 16, 1], report["genericEncode"]["vaeInputShape"])
        self.assertEqual(["samples"], report["genericEncode"]["keys"])
        self.assertEqual([1, 2, 6], report["tiledDecode"]["shape"])
        self.assertEqual(22050, report["tiledDecode"]["sampleRate"])
        self.assertEqual(12345, report["tiledDecode"]["overrideRate"])
        self.assertTrue(report["tiledDecode"]["singletonNaN"])
        self.assertEqual(24000, report["ltxDecode"]["sampleRate"])
        self.assertTrue(report["ltxDecode"]["unscaled"])


if __name__ == "__main__":
    unittest.main()
