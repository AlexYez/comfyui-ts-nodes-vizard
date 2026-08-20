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


SPECS = {
    "core.vae-decode-tiled": {"dir": "vae-decode-tiled", "id": "VAEDecodeTiled", "module": "nodes", "fp": "sha256:7329f213504db6c8ace2e8a7d99f98cc7e3b783b72ad538c85c317f9f8f4cb6e", "recipe": "recipe.tiled-vae-seedvr2-pass", "docs": {"en": "749b3b82e3425283134d6aa1cce341ffea1ceecb4dd3fd92eb34010d35f3b6ca", "ru": "7e0f527ce93121428106e684c4e922cc92df6c158ab062ee47715b178417dceb"}},
    "core.vae-encode-tiled": {"dir": "vae-encode-tiled", "id": "VAEEncodeTiled", "module": "nodes", "fp": "sha256:86bbadf518055387f7f3e45514c7601ab152dea738f3b59153603b39adf111c3", "recipe": "recipe.tiled-vae-seedvr2-pass", "docs": {"en": "ac87525f0442a87d3a54d332bbcb4c761f09f5b237df69ff85bffcc99d8f7969", "ru": "7b3b23601627a2cecfe1cd173b8cfe072d1fa417c978a11208c7be62a7078d37"}},
    "core.tome-patch-model": {"dir": "tome-patch-model", "id": "TomePatchModel", "module": "comfy_extras.nodes_tomesd", "fp": "sha256:69fe3af3881816d1cb6b2214cdc5e7503f1fb3ade33fa9284dcd76ce29fe832f", "recipe": "recipe.tome-token-merge-30", "docs": {"en": "b299d2940e23aacb6535b44edf03f07cf583fcd7b4cfbb2da032adc328c03f14", "ru": "c7b9543ac1112d85f7cc004121aad5a595cd98fcdd4a488ad58f85204fa08aec"}},
    "core.patch-model-add-downscale": {"dir": "patch-model-add-downscale", "id": "PatchModelAddDownscale", "module": "comfy_extras.nodes_model_downscale", "fp": "sha256:3b748617303d967a7dd14a8c9403b2551465e9e0ef13247edfc0afed02eae9d2", "recipe": "recipe.kohya-deep-shrink-window", "docs": {"en": "43c2c403df710b6e4066c7b08bbf9ef34ebc7dc333f376c36afe0e62be5797a9", "ru": "052e55d54eb2831116ac0506dbddabdf38f2a786c893b6f620cc471bd851656f"}},
}
RECIPES = {
    "recipe.tiled-vae-seedvr2-pass": "tiled-vae-seedvr2-pass",
    "recipe.tome-token-merge-30": "tome-token-merge-30",
    "recipe.kohya-deep-shrink-window": "kohya-deep-shrink-window",
}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SD_SHA = "51e72a263e8bd77812aefcebcf3cfaf9fda57150d763897b6d8b4890d7fee207"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOWS_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
PROBE = Path(__file__).with_name("vae_tiled_model_patch_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["dir"] / "manifest.json"


def descriptors(node: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        result.update(node.get("input", {}).get(group, {}))
    return result


def descriptor_type(value: Any) -> Any:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return "COMBO"
    return value[0] if isinstance(value, list) and value else None


def graph_scopes(payload: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for graph in definitions.get("subgraphs", []):
            if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
                yield "subgraph", graph


def link_fields(link: Any) -> tuple[Any, int, Any, int, Any] | None:
    if isinstance(link, list) and len(link) >= 6:
        return link[1], link[2], link[3], link[4], link[5]
    if isinstance(link, dict):
        return link.get("origin_id"), link.get("origin_slot", 0), link.get("target_id"), link.get("target_slot", 0), link.get("type")
    return None


class VAETiledModelPatchContentTests(unittest.TestCase):
    def test_content_schemas_honesty_ten_sections_and_natural_russian(self) -> None:
        schema_names = {"article": "article.schema.v1.json", "recipe": "recipe.schema.v1.json", "fragment": "recipe-fragment.schema.v1.json", "research": "article-research.schema.v1.json"}
        schemas = {key: catalog.load_json(catalog.CONTENT / "schemas" / value) for key, value in schema_names.items()}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        runtime_collisions = Counter(catalog.load_json(path).get("runtimeIdentity", {}).get("classType") for path in (catalog.CONTENT / "articles").rglob("manifest.json"))
        errors: list[str] = []
        cliche = re.compile(r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|\bдавайте\b|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода|вот перевод документации", re.I)
        stray_english = re.compile(r"\b(?:official|exact|source-derived|pinned|workflow|workflows|template|templates|root|subgraph|census|frontend|runtime|fingerprint|experimental|deprecated|active|formal|replacement|image|video|tiled|encode|decode|sample|sampling|sampler|checkpoint|loader|prompt|scheduler|latent|conditioning|backend|attention|query|key|value|source|destination|lossy|metric|stride|scatter|identity|downsample|input|output|block|blocks|skip|hook|hooks|feature|map|resize|factor|default|combo|wall-clock|memory|profile|batch|preprocessing|postprocessing)\b", re.I)

        def prose_only(text: str) -> str:
            without_code = re.sub(r"`[^`\n]*`", "", text)
            without_links = re.sub(r"\]\([^)]*\)", "]", without_code)
            return re.sub(r"\b(?:LATENT|IMAGE|MODEL|CONDITIONING|VAE)\b", "", without_links)

        article_bodies: dict[str, str] = {}
        for article_id, spec in SPECS.items():
            path = article_path(spec)
            manifest = catalog.load_json(path)
            self.assertEqual(1, runtime_collisions[spec["id"]], spec["id"])
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]), article_id)
            catalog.validate_article(path, manifest, errors)
            self.assertEqual("draft", manifest["status"])
            self.assertEqual("in_review", manifest["editorial"]["state"])
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"])
            self.assertEqual(spec["recipe"], manifest["assets"][0]["id"])
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            article_bodies[article_id] = body
            self.assertEqual(10, len(re.findall(r"^## ", body, re.M)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            for label, text in (("title", manifest["title"]), ("summary", manifest["summary"]), ("body", body)):
                self.assertIsNone(stray_english.search(prose_only(text)), f"{article_id}:{label}")
            self.assertNotIn("\ufffd", body)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(any("human" in gap.lower() or "человечес" in gap.lower() for gap in ledger["knownGaps"]))
        for recipe_id, directory in RECIPES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            recipe_body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertIsNone(cliche.search(recipe_body), recipe_id)
            user_texts = [("title", recipe["title"]), ("summary", recipe["summary"]), ("body", recipe_body), ("fragment-title", fragment["title"])]
            user_texts.extend((f"role:{node['ref']}", node["role"]) for node in fragment["nodes"])
            for label, text in user_texts:
                self.assertIsNone(stray_english.search(prose_only(text)), f"{recipe_id}:{label}")
        encode_body = article_bodies["core.vae-encode-tiled"]
        self.assertIn("В двух графах для изображений", encode_body)
        self.assertIn("В графе для видео", encode_body)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            node = nodes[spec["id"]]
            self.assertEqual(spec["module"], node["python_module"])
            self.assertFalse(node.get("experimental", False))
            self.assertFalse(node.get("deprecated", False))
            self.assertEqual(spec["fp"], catalog.schema_fingerprint(spec["id"], node), article_id)
            self.assertEqual(spec["fp"], catalog.load_json(article_path(spec))["editorial"]["schemaHash"])
        decode = nodes["VAEDecodeTiled"]["input"]["required"]
        encode = nodes["VAEEncodeTiled"]["input"]["required"]
        self.assertEqual((512, 64, 4096, 32), tuple(decode["tile_size"][1][key] for key in ("default", "min", "max", "step")))
        self.assertEqual((512, 64, 4096, 64), tuple(encode["tile_size"][1][key] for key in ("default", "min", "max", "step")))
        self.assertEqual((0.3, 0.0, 1.0, 0.01), tuple(nodes["TomePatchModel"]["input"]["required"]["ratio"][1][key] for key in ("default", "min", "max", "step")))
        patch_required = nodes["PatchModelAddDownscale"]["input"]["required"]
        self.assertEqual(["bicubic", "nearest-exact", "bilinear", "area", "bislerp"], patch_required["downscale_method"][1]["options"])
        for recipe_id, directory in RECIPES.items():
            fragment = catalog.load_json(catalog.CONTENT / "recipes" / directory / "fragment.json")
            by_ref = {item["ref"]: item for item in fragment["nodes"]}
            supplied = {ref: set(item["settings"]) for ref, item in by_ref.items()}
            for external in fragment["externalInputs"]:
                target = by_ref[external["to"]]
                self.assertEqual(external["type"], descriptor_type(descriptors(nodes[target["classType"]])[external["input"]]))
                supplied[external["to"]].add(external["input"])
            for connection in fragment["connections"]:
                source_node = nodes[by_ref[connection["from"]]["classType"]]
                target_node = nodes[by_ref[connection["to"]]["classType"]]
                output_index = source_node["output_name"].index(connection["output"])
                self.assertEqual(source_node["output"][output_index], descriptor_type(descriptors(target_node)[connection["input"]]))
                supplied[connection["to"]].add(connection["input"])
            for ref, item in by_ref.items():
                required = set(nodes[item["classType"]].get("input", {}).get("required", {}))
                self.assertTrue(required <= supplied[ref], (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_pinned_source_and_replacement_contracts(self) -> None:
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        core = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        sd_path = SOURCE / "comfy" / "sd.py"
        self.assertEqual(SD_SHA, hashlib.sha256(sd_path.read_bytes()).hexdigest())
        sd = sd_path.read_text(encoding="utf-8")
        tome = (SOURCE / "comfy_extras" / "nodes_tomesd.py").read_text(encoding="utf-8")
        downscale = (SOURCE / "comfy_extras" / "nodes_model_downscale.py").read_text(encoding="utf-8")
        for snippet in ("if tile_size < overlap * 4:", "temporal_overlap = temporal_overlap // 2", "latent = latent.unbind()[0]", "vae.decode_tiled(latent", "vae.encode_tiled(pixels", 'return ({"samples": t}, )'):
            self.assertIn(snippet, core)
        for snippet in ("pixel_samples = self.vae_encode_crop_pixels(pixel_samples)", "pixels = pixels.narrow(d + 1, x_offset, x)", "pixels = pixels[..., :self.output_channels]", "pixels = torch.nn.functional.pad", "samples = comfy.utils.tiled_scale(pixel_samples, encode_fn, tile_x, tile_y, overlap", "samples += comfy.utils.tiled_scale(pixel_samples, encode_fn, tile_x * 2, tile_y // 2, overlap", "samples += comfy.utils.tiled_scale(pixel_samples, encode_fn, tile_x // 2, tile_y * 2, overlap", "if self.handles_tiling and dims in (2, 3):", "samples = self.encode_tiled_3d(pixel_samples[:,:,:maximum], **args)", "output = self.decode_tiled_3d(samples, **args)", "return output.movedim(1, -1)", "retrying with tiled VAE encoding"):
            self.assertIn(snippet, sd)
        for snippet in ("downsample <= max_downsample", "r = int(x.shape[1] * ratio)", "m, u = get_functions(q, ratio", "return m(q), k, v", "set_model_attn1_output_patch"):
            self.assertIn(snippet, tome)
        for snippet in ('transformer_options["block"][1] == block_number', "sigma <= sigma_start and sigma >= sigma_end", "round(h.shape[-1] * (1.0 / downscale_factor))", "if h.shape[2] != hsp.shape[2]", "set_model_input_block_patch_after_skip"):
            self.assertIn(snippet, downscale)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in SPECS.values():
            self.assertNotIn(spec["id"], replacements)

    @unittest.skipUnless(DOCS.exists(), "pinned docs absent")
    def test_pinned_docs_hashes_and_recorded_limitations(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            for spec in SPECS.values():
                for locale, digest in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec['id']}/{locale}.md"
                    self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest(), name)
            self.assertIn("automatically adjusts overlap", archive.read("comfyui_embedded_docs/docs/VAEDecodeTiled/en.md").decode("utf-8"))
            self.assertIn("no effect on standard image VAEs", archive.read("comfyui_embedded_docs/docs/VAEEncodeTiled/en.md").decode("utf-8"))
            self.assertIn("potentially lower quality", archive.read("comfyui_embedded_docs/docs/TomePatchModel/en.md").decode("utf-8"))
            self.assertIn("maintaining quality", archive.read("comfyui_embedded_docs/docs/PatchModelAddDownscale/en.md").decode("utf-8"))
        decode_body = (article_path(SPECS["core.vae-decode-tiled"]).parent / "ru.md").read_text(encoding="utf-8")
        patch_body = (article_path(SPECS["core.patch-model-add-downscale"]).parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn("не является гарантией", decode_body)
        self.assertIn("проверяет только `h.shape[2]", patch_body)

    @unittest.skipUnless(WORKFLOWS.exists(), "pinned workflows absent")
    def test_exhaustive_workflow_census_and_exact_seedvr2_topology(self) -> None:
        self.assertEqual(WORKFLOWS_SHA, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec["id"] for spec in SPECS.values()}
        counts = {target: Counter() for target in targets}
        files = {target: set() for target in targets}
        widgets = {target: Counter() for target in targets}
        seedvr: dict[str, tuple[dict[Any, dict[str, Any]], set[tuple[Any, int, Any, int, Any]]]] = {}
        seedvr_members = {"utility_seedvr2_3b_int8_upscale_image.json", "utility_seedvr2_7b_int8_upscale_image.json", "utility_seedvr2_3b_int8_upscale_video.json"}
        json_count = roots = subgraphs = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            members = sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json"))
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    roots += 1
                definitions = payload.get("definitions", {}) if isinstance(payload, dict) else {}
                if isinstance(definitions, dict):
                    subgraphs += sum(isinstance(graph, dict) for graph in definitions.get("subgraphs", []))
                for scope, graph in graph_scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    links = {item for raw in graph.get("links", []) if (item := link_fields(raw)) is not None}
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            files[node_type].add(member)
                            widgets[node_type][json.dumps(node.get("widgets_values", []), separators=(",", ":"))] += 1
                    basename = member.rsplit("/", 1)[-1]
                    if basename in seedvr_members and scope == "subgraph" and any(node.get("type") == "VAEEncodeTiled" for node in nodes.values()):
                        seedvr[basename] = nodes, links
        self.assertEqual((512, 496, 272), (json_count, roots, subgraphs))
        self.assertEqual((5, 22, 23, 22, 5), (counts["VAEDecodeTiled"]["root"], counts["VAEDecodeTiled"]["subgraph"], len(files["VAEDecodeTiled"]), counts["VAEDecodeTiled"]["mode:0"], counts["VAEDecodeTiled"]["mode:4"]))
        self.assertEqual((0, 3, 3), (counts["VAEEncodeTiled"]["root"], counts["VAEEncodeTiled"]["subgraph"], len(files["VAEEncodeTiled"])))
        self.assertEqual(2, widgets["VAEEncodeTiled"]["[512,128,4096,8]"])
        self.assertEqual(1, widgets["VAEEncodeTiled"]["[512,128,64,8]"])
        self.assertEqual(Counter({"[512,64,4096,8]": 7, "[768,64,4096,4]": 5, "[768,64,4096,64]": 5, "[512,64,64,4096]": 3, "[512,128,4096,8]": 2, "[768,64,4096,32]": 2, "[256,64,64,8]": 1, "[512,128,64,8]": 1, "[512,64,64,8]": 1}), widgets["VAEDecodeTiled"])
        for target in ("TomePatchModel", "PatchModelAddDownscale"):
            self.assertEqual((0, 0, 0), (counts[target]["root"], counts[target]["subgraph"], len(files[target])))
        self.assertEqual(seedvr_members, set(seedvr))
        for basename in ("utility_seedvr2_3b_int8_upscale_image.json", "utility_seedvr2_7b_int8_upscale_image.json"):
            nodes, links = seedvr[basename]
            self.assertEqual([512, 128, 4096, 8], nodes[48]["widgets_values"])
            self.assertEqual([959948902156062, "fixed", 1, 1, "euler", "simple", 1], nodes[54]["widgets_values"])
            self.assertEqual([512, 128, 4096, 8], nodes[55]["widgets_values"])
            self.assertEqual(["seedvr2_ema_vae_fp16.safetensors"], nodes[51]["widgets_values"])
            for link in ((58, 0, 48, 0, "IMAGE"), (51, 0, 48, 1, "VAE"), (48, 0, 61, 1, "LATENT"), (48, 0, 54, 3, "LATENT"), (54, 0, 55, 0, "LATENT"), (51, 0, 55, 1, "VAE")):
                self.assertIn(link, links, (basename, link))
        nodes, links = seedvr["utility_seedvr2_3b_int8_upscale_video.json"]
        self.assertEqual([512, 128, 64, 8], nodes[48]["widgets_values"])
        self.assertEqual([959948902156062, "fixed", 1, 1, "euler", "simple", 1], nodes[54]["widgets_values"])
        self.assertEqual([512, 128, 64, 8], nodes[55]["widgets_values"])
        self.assertEqual([0, "auto"], nodes[99]["widgets_values"])
        self.assertEqual([False], nodes[102]["widgets_values"])
        self.assertEqual([False], nodes[103]["widgets_values"])
        self.assertEqual(["seedvr2_ema_vae_fp16.safetensors"], nodes[51]["widgets_values"])
        for link in ((58, 0, 48, 0, "IMAGE"), (51, 0, 48, 1, "VAE"), (48, 0, 99, 0, "LATENT"), (48, 0, 102, 0, "LATENT"), (99, 0, 102, 1, "LATENT"), (102, 0, 61, 1, "LATENT"), (102, 0, 54, 3, "LATENT"), (54, 0, 100, 0, "LATENT"), (99, 1, 100, 1, "INT"), (54, 0, 103, 0, "LATENT"), (100, 0, 103, 1, "LATENT"), (103, 0, 55, 0, "LATENT"), (51, 0, 55, 1, "VAE")):
            self.assertIn(link, links, ("utility_seedvr2_3b_int8_upscale_video.json", link))

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_exact_source_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        executable = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(executable)
        result = subprocess.run([str(executable), "-X", "utf8", str(PROBE), str(SOURCE)], cwd=catalog.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([2, 16, 20, 3], report["decode"]["shape"])
        self.assertEqual(16, report["decode"]["call"]["tile_x"])
        self.assertEqual(1, report["decode"]["call"]["overlap_t"])
        self.assertEqual([None, None], report["decode"]["imageTemporal"])
        self.assertEqual([4, 8, 10], report["decode"]["nestedShape"])
        self.assertEqual(1.0, report["decode"]["nestedFirst"])
        self.assertEqual([1, 8, 16, 3], report["encode"]["cropShape"])
        self.assertEqual([1, 8, 16, 3], report["encode"]["padShape"])
        self.assertEqual(0.25, report["encode"]["padValue"])
        self.assertEqual([(8, 6), (16, 3), (4, 12)], [(call["tile_x"], call["tile_y"]) for call in report["vaeCore"]["encodeGrids"]])
        self.assertEqual([(4, 12), (16, 3), (8, 6)], [(call["tile_x"], call["tile_y"]) for call in report["vaeCore"]["decodeGrids"]])
        self.assertEqual(2.0, report["vaeCore"]["baseEncodeMean"])
        self.assertEqual(2.0, report["vaeCore"]["baseDecodeMean"])
        self.assertEqual([1, 3, 12, 16], report["vaeCore"]["encode2d"]["shape"])
        self.assertEqual([1, 3, 9, 12, 16], report["vaeCore"]["encode3d"]["shape"])
        self.assertEqual([61, [5, 2, 2]], [report["vaeCore"]["encode3d"]["tile_t"], report["vaeCore"]["encode3d"]["overlap"]])
        self.assertEqual([1, 3, 10, 12, 16], report["vaeCore"]["encodeOwned"]["shape"])
        self.assertEqual([64, 8], [report["vaeCore"]["encodeOwned"]["tile_t"], report["vaeCore"]["encodeOwned"]["overlap_t"]])
        self.assertEqual([3, 2, 2], report["vaeCore"]["decode3d"]["overlap"])
        self.assertEqual(3, report["vaeCore"]["decodeOwned"]["overlap_t"])
        self.assertEqual([1, 12, 2], report["tome"]["merged"])
        self.assertEqual([1, 16, 2], report["tome"]["restored"])
        self.assertEqual([1, 12, 2], report["tome"]["zeroMetricMerged"])
        self.assertTrue(report["tome"]["queryLongerError"])
        self.assertEqual([1, 4, 4, 5], report["downscale"]["shrunk"])
        self.assertTrue(report["downscale"]["heightOnlySkipped"])


if __name__ == "__main__":
    unittest.main()
