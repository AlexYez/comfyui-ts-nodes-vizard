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
    "core.create-bounding-boxes": ("create-bounding-boxes", "CreateBoundingBoxes", "comfy_extras.nodes_bounding_boxes", "sha256:df299e9e3852155b069a65aa66ea6263177279265b93e15571ee1413d1347dbf", "recipe.ideogram-layout-json-prompt"),
    "core.build-json-prompt-ideogram": ("build-json-prompt-ideogram", "BuildJsonPromptIdeogram", "comfy_extras.nodes_json_prompt", "sha256:fd8811d714116ca0e8b4c6f1b46083ce0ceaf069a811ebe58aaf46f1d766aa1f", "recipe.ideogram-layout-json-prompt"),
    "core.train-lora-node": ("train-lora-node", "TrainLoraNode", "comfy_extras.nodes_train", "sha256:9b2e97f62ee9dda28e7eba11da9df7d37b20d99b7fea7b1f715a483ad746c053", "recipe.train-lora-minimal-contract"),
    "core.lora-model-loader": ("lora-model-loader", "LoraModelLoader", "comfy_extras.nodes_train", "sha256:9049b9f00df4ffd87e4f3d35c5fab729dd002e41765511b63ffca353252360ba", "recipe.train-lora-minimal-contract"),
}
RECIPES = {
    "recipe.ideogram-layout-json-prompt": "ideogram-layout-json-prompt",
    "recipe.train-lora-minimal-contract": "train-lora-minimal-contract",
}
DOC_HASHES = {
    "CreateBoundingBoxes": {"en": "6eb26c20b02c3146503633aa03fa079efd6a5b31fd2b49c14c921e15dc7aeca7", "ru": "bffe51474b08543c792a2e6089812cec88dcf9065bd9e0154a4702fd567b4308"},
    "BuildJsonPromptIdeogram": {"en": "4b9286b36659971d4a5acd40e6d738b7665bc479d6f6dff49f7e30514a29ecbd", "ru": "7a0a039a58e44c00061ceb515078bd4b097bea30e97d4261dcfde14388c02182"},
    "TrainLoraNode": {"en": "370cb93a922e4b7436e06380293aa0d8cb8c66efbc1f111aea3e6c5f46a9f9c5", "ru": "36f231bfa94392a001e8eab2c3ce62df3bdad1be30caf4bdae58b9a3a1b6ee98"},
    "LoraModelLoader": {"en": "97fd3cf6bfa621a1a1d7b1889afdf62d9b113226e31588f1d16de11dd789392c", "ru": "b32979b94bbb3080925ce6dadfcd47fd948c419b5a11544477895bdf7ad7df25"},
}
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
FRONTEND = catalog.ROOT / ".frontend-source-1.48.7"
DOCS = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
WORKFLOWS = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
PROBE = Path(__file__).with_name("bbox_json_train_lora_synthetic_probe.py")


def article_path(article_id: str) -> Path:
    return catalog.CONTENT / "articles" / "core" / SPECS[article_id][0] / "manifest.json"


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


def descriptor_type(value: Any) -> Any:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return "COMBO"
    return value[0] if isinstance(value, list) and value else None


class BBoxJsonTrainLoraContentTests(unittest.TestCase):
    def test_content_schemas_honesty_ten_sections_and_natural_russian(self) -> None:
        schemas = {
            kind: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for kind, filename in {
                "article": "article.schema.v1.json",
                "research": "article-research.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
            }.items()
        }
        all_ids = {catalog.load_json(path)["articleId"] for path in (catalog.CONTENT / "articles").rglob("manifest.json")}
        collisions = Counter(catalog.load_json(path).get("runtimeIdentity", {}).get("classType") for path in (catalog.CONTENT / "articles").rglob("manifest.json"))
        errors: list[str] = []
        cliche = re.compile(r"важно отметить|стоит отметить|следует отметить|в современном мире|революционн|является мощн|\bдавайте\b|глубже погруз|открывает новые|может показаться|позволяет вам|подводя итог|в заключение|данная нода|вот перевод документации", re.I)
        for article_id, (directory, class_type, _module, fingerprint, recipe_id) in SPECS.items():
            path = article_path(article_id)
            manifest = catalog.load_json(path)
            self.assertEqual(1, collisions[class_type], class_type)
            self.assertEqual([], catalog.json_schema_errors(manifest, schemas["article"]), article_id)
            catalog.validate_article(path, manifest, errors)
            self.assertEqual("draft", manifest["status"])
            self.assertEqual("in_review", manifest["editorial"]["state"])
            self.assertIn("human approval pending", manifest["editorial"]["reviewedBy"])
            self.assertEqual(fingerprint, manifest["editorial"]["schemaHash"])
            self.assertIn(recipe_id, [asset["id"] for asset in manifest["assets"]])
            body = (path.parent / "ru.md").read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## ", body, re.M)), article_id)
            self.assertIsNone(cliche.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / (article_id + ".json"))
            self.assertEqual([], catalog.json_schema_errors(ledger, schemas["research"]), article_id)
            self.assertEqual(("fact_checked", "automated_assisted"), (ledger["state"], ledger["reviewMode"]))
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["russianEdited"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))
        for recipe_id, directory in RECIPES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]), recipe_id)
            catalog.validate_recipe(path, recipe, all_ids, errors)
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / "fragment.json"
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertIsNone(cliche.search((path.parent / "ru.md").read_text(encoding="utf-8")), recipe_id)
        self.assertEqual([], errors)

    def test_runtime_fingerprints_ports_fragments_and_replacements(self) -> None:
        self.assertTrue(INVENTORY.is_file(), f"required pinned evidence absent: {INVENTORY}")
        self.assertTrue(REPLACEMENTS.is_file(), f"required pinned evidence absent: {REPLACEMENTS}")
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))

        def input_descriptors(node: dict[str, Any]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for group in ("required", "optional"):
                result.update(node.get("input", {}).get(group, {}))
            return result

        def validate_setting(value: Any, descriptor: Any, label: str) -> None:
            input_type = descriptor_type(descriptor)
            constraints = descriptor[1] if len(descriptor) > 1 and isinstance(descriptor[1], dict) else {}
            if input_type == "INT":
                self.assertIs(type(value), int, label)
                if "min" in constraints:
                    self.assertGreaterEqual(value, constraints["min"], label)
                if "max" in constraints:
                    self.assertLessEqual(value, constraints["max"], label)
            elif input_type == "FLOAT":
                self.assertIsInstance(value, (int, float), label)
                self.assertIsNot(type(value), bool, label)
                if "min" in constraints:
                    self.assertGreaterEqual(value, constraints["min"], label)
                if "max" in constraints:
                    self.assertLessEqual(value, constraints["max"], label)
            elif input_type == "BOOLEAN":
                self.assertIs(type(value), bool, label)
            elif input_type == "STRING":
                self.assertIsInstance(value, str, label)
            elif input_type == "COMBO":
                self.assertIsInstance(value, str, label)
                options = constraints.get("options", descriptor[0] if isinstance(descriptor[0], list) else [])
                self.assertIn(value, options, label)
            elif input_type == "COLORS":
                self.assertIsInstance(value, list, label)
                self.assertLessEqual(len(value), 16, label)
                self.assertTrue(all(isinstance(item, str) for item in value), label)
            elif input_type == "BOUNDING_BOXES":
                self.assertIsInstance(value, list, label)
                for index, box in enumerate(value):
                    box_label = f"{label}[{index}]"
                    self.assertIsInstance(box, dict, box_label)
                    self.assertEqual({"x", "y", "width", "height", "metadata"}, set(box), box_label)
                    self.assertTrue(all(isinstance(box[key], (int, float)) and not isinstance(box[key], bool) for key in ("x", "y", "width", "height")), box_label)
                    metadata = box["metadata"]
                    self.assertIsInstance(metadata, dict, box_label)
                    self.assertEqual({"type", "text", "desc", "palette"}, set(metadata), box_label)
                    self.assertIn(metadata["type"], ("obj", "text"), box_label)
                    self.assertIsInstance(metadata["text"], str, box_label)
                    self.assertIsInstance(metadata["desc"], str, box_label)
                    self.assertIsInstance(metadata["palette"], list, box_label)
                    self.assertLessEqual(len(metadata["palette"]), 5, box_label)
                    self.assertTrue(all(isinstance(color, str) for color in metadata["palette"]), box_label)
            elif input_type == "COMFY_DYNAMICCOMBO_V3":
                self.assertIsInstance(value, dict, label)
                selector = label.rsplit(".", 1)[-1]
                self.assertIsInstance(value.get(selector), str, label)
                option = next(
                    (item for item in constraints.get("options", []) if item["key"] == value[selector]),
                    None,
                )
                self.assertIsNotNone(option, label)
                nested_inputs = option["inputs"]
                nested_required = nested_inputs.get("required", {})
                nested_optional = nested_inputs.get("optional", {})
                allowed = {selector, *nested_required, *nested_optional}
                self.assertEqual(allowed, set(value), label)
                self.assertTrue(set(nested_required) <= set(value), label)
                for nested_name, nested_descriptor in (nested_required | nested_optional).items():
                    if nested_name in value:
                        validate_setting(value[nested_name], nested_descriptor, f"{label}.{nested_name}")
            else:
                self.fail(f"unsupported fragment setting type {input_type}: {label}")

        for article_id, (_directory, class_type, module, fingerprint, _recipe) in SPECS.items():
            node = nodes[class_type]
            self.assertEqual(module, node["python_module"])
            self.assertTrue(node["experimental"])
            self.assertFalse(node.get("deprecated", False))
            self.assertEqual(fingerprint, catalog.schema_fingerprint(class_type, node), article_id)
        expected_contracts = {
            "CreateBoundingBoxes": {
                "category": "utilities", "is_input_list": False, "output_node": True,
                "required": ["width", "height", "editor_state"],
                "optional": ["background", "bboxes", "last_incoming"],
                "output": ["IMAGE", "BOUNDING_BOX", "ARRAY"], "output_name": ["preview", "bboxes", "elements"],
            },
            "BuildJsonPromptIdeogram": {
                "category": "text", "is_input_list": False, "output_node": False,
                "required": ["element", "high_level_description", "background", "style", "aesthetics", "lighting", "medium", "color_palette"],
                "optional": [], "output": ["DICT"], "output_name": ["prompt"],
            },
            "TrainLoraNode": {
                "category": "model/training", "is_input_list": True, "output_node": False,
                "required": ["model", "latents", "positive", "batch_size", "grad_accumulation_steps", "steps", "learning_rate", "rank", "optimizer", "loss_function", "seed", "training_dtype", "lora_dtype", "quantized_backward", "algorithm", "gradient_checkpointing", "checkpoint_depth", "offloading", "existing_lora", "bucket_mode", "bypass_mode"],
                "optional": [], "output": ["LORA_MODEL", "LOSS_MAP", "INT"], "output_name": ["lora", "loss_map", "steps"],
            },
            "LoraModelLoader": {
                "category": "model/loaders", "is_input_list": False, "output_node": False,
                "required": ["model", "lora", "strength_model", "bypass"],
                "optional": [], "output": ["MODEL"], "output_name": ["model"],
            },
        }
        for class_type, expected in expected_contracts.items():
            node = nodes[class_type]
            self.assertEqual(expected["category"], node["category"])
            self.assertEqual(expected["is_input_list"], node["is_input_list"])
            self.assertEqual(expected["output_node"], node["output_node"])
            self.assertFalse(node["has_intermediate_output"])
            self.assertFalse(node.get("deprecated", False))
            self.assertTrue(node["experimental"])
            self.assertFalse(node.get("dev_only", False))
            self.assertFalse(node.get("api_node", False))
            self.assertEqual(expected["required"], list(node["input"].get("required", {})))
            self.assertEqual(expected["optional"], list(node["input"].get("optional", {})))
            self.assertEqual(expected["output"], node["output"])
            self.assertEqual(expected["output_name"], node["output_name"])
            self.assertEqual([False] * len(expected["output"]), node["output_is_list"])
        bbox = nodes["CreateBoundingBoxes"]
        self.assertTrue(bbox["output_node"])
        self.assertEqual(["IMAGE", "BOUNDING_BOX", "ARRAY"], bbox["output"])
        self.assertEqual(["preview", "bboxes", "elements"], bbox["output_name"])
        self.assertEqual("BOUNDING_BOX,ARRAY,STRING", bbox["input"]["optional"]["bboxes"][0])
        self.assertTrue(bbox["input"]["optional"]["last_incoming"][1]["socketless"])
        for dimension in ("width", "height"):
            self.assertEqual(
                {"default": 1024, "min": 64, "max": 16384, "step": 16},
                {key: bbox["input"]["required"][dimension][1][key] for key in ("default", "min", "max", "step")},
            )
        style = nodes["BuildJsonPromptIdeogram"]["input"]["required"]["style"]
        self.assertEqual("COMFY_DYNAMICCOMBO_V3", style[0])
        self.assertEqual(["none", "photo", "art_style"], [item["key"] for item in style[1]["options"]])
        train = nodes["TrainLoraNode"]
        self.assertTrue(train["is_input_list"])
        self.assertEqual(["LORA_MODEL", "LOSS_MAP", "INT"], train["output"])
        self.assertEqual(["LoRA", "LoHa", "LoKr", "OFT"], train["input"]["required"]["algorithm"][1]["options"])
        self.assertEqual((-100.0, 100.0), tuple(nodes["LoraModelLoader"]["input"]["required"]["strength_model"][1][key] for key in ("min", "max")))

        for directory in RECIPES.values():
            fragment = catalog.load_json(catalog.CONTENT / "recipes" / directory / "fragment.json")
            by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                target = by_ref[external["to"]]
                descriptor = input_descriptors(nodes[target["classType"]])
                self.assertEqual(external["type"], descriptor_type(descriptor[external["input"]]))
                supplied[external["to"]].add(external["input"])
            for link in fragment["connections"]:
                source_node = nodes[by_ref[link["from"]]["classType"]]
                target_node = nodes[by_ref[link["to"]]["classType"]]
                descriptors = input_descriptors(target_node)
                output_index = source_node["output_name"].index(link["output"])
                target_type = descriptor_type(descriptors[link["input"]])
                self.assertIn(target_type, (source_node["output"][output_index], "*"))
                supplied[link["to"]].add(link["input"])
            for ref, node in by_ref.items():
                runtime_node = nodes[node["classType"]]
                descriptors = input_descriptors(runtime_node)
                for setting_name, setting_value in node["settings"].items():
                    self.assertIn(setting_name, descriptors, (directory, ref, setting_name))
                    validate_setting(setting_value, descriptors[setting_name], f"{directory}.{ref}.{setting_name}")
                required = set(runtime_node.get("input", {}).get("required", {}))
                self.assertTrue(required <= supplied[ref], (directory, ref, required - supplied[ref]))
        replacement_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for spec in SPECS.values():
            self.assertNotIn(spec[1], replacement_text)

    def test_pinned_source_frontend_hashes_and_contracts(self) -> None:
        expected = {
            SOURCE / "comfy_extras" / "nodes_bounding_boxes.py": "d421d2b424db5d308bbcace6421e1d99e5dfbc2271164a5d69f77fbb5ade283d",
            SOURCE / "comfy_extras" / "nodes_json_prompt.py": "24b7a3b2456be45e4bfc45591890eb276fa0061fd53d7900fc969f9feefb554e",
            SOURCE / "comfy_extras" / "color_util.py": "89a329605d8ce87d90d13067ea0852cd2c493c521e06ad2276323a67fa89318e",
            SOURCE / "comfy_extras" / "nodes_train.py": "b95c59f1e7a0dc9e4ca2782377b571dc3ffe722d7d36eb08801526a9dfb34ae5",
            SOURCE / "comfy" / "sd.py": "51e72a263e8bd77812aefcebcf3cfaf9fda57150d763897b6d8b4890d7fee207",
            SOURCE / "comfy" / "weight_adapter" / "lora.py": "5e30c8b8a22be6459883cb5d758fa76f725cc4688d4048200145b885567c4cec",
            SOURCE / "comfy" / "weight_adapter" / "loha.py": "89c6750b772017f4b35190b9a75a9161fb2c502ae7cf1377a8ea448a728e7731",
            SOURCE / "comfy" / "weight_adapter" / "lokr.py": "ef39581b4f0a5f2eb1175542bf8f65ff74d5e02d5652f598fe96f047ecc7c299",
            SOURCE / "comfy" / "weight_adapter" / "oft.py": "e6b9c771d96dcde11a6dad62c37c5f062f3f9933452eed8b49c62589e38b9fff",
            SOURCE / "comfy_api" / "latest" / "_io.py": "1aec1852116daa2caf3361e0a41e58d5c9e2f3ae36b1d9d28bccce582feb9f14",
            SOURCE / "execution.py": "c47ebc80efb350568ee3d33b03efaf0fb27fc32ca723bfd9aa10ed591fdf75f2",
            FRONTEND / "src" / "extensions" / "core" / "createBoundingBoxes.ts": "32e2c1b962258601d121f6f43e143e204a2033fd02cdff64535cc9027cc6b5ac",
            FRONTEND / "src" / "composables" / "boundingBoxes" / "useBoundingBoxes.ts": "75883f8100b4b0df2182d8559f5c43cfcae5494194b1b181c8df501cc7cea748",
            FRONTEND / "src" / "components" / "palette" / "WidgetColors.vue": "f58d4f86acb84f4df0666a3dc914dbc7740e3245b687746fdfcd2dd7e0fd6cb8",
        }
        for path, digest in expected.items():
            self.assertTrue(path.is_file(), f"required pinned evidence absent: {path}")
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)
        bounding = (SOURCE / "comfy_extras" / "nodes_bounding_boxes.py").read_text(encoding="utf-8")
        for marker in ("frame = bboxes[0] if isinstance(bboxes[0], list) else []", "image[0].detach().cpu().numpy()", "upstream_changed = bool(incoming) and incoming != applied", "source = incoming if upstream_changed else (editor_state or [])", "palette[:5]"):
            self.assertIn(marker, bounding)
        prompt = (SOURCE / "comfy_extras" / "nodes_json_prompt.py").read_text(encoding="utf-8")
        self.assertIn('kind = style.get("style", "none") if isinstance(style, dict) else "none"', prompt)
        training = (SOURCE / "comfy_extras" / "nodes_train.py").read_text(encoding="utf-8")
        for marker in ("total_steps=steps * grad_accumulation_steps", "self.seed + i * 1000", "bucket_idx = torch.multinomial(self.bucket_weights, 1).item()", "relative_indices = torch.randperm(bucket_size)", "torch.rand((1,)).item()", 'loss_map = {"loss": []}', "comfy.model_management.training_fp8_bwd = quantized_backward", "return io.NodeOutput(lora_sd, loss_map, steps + existing_steps)"):
            self.assertIn(marker, training)
        self.assertRegex(training, r"if gradient_checkpointing:\s+modules_to_patch[\s\S]*?patch\(m, offloading=offloading\)")
        self.assertRegex(training, r"load_models_gpu\(\s*\[mp\], memory_required=1e20, force_full_load=not offloading\s*\)")
        self.assertNotIn("torch.manual_seed", training)

        adapter = (SOURCE / "comfy" / "weight_adapter" / "lora.py").read_text(encoding="utf-8")
        self.assertIn("torch.nn.init.kaiming_uniform_(mat1", adapter)
        loha = (SOURCE / "comfy" / "weight_adapter" / "loha.py").read_text(encoding="utf-8")
        self.assertIn("torch.nn.init.normal_(mat1, 0.1)", loha)
        lokr = (SOURCE / "comfy" / "weight_adapter" / "lokr.py").read_text(encoding="utf-8")
        self.assertIn("torch.nn.init.kaiming_uniform_(mat2", lokr)
        oft = (SOURCE / "comfy" / "weight_adapter" / "oft.py").read_text(encoding="utf-8")
        self.assertIn("block = torch.zeros(", oft)
        io_source = (SOURCE / "comfy_api" / "latest" / "_io.py").read_text(encoding="utf-8")
        for marker in ("def get_finalized_class_inputs", "def build_nested_inputs", "out_dict[\"dynamic_paths\"][finalized_id]"):
            self.assertIn(marker, io_source)
        execution = (SOURCE / "execution.py").read_text(encoding="utf-8")
        self.assertIn('input_is_list = getattr(obj, "INPUT_IS_LIST", False)', execution)
        self.assertIn("inputs = _io.build_nested_inputs(inputs, v3_data)", execution)
        self.assertIn("await process_inputs(input_data_all, 0, input_is_list=input_is_list)", execution)

        extension = (FRONTEND / "src" / "extensions" / "core" / "createBoundingBoxes.ts").read_text(encoding="utf-8")
        self.assertIn("const hidden = slot >= 0 && node.isInputConnected(slot)", extension)
        widget = (FRONTEND / "src" / "composables" / "boundingBoxes" / "useBoundingBoxes.ts").read_text(encoding="utf-8")
        for marker in ("getNodeImageUrls(inputNode)?.[0]", "if (!url)", "Math.max(DIMENSION_STEP, Math.round(v / DIMENSION_STEP) * DIMENSION_STEP)", "applyImageDimensions(img.naturalWidth, img.naturalHeight)"):
            self.assertIn(marker, widget)
        self.assertNotRegex(widget, r"Math\.min\([^\n]*16384")

    def test_pinned_docs_hashes_and_recorded_limitations(self) -> None:
        self.assertTrue(DOCS.is_file(), f"required pinned evidence absent: {DOCS}")
        self.assertEqual("30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c", hashlib.sha256(DOCS.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS) as archive:
            for class_type, locales in DOC_HASHES.items():
                for locale, digest in locales.items():
                    member = "comfyui_embedded_docs/docs/" + class_type + "/" + locale + ".md"
                    self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest(), member)
            ideogram_docs = archive.read("comfyui_embedded_docs/docs/BuildJsonPromptIdeogram/en.md").decode("utf-8")
            self.assertIn("The `background`, `aesthetics`, `lighting`, and `medium` parameters", ideogram_docs)
            self.assertIn("considered mandatory", ideogram_docs)
            self.assertIn("GradScaler", archive.read("comfyui_embedded_docs/docs/TrainLoraNode/en.md").decode("utf-8"))
        ideogram_article = (article_path("core.build-json-prompt-ideogram").parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn("`background`, `aesthetics`, `lighting` и `medium` технически имеют пустые значения", ideogram_article)
        self.assertIn("прямую и через `/prompt`", ideogram_article)
        train_article = (article_path("core.train-lora-node").parent / "ru.md").read_text(encoding="utf-8")
        self.assertIn('`LOSS_MAP` вида `{"loss": [...]}`', train_article)
        self.assertIn("список результатов предыдущей ноды", train_article)
        self.assertIn("torch.manual_seed", train_article)
        self.assertIn("только при одновременном включении `gradient_checkpointing`", train_article)

    def test_full_workflow_census_and_exact_ideogram_topology(self) -> None:
        self.assertTrue(WORKFLOWS.is_file(), f"required pinned evidence absent: {WORKFLOWS}")
        self.assertEqual("242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3", hashlib.sha256(WORKFLOWS.read_bytes()).hexdigest())
        targets = {spec[1] for spec in SPECS.values()}
        counts = Counter()
        scopes = Counter()
        json_count = roots = subgraphs = node_count = 0
        exact = None
        with zipfile.ZipFile(WORKFLOWS) as archive:
            for member in sorted(name for name in archive.namelist() if "/templates/" in name and name.endswith(".json")):
                json_count += 1
                payload = json.loads(archive.read(member))
                if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
                    roots += 1
                definitions = payload.get("definitions", {}) if isinstance(payload, dict) else {}
                if isinstance(definitions, dict):
                    subgraphs += sum(isinstance(item, dict) for item in definitions.get("subgraphs", []))
                for scope, graph in graph_scopes(payload):
                    nodes = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    node_count += len(nodes)
                    links = {tuple(link[1:6]) for link in graph.get("links", []) if isinstance(link, list) and len(link) >= 6}
                    for node in nodes.values():
                        if node.get("type") in targets:
                            counts[node["type"]] += 1
                            scopes[(node["type"], scope)] += 1
                    if member.endswith("api_ideogram_p_image_t2i.json") and scope == "root":
                        exact = nodes, links
        self.assertEqual((512, 496, 272, 8120), (json_count, roots, subgraphs, node_count))
        self.assertEqual({"CreateBoundingBoxes": 1, "BuildJsonPromptIdeogram": 1}, dict(counts))
        self.assertEqual(1, scopes[("CreateBoundingBoxes", "root")])
        self.assertEqual(1, scopes[("BuildJsonPromptIdeogram", "root")])
        self.assertIsNotNone(exact)
        nodes, links = exact or ({}, set())
        self.assertEqual(
            {4: "PreviewAny", 9: "CreateBoundingBoxes", 11: "IdeogramPImage", 12: "BuildJsonPromptIdeogram", 13: "SaveImageAdvanced"},
            {node_id: node["type"] for node_id, node in nodes.items()},
        )
        self.assertEqual({4: 2, 9: 0, 11: 3, 12: 1, 13: 4}, {node_id: node["order"] for node_id, node in nodes.items()})
        self.assertTrue(all(node["mode"] == 0 for node in nodes.values()))
        self.assertEqual(
            {
                (4, 0, 11, 0, "STRING"),
                (12, 0, 4, 0, "DICT"),
                (11, 0, 13, 0, "IMAGE"),
                (9, 2, 12, 0, "ARRAY"),
            },
            links,
        )

        fragment = catalog.load_json(catalog.CONTENT / "recipes" / "ideogram-layout-json-prompt" / "fragment.json")
        fragment_nodes = {node["ref"]: node for node in fragment["nodes"]}
        self.assertEqual(["CreateBoundingBoxes", "BuildJsonPromptIdeogram", "PreviewAny"], [node["classType"] for node in fragment["nodes"]])
        self.assertEqual([], fragment["externalInputs"])
        self.assertEqual(
            [
                {"from": "boxes", "output": "elements", "to": "build", "input": "element"},
                {"from": "build", "output": "prompt", "to": "preview", "input": "source"},
            ],
            fragment["connections"],
        )

        box_settings = fragment_nodes["boxes"]["settings"]
        official_box_settings = nodes[9]["widgets_values_named"]
        self.assertEqual([], official_box_settings["last_incoming"])
        self.assertEqual(box_settings, {key: official_box_settings[key] for key in ("width", "height", "editor_state")})
        self.assertEqual([box_settings["width"], box_settings["height"], box_settings["editor_state"], []], nodes[9]["widgets_values"])

        build_settings = dict(fragment_nodes["build"]["settings"])
        nested_style = build_settings.pop("style")
        official_build_settings = dict(build_settings)
        official_build_settings["style"] = nested_style["style"]
        official_build_settings["style.photo"] = nested_style["photo"]
        self.assertEqual(official_build_settings, nodes[12]["widgets_values_named"])
        self.assertEqual(
            [
                official_build_settings["high_level_description"], official_build_settings["background"],
                "photo", "editorial", official_build_settings["aesthetics"],
                official_build_settings["lighting"], official_build_settings["medium"],
                official_build_settings["color_palette"],
            ],
            nodes[12]["widgets_values"],
        )
        self.assertEqual({}, fragment_nodes["preview"]["settings"])
        self.assertEqual(([], {}), (nodes[4]["widgets_values"], nodes[4]["widgets_values_named"]))
        self.assertEqual(
            ["", "MEDIUM", "1K", "1:1", "AUTO", 1290088285, "randomize"],
            nodes[11]["widgets_values"],
        )
        self.assertEqual(
            {
                "prompt": "", "quality": "MEDIUM", "resolution": "1K", "aspect_ratio": "1:1",
                "prompt_upsampling": "AUTO", "seed": 1290088285, "control_after_generate": "randomize",
            },
            nodes[11]["widgets_values_named"],
        )
        self.assertEqual(
            ["Ideogram_P-Image", "png", "8-bit", "sRGB"],
            nodes[13]["widgets_values"],
        )
        self.assertEqual(
            {"filename_prefix": "Ideogram_P-Image", "format": "png", "format.bit_depth": "8-bit", "format.input_color_space": "sRGB"},
            nodes[13]["widgets_values_named"],
        )

    def test_safe_exact_source_probe(self) -> None:
        self.assertTrue(SOURCE.is_dir(), f"required pinned evidence absent: {SOURCE}")
        self.assertTrue(PROBE.is_file(), f"probe absent: {PROBE}")
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        self.assertIsNotNone(executable)
        result = subprocess.run(
            [str(executable), "-X", "utf8", str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT, capture_output=True, text=True, encoding="utf-8",
            timeout=120, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + "\n" + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([1, 100, 100, 3], report["bbox"]["previewShape"])
        self.assertEqual(-40, report["bbox"]["frame"][0][0]["x"])
        self.assertEqual([200, 0, 600, 0], report["bbox"]["elements"][0]["bbox"])
        self.assertEqual(5, len(report["bbox"]["elements"][0]["color_palette"]))
        self.assertEqual({"x": -10, "y": 20, "width": 90, "height": 220}, {key: report["bbox"]["converted"][0][key] for key in ("x", "y", "width", "height")})
        expected_first_box = [{"x": 1, "y": 2, "width": 3, "height": 4}]
        self.assertEqual({name: expected_first_box for name in ("dict", "dictJson", "nested", "nestedJson")}, report["bbox"]["inputFormats"])
        self.assertEqual([63, 63, 63], report["bbox"]["backgroundFirstPixel"])
        self.assertEqual(-40, report["bbox"]["incoming"][0][0]["x"])
        self.assertEqual([{"x": 10, "y": 10, "width": 10, "height": 10}], report["bbox"]["editor"][0])
        self.assertEqual([{"x": 10, "y": 10, "width": 10, "height": 10}], report["bbox"]["empty"][0])
        self.assertTrue(report["bbox"]["uiIncoming"])
        self.assertEqual("  title  ", report["json"]["none"]["high_level_description"])
        self.assertNotIn("style_description", report["json"]["none"])
        self.assertEqual(["#ABC", "BAD"], report["json"]["photo"]["style_description"]["color_palette"])
        self.assertEqual("ink", report["json"]["art"]["style_description"]["art_style"])
        self.assertNotIn("style_description", report["json"]["string"])
        self.assertEqual(
            ["aesthetics", "background", "color_palette", "element", "high_level_description", "lighting", "medium", "style", "style.photo"],
            report["json"]["v3FlatFinalRequired"],
        )
        self.assertIsNone(report["json"]["v3FlatHidden"])
        self.assertEqual({"style": "style.style", "style.photo": "style.photo"}, report["json"]["v3FlatPaths"])
        self.assertEqual({"style": "photo", "photo": "editorial"}, report["json"]["v3MaterializedStyle"])
        self.assertEqual("editorial", report["json"]["v3MaterializedResult"]["style_description"]["photo"])
        self.assertNotIn("style", report["json"]["v3NestedFinalRequired"])
        self.assertIsNone(report["json"]["v3NestedHidden"])
        self.assertEqual({}, report["json"]["v3NestedPaths"])
        self.assertEqual([2, 4, 8, 8], report["train"]["oneShape"])
        self.assertEqual([[1, 4, 8, 8], [1, 4, 8, 8], [1, 4, 8, 8]], report["train"]["equalShapes"])
        self.assertEqual([[1, 4, 8, 8], [1, 4, 6, 8]], report["train"]["unequalShapes"])
        self.assertEqual([[3, 4, 8, 8], 3, False], report["train"]["equalPrepared"])
        self.assertEqual([2, 2, True], report["train"]["unequalPrepared"])
        self.assertEqual(3, report["train"]["expanded"])
        self.assertEqual("ValueError", report["train"]["mismatch"])
        self.assertEqual([[2, 4, 8, 8], [1, 4, 6, 8]], report["train"]["bucketShapes"])
        self.assertEqual([[[2, 4, 8, 8], [1, 4, 6, 8]], 3, False], report["train"]["bucketPrepared"])
        self.assertEqual([["only"]], report["train"]["bucketConditioning"])
        self.assertEqual([0, 2, 3], report["train"]["bucketOffsets"])
        self.assertEqual([2.0, 1.0], report["train"]["bucketWeights"])
        bucket = report["train"]["bucketPostfix"]["bucket"]
        start, end = report["train"]["bucketOffsets"][bucket:bucket + 2]
        bucket_call = report["train"]["bucketCall"]
        self.assertEqual(3, bucket_call["datasetSize"])
        self.assertEqual(end - start, bucket_call["batchShape"][0])
        self.assertEqual(end - start, bucket_call["sigmaCount"])
        self.assertTrue(all(start <= index < end for index in bucket_call["indices"]))
        self.assertEqual((True, True, 3, {"tag": "probe"}), (bucket_call["bwd"], bucket_call["noiseIsZero"], bucket_call["conditionCount"], bucket_call["extraArgs"]))
        self.assertEqual(([0.25], "0.2500"), (report["train"]["bucketLosses"], report["train"]["bucketPostfix"]["loss"]))
        self.assertTrue(report["train"]["nodeSeedIgnoredForSigmas"])
        self.assertTrue(report["train"]["adapterSameGlobalRng"])
        self.assertTrue(report["train"]["adapterChangedGlobalRng"])
        self.assertEqual([{}, 0], report["train"]["noneExisting"])
        self.assertTrue(report["loader"]["zeroIdentity"])
        self.assertEqual(("standard-model", "bypass-model"), (report["loader"]["regular"], report["loader"]["bypass"]))
        self.assertEqual(["standard", "bypass"], [call["kind"] for call in report["loader"]["calls"]])
        self.assertTrue(all(call["clip"] is None and call["strength_clip"] == 0 for call in report["loader"]["calls"]))
        self.assertEqual([0.5, -2.0], [call["strength_model"] for call in report["loader"]["calls"]])


if __name__ == "__main__":
    unittest.main()
