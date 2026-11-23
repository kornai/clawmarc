"""Inspect and verify both serial and reduction-aware run layouts."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import _ref
from .store import ShardReader, verify_output


def read_run(directory: Path, *, allow_partial=False):
    try:
        run = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        status = run["status"]
        outputs = run["outputs"]
        schema = run["schema"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid run manifest in {directory}") from exc
    if schema != "mintkit-run-1" or (status != "complete" and not allow_partial):
        raise ValueError(f"Expected a complete mintkit-run-1 manifest in {directory}")
    if not isinstance(outputs, dict):
        raise ValueError(f"Invalid outputs in {directory}")
    return run


def _name(value: str) -> str:
    if Path(value).name != value or value in {"", ".", ".."}:
        raise ValueError(f"Invalid output path component {value!r}")
    return value


def variants(directory, run, *, model=None, reduction=None):
    for alias, group in run["outputs"].items():
        if model is not None and alias != model:
            continue
        root = directory / "cards" / _name(alias)
        if "reductions" not in group:
            if reduction is None or reduction == "mean_tokw":
                yield alias, "mean_tokw", root, group
            continue
        for label, output in group["reductions"].items():
            if reduction is None or reduction in {label, output["reduction"]["name"]}:
                yield alias, label, root / _name(label), output


def iter_cards(directory, output):
    if output["layout"] == "shards":
        for shard in output["shards"]:
            with ShardReader(directory / _name(shard["path"])) as reader:
                yield from reader
    elif output["layout"] == "files":
        for ordinal in range(output["cards"]):
            yield (directory / f"{ordinal:012d}.cxcc").read_bytes()


def inspect(directory, *, model=None, reduction=None, ordinal=None):
    run = read_run(directory, allow_partial=True)
    if ordinal is None:
        return run
    for _, _, root, output in variants(directory, run, model=model, reduction=reduction):
        if output["layout"] == "vectors" or not 0 <= ordinal < output["cards"]:
            continue
        if output["layout"] == "files":
            return _ref.unpack_basic((root / f"{ordinal:012d}.cxcc").read_bytes())
        within_shard = ordinal
        for shard in output["shards"]:
            if within_shard < shard["cards"]:
                with ShardReader(root / _name(shard["path"])) as reader:
                    return _ref.unpack_basic(reader.card(within_shard))
            within_shard -= shard["cards"]
    raise ValueError(f"No card at ordinal {ordinal}")


def verify(directory, *, use_c=False):
    run = read_run(directory, allow_partial=True)
    outputs = [(root, output) for _, _, root, output in variants(directory, run) if output["layout"] != "vectors"]
    if not outputs:
        raise ValueError("Run has no card outputs")
    count = sum(verify_output(root, output) for root, output in outputs)
    if use_c:
        reference = _ref.REFERENCE_DIR / "c"
        tool = reference / "build" / "cxcc-verify"
        with tempfile.TemporaryDirectory(prefix="mintkit-verify-") as temp:
            workspace = Path(temp)
            if not tool.is_file():
                for source in reference.iterdir():
                    if source.is_file():
                        shutil.copy2(source, workspace / source.name)
                subprocess.run(["make", "build/cxcc-verify"], cwd=workspace, check=True)
                tool = workspace / "build" / "cxcc-verify"
            card_path = workspace / "card.cxcc"
            for root, output in outputs:
                for card in iter_cards(root, output):
                    card_path.write_bytes(card)
                    subprocess.run([str(tool), str(card_path)], stdout=subprocess.DEVNULL, check=True)
    return count
