"""Persist run provenance and a local run index."""

import csv
import datetime as dt
import importlib.metadata
import json
import os
import platform
import re
import secrets
import subprocess
from pathlib import Path

import psutil

from ._ref import REFERENCE_DIR
from .sources._io import sha256_file


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def make_run_id(started: dt.datetime, host_label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", host_label.lower()).strip("-")[:48] or "host"
    return f"{started:%Y%m%dT%H%M%SZ}-{slug}-{secrets.token_hex(2)}"


def _cpu_name() -> str:
    try:
        with Path("/proc/cpuinfo").open(encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("model name"):
                    return line.partition(":")[2].strip()
    except OSError:
        pass
    if platform.system() == "Darwin":
        try:
            return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return platform.processor() or platform.machine()


def machine_info(device: str, label: str | None) -> dict:
    cpu = _cpu_name()
    gpus = []
    if device.startswith("cuda"):
        try:
            listing = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                text=True, stderr=subprocess.DEVNULL, timeout=3,
            )
            for name, memory, driver in csv.reader(listing.splitlines(), skipinitialspace=True):
                gpus.append({"name": name, "vram_mib": int(memory), "driver": driver})
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return {
        "host_label": label or f"{device} / {cpu}",
        "gpus": gpus,
        "os": platform.platform(),
        "cpu": cpu,
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(),
        "ram_bytes": psutil.virtual_memory().total,
        "device": device,
    }


def software_info() -> dict:
    software = {"python": platform.python_version()}
    for package in ("numpy", "cryptography", "zstandard", "torch", "sentence-transformers",
                    "transformers", "huggingface-hub", "ir-datasets"):
        try:
            software[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue

    git = ["git", "-C", str(REFERENCE_DIR)]
    try:
        software["git_commit"] = subprocess.check_output(
            [*git, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL,
        ).strip()
        software["git_dirty"] = bool(subprocess.check_output(
            [*git, "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL,
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        pass

    software["reference_sha256"] = {
        name: sha256_file(REFERENCE_DIR / name)
        for name in ("libangel_catalog.py", "libangel_mint.py", "libangel_card.py",
                     "content_policy.py", "clawmarc_catalog_card.h")
    }
    package = Path(__file__).resolve().parent
    software["mintkit_sha256"] = {
        path.relative_to(package).as_posix(): sha256_file(path) for path in sorted(package.rglob("*.py"))
    }
    return software


def write_manifest(run_dir: Path, manifest: dict) -> None:
    temporary = run_dir / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(run_dir / "manifest.json")


def append_run_index(run_dir: Path, manifest: dict) -> None:
    directory = run_dir.parent
    index = directory / "INDEX.tsv"
    fields = ("run_id", "started_utc", "host_label", "source", "models", "cards", "status")
    replacement = (
        manifest["run_id"], manifest["started_utc"], manifest["machine"]["host_label"],
        manifest["source"]["spec"], ",".join(manifest["outputs"]),
        sum(output["cards"] for output in manifest["outputs"].values()), manifest["status"],
    )
    with (directory / ".index.lock").open("a") as lock:
        if os.name == "posix":
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
        rows = []
        if index.is_file():
            with index.open(encoding="utf-8", newline="") as stream:
                reader = csv.reader(stream, delimiter="\t")
                next(reader, None)
                rows.extend(row for row in reader if row and row[0] != manifest["run_id"])
        pending = directory / ".index.pending"
        with pending.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            writer.writerow(fields)
            writer.writerows(rows)
            writer.writerow(replacement)
        pending.replace(index)
