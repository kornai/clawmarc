#!/usr/bin/env python3
"""Capture catalog-producer compatibility fixtures from a baseline commit."""

import argparse
import importlib.metadata
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "tests" / "golden"
ISSUED_UNIX = 1782071790
REFERENCE_FILES = (
    "clawmarc_catalog_card.h",
    "content_policy.py",
    "libangel_card.py",
    "libangel_catalog.py",
    "libangel_mint.py",
)
MODELS = {
    "bge": "BAAI/bge-small-en-v1.5",
    "mbert": "bert-base-multilingual-cased",
    "mpnet": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
}


def git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def write_fixtures(directory: Path, revision: str) -> list[Path]:
    directory.mkdir()
    text = "A stable paragraph for checking the ClawMARc catalog producer. It includes Unicode café.\n"
    (directory / "short.txt").write_bytes(text.encode("utf-8"))
    (directory / "long.txt").write_bytes((text * 300).encode("utf-8"))
    (directory / "article.md").write_bytes(f"# Article\r\n\r\n{text}".encode("utf-8"))
    (directory / "article.html").write_bytes(f"<html><body><p>{text}</p></body></html>".encode("utf-8"))
    tex = r"\section{Article}" + "\n" + text
    (directory / "article.tex").write_bytes(tex.encode("utf-8"))
    pdf = git("show", f"{revision}:src/clawmarc_wadl.pdf")
    (directory / "article.pdf").write_bytes(pdf)

    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(b"\0\xff"))
    png += png_chunk(b"IEND", b"")
    (directory / "pixel.png").write_bytes(png)
    with zipfile.ZipFile(directory / "project.zip", "w") as archive:
        archive.writestr(zipfile.ZipInfo("project.yaml"), "title: Golden bundle\nroot_tex: article.tex\n")
        archive.writestr(zipfile.ZipInfo("article.tex"), tex.encode("utf-8"))
    return sorted(directory.iterdir())


def capture(
    workspace: Path, fixtures: list[Path], output: Path, alias: str, model: str | None,
) -> None:
    for fixture in fixtures:
        if model is not None and fixture.suffix == ".png":
            continue
        card = output / alias / fixture.with_suffix(f"{fixture.suffix}.cxcc").name
        sidecar = card.with_suffix(".cxcc.json")
        command = [
            sys.executable, "reference/libangel_catalog.py", str(fixture.relative_to(workspace)),
            "--out-card", str(card), "--out-meta", str(sidecar),
            "--schema", "reference/clawmarc_catalog_card.h", "--card-issued-unix", str(ISSUED_UNIX),
        ]
        if model is None:
            command.append("--no-embed")
        else:
            command.extend(("--embedding-model", model))
        if model is not None:
            # The historical CLI has no device flag. Force only model construction
            # onto CPU and leave the historical tokenization and pooling untouched.
            command = [
                sys.executable, "-c",
                "import runpy, sys; import sentence_transformers as st; "
                "constructor = st.SentenceTransformer; "
                "st.SentenceTransformer = lambda *a, **kw: constructor(*a, **(kw | {'device': 'cpu'})); "
                "sys.argv = sys.argv[1:]; sys.path.insert(0, 'reference'); "
                "runpy.run_path(sys.argv[0], run_name='__main__')",
                *command[1:],
            ]
        subprocess.run(command, cwd=workspace, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="0b52701")
    parser.add_argument("--models", nargs="+", choices=MODELS, default=[])
    parser.add_argument("--output", type=Path, default=GOLDEN_DIR)
    args = parser.parse_args()
    revision = git("rev-parse", "--verify", f"{args.ref}^{{commit}}").decode().strip()
    output = args.output.resolve()
    if shutil.which("pdftotext") is None or shutil.which("pandoc") is None:
        parser.error("capturing PDF and HTML fixtures requires pdftotext and pandoc")

    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        reference = workspace / "reference"
        reference.mkdir()
        for filename in REFERENCE_FILES:
            (reference / filename).write_bytes(git("show", f"{revision}:reference/{filename}"))
        fixtures = write_fixtures(workspace / "fixtures", revision)
        capture(workspace, fixtures, output, "no-embed", None)
        for alias in args.models:
            capture(workspace, fixtures, output / "local", alias, MODELS[alias])

    versions = {"python": sys.version.split()[0]}
    for package in ("cryptography", "numpy", "Pillow", "torch", "sentence-transformers", "transformers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
    provenance = {"commit": revision, "issued_unix": ISSUED_UNIX, "models": args.models, "versions": versions, "pandoc": shutil.which("pandoc")}
    manifest_dir = output / "local" if args.models else output
    (manifest_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
