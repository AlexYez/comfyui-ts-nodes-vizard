from __future__ import annotations

import hashlib
import json
import re
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.lora-loader": ("lora-loader", "LoraLoader", "sha256:e5378fcb5e2752288dc29d2cbdf47f08c284f747e73f164616b681ff1819640f"),
    "core.clip-loader": ("clip-loader", "CLIPLoader", "sha256:112867ec515a3cf857868ddcf765e4b7140eaf93f0e4095bbc030faecad63a04"),
    "core.unet-loader": ("unet-loader", "UNETLoader", "sha256:1ac048a4f00d1a14a2e93f61f24e446c6b1de07311fd46d00b8b0cad216092ad"),
    "core.dual-clip-loader": ("dual-clip-loader", "DualCLIPLoader", "sha256:5f5f41b5882f43522b531436882c10c2ded3b51a156f300af301a7ba3d2d8ce0"),
}
RECIPE_DIRS = ("wan-vace-lora", "stable-audio-clip-loader", "flux-schnell-split-loaders")
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"


def graph_records(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield "root", node, payload
    definitions = payload.get("definitions")
    if isinstance(definitions, dict):
        for subgraph in definitions.get("subgraphs", []):
            if isinstance(subgraph, dict):
                for node in subgraph.get("nodes", []):
                    if isinstance(node, dict):
                        yield "subgraph", node, subgraph


class SplitModelLoadersContentTests(unittest.TestCase):
    def test_schema_identity_honesty_and_natural_russian(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        inventory = catalog.load_json(INVENTORY)
        article_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        errors: list[str] = []
        text_paths: list[Path] = []

        for article_id, (directory, class_type, fingerprint) in ARTICLE_SPECS.items():
            path = catalog.CONTENT / "articles" / "core" / directory / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual("nodes", article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(fingerprint, article["editorial"]["schemaHash"])
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, inventory[class_type]))
            for relation in article["relations"]["related"] + article["relations"]["alternatives"]:
                self.assertIn(relation, article_ids)
            body = path.parent / "ru.md"
            self.assertEqual(10, len(re.findall(r"^## ", body.read_text(encoding="utf-8"), re.MULTILINE)))
            text_paths.append(body)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for directory in RECIPE_DIRS:
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(fragment_path, fragment, errors)
            text_paths.append(path.parent / "ru.md")

        self.assertEqual([], errors)
        forbidden = ("важно отметить", "стоит отметить", "таким образом", "в современном мире", "давайте", "погрузимся", "можно с уверенностью")
        for path in text_paths:
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("\ufffd", text)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_runtime_contracts_and_fragment_types(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        self.assertEqual(["MODEL", "CLIP"], inventory["LoraLoader"]["output"])
        self.assertEqual((-100.0, 100.0, 0.01), tuple(inventory["LoraLoader"]["input"]["required"]["strength_model"][1][key] for key in ("min", "max", "step")))
        self.assertEqual(["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"], inventory["UNETLoader"]["input"]["required"]["weight_dtype"][0])
        self.assertIn("stable_audio", inventory["CLIPLoader"]["input"]["required"]["type"][0])
        self.assertIn("wan", inventory["CLIPLoader"]["input"]["required"]["type"][0])
        self.assertIn("flux", inventory["DualCLIPLoader"]["input"]["required"]["type"][0])
        self.assertEqual(["default", "cpu"], inventory["DualCLIPLoader"]["input"]["optional"]["device"][0])

        wan = catalog.load_json(catalog.CONTENT / "recipes" / "wan-vace-lora" / "fragment.json")
        self.assertEqual(["UNETLoader", "CLIPLoader", "LoraLoader"], [node["classType"] for node in wan["nodes"]])
        self.assertEqual({("MODEL", "model"), ("CLIP", "clip")}, {(link["output"], link["input"]) for link in wan["connections"]})
        lora = next(node for node in wan["nodes"] if node["classType"] == "LoraLoader")
        self.assertEqual((0.7, 1.0), (lora["settings"]["strength_model"], lora["settings"]["strength_clip"]))

        audio = catalog.load_json(catalog.CONTENT / "recipes" / "stable-audio-clip-loader" / "fragment.json")
        loader = next(node for node in audio["nodes"] if node["classType"] == "CLIPLoader")
        self.assertEqual(("t5-base.safetensors", "stable_audio", "default"), tuple(loader["settings"][key] for key in ("clip_name", "type", "device")))
        self.assertEqual(2, len(audio["connections"]))

        flux = catalog.load_json(catalog.CONTENT / "recipes" / "flux-schnell-split-loaders" / "fragment.json")
        dual = next(node for node in flux["nodes"] if node["classType"] == "DualCLIPLoader")
        self.assertEqual(("clip_l.safetensors", "t5xxl_fp16.safetensors", "flux", "default"), tuple(dual["settings"][key] for key in ("clip_name1", "clip_name2", "type", "device")))
        self.assertEqual({("text_encoders", "encode", "CLIP", "clip")}, {(link["from"], link["to"], link["output"], link["input"]) for link in flux["connections"]})

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_pinned_source_contracts(self) -> None:
        nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        folders = (SOURCE / "folder_paths.py").read_text(encoding="utf-8")
        self.assertIn("if strength_model == 0 and strength_clip == 0", nodes)
        self.assertIn("self.loaded_lora = (lora_path, lora, lora_metadata)", nodes)
        self.assertIn('model_options["fp8_optimizations"] = True', nodes)
        self.assertIn('model_options["load_device"] = model_options["offload_device"] = torch.device("cpu")', nodes)
        self.assertIn("ckpt_paths=[clip_path1, clip_path2]", nodes)
        self.assertIn("new_modelpatcher = model.clone()", sd)
        self.assertIn("logging.warning(\"NOT LOADED {}\".format(x))", sd)
        self.assertIn("raise RuntimeError(\"ERROR: Could not detect model type of:", sd)
        self.assertIn('folder_names_and_paths["text_encoders"]', folders)
        self.assertIn('folder_names_and_paths["diffusion_models"]', folders)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_workflow_census_and_cases(self) -> None:
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec[1] for spec in ARTICLE_SPECS.values()}
        counts: Counter[tuple[str, str]] = Counter()
        files: dict[str, set[str]] = defaultdict(set)
        workflows: dict[str, dict[str, Any]] = {}
        parsed = graphs = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(name for name in archive.namelist() if name.endswith(".json")):
                payload = json.loads(archive.read(member).decode("utf-8"))
                parsed += 1
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    graphs += 1
                workflows[member] = payload
                for scope, node, _graph in graph_records(payload):
                    class_type = node.get("type")
                    if class_type in targets:
                        counts[(class_type, scope)] += 1
                        files[class_type].add(member)
        self.assertEqual((512, 496), (parsed, graphs))
        self.assertEqual((8, 6, 10), (counts[("LoraLoader", "root")], counts[("LoraLoader", "subgraph")], len(files["LoraLoader"])))
        self.assertEqual((46, 130, 134), (counts[("CLIPLoader", "root")], counts[("CLIPLoader", "subgraph")], len(files["CLIPLoader"])))
        self.assertEqual((67, 161, 165), (counts[("UNETLoader", "root")], counts[("UNETLoader", "subgraph")], len(files["UNETLoader"])))
        self.assertEqual((12, 17, 28), (counts[("DualCLIPLoader", "root")], counts[("DualCLIPLoader", "subgraph")], len(files["DualCLIPLoader"])))

        wan = next(payload for name, payload in workflows.items() if name.endswith("/video_wan_vace_14B_t2v.json"))
        wan_nodes = {node["id"]: node for node in wan["nodes"]}
        self.assertEqual(["wan2.1_vace_14B_fp16.safetensors", "default"], wan_nodes[106]["widgets_values"])
        self.assertEqual(["umt5_xxl_fp16.safetensors", "wan", "default"], wan_nodes[110]["widgets_values"])
        self.assertEqual(["Wan21_CausVid_14B_T2V_lora_rank32.safetensors", 0.7000000000000002, 1], wan_nodes[107]["widgets_values"])
        self.assertIn([188, 106, 0, 107, 0, "MODEL"], wan["links"])
        self.assertIn([189, 110, 0, 107, 1, "CLIP"], wan["links"])

        audio = next(payload for name, payload in workflows.items() if name.endswith("/audio_stable_audio_example.json"))
        audio_nodes = {node["id"]: node for node in audio["nodes"]}
        self.assertEqual(["t5-base.safetensors", "stable_audio", "default"], audio_nodes[10]["widgets_values"])
        self.assertIn([25, 10, 0, 6, 0, "CLIP"], audio["links"])
        self.assertIn([26, 10, 0, 7, 0, "CLIP"], audio["links"])

        flux = next(payload for name, payload in workflows.items() if name.endswith("/flux_schnell_full_text_to_image.json"))
        flux_nodes = {node["id"]: node for node in flux["nodes"]}
        self.assertEqual(["flux1-schnell.safetensors", "default"], flux_nodes[38]["widgets_values"])
        self.assertEqual(["clip_l.safetensors", "t5xxl_fp16.safetensors", "flux", "default"], flux_nodes[40]["widgets_values"])
        self.assertIn([59, 40, 0, 41, 0, "CLIP"], flux["links"])
        self.assertIn([61, 38, 0, 31, 0, "MODEL"], flux["links"])


if __name__ == "__main__":
    unittest.main()
