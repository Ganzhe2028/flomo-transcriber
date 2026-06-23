#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUI_ROOT = PROJECT_ROOT / "gui"
TAURI_ROOT = GUI_ROOT / "src-tauri"
BINARIES_ROOT = TAURI_ROOT / "binaries"
SIDECAR_NAME = "flomo-sidecar"


def _target_triple() -> str:
    result = subprocess.run(
        ["rustc", "--print", "host-tuple"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    fallback = subprocess.run(
        ["rustc", "-Vv"],
        capture_output=True,
        check=False,
        text=True,
    )
    if fallback.returncode != 0:
        raise SystemExit("rustc is required to determine the Tauri sidecar target triple.")
    for line in fallback.stdout.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("Could not determine Rust target triple from rustc -Vv.")


def _run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the flomo-transcriber Tauri sidecar")
    parser.add_argument(
        "--target-triple",
        default=None,
        help="Override the Rust host tuple used in the sidecar filename.",
    )
    args = parser.parse_args()

    target_triple = args.target_triple or _target_triple()
    extension = ".exe" if sys.platform == "win32" else ""
    dist_binary = BINARIES_ROOT / f"{SIDECAR_NAME}{extension}"
    tauri_binary = BINARIES_ROOT / f"{SIDECAR_NAME}-{target_triple}{extension}"

    BINARIES_ROOT.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--noconsole",
            "--onefile",
            "--name",
            SIDECAR_NAME,
            "--paths",
            str(PROJECT_ROOT / "src"),
            "--distpath",
            str(BINARIES_ROOT),
            "--workpath",
            str(TAURI_ROOT / "pyinstaller-build"),
            "--specpath",
            str(TAURI_ROOT / "pyinstaller-spec"),
            str(PROJECT_ROOT / "scripts" / "flomo_sidecar.py"),
        ]
    )

    if not dist_binary.exists():
        raise SystemExit(f"PyInstaller output not found: {dist_binary}")
    if tauri_binary.exists():
        tauri_binary.unlink()
    shutil.move(str(dist_binary), str(tauri_binary))
    print(f"Sidecar ready: {tauri_binary}")


if __name__ == "__main__":
    main()
