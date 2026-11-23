"""Regression coverage for the serial input and output contracts."""

import csv
import gzip
import json

import pytest
from pathlib import Path

from mintkit.cli import main
from mintkit.sources import load_source, select


def test_mldr_positives_use_split_only(tmp_path):
    source_dir = tmp_path / "mldr-v1.0-en"
    source_dir.mkdir()
    rows = [
        {
            "query_id": f"q{ordinal}", "query": f"query {ordinal}",
            "positive_passages": [{"docid": "d1", "text": "same passage"}],
        }
        for ordinal in range(2)
    ]
    with gzip.open(source_dir / "dev.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")

    source = load_source("mldr:en", root=tmp_path, mode="positives")
    selection = select(source, "all", split="dev")
    assert [doc.doc_id for doc in selection.iter_docs()] == ["d1"]
    assert [query.qid for query in selection.queries] == ["q0", "q1"]
    assert selection.qrels == {"q0": {"d1": 1}, "q1": {"d1": 1}}


def test_beir_qrels_sample_keeps_positives_and_requested_distractors(tmp_path):
    (tmp_path / "corpus.jsonl").write_text(
        "".join(json.dumps({"_id": doc_id, "text": doc_id}) + "\n" for doc_id in ("a", "b", "c", "d")),
        encoding="utf-8",
    )
    (tmp_path / "queries.jsonl").write_text(
        '{"_id":"q1","text":"sample query"}\n{"_id":"other","text":"other split"}\n',
        encoding="utf-8",
    )
    (tmp_path / "qrels").mkdir()
    (tmp_path / "qrels" / "test.tsv").write_text(
        "query-id\tcorpus-id\tscore\nq1\tb\t2\nq1\td\t1\n", encoding="utf-8",
    )

    selection = select(load_source(f"beir:{tmp_path}"), "qrels:1+1", split="test")
    picked = [doc.doc_id for doc in selection.iter_docs()]
    assert len(picked) == 3
    assert picked == [doc.doc_id for doc in selection.iter_docs()]
    assert selection.restrict_qrels(set(picked)) == {"q1": {"b": 2, "d": 1}}
    assert [query.qid for query in selection.queries] == ["q1"]


def test_serial_folder_filters_judgments_and_writes_verifiable_shards(tmp_path, capsys):
    corpus = tmp_path / "folder"
    corpus.mkdir()
    (corpus / "a.txt").write_text("first document", encoding="utf-8")
    (corpus / "b.txt").write_text("second document", encoding="utf-8")
    (corpus / "queries.tsv").write_text("qid\ttext\nq1\tquery text\n", encoding="utf-8")
    (corpus / "qrels.tsv").write_text("q1\ta.txt\t2\nq1\tb.txt\t1\n", encoding="utf-8")

    assert main([
        "mint", f"folder:{corpus}", "--runs-dir", str(tmp_path / "runs"),
        "--sample", "first:1", "--no-embed", "--issued-unix", "1782071790",
    ]) == 0
    run_dir = Path(capsys.readouterr().out.strip())
    with (run_dir / "qrels.tsv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert rows == [{"qid": "q1", "doc_id": "a.txt", "relevance": "2"}]
    shard, = (run_dir / "cards" / "no-embed").glob("*/shard-00000.cxcc")
    assert shard.stat().st_size == 4096
    assert main(["verify", str(run_dir)]) == 0
    card = bytearray(shard.read_bytes())
    card[-1] ^= 1
    shard.write_bytes(card)
    with pytest.raises(SystemExit, match="1"):
        main(["verify", str(run_dir)])


def test_short_window_chunking_uses_model_limit(fake_model):
    from mintkit._ref import document_embedding_f16le

    model = fake_model(dimensions=768, max_seq_length=128)
    _, policy = document_embedding_f16le(
        "word " * 300, "sentence-transformers/paraphrase-multilingual-mpnet-base-v2", model=model,
    )
    assert policy["chunking"]["chunk_token_counts"] == [126, 126, 48]



def test_folder_filters_hidden_and_generated_outputs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hidden.txt").write_text("private", encoding="utf-8")
    generated = tmp_path / "old-run"
    generated.mkdir()
    (generated / "manifest.json").write_text('{"schema":"mintkit-run-1"}', encoding="utf-8")
    (generated / "data.txt").write_text("mint output", encoding="utf-8")
    (tmp_path / "data.txt").write_text("source input", encoding="utf-8")
    spec = f"folder:{tmp_path}"
    assert [doc.doc_id for doc in load_source(spec).iter_docs()] == ["data.txt"]
    assert [doc.doc_id for doc in load_source(spec, include_hidden=True).iter_docs()] == [".git/hidden.txt", "data.txt"]


def test_serial_file_layout_verifies(tmp_path, capsys):
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "a.txt").write_text("contents", encoding="utf-8")
    assert main(["mint", f"folder:{source}", "--no-embed", "--threads", "0", "--layout", "files",
                 "--runs-dir", str(tmp_path / "runs")]) == 0
    run = Path(capsys.readouterr().out.strip())
    assert len(list((run / "cards").glob("**/*.cxcc.json"))) == 1
    assert main(["verify", str(run)]) == 0


def test_random_sample_and_missing_id(tmp_path):
    for index in range(20):
        (tmp_path / f"{index:02}.txt").write_text(str(index), encoding="utf-8")
    source = load_source(f"folder:{tmp_path}")
    ids = lambda spec: [doc.doc_id for doc in select(source, spec).iter_docs()]
    assert ids("random:4") == ids("random:4")
    assert ids("random:4") != ids("first:4")
    id_file = tmp_path / "ids"
    id_file.write_text("missing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        ids(f"ids:{id_file}")


def test_msmarco_adapter_reads_the_registered_passage_splits(monkeypatch):
    ir_datasets = pytest.importorskip("ir_datasets")
    from types import SimpleNamespace

    monkeypatch.setattr(ir_datasets, "load", lambda name: SimpleNamespace(
        docs_iter=lambda: iter([SimpleNamespace(doc_id="d1", text="passage")]),
        queries_iter=lambda: iter([SimpleNamespace(query_id="q1", text="query")]),
        qrels_iter=lambda: iter([SimpleNamespace(query_id="q1", doc_id="d1", relevance=2)]),
    ))
    source = load_source("msmarco:passage")
    selection = select(source, "first:1", split="dev/small")
    assert [doc.doc_id for doc in selection.iter_docs()] == ["d1"]
    assert selection.qrels == {"q1": {"d1": 2}}
