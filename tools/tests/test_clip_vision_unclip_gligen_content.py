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
    "core.clip-vision-loader": {
        "directory": "clip-vision-loader",
        "classType": "CLIPVisionLoader",
        "fingerprint": "sha256:51c6657ce101c57646f468509b8f221478c86942f23486b67838bb59319c0d41",
        "category": "model/loaders",
        "recipe": "recipe.load-and-encode-clip-vision",
        "required": {"clip_name": [[]]},
        "outputs": ["CLIP_VISION"],
    },
    "core.unclip-checkpoint-loader": {
        "directory": "unclip-checkpoint-loader",
        "classType": "unCLIPCheckpointLoader",
        "fingerprint": "sha256:12837b6dd3fec9e42756ef88636e7f56f51508093951fc5b435717cd5c4d2b67",
        "category": "model/loaders",
        "recipe": "recipe.load-unclip-image-conditioning",
        "required": {"ckpt_name": [[]]},
        "outputs": ["MODEL", "CLIP", "VAE", "CLIP_VISION"],
    },
    "core.gligen-loader": {
        "directory": "gligen-loader",
        "classType": "GLIGENLoader",
        "fingerprint": "sha256:d87968d9c43ce26992edd9757b34ce0469e91be1dec348875cb151df645401ac",
        "category": "model/loaders",
        "recipe": "recipe.apply-gligen-text-box",
        "required": {"gligen_name": [[]]},
        "outputs": ["GLIGEN"],
    },
    "core.gligen-text-box-apply": {
        "directory": "gligen-text-box-apply",
        "classType": "GLIGENTextBoxApply",
        "fingerprint": "sha256:ebd993b388d98a30147b048936e3978205a72061b4fb11a5896c1ea1818b06ca",
        "category": "model/conditioning/gligen",
        "recipe": "recipe.apply-gligen-text-box",
        "required": {
            "conditioning_to": ["CONDITIONING"],
            "clip": ["CLIP"],
            "gligen_textbox_model": ["GLIGEN"],
            "text": ["STRING", {"multiline": True, "dynamicPrompts": True}],
            "width": ["INT", {"default": 64, "min": 8, "max": 16384, "step": 8}],
            "height": ["INT", {"default": 64, "min": 8, "max": 16384, "step": 8}],
            "x": ["INT", {"default": 0, "min": 0, "max": 16384, "step": 8}],
            "y": ["INT", {"default": 0, "min": 0, "max": 16384, "step": 8}],
        },
        "outputs": ["CONDITIONING"],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.load-and-encode-clip-vision": "load-and-encode-clip-vision",
    "recipe.load-unclip-image-conditioning": "load-unclip-image-conditioning",
    "recipe.apply-gligen-text-box": "apply-gligen-text-box",
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
INVENTORY_METADATA = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = catalog.ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
SYNTHETIC_PROBE = Path(__file__).with_name("clip_vision_unclip_gligen_synthetic_probe.py")


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


def iter_graphs(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for index, subgraph in enumerate(subgraphs):
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield f"sg{index}", subgraph


class ClipVisionUnclipGligenContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_cross_links_validate(self) -> None:
        article_ids = all_article_ids()
        schemas = {
            "article": catalog.load_json(catalog.CONTENT / "schemas" / "article.schema.v1.json"),
            "recipe": catalog.load_json(catalog.CONTENT / "schemas" / "recipe.schema.v1.json"),
            "fragment": catalog.load_json(catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"),
            "research": catalog.load_json(catalog.CONTENT / "schemas" / "article-research.schema.v1.json"),
        }
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertFalse(article["experimental"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual("nodes", article["runtimeIdentity"]["pythonModule"])
            self.assertIn(
                spec["recipe"],
                {item["id"] for item in article["assets"] if item["type"] == "recipe"},
            )

            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets - article_ids))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|"
                r"в современном мире|революционн|является мощн|"
                r"\bдавайте\b|глубже погруз|открывает новые|"
                r"может показаться|позволяет вам|подводя итог|"
                r"в заключение|данная нода|не просто .{0,80},? а ",
            )

            research = catalog.load_json(catalog.CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(research, schemas["research"]))
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertTrue(research["checks"]["implementationRead"])
            self.assertTrue(research["checks"]["runtimeCompared"])
            self.assertTrue(research["checks"]["officialCasesInspected"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])

        self.assertEqual([], errors)

    def test_exact_runtime_fingerprints_flags_ports_and_fragment_contracts(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        metadata = catalog.load_json(INVENTORY_METADATA)
        self.assertEqual(SOURCE_COMMIT, metadata["source"]["commit"])
        self.assertEqual("0.32.0", metadata["source"]["backendVersion"])
        self.assertEqual("/object_info", metadata["capture"]["endpoint"])

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("nodes", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["required"], runtime["input"]["required"])
            self.assertEqual(spec["outputs"], runtime["output"])
            self.assertEqual(spec["outputs"], runtime["output_name"])
            self.assertEqual([False] * len(spec["outputs"]), runtime["output_is_list"])
            self.assertFalse(runtime["output_node"])
            for flag in ("deprecated", "experimental", "dev_only", "api_node"):
                self.assertFalse(runtime.get(flag, False), (article_id, flag))
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], runtime))
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        for recipe_id in RECIPE_DIRECTORIES:
            recipe = catalog.load_json(recipe_path(recipe_id))
            fragment = catalog.load_json(recipe_path(recipe_id).parent / recipe["fragment"]["path"])
            by_ref = {item["ref"]: item for item in fragment["nodes"]}
            supplied: dict[str, set[str]] = {ref: set(node["settings"]) for ref, node in by_ref.items()}
            for external in fragment["externalInputs"]:
                supplied[external["to"]].add(external["input"])
                runtime = nodes[by_ref[external["to"]]["classType"]]
                self.assertEqual(external["type"], runtime["input"]["required"][external["input"]][0])
            for connection in fragment["connections"]:
                supplied[connection["to"]].add(connection["input"])
                source_runtime = nodes[by_ref[connection["from"]]["classType"]]
                target_runtime = nodes[by_ref[connection["to"]]["classType"]]
                output_index = source_runtime["output_name"].index(connection["output"])
                self.assertEqual(
                    source_runtime["output"][output_index],
                    target_runtime["input"]["required"][connection["input"]][0],
                )
            for ref, node in by_ref.items():
                runtime = nodes[node["classType"]]
                self.assertTrue(set(runtime["input"]["required"]).issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = runtime["input"]["required"][name]
                    if descriptor[0] in ("INT", "FLOAT"):
                        self.assertGreaterEqual(value, descriptor[1]["min"])
                        self.assertLessEqual(value, descriptor[1]["max"])
                    elif isinstance(descriptor[0], list) and descriptor[0]:
                        self.assertIn(value, descriptor[0])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_exact_pinned_source_component_crop_gligen_and_sampler_semantics(self) -> None:
        self.assertEqual(SOURCE_COMMIT, (SOURCE / ".git" / "HEAD").read_text(encoding="utf-8").strip())
        source = (SOURCE / "nodes.py").read_text(encoding="utf-8")
        clip_vision = (SOURCE / "comfy" / "clip_vision.py").read_text(encoding="utf-8")
        sd = (SOURCE / "comfy" / "sd.py").read_text(encoding="utf-8")
        supported = (SOURCE / "comfy" / "supported_models.py").read_text(encoding="utf-8")
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(encoding="utf-8")
        gligen = (SOURCE / "comfy" / "gligen.py").read_text(encoding="utf-8")
        samplers = (SOURCE / "comfy" / "samplers.py").read_text(encoding="utf-8")
        helpers = (SOURCE / "comfy" / "sampler_helpers.py").read_text(encoding="utf-8")

        vision_loader = source.split("class CLIPVisionLoader:", 1)[1].split("class CLIPVisionEncode:", 1)[0]
        vision_encode = source.split("class CLIPVisionEncode:", 1)[1].split("class StyleModelLoader:", 1)[0]
        unclip_loader = source.split("class unCLIPCheckpointLoader:", 1)[1].split("class CLIPSetLastLayer:", 1)[0]
        gligen_loader = source.split("class GLIGENLoader:", 1)[1].split("class GLIGENTextBoxApply:", 1)[0]
        gligen_apply = source.split("class GLIGENTextBoxApply:", 1)[1].split("class EmptyLatentImage:", 1)[0]

        self.assertIn('get_full_path_or_raise("clip_vision", clip_name)', vision_loader)
        self.assertIn("comfy.clip_vision.load(clip_path)", vision_loader)
        self.assertIn("clip vision file is invalid and does not contain a valid vision model", vision_loader)
        self.assertNotIn("crop", vision_loader)
        self.assertIn("clip_vision.encode_image(image, crop=crop_image)", vision_encode)
        for model_type in ("clip_vision_model", "siglip_vision_model", "siglip2_vision_model", "dinov2", "dinov3"):
            self.assertIn(f'"{model_type}"', clip_vision)
        self.assertIn("else:\n        return None", clip_vision)

        self.assertIn('RETURN_TYPES = ("MODEL", "CLIP", "VAE", "CLIP_VISION")', unclip_loader)
        self.assertIn("output_vae=True, output_clip=True, output_clipvision=True", unclip_loader)
        self.assertIn("if model_config.clip_vision_prefix is not None:", sd)
        self.assertIn("return (model_patcher, clip, vae, clipvision)", sd)
        self.assertIn("class SD21UnclipL", supported)
        self.assertIn("class SD21UnclipH", supported)
        self.assertIn('clip_vision_prefix = "embedder.model.visual."', supported)
        self.assertIn("class SD21UNCLIP", model_base)
        self.assertIn("def sdxl_pooled", model_base)
        self.assertIn('if "unclip_conditioning" in args:', model_base)

        self.assertIn('get_full_path_or_raise("gligen", gligen_name)', gligen_loader)
        self.assertIn("safe_load=True", sd)
        self.assertIn("model_management.should_use_fp16()", sd)
        self.assertIn("model = model.half()", sd)
        self.assertIn("CoreModelPatcher(model", sd)
        self.assertIn("position_net.null_positive_feature", gligen)
        self.assertIn("self.max_objs = 30", gligen)
        self.assertIn("x1 = (p[4]) / w", gligen)
        self.assertIn("y2 = (p[3] + p[1]) / h", gligen)

        self.assertIn('return_pooled="unprojected"', gligen_apply)
        self.assertIn("(cond_pooled, height // 8, width // 8, y // 8, x // 8)", gligen_apply)
        self.assertIn("prev + position_params", gligen_apply)
        self.assertIn("gligen_model.model.set_position(input_x.shape", samplers)
        self.assertIn("patches['middle_patch']", samplers)
        self.assertIn('get_models_from_cond(conds[k], "gligen")', helpers)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent")
    def test_embedded_docs_hash_paths_and_documented_gaps(self) -> None:
        self.assertEqual(DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            docs: dict[tuple[str, str], str] = {}
            archive_directories = {
                "CLIPVisionLoader": "ClipVisionLoader",
                "unCLIPCheckpointLoader": "UnclipCheckpointLoader",
                "GLIGENLoader": "GligenLoader",
                "GLIGENTextBoxApply": "GligenTextBoxApply",
            }
            for spec in ARTICLE_SPECS.values():
                for locale in ("en", "ru"):
                    directory = archive_directories[spec["classType"]]
                    path = f"comfyui_embedded_docs/docs/{directory}/{locale}.md"
                    self.assertIn(path, archive.namelist())
                    docs[(spec["classType"], locale)] = archive.read(path).decode("utf-8")

        for spec in ARTICLE_SPECS.values():
            self.assertIn("This documentation was AI-generated", docs[(spec["classType"], "en")])
        self.assertNotIn("siglip", docs[("CLIPVisionLoader", "en")].lower())
        self.assertNotIn("crop", docs[("CLIPVisionLoader", "en")].lower())
        self.assertNotIn("clip_vision_prefix", docs[("unCLIPCheckpointLoader", "en")])
        self.assertNotIn("fp16", docs[("GLIGENLoader", "en")].lower())
        apply_docs = docs[("GLIGENTextBoxApply", "en")].lower()
        self.assertNotIn("unprojected", apply_docs)
        self.assertNotIn("// 8", apply_docs)
        self.assertNotIn("30", apply_docs)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_census_and_representative_topology(self) -> None:
        self.assertEqual(WORKFLOW_WHEEL_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        occurrences: dict[str, list[tuple[str, str, dict[str, Any]]]] = {target: [] for target in targets}
        json_count = dict_count = list_count = graph_count = subgraph_count = 0
        revision: dict[str, Any] | None = None

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(member for member in archive.namelist() if "/templates/" in member and member.endswith(".json"))
            for member in members:
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if isinstance(payload, list):
                    list_count += 1
                    continue
                if not isinstance(payload, dict):
                    continue
                dict_count += 1
                graphs = list(iter_graphs(payload))
                if graphs:
                    graph_count += 1
                subgraph_count += sum(scope != "root" for scope, _ in graphs)
                if Path(member).name == "sdxl_revision_text_prompts.json":
                    revision = payload
                for scope, graph in graphs:
                    for node in graph["nodes"]:
                        if isinstance(node, dict) and node.get("type") in targets:
                            occurrences[node["type"]].append((Path(member).name, scope, node))

        self.assertEqual((512, 499, 13, 496, 272), (json_count, dict_count, list_count, graph_count, subgraph_count))
        clip_hits = occurrences["CLIPVisionLoader"]
        self.assertEqual(25, len(clip_hits))
        self.assertEqual(21, len({name for name, _, _ in clip_hits}))
        clip_files = {name for name, _, _ in clip_hits}
        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            clip_workflow_ids = {
                json.loads(archive.read(member).decode("utf-8")).get("id")
                for member in archive.namelist()
                if Path(member).name in clip_files
            }
        self.assertEqual(15, len(clip_workflow_ids))
        self.assertEqual((10, 15), (sum(scope == "root" for _, scope, _ in clip_hits), sum(scope != "root" for _, scope, _ in clip_hits)))
        self.assertEqual({0}, {node.get("mode") for _, _, node in clip_hits})
        widgets = Counter(tuple(node.get("widgets_values") or []) for _, _, node in clip_hits)
        self.assertEqual(
            Counter({
                ("clip_vision_h.safetensors",): 16,
                ("sigclip_vision_patch14_384.safetensors",): 7,
                ("clip_vision_g.safetensors",): 1,
                ("dino_v3_vit_h.safetensors",): 1,
            }),
            widgets,
        )
        for target in ("unCLIPCheckpointLoader", "GLIGENLoader", "GLIGENTextBoxApply"):
            self.assertEqual([], occurrences[target])

        self.assertIsNotNone(revision)
        assert revision is not None
        self.assertEqual("22fbfe6b-e7d7-4193-8409-8599b5dce771", revision["id"])
        by_id = {node["id"]: node for node in revision["nodes"]}
        self.assertEqual("CLIPVisionLoader", by_id[39]["type"])
        self.assertEqual(["clip_vision_g.safetensors"], by_id[39]["widgets_values"])
        self.assertEqual(["center"], by_id[13]["widgets_values"])
        self.assertEqual(["center"], by_id[36]["widgets_values"])
        links = {(link[1], link[2], link[3], link[4], link[5]) for link in revision["links"] if isinstance(link, list)}
        self.assertIn((39, 0, 13, 0, "CLIP_VISION"), links)
        self.assertIn((39, 0, 36, 0, "CLIP_VISION"), links)
        self.assertIn((13, 0, 19, 1, "CLIP_VISION_OUTPUT"), links)
        self.assertIn((36, 0, 37, 1, "CLIP_VISION_OUTPUT"), links)
        self.assertIn((19, 0, 37, 0, "CONDITIONING"), links)

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_exact_source_dispatch_and_metadata_probe_without_weights(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", "")) / "nodes-wizard-comfyui-v0.32.0-venv" / "Scripts" / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for isolated probe")
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=catalog.ROOT,
            env={**os.environ, "PYTHONUTF8": "1"},
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(["vision-model"], payload["clipVisionLoader"]["output"])
        self.assertEqual(
            "ERROR: clip vision file is invalid and does not contain a valid vision model.",
            payload["clipVisionLoader"]["invalidError"],
        )
        self.assertEqual(["model", "clip", "vae", "embedded-vision"], payload["unclipCheckpointLoader"]["output"])
        self.assertEqual(
            {"output_vae": True, "output_clip": True, "output_clipvision": True, "embedding_directory": ["/models/embeddings"]},
            payload["unclipCheckpointLoader"]["kwargs"],
        )
        self.assertEqual(["gligen-patcher"], payload["gligenLoader"]["output"])
        apply = payload["gligenTextBoxApply"]
        self.assertEqual(["красный куб"], apply["tokenized"])
        self.assertEqual(["unprojected"], apply["returnPooled"])
        self.assertEqual(["unprojected-pooled", 16, 32, 4, 8], apply["newParam"])
        self.assertEqual("new-model", apply["secondGligen"][1])
        self.assertEqual(2, len(apply["secondGligen"][2]))
        self.assertTrue(apply["tensorIdentityPreserved"])
        self.assertTrue(apply["metadataCopied"])
        self.assertTrue(apply["sourceMetadataUnchanged"])


if __name__ == "__main__":
    unittest.main()
