"""Execute fixed mint presets and record measured runs."""

import csv
import itertools
import json
import statistics
import sys
from pathlib import Path

import yaml


BENCH_FIELDS = ("schema", "preset", "model", "device", "host", "cpu", "gpus", "python", "torch",
                "run_ids", "settings", "cards_per_s_median", "cards_per_s_min", "cards_per_s_max",
                "tokens_per_s_median", "latency_p99_s_median", "bottleneck")
SWEEP_FIELDS = {"batch_chunks", "prep_workers", "sign_workers", "sort_window", "max_inflight", "torch_threads"}


def append_rows(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8", newline="") as stream:
        if sys.platform != "win32":
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        header = next(csv.reader(stream), None)
        if header is not None and tuple(header) != fields:
            raise ValueError(f"Incompatible CSV header in {path}")
        stream.seek(0, 2)
        writer = csv.DictWriter(stream, fieldnames=fields)
        if header is None:
            writer.writeheader()
        writer.writerows(rows)


def _sweep(specs):
    settings = {}
    for spec in specs or ():
        name, separator, raw = spec.partition("=")
        name = name.replace("-", "_")
        if not separator or name not in SWEEP_FIELDS or name in settings:
            raise ValueError(f"Invalid benchmark sweep {spec!r}")
        values = [int(value) for value in raw.split(",")]
        if any(value < 1 for value in values):
            raise ValueError(f"Benchmark sweep values must be positive in {spec!r}")
        settings[name] = values
    for combination in itertools.product(*settings.values()):
        yield dict(zip(settings, combination, strict=True))


def bench(args, mint_parser, mint):
    presets = yaml.safe_load(Path(__file__).with_name("bench_presets.yaml").read_text(encoding="utf-8"))
    if args.preset not in presets:
        raise ValueError(f"Unknown benchmark preset {args.preset!r}")
    defaults = presets[args.preset].copy()
    source = defaults.pop("source", None) or (f"folder:{args.folder}" if args.folder else None)
    if source is None:
        raise ValueError("folder-pdf requires --folder")
    template = ["mint", source, "--runs-dir", str(args.runs_dir), "--device", args.device,
                "--models", *args.models, "--quiet"]
    for name, value in defaults.items():
        template.extend((f"--{name}", str(value)))
    for settings in _sweep(args.sweep):
        invocation = template.copy()
        for name, value in settings.items():
            invocation.extend((f"--{name.replace('_', '-')}", str(value)))
        samples = []
        for index in range(args.repeat + 1):
            directory = mint(mint_parser.parse_args(invocation), invocation)
            if index > 0:
                timing = json.loads((directory / "timing.json").read_text(encoding="utf-8"))
                manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
                samples.append((manifest, timing))
        machine = samples[0][0]["machine"]
        versions = samples[0][0]["software"]
        rows = []
        for alias in samples[0][1]:
            timings = [timing[alias] for _, timing in samples]
            rates = [timing["cards_per_s"] for timing in timings]
            latencies = [timing["latency_s"]["p99"] for timing in timings if timing["latency_s"]]
            rows.append(dict(
                schema="mintkit-bench-1", preset=args.preset, model=alias, device=args.device,
                host=machine["host_label"], cpu=machine["cpu"], gpus=json.dumps(machine["gpus"]),
                python=versions["python"], torch=versions.get("torch", ""),
                run_ids=" ".join(manifest["run_id"] for manifest, _ in samples), settings=json.dumps(settings, sort_keys=True),
                cards_per_s_median=statistics.median(rates), cards_per_s_min=min(rates), cards_per_s_max=max(rates),
                tokens_per_s_median=statistics.median(timing["tokens_per_s"] for timing in timings),
                latency_p99_s_median=statistics.median(latencies) if latencies else "",
                bottleneck=statistics.mode(timing["bottleneck"] for timing in timings),
            ))
        append_rows(args.output, BENCH_FIELDS, rows)


def report(path):
    if path.is_dir():
        path = path / "INDEX.tsv"
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t" if path.suffix == ".tsv" else ",")
        fields = [key for key in ("run_id", "preset", "model", "device", "host", "source", "cards",
                                  "status", "cards_per_s_median", "bottleneck") if key in (reader.fieldnames or [])]
        print("\t".join(fields))
        for row in reader:
            print("\t".join(row[key] for key in fields))
