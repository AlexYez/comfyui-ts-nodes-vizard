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


SPECS: dict[str, dict[str, Any]] = {
    "core.get-ic-lora-parameters": {"dir": "get-ic-lora-parameters", "id": "GetICLoRAParameters", "fp": "sha256:2842585e74ef274d9f867b5a7eea2bce4e052dab9ff97a4e729a82e3f25096b4", "recipes": ["recipe.ltxv-iclora-guide-parameters"], "docs": {"en": "9d3c47384314d6c23b1d782689fd58930152641c45c2bb8a9168b17911fa52db", "ru": "bb4c9f1f178615489374e7afeb88434894c258c80a6d6fca68a25f1875a1a9b2"}},
    "core.ltxv-add-guide": {"dir": "ltxv-add-guide", "id": "LTXVAddGuide", "fp": "sha256:3c478070c2ad282646d3e923fc8ecbbe8196d3a68601421f99d2a612129885d1", "recipes": ["recipe.ltxv-two-guide-style-transition", "recipe.ltxv-iclora-guide-parameters"], "docs": {"en": "fc973c571d5fbc74b1f986c6ff1486c89e2672aa250d51ce174a929f07e31b91", "ru": "6f5ebd93ad58b117d4f66262735b8c646f07fb3a45c81d393110c42c2da3542a"}},
    "core.ltxv-crop-guides": {"dir": "ltxv-crop-guides", "id": "LTXVCropGuides", "fp": "sha256:1b85c22c9ca23991f9fce46cff2ffee32e993ec36633c84dd2e95b62b2b46ee0", "recipes": ["recipe.ltxv-crop-guides-after-sampling"], "docs": {"en": "395edf49ad01901b870c3d4a20764f9c8b44c883343286c3c4471cf1c6cc23e0", "ru": "a4eda6717878431a3bbd1090312f2b0ef035cf2b187a4320ab07620106ae25f4"}},
    "core.ltxv-preprocess": {"dir": "ltxv-preprocess", "id": "LTXVPreprocess", "fp": "sha256:0343134bdc3eb505b9b6fe3e4cef2808a3e8fb8c04e5e046eb86f80773ae2606", "recipes": ["recipe.ltxv-two-guide-style-transition"], "docs": {"en": "314821da016a354d5b8f67936bab36f87692ab860530f20b6cf11a80b3dec69e", "ru": "feba942d20a6d6130f380c639223e648eb1364ec2676950068a3621708af3ac9"}},
}
RECIPES = {
    "recipe.ltxv-iclora-guide-parameters": "ltxv-iclora-guide-parameters",
    "recipe.ltxv-two-guide-style-transition": "ltxv-two-guide-style-transition",
    "recipe.ltxv-crop-guides-after-sampling": "ltxv-crop-guides-after-sampling",
}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOWS_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
PROBE = Path(__file__).with_name("ltxv_guide_preprocess_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["dir"] / "manifest.json"


def descriptor_type(value: Any) -> Any:
    return "COMBO" if isinstance(value, list) and value and isinstance(value[0], list) else value[0] if isinstance(value, list) and value else None


def descriptors(node: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        result.update(node.get("input", {}).get(group, {}))
    return result


def graph_scopes(payload: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
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
        return link.get("origin_id"), link.get("origin_slot", 0), link.get("target_id"), link.get("target_slot", 0), link.get("type")
    return None


class LtxvGuidePreprocessContentTests(unittest.TestCase):
    def test_content_schemas_honesty_ten_sections_and_natural_russian(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / filename) for name, filename in {"article": "article.schema.v1.json", "recipe": "recipe.schema.v1.json", "fragment": "recipe-fragment.schema.v1.json", "research": "article-research.schema.v1.json"}.items()}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        cliche = re.compile(r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|\bдавайте\b|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода|вот перевод документации", re.I)
        targets = {spec["id"] for spec in SPECS.values()}
        occurrences = Counter()
        for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
            class_type = catalog.load_json(path).get("runtimeIdentity", {}).get("classType")
            if class_type in targets:
                occurrences[class_type] += 1
        self.assertEqual(Counter({target: 1 for target in targets}), occurrences)

        for article_id, spec in SPECS.items():
            path = article_path(spec)
            manifest = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]), article_id)
            catalog.validate_article(path, manifest, errors)
            self.assertEqual(article_id, manifest["articleId"])
            self.assertEqual("draft", manifest["status"])
            self.assertEqual("in_review", manifest["editorial"]["state"])
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"])
            self.assertEqual(spec["recipes"], [asset["id"] for asset in manifest["assets"]])
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.M)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человечес" in gap.lower() or "human" in gap.lower() for gap in ledger["knownGaps"]))

        for recipe_id, directory in RECIPES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertIsNone(cliche.search((path.parent / "ru.md").read_text(encoding="utf-8")), recipe_id)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            node = nodes[spec["id"]]
            self.assertEqual("comfy_extras.nodes_lt", node["python_module"])
            self.assertFalse(node["experimental"])
            self.assertFalse(node["deprecated"])
            self.assertFalse(node["dev_only"])
            self.assertFalse(node["api_node"])
            self.assertEqual(spec["fp"], catalog.schema_fingerprint(spec["id"], node), article_id)
            self.assertEqual(spec["fp"], catalog.load_json(article_path(spec))["editorial"]["schemaHash"])

        self.assertEqual(["IC_LORA_PARAMETERS"], nodes["GetICLoRAParameters"]["output"])
        guide = nodes["LTXVAddGuide"]
        self.assertEqual(["CONDITIONING", "CONDITIONING", "LATENT"], guide["output"])
        self.assertEqual((0, 1.0, 10.0), (guide["input"]["required"]["frame_idx"][1]["default"], guide["input"]["required"]["strength"][1]["default"], guide["input"]["required"]["strength"][1]["max"]))
        self.assertEqual({"attention_mask", "iclora_parameters"}, set(guide["input"]["optional"]))
        self.assertEqual([], list(nodes["LTXVCropGuides"]["input"].get("optional", {})))
        compression = nodes["LTXVPreprocess"]["input"]["required"]["img_compression"][1]
        self.assertEqual((35, 0, 100), (compression["default"], compression["min"], compression["max"]))

        for recipe_id, directory in RECIPES.items():
            fragment = catalog.load_json(catalog.CONTENT / "recipes" / directory / "fragment.json")
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                target = by_ref[external["to"]]
                self.assertEqual(external["type"], descriptor_type(descriptors(nodes[target["classType"]])[external["input"]]))
                supplied[external["to"]].add(external["input"])
            for connection in fragment["connections"]:
                source = nodes[by_ref[connection["from"]]["classType"]]
                target = nodes[by_ref[connection["to"]]["classType"]]
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], descriptor_type(descriptors(target)[connection["input"]]))
                supplied[connection["to"]].add(connection["input"])
            for ref, record in by_ref.items():
                required = set(nodes[record["classType"]]["input"].get("required", {}))
                self.assertTrue(required <= supplied[ref], (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_pinned_source_and_replacement_contracts(self) -> None:
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        sd_source = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        for snippet in (
            'metadata = iclora_model.get_attachment("lora_metadata")',
            'if k.endswith("reference_downscale_factor")',
            "images = images[:(images.shape[0] - 1) // time_scale_factor * time_scale_factor + 1]",
            "if guide_length > 1 and frame_idx != 0:",
            'raise ValueError("Adding guide to a combined AV latent is not supported.")',
            "latent_image = torch.cat([latent_image, guiding_latent], dim=2)",
            '"guide_attention_entries": entries',
            "latent_image = latent_image[:, :, :-num_keyframes]",
            '"keyframe_idxs": None',
            'container.add_stream(',
            '"libx264", rate=1, options={"crf": str(crf), "preset": "veryfast"}',
            "image[:(image.shape[0] // 2) * 2, :(image.shape[1] // 2) * 2]",
        ):
            self.assertIn(snippet, source)
        self.assertIn('new_modelpatcher.set_attachments("lora_metadata", lora_metadata)', sd_source)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in SPECS.values():
            self.assertNotIn(spec["id"], replacements)

    @unittest.skipUnless(DOCS.exists(), "pinned docs absent")
    def test_pinned_docs_hashes_and_discrepancies(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        texts: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(DOCS) as archive:
            for spec in SPECS.values():
                for locale, digest in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['id']}/{locale}.md"
                    raw = archive.read(name)
                    self.assertEqual(digest, hashlib.sha256(raw).hexdigest(), name)
                    texts[(spec["id"], locale)] = raw.decode("utf-8")
        self.assertIn("safetensors metadata", texts[("GetICLoRAParameters", "en")])
        self.assertIn("0.0 to 10.0", texts[("LTXVAddGuide", "en")])
        self.assertIn("от 0.0 до 1.0", texts[("LTXVAddGuide", "ru")])
        self.assertNotIn("attention_mask", texts[("LTXVAddGuide", "ru")])
        self.assertIn("keyframe indices", texts[("LTXVCropGuides", "en")])
        self.assertIn("single-frame MP4", texts[("LTXVPreprocess", "en")])

    @unittest.skipUnless(WORKFLOWS.exists(), "pinned workflows absent")
    def test_exhaustive_workflow_census_and_exact_topology(self) -> None:
        self.assertEqual(WORKFLOWS_SHA, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec["id"] for spec in SPECS.values()}
        counts = {target: Counter() for target in targets}
        files = {target: set() for target in targets}
        widgets = {target: Counter() for target in targets}
        style_graph = None
        style_graph_25 = None
        iclora_graph = None
        json_count = root_count = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")):
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    root_count += 1
                if isinstance(payload, dict) and isinstance(payload.get("definitions"), dict):
                    subgraph_count += sum(isinstance(item, dict) for item in payload["definitions"].get("subgraphs", []))
                for scope, graph in graph_scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    links = {fields for link in graph.get("links", []) if (fields := link_fields(link)) is not None}
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            files[node_type].add(member)
                            widgets[node_type][json.dumps(node.get("widgets_values", []), separators=(",", ":"))] += 1
                    if member.endswith("video_ltx2_3_flf2v.json") and graph.get("id") == "f9f61b10-b689-4d67-b4fa-0acc1d9b5390":
                        style_graph = nodes, links
                    if member.endswith("video_ltx2_5_flf2v.json") and graph.get("id") == "cf70afc4-5a03-47ce-8210-734b1de6c6bc":
                        style_graph_25 = nodes, links
                    if member.endswith("video_ltx2_3_ic_lora.json") and graph.get("id") == "f9f61b10-b689-4d67-b4fa-0acc1d9b5390":
                        iclora_graph = nodes, links

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual((0, 2, 2), (counts["GetICLoRAParameters"]["root"], counts["GetICLoRAParameters"]["subgraph"], len(files["GetICLoRAParameters"])))
        self.assertEqual(2, widgets["GetICLoRAParameters"]["[]"])
        self.assertEqual((0, 12, 7), (counts["LTXVAddGuide"]["root"], counts["LTXVAddGuide"]["subgraph"], len(files["LTXVAddGuide"])))
        self.assertEqual((11, 1), (counts["LTXVAddGuide"]["mode:0"], counts["LTXVAddGuide"]["mode:4"]))
        self.assertEqual(Counter({"[0,1]": 6, "[-1,0.7]": 3, "[0,0.7]": 3}), widgets["LTXVAddGuide"])
        self.assertEqual((0, 18, 16), (counts["LTXVCropGuides"]["root"], counts["LTXVCropGuides"]["subgraph"], len(files["LTXVCropGuides"])))
        self.assertEqual((17, 1), (counts["LTXVCropGuides"]["mode:0"], counts["LTXVCropGuides"]["mode:4"]))
        self.assertEqual((0, 15, 12), (counts["LTXVPreprocess"]["root"], counts["LTXVPreprocess"]["subgraph"], len(files["LTXVPreprocess"])))
        self.assertEqual(Counter({"[18]": 8, "[25]": 4, "[33]": 3}), widgets["LTXVPreprocess"])

        self.assertIsNotNone(style_graph)
        nodes, links = style_graph or ({}, set())
        self.assertEqual([25], nodes[104]["widgets_values"])
        self.assertEqual([25], nodes[99]["widgets_values"])
        self.assertEqual([0, 0.7], nodes[115]["widgets_values"])
        self.assertEqual([-1, 0.7], nodes[111]["widgets_values"])
        for expected in ((104, 0, 115, 4, "IMAGE"), (115, 0, 111, 0, "CONDITIONING"), (115, 1, 111, 1, "CONDITIONING"), (115, 2, 111, 3, "LATENT"), (99, 0, 111, 4, "IMAGE"), (111, 0, 106, 0, "CONDITIONING"), (111, 1, 106, 1, "CONDITIONING"), (121, 0, 106, 2, "LATENT")):
            self.assertIn(expected, links)

        self.assertIsNotNone(style_graph_25)
        nodes, links = style_graph_25 or ({}, set())
        self.assertEqual([18], nodes[195]["widgets_values"])
        self.assertEqual([18], nodes[199]["widgets_values"])
        self.assertEqual([0, 0.7], nodes[206]["widgets_values"])
        self.assertEqual([-1, 0.7], nodes[204]["widgets_values"])

        self.assertIsNotNone(iclora_graph)
        nodes, links = iclora_graph or ({}, set())
        self.assertEqual("LoraLoaderModelOnly", nodes[195]["type"])
        self.assertEqual("GetICLoRAParameters", nodes[196]["type"])
        self.assertEqual([0, 1], nodes[115]["widgets_values"])
        self.assertIn((195, 0, 196, 0, "MODEL"), links)
        self.assertIn((196, 0, 115, 6, "IC_LORA_PARAMETERS"), links)

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_model_independent_exact_class_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        executable = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(executable)
        result = subprocess.run([str(executable), "-X", "utf8", str(PROBE), str(SOURCE)], cwd=catalog.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual({"fallback": 1, "overflow": True, "roundEven": 2, "roundUp": 3}, report["metadata"])
        self.assertEqual([1, 128, 4, 2, 2], report["guide"]["shape"])
        self.assertEqual([9, 2], report["guide"]["aligned"])
        self.assertTrue(report["guide"]["channelError"])
        self.assertEqual([9, 64, 64, 3], report["guide"]["noncausalVaeInput"])
        self.assertAlmostEqual(0.7, report["guide"]["noncausalLastOriginal"], places=6)
        self.assertEqual([1, 128, 3, 2, 2], report["crop"]["shape"])
        self.assertTrue(report["crop"]["plainMetadataDropped"])
        self.assertTrue(report["preprocess"]["zeroEqual"])
        self.assertTrue(report["preprocess"]["newBatch"])
        self.assertEqual([8, 10, 3], report["preprocess"]["rgbShape"])
        self.assertTrue(report["preprocess"]["rgbaError"])


if __name__ == "__main__":
    unittest.main()
