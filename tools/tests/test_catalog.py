from __future__ import annotations

import copy
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import catalog


SAMPLE_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.sample.json"
FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
FULL_INVENTORY_METADATA = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.meta.json"
FULL_INVENTORY_REPORT = catalog.CONTENT / "runtime" / "comfyui-0.32.0.inventory-report.json"
FRONTEND_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-frontend-1.48.7.frontend-inventory.sample.json"


class FingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = catalog.object_info_nodes(catalog.load_json(SAMPLE_INVENTORY))

    def test_fingerprint_is_prefixed_sha256(self) -> None:
        value = catalog.schema_fingerprint("KSampler", self.nodes["KSampler"])
        self.assertRegex(value, r"^sha256:[a-f0-9]{64}$")

    def test_dynamic_combo_choices_do_not_change_hash(self) -> None:
        before = copy.deepcopy(self.nodes["CheckpointLoaderSimple"])
        after = copy.deepcopy(before)
        after["input"]["required"]["ckpt_name"][0] = [
            "different-model.safetensors",
            "nested/another-model.safetensors",
        ]
        self.assertEqual(
            catalog.schema_fingerprint("CheckpointLoaderSimple", before),
            catalog.schema_fingerprint("CheckpointLoaderSimple", after),
        )

    def test_dynamic_sampler_choices_do_not_change_hash(self) -> None:
        before = copy.deepcopy(self.nodes["KSampler"])
        after = copy.deepcopy(before)
        after["input"]["required"]["sampler_name"][0].append("future_sampler")
        after["input"]["required"]["scheduler"][0] = ["brand_new_scheduler"]
        self.assertEqual(
            catalog.schema_fingerprint("KSampler", before),
            catalog.schema_fingerprint("KSampler", after),
        )

    def test_scalar_constraint_changes_hash(self) -> None:
        before = copy.deepcopy(self.nodes["KSampler"])
        after = copy.deepcopy(before)
        after["input"]["required"]["steps"][1]["max"] = 20000
        self.assertNotEqual(
            catalog.schema_fingerprint("KSampler", before),
            catalog.schema_fingerprint("KSampler", after),
        )

    def test_output_tooltip_changes_hash(self) -> None:
        before = copy.deepcopy(self.nodes["KSampler"])
        after = copy.deepcopy(before)
        after["output_tooltips"][0] = "Changed structural documentation."
        self.assertNotEqual(
            catalog.schema_fingerprint("KSampler", before),
            catalog.schema_fingerprint("KSampler", after),
        )


class CatalogTests(unittest.TestCase):
    def test_source_catalog_is_valid(self) -> None:
        self.assertEqual([], catalog.validate_catalog())

    def test_catalog_manifest_is_the_sorted_complete_source_inventory(self) -> None:
        source = catalog.load_json(catalog.CATALOG_MANIFEST)
        self.assertEqual(catalog.discovered_catalog_members(), {
            key: source[key] for key in ("articles", "recipes", "workflows")
        })
        drifted = copy.deepcopy(source)
        drifted["articles"] = list(reversed(drifted["articles"]))
        self.assertTrue(any("deterministic sorted order" in error for error in catalog.catalog_membership_errors(drifted)))
        drifted = copy.deepcopy(source)
        omitted = drifted["articles"].pop()
        self.assertTrue(any(omitted in error and "omits" in error for error in catalog.catalog_membership_errors(drifted)))

    def test_sync_manifest_check_is_read_only(self) -> None:
        before = catalog.CATALOG_MANIFEST.read_bytes()
        result = subprocess.run(
            [sys.executable, "tools/catalog.py", "sync-manifest", "--check"],
            cwd=catalog.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, catalog.CATALOG_MANIFEST.read_bytes())

    def test_approved_article_cannot_bypass_human_research_record(self) -> None:
        _, articles, _, _ = catalog.load_source_catalog()
        copied = [(path, copy.deepcopy(article)) for path, article in articles]
        copied[0][1]["editorial"]["state"] = "approved"
        errors: list[str] = []
        catalog.validate_article_research_records(copied, errors)
        self.assertTrue(any("needs human_approved research" in error for error in errors))
        self.assertTrue(any("incomplete research checks" in error for error in errors))
        self.assertTrue(any("known research gaps" in error for error in errors))

    def test_compiled_shape_matches_frontend_contract(self) -> None:
        compiled, search = catalog.compile_catalog()
        self.assertEqual("1.0", compiled["schemaVersion"])
        source_catalog = catalog.load_json(catalog.CATALOG_MANIFEST)
        self.assertEqual(len(source_catalog["articles"]), len(compiled["articles"]))
        article = next(item for item in compiled["articles"] if item["manifest"]["articleId"] == "core.ksampler")
        self.assertEqual("KSampler", article["manifest"]["runtimeIdentity"]["classType"])
        self.assertEqual("KSampler", article["manifest"]["node"]["nodeId"])
        self.assertEqual("backend", article["manifest"]["node"]["kind"])
        self.assertRegex(article["manifest"]["compatibility"]["schemaFingerprint"], r"^sha256:[a-f0-9]{64}$")
        self.assertIn("recipeData", article)
        self.assertIn("workflowData", article)
        self.assertEqual(len(compiled["articles"]), len(search["documents"]))
        self.assertEqual([], catalog.validate_compiled_catalog_instance(compiled))

    def test_fragment_only_recipe_is_valid_and_compiles_without_workflow(self) -> None:
        recipe_path = catalog.CONTENT / "recipes" / "inpaint-latent" / "recipe.json"
        source_recipe = catalog.load_json(recipe_path)
        self.assertNotIn("workflow", source_recipe)

        errors: list[str] = []
        catalog.validate_recipe(
            recipe_path,
            source_recipe,
            set(source_recipe["articleIds"]),
            errors,
        )
        self.assertEqual([], errors)
        compiled_recipe = catalog.compile_recipe(recipe_path, source_recipe)
        self.assertNotIn("workflow", compiled_recipe)
        self.assertNotIn("workflowData", compiled_recipe)

        compiled, _ = catalog.compile_catalog()
        article = next(
            item for item in compiled["articles"]
            if item["manifest"]["articleId"] == "core.vae-encode-for-inpaint"
        )
        recipe = next(
            item for item in article["recipeData"]
            if item["recipeId"] == "recipe.inpaint-latent"
        )
        self.assertIn("fragmentData", recipe)
        self.assertNotIn("workflow", recipe)
        self.assertNotIn("workflowData", recipe)
        self.assertNotIn("workflowData", article)
        self.assertEqual([], catalog.validate_compiled_catalog_instance(compiled))

    def test_explicit_null_workflow_is_accepted_by_source_and_compiled_contracts(self) -> None:
        recipe_path = catalog.CONTENT / "recipes" / "inpaint-latent" / "recipe.json"
        source_recipe = copy.deepcopy(catalog.load_json(recipe_path))
        source_recipe["workflow"] = None
        errors: list[str] = []
        catalog.validate_recipe(
            recipe_path,
            source_recipe,
            set(source_recipe["articleIds"]),
            errors,
        )
        self.assertEqual([], errors)
        compiled_recipe = catalog.compile_recipe(recipe_path, source_recipe)
        self.assertIsNone(compiled_recipe["workflow"])
        self.assertNotIn("workflowData", compiled_recipe)

        compiled, _ = catalog.compile_catalog()
        article = next(
            item for item in compiled["articles"]
            if item["manifest"]["articleId"] == "core.vae-encode-for-inpaint"
        )
        recipe = next(
            item for item in article["recipeData"]
            if item["recipeId"] == "recipe.inpaint-latent"
        )
        recipe["workflow"] = None
        recipe["workflowData"] = None
        self.assertEqual([], catalog.validate_compiled_catalog_instance(compiled))

    def test_compiled_schema_rejects_manifest_drift(self) -> None:
        compiled, _ = catalog.compile_catalog()
        drifted = copy.deepcopy(compiled)
        manifest = drifted["articles"][0]["manifest"]
        manifest["unexpectedResolverHint"] = "must not silently ship"
        del manifest["node"]["nodeId"]
        errors = catalog.validate_compiled_catalog_instance(drifted)
        self.assertTrue(any("additional property 'unexpectedResolverHint'" in error for error in errors))
        self.assertTrue(any("missing required property 'nodeId'" in error for error in errors))

    def test_validate_compiled_cli_is_read_only_and_rejects_drift(self) -> None:
        valid = subprocess.run(
            [sys.executable, "tools/catalog.py", "validate-compiled", str(catalog.GENERATED / "catalog.json")],
            cwd=catalog.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, valid.returncode, valid.stderr)
        valid_stdin = subprocess.run(
            [sys.executable, "tools/catalog.py", "validate-compiled", "-"],
            cwd=catalog.ROOT,
            input=(catalog.GENERATED / "catalog.json").read_bytes(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, valid_stdin.returncode, valid_stdin.stderr.decode("utf-8", errors="replace"))
        with tempfile.TemporaryDirectory() as directory:
            drifted_path = Path(directory) / "catalog.json"
            drifted = json.loads((catalog.GENERATED / "catalog.json").read_text(encoding="utf-8"))
            drifted["articles"][0]["manifest"]["uncontracted"] = True
            drifted_path.write_text(json.dumps(drifted), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, "tools/catalog.py", "validate-compiled", str(drifted_path)],
                cwd=catalog.ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, rejected.returncode)
            self.assertIn("uncontracted", rejected.stderr)

    def test_basic_workflow_keeps_declared_node_types(self) -> None:
        workflow = catalog.load_json(catalog.CONTENT / "workflows" / "basic-text-to-image.workflow.json")
        node_types = {node["type"] for node in workflow["nodes"]}
        self.assertTrue({"CheckpointLoaderSimple", "KSampler", "SaveImage"}.issubset(node_types))

    def test_generic_workflow_validator_does_not_require_txt2img_nodes(self) -> None:
        workflow = {
            "version": 0.4,
            "nodes": [
                {"id": 1, "type": "UtilityNode"},
                {"id": 2, "type": "OutputUtility"},
            ],
            "links": [[1, 1, 0, 2, 0, "STRING"]],
        }
        errors = []
        catalog.validate_workflow(catalog.CONTENT / "workflows" / "generic-test.workflow.json", workflow, errors)
        self.assertEqual([], errors)

    def test_workflow_asset_compiles_without_recipe_asset(self) -> None:
        manifest_path = catalog.CONTENT / "articles" / "core" / "ksampler" / "manifest.json"
        article = catalog.load_json(manifest_path)
        article["assets"] = [asset for asset in article["assets"] if asset["type"] == "workflow"]
        workflows = catalog.compile_workflow_assets(manifest_path, article)
        self.assertEqual(1, len(workflows))
        self.assertTrue(any(node["type"] == "KSampler" for node in workflows[0]["nodes"]))

    def test_alias_collision_with_canonical_class_type_is_rejected(self) -> None:
        errors = []
        catalog.validate_runtime_namespace(
            {"KSampler": "core.ksampler"},
            {"KSampler": "custom.legacy-sampler"},
            errors,
        )
        self.assertEqual(1, len(errors))
        self.assertIn("collides with canonical classType", errors[0])

    def test_frontend_only_nodes_are_not_backend_coverage_debt(self) -> None:
        nodes = catalog.object_info_nodes(catalog.load_json(SAMPLE_INVENTORY))
        coverage = catalog.catalog_coverage(nodes)
        self.assertEqual([], coverage["missingArticles"])
        self.assertEqual(
            [
                "frontend.markdown-note",
                "frontend.note",
                "frontend.primitive-node",
                "frontend.reroute",
            ],
            coverage["frontendArticleIds"],
        )

    def test_api_nodes_are_not_local_catalog_coverage_debt(self) -> None:
        nodes = {
            "LocalNode": {"name": "LocalNode", "python_module": "nodes", "api_node": False},
            "RemoteApiNode": {"name": "RemoteApiNode", "python_module": "comfy_api_nodes.remote", "api_node": True},
            "RemoteApiHelper": {"name": "RemoteApiHelper", "python_module": "comfy_api_nodes.remote", "api_node": False},
        }
        scoped = catalog.local_generation_nodes(nodes)
        self.assertEqual(["LocalNode"], sorted(scoped))
        coverage = catalog.catalog_coverage(nodes)
        self.assertEqual(1, coverage["runtimeNodeCount"])
        self.assertNotIn("RemoteApiNode", coverage["missingArticles"])
        self.assertNotIn("RemoteApiHelper", coverage["missingArticles"])

    def test_generated_build_is_current(self) -> None:
        catalog.build(catalog.GENERATED, check=True)

    def test_bundle_is_reproducible_and_contains_only_runtime_data(self) -> None:
        compiled, search = catalog.compile_catalog()
        files = {
            "catalog.json": catalog.generated_text(compiled).encode("utf-8"),
            "search-index.json": catalog.generated_text(search).encode("utf-8"),
        }
        first = catalog.deterministic_bundle(files)
        second = catalog.deterministic_bundle(files)
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.zip"
            path.write_bytes(first)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(["catalog.json", "search-index.json"], archive.namelist())


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.before = catalog.object_info_nodes(catalog.load_json(SAMPLE_INVENTORY))

    def test_diff_reports_add_remove_and_structural_change(self) -> None:
        after = copy.deepcopy(self.before)
        after["NewNode"] = {
            "name": "NewNode",
            "python_module": "example",
            "input": {},
            "output": [],
        }
        del after["SaveImage"]
        after["KSampler"]["input"]["required"]["steps"][1]["max"] = 20000
        result = catalog.diff_inventories(self.before, after, {"SaveImage": "SaveImageV2"})
        self.assertEqual(["NewNode"], result["added"])
        self.assertEqual([{"nodeId": "SaveImage", "replacedBy": "SaveImageV2"}], result["removed"])
        self.assertEqual("KSampler", result["changed"][0]["nodeId"])

    def test_inventory_report_writes_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = catalog.inventory_report(SAMPLE_INVENTORY, None, None, SAMPLE_INVENTORY)
            catalog.write_json(output / "inventory-report.json", report)
            (output / "inventory-report.md").write_text(catalog.report_markdown(report), encoding="utf-8")
            self.assertTrue((output / "inventory-report.json").exists())
            self.assertIn("# Nodes Wizard inventory report", (output / "inventory-report.md").read_text(encoding="utf-8"))

    def test_replacements_accept_current_and_wrapped_shapes(self) -> None:
        payload = {
            "replacements": [
                {"old_node_id": "OldOne", "new_node_id": "NewOne"},
                {"oldNodeId": "OldTwo", "newNodeId": "NewTwo"},
            ]
        }
        self.assertEqual({"OldOne": "NewOne", "OldTwo": "NewTwo"}, catalog.extract_replacements(payload))


class PinnedBackendInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_bytes = FULL_INVENTORY.read_bytes()
        cls.snapshot = json.loads(cls.raw_bytes.decode("utf-8"))
        cls.metadata = catalog.load_json(FULL_INVENTORY_METADATA)
        cls.report = catalog.load_json(FULL_INVENTORY_REPORT)

    def test_exact_official_source_and_snapshot_integrity(self) -> None:
        self.assertEqual("0.32.0", self.metadata["source"]["backendVersion"])
        self.assertEqual("v0.32.0", self.metadata["source"]["tag"])
        self.assertEqual("c2bcbecd82ec5ae66594340b395c24ef0217b238", self.metadata["source"]["commit"])
        self.assertEqual(len(self.raw_bytes), self.metadata["snapshot"]["size"])
        self.assertEqual(hashlib.sha256(self.raw_bytes).hexdigest(), self.metadata["snapshot"]["sha256"])
        self.assertEqual(len(self.snapshot), self.metadata["capture"]["endpointNodeCount"])
        self.assertEqual(
            self.metadata["capture"]["nodeClassMappingCount"],
            self.metadata["capture"]["endpointNodeCount"],
        )

    def test_expected_user_server_counts_and_flags(self) -> None:
        self.assertEqual(840, self.report["counts"]["rawNodeCount"])
        self.assertEqual(840, self.report["counts"]["userServerNodeCount"])
        self.assertEqual(0, self.report["counts"]["devOnlyNodeCount"])
        self.assertEqual(0, self.report["counts"]["testNodeCount"])
        self.assertEqual(
            {"api": 220, "experimental": 137, "deprecated": 31, "devOnly": 0},
            self.report["userServerFlags"],
        )

    def test_derived_report_is_deterministic_and_current(self) -> None:
        first = catalog.backend_inventory_report(self.snapshot, self.metadata)
        second = catalog.backend_inventory_report(copy.deepcopy(self.snapshot), copy.deepcopy(self.metadata))
        self.assertEqual(first, second)
        self.assertEqual(self.report, first)
        markdown = FULL_INVENTORY_REPORT.with_suffix(".md").read_text(encoding="utf-8")
        self.assertEqual(markdown, catalog.backend_inventory_markdown(first))

    def test_exclusions_are_derived_without_mutating_raw_snapshot(self) -> None:
        synthetic = {
            "Visible": {"python_module": "nodes"},
            "DeveloperOnly": {"python_module": "nodes", "dev_only": True},
            "TestFixtureNode": {"python_module": "tests.nodes"},
        }
        before = copy.deepcopy(synthetic)
        report = catalog.backend_inventory_report(synthetic, self.metadata)
        self.assertEqual(before, synthetic)
        self.assertEqual(3, report["counts"]["rawNodeCount"])
        self.assertEqual(1, report["counts"]["userServerNodeCount"])
        self.assertEqual(["DeveloperOnly", "TestFixtureNode"], report["excluded"]["unionNodeIds"])

    def test_embedded_docs_provenance_is_pinned_but_not_vendored(self) -> None:
        docs = self.metadata["embeddedDocs"]
        self.assertEqual("comfyui-embedded-docs", docs["package"])
        self.assertEqual("0.5.9", docs["version"])
        self.assertEqual("comfyui_embedded_docs/docs/{classType}/en.md", docs["documentPattern"])
        self.assertFalse(docs["vendored"])

    def test_compiler_and_release_manifest_use_full_inventory(self) -> None:
        compiled, _ = catalog.compile_catalog()
        save_image = next(
            article for article in compiled["articles"]
            if article["manifest"]["runtimeIdentity"]["classType"] == "SaveImage"
        )
        expected = catalog.schema_fingerprint("SaveImage", self.snapshot["SaveImage"])
        self.assertEqual(expected, save_image["manifest"]["compatibility"]["schemaFingerprint"])
        update_manifest = catalog.load_json(catalog.CONTENT / "update-manifest.json")
        self.assertEqual("runtime/comfyui-0.32.0.object-info.json", update_manifest["inventory"]["source"])


class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        source_catalog, articles, recipes, workflows = catalog.load_source_catalog()
        self.source_catalog = copy.deepcopy(source_catalog)
        self.articles = [(path, copy.deepcopy(article)) for path, article in articles]
        self.recipes = [(path, copy.deepcopy(recipe)) for path, recipe in recipes]
        self.workflows = [(path, copy.deepcopy(workflow)) for path, workflow in workflows]
        self.nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        documented_node_ids = {
            article["runtimeIdentity"]["classType"]
            for _, article in self.articles
            if article.get("runtimeIdentity", {}).get("origin") == "backend"
        }
        self.nodes = {node_id: self.nodes[node_id] for node_id in documented_node_ids}
        full_frontend_path = catalog.CONTENT / "runtime" / "comfyui-frontend-1.48.7.frontend-inventory.json"
        full_frontend = catalog.parse_frontend_inventory(catalog.load_json(full_frontend_path))
        documented_frontend_ids = {
            article["runtimeIdentity"]["classType"]
            for _, article in self.articles
            if article.get("runtimeIdentity", {}).get("origin") == "frontend"
        }
        self.frontend_inventory = copy.deepcopy(full_frontend)
        self.frontend_inventory["nodes"] = {
            node_id: full_frontend["nodes"][node_id] for node_id in documented_frontend_ids
        }

    def approve_stable_fixture(self) -> None:
        self.source_catalog["release"] = {
            "channel": "stable",
            "humanApproval": {
                "state": "approved",
                "approvedBy": "Ответственный редактор",
                "approvedAt": "2026-08-13T15:00:00+03:00",
                "note": "Каталог проверен человеком и готов к стабильному выпуску.",
            },
        }
        for _, article in self.articles:
            if article.get("kind") == "core" or article.get("runtimeIdentity", {}).get("origin") == "frontend":
                runtime = self.nodes.get(article.get("runtimeIdentity", {}).get("classType"), {})
                article["status"] = (
                    "deprecated" if runtime.get("deprecated") is True
                    else "experimental" if runtime.get("experimental") is True
                    else "active"
                )
                article["editorial"]["state"] = "approved"
        for _, recipe in self.recipes:
            recipe["editorial"]["state"] = "approved"

    def reasons(self) -> list[str]:
        return catalog.release_policy_reasons(
            self.source_catalog,
            self.articles,
            self.recipes,
            self.workflows,
            self.nodes,
            frontend_inventory=self.frontend_inventory,
        )

    def test_current_alpha_fails_for_explicit_human_approval(self) -> None:
        reasons = catalog.release_gate_reasons(self.nodes)
        self.assertTrue(any("human approval pending" in reason for reason in reasons))
        self.assertTrue(any("release channel is 'alpha'" in reason for reason in reasons))
        self.assertTrue(any("frontend inventory missing" in reason for reason in reasons))

    def test_release_gate_cli_returns_nonzero_for_alpha(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "tools/catalog.py",
                "release-gate",
                "--inventory",
                str(SAMPLE_INVENTORY),
            ],
            cwd=catalog.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("Stable release gate FAILED", result.stderr)
        self.assertIn("human approval pending", result.stderr)

    def test_approved_fixture_has_complete_local_examples(self) -> None:
        self.approve_stable_fixture()
        reasons = self.reasons()
        self.assertEqual([], reasons)

    def test_gate_reports_missing_stale_and_runtime_module_mismatch(self) -> None:
        self.approve_stable_fixture()
        del self.nodes["SaveImage"]
        self.nodes["KSampler"]["input"]["required"]["steps"][1]["max"] = 20000
        self.nodes["CheckpointLoaderSimple"]["python_module"] = "wrong.module"
        self.nodes["UndocumentedNode"] = {
            "input": {},
            "output": [],
            "python_module": "nodes",
        }
        reasons = self.reasons()
        self.assertTrue(any("missing article for runtime node 'UndocumentedNode'" in reason for reason in reasons))
        self.assertTrue(any("runtime mismatch for core.save-image" in reason for reason in reasons))
        self.assertTrue(any("stale article core.ksampler" in reason for reason in reasons))
        self.assertTrue(any("runtime module mismatch for core.checkpoint-loader-simple" in reason for reason in reasons))

    def test_gate_rejects_unapproved_recipe_and_broken_workflow_asset(self) -> None:
        self.approve_stable_fixture()
        basic_recipe = next(
            recipe
            for _, recipe in self.recipes
            if recipe["recipeId"] == "recipe.basic-text-to-image"
        )
        basic_recipe["editorial"]["state"] = "in_review"
        ksampler = next(article for _, article in self.articles if article["articleId"] == "core.ksampler")
        workflow_asset = next(asset for asset in ksampler["assets"] if asset["type"] == "workflow")
        workflow_asset["path"] = "../../../workflows/missing.workflow.json"
        reasons = self.reasons()
        self.assertTrue(any("referenced recipe recipe.basic-text-to-image is not editorially approved" in reason for reason in reasons))
        self.assertTrue(any("broken example workflow.basic-text-to-image" in reason for reason in reasons))

    def test_frontend_inventory_is_required_for_stable(self) -> None:
        self.approve_stable_fixture()
        self.frontend_inventory = None
        self.assertTrue(any("frontend inventory missing" in reason for reason in self.reasons()))

    def test_frontend_coverage_is_checked_in_both_directions(self) -> None:
        self.approve_stable_fixture()
        self.frontend_inventory["nodes"] = {
            "UndocumentedCanvasNode": {
                "classType": "UndocumentedCanvasNode",
                "packageId": "comfy-core",
            }
        }
        reasons = self.reasons()
        self.assertTrue(any("missing article for frontend runtime type 'UndocumentedCanvasNode'" in reason for reason in reasons))
        self.assertTrue(any("orphan frontend article frontend.reroute" in reason for reason in reasons))

    def test_frontend_inventory_version_must_match_release_target(self) -> None:
        self.approve_stable_fixture()
        self.frontend_inventory["frontendVersion"] = "0.0.1"
        self.assertTrue(any("frontend version mismatch" in reason for reason in self.reasons()))

    def test_frontend_inventory_filters_dev_only_and_rejects_duplicates(self) -> None:
        payload = {
            "$schema": "frontend-inventory.schema.v1.json",
            "schemaVersion": "1.0",
            "source": "unit test",
            "frontendVersion": "1.0.0",
            "capturedAt": "2026-08-13T12:00:00Z",
            "nodes": [
                {"classType": "Visible", "packageId": "comfy-core"},
                {"classType": "Internal", "dev_only": True},
            ],
        }
        parsed = catalog.parse_frontend_inventory(payload)
        self.assertEqual(["Visible"], sorted(parsed["nodes"]))
        payload["nodes"].append({"classType": "Visible"})
        with self.assertRaises(catalog.CatalogError):
            catalog.parse_frontend_inventory(payload)

    def test_dev_only_nodes_are_excluded_from_user_inventory(self) -> None:
        nodes = catalog.object_info_nodes({
            "Visible": {"name": "Visible", "input": {}, "output": []},
            "InternalTest": {"name": "InternalTest", "dev_only": True, "input": {}, "output": []},
        })
        self.assertEqual(["Visible"], sorted(nodes))


@unittest.skipUnless((catalog.ROOT / "node_modules" / "@noble" / "ed25519").exists(), "@noble/ed25519 is not installed")
class SigningTests(unittest.TestCase):
    def test_sign_verify_and_tamper_rejection(self) -> None:
        seed = bytes(range(1, 33))
        seed_value = base64.urlsafe_b64encode(seed).decode("ascii").rstrip("=")
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            unsigned = directory_path / "unsigned.json"
            signed = directory_path / "signed.json"
            unsigned.write_bytes((catalog.GENERATED / "update-manifest.example.json").read_bytes())
            sign_env = {
                **__import__("os").environ,
                "NODES_WIZARD_SIGNING_SEED": seed_value,
                "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                "NODES_WIZARD_PYTHON": sys.executable,
            }
            sign = __import__("subprocess").run(
                ["node", "tools/sign-update.mjs", "sign", "--manifest", str(unsigned), "--artifact-root", str(catalog.CONTENT), "--output", str(signed)],
                cwd=catalog.ROOT,
                env=sign_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, sign.returncode, sign.stderr)
            payload = json.loads(signed.read_text(encoding="utf-8"))
            trusted_key = payload["signature"]["publicKey"]
            verify_env = {
                **__import__("os").environ,
                "NODES_WIZARD_TRUSTED_PUBLIC_KEY": trusted_key,
                "NODES_WIZARD_TRUSTED_KEY_ID": "test-2026",
            }
            verify = __import__("subprocess").run(
                ["node", "tools/sign-update.mjs", "verify", "--manifest", str(signed)],
                cwd=catalog.ROOT,
                env=verify_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, verify.returncode, verify.stderr)
            payload["catalogVersion"] = "9.9.9"
            signed.write_text(json.dumps(payload), encoding="utf-8")
            tampered = __import__("subprocess").run(
                ["node", "tools/sign-update.mjs", "verify", "--manifest", str(signed)],
                cwd=catalog.ROOT,
                env=verify_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, tampered.returncode)

    def test_manifest_public_key_is_not_trusted_by_itself(self) -> None:
        seed = bytes(range(1, 33))
        seed_value = base64.urlsafe_b64encode(seed).decode("ascii").rstrip("=")
        wrong_key = base64.urlsafe_b64encode(bytes([99]) * 32).decode("ascii").rstrip("=")
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            unsigned = directory_path / "unsigned.json"
            signed = directory_path / "signed.json"
            unsigned.write_bytes((catalog.GENERATED / "update-manifest.example.json").read_bytes())
            sign_env = {
                **__import__("os").environ,
                "NODES_WIZARD_SIGNING_SEED": seed_value,
                "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                "NODES_WIZARD_PYTHON": sys.executable,
            }
            result = __import__("subprocess").run(
                ["node", "tools/sign-update.mjs", "sign", "--manifest", str(unsigned), "--artifact-root", str(catalog.CONTENT), "--output", str(signed)],
                cwd=catalog.ROOT,
                env=sign_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            verify_env = {**__import__("os").environ, "NODES_WIZARD_TRUSTED_PUBLIC_KEY": wrong_key}
            rejected = __import__("subprocess").run(
                ["node", "tools/sign-update.mjs", "verify", "--manifest", str(signed)],
                cwd=catalog.ROOT,
                env=verify_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("independently configured trusted public key", rejected.stderr)

    def test_sign_rejects_catalog_hash_or_size_drift_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            for case, expected in (("sha256", "SHA-256 mismatch"), ("size", "size mismatch")):
                with self.subTest(case=case):
                    unsigned = directory_path / f"unsigned-{case}.json"
                    signed = directory_path / f"signed-{case}.json"
                    manifest = json.loads((catalog.GENERATED / "update-manifest.example.json").read_text(encoding="utf-8"))
                    catalog_artifact = next(item for item in manifest["artifacts"] if Path(item["path"]).name == "catalog.json")
                    if case == "sha256":
                        catalog_artifact["sha256"] = "0" * 64
                    else:
                        catalog_artifact["size"] += 1
                    unsigned.write_text(json.dumps(manifest), encoding="utf-8")
                    result = subprocess.run(
                        [
                            "node", "tools/sign-update.mjs", "sign",
                            "--manifest", str(unsigned),
                            "--artifact-root", str(catalog.CONTENT),
                            "--output", str(signed),
                        ],
                        cwd=catalog.ROOT,
                        env={
                            **__import__("os").environ,
                            "NODES_WIZARD_SIGNING_SEED": base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii").rstrip("="),
                            "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                            "NODES_WIZARD_PYTHON": sys.executable,
                        },
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse(signed.exists())

    def test_sign_rejects_schema_invalid_catalog_even_when_bytes_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            artifact_root = directory_path / "artifacts"
            local_catalog = artifact_root / "generated" / "catalog.json"
            local_catalog.parent.mkdir(parents=True)
            payload = json.loads((catalog.GENERATED / "catalog.json").read_text(encoding="utf-8"))
            payload["articles"][0]["manifest"]["unsignedDrift"] = True
            catalog_bytes = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            local_catalog.write_bytes(catalog_bytes)

            manifest = json.loads((catalog.GENERATED / "update-manifest.example.json").read_text(encoding="utf-8"))
            catalog_artifact = next(item for item in manifest["artifacts"] if Path(item["path"]).name == "catalog.json")
            catalog_artifact["size"] = len(catalog_bytes)
            catalog_artifact["sha256"] = hashlib.sha256(catalog_bytes).hexdigest()
            unsigned = directory_path / "unsigned.json"
            signed = directory_path / "signed.json"
            unsigned.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "node", "tools/sign-update.mjs", "sign",
                    "--manifest", str(unsigned),
                    "--artifact-root", str(artifact_root),
                    "--output", str(signed),
                ],
                cwd=catalog.ROOT,
                env={
                    **__import__("os").environ,
                    "NODES_WIZARD_SIGNING_SEED": base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii").rstrip("="),
                    "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                    "NODES_WIZARD_PYTHON": sys.executable,
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("compiled catalog contract validation failed", result.stderr)
            self.assertIn("unsignedDrift", result.stderr)
            self.assertFalse(signed.exists())

    def test_sign_rejects_catalog_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            manifest = json.loads((catalog.GENERATED / "update-manifest.example.json").read_text(encoding="utf-8"))
            catalog_artifact = next(item for item in manifest["artifacts"] if Path(item["path"]).name == "catalog.json")
            catalog_artifact["path"] = "../catalog.json"
            unsigned = directory_path / "unsigned.json"
            signed = directory_path / "signed.json"
            unsigned.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    "node", "tools/sign-update.mjs", "sign",
                    "--manifest", str(unsigned),
                    "--artifact-root", str(catalog.CONTENT),
                    "--output", str(signed),
                ],
                cwd=catalog.ROOT,
                env={
                    **__import__("os").environ,
                    "NODES_WIZARD_SIGNING_SEED": base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii").rstrip("="),
                    "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                    "NODES_WIZARD_PYTHON": sys.executable,
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("catalog artifact path is unsafe", result.stderr)
            self.assertFalse(signed.exists())

    def test_sign_rejects_manifest_catalog_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            manifest = json.loads((catalog.GENERATED / "update-manifest.example.json").read_text(encoding="utf-8"))
            manifest["catalogVersion"] = "9.9.9"
            unsigned = directory_path / "unsigned.json"
            signed = directory_path / "signed.json"
            unsigned.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    "node", "tools/sign-update.mjs", "sign",
                    "--manifest", str(unsigned),
                    "--artifact-root", str(catalog.CONTENT),
                    "--output", str(signed),
                ],
                cwd=catalog.ROOT,
                env={
                    **__import__("os").environ,
                    "NODES_WIZARD_SIGNING_SEED": base64.urlsafe_b64encode(bytes(range(1, 33))).decode("ascii").rstrip("="),
                    "NODES_WIZARD_SIGNING_KEY_ID": "test-2026",
                    "NODES_WIZARD_PYTHON": sys.executable,
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("catalogVersion mismatch", result.stderr)
            self.assertFalse(signed.exists())


if __name__ == "__main__":
    unittest.main()
