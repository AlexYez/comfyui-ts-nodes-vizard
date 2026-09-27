"""Import the clean ComfyUI 0.37.0 CI capture without altering older evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from catalog import ROOT, inventory_report, report_markdown, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    runtime = ROOT / "content/runtime"
    stats = json.loads((args.artifact / "system-stats.json").read_text())["system"]
    assert stats["comfyui_version"] == "0.37.0"
    assert stats["required_frontend_version"] == "1.52.7"
    files = {}
    for source, suffix in (("object-info.json", "object-info.json"), ("node-replacements.json", "node-replacements.json"), ("system-stats.json", "system-stats.json")):
        target = runtime / f"comfyui-0.37.0.{suffix}"
        shutil.copyfile(args.artifact / source, target)
        files[target.name] = {"sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "size": target.stat().st_size}
    write_json(runtime / "comfyui-0.37.0.capture.json", {
        "capturedAt": "2026-09-27", "checkedThrough": "2026-09-27",
        "sourceCommit": "73c9bad4d21e7addbe1d13bc92eee0f1431b017d",
        "frontendCommit": "1a7a6b82514874545dc5e8203d0bd2188c2d9b18",
        "artifactRun": "https://github.com/AlexYez/comfyui-ts-nodes-vizard/actions/runs/36305462585",
        "customNodes": "disabled", "device": "cpu", "files": files,
        "qualification": "Inventory only; not GPU workflow execution or UI compatibility approval",
    })
    report = inventory_report(runtime / "comfyui-0.37.0.object-info.json", runtime / "comfyui-0.37.0.node-replacements.json", runtime / "comfyui-0.37.0.system-stats.json", runtime / "comfyui-0.32.0.object-info.json")
    # Paths in reports must not depend on a developer's absolute workspace.
    report["inventory"]["path"] = "content/runtime/comfyui-0.37.0.object-info.json"
    report["baseline"]["path"] = "content/runtime/comfyui-0.32.0.object-info.json"
    write_json(runtime / "comfyui-0.37.0.inventory-report.json", report)
    (runtime / "comfyui-0.37.0.inventory-report.md").write_text(report_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
