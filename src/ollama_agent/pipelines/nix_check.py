from __future__ import annotations
import subprocess

def run(repo_path: str = ".", **_) -> str:
    result = subprocess.run(
        ["nix", "flake", "check", "--no-build"],
        cwd=repo_path, capture_output=True, text=True, timeout=120
    )
    return "ok" if result.returncode == 0 else result.stderr