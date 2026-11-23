"""Compare captured baseline cards with both production preimage recipes."""

import argparse
import importlib.metadata
import importlib.util
import json
import shutil
import struct
from pathlib import Path

import pytest

from mintkit._ref import REFERENCE_DIR

from libangel_catalog import add_card_options, build_card

GOLDEN = Path(__file__).parent / "golden"
SPEC = importlib.util.spec_from_file_location("mintkit_golden_capture", GOLDEN / "make_golden.py")
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


def _fixtures(tmp_path, monkeypatch, *, embedded=False):
    directory = GOLDEN / "local" if embedded else GOLDEN
    provenance_path = directory / "provenance.json"
    if not provenance_path.is_file():
        pytest.skip("capture baseline cards with tests/golden/make_golden.py first")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if bool(provenance["pandoc"]) != bool(shutil.which("pandoc")):
        pytest.skip("golden capture used a different pandoc setup")
    if shutil.which("pdftotext") is None:
        pytest.skip("PDF fixtures require pdftotext")
    packages = ("Pillow", "torch", "sentence-transformers", "transformers", "numpy") if embedded else ("Pillow",)
    for package in packages:
        if package in provenance["versions"]:
            try:
                installed = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                pytest.skip(f"golden capture requires {package}")
            if installed != provenance["versions"][package]:
                pytest.skip(f"golden capture used another {package} version")
    CAPTURE.write_fixtures(tmp_path / "fixtures", provenance["commit"])
    monkeypatch.chdir(tmp_path)
    return directory


def _args(fixture, model=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact")
    add_card_options(parser)
    return parser.parse_args([
        f"fixtures/{fixture}", "--schema", str(REFERENCE_DIR / "clawmarc_catalog_card.h"),
        "--card-issued-unix", str(CAPTURE.ISSUED_UNIX),
        *(("--embedding-model", model) if model else ("--no-embed",)),
    ])


def _capture_pairs(directory):
    cards = sorted(directory.glob("*.cxcc"))
    if not cards:
        pytest.skip(f"no captured cards at {directory}")
    for card in cards:
        yield card.name.removesuffix(".cxcc"), card.read_bytes(), json.loads(
            card.with_suffix(".cxcc.json").read_text(encoding="utf-8"),
        )


def test_no_embed_matches_baseline(tmp_path, monkeypatch):
    directory = _fixtures(tmp_path, monkeypatch)
    for fixture, card, meta in _capture_pairs(directory / "no-embed"):
        assert build_card(_args(fixture)) == (card, meta)


def _only_vector_changes(old, new):
    split = struct.unpack_from("<H", old, 8)[0]
    assert new[:0x0D0] == old[:0x0D0]
    assert new[0x110:0x330] == old[0x110:0x330]
    assert new[0x350:0x4C0] == old[0x350:0x4C0]
    assert new[0x4C0 + split:0xFC0] == old[0x4C0 + split:0xFC0]
    assert new[0xFC8:] == old[0xFC8:]


def _assert_sidecar_changes(old, new):
    without_checksums = {"card_id", "card_content_id", "header_crc32", "body_crc32", "signature_b64"}
    for key in old.keys() | new.keys():
        if key in {"policy", "text_segments"}:
            continue
        if key == "cxcc":
            assert {k: v for k, v in new[key].items() if k not in without_checksums} == {
                k: v for k, v in old[key].items() if k not in without_checksums
            }
        else:
            assert new[key] == old[key]
    for key in ("title", "abstract", "keywords", "classification", "body_sha256"):
        assert new["text_segments"][key] == old["text_segments"][key]


@pytest.mark.model
@pytest.mark.parametrize("alias", CAPTURE.MODELS)
def test_model_recipes_against_baseline(alias, tmp_path, monkeypatch):
    import libangel_mint

    pytest.importorskip("sentence_transformers")
    from sentence_transformers import SentenceTransformer

    monkeypatch.setattr(libangel_mint, "load_embedding_model", lambda name: SentenceTransformer(name, device="cpu"))
    directory = _fixtures(tmp_path, monkeypatch, embedded=True)
    for fixture, expected_card, expected_meta in _capture_pairs(directory / alias):
        args = _args(fixture, CAPTURE.MODELS[alias])
        legacy_card, legacy_meta = build_card(args, legacy_embedding=True)
        if alias != "mpnet":
            assert (legacy_card, legacy_meta) == (expected_card, expected_meta)
        else:
            _only_vector_changes(expected_card, legacy_card)
            _assert_sidecar_changes(expected_meta, legacy_meta)
            stable = set(expected_meta["policy"]) - {"chunking", "pooling", "embedding_sha256"}
            assert {key: legacy_meta["policy"][key] for key in stable} == {
                key: expected_meta["policy"][key] for key in stable
            }
            assert legacy_meta["policy"]["chunking"]["max_body_tokens_per_chunk"] == 126
        current_card, current_meta = build_card(args)
        _only_vector_changes(legacy_card, current_card)
        _assert_sidecar_changes(legacy_meta, current_meta)
        assert current_meta["policy"]["preimage_recipe"] == "title+body/v2"
        if current_meta["text_segments"]["title_source"] == "metadata":
            assert current_meta["text_segments"]["embedding_preimage"].startswith(current_meta["text_segments"]["title"])
