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
    "core.empty-ltxv-latent-video": {"dir": "empty-ltxv-latent-video", "id": "EmptyLTXVLatentVideo", "fp": "sha256:fdfe6248dd9d26006ba2e8d46f0ad53669db964e3962d55f8cc91a99d54427a2", "recipe": "recipe.ltxv-empty-image-conditioning-inplace", "docs": {"en": "855bbf9ad7938d2dd5d26c66fd2508747874785d63a9361bb48165746d776e1d", "ru": "d8d3e676003616567e38a7e71cf70d0e91958fd097f60d27dc096196890ed004"}},
    "core.ltxv-img-to-video": {"dir": "ltxv-img-to-video", "id": "LTXVImgToVideo", "fp": "sha256:36fc9a19393c59083aded1df27bd9947e67d50e01e27dc8a46182111e0c32cdb", "recipe": "recipe.ltxv-legacy-image-to-video-conditioning", "docs": {"en": "3dd98b434dff8ebf3b795bd6d994c709289c5797cbfb3fd9e323e129c9f85f80", "ru": "6d467efc0fbb4d3296d091f8d1c180586089b620f7cb3b1eb7050cf1ff80d536"}},
    "core.ltxv-img-to-video-inplace": {"dir": "ltxv-img-to-video-inplace", "id": "LTXVImgToVideoInplace", "fp": "sha256:a72c287a49555d2909eb69807fe80fedfb6d0fde6fa5f9584ea98b9d25c7d2b0", "recipe": "recipe.ltxv-empty-image-conditioning-inplace", "docs": {"en": "c456c911404c4a73c6a44191a4b7fd36880828fa621bd08588bd619b825064de", "ru": "163d4cf127ae80584cc9d5692b7e23e3ecf138b9abf7407cf8abbb8318beb68b"}},
    "core.ltxv-conditioning": {"dir": "ltxv-conditioning", "id": "LTXVConditioning", "fp": "sha256:047867640f999858426cf2161d4fa043f962898d6c96437fe1c4ed43f3d6b65f", "recipe": "recipe.ltxv-legacy-image-to-video-conditioning", "docs": {"en": "0a33f5c6ef3c1d9472554bb5f26c724e1cd5d82adb5f2b13340a1f1dfd75fd15", "ru": "ae02e5f40d05dc8b39a1af8c64a2824c27ba47d632096ab502434a5951dd8c32"}},
}
RECIPES = {"recipe.ltxv-legacy-image-to-video-conditioning": "ltxv-legacy-image-to-video-conditioning", "recipe.ltxv-empty-image-conditioning-inplace": "ltxv-empty-image-conditioning-inplace"}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOWS_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
PROBE = Path(__file__).with_name("ltxv_legacy_i2v_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["dir"] / "manifest.json"


def descriptor_type(value: Any) -> Any:
    return "COMBO" if isinstance(value, list) and value and isinstance(value[0], list) else value[0] if isinstance(value, list) and value else None


def descriptors(node: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        result.update(node.get("input", {}).get(group, {}))
    return result


def scopes(payload: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    for subgraph in (payload.get("definitions") or {}).get("subgraphs", []):
        if isinstance(subgraph, dict):
            yield "subgraph", subgraph


def fields(link: Any) -> tuple[Any, int, Any, int, Any] | None:
    if isinstance(link, list) and len(link) >= 6:
        return link[1], link[2], link[3], link[4], link[5]
    if isinstance(link, dict):
        return link.get("origin_id"), link.get("origin_slot", 0), link.get("target_id"), link.get("target_slot", 0), link.get("type")
    return None


class LtxvLegacyI2VContentTests(unittest.TestCase):
    def test_content_schemas_honesty_ten_sections_and_natural_russian(self) -> None:
        schemas = {name: catalog.load_json(catalog.CONTENT / "schemas" / filename) for name, filename in {"article": "article.schema.v1.json", "recipe": "recipe.schema.v1.json", "fragment": "recipe-fragment.schema.v1.json", "research": "article-research.schema.v1.json"}.items()}
        article_ids = {catalog.load_json(p)["articleId"] for p in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        cliche = re.compile(r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|давайте|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода|вот перевод документации", re.I)
        seen: set[str] = set()
        targets = {spec["id"] for spec in SPECS.values()}
        for p in (catalog.CONTENT / "articles").rglob("manifest.json"):
            node_id = catalog.load_json(p).get("runtimeIdentity", {}).get("classType")
            if node_id in targets:
                self.assertNotIn(node_id, seen)
                seen.add(node_id)
        for article_id, spec in SPECS.items():
            path = article_path(spec)
            manifest = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]), article_id)
            catalog.validate_article(path, manifest, errors)
            self.assertEqual(article_id, manifest["articleId"])
            self.assertEqual("draft", manifest["status"])
            self.assertEqual("in_review", manifest["editorial"]["state"])
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"])
            self.assertEqual([spec["recipe"]], [a["id"] for a in manifest["assets"]])
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.M)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("человечес" in gap.lower() for gap in ledger["knownGaps"]))
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
            self.assertIsNone(cliche.search((path.parent / "ru.md").read_text(encoding="utf-8")))
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
        empty = nodes["EmptyLTXVLatentVideo"]["input"]["required"]
        self.assertEqual((768, 512, 97, 1), tuple(empty[k][1]["default"] for k in ("width", "height", "length", "batch_size")))
        legacy = nodes["LTXVImgToVideo"]
        self.assertEqual(["CONDITIONING", "CONDITIONING", "LATENT"], legacy["output"])
        self.assertEqual(0.0, legacy["input"]["required"]["strength"][1]["min"])
        inplace = nodes["LTXVImgToVideoInplace"]["input"]["required"]
        self.assertEqual(False, inplace["bypass"][1]["default"])
        conditioning = nodes["LTXVConditioning"]["input"]["required"]["frame_rate"]
        self.assertEqual((25.0, 0.0, 1000.0, 0.01), (conditioning[1]["default"], conditioning[1]["min"], conditioning[1]["max"], conditioning[1]["step"]))
        for recipe_id, directory in RECIPES.items():
            fragment = catalog.load_json(catalog.CONTENT / "recipes" / directory / "fragment.json")
            by_ref = {n["ref"]: n for n in fragment["nodes"]}
            supplied = {ref: set(n["settings"]) for ref, n in by_ref.items()}
            for ext in fragment["externalInputs"]:
                target = by_ref[ext["to"]]
                self.assertEqual(ext["type"], descriptor_type(descriptors(nodes[target["classType"]])[ext["input"]]))
                supplied[ext["to"]].add(ext["input"])
            for conn in fragment["connections"]:
                source = nodes[by_ref[conn["from"]]["classType"]]
                target = nodes[by_ref[conn["to"]]["classType"]]
                self.assertEqual(source["output"][source["output_name"].index(conn["output"])], descriptor_type(descriptors(target)[conn["input"]]))
                supplied[conn["to"]].add(conn["input"])
            for ref, record in by_ref.items():
                required = set(nodes[record["classType"]]["input"].get("required", {}))
                self.assertTrue(required <= supplied[ref], (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_pinned_source_and_replacement_contracts(self) -> None:
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        helpers = (SOURCE / "node_helpers.py").read_text(encoding="utf-8")
        for snippet in ("[batch_size, 128, ((length - 1) // 8) + 1, height // 32, width // 32]", '"downscale_ratio_spacial": 32', 'encode_pixels = pixels[:, :, :, :3]', 'conditioning_latent_frames_mask[:, :, :t.shape[2]] = 1.0 - strength', "if bypass:", "samples = latent[\"samples\"].clone()", "conditioning_latent_frames_mask = get_noise_mask(latent)", 'conditioning_set_values(positive, {"frame_rate": frame_rate})'):
            self.assertIn(snippet, source)
        self.assertIn("n = [t[0], t[1].copy()]", helpers)
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
                    self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
                    texts[(spec["id"], locale)] = raw.decode("utf-8")
        self.assertIn("extends it into a sequence", texts[("LTXVImgToVideo", "en")])
        self.assertIn("blending strength", texts[("LTXVImgToVideoInplace", "en")])
        self.assertIn("frame rate information", texts[("LTXVConditioning", "en")])

    @unittest.skipUnless(WORKFLOWS.exists(), "pinned workflows absent")
    def test_exhaustive_workflow_census_and_exact_topology(self) -> None:
        self.assertEqual(WORKFLOWS_SHA, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {s["id"] for s in SPECS.values()}
        counts = {t: Counter() for t in targets}; fileset = {t: set() for t in targets}; widgets = {t: Counter() for t in targets}; incoming = Counter(); outgoing = Counter(); root_sampler_links = Counter(); json_count = roots = subgraphs = 0
        legacy_graph = None; inplace_graph = None
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for name in sorted(n for n in archive.namelist() if "/templates/" in n and n.endswith(".json")):
                json_count += 1; payload = json.loads(archive.read(name))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list): roots += 1
                if isinstance(payload, dict):
                    subgraphs += sum(isinstance(s, dict) for s in (payload.get("definitions") or {}).get("subgraphs", []))
                for scope, graph in scopes(payload):
                    by = {n.get("id"): n for n in graph.get("nodes", []) if isinstance(n, dict)}; links = set()
                    for n in by.values():
                        node_id = n.get("type")
                        if node_id in targets:
                            counts[node_id][scope] += 1; counts[node_id][f"mode:{n.get('mode', 0)}"] += 1; fileset[node_id].add(name); widgets[node_id][json.dumps(n.get("widgets_values", []), separators=(",", ":"))] += 1
                    for link in graph.get("links", []):
                        f = fields(link)
                        if f is None: continue
                        links.add(f); oid, _, tid, _, typ = f; st = by.get(oid, {}).get("type"); tt = by.get(tid, {}).get("type")
                        if st in targets:
                            outgoing[(st, tt, typ)] += 1
                            if st == "LTXVConditioning" and tt == "SamplerCustom" and scope == "root":
                                root_sampler_links[name.rsplit("/", 1)[-1]] += 1
                        if tt in targets: incoming[(st, tt, typ)] += 1
                    if name.endswith("ltxv_image_to_video.json") and scope == "root": legacy_graph = (by, links)
                    if name.endswith("video_ltx2_3_i2v.json") and graph.get("id") == "2454ad83-157c-40dd-9f19-5daaf4041ce0": inplace_graph = (by, links)
        self.assertEqual((512, 496, 272), (json_count, roots, subgraphs))
        self.assertEqual((1, 21, 20), (counts["EmptyLTXVLatentVideo"]["root"], counts["EmptyLTXVLatentVideo"]["subgraph"], len(fileset["EmptyLTXVLatentVideo"])))
        self.assertEqual(21, widgets["EmptyLTXVLatentVideo"]["[768,512,97,1]"])
        self.assertEqual((1, 0, 1), (counts["LTXVImgToVideo"]["root"], counts["LTXVImgToVideo"]["subgraph"], len(fileset["LTXVImgToVideo"])))
        self.assertEqual(1, widgets["LTXVImgToVideo"]["[768,512,97,1,0.15]"])
        self.assertEqual((0, 27, 13), (counts["LTXVImgToVideoInplace"]["root"], counts["LTXVImgToVideoInplace"]["subgraph"], len(fileset["LTXVImgToVideoInplace"])))
        self.assertEqual(Counter({"[1,false]": 20, "[0.7,false]": 6, "[1,true]": 1}), widgets["LTXVImgToVideoInplace"])
        self.assertEqual((2, 21, 21), (counts["LTXVConditioning"]["root"], counts["LTXVConditioning"]["subgraph"], len(fileset["LTXVConditioning"])))
        self.assertEqual(Counter({"[25]": 16, "[24]": 7}), widgets["LTXVConditioning"])
        self.assertEqual(15, incoming[("EmptyLTXVLatentVideo", "LTXVImgToVideoInplace", "LATENT")]); self.assertEqual(12, incoming[("LTXVLatentUpsampler", "LTXVImgToVideoInplace", "LATENT")]); self.assertEqual(21, outgoing[("LTXVImgToVideoInplace", "LTXVConcatAVLatent", "LATENT")])
        self.assertEqual(39, incoming[("CLIPTextEncode", "LTXVConditioning", "CONDITIONING")]); self.assertEqual(22, outgoing[("LTXVConditioning", "CFGGuider", "CONDITIONING")])
        self.assertEqual(2, incoming[("LTXVImgToVideo", "LTXVConditioning", "CONDITIONING")])
        self.assertEqual(2, incoming[("LTXVReferenceAudio", "LTXVConditioning", "CONDITIONING")])
        self.assertEqual(Counter({"ltxv_image_to_video.json": 2, "ltxv_text_to_video.json": 2}), root_sampler_links)
        self.assertIsNotNone(legacy_graph); by, links = legacy_graph or ({}, set()); self.assertEqual([768, 512, 97, 1, 0.15], by[77]["widgets_values"]); self.assertEqual([25], by[69]["widgets_values"])
        for expected in ((77, 0, 69, 0, "CONDITIONING"), (77, 1, 69, 1, "CONDITIONING"), (77, 2, 71, 0, "LATENT"), (77, 2, 72, 5, "LATENT")): self.assertIn(expected, links)
        self.assertIsNotNone(inplace_graph); by, links = inplace_graph or ({}, set()); self.assertEqual([768, 512, 97, 1], by[295]["widgets_values"]); self.assertEqual([0.7, False], by[296]["widgets_values"]); self.assertEqual([1, False], by[288]["widgets_values"])
        self.assertIn((295, 0, 296, 2, "LATENT"), links); self.assertIn((287, 0, 288, 2, "LATENT"), links)

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_exact_class_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        executable = next((p for p in candidates if p.is_file()), None); self.assertIsNotNone(executable)
        result = subprocess.run([str(executable), "-X", "utf8", str(PROBE), str(SOURCE)], cwd=catalog.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([1, 128, 13, 16, 24], report["empty"]["shape"]); self.assertEqual(32, report["empty"]["ratio"])
        self.assertEqual([2, 128, 2, 2, 2], report["legacy"]["shape"]); self.assertTrue(report["legacy"]["conditioningIdentity"]); self.assertEqual((0.0, 1.0), (report["legacy"]["strengthOneMask"], report["legacy"]["strengthZeroMask"]))
        self.assertTrue(report["inplace"]["inputUnchanged"]); self.assertTrue(report["inplace"]["metadataDiscarded"]); self.assertTrue(report["inplace"]["bypassIdentity"])
        self.assertTrue(report["conditioning"]["tensorIdentity"]); self.assertTrue(report["conditioning"]["metadataCopied"]); self.assertTrue(report["conditioning"]["nestedShared"])


if __name__ == "__main__":
    unittest.main()
