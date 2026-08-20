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


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.sampler-euler-cfgpp": {
        "directory": "sampler-euler-cfgpp",
        "classType": "SamplerEulerCFGpp",
        "pythonModule": "comfy_extras.nodes_advanced_samplers",
        "fingerprint": "sha256:7b7028566d057d081bec3dbacb2ae030c98899a559dcabc81d2900ae00dc421c",
        "experimental": True,
        "recipe": "recipe.euler-cfgpp-regular-custom-sampling",
        "recipeDirectory": "euler-cfgpp-regular-custom-sampling",
        "algorithmSettings": {"version": "regular"},
        "sampleClass": "SamplerCustomAdvanced",
    },
    "core.sampler-lcm": {
        "directory": "sampler-lcm",
        "classType": "SamplerLCM",
        "pythonModule": "comfy_extras.nodes_advanced_samplers",
        "fingerprint": "sha256:135a4b71dc79fed8c9c0daa794687e637445f87fc844033ae1bcca3f33d993f0",
        "experimental": False,
        "recipe": "recipe.hidream-o1-dev-lcm-sampler",
        "recipeDirectory": "hidream-o1-dev-lcm-sampler",
        "algorithmSettings": {
            "s_noise": 1.0,
            "s_noise_end": 1.0,
            "noise_clip_std": 2.5,
        },
        "sampleClass": "SamplerCustom",
    },
    "core.sampler-lcm-upscale": {
        "directory": "sampler-lcm-upscale",
        "classType": "SamplerLCMUpscale",
        "pythonModule": "comfy_extras.nodes_advanced_samplers",
        "fingerprint": "sha256:976ae401e94b69f54cef0e360417ca3d01381a861e55cfea77d692a0ead76f77",
        "experimental": False,
        "recipe": "recipe.lcm-upscale-custom-sampling",
        "recipeDirectory": "lcm-upscale-custom-sampling",
        "algorithmSettings": {
            "scale_ratio": 2.0,
            "scale_steps": -1,
            "upscale_method": "bislerp",
        },
        "sampleClass": "SamplerCustomAdvanced",
    },
    "core.sampler-ar-video": {
        "directory": "sampler-ar-video",
        "classType": "SamplerARVideo",
        "pythonModule": "comfy_extras.nodes_ar_video",
        "fingerprint": "sha256:d2dea5eea7232493f4b4241f488c0dfeee7782c7c3d47221054d16cc51630035",
        "experimental": False,
        "recipe": "recipe.causal-forcing-framewise-ar-sampler",
        "recipeDirectory": "causal-forcing-framewise-ar-sampler",
        "algorithmSettings": {"num_frame_per_block": 1},
        "sampleClass": "SamplerCustomAdvanced",
    },
}

INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_META = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_SHA = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = (
    catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_SHA = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = Path(__file__).with_name("euler_lcm_ar_sampler_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"


def recipe_path(spec: dict[str, Any]) -> Path:
    return catalog.CONTENT / "recipes" / spec["recipeDirectory"] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def nested_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)


def workflow_graphs(
    member: str, payload: dict[str, Any]
) -> Iterator[tuple[str, int | None, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", None, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, graph in enumerate(subgraphs):
        if isinstance(graph, dict):
            yield "subgraph", index, graph


def graph_nodes(graph: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    return {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    }


def normalized_links(graph: dict[str, Any]) -> Iterator[tuple[Any, Any, int, Any, int, Any]]:
    for link in graph.get("links", []):
        if isinstance(link, list) and len(link) >= 6:
            yield link[0], link[1], link[2], link[3], link[4], link[5]
        elif isinstance(link, dict):
            yield (
                link.get("id"),
                link.get("origin_id"),
                link.get("origin_slot"),
                link.get("target_id"),
                link.get("target_slot"),
                link.get("type"),
            )


def slot_name(node: dict[str, Any], key: str, index: int) -> str | None:
    slots = node.get(key, [])
    if not isinstance(slots, list) or not isinstance(index, int) or not 0 <= index < len(slots):
        return None
    slot = slots[index]
    return slot.get("name") if isinstance(slot, dict) else None


def typed_edges(graph: dict[str, Any]) -> set[tuple[str | None, str | None, str | None, str | None, Any]]:
    nodes = graph_nodes(graph)
    result: set[tuple[str | None, str | None, str | None, str | None, Any]] = set()
    for _, source_id, source_slot, target_id, target_slot, link_type in normalized_links(graph):
        source = nodes.get(source_id, {})
        target = nodes.get(target_id, {})
        result.add(
            (
                source.get("type"),
                slot_name(source, "outputs", source_slot),
                target.get("type"),
                slot_name(target, "inputs", target_slot),
                link_type,
            )
        )
    return result


def recursive_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from recursive_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from recursive_strings(item)


class EulerLcmArSamplerContentTests(unittest.TestCase):
    def test_article_recipe_fragment_research_contracts(self) -> None:
        schemas = {
            key: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for key, filename in {
                "article": "article.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
                "research": "article-research.schema.v1.json",
            }.items()
        }
        inventory = catalog.load_json(INVENTORY)
        article_ids = all_article_ids()
        errors: list[str] = []
        russian_texts: list[Path] = []

        for article_id, spec in ARTICLE_SPECS.items():
            manifest_path = article_path(spec)
            article = catalog.load_json(manifest_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(manifest_path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("core", article["kind"])
            self.assertEqual("ru", article["locale"])
            self.assertEqual(("draft", "in_review"), (article["status"], article["editorial"]["state"]))
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"].casefold())
            self.assertEqual(spec["experimental"], article["experimental"])
            runtime_identity = article["runtimeIdentity"]
            self.assertEqual(spec["classType"], runtime_identity["classType"])
            self.assertEqual(spec["pythonModule"], runtime_identity["pythonModule"])
            self.assertEqual("comfy-core", runtime_identity.get("packageId"))
            self.assertEqual("backend", runtime_identity["origin"])
            self.assertEqual([], runtime_identity["aliases"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual("0.32.0", article["compatibility"]["comfyui"])
            self.assertEqual(">=1.48.7", article["compatibility"]["frontend"])
            self.assertEqual(
                f"ComfyUI v0.32.0 ({SOURCE_COMMIT})",
                article["compatibility"]["sourceRevision"],
            )
            self.assertIn(
                spec["recipe"],
                {asset["id"] for asset in article["assets"] if asset["type"] == "recipe"},
            )
            relation_targets = set(
                article["relations"]["related"] + article["relations"]["alternatives"]
            )
            self.assertTrue(relation_targets.issubset(article_ids))
            self.assertIsNone(article["relations"]["replacedBy"])

            article_body = manifest_path.parent / article["body"]
            body_text = article_body.read_text(encoding="utf-8")
            self.assertEqual(
                10,
                len(re.findall(r"^## .+$", body_text, re.MULTILINE)),
                article_body,
            )
            russian_texts.append(article_body)

            research_path = catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["pythonModule"], research["node"]["pythonModule"])
            self.assertEqual("backend", research["node"]["origin"])
            self.assertEqual(("fact_checked", "automated_assisted"), (research["state"], research["reviewMode"]))
            self.assertEqual(
                {
                    "comfyui": "0.32.0",
                    "frontend": "1.48.7",
                    "sourceCommit": SOURCE_COMMIT,
                    "embeddedDocs": "0.5.9",
                    "workflowTemplatesJson": "0.1.42",
                },
                research["baseline"],
            )
            checks = research["checks"]
            for key in (
                "implementationRead",
                "runtimeCompared",
                "officialCasesInspected",
                "exampleSchemaValidated",
                "russianEdited",
                "factsRecheckedAfterEditing",
            ):
                self.assertTrue(checks[key], f"{article_id}: {key}")
            self.assertFalse(checks["exampleExecuted"])
            self.assertTrue(research["knownGaps"])
            self.assertTrue(
                {"en", "ru"}.issubset(
                    {entry["locale"] for entry in research["evidence"]["embeddedDocs"]}
                )
            )

            current_recipe_path = recipe_path(spec)
            recipe = catalog.load_json(current_recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(current_recipe_path, recipe, article_ids, errors)
            self.assertEqual(spec["recipe"], recipe["recipeId"])
            self.assertEqual("ru", recipe["locale"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"].casefold())
            self.assertIn(article_id, recipe["articleIds"])
            self.assertNotIn("workflow", recipe, "these examples are fragment-only, not executable workflows")
            russian_texts.append(current_recipe_path.parent / recipe["body"])

            fragment_path = current_recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            self.assertEqual(spec["classType"], nodes["algorithm"]["classType"])
            self.assertEqual(spec["algorithmSettings"], nodes["algorithm"]["settings"])
            self.assertEqual(spec["sampleClass"], nodes["sample"]["classType"])
            self.assertIn(
                {
                    "from": "algorithm",
                    "output": "SAMPLER",
                    "to": "sample",
                    "input": "sampler",
                },
                fragment["connections"],
            )

            for external in fragment["externalInputs"]:
                target_runtime = inventory[nodes[external["to"]]["classType"]]
                target_inputs = {
                    **target_runtime["input"].get("required", {}),
                    **target_runtime["input"].get("optional", {}),
                }
                self.assertEqual(external["type"], target_inputs[external["input"]][0])
            for connection in fragment["connections"]:
                source_runtime = inventory[nodes[connection["from"]]["classType"]]
                target_runtime = inventory[nodes[connection["to"]]["classType"]]
                output_index = source_runtime["output_name"].index(connection["output"])
                target_inputs = {
                    **target_runtime["input"].get("required", {}),
                    **target_runtime["input"].get("optional", {}),
                }
                self.assertEqual(
                    source_runtime["output"][output_index],
                    target_inputs[connection["input"]][0],
                )

            algorithm_runtime = inventory[spec["classType"]]
            algorithm_inputs = {
                **algorithm_runtime["input"].get("required", {}),
                **algorithm_runtime["input"].get("optional", {}),
            }
            for name, value in spec["algorithmSettings"].items():
                self.assertIn(name, algorithm_inputs)
                input_type, config = algorithm_inputs[name]
                if input_type == "COMBO":
                    self.assertIn(value, config["options"])
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if "min" in config:
                        self.assertGreaterEqual(value, config["min"])
                    if "max" in config:
                        self.assertLessEqual(value, config["max"])

        self.assertEqual([], errors)
        forbidden = (
            "важно отметить",
            "стоит отметить",
            "следует отметить",
            "таким образом",
            "в современном мире",
            "давайте",
            "погрузимся",
            "революционн",
            "является мощн",
            "подводя итог",
            "в заключение",
            "данная нода",
        )
        for path in russian_texts:
            text = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("\ufffd", text, path)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_exact_runtime_contracts_fingerprints_flags_and_no_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        metadata = catalog.load_json(INVENTORY_META)
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])

        expected_orders = {
            "SamplerEulerCFGpp": ["version"],
            "SamplerLCM": ["s_noise", "s_noise_end", "noise_clip_std"],
            "SamplerLCMUpscale": ["scale_ratio", "scale_steps", "upscale_method"],
            "SamplerARVideo": ["num_frame_per_block"],
        }
        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            runtime = inventory[class_type]
            self.assertEqual(class_type, runtime["name"])
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime))
            self.assertEqual(expected_orders[class_type], runtime["input_order"]["required"])
            self.assertEqual(["SAMPLER"], runtime["output"])
            self.assertEqual(["SAMPLER"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            self.assertIsNone(runtime["search_aliases"])
            self.assertEqual(
                {
                    "output_node": False,
                    "deprecated": False,
                    "experimental": spec["experimental"],
                    "dev_only": False,
                    "api_node": False,
                    "has_intermediate_output": False,
                },
                {
                    key: runtime[key]
                    for key in (
                        "output_node",
                        "deprecated",
                        "experimental",
                        "dev_only",
                        "api_node",
                        "has_intermediate_output",
                    )
                },
            )

        euler = inventory["SamplerEulerCFGpp"]
        self.assertEqual("experimental", euler["category"])
        self.assertEqual("SamplerEulerCFG++", euler["display_name"])
        self.assertEqual("COMBO", euler["input"]["required"]["version"][0])
        self.assertEqual(
            {"advanced": True, "multiselect": False, "options": ["regular", "alternative"]},
            euler["input"]["required"]["version"][1],
        )

        lcm = inventory["SamplerLCM"]
        self.assertEqual("model/sampling/samplers", lcm["category"])
        for name, default, maximum in (
            ("s_noise", 1.0, 64.0),
            ("s_noise_end", 1.0, 64.0),
            ("noise_clip_std", 0.0, 10.0),
        ):
            input_type, config = lcm["input"]["required"][name]
            self.assertEqual("FLOAT", input_type)
            self.assertEqual((default, 0.0, maximum, 0.01), tuple(config[key] for key in ("default", "min", "max", "step")))

        upscale = inventory["SamplerLCMUpscale"]
        self.assertEqual(
            (1.0, 0.1, 20.0, 0.01, True),
            tuple(upscale["input"]["required"]["scale_ratio"][1][key] for key in ("default", "min", "max", "step", "advanced")),
        )
        self.assertEqual(
            (-1, -1, 1000, 1, True),
            tuple(upscale["input"]["required"]["scale_steps"][1][key] for key in ("default", "min", "max", "step", "advanced")),
        )
        self.assertEqual(
            ["bislerp", "nearest-exact", "bilinear", "area", "bicubic"],
            upscale["input"]["required"]["upscale_method"][1]["options"],
        )

        ar_video = inventory["SamplerARVideo"]
        self.assertEqual("model/sampling/samplers", ar_video["category"])
        self.assertEqual("Sampler AR Video", ar_video["display_name"])
        self.assertEqual(
            (1, 1, 64),
            tuple(ar_video["input"]["required"]["num_frame_per_block"][1][key] for key in ("default", "min", "max")),
        )

        replacement_strings = set(recursive_strings(catalog.load_json(REPLACEMENTS)))
        for spec in ARTICLE_SPECS.values():
            self.assertNotIn(spec["classType"], replacement_strings)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_dispatch_and_algorithm_branches(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        advanced = (SOURCE / "comfy_extras" / "nodes_advanced_samplers.py").read_text(encoding="utf-8")
        ar_nodes = (SOURCE / "comfy_extras" / "nodes_ar_video.py").read_text(encoding="utf-8")
        sampling = (SOURCE / "comfy" / "k_diffusion" / "sampling.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")

        self.assertIn('if version == "alternative":', advanced)
        self.assertIn("KSAMPLER(sample_euler_pp)", advanced)
        self.assertIn('ksampler("euler_cfg_pp")', advanced)
        self.assertIn("set_model_options_post_cfg_function", advanced)
        self.assertIn("d = to_d(x - denoised + temp[0], sigmas[i], denoised)", advanced)
        self.assertIn('ksampler(\n            "lcm",', advanced)
        self.assertIn('"s_noise_end": float(s_noise_end)', advanced)
        self.assertIn('"noise_clip_std": float(noise_clip_std)', advanced)
        self.assertIn("if scale_steps < 0:", advanced)
        self.assertIn("scale_steps = None", advanced)
        self.assertIn("upscale_steps = max(len(sigmas) // 2 + 1, 2)", advanced)
        self.assertIn("upscale_steps = min(upscale_steps, len(sigmas) + 1)", advanced)
        self.assertIn("upscales = np.linspace(1.0, total_upscale, upscale_steps)[1:]", advanced)
        self.assertIn("round(orig_shape[-1] * upscales[i])", advanced)
        self.assertIn("round(orig_shape[-2] * upscales[i])", advanced)

        self.assertIn('ksampler("ar_video", extra_options)', ar_nodes)
        self.assertIn('"num_frame_per_block": num_frame_per_block', ar_nodes)
        self.assertIn("def sample_lcm(", sampling)
        self.assertIn("clip_val = noise_clip_std * noise.std()", sampling)
        self.assertIn("noise = noise.clamp(min=-clip_val, max=clip_val)", sampling)
        self.assertIn("t = (i / (n_steps - 1)) if n_steps > 1 else 0.0", sampling)
        self.assertIn("s_noise_i = s_start + (s_end - s_start) * t", sampling)
        self.assertIn("model_sampling.noise_scaling(sigmas[i + 1], noise, x)", sampling)
        self.assertIn("return sample_euler_ancestral_cfg_pp", sampling)
        self.assertIn("eta=0.0, s_noise=0.0, noise_sampler=None", sampling)
        self.assertIn("if x.ndim != 5:", sampling)
        self.assertIn("init_kv_caches", sampling)
        self.assertIn("init_crossattn_caches", sampling)
        self.assertIn("num_blocks = -(-lat_t // num_frame_per_block)", sampling)
        self.assertIn('transformer_options.pop("ar_state", None)', sampling)
        self.assertIn('"euler_cfg_pp"', samplers)
        self.assertIn('"lcm"', samplers)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_pinned_embedded_docs_and_ai_disclosure(self) -> None:
        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for spec in ARTICLE_SPECS.values():
                class_type = spec["classType"]
                en_member = f"comfyui_embedded_docs/docs/{class_type}/en.md"
                ru_member = f"comfyui_embedded_docs/docs/{class_type}/ru.md"
                self.assertIn(en_member, archive.namelist())
                self.assertIn(ru_member, archive.namelist())
                en = archive.read(en_member).decode("utf-8")
                ru = archive.read(ru_member).decode("utf-8")
                self.assertIn("This documentation was AI-generated.", en)
                self.assertIn("Эта документация была создана с помощью ИИ.", ru)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_topology_and_generic_widget_evidence(self) -> None:
        self.assertEqual(WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        direct_counts = Counter({target: 0 for target in targets})
        direct_records: list[dict[str, Any]] = []
        executable_lcm: set[tuple[Any, ...]] = set()
        all_lcm_widget_types: Counter[str] = Counter()
        lcm_prose_mentions: list[tuple[str, Any]] = []
        euler_widget_hits: list[tuple[str, str, Any]] = []
        json_count = root_count = subgraph_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            members = [
                name
                for name in archive.namelist()
                if "/templates/" in name and name.endswith(".json")
            ]
            self.assertEqual(512, len(members))
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                definitions = payload.get("definitions")
                subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
                subgraph_count += sum(isinstance(graph, dict) for graph in subgraphs)
                for graph_kind, graph_index, graph in workflow_graphs(member, payload):
                    for node in graph.get("nodes", []):
                        if not isinstance(node, dict):
                            continue
                        node_type = node.get("type")
                        if node_type in targets:
                            direct_counts[node_type] += 1
                            direct_records.append(
                                {
                                    "member": member,
                                    "payload": payload,
                                    "graphKind": graph_kind,
                                    "graphIndex": graph_index,
                                    "graph": graph,
                                    "node": node,
                                }
                            )
                        for value in nested_strings(node.get("widgets_values")):
                            folded = value.casefold()
                            if folded == "lcm":
                                all_lcm_widget_types[str(node_type)] += 1
                                if node_type in {"KSampler", "KSamplerSelect"}:
                                    executable_lcm.add(
                                        (
                                            Path(member).name,
                                            graph_kind,
                                            graph_index,
                                            graph.get("id"),
                                            node.get("id"),
                                            node_type,
                                            node.get("mode"),
                                            json.dumps(node.get("widgets_values"), ensure_ascii=False, separators=(",", ":")),
                                        )
                                    )
                            elif node_type == "MarkdownNote" and "lcm" in folded:
                                lcm_prose_mentions.append((Path(member).name, node.get("id")))
                            if folded == "euler_cfg_pp":
                                euler_widget_hits.append((member, str(node_type), node.get("id")))

        self.assertEqual((512, 496, 272), (json_count, root_count, subgraph_count))
        self.assertEqual(
            {
                "SamplerEulerCFGpp": 0,
                "SamplerLCM": 1,
                "SamplerLCMUpscale": 0,
                "SamplerARVideo": 1,
            },
            dict(sorted(direct_counts.items())),
        )
        self.assertEqual([], euler_widget_hits)
        self.assertEqual(
            {"KSampler": 5, "KSamplerSelect": 3},
            dict(all_lcm_widget_types),
        )
        self.assertEqual(
            {("hidream_i1_dev.json", 72), ("hidream_i1_fast.json", 89), ("hidream_i1_full.json", 88)},
            set(lcm_prose_mentions),
        )

        expected_lcm_widgets = {
            (
                "audio_stable_audio_3_medium.json", "subgraph", 0,
                "8b66c757-fe2f-4184-91f3-479a19deb565", 3, "KSampler", 0,
                '[1038503484137406,"randomize",8,1,"lcm","simple",1]',
            ),
            (
                "audio_stable_audio_3_medium_base.json", "subgraph", 0,
                "8b66c757-fe2f-4184-91f3-479a19deb565", 3, "KSampler", 0,
                '[246013967987712,"randomize",50,7,"lcm","simple",1]',
            ),
            (
                "hidream_i1_dev.json", "root", None,
                "01d66ae9-78be-4a8d-b737-24eee5e1d447", 3, "KSampler", 0,
                '[426270906276990,"randomize",28,1,"lcm","normal",1]',
            ),
            (
                "hidream_i1_fast.json", "root", None,
                "01d66ae9-78be-4a8d-b737-24eee5e1d447", 94, "KSampler", 0,
                '[833271177511441,"randomize",16,1,"lcm","normal",1]',
            ),
            (
                "image_boogu_image_0_1_turbo_t2i.json", "subgraph", 0,
                "4f6f2e64-58b0-4eb6-9b91-a61d1945a19f", 32, "KSampler", 0,
                '[896977722960984,"randomize",4,1,"lcm","sgm_uniform",1]',
            ),
            (
                "utility_pid_latent_upscale_dit.json", "subgraph", 0,
                "b6f63f3c-4f79-4394-83c3-552b6b84af62", 76, "KSamplerSelect", 0,
                '["lcm"]',
            ),
            (
                "video_wan_animate2.json", "subgraph", 0,
                "11706f8a-428d-4ef9-b24f-863f651c1b0b", 27, "KSamplerSelect", 0,
                '["lcm"]',
            ),
            (
                "video_wan_animate2.json", "subgraph", 2,
                "b798a87e-23ec-483d-ab9b-6af5b298d0ad", 464, "KSamplerSelect", 0,
                '["lcm"]',
            ),
        }
        self.assertEqual(expected_lcm_widgets, executable_lcm)

        lcm_record = next(record for record in direct_records if record["node"]["type"] == "SamplerLCM")
        self.assertEqual("image_hidream_o1_dev.json", Path(lcm_record["member"]).name)
        self.assertEqual("root", lcm_record["graphKind"])
        self.assertIsNone(lcm_record["graphIndex"])
        self.assertEqual("a2143803-dd9d-4fd4-9370-31ce70307498", lcm_record["graph"].get("id"))
        self.assertEqual((125, 0, {}, [1, 1, 2.5]), tuple(lcm_record["node"][key] for key in ("id", "mode", "flags", "widgets_values")))
        self.assertEqual("0.21.0", lcm_record["node"]["properties"]["ver"])
        self.assertIn(
            ("SamplerLCM", "SAMPLER", "SamplerCustom", "sampler", "SAMPLER"),
            typed_edges(lcm_record["graph"]),
        )
        lcm_nodes = graph_nodes(lcm_record["graph"])
        self.assertEqual(["normal", 28, 1], lcm_nodes[112]["widgets_values"])
        self.assertEqual([7.6], lcm_nodes[124]["widgets_values"])
        self.assertEqual([True, 270186383729385, "randomize", 1], lcm_nodes[108]["widgets_values"])

        ar_record = next(record for record in direct_records if record["node"]["type"] == "SamplerARVideo")
        self.assertEqual("video_causal_forcing_i2v.json", Path(ar_record["member"]).name)
        self.assertEqual(("subgraph", 0), (ar_record["graphKind"], ar_record["graphIndex"]))
        self.assertEqual("b5d4e2f9-8c3a-4b0e-a4d2-f9e6b3c0a1d5", ar_record["payload"].get("id"))
        self.assertEqual("96ba6b5d-dd48-49b3-84c3-5b86eafc2a07", ar_record["graph"].get("id"))
        self.assertEqual("Image to Video (Causal Forcing Framewise)", ar_record["graph"].get("name"))
        self.assertEqual((12, 0, {}, [1]), tuple(ar_record["node"][key] for key in ("id", "mode", "flags", "widgets_values")))
        self.assertEqual("0.22.0", ar_record["node"]["properties"]["ver"])
        ar_nodes = graph_nodes(ar_record["graph"])
        self.assertEqual([832, 480, 81, 1], ar_nodes[8]["widgets_values"])
        self.assertEqual(["simple", 4, 1], ar_nodes[13]["widgets_values"])
        self.assertEqual([1], ar_nodes[14]["widgets_values"])
        ar_edges = typed_edges(ar_record["graph"])
        for edge in {
            ("ARVideoI2V", "MODEL", "BasicScheduler", "model", "MODEL"),
            ("ARVideoI2V", "MODEL", "CFGGuider", "model", "MODEL"),
            ("RandomNoise", "NOISE", "SamplerCustomAdvanced", "noise", "NOISE"),
            ("CFGGuider", "GUIDER", "SamplerCustomAdvanced", "guider", "GUIDER"),
            ("SamplerARVideo", "SAMPLER", "SamplerCustomAdvanced", "sampler", "SAMPLER"),
            ("BasicScheduler", "SIGMAS", "SamplerCustomAdvanced", "sigmas", "SIGMAS"),
            ("ARVideoI2V", "LATENT", "SamplerCustomAdvanced", "latent_image", "LATENT"),
            ("SamplerCustomAdvanced", "output", "VAEDecode", "samples", "LATENT"),
            ("VAEDecode", "IMAGE", "CreateVideo", "images", "IMAGE"),
        }:
            self.assertIn(edge, ar_edges)
        root_nodes = graph_nodes(ar_record["payload"])
        self.assertEqual("96ba6b5d-dd48-49b3-84c3-5b86eafc2a07", root_nodes[29]["type"])
        root_edges = typed_edges(ar_record["payload"])
        self.assertIn(("LoadImage", "IMAGE", "96ba6b5d-dd48-49b3-84c3-5b86eafc2a07", "start_image", "IMAGE"), root_edges)
        self.assertIn(("96ba6b5d-dd48-49b3-84c3-5b86eafc2a07", "VIDEO", "SaveVideo", "video", "VIDEO"), root_edges)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_ast_probe(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((path for path in candidates if path.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter")
        result = subprocess.run(
            [str(python), str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            env={**os.environ, "PYTHONUTF8": "1"},
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        constructors = payload["constructors"]
        self.assertEqual(
            {"kind": "named", "name": "euler_cfg_pp", "options": {}, "inpaintOptions": {}},
            constructors["eulerRegular"],
        )
        self.assertEqual("sample_euler_pp", constructors["eulerAlternative"]["function"])
        self.assertEqual("callable", constructors["eulerAlternative"]["kind"])
        self.assertEqual(
            {"s_noise": 1.0, "s_noise_end": 0.25, "noise_clip_std": 2.5},
            constructors["lcm"]["options"],
        )
        self.assertEqual(("named", "lcm"), (constructors["lcm"]["kind"], constructors["lcm"]["name"]))
        self.assertEqual(
            {"total_upscale": 2.0, "upscale_steps": None, "upscale_method": "bislerp"},
            constructors["lcmUpscaleAuto"]["options"],
        )
        self.assertEqual(
            {"total_upscale": 1.5, "upscale_steps": 3, "upscale_method": "bicubic"},
            constructors["lcmUpscaleExplicit"]["options"],
        )
        self.assertEqual("sample_lcm_upscale", constructors["lcmUpscaleAuto"]["function"])
        self.assertEqual(
            {"num_frame_per_block": 3},
            constructors["arVideo"]["options"],
        )
        self.assertEqual(("named", "ar_video"), (constructors["arVideo"]["kind"], constructors["arVideo"]["name"]))

        self.assertEqual(17.0, payload["eulerWrapper"]["result"])
        self.assertEqual(
            {
                "extra_args": {"seed": 9},
                "callback": None,
                "disable": True,
                "eta": 0.0,
                "s_noise": 0.0,
                "noise_sampler": None,
            },
            payload["eulerWrapper"]["forwarded"][0],
        )
        lcm_algorithm = payload["lcmAlgorithm"]
        self.assertEqual([1.0, 2.0], lcm_algorithm["interpolatedNoiseMeans"])
        self.assertEqual([2.0, 1.0], lcm_algorithm["interpolatedSigmas"])
        self.assertEqual([0.5], lcm_algorithm["constantNoiseMeans"])
        self.assertAlmostEqual(lcm_algorithm["expectedClip"], lcm_algorithm["clippedMaximum"], places=6)

        upscale_algorithm = payload["upscaleAlgorithm"]
        self.assertEqual(
            [
                {"inputShape": [1, 1, 3, 4], "width": 6, "height": 4, "method": "bislerp", "crop": "disabled"},
                {"inputShape": [1, 1, 4, 6], "width": 8, "height": 6, "method": "bislerp", "crop": "disabled"},
            ],
            upscale_algorithm["autoCalls"],
        )
        self.assertEqual([1, 1, 6, 8], upscale_algorithm["autoResultShape"])
        self.assertEqual(
            [{"inputShape": [1, 1, 3, 4], "width": 8, "height": 6, "method": "bicubic", "crop": "disabled"}],
            upscale_algorithm["explicitCalls"],
        )
        self.assertEqual([1, 1, 6, 8], upscale_algorithm["explicitResultShape"])
        self.assertIn("requires 5-D video latents", payload["arValidation"]["rankError"])
        self.assertIn("got 4-D tensor", payload["arValidation"]["rankError"])
        self.assertIn("init_kv_caches()", payload["arValidation"]["interfaceError"])
        self.assertIn("init_crossattn_caches()", payload["arValidation"]["interfaceError"])


if __name__ == "__main__":
    unittest.main()
