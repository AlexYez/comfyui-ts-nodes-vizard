from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from tools import catalog


ARTICLE_SPECS = {
    "core.voxel-to-mesh": {
        "directory": "voxel-to-mesh",
        "classType": "VoxelToMesh",
        "module": "comfy_extras.nodes_hunyuan3d",
        "fingerprint": "sha256:7725ca3a26cb7d84d9ed0e70a9ac3472ca29756e71516785f226cd4d3f5ab67a",
        "recipe": "recipe.voxel-to-mesh-surface-net",
    },
    "core.voxel-to-mesh-basic": {
        "directory": "voxel-to-mesh-basic",
        "classType": "VoxelToMeshBasic",
        "module": "comfy_extras.nodes_hunyuan3d",
        "fingerprint": "sha256:7c5885f673fa1ed61a1f801623e7ce5952d6da685bba5464f6b9d23c8a3f82a0",
        "recipe": "recipe.inspect-legacy-voxel-to-mesh-basic",
    },
    "core.merge-splat": {
        "directory": "merge-splat",
        "classType": "MergeSplat",
        "module": "comfy_extras.nodes_gaussian_splat",
        "fingerprint": "sha256:8f08f65a06275869b617bb5e2ad8292ae3d06fcd467a60eb48947e29da104052",
        "recipe": "recipe.merge-two-splats",
    },
    "core.splat-to-mesh": {
        "directory": "splat-to-mesh",
        "classType": "SplatToMesh",
        "module": "comfy_extras.nodes_gaussian_splat",
        "fingerprint": "sha256:2c1e992f31475ee0155cd82dbb2b1a1e63bf8131a3949042cfc254def907602f",
        "recipe": "recipe.splat-to-colored-mesh",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.voxel-to-mesh-surface-net": "voxel-to-mesh-surface-net",
    "recipe.inspect-legacy-voxel-to-mesh-basic": "inspect-legacy-voxel-to-mesh-basic",
    "recipe.merge-two-splats": "merge-two-splats",
    "recipe.splat-to-colored-mesh": "splat-to-colored-mesh",
}

ROOT = catalog.ROOT
CONTENT = catalog.CONTENT
SOURCE = ROOT / ".comfyui-source-0.32.0"
INVENTORY = CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
REPLACEMENTS = CONTENT / "runtime" / "comfyui-0.32.0.node-replacements.json"
WORKFLOW_WHEEL = ROOT / ".upstream-cache" / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
WORKFLOW_SHA256 = "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
DOCS_WHEEL = ROOT / ".upstream-cache" / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
DOCS_SHA256 = "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
PROBE = ROOT / "tools" / "tests" / "voxel_splat_synthetic_probe.py"
TARGET_TYPES = {spec["classType"] for spec in ARTICLE_SPECS.values()}

DOC_HASHES = {
    ("VoxelToMesh", "en"): "8596decb4cb49779814b15b2f1a3cbde5556bc213461eb422c6d63f15abe8d98",
    ("VoxelToMesh", "ru"): "28352c82efce42aacb3c7b58c3618464ab666083b04cc2273965aad71a6e48c2",
    ("VoxelToMeshBasic", "en"): "d511823ae59e022bfda705cd3d59d35216a29ceac420f287cf4486f6fe02c4d2",
    ("VoxelToMeshBasic", "ru"): "17dbb399becbf2101cae7aa60c57a9c2bbf022f77bd2895e927f228586900c03",
    ("MergeSplat", "en"): "1a4c5e2e453c54cf439e26f806663f1fd0bddf74e30abcf3e2582d13fb3a5bfd",
    ("MergeSplat", "ru"): "6e9d4760628070f4d374f0ce5b5ed54c196f263d51b2d7f7334b50687a3e5e40",
    ("SplatToMesh", "en"): "45ca7a9613f3a88d68d9418acc28a7f48ff89a92619c894ddf60208d4e8e6ca9",
    ("SplatToMesh", "ru"): "a2ec6085167796052292db59fd56cd4fdb755c7c03c1228692be156037d83852",
}


def all_article_ids() -> set[str]:
    ids: set[str] = set()
    for path in (CONTENT / "articles").rglob("manifest.json"):
        value = catalog.load_json(path)
        if isinstance(value, dict) and isinstance(value.get("articleId"), str):
            ids.add(value["articleId"])
    return ids


def workflow_scopes(payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(payload.get("nodes"), list):
        yield "root", payload
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph in subgraphs:
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield "subgraph", subgraph


class VoxelSplatContentTests(unittest.TestCase):
    def test_articles_recipes_ledgers_and_editorial_contract(self) -> None:
        article_schema = catalog.load_json(CONTENT / "schemas" / "article.schema.v1.json")
        recipe_schema = catalog.load_json(CONTENT / "schemas" / "recipe.schema.v1.json")
        fragment_schema = catalog.load_json(CONTENT / "schemas" / "recipe-fragment.schema.v1.json")
        research_schema = catalog.load_json(CONTENT / "schemas" / "article-research.schema.v1.json")
        article_ids = all_article_ids()
        article_errors: list[str] = []
        cliches = re.compile(
            r"важно отметить|стоит отметить|в современном мире|революционн|"
            r"данная нода|давайте разбер|подводя итог|мощный инструмент|"
            r"не просто .{0,80}, а",
            flags=re.IGNORECASE,
        )

        for article_id, spec in ARTICLE_SPECS.items():
            path = CONTENT / "articles" / "core" / spec["directory"] / "manifest.json"
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, article_schema), article_id)
            catalog.validate_article(path, article, article_errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertFalse(article["experimental"])
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])
            self.assertIn(spec["recipe"], [asset["id"] for asset in article["assets"]])

            relations = article["relations"]
            targets = list(relations["related"]) + list(relations["alternatives"])
            if relations["replacedBy"] is not None:
                targets.append(relations["replacedBy"])
            self.assertTrue(set(targets).issubset(article_ids), (article_id, targets))

            body = (path.parent / article["body"]).read_text(encoding="utf-8")
            self.assertEqual(10, len(re.findall(r"^## .+$", body, flags=re.MULTILINE)), article_id)
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(body, cliches)

            ledger = catalog.load_json(CONTENT / "research" / "reviews" / f"{article_id}.json")
            self.assertEqual([], catalog.json_schema_errors(ledger, research_schema), article_id)
            self.assertEqual("fact_checked", ledger["state"])
            self.assertEqual("automated_assisted", ledger["reviewMode"])
            self.assertFalse(ledger["checks"]["exampleExecuted"])
            self.assertTrue(ledger["checks"]["factsRecheckedAfterEditing"])
            self.assertTrue(any("Редактор пока" in gap for gap in ledger["knownGaps"]))

        self.assertEqual([], article_errors)

        recipe_errors: list[str] = []
        for recipe_id, directory in RECIPE_DIRECTORIES.items():
            path = CONTENT / "recipes" / directory / "recipe.json"
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, recipe_schema), recipe_id)
            catalog.validate_recipe(path, recipe, article_ids, recipe_errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertEqual("in_review", recipe["editorial"]["state"])
            self.assertNotIn("workflow", recipe)
            body = (path.parent / recipe["body"]).read_text(encoding="utf-8")
            self.assertIn("Редактор пока не проверил материал вручную.", body)
            self.assertNotRegex(body, cliches)

            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, fragment_schema), recipe_id)
            catalog.validate_fragment(fragment_path, fragment, recipe_errors)

        self.assertEqual([], recipe_errors)

    def test_runtime_contracts_fingerprints_fragments_and_replacements(self) -> None:
        inventory = catalog.load_json(INVENTORY)
        for spec in ARTICLE_SPECS.values():
            definition = inventory[spec["classType"]]
            self.assertEqual(spec["module"], definition["python_module"])
            self.assertEqual(spec["fingerprint"], catalog.schema_fingerprint(spec["classType"], definition))
            self.assertFalse(definition["output_node"])
            for flag in ("experimental", "dev_only", "api_node", "is_input_list"):
                self.assertFalse(definition[flag])

        voxel = inventory["VoxelToMesh"]
        self.assertEqual("3d", voxel["category"])
        self.assertEqual(["voxel", "algorithm", "threshold"], voxel["input_order"]["required"])
        self.assertEqual(["surface net", "basic"], voxel["input"]["required"]["algorithm"][1]["options"])
        self.assertEqual(
            {"default": 0.6, "min": -1.0, "max": 1.0, "step": 0.01},
            voxel["input"]["required"]["threshold"][1],
        )
        self.assertEqual((["MESH"], ["MESH"]), (voxel["output"], voxel["output_name"]))

        basic = inventory["VoxelToMeshBasic"]
        self.assertTrue(basic["deprecated"])
        self.assertEqual(["voxel", "threshold"], basic["input_order"]["required"])

        merge = inventory["MergeSplat"]
        self.assertEqual("3d/splat", merge["category"])
        autogrow = merge["input"]["required"]["splats"]
        self.assertEqual("COMFY_AUTOGROW_V3", autogrow[0])
        template = autogrow[1]["template"]
        self.assertEqual(("splat", 2, 32), (template["prefix"], template["min"], template["max"]))
        self.assertEqual("SPLAT", template["input"]["required"]["splat"][0])
        self.assertEqual((["SPLAT"], ["splat"]), (merge["output"], merge["output_name"]))

        splat_mesh = inventory["SplatToMesh"]
        self.assertEqual(
            ["splat", "resolution", "kernel", "smooth", "level", "min_component", "min_opacity", "color_sharpen"],
            splat_mesh["input_order"]["required"],
        )
        expected_options = {
            "resolution": {"default": 384, "min": 64, "max": 768, "step": 16},
            "kernel": {"default": 5, "min": 1, "max": 8},
            "smooth": {"advanced": True, "default": 0, "min": 0, "max": 60},
            "level": {"default": 0.4, "min": 0.0, "max": 2.0, "step": 0.01},
            "min_component": {"advanced": True, "default": 500, "min": 0, "max": 100000, "step": 50},
            "min_opacity": {"advanced": True, "default": 0.02, "min": 0.0, "max": 1.0, "step": 0.01},
            "color_sharpen": {"default": 2.0, "min": 1.0, "max": 8.0, "step": 0.5},
        }
        for name, options in expected_options.items():
            actual = splat_mesh["input"]["required"][name][1]
            for key, value in options.items():
                self.assertEqual(value, actual[key], (name, key))
        self.assertEqual((["MESH"], ["mesh"]), (splat_mesh["output"], splat_mesh["output_name"]))

        fragments = {
            directory: catalog.load_json(CONTENT / "recipes" / directory / "fragment.json")
            for directory in RECIPE_DIRECTORIES.values()
        }
        self.assertEqual(
            [("VoxelToMesh", {"algorithm": "surface net", "threshold": 0.6}), ("SaveGLB", {"filename_prefix": "3d/ComfyUI_VoxelSurfaceNet"})],
            [(node["classType"], node["settings"]) for node in fragments["voxel-to-mesh-surface-net"]["nodes"]],
        )
        self.assertEqual("VoxelToMeshBasic", fragments["inspect-legacy-voxel-to-mesh-basic"]["nodes"][0]["classType"])
        merge_fragment = fragments["merge-two-splats"]
        self.assertEqual(
            ["splats.splat0", "splats.splat1"],
            [external["input"] for external in merge_fragment["externalInputs"]],
        )
        self.assertEqual(
            ["MergeSplat", "GetSplatCount", "PreviewAny"],
            [node["classType"] for node in merge_fragment["nodes"]],
        )
        self.assertEqual(
            {"from": "count", "output": "count", "to": "preview-count", "input": "source"},
            merge_fragment["connections"][-1],
        )
        self.assertTrue(inventory["PreviewAny"]["output_node"])
        splat_fragment = fragments["splat-to-colored-mesh"]
        self.assertEqual(
            {"resolution": 384, "kernel": 5, "smooth": 0, "level": 0.4, "min_component": 500, "min_opacity": 0.02, "color_sharpen": 2.0},
            splat_fragment["nodes"][0]["settings"],
        )
        self.assertTrue(all(node["classType"] in inventory for fragment in fragments.values() for node in fragment["nodes"]))

        replacements = catalog.load_json(REPLACEMENTS)
        serialized = json.dumps(replacements, ensure_ascii=False)
        for class_type in TARGET_TYPES:
            self.assertNotIn(class_type, replacements)
            self.assertNotIn(f'"new_node_id": "{class_type}"', serialized)

    @unittest.skipUnless(SOURCE.exists(), "pinned source checkout is absent")
    def test_pinned_source_hashes_registration_and_edge_contracts(self) -> None:
        expected_hashes = {
            SOURCE / "comfy_extras" / "nodes_hunyuan3d.py": "818c71e7f1366f2072861b7d33ab91ce732cd9a0bbf7c5a92bcc2ebded0d04a7",
            SOURCE / "comfy_extras" / "nodes_gaussian_splat.py": "d899cae4db30838ec5f8b80331236a51c0b407e6e85a49681098d49d4c9d83ce",
            SOURCE / "comfy_extras" / "nodes_save_3d.py": "02bc326fd286fcc9c5858b2a26abdf7a0c1003d83957274e0208f894b761c62b",
            SOURCE / "comfy_extras" / "nodes_replacements.py": "f7e70ac130098e243f3c36987941e70244b320a7c5e3d5042434509be8974849",
            SOURCE / "comfy_api" / "latest" / "_util" / "geometry_types.py": "eac581734bdec2d99f95f5752ce0d65e1160ee18e86bee2b62a4182945999122",
        }
        for path, expected in expected_hashes.items():
            self.assertEqual(expected, hashlib.sha256(path.read_bytes()).hexdigest(), path)

        hunyuan = (SOURCE / "comfy_extras" / "nodes_hunyuan3d.py").read_text(encoding="utf-8")
        for marker in (
            "binary = (voxels > threshold).float()",
            "vertices = torch.zeros((1, 3))",
            "faces = torch.zeros((1, 3))",
            "vert_progress_mod = round(len(cell_vertices)/50)",
            'node_id="VoxelToMeshBasic"',
            "is_deprecated=True, # This node is superseded by the Voxel To Mesh node",
            'IO.Combo.Input("algorithm", options=["surface net", "basic"])',
            'elif algorithm == "surface net":',
            "return IO.NodeOutput(pack_variable_mesh_batch(vertices, faces))",
        ):
            self.assertIn(marker, hunyuan)

        splat = (SOURCE / "comfy_extras" / "nodes_gaussian_splat.py").read_text(encoding="utf-8")
        for marker in (
            "if g.positions.shape[0] != b:",
            "sh = torch.cat([sh, sh.new_zeros",
            "if len(set(lengths)) > 1:",
            "prefix=\"splat\", min=2, max=32",
            "kreq = torch.ceil(3.0 * scale.amax(-1) / voxel).long().clamp(1, int(kernel))",
            "keep = opacity >= min_opacity",
            "_otsu_level(occ.cpu().numpy()) * level_bias",
            "col = np.where(col <= 0.04045",
            "verts = np.ascontiguousarray(verts * np.array([1.0, -1.0, -1.0]",
            "unlit=True",
        ):
            self.assertIn(marker, splat)

    @unittest.skipUnless(DOCS_WHEEL.exists(), "pinned embedded docs wheel is absent")
    def test_pinned_embedded_docs_hashes_and_material_gaps(self) -> None:
        self.assertEqual(DOCS_SHA256, hashlib.sha256(DOCS_WHEEL.read_bytes()).hexdigest())
        locales = {"ar", "en", "es", "fa", "fr", "ja", "ko", "pt-BR", "ru", "tr", "zh", "zh-TW"}
        with zipfile.ZipFile(DOCS_WHEEL) as archive:
            names = set(archive.namelist())
            for class_type in TARGET_TYPES:
                actual_locales = {
                    Path(name).stem
                    for name in names
                    if name.startswith(f"comfyui_embedded_docs/docs/{class_type}/") and name.endswith(".md")
                }
                self.assertEqual(locales, actual_locales, class_type)
            for (class_type, locale), digest in DOC_HASHES.items():
                member = f"comfyui_embedded_docs/docs/{class_type}/{locale}.md"
                self.assertEqual(digest, hashlib.sha256(archive.read(member)).hexdigest())

            voxel_ru = archive.read("comfyui_embedded_docs/docs/VoxelToMesh/ru.md").decode("utf-8")
            self.assertIn("VoxelToMeshBasic", voxel_ru)
            self.assertNotIn("`algorithm`", voxel_ru)
            basic_ru = archive.read("comfyui_embedded_docs/docs/VoxelToMeshBasic/ru.md").decode("utf-8")
            self.assertIn("Вот перевод документации", basic_ru)
            merge_en = archive.read("comfyui_embedded_docs/docs/MergeSplat/en.md").decode("utf-8")
            self.assertIn("At least 1 splat required", merge_en)
            self.assertIn("minimum of 2", merge_en)
            splat_en = archive.read("comfyui_embedded_docs/docs/SplatToMesh/en.md").decode("utf-8")
            self.assertIn("large ones aren't truncated", splat_en)

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "pinned workflow wheel is absent")
    def test_workflow_wheel_integrity_full_census_and_exact_topology(self) -> None:
        self.assertEqual(WORKFLOW_SHA256, hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest())
        counts: Counter[str] = Counter()
        scopes: Counter[tuple[str, str]] = Counter()
        modes: dict[str, Counter[int]] = defaultdict(Counter)
        occurrences: list[tuple[str, str, int, int, tuple[Any, ...], str | None, str | None]] = []
        json_count = root_count = subgraph_count = node_count = 0

        with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
            self.assertIsNone(archive.testzip())
            record_name = next(name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
            verified = unhashed = 0
            for name, digest_spec, size in csv.reader(archive.read(record_name).decode("utf-8").splitlines()):
                if not digest_spec:
                    unhashed += 1
                    continue
                algorithm, expected = digest_spec.split("=", 1)
                data = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).decode("ascii").rstrip("=")
                self.assertEqual(expected, actual)
                self.assertEqual(int(size), len(data))
                verified += 1
            self.assertEqual((516, 1), (verified, unhashed))

            for member in sorted(archive.namelist()):
                if not member.endswith(".json"):
                    continue
                json_count += 1
                payload = json.loads(archive.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("nodes"), list):
                    root_count += 1
                for scope, graph in workflow_scopes(payload):
                    if scope == "subgraph":
                        subgraph_count += 1
                    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
                    links = [link for link in graph.get("links", []) if isinstance(link, list) and len(link) >= 6]
                    by_id = {str(node.get("id")): node for node in nodes}
                    node_count += len(nodes)
                    for node in nodes:
                        class_type = node.get("type")
                        if class_type not in TARGET_TYPES:
                            continue
                        counts[class_type] += 1
                        scopes[(class_type, scope)] += 1
                        modes[class_type][node.get("mode", 0)] += 1
                        incoming = [link for link in links if str(link[3]) == str(node.get("id"))]
                        outgoing = [link for link in links if str(link[1]) == str(node.get("id"))]
                        upstream = by_id.get(str(incoming[0][1]), {}).get("type") if incoming else None
                        downstream = by_id.get(str(outgoing[0][3]), {}).get("type") if outgoing else None
                        occurrences.append(
                            (
                                Path(member).name,
                                class_type,
                                node["id"],
                                node.get("mode", 0),
                                tuple(node.get("widgets_values", [])),
                                upstream,
                                downstream,
                            )
                        )

        self.assertEqual((512, 496, 272, 8120), (json_count, root_count, subgraph_count, node_count))
        self.assertEqual(Counter({"VoxelToMesh": 4, "SplatToMesh": 1}), counts)
        self.assertEqual(5, sum(scopes[(class_type, "root")] for class_type in TARGET_TYPES))
        self.assertEqual(0, sum(scopes[(class_type, "subgraph")] for class_type in TARGET_TYPES))
        self.assertEqual(Counter({0: 4}), modes["VoxelToMesh"])
        self.assertEqual(Counter({4: 1}), modes["SplatToMesh"])
        self.assertEqual(
            {
                ("3d_hunyuan3d-v2.1.json", "VoxelToMesh", 9, 0, ("surface net", 0.6), "VAEDecodeHunyuan3D", "SaveGLB"),
                ("3d_hunyuan3d_image_to_model.json", "VoxelToMesh", 81, 0, ("surface net", 0.6), "VAEDecodeHunyuan3D", "SaveGLB"),
                ("3d_hunyuan3d_multiview_to_model.json", "VoxelToMesh", 82, 0, ("surface net", 0.6), "VAEDecodeHunyuan3D", "SaveGLB"),
                ("3d_hunyuan3d_multiview_to_model_turbo.json", "VoxelToMesh", 83, 0, ("surface net", 0.6), "VAEDecodeHunyuan3D", "SaveGLB"),
                ("3d_triposplat_image_to_gaussian_splat.json", "SplatToMesh", 76, 4, (384, 5, 0, 0.6, 500, 0.02, 2), "b64333d5-4e6f-4e99-9506-2ec4f63259fe", "SaveGLB"),
            },
            set(occurrences),
        )

    @unittest.skipUnless(SOURCE.exists() and PROBE.exists(), "pinned source or probe is absent")
    def test_safe_exact_source_model_free_probe(self) -> None:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(PROBE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        voxel = payload["voxel"]
        self.assertEqual(([864, 3], [432, 3], "torch.int64"), (voxel["basic"]["vertices"], voxel["basic"]["faces"], voxel["basic"]["faceDtype"]))
        self.assertEqual(([218, 3], [432, 3], "torch.int64"), (voxel["surfaceNet"]["vertices"], voxel["surfaceNet"]["faces"], voxel["surfaceNet"]["faceDtype"]))
        self.assertEqual([-0.5, 0.5], voxel["basic"]["bounds"])
        self.assertAlmostEqual(-0.4, voxel["surfaceNet"]["bounds"][0], places=6)
        self.assertAlmostEqual(0.5666666667, voxel["surfaceNet"]["bounds"][1], places=6)
        self.assertEqual(([1, 3], [1, 3], "torch.float32"), (voxel["strictThreshold"]["basicSentinelVertices"], voxel["strictThreshold"]["basicSentinelFaces"], voxel["strictThreshold"]["basicSentinelFaceDtype"]))
        self.assertEqual([-1.0, -1.0, -1.0], voxel["strictThreshold"]["basicSentinelVertex"])
        self.assertEqual([0.0, 0.0, 0.0], voxel["strictThreshold"]["basicSentinelFace"])
        self.assertEqual(([0, 3], [0, 3]), (voxel["strictThreshold"]["surfaceVertices"], voxel["strictThreshold"]["surfaceFaces"]))
        self.assertEqual("ZeroDivisionError", voxel["tinySurfaceNetError"])

        merge = payload["merge"]
        self.assertEqual(([2, 3, 3], [3, 2], [2, 3, 4, 3]), (merge["shape"], merge["counts"], merge["shShape"]))
        self.assertEqual([1.0, 2.0, 10.0], merge["firstBatchX"])
        self.assertEqual([3.0, 20.0, 0.0], merge["secondBatchX"])
        self.assertTrue(merge["firstInputShPaddingIsZero"])
        self.assertEqual("MergeSplat: batch size mismatch (2 vs 1).", merge["mismatchError"])

        density = payload["splatDensity"]
        self.assertEqual([25, 20, 20], density["gridShape"])
        self.assertEqual((54, 637), (density["kernelOneNonzero"], density["kernelThreeNonzero"]))
        self.assertTrue(density["densityIndependentOfColorSharpen"])
        self.assertTrue(density["colorNormalizerDiffers"])
        self.assertAlmostEqual(0.4176652431488037, density["autoLevel"], places=6)
        self.assertAlmostEqual(0.16706609725952148, density["biasedLevel"], places=6)
        self.assertEqual((456, 908), (density["meshVertices"], density["meshFaces"]))


if __name__ == "__main__":
    unittest.main()
