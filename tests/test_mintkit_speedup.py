"""Speed-up settings: precision resolution, replay guards, and process-pool signing."""

from pathlib import Path

import pytest

from mintkit.cli import main
from mintkit.models import MODELS, ModelSpec, resolve_precision


def test_precision_auto_uses_fp16_only_for_checked_models_on_cuda():
    assert resolve_precision("auto", "cuda", MODELS["bge"]) == "fp16"
    assert resolve_precision("auto", "cuda:1", MODELS["mpnet"]) == "fp16"
    assert resolve_precision("auto", "cuda", MODELS["mbert"]) == "fp32"
    assert resolve_precision("auto", "cpu", MODELS["bge"]) == "fp32"
    assert resolve_precision("auto", "mps", MODELS["bge"]) == "fp32"
    assert resolve_precision("bf16", "cpu", MODELS["mbert"]) == "bf16"
    with pytest.raises(ValueError, match="fp16"):
        resolve_precision("fp16", "cpu", MODELS["bge"])


def _corpus(tmp_path):
    source = tmp_path / "corpus"
    source.mkdir()
    for index in range(9):
        (source / f"{index}.txt").write_text(f"document {index} " * (index + 3), encoding="utf-8")
    return source


def _options(source, *extra):
    return ["mint", f"folder:{source}", "--models", "bge", "--device", "cpu", "--sort-window", "3",
            "--max-inflight", "6", "--batch-chunks", "2", "--issued-unix", "1782071790", "--quiet",
            "--no-direct-ids", *extra]


def test_sign_processes_produce_identical_cards(tmp_path, capsys, monkeypatch, fake_model):
    monkeypatch.setattr(ModelSpec, "load", lambda self, *_args, **_kwargs: fake_model(dimensions=self.dim))
    source = _corpus(tmp_path)
    assert main([*_options(source), "--runs-dir", str(tmp_path / "local")]) == 0
    local = Path(capsys.readouterr().out.strip())
    assert main([*_options(source, "--sign-procs", "2"), "--runs-dir", str(tmp_path / "procs")]) == 0
    procs = Path(capsys.readouterr().out.strip())
    shards = sorted((local / "cards").rglob("shard-*"))
    assert shards
    for shard in shards:
        assert (procs / shard.relative_to(local)).read_bytes() == shard.read_bytes()
    assert main(["verify", str(procs)]) == 0


def test_planning_processes_produce_identical_cards(tmp_path, capsys, monkeypatch, fake_model):
    monkeypatch.setattr(ModelSpec, "load", lambda self, *_args, **_kwargs: fake_model(dimensions=self.dim))
    source = _corpus(tmp_path)
    extra = ("--reductions", "mean_tokw", "ctxprefix", "--keep-chunk-vectors")
    assert main([*_options(source, *extra), "--runs-dir", str(tmp_path / "threads")]) == 0
    threads = Path(capsys.readouterr().out.strip())
    assert main([*_options(source, *extra, "--prep-procs", "2"), "--runs-dir", str(tmp_path / "procs")]) == 0
    procs = Path(capsys.readouterr().out.strip())
    shards = sorted((threads / "cards").rglob("shard-*")) + sorted((threads / "chunks").rglob("*.npy"))
    assert shards
    for shard in shards:
        assert (procs / shard.relative_to(threads)).read_bytes() == shard.read_bytes()


def test_manifest_replay_rejects_a_different_precision(tmp_path, capsys, monkeypatch, fake_model):
    monkeypatch.setattr(ModelSpec, "load", lambda self, *_args, **_kwargs: fake_model(dimensions=self.dim))
    source = _corpus(tmp_path)
    assert main([*_options(source, "--precision", "bf16"), "--runs-dir", str(tmp_path / "first")]) == 0
    run = Path(capsys.readouterr().out.strip())
    with pytest.raises(SystemExit, match="1"):
        main(["mint", "--config", str(run / "manifest.json"), "--precision", "fp32", "--runs-dir", str(tmp_path / "again")])
    assert "precision" in capsys.readouterr().err
    assert main(["mint", "--config", str(run / "manifest.json"), "--runs-dir", str(tmp_path / "again")]) == 0
    replay = Path(capsys.readouterr().out.strip())
    for shard in sorted((run / "cards").rglob("shard-*")):
        assert (replay / shard.relative_to(run)).read_bytes() == shard.read_bytes()
