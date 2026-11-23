"""Deterministic checkpoint and retrieval regression tests."""

import json
from pathlib import Path

import numpy as np
import pytest

from mintkit.checkpoint import Journal
from mintkit.cli import main
from mintkit.models import ModelSpec
from mintkit.retrieve.backends import Dense, topk


def test_window_checkpoint_resume_uses_original_batches(tmp_path, capsys, monkeypatch, fake_model):
    monkeypatch.setattr(ModelSpec, "load", lambda self, *_args, **_kwargs: fake_model(dimensions=self.dim))
    source = tmp_path / "corpus"
    source.mkdir()
    for index in range(6):
        (source / f"{index}.txt").write_text(f"document {index} " * (index + 1), encoding="utf-8")
    options = [
        "mint", f"folder:{source}", "--models", "bge", "--sort-window", "2", "--max-inflight", "4",
        "--batch-chunks", "2", "--prep-workers", "2", "--shard-size", "3", "--issued-unix", "1782071790",
        "--quiet", "--keep-chunk-vectors",
    ]
    assert main([*options, "--runs-dir", str(tmp_path / "baseline")]) == 0
    expected = Path(capsys.readouterr().out.strip())
    commit = Journal.commit

    def interrupt(self, identity, rows):
        if len(self.windows) == 1:
            raise KeyboardInterrupt
        return commit(self, identity, rows)

    with monkeypatch.context() as scope:
        scope.setattr(Journal, "commit", interrupt)
        with pytest.raises(SystemExit, match="130"):
            main([*options, "--runs-dir", str(tmp_path / "interrupted")])
    pending, = (tmp_path / "interrupted").glob("*/manifest.json")
    assert json.loads(pending.read_text(encoding="utf-8"))["status"] == "partial"
    assert main(["verify", str(pending.parent)]) == 0
    capsys.readouterr()
    assert main(["mint", "--resume", str(pending.parent)]) == 0
    actual = Path(capsys.readouterr().out.strip())
    for old in sorted((expected / "cards").rglob("shard-*")):
        assert (actual / old.relative_to(expected)).read_bytes() == old.read_bytes()

    def unexpected_load(*_args, **_kwargs):
        pytest.fail("reduce must use cached chunks")

    monkeypatch.setattr(ModelSpec, "load", unexpected_load)
    assert main(["reduce", str(actual), "--reductions", "ema:alpha=0.3", "mean"]) == 0
    assert main(["verify", str(actual)]) == 0


def test_exact_topk_repairs_ties_across_blocks():
    matrix = np.array([[1, 0], [1, 0], [.5, .5], [1, 0]], dtype=np.float16)
    query = np.array([[1, 0]], dtype=np.float32)
    exact = Dense("mmap", block_size=2)
    exact.build(matrix)
    scores, ordinals = exact.search(query, 2)
    np.testing.assert_array_equal(ordinals, [[0, 1]])
    np.testing.assert_array_equal(scores, [[1, 1]])
    _, unordered = topk(np.array([[1, 1, 1]], np.float32), np.array([19, 8, 3]), 2)
    np.testing.assert_array_equal(unordered, [[3, 8]])
