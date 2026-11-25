"""Stage timing and resource samples for serial and threaded minting."""

import threading
import time
from collections import defaultdict
from contextlib import contextmanager

import numpy as np
import psutil


class Timing:
    def __init__(self, device: str):
        self.device = device
        self.started = time.perf_counter()
        self.stages = defaultdict(lambda: [0.0, 0])
        self.latency = []
        self.cards_seen = 0
        self.samples = []
        self.depths = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()

    def synchronize(self):
        if self.device.startswith(("cuda", "mps")):
            import torch

            if self.device.startswith("cuda"):
                torch.cuda.synchronize(self.device)
            else:
                torch.mps.synchronize()

    @contextmanager
    def measure(self, stage: str, count: int = 1, *, accelerator: bool = False):
        if accelerator:
            self.synchronize()
        started = time.perf_counter()
        try:
            yield
        finally:
            if accelerator:
                self.synchronize()
            with self.lock:
                total = self.stages[stage]
                total[0] += time.perf_counter() - started
                total[1] += count

    def add(self, stage: str, seconds: float, count: int = 1):
        """Record busy time measured elsewhere, such as in a signing process."""
        with self.lock:
            total = self.stages[stage]
            total[0] += seconds
            total[1] += count

    def record_latency(self, samples):
        for elapsed in samples:
            self.cards_seen += 1
            if len(self.latency) < 100_000:
                self.latency.append(elapsed)
            else:
                # Keep latency memory bounded for very large corpora.
                slot = (self.cards_seen * 11400714819323198485 % 2**64) % self.cards_seen
                if slot < len(self.latency):
                    self.latency[slot] = elapsed

    def _sample(self):
        process = psutil.Process()
        process.cpu_percent()
        nvml = None
        handle = None
        if self.device.startswith("cuda"):
            try:
                import pynvml

                pynvml.nvmlInit()
                nvml = pynvml
                handle = nvml.nvmlDeviceGetHandleByIndex(int(self.device.partition(":")[2] or "0"))
            except Exception:
                pass
        try:
            while not self.stop.wait(1):
                row = {
                    "elapsed_s": time.perf_counter() - self.started,
                    "cpu_percent": process.cpu_percent(), "rss_bytes": process.memory_info().rss,
                    "queues": self.depths.copy(),
                }
                if handle is not None:
                    try:
                        row["gpu_percent"] = nvml.nvmlDeviceGetUtilizationRates(handle).gpu
                        row["gpu_memory_bytes"] = nvml.nvmlDeviceGetMemoryInfo(handle).used
                    except nvml.NVMLError:
                        pass
                self.samples.append(row)
        finally:
            if nvml is not None:
                nvml.nvmlShutdown()

    def result(self, cards: int, workers: dict, tokens: int = 0, chunks: int = 0) -> dict:
        elapsed = time.perf_counter() - self.started
        overhead = sum(self.stages.get(stage, [0])[0] for stage in ("load", "warmup", "flush", "sampling"))
        steady = max(elapsed - overhead, 1e-9)
        stages = {}
        for stage, (seconds, items) in self.stages.items():
            stages[stage] = {"busy_s": seconds, "items": items, "items_per_s": items / seconds if seconds else 0}
            if stage in workers:
                stages[stage]["utilization"] = min(1.0, seconds / steady / workers[stage])
        active = [stage for stage in stages if "utilization" in stages[stage]]
        bottleneck = max(active, key=lambda stage: stages[stage]["utilization"], default=None)
        return {
            "wall_s": elapsed, "steady_s": steady, "stages": stages, "cards": cards,
            "cards_per_s": cards / steady, "tokens_per_s": tokens / steady, "chunks_per_s": chunks / steady,
            "bottleneck": bottleneck, "samples": self.samples,
            "latency_s": {f"p{p}": float(np.percentile(self.latency, p)) for p in (50, 90, 99)} if self.latency else {},
        }
