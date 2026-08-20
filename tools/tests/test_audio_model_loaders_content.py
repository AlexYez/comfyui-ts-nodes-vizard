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
    "core.ltxv-audio-vae-loader": {
        "directory": "ltxv-audio-vae-loader",
        "classType": "LTXVAudioVAELoader",
        "pythonModule": "comfy_extras.nodes_lt_audio",
        "fingerprint": "sha256:5483348324384b5122eb55fe218919220931a4e52fe63ba753dca390e3dcce71",
        "recipes": ["recipe.load-ltxv-audio-vae-for-encode-decode"],
        "docs": {
            "en": "6828d5e7f8352e8cdcd7be943b48aa23dd5bd94c79689169df9c4e83eef8a8ea",
            "ru": "c7d7e78a79be33fa241de978cd4935bd54ea67bb9edb861c0e0457c5b401cb94",
        },
    },
    "core.ltxav-text-encoder-loader": {
        "directory": "ltxav-text-encoder-loader",
        "classType": "LTXAVTextEncoderLoader",
        "pythonModule": "comfy_extras.nodes_lt_audio",
        "fingerprint": "sha256:47204f52171b84be9098b9a1c0a87ae7265a40e94432e3425d52466e0d189774",
        "recipes": ["recipe.load-ltxav-text-encoder-for-prompts"],
        "docs": {
            "en": "d3b52054f6d57b05f5ca6e32d443782f28a118e850a35f03c74282336bfb622c",
            "ru": "6052471fe58a8a136d219c4df97a7abff56ad8564723f8ee3e95da7ed1a38622",
        },
    },
    "core.audio-encoder-loader": {
        "directory": "audio-encoder-loader",
        "classType": "AudioEncoderLoader",
        "pythonModule": "comfy_extras.nodes_audio_encoder",
        "fingerprint": "sha256:1081da530587f98b6a1d013f4ee13a73097333b81c676f78a0a099ee052661bd",
        "recipes": ["recipe.encode-audio-for-humo"],
        "docs": {
            "en": "b441dbccd5da339a568d69762762c2fa1e3336146580a62c3406d366ae0d49e5",
            "ru": "e27367788e551c364d285d67810d53071791ab1ad448a0f09a8fd29485a4eb32",
        },
    },
    "core.audio-encoder-encode": {
        "directory": "audio-encoder-encode",
        "classType": "AudioEncoderEncode",
        "pythonModule": "comfy_extras.nodes_audio_encoder",
        "fingerprint": "sha256:f391593cefb0b34f2dad1a4d2f700039a0e2727458639d2a65573ba075362128",
        "recipes": ["recipe.encode-audio-for-humo"],
        "docs": {
            "en": "b72ab0c78bf6f143a8546d674b45ca515b880594ccadc043ac284af9c5d6470e",
            "ru": "acfefd542e8534fbc55cc06df41cc5518affc522dc5bd5ce09626a8eb0a0cd45",
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-ltxv-audio-vae-for-encode-decode": "load-ltxv-audio-vae-for-encode-decode",
    "recipe.load-ltxav-text-encoder-for-prompts": "load-ltxav-text-encoder-for-prompts",
    "recipe.encode-audio-for-humo": "encode-audio-for-humo",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("audio_model_loaders_synthetic_probe.py")


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


class AudioModelLoadersContentTests(unittest.TestCase):
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
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["recipes"], [asset["id"] for asset in article["assets"]])
            for relation in article["relations"]["related"] + article["relations"]["alternatives"]:
                self.assertIn(relation, article_ids, (article_id, relation))

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
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIsNone(cliche.search(body), recipe_id)
            self.assertNotIn("\ufffd", body)
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

        self.assertEqual(["default", "cpu"], nodes["LTXAVTextEncoderLoader"]["input"]["required"]["device"][1]["options"])
        self.assertEqual(["VAE"], nodes["LTXVAudioVAELoader"]["output"])
        self.assertEqual(["Audio VAE"], nodes["LTXVAudioVAELoader"]["output_name"])
        self.assertEqual(["AUDIO_ENCODER"], nodes["AudioEncoderLoader"]["output"])
        self.assertEqual(["AUDIO_ENCODER_OUTPUT"], nodes["AudioEncoderEncode"]["output"])

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
        ltx = (SOURCE / "comfy_extras" / "nodes_lt_audio.py").read_text(encoding="utf-8")
        nodes = (SOURCE / "comfy_extras" / "nodes_audio_encoder.py").read_text(encoding="utf-8")
        models = (SOURCE / "comfy" / "audio_encoders" / "audio_encoders.py").read_text(encoding="utf-8")
        whisper = (SOURCE / "comfy" / "audio_encoders" / "whisper.py").read_text(encoding="utf-8")
        for snippet in (
            'get_full_path_or_raise("checkpoints", ckpt_name)',
            'return_metadata=True',
            '{"audio_vae.": "autoencoder.", "vocoder.": "vocoder."}',
            "filter_keys=True",
            "vae.throw_exception_if_invalid()",
            "clip_type = comfy.sd.CLIPType.LTXV",
            "ckpt_paths=[clip_path1, clip_path2]",
            'model_options["load_device"] = model_options["offload_device"] = torch.device("cpu")',
        ):
            self.assertIn(snippet, ltx)
        for snippet in (
            'get_full_path_or_raise("audio_encoders", audio_encoder_name)',
            "load_torch_file(audio_encoder_name, safe_load=True)",
            "load_audio_encoder_from_sd(sd)",
            'raise RuntimeError("ERROR: audio encoder file is invalid',
            'audio_encoder.encode_audio(audio["waveform"], audio["sample_rate"])',
        ):
            self.assertIn(snippet, nodes)
        for snippet in (
            'self.model_sample_rate = 16000',
            "torchaudio.functional.resample(audio, sample_rate, self.model_sample_rate)",
            'outputs["encoded_audio"] = out',
            'outputs["encoded_audio_all_layers"] = all_layers',
            'outputs["audio_samples"] = audio.shape[2]',
            'if "encoder.layer_norm.bias" in sd',
            'elif "model.encoder.embed_positions.weight" in sd',
            'raise RuntimeError("ERROR: audio encoder not supported.")',
        ):
            self.assertIn(snippet, models)
        self.assertIn("self.n_samples = 480000", whisper)
        self.assertIn("audio = torch.mean(audio, dim=1)", whisper)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_hashes_and_omissions(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            texts: dict[tuple[str, str], str] = {}
            for spec in ARTICLE_SPECS.values():
                for locale, expected in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    raw = archive.read(name)
                    self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), name)
                    texts[(spec["classType"], locale)] = raw.decode("utf-8")
        self.assertNotIn("filter_keys", texts[("LTXVAudioVAELoader", "en")])
        self.assertNotIn("autoencoder.", texts[("LTXVAudioVAELoader", "en")])
        self.assertNotIn("CLIPType.LTXV", texts[("LTXAVTextEncoderLoader", "en")])
        self.assertNotIn("Wav2Vec2", texts[("AudioEncoderLoader", "en")])
        self.assertNotIn("encoded_audio_all_layers", texts[("AudioEncoderEncode", "en")])

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: Counter() for target in targets}
        widgets: dict[str, Counter[str]] = {target: Counter() for target in targets}
        files: dict[str, set[str]] = {target: set() for target in targets}
        incoming = Counter()
        outgoing = Counter()
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
                            widgets[node_type][json.dumps(node.get("widgets_values", []), ensure_ascii=False)] += 1
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
        self.assertEqual((0, 18, 17, 1, 16), (
            counts["LTXVAudioVAELoader"]["root"], counts["LTXVAudioVAELoader"]["subgraph"],
            counts["LTXVAudioVAELoader"]["mode:0"], counts["LTXVAudioVAELoader"]["mode:4"], len(files["LTXVAudioVAELoader"]),
        ))
        self.assertEqual((0, 18, 17, 1, 16), (
            counts["LTXAVTextEncoderLoader"]["root"], counts["LTXAVTextEncoderLoader"]["subgraph"],
            counts["LTXAVTextEncoderLoader"]["mode:0"], counts["LTXAVTextEncoderLoader"]["mode:4"], len(files["LTXAVTextEncoderLoader"]),
        ))
        self.assertEqual((3, 2, 4, 1, 3), (
            counts["AudioEncoderLoader"]["root"], counts["AudioEncoderLoader"]["subgraph"],
            counts["AudioEncoderLoader"]["mode:0"], counts["AudioEncoderLoader"]["mode:4"], len(files["AudioEncoderLoader"]),
        ))
        self.assertEqual((3, 4, 6, 1, 3), (
            counts["AudioEncoderEncode"]["root"], counts["AudioEncoderEncode"]["subgraph"],
            counts["AudioEncoderEncode"]["mode:0"], counts["AudioEncoderEncode"]["mode:4"], len(files["AudioEncoderEncode"]),
        ))
        self.assertEqual(5, widgets["LTXVAudioVAELoader"]['["ltx-2.3-22b-dev-fp8.safetensors"]'])
        self.assertEqual(5, widgets["LTXAVTextEncoderLoader"]['["gemma_3_12B_it_fp4_mixed.safetensors", "ltx-2.3-22b-dev-fp8.safetensors", "default"]'])
        self.assertEqual(2, widgets["AudioEncoderLoader"]['["wav2vec2-chinese-base_fp16.safetensors"]'])
        self.assertEqual(2, widgets["AudioEncoderLoader"]['["wav2vec2_large_english_fp16.safetensors"]'])
        self.assertEqual(1, widgets["AudioEncoderLoader"]['["whisper_large_v3_fp16.safetensors"]'])
        self.assertEqual(Counter({"[]": 7}), widgets["AudioEncoderEncode"])
        self.assertEqual(18, outgoing[("LTXVAudioVAELoader", "LTXVAudioVAEDecode", "VAE")])
        self.assertEqual(2, outgoing[("LTXVAudioVAELoader", "LTXVAudioVAEEncode", "VAE")])
        self.assertEqual(16, outgoing[("LTXVAudioVAELoader", "LTXVEmptyLatentAudio", "VAE")])
        self.assertEqual(1, outgoing[("LTXVAudioVAELoader", "LTXVReferenceAudio", "VAE")])
        self.assertEqual(32, outgoing[("LTXAVTextEncoderLoader", "CLIPTextEncode", "CLIP")])
        self.assertEqual(6, outgoing[("LTXAVTextEncoderLoader", "LoraLoader", "CLIP")])
        self.assertEqual(7, outgoing[("AudioEncoderLoader", "AudioEncoderEncode", "AUDIO_ENCODER")])
        self.assertEqual(3, incoming[("LoadAudio", "AudioEncoderEncode", "AUDIO")])
        self.assertEqual(1, outgoing[("AudioEncoderEncode", "WanHuMoImageToVideo", "AUDIO_ENCODER_OUTPUT")])
        self.assertEqual(4, outgoing[("AudioEncoderEncode", "WanInfiniteTalkToVideo", "AUDIO_ENCODER_OUTPUT")])
        self.assertEqual(2, outgoing[("AudioEncoderEncode", "WanSoundImageToVideo", "AUDIO_ENCODER_OUTPUT")])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_model_free_exact_method_probe(self) -> None:
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
        self.assertEqual(["autoencoder.encoder.weight", "vocoder.block.weight"], report["ltxAudioVaeLoader"]["keys"])
        self.assertTrue(report["ltxAudioVaeLoader"]["validated"])
        self.assertTrue(report["ltxAudioVaeLoader"]["invalidRejected"])
        self.assertEqual(["/models/text_encoders/gemma.safetensors", "/models/checkpoints/ltx.safetensors"], report["ltxTextEncoderLoader"]["paths"])
        self.assertEqual(["cpu", "cpu"], report["ltxTextEncoderLoader"]["cpuDevices"])
        self.assertTrue(report["audioEncoderLoader"]["invalidRejected"])
        self.assertTrue(report["audioEncoderEncode"]["delegatesIdentity"])
        self.assertEqual([8000, 16000, [1, 2, 8]], report["audioEncoderEncode"]["resample"])
        self.assertEqual(16, report["audioEncoderEncode"]["audioSamples"])
        self.assertEqual(["audio_samples", "encoded_audio", "encoded_audio_all_layers"], report["audioEncoderEncode"]["keys"])


if __name__ == "__main__":
    unittest.main()
