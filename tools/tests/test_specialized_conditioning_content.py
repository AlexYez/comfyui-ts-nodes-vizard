from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter
from typing import Any, Iterator

import torch

from tools import catalog


SPECS = {
    "core.clip-text-encode-controlnet": ("clip-text-encode-controlnet", "CLIPTextEncodeControlnet", "sha256:7e1bd95b97cb5d211955b2d7c11470e82023423be95ea753f818934023c01db2", "controlnet-specific-text"),
    "core.t5-tokenizer-options": ("t5-tokenizer-options", "T5TokenizerOptions", "sha256:6d52935980cfa05e2dc88975b0c594e29fc7956cfec12ece81fdc6dacc31044e", "t5-tokenizer-minimums"),
    "core.flux-kontext-multi-reference-latent-method": ("flux-kontext-multi-reference-latent-method", "FluxKontextMultiReferenceLatentMethod", "sha256:ba3955ddab60c0a90bdf9cf9c7c5ac2745fea1d802627b8008362e12ba9fa5aa", "flux-kontext-index-timestep-zero"),
    "core.photomaker-encode": ("photomaker-encode", "PhotoMakerEncode", "sha256:c3896d942a3a476039cbb754ec8155de1e2cd479dadd4b0dc479e4b18bcf7f32", "encode-photomaker-reference"),
}
ROOT = catalog.ROOT
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = ROOT / ".comfyui-source-0.32.0"
DOCS = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def scopes(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if isinstance(payload.get("nodes"), list):
        yield payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                yield subgraph


class SpecializedConditioningContentTests(unittest.TestCase):
    def test_content_contracts_honesty_and_language(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / name) for name in (
            "article.schema.v1.json", "recipe.schema.v1.json", "recipe-fragment.schema.v1.json", "article-research.schema.v1.json"
        )}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        for article_id, (directory, _class_type, _fingerprint, recipe_id) in SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article.schema.v1.json"]), article_id)
            catalog.validate_article(path, article, errors)
            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertEqual(10, len(re.findall(r"^## ", body, re.MULTILINE)))
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["article-research.schema.v1.json"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человеческое" in gap.casefold() for gap in ledger["knownGaps"]))
            recipe_path = catalog.CONTENT / "recipes" / recipe_id / "recipe.json"
            recipe = catalog.load_json(recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe.schema.v1.json"]), recipe_id)
            catalog.validate_recipe(recipe_path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["recipe-fragment.schema.v1.json"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            prose = re.sub(r"`[^`]+`|https?://\S+", "", body + "\n" + (recipe_path.parent / recipe["body"]).read_text(encoding="utf-8")).casefold()
            for phrase in ("official workflow", "source-derived", "full model", "runtime-контракт"):
                self.assertNotIn(phrase, prose, recipe_id)
        self.assertEqual([], errors)

    def test_runtime_identity_constraints_and_no_replacements(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        expected_modules = {
            "CLIPTextEncodeControlnet": "comfy_extras.nodes_cond",
            "T5TokenizerOptions": "comfy_extras.nodes_cond",
            "FluxKontextMultiReferenceLatentMethod": "comfy_extras.nodes_flux",
            "PhotoMakerEncode": "comfy_extras.nodes_photomaker",
        }
        for article_id, (directory, class_type, fingerprint, _recipe_id) in SPECS.items():
            runtime = nodes[class_type]
            article = catalog.load_json(catalog.CONTENT / "articles" / "core" / directory / "manifest.json")
            self.assertEqual(expected_modules[class_type], runtime["python_module"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, runtime), article_id)
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertTrue(runtime.get("experimental", False))
            self.assertFalse(runtime.get("api_node", False))
            self.assertFalse(runtime.get("deprecated", False))
        self.assertEqual(["offset", "index", "uxo/uno", "index_timestep_zero"], nodes["FluxKontextMultiReferenceLatentMethod"]["input"]["required"]["reference_latents_method"][1]["options"])
        self.assertEqual((0, 10000, 0), tuple(nodes["T5TokenizerOptions"]["input"]["required"]["min_padding"][1][key] for key in ("min", "max", "default")))
        replacements = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacements)

    def test_pinned_sources_and_model_free_semantics(self) -> None:
        paths = {
            "cond": (SOURCE / "comfy_extras" / "nodes_cond.py", "fb4c9abaaeaa96633344a3f30830fe1a2a7cb72b1d1a1bbc020cb30e566b6806"),
            "flux": (SOURCE / "comfy_extras" / "nodes_flux.py", "a4917fd9d4aed2afdbdfc005a527b6381be942200054d7998477a16987e7aff9"),
            "photo": (SOURCE / "comfy_extras" / "nodes_photomaker.py", "16241bf82c5cfcf0d2684cc6819392f6b9e8aff334560c233647db69dd15bacc"),
        }
        text = {}
        for key, (path, digest) in paths.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            text[key] = path.read_text(encoding="utf-8")
        for marker in ("cross_attn_controlnet", "pooled_output_controlnet", 'for t5_type in ["t5xxl", "pile_t5xl", "t5base", "mt5xl", "umt5xxl"]'):
            self.assertIn(marker, text["cond"])
        self.assertIn('if "uxo" in reference_latents_method or "uso" in reference_latents_method', text["flux"])
        for marker in ('special_token = "photomaker"', 'text.split(" ").index(special_token) + 1', "range(77)"):
            self.assertIn(marker, text["photo"])

        original = [[torch.tensor([1.0]), {"pooled_output": "base", "keep": 7}]]
        encoded = torch.tensor([2.0]); pooled = torch.tensor([3.0])
        copied = [[item[0], item[1].copy()] for item in original]
        copied[0][1]["cross_attn_controlnet"] = encoded
        copied[0][1]["pooled_output_controlnet"] = pooled
        self.assertEqual({"pooled_output": "base", "keep": 7}, original[0][1])
        self.assertIs(original[0][0], copied[0][0])
        self.assertIs(encoded, copied[0][1]["cross_attn_controlnet"])

        options = {}
        for t5_type in ["t5xxl", "pile_t5xl", "t5base", "mt5xl", "umt5xxl"]:
            options[f"{t5_type}_min_padding"] = 8
            options[f"{t5_type}_min_length"] = 32
        self.assertEqual(10, len(options))
        self.assertEqual("uxo", "uxo" if "uxo" in "uxo/uno" or "uso" in "uxo/uno" else "uxo/uno")

        self.assertEqual(3, "photograph of photomaker studio portrait".split(" ").index("photomaker") + 1)
        with self.assertRaises(ValueError):
            "photograph of photomaker, studio portrait".split(" ").index("photomaker")

    def test_docs_and_exhaustive_workflow_census(self) -> None:
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        doc_hashes = {
            "CLIPTextEncodeControlnet": ("96683030bfa62ee6543bc9f54d12ff7c5ebb2a288497eea50232d2bef9050637", "31d75ccfcc3612357040457f82c25d4ae6b0ea2d617970dc5e00074b8f4b6371"),
            "T5TokenizerOptions": ("d807020fb150e882973608c34fe0aa467a423f3918f7b104ccc53c80724e07f2", "eaf7b396b8325da39898cbd740195dff89539b2416b7eea0d52c1b3828fc5b1a"),
            "FluxKontextMultiReferenceLatentMethod": ("60419a619d7f274eecc823e9a66bff6cc790c5b45cb43f0c043a32bdb1533c86", "90e67947673c9e91a7639bca511bda73f0417757e50914cdef714091c1a26b1a"),
            "PhotoMakerEncode": ("cc2c6c42bfe45eb80fb44494560a8407979665f77a9c52a3ec19929ad102e191", "f3c1f2197c787a9a916767dc08519218d563229d41b0227cdeb4bdd612022c4f"),
        }
        with zipfile.ZipFile(DOCS) as archive:
            for class_type, hashes in doc_hashes.items():
                for locale, digest in zip(("en", "ru"), hashes):
                    self.assertEqual(digest, hashlib.sha256(archive.read(f"comfyui_embedded_docs/docs/{class_type}/{locale}.md")).hexdigest())

        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}; counts: Counter[str] = Counter(); widgets: dict[str, Counter[str]] = {target: Counter() for target in targets}
        json_count = root_count = subgraph_count = node_count = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in archive.namelist():
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                graphs = list(scopes(payload)) if isinstance(payload, dict) else []
                has_root = isinstance(payload, dict) and isinstance(payload.get("nodes"), list)
                root_count += int(has_root); subgraph_count += len(graphs) - int(has_root)
                for graph in graphs:
                    for node in graph.get("nodes", []):
                        node_count += 1
                        if isinstance(node, dict) and node.get("type") in targets:
                            class_type = node["type"]; counts[class_type] += 1; widgets[class_type][repr(node.get("widgets_values"))] += 1
        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"FluxKontextMultiReferenceLatentMethod": 30, "T5TokenizerOptions": 2}), counts)
        self.assertEqual(Counter({"['index_timestep_zero']": 27, "['index']": 2, "['uxo/uno']": 1}), widgets["FluxKontextMultiReferenceLatentMethod"])
        self.assertEqual(Counter({"[0, 0]": 2}), widgets["T5TokenizerOptions"])


if __name__ == "__main__":
    unittest.main()
