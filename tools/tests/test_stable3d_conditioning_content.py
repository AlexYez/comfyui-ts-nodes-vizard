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
from typing import Any

from tools import catalog


ARTICLE_SPECS: dict[str, dict[str, Any]] = {
    "core.stable-zero123-conditioning": {
        "directory": "stable-zero123-conditioning",
        "classType": "StableZero123_Conditioning",
        "category": "model/conditioning/stable zero123",
        "fingerprint": "sha256:64b1504203fd0c301fa0582b51bf23fb6c9d2fb6aac24bfc8a2efee37ae0dba4",
        "recipe": "recipe.stable-zero123-conditioning-basic",
        "required": [
            "clip_vision",
            "init_image",
            "vae",
            "width",
            "height",
            "batch_size",
            "elevation",
            "azimuth",
        ],
    },
    "core.stable-zero123-conditioning-batched": {
        "directory": "stable-zero123-conditioning-batched",
        "classType": "StableZero123_Conditioning_Batched",
        "category": "model/conditioning/stable zero123",
        "fingerprint": "sha256:d14dd6535cae9ff6003f0b0f47255974e4662957028e3039157e4ec4ce211e54",
        "recipe": "recipe.stable-zero123-conditioning-batched-orbit",
        "required": [
            "clip_vision",
            "init_image",
            "vae",
            "width",
            "height",
            "batch_size",
            "elevation",
            "azimuth",
            "elevation_batch_increment",
            "azimuth_batch_increment",
        ],
    },
    "core.sv3d-conditioning": {
        "directory": "sv3d-conditioning",
        "classType": "SV3D_Conditioning",
        "category": "model/conditioning/stable video 3d",
        "fingerprint": "sha256:bcf423ac3af14c084e58691891d2159fee629a5b1f035e7ffda7ea3e343f21d5",
        "recipe": "recipe.sv3d-conditioning-orbit",
        "required": [
            "clip_vision",
            "init_image",
            "vae",
            "width",
            "height",
            "video_frames",
            "elevation",
        ],
    },
}

RECIPE_DIRECTORIES = {
    "recipe.stable-zero123-conditioning-basic": "stable-zero123-conditioning-basic",
    "recipe.stable-zero123-conditioning-batched-orbit": "stable-zero123-conditioning-batched-orbit",
    "recipe.sv3d-conditioning-orbit": "sv3d-conditioning-orbit",
}

EXPECTED_FRAGMENT_SETTINGS = {
    "recipe.stable-zero123-conditioning-basic": {
        "width": 256,
        "height": 256,
        "batch_size": 1,
        "elevation": 0.0,
        "azimuth": 0.0,
    },
    "recipe.stable-zero123-conditioning-batched-orbit": {
        "width": 256,
        "height": 256,
        "batch_size": 8,
        "elevation": 0.0,
        "azimuth": 0.0,
        "elevation_batch_increment": 0.0,
        "azimuth_batch_increment": 45.0,
    },
    "recipe.sv3d-conditioning-orbit": {
        "width": 576,
        "height": 576,
        "video_frames": 21,
        "elevation": 0.0,
    },
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
INVENTORY_META = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
REPLACEMENTS = catalog.CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
REPLACEMENTS_SHA256 = "4d9e22176cbddd8c309707d434f011854cd768f92146586bf9e17c01e93ae5b6"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
SOURCE_COMMIT = "c2bcbecd82ec5ae66594340b395c24ef0217b238"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
DOCS_WHEEL_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
DOC_HASHES = {
    "StableZero123_Conditioning": {
        "en": "2ea6e68e9b5c5907039042d4f4afbc9c54df3854b7c5abf720bbc2685dd6cbf0",
        "ru": "059c377b64b8e1ca8d7505f11f911e534e980d4ea40462457caa3e2eb93fad08",
    },
    "StableZero123_Conditioning_Batched": {
        "en": "e09301558ca0e785b54673c056881930f88a5b9ed606c6400848b32880e42de9",
        "ru": "09c6362482c5a61c25bcd3d45265af8a748c3e97f67d5837388f63467a8d5e40",
    },
    "SV3D_Conditioning": {
        "en": "d8240bbbcc3a521053f02a4617c2ca1c6317afde1687bd30cac52960f0b4da34",
        "ru": "29d9fdd1c4e55256992b8ce03929114785b979ddbccad9ed2eee5d6969306132",
    },
}
PROBE = Path(__file__).with_name("stable3d_conditioning_synthetic_probe.py")


def article_path(spec: dict[str, Any]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return (
        catalog.CONTENT
        / "recipes"
        / RECIPE_DIRECTORIES[recipe_id]
        / "recipe.json"
    )


def all_ids(root: Path, filename: str, field: str) -> list[str]:
    result: list[str] = []
    for path in root.rglob(filename):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get(field), str):
            result.append(payload[field])
    return result


def descriptor_type(descriptor: Any) -> str | None:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    value = descriptor[0]
    return "COMBO" if isinstance(value, list) or value == "COMBO" else value


class Stable3DConditioningContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_natural_russian_contract(self) -> None:
        article_ids_list = all_ids(
            catalog.CONTENT / "articles", "manifest.json", "articleId"
        )
        recipe_ids_list = all_ids(
            catalog.CONTENT / "recipes", "recipe.json", "recipeId"
        )
        article_counts = Counter(article_ids_list)
        recipe_counts = Counter(recipe_ids_list)
        for article_id, spec in ARTICLE_SPECS.items():
            self.assertEqual(1, article_counts[article_id], article_id)
            self.assertEqual(1, recipe_counts[spec["recipe"]], spec["recipe"])
        article_ids = set(article_ids_list)

        schemas = {
            "article": catalog.load_json(
                catalog.CONTENT / "schemas" / "article.schema.v1.json"
            ),
            "recipe": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe.schema.v1.json"
            ),
            "fragment": catalog.load_json(
                catalog.CONTENT / "schemas" / "recipe-fragment.schema.v1.json"
            ),
            "research": catalog.load_json(
                catalog.CONTENT / "schemas" / "article-research.schema.v1.json"
            ),
        }
        banned = re.compile(
            r"без воды|коротко о главном|понятно и доступно|по-честному|"
            r"идеальн|революционн|уникальная возможность|в современном мире|"
            r"важно отметить|стоит отметить|следует отметить|\bдавайте\b|"
            r"глубже погруз|открывает новые|может показаться|позволяет вам|"
            r"подводя итог|в заключение|данная нода|является мощн|"
            r"вот перевод|не просто .{0,80},? а ",
            flags=re.IGNORECASE,
        )
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
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertEqual([], article["runtimeIdentity"]["aliases"])
            self.assertEqual(
                {spec["recipe"]},
                {
                    asset["id"]
                    for asset in article["assets"]
                    if asset["type"] == "recipe"
                },
            )
            relations = article["relations"]
            targets = set(relations["related"] + relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.add(relations["replacedBy"])
            self.assertTrue(targets.issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(
                EXPECTED_HEADINGS,
                re.findall(r"^## (.+)$", body, flags=re.MULTILINE),
            )
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), article_id)
            self.assertIn(spec["fingerprint"], body)
            self.assertIn("официальн", body.lower())

            research = catalog.load_json(
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            self.assertEqual(
                [], catalog.json_schema_errors(research, schemas["research"])
            )
            self.assertEqual(spec["classType"], research["node"]["classType"])
            self.assertEqual("fact_checked", research["state"])
            self.assertEqual("automated_assisted", research["reviewMode"])
            self.assertTrue(research["checks"]["officialCasesInspected"])
            self.assertTrue(research["checks"]["exampleSchemaValidated"])
            self.assertFalse(research["checks"]["exampleExecuted"])
            self.assertTrue(research["checks"]["russianEdited"])
            self.assertTrue(research["checks"]["factsRecheckedAfterEditing"])
            self.assertIn(
                "Статья ожидает человеческого утверждения.",
                research["knownGaps"],
            )

        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertIn("human approval pending", recipe["editorial"]["reviewedBy"])
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertNotIn("\ufffd", body)
            self.assertIsNone(banned.search(body), directory)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual(
                [], catalog.json_schema_errors(fragment, schemas["fragment"])
            )
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(recipe["fragment"]["id"], fragment["fragmentId"])
            self.assertEqual([], fragment["connections"])
            self.assertEqual(1, len(fragment["nodes"]))
            self.assertEqual(
                EXPECTED_FRAGMENT_SETTINGS[recipe_id],
                fragment["nodes"][0]["settings"],
            )

        self.assertEqual([], errors)

    def test_exact_runtime_flags_ports_fingerprints_and_fragments_fail_closed(self) -> None:
        self.assertTrue(FULL_INVENTORY.is_file())
        nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        meta = catalog.load_json(INVENTORY_META)
        self.assertEqual(SOURCE_COMMIT, meta["source"]["commit"])
        self.assertEqual("0.32.0", meta["source"]["backendVersion"])
        self.assertEqual("/object_info", meta["capture"]["endpoint"])

        for article_id, spec in ARTICLE_SPECS.items():
            runtime = nodes[spec["classType"]]
            article = catalog.load_json(article_path(spec))
            self.assertEqual("comfy_extras.nodes_stable3d", runtime["python_module"])
            self.assertEqual(spec["category"], runtime["category"])
            self.assertEqual(spec["classType"], runtime["name"])
            self.assertIsNone(runtime["display_name"])
            self.assertEqual(spec["required"], runtime["input_order"]["required"])
            self.assertEqual(
                ["CONDITIONING", "CONDITIONING", "LATENT"], runtime["output"]
            )
            self.assertEqual(["positive", "negative", "latent"], runtime["output_name"])
            self.assertEqual([False, False, False], runtime["output_is_list"])
            self.assertFalse(runtime["is_input_list"])
            self.assertFalse(runtime["output_node"])
            for flag in ("deprecated", "experimental", "api_node", "dev_only"):
                self.assertFalse(runtime.get(flag, False), (article_id, flag))
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        single = nodes["StableZero123_Conditioning"]
        batched = nodes["StableZero123_Conditioning_Batched"]
        sv3d = nodes["SV3D_Conditioning"]
        for runtime in (single, batched):
            required = runtime["input"]["required"]
            self.assertEqual(["CLIP_VISION", {}], required["clip_vision"])
            self.assertEqual(["IMAGE", {}], required["init_image"])
            self.assertEqual(["VAE", {}], required["vae"])
            for name in ("width", "height"):
                self.assertEqual(
                    ["INT", {"default": 256, "min": 16, "max": 16384, "step": 8}],
                    required[name],
                )
            self.assertEqual(
                ["INT", {"default": 1, "min": 1, "max": 4096}],
                required["batch_size"],
            )
            for name in ("elevation", "azimuth"):
                self.assertEqual(
                    [
                        "FLOAT",
                        {
                            "default": 0.0,
                            "min": -180.0,
                            "max": 180.0,
                            "step": 0.1,
                            "round": False,
                        },
                    ],
                    required[name],
                )
        for name in ("elevation_batch_increment", "azimuth_batch_increment"):
            self.assertEqual(
                [
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": -180.0,
                        "max": 180.0,
                        "step": 0.1,
                        "round": False,
                        "advanced": True,
                    },
                ],
                batched["input"]["required"][name],
            )

        sv_required = sv3d["input"]["required"]
        for name in ("width", "height"):
            self.assertEqual(
                ["INT", {"default": 576, "min": 16, "max": 16384, "step": 8}],
                sv_required[name],
            )
        self.assertEqual(
            ["INT", {"default": 21, "min": 1, "max": 4096}],
            sv_required["video_frames"],
        )
        self.assertEqual(
            [
                "FLOAT",
                {
                    "default": 0.0,
                    "min": -90.0,
                    "max": 90.0,
                    "step": 0.1,
                    "round": False,
                },
            ],
            sv_required["elevation"],
        )

        for article_id, spec in ARTICLE_SPECS.items():
            recipe = catalog.load_json(recipe_path(spec["recipe"]))
            fragment = catalog.load_json(
                recipe_path(spec["recipe"]).parent / recipe["fragment"]["path"]
            )
            node = fragment["nodes"][0]
            self.assertEqual(spec["classType"], node["classType"])
            supplied = set(node["settings"])
            for external in fragment["externalInputs"]:
                self.assertEqual("condition", external["to"])
                descriptor = nodes[spec["classType"]]["input"]["required"][
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied.add(external["input"])
            self.assertEqual(set(spec["required"]), supplied, article_id)

    def test_exact_pinned_source_replacements_and_semantic_markers(self) -> None:
        self.assertTrue(SOURCE.is_dir())
        stable3d = (SOURCE / "comfy_extras" / "nodes_stable3d.py").read_text(
            encoding="utf-8"
        )
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(
            encoding="utf-8"
        )
        supported = (SOURCE / "comfy" / "supported_models.py").read_text(
            encoding="utf-8"
        )
        utils = (SOURCE / "comfy" / "utils.py").read_text(encoding="utf-8")
        clip_model = (SOURCE / "comfy" / "clip_model.py").read_text(
            encoding="utf-8"
        )
        sample = (SOURCE / "comfy" / "sample.py").read_text(encoding="utf-8")
        core_nodes = (SOURCE / "nodes.py").read_text(encoding="utf-8")

        for marker in (
            "torch.deg2rad(\n                    (90 - elevation) - (90)",
            "torch.sin(torch.deg2rad(azimuth))",
            "torch.cos(torch.deg2rad(azimuth))",
            "output = clip_vision.encode_image(init_image)",
            'common_upscale(init_image.movedim(-1,1), width, height, "bilinear", "center")',
            "encode_pixels = pixels[:,:,:,:3]",
            "latent = torch.zeros([batch_size, 4, height // 8, width // 8])",
            "elevation += elevation_batch_increment",
            "azimuth += azimuth_batch_increment",
            '"batch_index": [0] * batch_size',
            "azimuth_increment = 360 / (max(video_frames, 2) - 1)",
            'positive = [[pooled, {"concat_latent_image": t, "elevation": elevations, "azimuth": azimuths}]]',
            "latent = torch.zeros([video_frames, 4, height // 8, width // 8])",
        ):
            self.assertIn(marker, stable3d)

        for marker in (
            "class SV3D_u(SVD_img2vid):",
            "class SV3D_p(SVD_img2vid):",
            "elevation = kwargs.get(\"elevation\", 0)",
            "azimuth = kwargs.get(\"azimuth\", 0)",
            "torch.fmod(torch.flatten(90 - torch.Tensor([elevation])), 360.0)",
            "utils.resize_to_batch_size(a, noise.shape[0])",
            "class Stable_Zero123(BaseModel):",
            "if cross_attn.shape[-1] != 768:",
            "cross_attn = self.cc_projection(cross_attn)",
        ):
            self.assertIn(marker, model_base)
        for marker in (
            "class SV3D_u(SVD_img2vid):",
            "adm_in_channels\": 256",
            "class SV3D_p(SV3D_u):",
            "adm_in_channels\": 1280",
            "class Stable_Zero123(supported_models_base.BASE):",
            'clip_vision_prefix = "cond_stage_model.model.visual."',
        ):
            self.assertIn(marker, supported)
        self.assertIn('if crop == "center":', utils)
        self.assertIn("torch.nn.functional.interpolate(s, size=(height, width), mode=upscale_method)", utils)
        self.assertIn("image = image[:, :, :, :3] if image.shape[3] > 3 else image", clip_model)
        self.assertIn("unique_inds, inverse = np.unique(noise_inds, return_inverse=True)", sample)
        self.assertIn('batch_inds = latent["batch_index"] if "batch_index" in latent else None', core_nodes)

        self.assertTrue(REPLACEMENTS.is_file())
        self.assertEqual(
            REPLACEMENTS_SHA256, hashlib.sha256(REPLACEMENTS.read_bytes()).hexdigest()
        )
        replacements_text = REPLACEMENTS.read_text(encoding="utf-8")
        for spec in ARTICLE_SPECS.values():
            self.assertEqual(0, replacements_text.count(spec["classType"]))

    def test_embedded_docs_exact_case_sensitive_members_hashes_and_gaps(self) -> None:
        self.assertTrue(DOCS_WHEEL.is_file())
        self.assertEqual(
            DOCS_WHEEL_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest()
        )
        docs: dict[tuple[str, str], str] = {}
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = archive.namelist()
            for class_type, hashes in DOC_HASHES.items():
                exact = [
                    name
                    for name in names
                    if re.search(rf"/{re.escape(class_type)}/(?:en|ru)\.md$", name)
                ]
                insensitive = [
                    name
                    for name in names
                    if re.search(
                        rf"/{re.escape(class_type)}/(?:en|ru)\.md$",
                        name,
                        flags=re.IGNORECASE,
                    )
                ]
                self.assertEqual(2, len(exact), class_type)
                self.assertEqual(exact, insensitive, class_type)
                for locale, expected_hash in hashes.items():
                    member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                    payload = archive.read(member)
                    self.assertEqual(expected_hash, hashlib.sha256(payload).hexdigest())
                    docs[(class_type, locale)] = payload.decode("utf-8")

        for class_type in DOC_HASHES:
            self.assertIn("AI-generated", docs[(class_type, "en")])
            self.assertNotIn("batch_index", docs[(class_type, "en")])
        single_en = docs[("StableZero123_Conditioning", "en")]
        single_ru = docs[("StableZero123_Conditioning", "ru")]
        self.assertNotIn("multiple input images", single_en.lower())
        self.assertIn("`начальное_изображение`", single_ru)
        self.assertEqual(2, single_ru.count("| `высота` |"))

        batched_en = docs[("StableZero123_Conditioning_Batched", "en")]
        batched_ru = docs[("StableZero123_Conditioning_Batched", "ru")]
        self.assertIn("| INT | No |", batched_en)
        self.assertNotIn("fixed noise", batched_en.lower())
        self.assertIn("Вот перевод документации", batched_ru)
        self.assertIn("`инкремент_азимута_пакета`", batched_ru)

        sv3d_en = docs[("SV3D_Conditioning", "en")]
        sv3d_ru = docs[("SV3D_Conditioning", "ru")]
        self.assertNotIn("360", sv3d_en)
        self.assertNotIn("SV3D_p", sv3d_en)
        self.assertIn("| INT | Нет |", sv3d_ru)
        self.assertIn("`кадры_видео`", sv3d_ru)

    def test_exhaustive_512_json_root_and_subgraph_census_has_no_cases(self) -> None:
        self.assertTrue(WORKFLOW_WHEEL.is_file())
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        targets = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        raw_counts = Counter({target: 0 for target in targets})
        root_hits = Counter({target: 0 for target in targets})
        subgraph_hits = Counter({target: 0 for target in targets})
        root_workflows = root_nodes = subgraphs = subgraph_nodes = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            members = sorted(
                name
                for name in archive.namelist()
                if "/templates/" in name and name.endswith(".json")
            )
            self.assertEqual(512, len(members))
            for member in members:
                raw = archive.read(member).decode("utf-8")
                for target in targets:
                    raw_counts[target] += raw.count(target)
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                nodes = payload.get("nodes")
                if isinstance(nodes, list):
                    root_workflows += 1
                    root_nodes += len(nodes)
                    for node in nodes:
                        if isinstance(node, dict) and node.get("type") in targets:
                            root_hits[node["type"]] += 1
                definitions = payload.get("definitions")
                nested = (
                    definitions.get("subgraphs", [])
                    if isinstance(definitions, dict)
                    else []
                )
                for subgraph in nested:
                    if not isinstance(subgraph, dict):
                        continue
                    subgraphs += 1
                    nodes = subgraph.get("nodes", []) or []
                    subgraph_nodes += len(nodes)
                    for node in nodes:
                        if isinstance(node, dict) and node.get("type") in targets:
                            subgraph_hits[node["type"]] += 1

        self.assertEqual(
            (496, 4083, 272, 4037, 8120),
            (
                root_workflows,
                root_nodes,
                subgraphs,
                subgraph_nodes,
                root_nodes + subgraph_nodes,
            ),
        )
        for target in targets:
            self.assertEqual(0, raw_counts[target], target)
            self.assertEqual(0, root_hits[target], target)
            self.assertEqual(0, subgraph_hits[target], target)

    def test_exact_source_synthetic_probe_without_full_fragment_execution(self) -> None:
        self.assertTrue(PROBE.is_file())
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(PROBE)],
            cwd=catalog.ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertTrue(payload["helpers"]["clipPreprocessDropsAlpha"])
        self.assertTrue(payload["helpers"]["clipPreprocessFinite"])

        single = payload["stableZero123"]
        self.assertEqual([1, 37, 61, 4], single["clipSawOriginalShape"])
        self.assertTrue(single["vaeSawResizedRgb"])
        self.assertEqual([1, 1, 10], single["positiveShape"])
        self.assertEqual([1, 1, 6], single["negativeShape"])
        self.assertTrue(single["cameraEncodingMatches"])
        self.assertEqual([1, 4, 5, 7], single["positiveReferenceLatentShape"])
        self.assertTrue(single["negativeReferenceIsZero"])
        self.assertEqual([3, 4, 5, 7], single["latentShape"])
        self.assertTrue(single["latentIsZero"])
        self.assertFalse(single["hasBatchIndex"])
        self.assertTrue(single["multiImageBatchShapeMismatch"])

        batched = payload["stableZero123Batched"]
        self.assertEqual([10.0, 5.0, 0.0, -5.0], batched["elevations"])
        self.assertEqual([-45.0, -15.0, 15.0, 45.0], batched["azimuths"])
        self.assertTrue(batched["cameraEncodingMatches"])
        self.assertEqual([4, 1, 10], batched["positiveShape"])
        self.assertEqual([1, 1, 6], batched["negativeShape"])
        self.assertEqual([4, 4, 5, 7], batched["latentShape"])
        self.assertEqual([0, 0, 0, 0], batched["batchIndex"])
        self.assertTrue(batched["batchIndexMakesInitialNoiseIdentical"])
        self.assertTrue(batched["noiseWithoutBatchIndexDiffers"])
        self.assertEqual(1, batched["referenceLatentBatch"])
        self.assertTrue(batched["multiImageBatchShapeMismatch"])

        sv3d = payload["sv3d"]
        self.assertEqual([15.0] * 5, sv3d["elevations"])
        self.assertEqual([0, 90.0, 180.0, 270.0, 360.0], sv3d["azimuths"])
        self.assertTrue(sv3d["negativeUsesSameSchedule"])
        self.assertEqual([1, 4, 5, 7], sv3d["referenceLatentShape"])
        self.assertEqual([5, 4, 5, 7], sv3d["latentShape"])
        self.assertTrue(sv3d["latentIsZero"])
        self.assertEqual([-7.5], sv3d["singleFrameElevation"])
        self.assertEqual([0], sv3d["singleFrameAzimuth"])
        self.assertEqual([1, 4, 5, 7], sv3d["singleFrameLatentShape"])

        models = payload["sv3dModels"]
        self.assertTrue(models["uIgnoresCameraSchedules"])
        self.assertEqual([1, 256], models["uAdmShape"])
        self.assertTrue(models["pPolarInputMatches"])
        self.assertTrue(models["pAzimuthInputMatches"])
        self.assertEqual([5, 1280], models["pAdmShape"])


if __name__ == "__main__":
    unittest.main()
