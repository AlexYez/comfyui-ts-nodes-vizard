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
    "core.cfg-override": {
        "directory": "cfg-override",
        "classType": "CFGOverride",
        "pythonModule": "comfy_extras.nodes_custom_sampler",
        "fingerprint": "sha256:8e7d297c11ff0c11918e298798848384ba0b22b81725743d0b691340aff21a82",
        "experimental": False,
        "recipe": "recipe.cfg-override-window",
        "recipeDirectory": "cfg-override-window",
        "targetNodes": {
            "override": (
                "CFGOverride",
                {"cfg": 3.0, "start_percent": 0.7, "end_percent": 1.0},
            ),
            "guider": ("DualModelGuider", {"cfg": 7.0}),
            "sample": ("SamplerCustomAdvanced", {}),
        },
        "connections": {
            ("override", "MODEL", "guider", "model"),
            ("guider", "GUIDER", "sample", "guider"),
        },
    },
    "core.video-linear-cfg-guidance": {
        "directory": "video-linear-cfg-guidance",
        "classType": "VideoLinearCFGGuidance",
        "pythonModule": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:d44e927ba77b0ab10d76ab2f9cbf642bf174d9e830158f5165d272155c7377c7",
        "experimental": False,
        "recipe": "recipe.video-linear-cfg-guidance",
        "recipeDirectory": "video-linear-cfg-guidance",
        "targetNodes": {
            "guidance": ("VideoLinearCFGGuidance", {"min_cfg": 1.0}),
            "sample": (
                "KSampler",
                {
                    "seed": 237514639057514,
                    "steps": 20,
                    "cfg": 2.5,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": 1.0,
                },
            ),
        },
        "connections": {("guidance", "MODEL", "sample", "model")},
    },
    "core.video-triangle-cfg-guidance": {
        "directory": "video-triangle-cfg-guidance",
        "classType": "VideoTriangleCFGGuidance",
        "pythonModule": "comfy_extras.nodes_video_model",
        "fingerprint": "sha256:7daaf0739719dc43d47e3efe41c531ad24ddacd1ad438dfd55b29d05ec062028",
        "experimental": False,
        "recipe": "recipe.video-triangle-cfg-guidance",
        "recipeDirectory": "video-triangle-cfg-guidance",
        "targetNodes": {
            "guidance": ("VideoTriangleCFGGuidance", {"min_cfg": 1.0}),
            "sample": (
                "KSampler",
                {
                    "seed": 0,
                    "steps": 20,
                    "cfg": 2.5,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": 1.0,
                },
            ),
        },
        "connections": {("guidance", "MODEL", "sample", "model")},
    },
    "core.perp-neg-guider": {
        "directory": "perp-neg-guider",
        "classType": "PerpNegGuider",
        "pythonModule": "comfy_extras.nodes_perpneg",
        "fingerprint": "sha256:74a7a7f40a3157ebad5bcc5137c65f80a980452778d01d54d38cd0f094ec8be6",
        "experimental": True,
        "recipe": "recipe.perp-neg-custom-sampling",
        "recipeDirectory": "perp-neg-custom-sampling",
        "targetNodes": {
            "guider": ("PerpNegGuider", {"cfg": 8.0, "neg_scale": 1.0}),
            "sample": ("SamplerCustomAdvanced", {}),
        },
        "connections": {("guider", "GUIDER", "sample", "guider")},
    },
}

TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}
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
PROBE = Path(__file__).with_name("guider_cfg_synthetic_probe.py")


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


def graph_iter(
    payload: dict[str, Any],
) -> Iterator[tuple[str, int | None, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", None, payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, graph in enumerate(subgraphs):
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
            yield "subgraph", index, graph


def normalized_links(
    graph: dict[str, Any],
) -> Iterator[tuple[Any, Any, int, Any, int, Any]]:
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


def graph_nodes(graph: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    return {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    }


def slot_name(node: dict[str, Any], key: str, index: int) -> str | None:
    slots = node.get(key, [])
    if not isinstance(slots, list) or not isinstance(index, int):
        return None
    if not 0 <= index < len(slots) or not isinstance(slots[index], dict):
        return None
    return slots[index].get("name")


def typed_edges(
    graph: dict[str, Any],
) -> set[tuple[str | None, str | None, str | None, str | None, Any]]:
    nodes = graph_nodes(graph)
    result: set[tuple[str | None, str | None, str | None, str | None, Any]] = set()
    for _, source_id, source_slot, target_id, target_slot, link_type in normalized_links(
        graph
    ):
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


def scalar_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from scalar_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from scalar_strings(item)


class GuiderCfgContentTests(unittest.TestCase):
    def test_articles_recipes_fragments_research_and_russian_contract(self) -> None:
        schemas = {
            key: catalog.load_json(catalog.CONTENT / "schemas" / filename)
            for key, filename in {
                "article": "article.schema.v1.json",
                "recipe": "recipe.schema.v1.json",
                "fragment": "recipe-fragment.schema.v1.json",
                "research": "article-research.schema.v1.json",
            }.items()
        }
        inventory = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        article_ids = all_article_ids()
        errors: list[str] = []
        russian_files: list[Path] = []

        for article_id, spec in ARTICLE_SPECS.items():
            manifest_path = article_path(spec)
            article = catalog.load_json(manifest_path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(manifest_path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual(("core", "ru"), (article["kind"], article["locale"]))
            self.assertEqual(
                ("draft", "in_review"),
                (article["status"], article["editorial"]["state"]),
            )
            self.assertIn(
                "human approval pending",
                article["editorial"]["reviewedBy"].casefold(),
            )
            self.assertEqual(spec["experimental"], article["experimental"])
            self.assertEqual(
                {
                    "classType": spec["classType"],
                    "pythonModule": spec["pythonModule"],
                    "packageId": "comfy-core",
                    "origin": "backend",
                    "aliases": [],
                },
                article["runtimeIdentity"],
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual("0.32.0", article["compatibility"]["comfyui"])
            self.assertEqual(">=1.48.7", article["compatibility"]["frontend"])
            self.assertEqual(
                f"ComfyUI v0.32.0 ({SOURCE_COMMIT})",
                article["compatibility"]["sourceRevision"],
            )
            self.assertIn(
                spec["recipe"],
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                },
            )
            relation_targets = set(
                article["relations"]["related"]
                + article["relations"]["alternatives"]
            )
            replaced_by = article["relations"]["replacedBy"]
            if replaced_by is not None:
                relation_targets.add(replaced_by)
            self.assertTrue(
                relation_targets.issubset(article_ids),
                (article_id, relation_targets - article_ids),
            )

            article_body = manifest_path.parent / article["body"]
            body_text = article_body.read_text(encoding="utf-8")
            self.assertEqual(
                10,
                len(re.findall(r"^## .+$", body_text, flags=re.MULTILINE)),
                article_body,
            )
            russian_files.append(article_body)

            research_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            research = catalog.load_json(research_path)
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual(article_id, research["articleId"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual(spec["pythonModule"], research["node"]["pythonModule"])
            self.assertEqual("backend", research["node"]["origin"])
            self.assertEqual(
                ("fact_checked", "automated_assisted"),
                (research["state"], research["reviewMode"]),
            )
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
            for key in (
                "implementationRead",
                "runtimeCompared",
                "officialCasesInspected",
                "exampleSchemaValidated",
                "russianEdited",
                "factsRecheckedAfterEditing",
            ):
                self.assertTrue(research["checks"][key], (article_id, key))
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])
            if spec["classType"] == "VideoLinearCFGGuidance":
                self.assertEqual([], research["evidence"]["embeddedDocs"])
                gaps = " ".join(research["knownGaps"]).casefold()
                self.assertTrue(
                    "отсутств" in gaps or "absent" in gaps,
                    gaps,
                )

            current_recipe_path = recipe_path(spec)
            recipe = catalog.load_json(current_recipe_path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(current_recipe_path, recipe, article_ids, errors)
            self.assertEqual(spec["recipe"], recipe["recipeId"])
            self.assertEqual("ru", recipe["locale"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn(
                "human approval pending",
                recipe["editorial"]["reviewedBy"].casefold(),
            )
            self.assertIn(article_id, recipe["articleIds"])
            self.assertNotIn(
                "workflow", recipe, "examples must remain honest fragment-only recipes"
            )
            russian_files.append(current_recipe_path.parent / recipe["body"])

            fragment_path = current_recipe_path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, schemas["fragment"])
            )
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            nodes = {node["ref"]: node for node in fragment["nodes"]}
            self.assertEqual(set(spec["targetNodes"]), set(nodes))
            for ref, (class_type, settings) in spec["targetNodes"].items():
                self.assertEqual(class_type, nodes[ref]["classType"])
                self.assertEqual(settings, nodes[ref]["settings"])
            self.assertEqual(
                spec["connections"],
                {
                    (
                        item["from"],
                        item["output"],
                        item["to"],
                        item["input"],
                    )
                    for item in fragment["connections"]
                },
            )

            supplied = {ref: set(node["settings"]) for ref, node in nodes.items()}
            for external in fragment["externalInputs"]:
                supplied[external["to"]].add(external["input"])
                target_runtime = inventory[nodes[external["to"]]["classType"]]
                target_inputs = {
                    **target_runtime["input"].get("required", {}),
                    **target_runtime["input"].get("optional", {}),
                }
                self.assertEqual(
                    external["type"], target_inputs[external["input"]][0]
                )
            for connection in fragment["connections"]:
                supplied[connection["to"]].add(connection["input"])
                source_runtime = inventory[nodes[connection["from"]]["classType"]]
                target_runtime = inventory[nodes[connection["to"]]["classType"]]
                output_index = source_runtime["output_name"].index(
                    connection["output"]
                )
                target_inputs = {
                    **target_runtime["input"].get("required", {}),
                    **target_runtime["input"].get("optional", {}),
                }
                self.assertEqual(
                    source_runtime["output"][output_index],
                    target_inputs[connection["input"]][0],
                )
            for ref, node in nodes.items():
                required = set(inventory[node["classType"]]["input"]["required"])
                self.assertTrue(
                    required.issubset(supplied[ref]),
                    (spec["recipe"], ref, required - supplied[ref]),
                )

        self.assertEqual([], errors)
        forbidden = (
            "важно отметить",
            "стоит отметить",
            "следует отметить",
            "в современном мире",
            "давайте",
            "погрузимся",
            "революционн",
            "является мощн",
            "подводя итог",
            "в заключение",
            "данная нода",
        )
        for path in russian_files:
            text = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("\ufffd", text, path)
            for phrase in forbidden:
                self.assertNotIn(phrase, text, path)

    def test_exact_runtime_fingerprints_ports_flags_and_replacements(self) -> None:
        inventory = catalog.object_info_nodes(catalog.load_json(INVENTORY))
        metadata = catalog.load_json(INVENTORY_META)
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("1.48.7", metadata["capture"]["requiredPackages"]["comfyui-frontend-package"])

        expected_required = {
            "CFGOverride": {
                "model": ["MODEL", {}],
                "cfg": [
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.1,
                        "round": 0.01,
                    },
                ],
                "start_percent": [
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001},
                ],
                "end_percent": [
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001},
                ],
            },
            "VideoLinearCFGGuidance": {
                "model": ["MODEL"],
                "min_cfg": [
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.5,
                        "round": 0.01,
                        "advanced": True,
                    },
                ],
            },
            "VideoTriangleCFGGuidance": {
                "model": ["MODEL"],
                "min_cfg": [
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.5,
                        "round": 0.01,
                        "advanced": True,
                    },
                ],
            },
            "PerpNegGuider": {
                "model": ["MODEL", {}],
                "positive": ["CONDITIONING", {}],
                "negative": ["CONDITIONING", {}],
                "empty_conditioning": ["CONDITIONING", {}],
                "cfg": [
                    "FLOAT",
                    {
                        "default": 8.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.1,
                        "round": 0.01,
                    },
                ],
                "neg_scale": [
                    "FLOAT",
                    {
                        "advanced": True,
                        "default": 1.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.01,
                    },
                ],
            },
        }
        expected_order = {
            name: list(required) for name, required in expected_required.items()
        }
        expected_display = {
            "CFGOverride": "CFG Override",
            "VideoLinearCFGGuidance": "Video Linear CFG Guidance",
            "VideoTriangleCFGGuidance": "Video Triangle CFG Guidance",
            "PerpNegGuider": "Perp-Neg Guider",
        }

        for spec in ARTICLE_SPECS.values():
            class_type = spec["classType"]
            runtime = inventory[class_type]
            self.assertEqual(class_type, runtime["name"])
            self.assertEqual(expected_display[class_type], runtime["display_name"])
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual(expected_required[class_type], runtime["input"]["required"])
            self.assertEqual(expected_order[class_type], runtime["input_order"]["required"])
            self.assertEqual(["MODEL"] if class_type != "PerpNegGuider" else ["GUIDER"], runtime["output"])
            self.assertEqual(runtime["output"], runtime["output_name"])
            self.assertEqual([False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            self.assertFalse(runtime["output_node"])
            self.assertFalse(runtime["has_intermediate_output"])
            self.assertEqual(
                [] if class_type.startswith("Video") else None,
                runtime["search_aliases"],
            )
            self.assertEqual(
                spec["fingerprint"], catalog.schema_fingerprint(class_type, runtime)
            )

        self.assertEqual("model/sampling/guiders", inventory["CFGOverride"]["category"])
        self.assertIn("sigma", inventory["CFGOverride"]["description"])
        self.assertEqual("model/sampling/guiders", inventory["VideoLinearCFGGuidance"]["category"])
        self.assertEqual("model/sampling/guiders", inventory["VideoTriangleCFGGuidance"]["category"])
        self.assertEqual("", inventory["VideoLinearCFGGuidance"]["description"])
        self.assertEqual("", inventory["VideoTriangleCFGGuidance"]["description"])
        self.assertEqual("experimental", inventory["PerpNegGuider"]["category"])

        full_flags = (
            "deprecated",
            "experimental",
            "dev_only",
            "api_node",
        )
        for class_type, experimental in (
            ("CFGOverride", False),
            ("PerpNegGuider", True),
        ):
            runtime = inventory[class_type]
            self.assertEqual(
                {
                    "deprecated": False,
                    "experimental": experimental,
                    "dev_only": False,
                    "api_node": False,
                },
                {flag: runtime[flag] for flag in full_flags},
            )
        for class_type in ("VideoLinearCFGGuidance", "VideoTriangleCFGGuidance"):
            runtime = inventory[class_type]
            for flag in full_flags:
                self.assertNotIn(
                    flag,
                    runtime,
                    f"{class_type} is a legacy descriptor: absent raw flags must stay absent",
                )

        replacements_text = json.dumps(catalog.load_json(REPLACEMENTS), ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements_text)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_source_and_embedded_docs_discrepancies(self) -> None:
        self.assertEqual(
            SOURCE_COMMIT,
            (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip(),
        )
        override_source = (
            SOURCE / "comfy_extras" / "nodes_custom_sampler.py"
        ).read_text(encoding="utf-8")
        video_source = (SOURCE / "comfy_extras" / "nodes_video_model.py").read_text(
            encoding="utf-8"
        )
        perp_source = (SOURCE / "comfy_extras" / "nodes_perpneg.py").read_text(
            encoding="utf-8"
        )
        patcher_source = (SOURCE / "comfy" / "patcher_extension.py").read_text(
            encoding="utf-8"
        )

        override = override_source.split("class CFGOverride", 1)[1].split(
            "class CustomSamplersExtension", 1
        )[0]
        self.assertIn("sigma_hi = ms.percent_to_sigma(start_percent)", override)
        self.assertIn("sigma_lo = ms.percent_to_sigma(end_percent)", override)
        self.assertIn("if not (sigma_lo <= sigma <= sigma_hi):", override)
        self.assertIn("saved = guider.cfg", override)
        self.assertIn("finally:", override)
        self.assertIn("guider.cfg = saved", override)
        self.assertIn("m.add_wrapper(comfy.patcher_extension.WrappersMP.PREDICT_NOISE", override)
        self.assertIn("w.append(wrapper)", patcher_source)
        self.assertIn("return self.wrappers[self.idx](self, *args, **kwargs)", patcher_source)

        linear = video_source.split("class VideoLinearCFGGuidance", 1)[1].split(
            "class VideoTriangleCFGGuidance", 1
        )[0]
        triangle = video_source.split("class VideoTriangleCFGGuidance", 1)[1].split(
            "class ImageOnlyCheckpointSave", 1
        )[0]
        for section in (linear, triangle):
            self.assertIn("m = model.clone()", section)
            self.assertIn("m.set_model_sampler_cfg_function(linear_cfg)", section)
            self.assertIn("return uncond + scale * (cond - uncond)", section)
        self.assertIn("torch.linspace(min_cfg, cond_scale, cond.shape[0]", linear)
        self.assertIn("values = torch.linspace(0, 1, cond.shape[0]", triangle)
        self.assertIn("torch.floor(values / period + 0.5)", triangle)

        perp_function = perp_source.split("def perp_neg", 1)[1].split(
            "class PerpNeg", 1
        )[0]
        perp_guider = perp_source.split("class Guider_PerpNeg", 1)[1].split(
            "class PerpNegGuider", 1
        )[0]
        self.assertIn("torch.norm(pos)**2", perp_function)
        self.assertNotIn("clamp", perp_function)
        self.assertIn("cfg_result = noise_pred_nocond + cond_scale*(pos - perp_neg)", perp_function)
        self.assertIn("calc_cond_batch(self.inner_model, conds", perp_guider)
        self.assertIn('model_options.get("sampler_pre_cfg_function", [])', perp_guider)
        self.assertIn('model_options.get("sampler_post_cfg_function", [])', perp_guider)
        self.assertIn("if math.isclose(self.neg_scale, 0.0):", perp_guider)

        self.assertEqual(DOCS_SHA, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            linear_prefix = "comfyui_embedded_docs/docs/VideoLinearCFGGuidance/"
            self.assertFalse(any(name.startswith(linear_prefix) for name in names))

            documents: dict[tuple[str, str], str] = {}
            for class_type in ("CFGOverride", "VideoTriangleCFGGuidance", "PerpNegGuider"):
                for locale in ("en", "ru"):
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    self.assertIn(member, names)
                    text = archive.read(member).decode("utf-8")
                    documents[(class_type, locale)] = text
                    marker = "AI-generated" if locale == "en" else "создана с помощью ИИ"
                    self.assertIn(marker, text)

            self.assertIn(
                "percentage of the total steps", documents[("CFGOverride", "en")]
            )
            self.assertIn("`начальный_процент`", documents[("CFGOverride", "ru")])
            self.assertNotIn("`start_percent`", documents[("CFGOverride", "ru")])
            self.assertIn(
                "oscillates between",
                documents[("VideoTriangleCFGGuidance", "en")],
            )
            self.assertIn("`мин_cfg`", documents[("VideoTriangleCFGGuidance", "ru")])
            self.assertNotIn("`min_cfg`", documents[("VideoTriangleCFGGuidance", "ru")])
            self.assertIn("| `model` |", documents[("VideoTriangleCFGGuidance", "en")])
            self.assertIn("| `guider` |", documents[("PerpNegGuider", "en")])

            triangle_fingerprints = {
                re.search(r"Source fingerprint \(SHA-256\):\*\* `([^`]+)`", text).group(1)
                for (class_type, _), text in documents.items()
                if class_type == "VideoTriangleCFGGuidance"
            }
            perp_fingerprints = {
                re.search(r"Source fingerprint \(SHA-256\):\*\* `([^`]+)`", text).group(1)
                for (class_type, _), text in documents.items()
                if class_type == "PerpNegGuider"
            }
            self.assertEqual(2, len(triangle_fingerprints))
            self.assertEqual(2, len(perp_fingerprints))

    def test_exhaustive_workflow_census_direct_topology_and_index_titles(self) -> None:
        self.assertEqual(
            WORKFLOW_SHA, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest()
        )
        direct: list[dict[str, Any]] = []
        payloads: dict[str, dict[str, Any]] = {}
        exact_scalar_hits = Counter()
        cfg_like_types = Counter()
        json_count = root_graphs = subgraph_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                if not member.endswith(".json") or "/templates/" not in member:
                    continue
                json_count += 1
                payload = json.loads(archive.read(member))
                for text in scalar_strings(payload):
                    if text in TARGET_TYPES:
                        exact_scalar_hits[text] += 1
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("nodes"), list
                ):
                    continue
                root_graphs += 1
                filename = Path(member).name
                payloads[filename] = payload
                definitions = payload.get("definitions")
                subgraphs = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                subgraph_count += sum(isinstance(graph, dict) for graph in subgraphs)
                for scope, graph_index, graph in graph_iter(payload):
                    for node in graph.get("nodes", []):
                        if not isinstance(node, dict):
                            continue
                        class_type = node.get("type") or node.get("class_type")
                        if re.search(r"cfg|guider|guidance", str(class_type), re.I):
                            cfg_like_types[str(class_type)] += 1
                        if class_type in TARGET_TYPES:
                            direct.append(
                                {
                                    "member": filename,
                                    "workflow": payload,
                                    "scope": scope,
                                    "graphIndex": graph_index,
                                    "graph": graph,
                                    "node": node,
                                }
                            )

            english_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.json")
            )
            russian_index = json.loads(
                archive.read("comfyui_workflow_templates_json/templates/index.ru.json")
            )

        self.assertEqual((512, 496, 272), (json_count, root_graphs, subgraph_count))
        self.assertEqual(
            Counter(
                {
                    "CFGOverride": 4,
                    "VideoLinearCFGGuidance": 2,
                }
            ),
            exact_scalar_hits,
            "type and S&R property are the only exact scalar mentions",
        )
        self.assertEqual(
            Counter(
                {
                    "CFGGuider": 62,
                    "CFGNorm": 33,
                    "FluxGuidance": 19,
                    "BasicGuider": 14,
                    "LTXVDualCFGGuider": 5,
                    "DualCFGGuider": 4,
                    "LatentApplyOperationCFG": 3,
                    "DualModelGuider": 2,
                    "CFGOverride": 2,
                    "SkipLayerGuidanceDiT": 2,
                    "CFGZeroStar": 2,
                    "VideoLinearCFGGuidance": 1,
                    "SkipLayerGuidanceDiTSimple": 1,
                }
            ),
            cfg_like_types,
            "generic CFG nodes are adjacent evidence, not direct target instances",
        )
        self.assertEqual(
            Counter(
                {
                    "CFGOverride": 2,
                    "VideoLinearCFGGuidance": 1,
                }
            ),
            Counter(record["node"].get("type") for record in direct),
        )

        override_records = [
            record for record in direct if record["node"].get("type") == "CFGOverride"
        ]
        self.assertEqual(
            {"image_ideogram4_t2i.json", "image_ideogram4_t2i_int8.json"},
            {record["member"] for record in override_records},
        )
        for record in override_records:
            self.assertEqual("fdcfc2b2-168f-4f3d-a1d0-6986b802fce5", record["workflow"].get("id"))
            self.assertEqual(("subgraph", 0), (record["scope"], record["graphIndex"]))
            self.assertEqual("83e6e004-48ea-408e-9024-eb49c3d7dc14", record["graph"].get("id"))
            self.assertEqual("Text to Image (Ideogram v4)", record["graph"].get("name"))
            self.assertEqual(
                (157, 0, {}, [3, 0.7, 1]),
                tuple(
                    record["node"][key]
                    for key in ("id", "mode", "flags", "widgets_values")
                ),
            )
            self.assertEqual("comfy-core", record["node"]["properties"]["cnr_id"])
            self.assertEqual("0.23.0", record["node"]["properties"]["ver"])
            self.assertTrue(all(isinstance(link, dict) for link in record["graph"]["links"]))
            edges = typed_edges(record["graph"])
            for edge in {
                ("UNETLoader", "MODEL", "CFGOverride", "model", "MODEL"),
                ("CFGOverride", "MODEL", "DualModelGuider", "model", "MODEL"),
                ("DualModelGuider", "GUIDER", "SamplerCustomAdvanced", "guider", "GUIDER"),
                ("KSamplerSelect", "SAMPLER", "SamplerCustomAdvanced", "sampler", "SAMPLER"),
                ("Ideogram4Scheduler", "SIGMAS", "SamplerCustomAdvanced", "sigmas", "SIGMAS"),
            }:
                self.assertIn(edge, edges)
            nodes = graph_nodes(record["graph"])
            self.assertEqual(["euler"], nodes[16]["widgets_values"])
            self.assertEqual([20, 1024, 1024, 0.5, 1.75], nodes[17]["widgets_values"])
            root_nodes = graph_nodes(record["workflow"])
            self.assertEqual(
                ("83e6e004-48ea-408e-9024-eb49c3d7dc14", 0),
                (root_nodes[98]["type"], root_nodes[98]["mode"]),
            )

        linear_record = next(
            record
            for record in direct
            if record["node"].get("type") == "VideoLinearCFGGuidance"
        )
        self.assertEqual("txt_to_image_to_video.json", linear_record["member"])
        self.assertEqual("858d315b-00e0-4802-b61b-fadbacbedaaf", linear_record["workflow"].get("id"))
        self.assertEqual(("root", None), (linear_record["scope"], linear_record["graphIndex"]))
        self.assertFalse(linear_record["workflow"].get("definitions"))
        self.assertEqual(
            (14, 0, {}, [1]),
            tuple(
                linear_record["node"][key]
                for key in ("id", "mode", "flags", "widgets_values")
            ),
        )
        self.assertEqual(
            {"Node name for S&R": "VideoLinearCFGGuidance"},
            linear_record["node"]["properties"],
        )
        self.assertTrue(all(isinstance(link, list) for link in linear_record["graph"]["links"]))
        linear_edges = typed_edges(linear_record["graph"])
        for edge in {
            ("ImageOnlyCheckpointLoader", "MODEL", "VideoLinearCFGGuidance", "model", "MODEL"),
            ("VideoLinearCFGGuidance", "MODEL", "KSampler", "model", "MODEL"),
            ("SVD_img2vid_Conditioning", "positive", "KSampler", "positive", "CONDITIONING"),
            ("SVD_img2vid_Conditioning", "negative", "KSampler", "negative", "CONDITIONING"),
            ("SVD_img2vid_Conditioning", "latent", "KSampler", "latent_image", "LATENT"),
        }:
            self.assertIn(edge, linear_edges)
        linear_nodes = graph_nodes(linear_record["graph"])
        self.assertEqual(["svd_xt.safetensors"], linear_nodes[15]["widgets_values"])
        self.assertEqual(
            [237514639057514, "randomize", 20, 2.5, "euler", "karras", 1],
            linear_nodes[3]["widgets_values"],
        )
        self.assertEqual([1024, 576, 25, 127, 6, 0], linear_nodes[12]["widgets_values"])

        def title_map(index: list[dict[str, Any]]) -> dict[str, str]:
            return {
                template["name"]: template["title"]
                for category in index
                for template in category.get("templates", [])
                if isinstance(template, dict)
            }

        en_titles = title_map(english_index)
        ru_titles = title_map(russian_index)
        self.assertEqual("SVD Text to Image to Video", en_titles["txt_to_image_to_video"])
        self.assertEqual("SVD Текст в изображение в видео", ru_titles["txt_to_image_to_video"])
        self.assertEqual("Ideogram v4: Text to Image", en_titles["image_ideogram4_t2i"])
        self.assertEqual("Ideogram v4: текст в изображение", ru_titles["image_ideogram4_t2i"])
        self.assertEqual("Ideogram v4 Int8: Text to Image", en_titles["image_ideogram4_t2i_int8"])
        self.assertEqual("Ideogram v4 Int8: текст в изображение", ru_titles["image_ideogram4_t2i_int8"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_ast_probe_without_weights(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        result = json.loads(completed.stdout.strip().splitlines()[-1])

        override = result["override"]
        self.assertEqual([2.0, 8.0], override["sigmaBounds"])
        self.assertEqual((9.0, [9.0], 9.0), (override["outsideResult"], override["outsideSeen"], override["outsideRestored"]))
        self.assertEqual((3.0, [3.0], 9.0), (override["insideResult"], override["insideSeen"], override["insideRestored"]))
        self.assertEqual([3.0, 3.0], override["endpointSeen"])
        self.assertEqual([3.0], override["failureSeen"])
        self.assertEqual(9.0, override["failureRestored"])
        self.assertEqual("synthetic executor failure", override["failureMessage"])
        self.assertEqual((9.0, [9.0], 9.0), (override["reversedResult"], override["reversedSeen"], override["reversedRestored"]))

        video = result["video"]
        self.assertTrue(video["originalUnchanged"])
        self.assertEqual((1, 1, 1), (video["linearSetCount"], video["triangleSetCount"], video["chainedSetCount"]))
        self.assertEqual([1.0], video["linear"]["1"])
        self.assertEqual([1.0, 5.0], video["linear"]["2"])
        self.assertEqual([1.0, 2.0, 3.0, 4.0, 5.0], video["linear"]["5"])
        self.assertEqual([1.0], video["triangle"]["1"])
        self.assertEqual([1.0, 1.0], video["triangle"]["2"])
        self.assertEqual([1.0, 3.0, 5.0, 3.0, 1.0], video["triangle"]["5"])
        self.assertAlmostEqual(1.0, video["triangle"]["4"][0], places=6)
        self.assertAlmostEqual(11.0 / 3.0, video["triangle"]["4"][1], places=5)
        self.assertAlmostEqual(11.0 / 3.0, video["triangle"]["4"][2], places=5)
        self.assertAlmostEqual(1.0, video["triangle"]["4"][3], places=6)
        self.assertEqual([1.0, 2.0, 3.0, 4.0, 5.0], video["chainedLinearStillLinear"])
        self.assertEqual([1.0, 3.0, 5.0, 3.0, 1.0], video["chainedFinalTriangle"])

        perp = result["perpNeg"]
        self.assertEqual([4.0, -1.0], perp["normal"])
        self.assertTrue(perp["zeroNormAllNan"])
        self.assertTrue(all(value != value for value in perp["zeroNorm"]))
        self.assertEqual(
            {
                "cfg": 8.0,
                "negScale": 1.0,
                "condKeys": ["empty_negative_prompt", "negative", "positive"],
                "emptyPromptType": "negative",
            },
            perp["constructor"],
        )


if __name__ == "__main__":
    unittest.main()
