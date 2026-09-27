"""Smoke-test the extracted pack in a real clean CPU ComfyUI checkout."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8198)
    args = parser.parse_args()
    root = args.comfy_root.resolve()
    pack = root / "custom_nodes/comfyui-ts-nodes-vizard"
    assert (pack / "__init__.py").is_file()
    url = f"http://127.0.0.1:{args.port}"
    log_path = root / "wizard-install.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "main.py", "--cpu", "--disable-auto-launch", "--listen", "127.0.0.1", "--port", str(args.port)], cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 180
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"ComfyUI exited: see {log_path}")
                try:
                    with urlopen(url + "/system_stats", timeout=2) as response:
                        stats = json.load(response)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"ComfyUI did not start: see {log_path}")
                    time.sleep(0.5)
            with urlopen(url + "/extensions", timeout=10) as response:
                extensions = json.load(response)
            wizard = [entry for entry in extensions if "/comfyui-ts-nodes-vizard/" in entry]
            assert wizard == ["/extensions/comfyui-ts-nodes-vizard/nodes-wizard.js"], wizard
            prefix = wizard[0].removesuffix("nodes-wizard.js")
            for file in (pack / "web").rglob("*"):
                if not file.is_file() or file.suffix not in {".js", ".mjs", ".json"}:
                    continue
                relative = file.relative_to(pack / "web").as_posix()
                with urlopen(url + prefix + relative, timeout=30) as response:
                    assert response.read() == file.read_bytes(), relative
                    if file.suffix in {".js", ".mjs"}:
                        assert "javascript" in response.headers["Content-Type"], (relative, response.headers)
            print(json.dumps({"installed": True, "system": stats["system"], "extensions": wizard}, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
