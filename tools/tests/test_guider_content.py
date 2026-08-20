from __future__ import annotations

import hashlib
import json
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
    "core.basic-guider": {
        "directory": "basic-guider",
        "classType": "BasicGuider",
        "fingerprint": "sha256:0683f804654dbd15bdb740dc4f39c976b85b4fbe388d6e21310926d1855525be",
        "recipe": "recipe.basic-guidance-custom-sampling",
        "required": {
            "model": ["MODEL", {}],
            "conditioning": ["CONDITIONING", {}],
        },
        "optional": {},
        "experimental": False,
        "searchAliases": None,
    },
    "core.cfg-guider": {
        "directory": "cfg-guider",
        "classType": "CFGGuider",
        "fingerprint": "sha256:d530e8a2677744e82d15018b1a3e4642acce83a73ff385811960dd66fa4d701b",
        "recipe": "recipe.cfg-guidance-custom-sampling",
        "required": {
            "model": ["MODEL", {}],
            "positive": ["CONDITIONING", {}],
            "negative": ["CONDITIONING", {}],
            "cfg": [
                "FLOAT",
                {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01},
            ],
        },
        "optional": {},
        "experimental": False,
        "searchAliases": None,
    },
    "core.dual-cfg-guider": {
        "directory": "dual-cfg-guider",
        "classType": "DualCFGGuider",
        "fingerprint": "sha256:f7494f04202bf60700ef80108f6e0ec370b656a9d4e1a3bc4781b363a53aaa1a",
        "recipe": "recipe.dual-cfg-regular-guidance",
        "required": {
            "model": ["MODEL", {}],
            "cond1": ["CONDITIONING", {}],
            "cond2": ["CONDITIONING", {}],
            "negative": ["CONDITIONING", {}],
            "cfg_conds": [
                "FLOAT",
                {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01},
            ],
            "cfg_cond2_negative": [
                "FLOAT",
                {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01},
            ],
            "style": [
                "COMBO",
                {"multiselect": False, "options": ["regular", "nested"]},
            ],
        },
        "optional": {},
        "experimental": False,
        "searchAliases": ["dual prompt guidance"],
    },
    "core.dual-model-guider": {
        "directory": "dual-model-guider",
        "classType": "DualModelGuider",
        "fingerprint": "sha256:376e3f9392576aa4e52f9aaa9baeb8f6e6d3165b622f1ec914d97ddd3a4323e3",
        "recipe": "recipe.dual-model-cfg-guidance",
        "required": {
            "model": ["MODEL", {"tooltip": "Model used for the positive (conditional) pass."}],
            "positive": ["CONDITIONING", {}],
            "cfg": [
                "FLOAT",
                {"default": 4.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01},
            ],
        },
        "optional": {
            "model_negative": [
                "MODEL",
                {"tooltip": "Model used for the negative (unconditional) pass. Use the same model for ordinary CFG."},
            ],
            "negative": [
                "CONDITIONING",
                {"tooltip": "Negative conditioning run on the negative model. Leave unconnected for a text-free (image-only) unconditional pass."},
            ],
        },
        "experimental": True,
        "searchAliases": None,
    },
}

RECIPE_DIRECTORIES = {
    "recipe.basic-guidance-custom-sampling": "basic-guidance-custom-sampling",
    "recipe.cfg-guidance-custom-sampling": "cfg-guidance-custom-sampling",
    "recipe.dual-cfg-regular-guidance": "dual-cfg-regular-guidance",
    "recipe.dual-model-cfg-guidance": "dual-model-cfg-guidance",
}

TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_META = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("guider_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            ids.add(payload["articleId"])
    return ids


def iter_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield f"subgraph:{index}", subgraph


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
                    "id": link[0],
                    "origin_id": link[1],
                    "origin_slot": link[2],
                    "target_id": link[3],
                    "target_slot": link[4],
                    "type": link[5],
                }
            )
        elif isinstance(link, dict):
            result.append(link)
    return result


def incoming_types(graph: dict[str, Any], node: dict[str, Any]) -> dict[str, str]:
    by_id = {item.get("id"): item for item in graph.get("nodes", []) if isinstance(item, dict)}
    links = {item.get("id"): item for item in normalized_links(graph)}
    result: dict[str, str] = {}
    for entry in node.get("inputs", []):
        link = links.get(entry.get("link"))
        if link is not None:
            result[entry["name"]] = by_id[link["origin_id"]]["type"]
    return result


class GuiderContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_russian_contract(self) -> None:
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        article_ids = all_article_ids()
        errors: list[str] = []
        cliché_pattern = re.compile(
            r"важно отметить|стоит отметить|следует отметить|в современном мире|"
            r"революционн|является мощн|давайте|глубже погруз|открывает новые|"
            r"может показаться|позволяет вам|подводя итог|в заключение|данная нода|"
            r"не просто .{0,80},? а ",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("comfy_extras.nodes_custom_sampler", article["runtimeIdentity"]["pythonModule"])
            self.assertIn(spec["recipe"], {asset["id"] for asset in article["assets"]})

            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIsNone(cliché_pattern.search(body), article_id)
            self.assertNotIn("\ufffd", body)
            for meaning in ("Что делает", "Когда использовать", "рецепт", "Входы", "Типовые", "пример", "ошибки", "Производительность", "Совместимость", "источники"):
                self.assertIn(meaning.lower(), body.lower(), (article_id, meaning))

            research_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_custom_sampler", research["node"]["pythonModule"])
            for flag in ("implementationRead", "runtimeCompared", "officialCasesInspected", "exampleSchemaValidated", "russianEdited", "factsRecheckedAfterEditing"):
                self.assertTrue(research["checks"][flag], (article_id, flag))
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            self.assertNotIn("workflow", recipe)
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])

        self.assertEqual([], errors)

    def test_exact_runtime_identity_fingerprints_flags_ports_and_fragments(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        metadata = catalog.load_json(INVENTORY_META)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual("/object_info", metadata["capture"]["endpoint"])
        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_custom_sampler", runtime["python_module"])
            self.assertEqual("model/sampling/guiders", runtime["category"])
            self.assertEqual(spec["required"], runtime["input"]["required"])
            self.assertEqual(spec["optional"], runtime["input"].get("optional", {}))
            self.assertEqual(["GUIDER"], runtime["output"])
            self.assertEqual(["GUIDER"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["deprecated"])
            self.assertEqual(spec["experimental"], runtime["experimental"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["api_node"])
            self.assertEqual(spec["searchAliases"], runtime["search_aliases"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertNotIn(spec["classType"], replacements_text)

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            by_ref = {item["ref"]: item for item in fragment["nodes"]}
            supplied = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                supplied[external["to"]].add(external["input"])
                descriptor = nodes[by_ref[external["to"]]["classType"]]["input"]
                port_map = descriptor.get("required", {}) | descriptor.get("optional", {})
                self.assertEqual(external["type"], port_map[external["input"]][0])
            for connection in fragment["connections"]:
                supplied[connection["to"]].add(connection["input"])
                source_runtime = nodes[by_ref[connection["from"]]["classType"]]
                target_runtime = nodes[by_ref[connection["to"]]["classType"]]
                index = source_runtime["output_name"].index(connection["output"])
                self.assertEqual(source_runtime["output"][index], target_runtime["input"]["required"][connection["input"]][0])
            for ref, node in by_ref.items():
                required = set(nodes[node["classType"]]["input"]["required"])
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref, required - supplied[ref]))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_formulas_optimizations_optional_models_and_flags(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        node_source = (SOURCE / "comfy_extras" / "nodes_custom_sampler.py").read_text(encoding="utf-8")
        sampler_source = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        helper_source = (SOURCE / "node_helpers.py").read_text(encoding="utf-8")

        basic = node_source.split("class Guider_Basic", 1)[1].split("class CFGGuider", 1)[0]
        cfg_node = node_source.split("class CFGGuider", 1)[1].split("class Guider_DualCFG", 1)[0]
        dual_cfg = node_source.split("class Guider_DualCFG", 1)[1].split("class Guider_DualModel", 1)[0]
        dual_model = node_source.split("class Guider_DualModel", 1)[1].split("class SamplerCustom", 1)[0]

        self.assertIn('self.inner_set_conds({"positive": positive})', basic)
        self.assertIn("guider = Guider_Basic(model)", basic)
        self.assertIn("guider = comfy.samplers.CFGGuider(model)", cfg_node)
        self.assertIn("guider.set_conds(positive, negative)", cfg_node)
        self.assertIn("guider.set_cfg(cfg)", cfg_node)
        self.assertIn('{"prompt_type": "negative"}', dual_cfg)
        self.assertIn("if math.isclose(self.cfg2, 1.0):", dual_cfg)
        self.assertIn("if math.isclose(self.cfg1, 1.0):", dual_cfg)
        self.assertIn("out[0] + self.cfg2 * (pred_text - out[0])", dual_cfg)
        self.assertIn("+ (out[2] - out[1]) * self.cfg1", dual_cfg)
        self.assertIn('options=["regular", "nested"]', dual_cfg)
        self.assertIn("is_experimental=True", dual_model)
        self.assertIn("if not math.isclose(self.cfg, 1.0):", dual_model)
        self.assertIn('if "multigpu_clones" in model_options', dual_model)
        self.assertIn("negative = [[None, {}]]", dual_model)
        self.assertIn("if model_negative is not None else comfy.samplers.CFGGuider(model)", dual_model)
        self.assertIn("uncond_pred + (cond_pred - uncond_pred) * cond_scale", sampler_source)
        self.assertIn("math.isclose(cond_scale, 1.0)", sampler_source)
        self.assertIn('model_options.get("disable_cfg1_optimization", False)', sampler_source)
        helper = helper_source.split("def conditioning_set_values", 1)[1].split("def conditioning_set_values_with_timestep_range", 1)[0]
        self.assertIn("n = [t[0], t[1].copy()]", helper)
        self.assertIn("n[1][k] = val", helper)

    def test_embedded_docs_archive_is_pinned_and_secondary(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            for class_type in TARGET_TYPES:
                for locale in ("en", "ru"):
                    path = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    self.assertIn(path, names)
                    text = archive.read(path).decode("utf-8")
                    marker = "AI-generated" if locale == "en" else "создана с помощью ИИ"
                    self.assertIn(marker, text)
                    self.assertGreater(len(text), 100)

    def test_exhaustive_workflow_census_widgets_and_representative_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        records: list[dict[str, Any]] = []
        payloads: dict[str, dict[str, Any]] = {}
        json_count = root_graphs = subgraph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_count += 1
                payload = json.loads(archive.read(member))
                if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
                    continue
                root_graphs += 1
                payloads[Path(member).name] = payload
                definitions = payload.get("definitions")
                subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraph_count += sum(isinstance(item, dict) for item in subgraphs)
                for scope, graph in iter_graphs(payload):
                    by_id = {node.get("id"): node for node in graph.get("nodes", []) if isinstance(node, dict)}
                    links = normalized_links(graph)
                    for node in by_id.values():
                        if node.get("type") not in TARGET_TYPES:
                            continue
                        outgoing = [link for link in links if link.get("origin_id") == node.get("id") and link.get("type") == "GUIDER"]
                        target_types = [by_id.get(link.get("target_id"), {}).get("type") for link in outgoing]
                        records.append(
                            {
                                "member": Path(member).name,
                                "workflowId": payload.get("id"),
                                "scope": scope,
                                "graph": graph,
                                "node": node,
                                "targetTypes": target_types,
                            }
                        )

        self.assertEqual((512, 496, 272), (json_count, root_graphs, subgraph_count))
        expected = {
            "BasicGuider": (14, 3, 11, 14, 10, Counter({0: 14})),
            "CFGGuider": (62, 8, 54, 35, 15, Counter({0: 56, 4: 6})),
            "DualCFGGuider": (4, 3, 1, 4, 2, Counter({0: 4})),
            "DualModelGuider": (2, 0, 2, 2, 1, Counter({0: 2})),
        }
        for class_type, values in expected.items():
            matches = [record for record in records if record["node"]["type"] == class_type]
            actual = (
                len(matches),
                sum(record["scope"] == "root" for record in matches),
                sum(record["scope"] != "root" for record in matches),
                len({record["member"] for record in matches}),
                len({record["workflowId"] for record in matches}),
                Counter(record["node"].get("mode") for record in matches),
            )
            self.assertEqual(values, actual, class_type)
            self.assertTrue(all(record["targetTypes"] == ["SamplerCustomAdvanced"] for record in matches), class_type)

        widgets = {
            class_type: Counter(tuple(record["node"].get("widgets_values", [])) for record in records if record["node"]["type"] == class_type)
            for class_type in TARGET_TYPES
        }
        self.assertEqual(Counter({(): 14}), widgets["BasicGuider"])
        self.assertEqual(
            Counter({(1,): 41, (6,): 8, (5,): 7, (3.5,): 2, (3,): 2, (4,): 2}),
            widgets["CFGGuider"],
        )
        self.assertEqual(Counter({(5, 2, "regular"): 3, (3, 1.5, "regular"): 1}), widgets["DualCFGGuider"])
        self.assertEqual(Counter({(7,): 2}), widgets["DualModelGuider"])
        self.assertFalse(any(record["node"].get("widgets_values", [])[-1:] == ["nested"] for record in records if record["node"]["type"] == "DualCFGGuider"))

        flux = payloads["flux_redux_model_example.json"]
        flux_node = next(node for node in flux["nodes"] if node.get("type") == "BasicGuider")
        self.assertEqual({"model": "ModelSamplingFlux", "conditioning": "StyleModelApply"}, incoming_types(flux, flux_node))

        chroma = payloads["image_chroma_text_to_image.json"]
        chroma_node = next(node for node in chroma["nodes"] if node.get("type") == "CFGGuider")
        self.assertEqual([3.5], chroma_node["widgets_values"])
        self.assertEqual(
            {"model": "ModelSamplingAuraFlow", "positive": "CLIPTextEncode", "negative": "CLIPTextEncode"},
            incoming_types(chroma, chroma_node),
        )

        hidream = payloads["hidream_e1_full.json"]
        hidream_node = next(node for node in hidream["nodes"] if node.get("type") == "DualCFGGuider")
        self.assertEqual([5, 2, "regular"], hidream_node["widgets_values"])
        self.assertEqual(
            {"model": "Reroute", "cond1": "InstructPixToPixConditioning", "cond2": "InstructPixToPixConditioning", "negative": "CLIPTextEncode"},
            incoming_types(hidream, hidream_node),
        )

        ideogram = payloads["image_ideogram4_t2i.json"]
        ideogram_graph = next(graph for _, graph in iter_graphs(ideogram) if any(node.get("type") == "DualModelGuider" for node in graph.get("nodes", [])))
        ideogram_node = next(node for node in ideogram_graph["nodes"] if node.get("type") == "DualModelGuider")
        self.assertEqual([7], ideogram_node["widgets_values"])
        self.assertEqual(
            {"model": "CFGOverride", "positive": "CLIPTextEncode", "model_negative": "UNETLoader", "negative": "ConditioningZeroOut"},
            incoming_types(ideogram_graph, ideogram_node),
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_formula_probe_without_models(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual(30.0, result["basic"]["result"])
        self.assertEqual([True, False], result["basic"]["batchPresence"])
        self.assertEqual(90.0, result["cfg"]["cfg4Result"])
        self.assertEqual([True, False], result["cfg"]["cfg1BatchPresence"])
        self.assertEqual([True, True], result["cfg"]["cfg1DisabledBatchPresence"])
        self.assertEqual(60.0, result["dualCfg"]["regularResult"])
        self.assertEqual(100.0, result["dualCfg"]["nestedResult"])
        self.assertEqual([False, False, True], result["dualCfg"]["regularCfg1Presence"])
        self.assertEqual([True, True, True], result["dualCfg"]["nestedPresence"])
        self.assertEqual("negative", result["dualCfg"]["middleMetadata"]["prompt_type"])
        self.assertEqual([[None, {}]], result["dualModel"]["nullNegative"])
        self.assertEqual("Guider_DualModel", result["dualModel"]["separateClass"])
        self.assertEqual(90.0, result["dualModel"]["cfg4Result"])


if __name__ == "__main__":
    unittest.main()
