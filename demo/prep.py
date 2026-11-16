#!/usr/bin/env python3
"""Restores the sandbox to the state setup.py left, before a recording. Usage: prep.py <tape>"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

B = Path(os.environ.get("BSC_DEMO", "/tmp/bsc-demo"))
ENV = {
    **{k: v for k, v in os.environ.items() if k != "OPENCODE_CLI_CONFIG_CONTENT"},
    "PATH": f"{B / 'bin'}:{os.environ['PATH']}",
    "XDG_CONFIG_HOME": str(B / "home/config"),
    "XDG_DATA_HOME": str(B / "home/data"),
    "XDG_STATE_HOME": str(B / "home/state"),
    "XDG_CACHE_HOME": str(B / "home/cache"),
}


def opencode(*args):
    return subprocess.run(["opencode", *args], env=ENV, capture_output=True, text=True, timeout=120)


opencode("service", "stop")
time.sleep(1.5)
for name in ("data", "state"):
    shutil.rmtree(B / "home" / name, ignore_errors=True)
    shutil.copytree(B / "snapshot" / name, B / "home" / name, symlinks=True)
subprocess.run(["git", "checkout", "--", "."], cwd=B / "acme-web", capture_output=True)

plan = json.loads((B / "plan.json").read_text())
if sys.argv[1:] == ["btw"]:
    # The main session is still working when the recording starts.
    opencode("api", "post", f"/api/session/{plan['main']}/prompt", "--data", json.dumps({"text": "Yes, start with the payment client."}))
    time.sleep(2)
