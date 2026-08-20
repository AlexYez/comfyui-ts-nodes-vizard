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
    "core.clip-text-encode-flux": {"dir": "clip-text-encode-flux", "id": "CLIPTextEncodeFlux", "fp": "sha256:16b4d31b05a25ea153b45e156642eda4328db8c26a17fff547ee1aaf9267427b", "recipe": "recipe.flux-dual-text-conditioning", "docsDir": "ClipTextEncodeFlux", "docs": {"en": "ab38f6ff0bc6b010436404537c8fd41ecdc0610b8b7e071457e39fe248c03dd9", "ru": "e47603e3628f13755e9d842bed9f2774e31fab65311a47eb6676db3caf1d9fa7"}},
    "core.flux-guidance": {"dir": "flux-guidance", "id": "FluxGuidance", "fp": "sha256:6739f8f7672b0de8b9669f488df7c088499ecf04ebf38fb084618d80ae1bcf79", "recipe": "recipe.set-flux-guidance", "docs": {"en": "c5a404218bb77bb74ee05d2eea161ec266f0c8f3254b1b156ad88173a5a4ae6c", "ru": "a8793cd14f30caf4738329fa80bd87e8b3820dfefbef1879182a5818b57c6187"}},
    "core.flux-disable-guidance": {"dir": "flux-disable-guidance", "id": "FluxDisableGuidance", "fp": "sha256:6102bb2dad592650ed5ac414c907034c32be4f437d0341f5d7865cec5e567068", "recipe": "recipe.disable-flux-guidance", "docs": {"en": "db4c895052c91b619abfa70e4ea08ab44c1153db0bbd06a096e00d13c29c708a", "ru": "64a297b35c902b891d52198a2c60b168d9914c97e487a83d789fb83de398f829"}},
    "core.flux-kontext-image-scale": {"dir": "flux-kontext-image-scale", "id": "FluxKontextImageScale", "fp": "sha256:07044e61d5fd7254d163481bf78a2bf1b15e99df28ae46b55c0427381daf16f2", "recipe": "recipe.scale-flux-kontext-reference", "docs": {"en": "42d6497897c7d759a3d7c2237f169b6f689aa919a1e7ab65b5aedd37dd7058ea", "ru": "10167845fed4bc78dede6338774e954f904eab1a933ecad9b17a16b622d213dd"}},
}
RECIPES = {
    "recipe.flux-dual-text-conditioning": "flux-dual-text-conditioning",
    "recipe.set-flux-guidance": "set-flux-guidance",
    "recipe.disable-flux-guidance": "disable-flux-guidance",
    "recipe.scale-flux-kontext-reference": "scale-flux-kontext-reference",
}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOWS_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
PROBE = Path(__file__).with_name("flux_conditioning_scale_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["dir"] / "manifest.json"


def descriptor_type(value: Any) -> Any:
    return "COMBO" if isinstance(value, list) and value and isinstance(value[0], list) else value[0] if isinstance(value, list) and value else None


def descriptors(node: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for group in ("required", "optional"):
        result.update(node.get("input", {}).get(group, {}))
    return result


def scopes(payload: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for graph in definitions.get("subgraphs", []):
            if isinstance(graph, dict):
                yield "subgraph", graph


def fields(link: Any) -> tuple[Any, int, Any, int, Any] | None:
    if isinstance(link, list) and len(link) >= 6:
        return link[1], link[2], link[3], link[4], link[5]
    if isinstance(link, dict):
        return link.get("origin_id"), link.get("origin_slot", 0), link.get("target_id"), link.get("target_slot", 0), link.get("type")
    return None


class FluxConditioningScaleContentTests(unittest.TestCase):
    def test_content_schemas_honesty_ten_sections_and_natural_russian(self) -> None:
        schemas = {key: catalog.load_json(catalog.CONTENT / "schemas" / name) for key, name in {"article": "article.schema.v1.json", "recipe": "recipe.schema.v1.json", "fragment": "recipe-fragment.schema.v1.json", "research": "article-research.schema.v1.json"}.items()}
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        target_types = {spec["id"] for spec in SPECS.values()}
        collisions = Counter(catalog.load_json(path).get("runtimeIdentity", {}).get("classType") for path in (catalog.CONTENT / "articles").rglob("manifest.json"))
        for node_id in target_types:
            self.assertEqual(1, collisions[node_id])
        errors: list[str] = []
        cliche = re.compile(r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|\bдавайте\b|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода|вот перевод документации", re.I)
        stray_english = re.compile(r"\b(?:official|exact|case|cases|prompt|prompts|encoder|encoders|loader|loaders|branch|branches|metadata|entry|entries|tensor|tensors|output|outputs|input|inputs|model|models|family|workflow|workflows|widget|widgets|source|runtime|frontend|backend|root|subgraph|subgraphs|files|preset|presets|resolution|resolutions|aspect|ratio|crop|padding|batch|channels|shape|classic|numeric|sampling)\b", re.I)

        def prose_only(body: str) -> str:
            without_code = re.sub(r"`[^`\n]*`", "", body)
            return re.sub(r"\]\([^)]*\)", "]", without_code)

        article_bodies: dict[str, str] = {}
        for article_id, spec in SPECS.items():
            path = article_path(spec)
            manifest = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]), article_id)
            catalog.validate_article(path, manifest, errors)
            self.assertEqual("draft", manifest["status"])
            self.assertEqual("in_review", manifest["editorial"]["state"])
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"])
            self.assertEqual([spec["recipe"]], [asset["id"] for asset in manifest["assets"]])
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            article_bodies[article_id] = body
            self.assertEqual(10, len(re.findall(r"^## ", body, re.M)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            self.assertIsNone(stray_english.search(prose_only(body)), article_id)
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
            self.assertIsNone(stray_english.search(prose_only(recipe_body)), recipe_id)
        kontext_body = article_bodies["core.flux-kontext-image-scale"]
        for snippet in ("CPU, NumPy и PIL", "np.clip(255. * image.cpu().numpy(), 0, 255).astype(np.uint8)", "дробная часть при переводе в `uint8` отбрасывается", "обычного входа RGB или RGBA", "трёхмерная форма `[B,W,H]`"):
            self.assertIn(snippet, kontext_body)
        guidance_body = article_bodies["core.flux-guidance"]
        self.assertIn("Более поздняя `FluxGuidance`", guidance_body)
        self.assertNotIn("Более поздний `CLIPTextEncodeFlux`", guidance_body)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_settings_and_fragment_types(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        for article_id, spec in SPECS.items():
            node = nodes[spec["id"]]
            self.assertEqual("comfy_extras.nodes_flux", node["python_module"])
            self.assertFalse(node["experimental"])
            self.assertFalse(node["deprecated"])
            self.assertFalse(node["dev_only"])
            self.assertFalse(node["api_node"])
            self.assertEqual(spec["fp"], catalog.schema_fingerprint(spec["id"], node), article_id)
            self.assertEqual(spec["fp"], catalog.load_json(article_path(spec))["editorial"]["schemaHash"])
        encode = nodes["CLIPTextEncodeFlux"]["input"]["required"]
        self.assertEqual((3.5, 0.0, 100.0, 0.1), tuple(encode["guidance"][1][key] for key in ("default", "min", "max", "step")))
        self.assertEqual(["CONDITIONING"], nodes["FluxGuidance"]["output"])
        self.assertEqual(["IMAGE"], nodes["FluxKontextImageScale"]["output"])
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
            for ref, node in by_ref.items():
                required = set(nodes[node["classType"]]["input"].get("required", {}))
                self.assertTrue(required <= supplied[ref], (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_pinned_source_and_replacement_contracts(self) -> None:
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "comfy_extras" / "nodes_flux.py").read_text(encoding="utf-8")
        for snippet in ('tokens = clip.tokenize(clip_l)', 'tokens["t5xxl"] = clip.tokenize(t5xxl)["t5xxl"]', 'add_dict={"guidance": guidance}', 'conditioning_set_values(conditioning, {"guidance": guidance})', 'conditioning_set_values(conditioning, {"guidance": None})', 'PREFERRED_KONTEXT_RESOLUTIONS = [', 'min((abs(aspect_ratio - w / h), w, h)', '"lanczos", "center"'):
            self.assertIn(snippet, source)
        upscale = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        for snippet in ('samples = samples.squeeze(1) if samples.shape[1] == 1 else samples.movedim(1, -1)', 'image.cpu().numpy()', 'np.clip(255. * image.cpu().numpy(), 0, 255).astype(np.uint8)', 'image.resize((width, height), resample=Image.Resampling.LANCZOS)', 'return result.to(samples.device, samples.dtype)', 's = samples.narrow(-2, y, old_height - y * 2).narrow(-1, x, old_width - x * 2)'):
            self.assertIn(snippet, upscale)
        zero_out = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        for snippet in ('d["pooled_output"] = torch.zeros_like(pooled_output)', 'd["conditioning_lyrics"] = torch.zeros_like(conditioning_lyrics)', 'n = [torch.zeros_like(t[0]), d]'):
            self.assertIn(snippet, zero_out)
        scheduled = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        for snippet in ("all_hooks = self.patcher.forced_hooks", "scheduled_keyframes = all_hooks.get_hooks_for_clip_schedule()", 'pooled_dict["clip_start_percent"] = t_range[0]', "pooled_dict.update(add_dict)"):
            self.assertIn(snippet, scheduled)
        if FRONTEND.exists():
            dynamic = (FRONTEND / "src" / "extensions" / "core" / "dynamicPrompts.ts").read_text(encoding="utf-8")
            self.assertIn("const prompt = processDynamicPrompt(widget.value)", dynamic)
            self.assertIn("return prompt", dynamic)
        replacements = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in SPECS.values():
            self.assertNotIn(spec["id"], replacements)

    @unittest.skipUnless(DOCS.exists(), "pinned docs absent")
    def test_pinned_docs_hashes_absence_and_known_limits(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            for spec in SPECS.values():
                for locale, digest in spec["docs"].items():
                    name = f"comfyui_embedded_docs/docs/{spec.get('docsDir', spec['id'])}/{locale}.md"
                    self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest(), name)
            self.assertIn("two separate text inputs", archive.read("comfyui_embedded_docs/docs/ClipTextEncodeFlux/en.md").decode("utf-8"))
            self.assertIn("setting it to None", archive.read("comfyui_embedded_docs/docs/FluxDisableGuidance/en.md").decode("utf-8"))
            self.assertIn("| 1568  | 672", archive.read("comfyui_embedded_docs/docs/FluxKontextImageScale/en.md").decode("utf-8"))

    @unittest.skipUnless(WORKFLOWS.exists(), "pinned workflows absent")
    def test_exhaustive_workflow_census_and_exact_topology(self) -> None:
        self.assertEqual(WORKFLOWS_SHA, hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec["id"] for spec in SPECS.values()}
        counts = {target: Counter() for target in targets}
        files = {target: set() for target in targets}
        widgets = {target: Counter() for target in targets}
        schnell = kontext = flux2 = None
        json_count = roots = subgraphs = 0
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")):
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    roots += 1
                if isinstance(payload, dict) and isinstance(payload.get("definitions"), dict):
                    subgraphs += sum(isinstance(graph, dict) for graph in payload["definitions"].get("subgraphs", []))
                for scope, graph in scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    links = {item for link in graph.get("links", []) if (item := fields(link)) is not None}
                    for node in nodes.values():
                        node_type = node.get("type")
                        if node_type in targets:
                            counts[node_type][scope] += 1
                            counts[node_type][f"mode:{node.get('mode', 0)}"] += 1
                            files[node_type].add(member)
                            widgets[node_type][json.dumps(node.get("widgets_values", []), separators=(",", ":"))] += 1
                    if member.endswith("flux_schnell_full_text_to_image.json") and scope == "root": schnell = nodes, links
                    if member.endswith("flux_kontext_dev_basic.json") and graph.get("id") == "654c828f-2572-47e8-ba85-8a832c89b30c": kontext = nodes, links
                    if member.endswith("image_flux2_text_to_image.json") and graph.get("id") == "e3a57dc6-b2bf-4d05-927d-3715b40d2a77": flux2 = nodes, links
        self.assertEqual((512, 496, 272), (json_count, roots, subgraphs))
        self.assertEqual((1, 0, 1), (counts["CLIPTextEncodeFlux"]["root"], counts["CLIPTextEncodeFlux"]["subgraph"], len(files["CLIPTextEncodeFlux"])))
        self.assertEqual((5, 14, 16), (counts["FluxGuidance"]["root"], counts["FluxGuidance"]["subgraph"], len(files["FluxGuidance"])))
        self.assertEqual(Counter({"[3.5]": 3, "[30]": 5, "[10]": 1, "[2.5]": 1, "[6]": 1, "[4]": 6, "[4.5]": 2}), widgets["FluxGuidance"])
        self.assertEqual((0, 0, 0), (counts["FluxDisableGuidance"]["root"], counts["FluxDisableGuidance"]["subgraph"], len(files["FluxDisableGuidance"])))
        self.assertEqual((1, 18, 12), (counts["FluxKontextImageScale"]["root"], counts["FluxKontextImageScale"]["subgraph"], len(files["FluxKontextImageScale"])))
        self.assertEqual(19, widgets["FluxKontextImageScale"]["[]"])
        self.assertIsNotNone(schnell); nodes, links = schnell or ({}, set()); self.assertIn((40, 0, 41, 0, "CLIP"), links); self.assertIn((41, 0, 31, 1, "CONDITIONING"), links); self.assertIn((41, 0, 42, 0, "CONDITIONING"), links); self.assertIn((42, 0, 31, 2, "CONDITIONING"), links)
        self.assertIsNotNone(kontext); nodes, links = kontext or ({}, set()); self.assertIn((146, 0, 42, 0, "IMAGE"), links); self.assertIn((42, 0, 124, 0, "IMAGE"), links)
        self.assertIsNotNone(flux2); nodes, links = flux2 or ({}, set()); self.assertEqual([4], nodes[26]["widgets_values"]); self.assertIn((26, 0, 22, 1, "CONDITIONING"), links)

    @unittest.skipUnless(SOURCE.exists(), "pinned source absent")
    def test_safe_exact_method_probe(self) -> None:
        candidates = [Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe", Path(sys.executable)]
        executable = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(executable)
        result = subprocess.run([str(executable), "-X", "utf8", str(PROBE), str(SOURCE)], cwd=catalog.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(["short", "long description"], report["encode"]["calls"])
        self.assertEqual(["t5:long description"], report["encode"]["t5"])
        self.assertEqual(4.0, report["metadata"]["guided"])
        self.assertIsNone(report["metadata"]["disabled"])
        self.assertTrue(report["metadata"]["tensorIdentity"])
        self.assertEqual(3.5, report["metadata"]["zeroOutGuidance"])
        self.assertEqual("kept", report["metadata"]["zeroOutMarker"])
        self.assertEqual([2, 1024, 1024, 4], report["scale"]["square"])
        self.assertEqual([1, 832, 1248, 3], report["scale"]["landscape"])
        self.assertEqual([1, 1248, 832, 3], report["scale"]["portrait"])
        self.assertAlmostEqual(0.2471, report["scale"]["cropThenResize"][0], places=3)
        self.assertAlmostEqual(0.1490, report["scale"]["resizeWithoutCrop"][0], places=3)
        self.assertEqual([1, 1248, 832], report["scale"]["mono"])
        self.assertAlmostEqual(64 / 255, report["scale"]["monoLevel"], places=7)
        self.assertAlmostEqual(0.0, report["scale"]["quantized"][0][0], places=7)
        self.assertAlmostEqual(127 / 255, report["scale"]["quantized"][0][1], places=7)
        self.assertAlmostEqual(1.0, report["scale"]["quantized"][0][2], places=7)
        self.assertAlmostEqual(1 / 255, report["scale"]["quantized"][1][0], places=7)
        self.assertAlmostEqual(64 / 255, report["scale"]["quantized"][1][1], places=7)
        self.assertAlmostEqual(254 / 255, report["scale"]["quantized"][1][2], places=7)


if __name__ == "__main__":
    unittest.main()
