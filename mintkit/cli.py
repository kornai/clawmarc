"""Command line for minting, benchmarking, and evaluating ClawMARc runs."""

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path

import psutil

from .sources import SOURCES, Source, load_source
from .sources.base import DEFAULT_SEED


SOURCE_ARGUMENTS = {"folder": "PATH", "mldr": "LANG", "beir": "PATH_OR_NAME", "msmarco": "passage"}
PATH_SETTINGS = {"queries", "qrels", "mldr_root", "runs_dir"}
MINT_DEFAULTS = {"title": "", "abstract": "", "keywords": "", "classification": "", "sequence": 1}
BACKENDS = ("mmap", "numpy", "torch", "faiss-flat", "faiss-ivf", "faiss-hnsw")


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def _nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return number


def _device(value):
    if value in {"cpu", "cuda", "mps"} or (value.startswith("cuda:") and value[5:].isdecimal()):
        return value
    raise argparse.ArgumentTypeError("choose cpu, cuda[:INDEX], or mps")


def _mint_options(mint):
    from ._ref import add_run_options

    mint.add_argument("source", nargs="?", help="Source such as folder:./docs or mldr:en")
    mint.add_argument("--config", type=Path, help="YAML settings or a completed run manifest")
    mint.add_argument("--resume", type=Path, help="Resume a partial or interrupted run")
    mint.add_argument("--sample", default="all", metavar="SPEC", help="all, first:N, random:N, qrels:Q[+D], or ids:FILE")
    mint.add_argument("--seed", default=DEFAULT_SEED, type=int)
    mint.add_argument("--split", help="Query split, or 'none' for a document-only run")
    mint.add_argument("--mode", choices=("corpus", "positives"), help="MLDR corpus or positive passages")
    mint.add_argument("--mldr-root", type=Path, help="Directory containing the MLDR language directories")
    mint.add_argument("--mldr-revision", help="Hugging Face revision for missing local MLDR files")
    mint.add_argument("--glob", help="Recursive folder glob")
    mint.add_argument("--include-hidden", action="store_true")
    mint.add_argument("--queries", type=Path, help="Folder queries.tsv override")
    mint.add_argument("--qrels", type=Path, help="Folder qrels.tsv override")
    mint.add_argument("--models", nargs="+", help="Embedding model aliases or registered local snapshots")
    mint.add_argument("--model-revision", help="Hugging Face commit for the selected model")
    mint.add_argument("--allow-remote-code", action="store_true", help="Allow the pinned jina-v3 adapter code")
    device = mint.add_mutually_exclusive_group()
    device.add_argument("--device", type=_device, help="Default: cuda, then mps, then cpu, whichever is available")
    device.add_argument("--devices", nargs="+", type=_device, help="One embedding device per process")
    mint.add_argument("--precision", choices=("auto", "fp32", "fp16", "bf16"), default="auto",
                      help="Encoder precision; auto uses fp16 on CUDA for models checked against fp32, else fp32")
    mint.add_argument("--direct-ids", action=argparse.BooleanOptionalAction, default=True,
                      help="Feed planned token ids to the encoder instead of re-tokenizing decoded chunk text")
    mint.add_argument("--sign-procs", type=_nonnegative, default=0,
                      help="Sign cards in N worker processes; 0 signs in this process")
    mint.add_argument("--host-label", help="Human-readable host label for the run manifest")
    mint.add_argument("--runs-dir", type=Path, default=Path("runs"))
    mint.add_argument("--layout", choices=("shards", "files"), default="shards")
    mint.add_argument("--shard-size", type=_positive, default=100_000)
    mint.add_argument("--record-docs", action=argparse.BooleanOptionalAction, default=True)
    mint.add_argument("--include-preimage", action="store_true")
    mint.add_argument("--keep-full-text", action="store_true", help="Save extracted text for lexical evaluation")
    mint.add_argument("--keep-checkpoints", action="store_true")
    mint.add_argument("--fail-fast", action="store_true")
    mint.add_argument("--quiet", action="store_true")
    mint.add_argument("--threads", type=_nonnegative, default=1, help="Use 0 for unbatched serial minting")
    mint.add_argument("--prep-workers", type=_positive)
    mint.add_argument("--sign-workers", type=_positive, default=1)
    mint.add_argument("--prep-procs", type=_nonnegative, default=0,
                      help="Prepare and tokenize in N worker processes instead of --prep-workers threads (avoids the GIL)")
    mint.add_argument("--torch-threads", type=_positive)
    mint.add_argument("--batch-chunks", type=_positive, default=64)
    mint.add_argument("--sort-window", type=_positive, default=64)
    mint.add_argument("--max-inflight", type=_positive, default=128)
    mint.add_argument("--text-cache-mb", type=_nonnegative, default=128)
    mint.add_argument("--reductions", nargs="+", default=["mean_tokw"])
    mint.add_argument("--keep-chunk-vectors", action="store_true")
    mint.add_argument("--card-dim", type=_positive)
    add_run_options(mint)
    mint.set_defaults(**MINT_DEFAULTS)


def _filter_options(parser):
    parser.add_argument("--model")
    parser.add_argument("--reduction")


def _parser():
    parser = argparse.ArgumentParser(prog="mintkit", description=__doc__)
    commands = parser.add_subparsers(dest="subcommand", required=True)
    sources = commands.add_parser("sources", help="List sources or the splits of one source")
    sources.add_argument("source", nargs="?")
    mint = commands.add_parser("mint", help="Mint and sign a run")
    _mint_options(mint)
    inspect = commands.add_parser("inspect", help="Show a run manifest or one card")
    inspect.add_argument("run_dir", type=Path)
    inspect.add_argument("--card", type=_nonnegative)
    _filter_options(inspect)
    verify = commands.add_parser("verify", help="Verify available card outputs")
    verify.add_argument("run_dir", type=Path)
    verify.add_argument("--c", action="store_true", help="Also verify with the independent C implementation")
    bench = commands.add_parser("bench", help="Run a minting benchmark preset")
    bench.add_argument("preset")
    bench.add_argument("--folder", type=Path)
    bench.add_argument("--models", nargs="+", default=["bge", "mbert", "mpnet"])
    bench.add_argument("--device", type=_device)
    bench.add_argument("--precision", choices=("auto", "fp32", "fp16", "bf16"), default="auto")
    bench.add_argument("--runs-dir", type=Path, default=Path("runs"))
    bench.add_argument("--repeat", type=_positive, default=3)
    bench.add_argument("--sweep", nargs="+")
    bench.add_argument("--output", type=Path, default=Path("benchmarks/results.csv"))
    commands.add_parser("report", help="Show run or benchmark summaries").add_argument("path", type=Path)
    reduce = commands.add_parser("reduce", help="Mint alternate reductions from cached chunks")
    reduce.add_argument("run_dir", type=Path)
    reduce.add_argument("--reductions", nargs="+", required=True)
    reduce.add_argument("--model")
    export = commands.add_parser("export", help="Export packed vectors and card header columns")
    export.add_argument("run_dir", type=Path)
    _filter_options(export)
    evaluate = commands.add_parser("eval", help="Measure retrieval agreement, latency, and IR quality")
    evaluate.add_argument("run_dir", type=Path)
    _filter_options(evaluate)
    evaluate.add_argument("--backends", nargs="+", choices=BACKENDS, default=["mmap", "numpy"])
    evaluate.add_argument("--dims", nargs="+")
    evaluate.add_argument("--device", nargs="+", type=_device)
    evaluate.add_argument("--query-device", type=_device)
    evaluate.add_argument("--allow-remote-code", action="store_true")
    evaluate.add_argument("--k", nargs="+", type=_positive, default=[10, 100])
    evaluate.add_argument("--dtype", choices=("float16", "float32"), default="float32")
    evaluate.add_argument("--block-size", type=_positive, default=65_536)
    evaluate.add_argument("--nprobe", nargs="+", type=_positive, default=[1, 4, 16, 64])
    evaluate.add_argument("--ef-search", nargs="+", type=_positive, default=[16, 64, 256])
    evaluate.add_argument("--scale-to", type=_positive)
    evaluate.add_argument("--latency-queries", type=_positive, default=100)
    evaluate.add_argument("--compare-run", type=Path)
    evaluate.add_argument("--lexical", action=argparse.BooleanOptionalAction, default=True)
    evaluate.add_argument("--output", type=Path, default=Path("benchmarks/retrieval.csv"))
    return parser, mint


def _source_for_mint(args) -> Source:
    kind = args.source.partition(":")[0]
    folder = {"glob": args.glob, "queries_path": args.queries, "qrels_path": args.qrels}
    mldr = {"mode": args.mode, "root": args.mldr_root, "revision": args.mldr_revision}
    if kind != "folder" and (args.include_hidden or any(value is not None for value in folder.values())):
        raise ValueError("Folder input options apply only to folder sources")
    if kind != "mldr" and any(value is not None for value in mldr.values()):
        raise ValueError("MLDR input options apply only to MLDR sources")
    options = {key: value for key, value in (folder if kind == "folder" else mldr).items() if value is not None}
    if kind == "folder":
        options["include_hidden"] = args.include_hidden
    if kind == "mldr":
        options["split"] = args.split if args.split not in {None, "none"} else "dev"
    source = load_source(args.source, **options)
    if args.split == "none":
        args.split = None
    elif args.split is None:
        available = source.splits()
        preferred = {"mldr": "dev", "msmarco": "dev/small", "beir": "test"}.get(kind)
        args.split = preferred if preferred in available else next(iter(available), None)
    return source


def _mint(args, invocation, *, resume_dir=None, previous=None):
    from . import _ref
    from .models import default_device, resolve_models, resolve_precision
    from .pipeline import run_serial
    from .reductions import parse_reductions

    if not args.source:
        raise ValueError("Mint requires a source")
    if args.devices is not None:
        if len(args.devices) != 1:
            raise ValueError("Mint supports one embedding device per process")
        args.device = args.devices[0]
    if args.device is None:
        args.device = default_device()
    physical = psutil.cpu_count(logical=False) or 1
    args.prep_workers = args.prep_workers or max(1, physical // 2)
    if args.torch_threads is None:
        # Prepare workers mostly wait on I/O for text sources; pass --torch-threads for extraction-heavy runs.
        args.torch_threads = physical
    for name in ("schema", "content_policy"):
        if value := getattr(args, name):
            setattr(args, name, str(Path(value).expanduser().resolve()))
    if args.threads and args.max_inflight < args.sort_window:
        raise ValueError("--max-inflight must be at least --sort-window")
    source = _source_for_mint(args)
    models = {"no-embed": None}
    reductions = parse_reductions(args.reductions)
    if args.embed:
        models = resolve_models(
            args.models or [_ref.DEFAULT_EMBEDDING_MODEL], allow_remote_code=args.allow_remote_code,
            revision=args.model_revision,
        )
        if args.model_revision and len(models) > 1:
            raise ValueError("--model-revision applies to a single model")
        for spec in models.values():
            if args.card_dim and (args.card_dim > spec.dim or (spec.profile and args.card_dim != spec.dim)):
                raise ValueError(f"--card-dim {args.card_dim} is incompatible with {spec.alias} and its registered format")
    elif args.models or args.card_dim or args.keep_chunk_vectors or [red.name for red in reductions] != ["mean_tokw"]:
        raise ValueError("--no-embed cannot be combined with models, card dimensions, or embedding reductions")
    args.precisions = {
        alias: resolve_precision(args.precision, args.device, spec) if spec else None for alias, spec in models.items()
    }
    expected = (previous or {}).get("config", {}).get("precisions") or getattr(args, "replayed_precisions", None)
    if previous is not None and expected is None:
        expected = {alias: "fp32" if spec else None for alias, spec in models.items()}  # mintkit v0 runs were fp32
    if expected is not None and any(expected[alias] != value for alias, value in args.precisions.items() if alias in expected):
        raise ValueError(f"Encoder precision {args.precisions} differs from the recorded run {expected}; pass --precision explicitly")
    return run_serial(source, args, models, ["python", "-m", "mintkit", *invocation], reductions, resume_dir=resume_dir, previous=previous)


def _saved_settings(mint_parser, config, *, manifest, cwd=None):
    actions = {action.dest: action for action in mint_parser._actions}
    settings = {}
    for raw, value in config.items():
        key = raw.replace("-", "_")
        if key in {"model_specs", "issued_unix", "embedding_model", "precisions", "replayed_precisions", *MINT_DEFAULTS} and manifest:
            continue
        if key not in actions or key in {"help", "resume", "config"}:
            raise ValueError(f"Unknown mint setting {raw!r}")
        action = actions[key]
        if key in PATH_SETTINGS and value is not None:
            value = Path(value).expanduser()
            if cwd and not value.is_absolute():
                value = cwd / value
        elif value is not None:
            if manifest and key == "models" and isinstance(value, dict):
                value = [model for model in value.values() if model is not None] or None
                if value is None:
                    settings[key] = value
                    continue
            is_list = action.nargs == "+"
            if is_list and not isinstance(value, list):
                raise ValueError(f"Setting {raw!r} requires a list")
            values = value if is_list else [value]
            if isinstance(action.default, bool):
                if not isinstance(value, bool):
                    raise ValueError(f"Setting {raw!r} expects true or false")
            elif any(isinstance(item, (dict, list)) for item in values):
                raise ValueError(f"Setting {raw!r} requires scalar values")
            else:
                values = [action.type(str(item)) if action.type is not None else str(item) for item in values]
                if action.choices and any(item not in action.choices for item in values):
                    raise ValueError(f"Unsupported value for {raw!r}")
                value = values if is_list else values[0]
        settings[key] = value
    return settings


def _mint_command(parser, mint_parser, args, invocation):
    from .operations import read_run

    if args.resume:
        if len(invocation) != (2 if "=" in invocation[-1] else 3) or args.source or args.config:
            raise ValueError("Use mint --resume RUN_DIR by itself")
        directory = args.resume.expanduser().resolve()
        previous = read_run(directory, allow_partial=True)
        if previous["status"] == "complete" or not (directory / ".checkpoints").is_dir():
            raise ValueError("The run has no resumable checkpoint")
        config = _saved_settings(mint_parser, previous["config"], manifest=True)
        config.setdefault("direct_ids", False)
        saved = argparse.Namespace(**(vars(args) | config | MINT_DEFAULTS))
        cwd = Path(previous.get("cwd", "."))
        with contextlib.chdir(cwd):
            return _mint(saved, invocation, resume_dir=directory, previous=previous)
    if args.config:
        import yaml

        path = args.config.expanduser()
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Mint config must be a mapping")
        is_manifest = document.get("schema") == "mintkit-run-1"
        default_cwd = Path(document["cwd"]) if is_manifest and "cwd" in document else Path.cwd()
        if is_manifest:
            try:
                config = document["config"].copy()
                if "source" not in config:
                    config["source"] = document["source"]["spec"]
            except (AttributeError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid run manifest in {path}") from exc
        else:
            config = document
        if not isinstance(config, dict):
            raise ValueError("Mint settings must be a mapping")
        settings = _saved_settings(mint_parser, config, manifest=is_manifest)
        if is_manifest:
            settings.setdefault("direct_ids", False)  # mintkit v0 re-tokenized decoded chunk text
        mint_parser.set_defaults(**settings)
        replayed = parser.parse_args(invocation)
        if is_manifest:
            replayed.replayed_precisions = config.get("precisions") or {
                alias: "fp32" if spec else None for alias, spec in config.get("model_specs", {}).items()
            }
        with contextlib.chdir(default_cwd):
            return _mint(replayed, invocation)
    return _mint(args, invocation)


def main(argv=None):
    parser, mint_parser = _parser()
    invocation = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(invocation)
    try:
        if args.subcommand == "sources":
            if args.source is None:
                print("\n".join(f"{kind}:{SOURCE_ARGUMENTS.get(kind, 'VALUE')}" for kind in SOURCES))
            else:
                source = load_source(args.source)
                print("\n".join([source.name, *source.splits()]))
        elif args.subcommand == "mint":
            print(_mint_command(parser, mint_parser, args, invocation))
        elif args.subcommand == "inspect":
            from .operations import inspect

            print(json.dumps(inspect(args.run_dir.expanduser(), model=args.model, reduction=args.reduction, ordinal=args.card), indent=2))
        elif args.subcommand == "verify":
            from .operations import verify

            print(f"Verified {verify(args.run_dir.expanduser(), use_c=args.c)} cards")
        elif args.subcommand == "bench":
            from .benchmark import bench
            from .models import default_device

            args.device = args.device or default_device()
            bench(args, parser, _mint)
            print(args.output)
        elif args.subcommand == "report":
            from .benchmark import report

            report(args.path.expanduser())
        elif args.subcommand == "reduce":
            from .reduce_run import reduce_run
            from .reductions import parse_reductions

            reduce_run(args.run_dir.expanduser(), parse_reductions(args.reductions), model=args.model)
        elif args.subcommand == "export":
            from .retrieve.matrix import export_run

            count = export_run(args.run_dir.expanduser(), model=args.model, reduction=args.reduction)
            print(f"Exported {count} vectors")
        elif args.subcommand == "eval":
            from .evaluate import evaluate
            from .models import default_device

            args.device = args.device or [default_device()]
            args.query_device = args.query_device or args.device[0]
            args.run_dir = args.run_dir.expanduser()
            if args.compare_run:
                args.compare_run = args.compare_run.expanduser()
            args.dims = [_positive(dim) for value in args.dims for dim in value.split(",")] if args.dims else None
            print(f"Wrote {evaluate(args)} retrieval benchmark rows")
    except (ValueError, OSError, RuntimeError, argparse.ArgumentTypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"mintkit: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "mintkit: interrupted\n")
    return 0
