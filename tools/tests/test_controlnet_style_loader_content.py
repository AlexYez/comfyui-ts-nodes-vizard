from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import re
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import torch

from tools import catalog


ARTICLE_SPECS = {
    "core.control-net-apply-advanced": {
        "directory": "control-net-apply-advanced",
        "classType": "ControlNetApplyAdvanced",
        "fingerprint": "sha256:e8b4b1fe144b82dcca53b381235c5621aa1db99b825b14675010f0dc7f9863a6",
        "recipe": "recipe.chain-two-controlnets-advanced",
    },
    "core.control-net-loader": {
        "directory": "control-net-loader",
        "classType": "ControlNetLoader",
        "fingerprint": "sha256:13f2e18be93c46b84477a68f82c99ae04c534187f5066ba4bd1b2d877fbd717d",
        "recipe": "recipe.apply-controlnet-canny",
    },
    "core.diff-control-net-loader": {
        "directory": "diff-control-net-loader",
        "classType": "DiffControlNetLoader",
        "fingerprint": "sha256:075402665a87661da8ab0473a7248e63687a11a8db724f22b27d5802e7308385",
        "recipe": "recipe.load-diff-controlnet-with-model",
    },
    "core.style-model-loader": {
        "directory": "style-model-loader",
        "classType": "StyleModelLoader",
        "fingerprint": "sha256:3364d60b628d3d6db7eb9c3f8fb46723927a03cfce12120448ad113f3babff45",
        "recipe": "recipe.apply-style-model-reference",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.apply-controlnet-canny": "apply-controlnet-canny",
    "recipe.chain-two-controlnets-advanced": "chain-two-controlnets-advanced",
    "recipe.load-diff-controlnet-with-model": "load-diff-controlnet-with-model",
    "recipe.apply-style-model-reference": "apply-style-model-reference",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.apply-controlnet-canny": [
        ("ControlNetLoader", {"control_net_name": "выберите совместимый Canny ControlNet"}),
        ("ControlNetApplyAdvanced", {"strength": 0.66, "start_percent": 0.0, "end_percent": 1.0}),
    ],
    "recipe.chain-two-controlnets-advanced": [
        ("ControlNetApplyAdvanced", {"strength": 0.75, "start_percent": 0.0, "end_percent": 0.65}),
        ("ControlNetApplyAdvanced", {"strength": 0.55, "start_percent": 0.35, "end_percent": 1.0}),
    ],
    "recipe.load-diff-controlnet-with-model": [
        ("DiffControlNetLoader", {"control_net_name": "выберите diff-ControlNet для этой MODEL"}),
        ("ControlNetApplyAdvanced", {"strength": 1.0, "start_percent": 0.0, "end_percent": 1.0}),
    ],
    "recipe.apply-style-model-reference": [
        ("CLIPVisionLoader", {"clip_name": "sigclip_vision_patch14_384.safetensors"}),
        ("CLIPVisionEncode", {"crop": "center"}),
        ("StyleModelLoader", {"style_model_name": "flux1-redux-dev.safetensors"}),
        ("StyleModelApply", {"strength": 1.0, "strength_type": "multiply"}),
    ],
}

SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def graph_records(payload: dict[str, Any], member: str) -> Iterator[dict[str, Any]]:
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {"member": member, "workflowId": payload.get("id"), "scope": "root", "node": node}
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": payload.get("id"),
                    "scope": "subgraph",
                    "subgraphId": subgraph.get("id"),
                    "node": node,
                }


def extract_node_classes(namespace: dict[str, Any]) -> dict[str, type]:
    path = SOURCE / "nodes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"ControlNetApplyAdvanced", "ControlNetLoader", "DiffControlNetLoader"}
    body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in wanted}


def extract_style_loader(namespace: dict[str, Any]) -> Any:
    path = SOURCE / "comfy" / "sd.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [
        node
        for node in tree.body
        if (isinstance(node, ast.ClassDef) and node.name == "StyleModel")
        or (isinstance(node, ast.FunctionDef) and node.name == "load_style_model")
    ]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["load_style_model"]


class ControlNetStyleLoaderContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_russian_contract(self) -> None:
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])
            relations = article["relations"]
            targets = relations["related"] + relations["alternatives"]
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, targets - article_ids if isinstance(targets, set) else targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            semantic_h2 = [h for h in re.findall(r"^## (.+)$", body, flags=re.MULTILINE) if h != "Источники"]
            self.assertEqual(10, len(semantic_h2), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|в современном мире|революционн|"
                r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
                r"не просто .{0,80}, а",
            )
            for source in article["sources"]:
                url = source["url"]
                if "github.com/Comfy-Org/ComfyUI/" in url:
                    self.assertIn("c2bcbecd82ec5ae66594340b395c24ef0217b238", url)
                if "github.com/Comfy-Org/embedded-docs/" in url:
                    self.assertIn("1d258cf6e374d60d138a2bfcd273c7e11f750ef9", url)
                if "github.com/Comfy-Org/workflow_templates/" in url:
                    self.assertIn("cca1ea5ea4560108ecc2f44dee951f41ea433062", url)

            ledger = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema))
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["knownGaps"])

        self.assertEqual([], errors)

        recipe_errors: list[str] = []
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = catalog.CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("draft", recipe["editorial"]["state"])
            self.assertTrue(set(recipe["articleIds"]).issubset(article_ids))
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            catalog.validate_fragment(path.parent / recipe["fragment"]["path"], fragment, recipe_errors)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
            refs = {node["ref"] for node in fragment["nodes"]}
            self.assertTrue(all(item["to"] in refs for item in fragment["externalInputs"]))
            self.assertTrue(all(edge["from"] in refs and edge["to"] in refs for edge in fragment["connections"]))
        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_and_schema_fingerprints(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual("nodes", definition["python_module"])
            self.assertFalse(definition.get("deprecated", False))
            self.assertFalse(definition.get("experimental", False))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))

        apply_inputs = inventory["ControlNetApplyAdvanced"]["input"]
        self.assertEqual(
            ["positive", "negative", "control_net", "image", "strength", "start_percent", "end_percent"],
            inventory["ControlNetApplyAdvanced"]["input_order"]["required"],
        )
        self.assertEqual(["vae"], inventory["ControlNetApplyAdvanced"]["input_order"]["optional"])
        self.assertEqual((0.0, 10.0, 0.01), tuple(apply_inputs["required"]["strength"][1][k] for k in ("min", "max", "step")))
        for key in ("start_percent", "end_percent"):
            self.assertEqual((0.0, 1.0, 0.001), tuple(apply_inputs["required"][key][1][k] for k in ("min", "max", "step")))
        self.assertEqual(["CONDITIONING", "CONDITIONING"], inventory["ControlNetApplyAdvanced"]["output"])

        self.assertEqual(["control_net_name"], inventory["ControlNetLoader"]["input_order"]["required"])
        self.assertEqual(["model", "control_net_name"], inventory["DiffControlNetLoader"]["input_order"]["required"])
        self.assertEqual(["style_model_name"], inventory["StyleModelLoader"]["input_order"]["required"])
        self.assertEqual(["CONTROL_NET"], inventory["ControlNetLoader"]["output"])
        self.assertEqual(["CONTROL_NET"], inventory["DiffControlNetLoader"]["output"])
        self.assertEqual(["STYLE_MODEL"], inventory["StyleModelLoader"]["output"])

    def test_exact_apply_and_loader_methods_on_synthetic_objects(self) -> None:
        calls: list[tuple[Any, ...]] = []
        load_result: list[Any] = [object()]

        def load_controlnet(*args: Any) -> Any:
            calls.append(args)
            return load_result[0]

        namespace: dict[str, Any] = {
            "folder_paths": SimpleNamespace(
                get_filename_list=lambda _category: [],
                get_full_path_or_raise=lambda category, name: f"/{category}/{name}",
            ),
            "comfy": SimpleNamespace(controlnet=SimpleNamespace(load_controlnet=load_controlnet)),
        }
        classes = extract_node_classes(namespace)

        regular = classes["ControlNetLoader"]()
        expected = load_result[0]
        self.assertIs(expected, regular.load_controlnet("regular.safetensors")[0])
        self.assertEqual(("/controlnet/regular.safetensors",), calls[-1])
        load_result[0] = None
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            regular.load_controlnet("broken.safetensors")

        load_result[0] = object()
        model = object()
        diff = classes["DiffControlNetLoader"]()
        self.assertIs(load_result[0], diff.load_controlnet(model, "difference.pth")[0])
        self.assertEqual(("/controlnet/difference.pth", model), calls[-1])

        class FakeControl:
            def __init__(self) -> None:
                self.hint: Any = None
                self.strength: float | None = None
                self.window: tuple[float, float] | None = None
                self.vae: Any = None
                self.previous: Any = None

            def copy(self) -> "FakeControl":
                return FakeControl()

            def set_cond_hint(self, hint: Any, strength: float, window: tuple[float, float], vae: Any = None, extra_concat: list[Any] | None = None) -> "FakeControl":
                self.hint, self.strength, self.window, self.vae = hint, strength, window, vae
                return self

            def set_previous_controlnet(self, previous: Any) -> "FakeControl":
                self.previous = previous
                return self

        method = classes["ControlNetApplyAdvanced"]().apply_controlnet
        tensor = torch.tensor([[1.0]])
        image = torch.zeros((1, 5, 7, 3))
        previous = FakeControl()
        positive = [[tensor, {"control": previous, "branch": "positive"}]]
        negative = [[tensor, {"control": previous, "branch": "negative"}]]
        vae = object()
        out_positive, out_negative = method(positive, negative, FakeControl(), image, 0.8, 0.2, 0.9, vae=vae)
        self.assertIs(tensor, out_positive[0][0])
        self.assertIsNot(positive[0][1], out_positive[0][1])
        new_control = out_positive[0][1]["control"]
        self.assertIs(new_control, out_negative[0][1]["control"])
        self.assertIs(previous, new_control.previous)
        self.assertEqual((1, 3, 5, 7), tuple(new_control.hint.shape))
        self.assertEqual((0.8, (0.2, 0.9), vae), (new_control.strength, new_control.window, new_control.vae))
        self.assertFalse(out_positive[0][1]["control_apply_to_uncond"])
        self.assertFalse(out_negative[0][1]["control_apply_to_uncond"])
        zero_positive, zero_negative = method(positive, negative, FakeControl(), image, 0.0, 0.0, 1.0)
        self.assertIs(positive, zero_positive)
        self.assertIs(negative, zero_negative)

    def test_style_format_dispatch_from_pinned_function(self) -> None:
        marker: dict[str, Any] = {}

        class FakeStyleAdapter:
            def __init__(self, **kwargs: Any) -> None:
                marker["adapter_args"] = kwargs

            def load_state_dict(self, state: dict[str, Any]) -> None:
                marker["loaded"] = state

        class FakeRedux:
            def __init__(self) -> None:
                marker["redux"] = True

            def load_state_dict(self, state: dict[str, Any]) -> None:
                marker["loaded"] = state

        states: list[dict[str, Any]] = [{"style_embedding": object()}]
        fake_comfy = SimpleNamespace(
            utils=SimpleNamespace(load_torch_file=lambda _path, safe_load: states[0]),
            t2i_adapter=SimpleNamespace(adapter=SimpleNamespace(StyleAdapter=FakeStyleAdapter)),
            ldm=SimpleNamespace(flux=SimpleNamespace(redux=SimpleNamespace(ReduxImageEncoder=FakeRedux))),
        )
        load_style_model = extract_style_loader({"comfy": fake_comfy})
        style = load_style_model("legacy.safetensors")
        self.assertIsInstance(style.model, FakeStyleAdapter)
        self.assertEqual(
            {"width": 1024, "context_dim": 768, "num_head": 8, "n_layes": 3, "num_token": 8},
            marker["adapter_args"],
        )
        states[0] = {"redux_down.weight": object()}
        redux = load_style_model("redux.safetensors")
        self.assertIsInstance(redux.model, FakeRedux)
        states[0] = {"other": object()}
        with self.assertRaisesRegex(Exception, "invalid style model"):
            load_style_model("invalid.safetensors")

    def test_pinned_source_and_embedded_docs_boundaries(self) -> None:
        nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        controlnet = (SOURCE / "comfy" / "controlnet.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        cache = (SOURCE / "comfy_execution" / "caching.py").read_text(encoding="utf-8")
        self.assertIn("class ControlNetApplyAdvanced:", nodes)
        self.assertIn("prev_cnet = d.get('control', None)", nodes)
        self.assertIn("d['control_apply_to_uncond'] = False", nodes)
        self.assertIn("class ControlNetLoader:", nodes)
        self.assertIn("class DiffControlNetLoader:", nodes)
        self.assertIn("comfy.controlnet.load_controlnet(controlnet_path, model)", nodes)
        self.assertIn("if 'difference' in controlnet_data:", controlnet)
        self.assertIn("cd += model_sd[sd_key]", controlnet)
        self.assertIn("self.cond_hint = self.vae.encode", controlnet)
        self.assertIn("This Controlnet needs a VAE but none was provided", controlnet)
        self.assertIn('if "style_embedding" in keys:', sd)
        self.assertIn('elif "redux_down.weight" in keys:', sd)
        self.assertIn('signature = [class_type, await self.is_changed_cache.get(node_id)]', cache)

        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            aliases = {
                "ControlNetApplyAdvanced": "ControlnetApplyAdvanced",
                "ControlNetLoader": "ControlnetLoader",
                "DiffControlNetLoader": "DiffControlnetLoader",
            }
            for class_type, alias in aliases.items():
                self.assertNotIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                path = f"comfyui_embedded_docs/docs/{alias}/en.md"
                self.assertIn(path, names)
                self.assertIn("AI-generated", archive.read(path).decode("utf-8"))
            self.assertIn("comfyui_embedded_docs/docs/StyleModelLoader/en.md", names)

    def test_workflow_wheel_integrity_census_and_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        root_graphs = 0
        subgraphs = 0
        json_members = 0
        payloads_by_basename: dict[str, dict[str, Any]] = {}
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            self.assertEqual(517, len(rows))
            checked = 0
            for name, digest, size in rows:
                if not digest:
                    self.assertEqual(record_name, name)
                    continue
                algorithm, encoded = digest.split("=", 1)
                self.assertEqual("sha256", algorithm)
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                data = archive.read(name)
                self.assertEqual(expected, hashlib.sha256(data).digest())
                self.assertEqual(int(size), len(data))
                checked += 1
            self.assertEqual(516, checked)

            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_members += 1
                payload = json.loads(archive.read(member))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                payloads_by_basename[Path(member).name] = payload
                definitions = payload.get("definitions")
                if isinstance(definitions, dict) and isinstance(definitions.get("subgraphs"), list):
                    subgraphs += len(definitions["subgraphs"])
                for record in graph_records(payload, member):
                    if record["node"].get("type") in TARGET_TYPES:
                        records.append(record)

        self.assertEqual((512, 496, 272), (json_members, root_graphs, subgraphs))
        expected = {
            "ControlNetApplyAdvanced": (5, 3, 2, 5, 4, Counter({0: 5})),
            "ControlNetLoader": (7, 5, 2, 6, 4, Counter({0: 6, 4: 1})),
            "DiffControlNetLoader": (0, 0, 0, 0, 0, Counter()),
            "StyleModelLoader": (1, 1, 0, 1, 1, Counter({0: 1})),
        }
        for class_type, values in expected.items():
            matches = [record for record in records if record["node"]["type"] == class_type]
            actual = (
                len(matches),
                sum(record["scope"] == "root" for record in matches),
                sum(record["scope"] == "subgraph" for record in matches),
                len({record["member"] for record in matches}),
                len({record["workflowId"] for record in matches}),
                Counter(record["node"].get("mode") for record in matches),
            )
            self.assertEqual(values, actual, class_type)

        apply_widgets = Counter(tuple(record["node"]["widgets_values"]) for record in records if record["node"]["type"] == "ControlNetApplyAdvanced")
        self.assertEqual(Counter({(1, 0, 1): 3, (0.66, 0, 1): 1, (0.7000000000000002, 0, 1): 1}), apply_widgets)
        apply_records = [record for record in records if record["node"]["type"] == "ControlNetApplyAdvanced"]
        self.assertTrue(
            all(
                any(item.get("name") == "vae" and item.get("link") is not None for item in record["node"].get("inputs", []))
                for record in apply_records
            )
        )
        self.assertEqual(
            len(apply_records),
            len({(record["member"], record["scope"], record.get("subgraphId")) for record in apply_records}),
            "Pinned wheel has no Advanced-to-Advanced chain in one graph scope",
        )
        loader_widgets = Counter(
            tuple(record["node"]["widgets_values"])
            for record in records
            if record["node"]["type"] == "ControlNetLoader"
        )
        self.assertEqual(
            Counter(
                {
                    ("Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors",): 1,
                    ("Qwen-Image-InstantX-ControlNet-Union.safetensors",): 1,
                    ("Qwen-Image-InstantX-ControlNet-Inpainting.safetensors",): 2,
                    ("sd3.5_large_controlnet_blur.safetensors",): 1,
                    ("sd3.5_large_controlnet_canny.safetensors",): 1,
                    ("sd3.5_large_controlnet_depth.safetensors",): 1,
                }
            ),
            loader_widgets,
        )
        style = next(record for record in records if record["node"]["type"] == "StyleModelLoader")
        self.assertEqual(["flux1-redux-dev.safetensors"], style["node"]["widgets_values"])

        canny = payloads_by_basename["sd3.5_large_canny_controlnet_example.json"]
        by_id = {node["id"]: node for node in canny["nodes"]}
        links = {link[0]: link for link in canny["links"]}
        self.assertEqual("ControlNetLoader", by_id[46]["type"])
        self.assertEqual(["sd3.5_large_controlnet_canny.safetensors"], by_id[46]["widgets_values"])
        self.assertEqual([0.66, 0, 1], by_id[51]["widgets_values"])
        self.assertEqual([100, 46, 0, 51, 2, "CONTROL_NET"], links[100])
        self.assertEqual([99, 47, 0, 51, 3, "IMAGE"], links[99])
        self.assertEqual([105, 4, 2, 51, 4, "VAE"], links[105])
        self.assertEqual([103, 51, 0, 3, 1, "CONDITIONING"], links[103])
        self.assertEqual([104, 51, 1, 3, 2, "CONDITIONING"], links[104])

        redux = payloads_by_basename["flux_redux_model_example.json"]
        redux_nodes = {node["id"]: node for node in redux["nodes"]}
        redux_links = {link[0]: link for link in redux["links"]}
        self.assertEqual(["flux1-redux-dev.safetensors"], redux_nodes[42]["widgets_values"])
        self.assertEqual([1, "multiply"], redux_nodes[41]["widgets_values"])
        self.assertEqual([1, "multiply"], redux_nodes[45]["widgets_values"])
        self.assertEqual([119, 42, 0, 41, 1, "STYLE_MODEL"], redux_links[119])
        self.assertEqual([125, 42, 0, 45, 1, "STYLE_MODEL"], redux_links[125])
        self.assertEqual([129, 41, 0, 45, 0, "CONDITIONING"], redux_links[129])


if __name__ == "__main__":
    unittest.main()
