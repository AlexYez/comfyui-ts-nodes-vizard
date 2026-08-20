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
    "core.ltxv-empty-latent-audio": {
        "directory": "ltxv-empty-latent-audio",
        "classType": "LTXVEmptyLatentAudio",
        "pythonModule": "comfy_extras.nodes_lt_audio",
        "fingerprint": "sha256:94d23a78d091be79085a4f684424ac799af2a7f2bcff145ad646f43887b333f4",
        "recipes": ["recipe.ltxv-empty-av-sample-and-split"],
        "docs": {
            "en": "2927c7984a5197ca8a4fe34d898bb31f23a8c9727b8b70c9278f89afd2e90f29",
            "ru": "632b7e794c57292ca8ae166d436ef1f220398c83dc63e8973073f5d06daffd63",
        },
    },
    "core.ltxv-concat-av-latent": {
        "directory": "ltxv-concat-av-latent",
        "classType": "LTXVConcatAVLatent",
        "pythonModule": "comfy_extras.nodes_lt",
        "fingerprint": "sha256:d3acc56f6dd01fcaab5e7ff80a1ea34710f6164f5eae0b8ec090263d5e59f180",
        "recipes": ["recipe.ltxv-empty-av-sample-and-split"],
        "docs": {
            "en": "208a0f66392081a18f24ef636d95c00367a9a7234ae23f1299824473f7bae81e",
            "ru": "65801d98172b9e665568a3705fb88a0369fb641967bc8766a1336620a8ba5bdc",
        },
    },
    "core.ltxv-separate-av-latent": {
        "directory": "ltxv-separate-av-latent",
        "classType": "LTXVSeparateAVLatent",
        "pythonModule": "comfy_extras.nodes_lt",
        "fingerprint": "sha256:9aa183ccf30449afffab27a3fdbc03b541e03437b985f78256aa49670b0dbf0a",
        "recipes": ["recipe.ltxv-empty-av-sample-and-split"],
        "docs": {
            "en": "323dc3dc34a5559e20ecc53f0e1d05dd1475c59c0b175e3f6afc935d06cc0ff1",
            "ru": "b53f9b5bbc73b08c02b6570f6de3e3a188b815efccbfd42faa83dc26a8ccb3d3",
        },
    },
    "core.ltxv-reference-audio": {
        "directory": "ltxv-reference-audio",
        "classType": "LTXVReferenceAudio",
        "pythonModule": "comfy_extras.nodes_lt",
        "fingerprint": "sha256:3b6634f8f0d62d633b4917834ea9da24aea26cb9f15ec4b9b8b35249ba4bc8a6",
        "recipes": ["recipe.ltxv-reference-audio-id-lora"],
        "docs": {
            "en": "ac369baab718f09fed875d7d56384b34890731abe57036f25f82e0bc0ff54c03",
            "ru": "33328a9ef11372de1f80b1bc85b1a4a7a869cf3cd3d915643d2131134aa587f5",
        },
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ltxv-empty-av-sample-and-split": "ltxv-empty-av-sample-and-split",
    "recipe.ltxv-reference-audio-id-lora": "ltxv-reference-audio-id-lora",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("ltxv_av_latent_reference_synthetic_probe.py")


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


class LtxvAvLatentReferenceContentTests(unittest.TestCase):
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
            r"может показаться|позволяет вам|подводя итог|в заключение|данная нода|"
            r"вот перевод документации",
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

        empty = nodes["LTXVEmptyLatentAudio"]
        self.assertEqual(["frames_number", "frame_rate", "batch_size", "audio_vae"], empty["input_order"]["required"])
        self.assertEqual("FLOAT,INT", descriptor_type(empty["input"]["required"]["frame_rate"]))
        self.assertEqual(97, empty["input"]["required"]["frames_number"][1]["default"])
        self.assertEqual(25.0, empty["input"]["required"]["frame_rate"][1]["default"])
        self.assertEqual(4096, empty["input"]["required"]["batch_size"][1]["max"])
        self.assertEqual(["LATENT"], empty["output"])
        self.assertEqual(["Latent"], empty["output_name"])
        self.assertEqual(["video_latent", "audio_latent"], nodes["LTXVConcatAVLatent"]["input_order"]["required"])
        self.assertEqual(["latent"], nodes["LTXVConcatAVLatent"]["output_name"])
        self.assertEqual(["video_latent", "audio_latent"], nodes["LTXVSeparateAVLatent"]["output_name"])
        reference = nodes["LTXVReferenceAudio"]
        self.assertEqual(["MODEL", "CONDITIONING", "CONDITIONING"], reference["output"])
        self.assertEqual(["MODEL", "positive", "negative"], reference["output_name"])
        self.assertEqual(3.0, reference["input"]["required"]["identity_guidance_scale"][1]["default"])
        self.assertEqual(100.0, reference["input"]["required"]["identity_guidance_scale"][1]["max"])
        self.assertEqual(0.0, reference["input"]["required"]["start_percent"][1]["default"])
        self.assertEqual(1.0, reference["input"]["required"]["end_percent"][1]["default"])

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
        ltx_audio = (SOURCE / "comfy_extras" / "nodes_lt_audio.py").read_text(encoding="utf-8")
        ltx = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        nested = (SOURCE / "comfy" / "nested_tensor.py").read_text(encoding="utf-8")
        helpers = (SOURCE / "node_helpers.py").read_text(encoding="utf-8")
        for snippet in (
            'assert audio_vae is not None, "Audio VAE model is required"',
            "audio_vae.first_stage_model.num_of_latents_from_frames(frames_number, frame_rate)",
            "(batch_size, z_channels, num_audio_latents, audio_freq)",
            '"type": "audio"',
        ):
            self.assertIn(snippet, ltx_audio)
        for snippet in (
            "output.update(video_latent)",
            "output.update(audio_latent)",
            "if video_samples.is_nested",
            "audio_samples, audio_noise_mask = cls.fit_audio(streams[1], audio_samples, audio_noise_mask)",
            "torch.ones_like(pad)",
            "latents = av_latent[\"samples\"].unbind()",
            "video_latent[\"samples\"] = latents[0]",
            "audio_latent[\"samples\"] = latents[1]",
            "audio_vae.encode(waveform.movedim(1, -1))",
            "ref_tokens = audio_latents.permute(0, 2, 1, 3).reshape(b, t, c * f)",
            'mc.pop("ref_audio", None)',
            "return cfg_result + (cond_pred - pred_noref) * scale",
        ):
            self.assertIn(snippet, ltx)
        self.assertIn("return self.tensors", nested)
        self.assertIn("return self.tensors[0].shape", nested)
        self.assertIn("n = [t[0], t[1].copy()]", helpers)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacements)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_hashes_and_known_discrepancies(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs: dict[tuple[str, str], str] = {}
            for spec in ARTICLE_SPECS.values():
                for locale, expected in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['classType']}/{locale}.md"
                    raw = archive.read(name)
                    self.assertEqual(expected, hashlib.sha256(raw).hexdigest(), name)
                    docs[(spec["classType"], locale)] = raw.decode("utf-8")
        self.assertIn("INT", docs[("LTXVEmptyLatentAudio", "en")])
        self.assertEqual("FLOAT,INT", descriptor_type(catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))["LTXVEmptyLatentAudio"]["input"]["required"]["frame_rate"]))
        self.assertIn("concatenated", docs[("LTXVConcatAVLatent", "en")].lower())
        self.assertIn("batch dimension", docs[("LTXVSeparateAVLatent", "en")].lower())
        self.assertGreaterEqual(docs[("LTXVReferenceAudio", "ru")].count("| `positive` |"), 2)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        counts = {target: Counter() for target in targets}
        files: dict[str, set[str]] = {target: set() for target in targets}
        widgets = {target: Counter() for target in targets}
        outgoing = Counter()
        incoming = Counter()
        incoming_ports = Counter()
        repeat_concat_video_sources = Counter()
        representative: tuple[dict[int, dict[str, Any]], set[tuple[Any, int, Any, int, Any]]] | None = None
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
                    link_set: set[tuple[Any, int, Any, int, Any]] = set()
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            files[node_type].add(member)
                            widgets[node_type][json.dumps(node.get("widgets_values", []), separators=(",", ":"))] += 1
                    for link in graph.get("links", []):
                        fields = link_fields(link)
                        if fields is None:
                            continue
                        link_set.add(fields)
                        origin_id, origin_slot, target_id, target_slot, link_type = fields
                        source_type = nodes.get(origin_id, {}).get("type")
                        target_type = nodes.get(target_id, {}).get("type")
                        if source_type in targets:
                            outgoing[(source_type, target_type, link_type)] += 1
                        if target_type in targets:
                            incoming[(source_type, target_type, link_type)] += 1
                            target_inputs = nodes.get(target_id, {}).get("inputs", [])
                            if isinstance(target_inputs, list) and 0 <= target_slot < len(target_inputs):
                                target_input = target_inputs[target_slot]
                                if isinstance(target_input, dict):
                                    incoming_ports[(source_type, target_type, target_input.get("name"), link_type)] += 1
                    for concat_id, concat_node in nodes.items():
                        if concat_node.get("type") != "LTXVConcatAVLatent":
                            continue
                        separate_audio_links = [
                            fields
                            for fields in link_set
                            if fields[2] == concat_id
                            and fields[3] == 1
                            and nodes.get(fields[0], {}).get("type") == "LTXVSeparateAVLatent"
                        ]
                        if not separate_audio_links:
                            continue
                        video_links = [fields for fields in link_set if fields[2] == concat_id and fields[3] == 0]
                        self.assertEqual(1, len(video_links), (member, scope, concat_id, video_links))
                        repeat_concat_video_sources[nodes.get(video_links[0][0], {}).get("type")] += 1
                    if member.endswith("video_ltx2_3_id_lora.json") and graph.get("id") == "98ee9e5b-467b-40aa-a534-36033f27d0b4":
                        representative = (nodes, link_set)

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((0, 19, 17), (counts["LTXVEmptyLatentAudio"]["root"], counts["LTXVEmptyLatentAudio"]["subgraph"], len(files["LTXVEmptyLatentAudio"])))
        self.assertEqual((18, 1), (counts["LTXVEmptyLatentAudio"]["mode:0"], counts["LTXVEmptyLatentAudio"]["mode:4"]))
        self.assertEqual(18, widgets["LTXVEmptyLatentAudio"]["[97,25,1]"])
        self.assertEqual(1, widgets["LTXVEmptyLatentAudio"]["[121,25,1]"])
        self.assertEqual((0, 37, 19), (counts["LTXVConcatAVLatent"]["root"], counts["LTXVConcatAVLatent"]["subgraph"], len(files["LTXVConcatAVLatent"])))
        self.assertEqual((35, 2), (counts["LTXVConcatAVLatent"]["mode:0"], counts["LTXVConcatAVLatent"]["mode:4"]))
        self.assertEqual((0, 37, 19), (counts["LTXVSeparateAVLatent"]["root"], counts["LTXVSeparateAVLatent"]["subgraph"], len(files["LTXVSeparateAVLatent"])))
        self.assertEqual((35, 2), (counts["LTXVSeparateAVLatent"]["mode:0"], counts["LTXVSeparateAVLatent"]["mode:4"]))
        self.assertEqual((0, 1, 1), (counts["LTXVReferenceAudio"]["root"], counts["LTXVReferenceAudio"]["subgraph"], len(files["LTXVReferenceAudio"])))
        self.assertEqual(1, widgets["LTXVReferenceAudio"]["[3,0,1]"])

        self.assertEqual(19, outgoing[("LTXVEmptyLatentAudio", "LTXVConcatAVLatent", "LATENT")])
        self.assertEqual(35, outgoing[("LTXVConcatAVLatent", "SamplerCustomAdvanced", "LATENT")])
        self.assertEqual(2, outgoing[("LTXVConcatAVLatent", "KSampler", "LATENT")])
        self.assertEqual(35, incoming[("SamplerCustomAdvanced", "LTXVSeparateAVLatent", "LATENT")])
        self.assertEqual(2, incoming[("KSampler", "LTXVSeparateAVLatent", "LATENT")])
        self.assertEqual(21, outgoing[("LTXVSeparateAVLatent", "LTXVAudioVAEDecode", "LATENT")])
        self.assertEqual(16, outgoing[("LTXVSeparateAVLatent", "LTXVConcatAVLatent", "LATENT")])
        self.assertEqual(1, incoming[("LoraLoaderModelOnly", "LTXVReferenceAudio", "MODEL")])
        self.assertEqual(2, incoming[("CLIPTextEncode", "LTXVReferenceAudio", "CONDITIONING")])
        self.assertEqual(1, incoming[("LTXVAudioVAELoader", "LTXVReferenceAudio", "VAE")])
        self.assertEqual(1, outgoing[("LTXVReferenceAudio", "CFGGuider", "MODEL")])
        self.assertEqual(2, outgoing[("LTXVReferenceAudio", "LTXVConditioning", "CONDITIONING")])
        self.assertEqual(6, incoming_ports[("GetImageSize", "LTXVEmptyLatentAudio", "frames_number", "INT")])
        self.assertEqual(8, incoming_ports[("ComfyMathExpression", "LTXVEmptyLatentAudio", "frames_number", "INT")])
        self.assertEqual(5, incoming_ports[("PrimitiveInt", "LTXVEmptyLatentAudio", "frames_number", "INT")])
        self.assertEqual(12, incoming_ports[("PrimitiveInt", "LTXVEmptyLatentAudio", "frame_rate", "INT")])
        self.assertEqual(5, incoming_ports[("ComfyMathExpression", "LTXVEmptyLatentAudio", "frame_rate", "INT")])
        self.assertEqual(
            Counter({"LTXVImgToVideoInplace": 12, "LTXVLatentUpsampler": 4}),
            repeat_concat_video_sources,
        )

        self.assertIsNotNone(representative)
        nodes, links = representative or ({}, set())
        self.assertEqual("LTXVEmptyLatentAudio", nodes[348]["type"])
        self.assertEqual([97, 25, 1], nodes[348]["widgets_values"])
        self.assertEqual("LTXVReferenceAudio", nodes[349]["type"])
        self.assertEqual([3, 0, 1], nodes[349]["widgets_values"])
        for expected in (
            (348, 0, 326, 1, "LATENT"),
            (326, 0, 291, 4, "LATENT"),
            (291, 0, 309, 0, "LATENT"),
            (309, 1, 287, 1, "LATENT"),
            (296, 0, 287, 0, "LATENT"),
            (287, 0, 310, 4, "LATENT"),
            (310, 0, 311, 0, "LATENT"),
            (349, 0, 315, 0, "MODEL"),
            (349, 1, 307, 0, "CONDITIONING"),
            (349, 2, 307, 1, "CONDITIONING"),
        ):
            self.assertIn(expected, links)

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
        self.assertEqual([2, 4, 11, 6], report["empty"]["shape"])
        self.assertEqual("audio", report["empty"]["type"])
        self.assertEqual("audio", report["concat"]["metadataWinner"])
        self.assertTrue(report["concat"]["paddedTailMaskOnes"])
        self.assertTrue(report["concat"]["mismatchRejected"])
        self.assertTrue(report["separate"]["identityPreserved"])
        self.assertTrue(report["separate"]["extraStreamIgnored"])
        self.assertEqual([1, 16, 1], report["reference"]["vaeInputShape"])
        self.assertEqual([1, 3, 8], report["reference"]["tokenShape"])
        self.assertEqual(14.0, report["reference"]["guidedMean"])
        self.assertTrue(report["reference"]["scaleZeroKeepsTokens"])
        self.assertTrue(report["reference"]["scaleZeroBypassesExtraCall"])
        self.assertTrue(report["reference"]["outsideWindowBypassesExtraCall"])


if __name__ == "__main__":
    unittest.main()
