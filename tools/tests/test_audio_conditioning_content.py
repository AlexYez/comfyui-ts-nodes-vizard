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
    "core.conditioning-stable-audio": {
        "directory": "conditioning-stable-audio",
        "classType": "ConditioningStableAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:66ed7c59279a796c48dc1d34b1cc29d03adeba0eb10fb645da4e02461a6cf391",
        "recipe": "recipe.stable-audio-timing-metadata",
    },
    "core.empty-latent-audio": {
        "directory": "empty-latent-audio",
        "classType": "EmptyLatentAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:51484af23562779ad8e9ad391f7128469e506eb05db2a979896e8f936be422d1",
        "recipe": "recipe.stable-audio-latent-decode",
    },
    "core.vae-decode-audio": {
        "directory": "vae-decode-audio",
        "classType": "VAEDecodeAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:9f6e29cb1600bbe8424449e0e2e967fed15682e4aa771ad09032d4fe178a6308",
        "recipe": "recipe.stable-audio-latent-decode",
    },
    "core.empty-audio": {
        "directory": "empty-audio",
        "classType": "EmptyAudio",
        "pythonModule": "comfy_extras.nodes_audio",
        "fingerprint": "sha256:bdc9d4abdb70953ce1ba6f32c64b6df4b6d061b88f9981f8ffd75d8fe02cf69d",
        "recipe": "recipe.silent-audio-buffer",
    },
}

RECIPE_DIRECTORIES = {
    "recipe.stable-audio-timing-metadata": "stable-audio-timing-metadata",
    "recipe.stable-audio-latent-decode": "stable-audio-latent-decode",
    "recipe.silent-audio-buffer": "silent-audio-buffer",
}

EXPECTED_FRAGMENT_NODES = {
    "recipe.stable-audio-timing-metadata": [
        (
            "ConditioningStableAudio",
            {"seconds_start": 0.0, "seconds_total": 47.0},
        )
    ],
    "recipe.stable-audio-latent-decode": [
        ("EmptyLatentAudio", {"seconds": 47.6, "batch_size": 1}),
        (
            "KSampler",
            {
                "seed": 840755638734093,
                "steps": 50,
                "cfg": 4.98,
                "sampler_name": "dpmpp_3m_sde_gpu",
                "scheduler": "exponential",
                "denoise": 1.0,
            },
        ),
        ("VAEDecodeAudio", {}),
    ],
    "recipe.silent-audio-buffer": [
        (
            "EmptyAudio",
            {"duration": 2.0, "sample_rate": 44100, "channels": 2},
        )
    ],
}

FULL_INVENTORY = catalog.CONTENT / "runtime" / "comfyui-0.32.0.object-info.json"
SOURCE = catalog.ROOT / ".comfyui-source-0.32.0"
WORKFLOW_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_workflow_templates_json-0.1.42-py3-none-any.whl"
)
WORKFLOW_WHEEL_SHA256 = (
    "242982d65e1c51ca03d892bc1009bb6843f457e7dfc0c20afe6438770b7a14a3"
)
EMBEDDED_DOCS_WHEEL = (
    catalog.ROOT
    / ".upstream-cache"
    / "comfyui_embedded_docs-0.5.9-py3-none-any.whl"
)
EMBEDDED_DOCS_WHEEL_SHA256 = (
    "30afae432a71c96aa59421d0f37388c66ff6572b8cbeee8ff045e4d5f84f896c"
)
SYNTHETIC_PROBE = Path(__file__).with_name("audio_synthetic_probe.py")


def article_path(spec: dict[str, str]) -> Path:
    return (
        catalog.CONTENT
        / "articles"
        / "core"
        / spec["directory"]
        / "manifest.json"
    )


def recipe_path(recipe_id: str) -> Path:
    return catalog.CONTENT / "recipes" / RECIPE_DIRECTORIES[recipe_id] / "recipe.json"


def all_article_ids() -> set[str]:
    result: set[str] = set()
    for path in (catalog.CONTENT / "articles").rglob("manifest.json"):
        payload = catalog.load_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("articleId"), str):
            result.add(payload["articleId"])
    return result


def runtime_input_specs(runtime: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in ("required", "optional"):
        values = runtime.get("input", {}).get(group, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def descriptor_type(descriptor: Any) -> Any:
    if not isinstance(descriptor, list) or not descriptor:
        return None
    value = descriptor[0]
    return "COMBO" if isinstance(value, list) else value


def workflow_node_records(
    payload: dict[str, Any], member: str
) -> Iterator[dict[str, Any]]:
    workflow_id = payload.get("id")
    for node in payload.get("nodes", []):
        if isinstance(node, dict):
            yield {
                "member": member,
                "workflowId": workflow_id,
                "scope": "root",
                "node": node,
                "graph": payload,
            }
    definitions = payload.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    for subgraph_index, subgraph in enumerate(subgraphs):
        if not isinstance(subgraph, dict):
            continue
        for node in subgraph.get("nodes", []):
            if isinstance(node, dict):
                yield {
                    "member": member,
                    "workflowId": workflow_id,
                    "scope": "subgraph",
                    "subgraphIndex": subgraph_index,
                    "node": node,
                    "graph": subgraph,
                }


def load_official_workflows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    workflows: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(WORKFLOW_WHEEL) as archive:
        members = sorted(
            member
            for member in archive.namelist()
            if "/templates/" in member and member.endswith(".json")
        )
        for member in members:
            payload = json.loads(archive.read(member).decode("utf-8"))
            workflows[member] = payload
            if isinstance(payload, dict):
                records.extend(workflow_node_records(payload, member))
    return workflows, records


class AudioConditioningContentTests(unittest.TestCase):
    def test_articles_recipes_research_and_cross_links_validate(self) -> None:
        article_ids = all_article_ids()
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
        errors: list[str] = []

        for article_id, spec in ARTICLE_SPECS.items():
            path = article_path(spec)
            article = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(article, schemas["article"]))
            catalog.validate_article(path, article, errors)
            self.assertEqual(article_id, article["articleId"])
            self.assertEqual("draft", article["status"])
            self.assertEqual("in_review", article["editorial"]["state"])
            self.assertIn("human approval pending", article["editorial"]["reviewedBy"])
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
                10,
                len(re.findall(r"^## .+$", body, flags=re.MULTILINE)),
                article_id,
            )
            self.assertNotIn("\ufffd", body)
            self.assertNotRegex(
                body.lower(),
                r"важно отметить|стоит отметить|следует отметить|в современном мире|"
                r"революционн|является незаменим|является мощн|\bдавайте\b|"
                r"глубже погруз|открывает новые|может показаться|позволяет вам|"
                r"подводя итог|в заключение",
            )

            record_path = (
                catalog.CONTENT / "research" / "reviews" / f"{article_id}.json"
            )
            record = catalog.load_json(record_path)
            self.assertEqual([], catalog.json_schema_errors(record, schemas["research"]))
            self.assertEqual(article_id, record["articleId"])
            self.assertEqual(spec["classType"], record["node"]["classType"])
            self.assertEqual(spec["pythonModule"], record["node"]["pythonModule"])
            self.assertEqual("fact_checked", record["state"])
            self.assertEqual("automated_assisted", record["reviewMode"])
            self.assertFalse(record["checks"]["exampleExecuted"])
            self.assertTrue(record["knownGaps"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            self.assertEqual([], catalog.json_schema_errors(recipe, schemas["recipe"]))
            catalog.validate_recipe(path, recipe, article_ids, errors)
            self.assertEqual(recipe_id, recipe["recipeId"])
            self.assertNotIn("workflow", recipe)
            self.assertEqual("in_review", recipe["editorial"]["state"])
            fragment_path = path.parent / recipe["fragment"]["path"]
            fragment = catalog.load_json(fragment_path)
            self.assertEqual([], catalog.json_schema_errors(fragment, schemas["fragment"]))
            catalog.validate_fragment(fragment_path, fragment, errors)
            self.assertEqual(
                EXPECTED_FRAGMENT_NODES[recipe_id],
                [
                    (node["classType"], node["settings"])
                    for node in fragment["nodes"]
                ],
            )

        self.assertEqual([], errors)

    def test_runtime_identity_replacement_fingerprints_ports_and_settings(self) -> None:
        runtime_nodes = catalog.object_info_nodes(catalog.load_json(FULL_INVENTORY))
        self.assertNotIn("StableAudioEmptyLatentImage", runtime_nodes)
        self.assertIn("EmptyAudio", runtime_nodes)
        self.assertFalse(runtime_nodes["EmptyAudio"].get("dev_only", False))
        self.assertFalse(runtime_nodes["EmptyAudio"].get("deprecated", False))

        for article_id, spec in ARTICLE_SPECS.items():
            article = catalog.load_json(article_path(spec))
            runtime = runtime_nodes[spec["classType"]]
            self.assertEqual(spec["pythonModule"], runtime["python_module"])
            self.assertEqual(spec["pythonModule"], article["runtimeIdentity"]["pythonModule"])
            self.assertEqual(
                spec["fingerprint"],
                catalog.schema_fingerprint(spec["classType"], runtime),
                article_id,
            )
            self.assertEqual(spec["fingerprint"], article["editorial"]["schemaHash"])

        for recipe_id in RECIPE_DIRECTORIES:
            path = recipe_path(recipe_id)
            recipe = catalog.load_json(path)
            fragment = catalog.load_json(path.parent / recipe["fragment"]["path"])
            node_by_ref = {node["ref"]: node for node in fragment["nodes"]}
            supplied: dict[str, set[str]] = {
                ref: set(node["settings"]) for ref, node in node_by_ref.items()
            }

            for external in fragment["externalInputs"]:
                target = node_by_ref[external["to"]]
                descriptor = runtime_input_specs(runtime_nodes[target["classType"]])[
                    external["input"]
                ]
                self.assertEqual(external["type"], descriptor_type(descriptor))
                supplied[external["to"]].add(external["input"])

            for connection in fragment["connections"]:
                origin = node_by_ref[connection["from"]]
                target = node_by_ref[connection["to"]]
                origin_runtime = runtime_nodes[origin["classType"]]
                target_runtime = runtime_nodes[target["classType"]]
                output_index = origin_runtime["output_name"].index(connection["output"])
                self.assertEqual(
                    origin_runtime["output"][output_index],
                    descriptor_type(runtime_input_specs(target_runtime)[connection["input"]]),
                )
                supplied[connection["to"]].add(connection["input"])

            for ref, node in node_by_ref.items():
                runtime = runtime_nodes[node["classType"]]
                specs = runtime_input_specs(runtime)
                required = set(runtime.get("input", {}).get("required", {}))
                self.assertTrue(required.issubset(supplied[ref]), (recipe_id, ref))
                for name, value in node["settings"].items():
                    descriptor = specs[name]
                    input_type = descriptor[0]
                    constraints = (
                        descriptor[1]
                        if len(descriptor) > 1 and isinstance(descriptor[1], dict)
                        else {}
                    )
                    if isinstance(input_type, list):
                        self.assertIn(value, input_type)
                    elif input_type == "INT":
                        self.assertIsInstance(value, int)
                        self.assertNotIsInstance(value, bool)
                    elif input_type == "FLOAT":
                        self.assertIsInstance(value, (int, float))
                        self.assertNotIsInstance(value, bool)
                    if "min" in constraints:
                        self.assertGreaterEqual(value, constraints["min"])
                    if "max" in constraints:
                        self.assertLessEqual(value, constraints["max"])

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_articles_track_exact_pinned_implementations(self) -> None:
        audio = (
            SOURCE / "comfy_extras" / "nodes_audio.py"
        ).read_text(encoding="utf-8")
        model_base = (SOURCE / "comfy" / "model_base.py").read_text(encoding="utf-8")
        audio_embedders = (
            SOURCE / "comfy" / "ldm" / "audio" / "embedders.py"
        ).read_text(encoding="utf-8")
        sample = (SOURCE / "comfy" / "sample.py").read_text(encoding="utf-8")

        self.assertIn("round((seconds * 44100 / 2048) / 2) * 2", audio)
        self.assertIn("torch.zeros([batch_size, 64, length]", audio)
        self.assertIn('"downscale_ratio_temporal": 2048', audio)
        self.assertIn('{"seconds_start": seconds_start, "seconds_total": seconds_total}', audio)
        self.assertIn("latent = latent.unbind()[-1]", audio)
        self.assertIn("vae.decode(latent).movedim(-1, 1)", audio)
        self.assertIn("torch.std(audio, dim=[1, 2], keepdim=True) * 5.0", audio)
        self.assertIn("audio /= std", audio)
        self.assertIn('vae_sample_rate if "sample_rate" not in samples else samples["sample_rate"]', audio)
        self.assertIn("int(round(duration * sample_rate))", audio)
        self.assertIn("torch.zeros((1, channels, num_samples), dtype=torch.float32)", audio)

        self.assertIn('seconds_start = kwargs.get("seconds_start", 0)', model_base)
        self.assertIn('seconds_total = kwargs.get("seconds_total"', model_base)
        stable_audio_three = model_base.split("class StableAudio3", 1)[1]
        self.assertNotIn('kwargs.get("seconds_start"', stable_audio_three)
        self.assertIn("floats = floats.clamp(self.min_val, self.max_val)", audio_embedders)
        self.assertIn("downscale_ratio_temporal / latent_format.temporal_downscale_ratio", sample)

    @unittest.skipUnless(
        EMBEDDED_DOCS_WHEEL.exists(), "pinned embedded-docs wheel is absent"
    )
    def test_embedded_docs_paths_and_known_omissions(self) -> None:
        self.assertEqual(
            EMBEDDED_DOCS_WHEEL_SHA256,
            hashlib.sha256(EMBEDDED_DOCS_WHEEL.read_bytes()).hexdigest(),
        )
        names = [
            "ConditioningStableAudio",
            "EmptyLatentAudio",
            "VAEDecodeAudio",
            "EmptyAudio",
        ]
        with zipfile.ZipFile(EMBEDDED_DOCS_WHEEL) as archive:
            docs = {
                name: archive.read(
                    f"comfyui_embedded_docs/docs/{name}/en.md"
                ).decode("utf-8")
                for name in names
            }
            self.assertNotIn(
                "comfyui_embedded_docs/docs/StableAudioEmptyLatentImage/en.md",
                archive.namelist(),
            )
        self.assertTrue(all("This documentation was AI-generated" in text for text in docs.values()))
        self.assertNotIn("StableAudio3", docs["ConditioningStableAudio"])
        self.assertIn("[batch_size, 64, length]", docs["EmptyLatentAudio"])
        self.assertNotIn("hard-coded", docs["EmptyLatentAudio"])
        self.assertIn("normalization", docs["VAEDecodeAudio"])
        self.assertNotIn("audio_sample_rate_output", docs["VAEDecodeAudio"])
        self.assertIn("silent audio clip", docs["EmptyAudio"])
        self.assertNotIn("memory", docs["EmptyAudio"].lower())

    @unittest.skipUnless(WORKFLOW_WHEEL.exists(), "official workflow wheel is absent")
    def test_exhaustive_workflow_counts_and_representative_topology(self) -> None:
        self.assertEqual(
            WORKFLOW_WHEEL_SHA256,
            hashlib.sha256(WORKFLOW_WHEEL.read_bytes()).hexdigest(),
        )
        workflows, records = load_official_workflows()
        self.assertEqual(512, len(workflows))
        target_types = {spec["classType"] for spec in ARTICLE_SPECS.values()}
        targets = [record for record in records if record["node"].get("type") in target_types]
        counts = Counter(record["node"]["type"] for record in targets)
        self.assertEqual({"EmptyLatentAudio": 3, "VAEDecodeAudio": 16}, dict(counts))

        empty = [record for record in targets if record["node"]["type"] == "EmptyLatentAudio"]
        decoded = [record for record in targets if record["node"]["type"] == "VAEDecodeAudio"]
        self.assertEqual(3, len({record["member"] for record in empty}))
        self.assertEqual(Counter({"subgraph": 2, "root": 1}), Counter(r["scope"] for r in empty))
        self.assertEqual(Counter({"root": 11, "subgraph": 5}), Counter(r["scope"] for r in decoded))
        self.assertTrue(all(record["node"].get("widgets_values") == [] for record in decoded))

        member = next(
            name for name in workflows if name.endswith("/audio_stable_audio_example.json")
        )
        workflow = workflows[member]
        self.assertEqual("5fa61cc8-29d9-4deb-9f90-02d3c00b63b3", workflow["id"])
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        self.assertEqual("EmptyLatentAudio", nodes[11]["type"])
        self.assertEqual([47.6, 1], nodes[11]["widgets_values"])
        self.assertEqual("KSampler", nodes[3]["type"])
        self.assertEqual(
            [840755638734093, "randomize", 50, 4.98, "dpmpp_3m_sde_gpu", "exponential", 1],
            nodes[3]["widgets_values"],
        )
        self.assertEqual("VAEDecodeAudio", nodes[12]["type"])
        self.assertEqual([], nodes[12]["widgets_values"])
        self.assertEqual((11, 3, "LATENT"), (links[12][1], links[12][3], links[12][5]))
        self.assertEqual("latent_image", nodes[3]["inputs"][3]["name"])
        self.assertEqual((3, 12, "LATENT"), (links[13][1], links[13][3], links[13][5]))
        self.assertEqual("samples", nodes[12]["inputs"][0]["name"])
        self.assertEqual((4, 12, "VAE"), (links[14][1], links[14][3], links[14][5]))

        recipe = catalog.load_json(recipe_path("recipe.stable-audio-latent-decode"))
        fragment = catalog.load_json(
            recipe_path("recipe.stable-audio-latent-decode").parent
            / recipe["fragment"]["path"]
        )
        fragment_nodes = {node["classType"]: node for node in fragment["nodes"]}
        self.assertEqual(
            {"seconds": 47.6, "batch_size": 1},
            fragment_nodes["EmptyLatentAudio"]["settings"],
        )
        self.assertEqual(
            {
                "seed": nodes[3]["widgets_values"][0],
                "steps": nodes[3]["widgets_values"][2],
                "cfg": nodes[3]["widgets_values"][3],
                "sampler_name": nodes[3]["widgets_values"][4],
                "scheduler": nodes[3]["widgets_values"][5],
                "denoise": nodes[3]["widgets_values"][6],
            },
            fragment_nodes["KSampler"]["settings"],
        )

    @unittest.skipUnless(SOURCE.exists(), "pinned ComfyUI source checkout is absent")
    def test_safe_synthetic_execution_without_model_weights(self) -> None:
        candidates = [
            Path(os.environ.get("TEMP", ""))
            / "nodes-wizard-comfyui-v0.32.0-venv"
            / "Scripts"
            / "python.exe",
            Path(sys.executable),
        ]
        python = next((candidate for candidate in candidates if candidate.exists()), None)
        if python is None:
            self.skipTest("no Python interpreter for the synthetic probe")
        result = subprocess.run(
            [str(python), str(SYNTHETIC_PROBE), str(SOURCE)],
            cwd=SOURCE,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0 and python != Path(sys.executable):
            self.fail(result.stderr or result.stdout)
        if result.returncode != 0:
            self.skipTest(f"synthetic probe dependencies unavailable: {result.stderr}")
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([1, 1, 80], payload["emptyAudio"]["shape"])
        self.assertEqual(0, payload["emptyAudio"]["nonzero"])
        self.assertEqual([2, 64, 22], payload["emptyLatentAudio"]["shape"])
        self.assertEqual(2048, payload["emptyLatentAudio"]["downscaleRatioTemporal"])
        self.assertEqual([1, 2, 4], payload["vaeDecodeAudio"]["shape"])
        self.assertEqual(32000, payload["vaeDecodeAudio"]["sampleRateFromSamples"])
        self.assertEqual(48000, payload["vaeDecodeAudio"]["sampleRateFromVae"])


if __name__ == "__main__":
    unittest.main()
