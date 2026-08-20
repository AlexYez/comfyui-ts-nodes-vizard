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


ARTICLE_SPECS = {
    "core.ltxv-modality-guidance": {
        "directory": "ltxv-modality-guidance",
        "classType": "LTXVModalityGuidance",
        "fingerprint": "sha256:c5f9451a382e5e1ac47bb08bfce0c55102153926e2a3098deb0efca3b891e747",
        "recipe": "recipe.ltxv-modality-guidance-source",
    },
    "core.ltxv-spatio-temporal-guidance": {
        "directory": "ltxv-spatio-temporal-guidance",
        "classType": "LTXVSpatioTemporalGuidance",
        "fingerprint": "sha256:6a29a729966cc530c7c6dbca805623863f86aad25a220833952461663180b0ca",
        "recipe": "recipe.ltxv-stg-source",
    },
    "core.ltxv-dual-cfg-guider": {
        "directory": "ltxv-dual-cfg-guider",
        "classType": "LTXVDualCFGGuider",
        "fingerprint": "sha256:3e7769b6f756a7f1615523d04d8fb59d0f94b21a1b7304b1076b13ba8d8b03e5",
        "recipe": "recipe.ltxv-dual-cfg-official",
    },
    "core.ltxv-duration-predictor": {
        "directory": "ltxv-duration-predictor",
        "classType": "LTXVDurationPredictor",
        "fingerprint": "sha256:e0571d5bea7098876887d6eeb8287849f605000a0d0e80d98bad780917c58420",
        "recipe": "recipe.ltxv-duration-predictor-source",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.ltxv-modality-guidance-source": "ltxv-modality-guidance-source",
    "recipe.ltxv-stg-source": "ltxv-stg-source",
    "recipe.ltxv-dual-cfg-official": "ltxv-dual-cfg-official",
    "recipe.ltxv-duration-predictor-source": "ltxv-duration-predictor-source",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.ltxv-modality-guidance-source": [
        (
            "LTXVModalityGuidance",
            {"modality_scale": 3.0, "start_percent": 0.0, "end_percent": 1.0},
        ),
        ("LTXVDualCFGGuider", {"video_cfg": 3.0, "audio_cfg": 7.0}),
    ],
    "recipe.ltxv-stg-source": [
        (
            "LTXVSpatioTemporalGuidance",
            {"scale": 1.0, "blocks": "29", "start_percent": 0.0, "end_percent": 1.0},
        ),
        ("LTXVDualCFGGuider", {"video_cfg": 3.0, "audio_cfg": 7.0}),
    ],
    "recipe.ltxv-dual-cfg-official": [
        ("LTXVDualCFGGuider", {"video_cfg": 1.0, "audio_cfg": 1.0}),
        ("SamplerCustomAdvanced", {}),
    ],
    "recipe.ltxv-duration-predictor-source": [
        (
            "LTXVDurationPredictor",
            {"frame_rate": 24.0, "min_seconds": 1.0, "max_seconds": 20.0},
        ),
    ],
}

EXPECTED_HEADINGS = [
    "Что делает нода",
    "Когда использовать и когда не использовать",
    "Короткий рецепт подключения",
    "Входы, выходы и параметры",
    "Типовые связки",
    "Практический пример",
    "Частые ошибки и способы проверки",
    "Производительность и внутреннее поведение",
    "Совместимость, изменения и устаревание",
    "Связанные ноды и источники",
]

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("ltxv_guidance_duration_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_inputs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def normalized_links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            result.append(
                {
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


def workflow_graphs(payload: dict[str, Any], scope: str = "root") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield scope, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict):
            yield from workflow_graphs(subgraph, f"{scope}/subgraph:{index}")


class LtxvGuidanceDurationContentTests(unittest.TestCase):
    def test_articles_fragment_only_recipes_and_research_validate(self) -> None:
        article_ids = all_article_ids()
        article_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json")
        errors: list[str] = []
        cliche_pattern = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"давайте разбер|важно отметить|стоит подчеркнуть|подводя итог|"
            r"данная нода|является незаменим|устали от|знакомо\?|успейте|"
            r"вот перевод|ключевую роль|мощный инструмент",
            re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(spec["recipe"], article["assets"][0]["id"])
            relation_targets = article["relations"]["related"] + article["relations"]["alternatives"]
            if article["relations"]["replacedBy"] is not None:
                relation_targets.append(article["relations"]["replacedBy"])
            self.assertTrue(set(relation_targets).issubset(article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(EXPECTED_HEADINGS, re.findall(r"^## (.+)$", body, re.MULTILINE))
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, research_schema))
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("comfy_extras.nodes_lt", research["node"]["pythonModule"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual([], research["evidence"]["embeddedDocs"])
            self.assertTrue(research["checks"]["implementationRead"])
            self.assertTrue(research["checks"]["runtimeCompared"])
            self.assertTrue(research["checks"]["officialCasesInspected"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            gaps = " ".join(research["knownGaps"]).lower()
            self.assertIn("embedded docs", gaps)
            self.assertIn("человеческ", gaps)

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliche_pattern)

            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema))
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [(node["classType"], node["settings"]) for node in fragment["nodes"]],
            )
            compiled = catalog.compile_recipe(path, recipe)
            self.assertIn("fragmentData", compiled)
            self.assertNotIn("workflowData", compiled)

        self.assertEqual([], errors)

    def test_runtime_fingerprints_flags_ports_widgets_and_fragment_contracts(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        expected_categories = {
            "LTXVModalityGuidance": "advanced/guidance",
            "LTXVSpatioTemporalGuidance": "advanced/guidance",
            "LTXVDualCFGGuider": "model/sampling/guiders",
            "LTXVDurationPredictor": "conditioning/video_models",
        }
        expected_display_names = {
            "LTXVModalityGuidance": "LTXV Modality Guidance (A/V coupling)",
            "LTXVSpatioTemporalGuidance": "LTXV Spatio-Temporal Guidance (STG)",
            "LTXVDualCFGGuider": "LTXV Dual CFG Guider",
            "LTXVDurationPredictor": "LTXV Duration Predictor",
        }
        for spec in ARTICLE_SPECS.values():
            runtime = dict(nodes[spec["classType"]])
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_lt", runtime["python_module"])
            self.assertEqual(expected_categories[spec["classType"]], runtime["category"])
            self.assertEqual(expected_display_names[spec["classType"]], runtime["display_name"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertFalse(runtime["deprecated"])
            self.assertFalse(runtime["experimental"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["api_node"])
            self.assertFalse(runtime["dev_only"])
            self.assertFalse(runtime["is_input_list"])
            self.assertFalse(runtime["has_intermediate_output"])

        modality = nodes["LTXVModalityGuidance"]
        self.assertEqual(
            ["model", "modality_scale", "start_percent", "end_percent"],
            modality["input_order"]["required"],
        )
        self.assertEqual(
            {"default": 3.0, "min": 1.0, "max": 100.0, "step": 0.1, "round": 0.01},
            modality["input"]["required"]["modality_scale"][1],
        )
        for name, default in (("start_percent", 0.0), ("end_percent", 1.0)):
            self.assertEqual(
                {"advanced": True, "default": default, "min": 0.0, "max": 1.0, "step": 0.001},
                modality["input"]["required"][name][1],
            )
        self.assertEqual(["MODEL"], modality["output"])
        self.assertEqual(["MODEL"], modality["output_name"])

        stg = nodes["LTXVSpatioTemporalGuidance"]
        self.assertEqual(
            ["model", "scale", "blocks", "start_percent", "end_percent"],
            stg["input_order"]["required"],
        )
        self.assertEqual(
            {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01, "round": 0.01},
            stg["input"]["required"]["scale"][1],
        )
        self.assertEqual(
            {
                "tooltip": "Comma-separated transformer block indices to perturb.",
                "default": "29",
                "multiline": False,
            },
            stg["input"]["required"]["blocks"][1],
        )
        self.assertEqual(["MODEL"], stg["output"])
        self.assertEqual(["MODEL"], stg["output_name"])

        dual = nodes["LTXVDualCFGGuider"]
        self.assertEqual(
            ["model", "positive", "negative", "video_cfg", "audio_cfg"],
            dual["input_order"]["required"],
        )
        for name, default in (("video_cfg", 3.0), ("audio_cfg", 7.0)):
            self.assertEqual(
                {"default": default, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01},
                dual["input"]["required"][name][1],
            )
        self.assertEqual(["GUIDER"], dual["output"])
        self.assertEqual(["GUIDER"], dual["output_name"])

        duration = nodes["LTXVDurationPredictor"]
        self.assertEqual(
            ["model", "positive", "duration_head", "frame_rate", "min_seconds", "max_seconds"],
            duration["input_order"]["required"],
        )
        self.assertEqual(
            {"tooltip": "LTX 2.4 duration head loaded with ModelPatchLoader."},
            duration["input"]["required"]["duration_head"][1],
        )
        self.assertEqual(
            {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.01},
            duration["input"]["required"]["frame_rate"][1],
        )
        for name, default in (("min_seconds", 1.0), ("max_seconds", 20.0)):
            self.assertEqual(
                {"default": default, "min": 0.5, "max": 120.0, "step": 0.1},
                duration["input"]["required"][name][1],
            )
        self.assertEqual(["INT", "FLOAT"], duration["output"])
        self.assertEqual(["num_frames", "seconds"], duration["output_name"])
        self.assertEqual([None, "Raw (unclamped) predicted duration."], duration["output_tooltips"])
        self.assertEqual(["auto duration", "duration head", "num_frames"], duration["search_aliases"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            refs = {node["ref"]: node for node in fragment["nodes"]}
            for node in fragment["nodes"]:
                inputs = runtime_inputs(dict(nodes[node["classType"]]))
                self.assertTrue(set(node["settings"]).issubset(inputs))
                for name, value in node["settings"].items():
                    options = inputs[name][1]
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        self.assertGreaterEqual(value, options.get("min", value))
                        self.assertLessEqual(value, options.get("max", value))
            for external in fragment["externalInputs"]:
                target = dict(nodes[refs[external["to"]]["classType"]])
                self.assertEqual(external["type"], runtime_inputs(target)[external["input"]][0])
            for connection in fragment["connections"]:
                source = dict(nodes[refs[connection["from"]]["classType"]])
                target = dict(nodes[refs[connection["to"]]["classType"]])
                output_index = source["output_name"].index(connection["output"])
                self.assertEqual(source["output"][output_index], runtime_inputs(target)[connection["input"]][0])

        modality_fragment = catalog.load_json(
            recipe_path("recipe.ltxv-modality-guidance-source").parent / "fragment.json"
        )
        self.assertEqual(
            [("modality", "MODEL", "guider", "model")],
            [(c["from"], c["output"], c["to"], c["input"]) for c in modality_fragment["connections"]],
        )
        stg_fragment = catalog.load_json(recipe_path("recipe.ltxv-stg-source").parent / "fragment.json")
        self.assertEqual(
            [("stg", "MODEL", "guider", "model")],
            [(c["from"], c["output"], c["to"], c["input"]) for c in stg_fragment["connections"]],
        )
        dual_fragment = catalog.load_json(recipe_path("recipe.ltxv-dual-cfg-official").parent / "fragment.json")
        self.assertEqual(
            [("guider", "GUIDER", "sample", "guider")],
            [(c["from"], c["output"], c["to"], c["input"]) for c in dual_fragment["connections"]],
        )
        duration_fragment = catalog.load_json(
            recipe_path("recipe.ltxv-duration-predictor-source").parent / "fragment.json"
        )
        self.assertEqual([], duration_fragment["connections"])

        replacement_text = json.dumps(catalog.load_json(REPLACEMENTS), sort_keys=True)
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_text)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_contracts(self) -> None:
        nodes_lt = (SOURCE / "comfy_extras" / "nodes_lt.py").read_text(encoding="utf-8")
        av_model = (SOURCE / "comfy" / "ldm" / "lightricks" / "av_model.py").read_text(encoding="utf-8")
        attention = (SOURCE / "comfy" / "ldm" / "lightricks" / "model.py").read_text(encoding="utf-8")
        duration_head = (SOURCE / "comfy" / "ldm" / "lightricks" / "duration_head.py").read_text(encoding="utf-8")
        model_patch = (SOURCE / "comfy_extras" / "nodes_model_patch.py").read_text(encoding="utf-8")
        model_patcher = (SOURCE / "comfy" / "model_patcher.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")

        for marker in (
            'block_set = frozenset(int(b) for b in re.findall(r"\\d+", blocks))',
            'transformer_options["stg_self_attn_blocks"] = block_set',
            "return cfg_result + (cond_pred - perturbed) * scale",
            "if math.isclose(modality_scale, 1.0):",
            'transformer_options["a2v_cross_attn"] = False',
            'transformer_options["v2a_cross_attn"] = False',
            "return cfg_result + (cond_pred - mod_pred) * (modality_scale - 1.0)",
            "self._v_numel = math.prod(parts[0].shape[1:])",
            "out = uncond + (cond - uncond) * video_cfg",
            "out[..., v:] = uncond[..., v:] + (cond[..., v:] - uncond[..., v:]) * audio_cfg",
            'model_options = {**model_options, "sampler_cfg_function": dual_cfg, "disable_cfg1_optimization": True}',
            "context = positive[0][0]",
            "context = context[:1]",
            "comfy.model_management.load_models_gpu([model, duration_head])",
            'processed = dm.preprocess_text_embeds(context, unprocessed=meta.get("unprocessed_ltxav_embeds", False))',
            "video_tokens = processed[..., :dm.cross_attention_dim].float()",
            "audio_tokens = processed[..., dm.cross_attention_dim:].float()",
        ):
            self.assertIn(marker, nodes_lt)

        self.assertIn('transformer_options.get("a2v_cross_attn", True)', av_model)
        self.assertIn('transformer_options.get("v2a_cross_attn", True)', av_model)
        self.assertIn("for i, block in enumerate(self.transformer_blocks):", av_model)
        self.assertIn('block_transformer_options = {**transformer_options, "stg_skip_self_attn": True}', av_model)
        self.assertIn('if self_attn and transformer_options.get("stg_skip_self_attn", False):', attention)
        self.assertIn("out = v", attention)

        self.assertIn("return self.mlp_out(hidden).squeeze(-1).exp()", duration_head)
        self.assertIn("min_frames = max(1, round(min_seconds * frame_rate))", duration_head)
        self.assertIn("raw_frames = max(min_frames, min(round(seconds * frame_rate), max_frames))", duration_head)
        self.assertIn("frames = (raw_frames - 1) // time_scale * time_scale + 1", duration_head)
        self.assertIn('any(k.endswith("duration_head.attention_pooler.query_tokens") for k in sd)', model_patch)
        self.assertIn("sd = {k: v.float() for k, v in sd.items()}  # tiny head, keep fp32", model_patch)

        self.assertIn(
            'model_options["sampler_post_cfg_function"] = model_options.get("sampler_post_cfg_function", []) + [post_cfg_function]',
            model_patcher,
        )
        self.assertIn('model_options.get("disable_cfg1_optimization", False) == False', samplers)
        self.assertIn("tensors.append(tensor.reshape(tensor.shape[0], 1, -1))", utils)
        self.assertIn("latent = torch.cat(tensors, dim=-1)", utils)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_exact_pages_are_absent(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for spec in ARTICLE_SPECS.values():
                class_type = spec["classType"]
                self.assertNotIn(f"comfyui_embedded_docs/docs/{class_type}/en.md", names)
                self.assertNotIn(f"comfyui_embedded_docs/docs/{class_type}/ru.md", names)
                self.assertFalse(any(f"/docs/{class_type}/" in name for name in names))

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_official_root_and_recursive_subgraph_census(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        records: list[dict[str, Any]] = []
        file_count = 0
        root_graph_count = 0
        graph_count = 0
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            for member in sorted(archive.namelist()):
                if "/templates/" not in member or not member.endswith(".json"):
                    continue
                file_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_graph_count += 1
                for scope, graph in workflow_graphs(payload):
                    graph_count += 1
                    graph_nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    by_id = {node.get("id"): node for node in graph_nodes}
                    links = normalized_links(graph)
                    for node in graph_nodes:
                        if node.get("type") in targets:
                            records.append(
                                {
                                    "member": member,
                                    "scope": scope,
                                    "node": node,
                                    "by_id": by_id,
                                    "links": links,
                                    "raw_links": graph.get("links", []),
                                }
                            )

        self.assertEqual(512, file_count)
        self.assertEqual(496, root_graph_count)
        self.assertEqual(768, graph_count)
        self.assertEqual(Counter({"LTXVDualCFGGuider": 5}), Counter(r["node"]["type"] for r in records))
        self.assertEqual(
            Counter(
                {
                    "video_ltx2_5_flf2v.json": 1,
                    "video_ltx2_5_i2v.json": 2,
                    "video_ltx2_5_t2v.json": 2,
                }
            ),
            Counter(Path(r["member"]).name for r in records),
        )

        conditioning_sources: list[str] = []
        for record in records:
            node = record["node"]
            node_id = node["id"]
            self.assertEqual("root/subgraph:0", record["scope"])
            self.assertEqual([1, 1], node.get("widgets_values"))
            self.assertEqual(0, node.get("mode"))
            self.assertEqual("comfy-core", node.get("properties", {}).get("cnr_id"))
            self.assertEqual("0.28.0", node.get("properties", {}).get("ver"))
            self.assertTrue(all(isinstance(link, dict) for link in record["raw_links"]))

            incoming = [link for link in record["links"] if link.get("target_id") == node_id]
            outgoing = [link for link in record["links"] if link.get("origin_id") == node_id]
            self.assertEqual(
                {(0, "MODEL"), (1, "CONDITIONING"), (2, "CONDITIONING")},
                {(link["target_slot"], link["type"]) for link in incoming},
            )
            self.assertEqual(1, len(outgoing))
            self.assertEqual(0, outgoing[0]["origin_slot"])
            self.assertEqual(1, outgoing[0]["target_slot"])
            self.assertEqual("GUIDER", outgoing[0]["type"])

            model_link = next(link for link in incoming if link["target_slot"] == 0)
            positive_link = next(link for link in incoming if link["target_slot"] == 1)
            negative_link = next(link for link in incoming if link["target_slot"] == 2)
            self.assertEqual("UNETLoader", record["by_id"][model_link["origin_id"]]["type"])
            positive_type = record["by_id"][positive_link["origin_id"]]["type"]
            negative_type = record["by_id"][negative_link["origin_id"]]["type"]
            self.assertEqual(positive_type, negative_type)
            conditioning_sources.append(positive_type)
            self.assertEqual("SamplerCustomAdvanced", record["by_id"][outgoing[0]["target_id"]]["type"])

        self.assertEqual(Counter({"LTXVConditioning": 4, "LTXVAddGuide": 1}), Counter(conditioning_sources))

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_model_free_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for exact-source probe")
        result = subprocess.run(
            [str(python), "-X", "utf8", str(SYNTHETIC_PROBE)],
            cwd=catalog.ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0 and python == Path(sys.executable):
            self.skipTest(f"torch unavailable for probe: {result.stderr}")
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        guidance = payload["guidance"]
        modality = guidance["modality"]
        self.assertTrue(modality["sourceUnchanged"])
        self.assertTrue(modality["cloneParentIdentity"])
        self.assertAlmostEqual(8.0, modality["thresholds"][0])
        self.assertAlmostEqual(2.0, modality["thresholds"][1])
        self.assertEqual([[[8.0, 8.0]]], modality["insideResult"])
        self.assertEqual({"a2v": False, "v2a": False, "kept": "callback"}, modality["flags"])
        self.assertTrue(modality["callbackOptionsUnchanged"])
        self.assertTrue(modality["scaleOneIdentity"])
        self.assertTrue(modality["scaleOneAvoidsPass"])
        self.assertTrue(modality["outsideIdentity"])
        self.assertTrue(modality["outsideAvoidsPass"])

        stg = guidance["stg"]
        self.assertTrue(stg["sourceUnchanged"])
        self.assertEqual([[[6.5, 6.5]]], stg["insideResult"])
        self.assertEqual([3, 5, 7, 29], stg["parsedBlocks"])
        self.assertEqual("callback", stg["kept"])
        self.assertTrue(stg["emptyBlocksIdentity"])
        self.assertTrue(stg["emptyBlocksAvoidPass"])
        self.assertTrue(stg["zeroScaleIdentity"])
        self.assertTrue(stg["zeroScaleAvoidsPass"])
        self.assertEqual(2, guidance["stackedCallbackCount"])

        dual = payload["dualCFG"]
        self.assertTrue(dual["modelIdentity"])
        self.assertTrue(dual["positiveIdentity"])
        self.assertTrue(dual["negativeIdentity"])
        self.assertTrue(dual["initialCfgIsMax"])
        self.assertEqual("sampled", dual["sampleResult"])
        self.assertEqual(60, dual["videoNumelExcludesBatch"])
        self.assertEqual([3.0], dual["dualVideoValues"])
        self.assertEqual([7.0], dual["dualTailValues"])
        self.assertTrue(dual["disableCfgOneOptimization"])
        self.assertTrue(dual["inputOptionsUnchanged"])
        self.assertTrue(dual["equalFallsBack"])
        self.assertTrue(dual["flatFallsBackToVideo"])

        duration = payload["duration"]
        self.assertEqual(473, duration["numFrames"])
        self.assertEqual(30.0, duration["rawSeconds"])
        self.assertTrue(duration["loadCallUsesBothPatchers"])
        self.assertEqual(
            {"shape": [1, 3, 6], "dtype": "torch.float16", "unprocessed": True},
            duration["preprocess"],
        )
        self.assertEqual(
            {
                "videoShape": [1, 3, 4],
                "audioShape": [1, 3, 2],
                "videoDtype": "torch.float32",
                "audioDtype": "torch.float32",
            },
            duration["headCall"],
        )
        self.assertTrue(duration["wrongPatchRejectedBeforeLoad"])
        self.assertEqual(
            {"belowMin": 25, "inside": 57, "aboveMax": 473, "tightBoundsMayBeOffGrid": 12, "reversedBounds": 24},
            duration["gridExamples"],
        )
        self.assertEqual([1.0], duration["zeroWeightsPredictOneSecond"])
        self.assertTrue(duration["noTokensRejected"])


if __name__ == "__main__":
    unittest.main()
