"""Vector-search backend interface and implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter

import numpy as np


@dataclass(frozen=True)
class BuildStats:
    seconds: float
    ram_bytes: int = 0
    vram_bytes: int = 0
    disk_bytes: int = 0


class Backend(ABC):
    exact = True

    def __init__(self, name, **params):
        self.name = name
        self._params = params

    def params(self):
        return self._params.copy()

    @abstractmethod
    def build(self, matrix) -> BuildStats:
        ...

    @abstractmethod
    def search(self, queries, k):
        ...


def topk(scores, ordinals, k):
    """Sort by decreasing score and then ascending ordinal, including cutoff ties."""
    width = scores.shape[1]
    k = min(k, width)
    if not k:
        return scores[:, :0], np.empty(scores[:, :0].shape, dtype=np.int64)
    output_scores = np.empty((len(scores), k), dtype=np.float32)
    output_ids = np.empty((len(scores), k), dtype=np.int64)
    candidates = np.argpartition(scores, width - k, axis=1)[:, width - k:] if k < width else None
    for index, row in enumerate(scores):
        ids = ordinals if ordinals.ndim == 1 else ordinals[index]
        if candidates is None:
            chosen = np.arange(width)
        else:
            chosen = candidates[index]
            cutoff = row[chosen].min()
            better = chosen[row[chosen] > cutoff]
            ties = np.flatnonzero(row == cutoff)
            ties = ties[np.argsort(ids[ties], kind="stable")[:k - len(better)]]
            chosen = np.concatenate((better, ties))
        order = np.lexsort((ids[chosen], -row[chosen]))
        output_scores[index] = row[chosen][order]
        output_ids[index] = ids[chosen][order]
    return output_scores, output_ids


class Dense(Backend):
    def build(self, matrix):
        started = perf_counter()
        if self.name == "numpy":
            self.matrix = np.array(matrix, dtype=self._params["dtype"], order="C", copy=True)
            return BuildStats(perf_counter() - started, ram_bytes=self.matrix.nbytes)
        self.matrix = matrix
        paths = getattr(matrix, "paths", ())
        disk = sum(path.stat().st_size for path in paths)
        if not disk:
            disk = getattr(matrix, "nbytes", 0)
        return BuildStats(perf_counter() - started, disk_bytes=disk)

    def search(self, queries, k):
        block_size = self._params["block_size"]
        if hasattr(self.matrix, "blocks"):
            blocks = self.matrix.blocks(block_size)
        else:
            blocks = ((start, self.matrix[start:start + block_size]) for start in range(0, len(self.matrix), block_size))
        result = (np.empty((len(queries), 0), dtype=np.float32), np.empty((len(queries), 0), dtype=np.int64))
        for start, block in blocks:
            scores = queries @ np.asarray(block, dtype=np.float32).T
            values, ids = topk(scores, np.arange(start, start + len(block)), k)
            result = topk(np.concatenate((result[0], values), axis=1), np.concatenate((result[1], ids), axis=1), k)
        return result


class TorchBackend(Backend):
    def _sync(self):
        device = self._params["device"]
        if device.startswith("cuda"):
            self.torch.cuda.synchronize(device)
        elif device.startswith("mps"):
            self.torch.mps.synchronize()

    def build(self, matrix):
        started = perf_counter()
        try:
            import torch
        except ImportError as exc:
            raise ValueError("The torch backend requires the embed extra") from exc
        self.torch = torch
        dtype = getattr(torch, self._params["dtype"])
        self.matrix = torch.from_numpy(np.array(matrix, dtype=self._params["dtype"], copy=True)).to(
            device=self._params["device"], dtype=dtype,
        )
        self._sync()
        size = self.matrix.nelement() * self.matrix.element_size()
        cpu = self._params["device"] == "cpu"
        return BuildStats(perf_counter() - started, ram_bytes=size if cpu else 0, vram_bytes=0 if cpu else size)

    def search(self, queries, k):
        torch = self.torch
        q = torch.as_tensor(queries, device=self.matrix.device, dtype=self.matrix.dtype)
        result = (np.empty((len(queries), 0), dtype=np.float32), np.empty((len(queries), 0), dtype=np.int64))
        step = self._params["block_size"]
        for start in range(0, len(self.matrix), step):
            scores = q @ self.matrix[start:start + step].T
            size = min(scores.shape[1], k)
            best, indices = torch.topk(scores, min(size + 1, scores.shape[1]), dim=1)
            values = best[:, :size].float().cpu().numpy()
            ids = indices[:, :size].cpu().numpy() + start
            if best.shape[1] > size:
                for row in torch.where(best[:, size - 1] == best[:, size])[0].tolist():
                    values[row], ids[row] = (value[0] for value in topk(
                        scores[row:row + 1].float().cpu().numpy(), np.arange(start, start + scores.shape[1]), size,
                    ))
            result = topk(np.concatenate((result[0], values), axis=1), np.concatenate((result[1], ids), axis=1), k)
        self._sync()
        return result


class FaissBackend(Backend):
    @property
    def exact(self):
        return self.name == "faiss-flat"

    def build(self, matrix):
        started = perf_counter()
        try:
            import faiss
        except ImportError as exc:
            raise ValueError("FAISS backends require the faiss extra") from exc
        self.faiss = faiss
        n, dim = matrix.shape
        if self.name == "faiss-flat":
            self.index = faiss.IndexFlatIP(dim)
        elif self.name == "faiss-ivf":
            nlist = max(1, min(int(4 * np.sqrt(n)), n // 32))
            self.index = faiss.IndexIVFFlat(faiss.IndexFlatIP(dim), dim, nlist, faiss.METRIC_INNER_PRODUCT)
            rng = np.random.default_rng(20260910)
            ids = rng.choice(n, size=min(n, 256 * nlist), replace=False)
            training = np.ascontiguousarray(matrix[ids], dtype=np.float32)
            self.index.cp.seed = 20260910
            self.index.train(training)
            self.index.nprobe = min(self._params["nprobe"], nlist)
            self._params["nlist"] = nlist
        else:
            self.index = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
            self.index.hnsw.efConstruction = 200
            self.index.hnsw.efSearch = self._params["efSearch"]
        for start in range(0, n, 8192):
            self.index.add(np.ascontiguousarray(matrix[start:start + 8192], dtype=np.float32))
        graph = n * 32 * 2 * 4 if self.name == "faiss-hnsw" else n * 8 if self.name == "faiss-ivf" else 0
        return BuildStats(perf_counter() - started, ram_bytes=n * dim * 4 + graph)

    def search(self, queries, k):
        q = np.ascontiguousarray(queries, dtype=np.float32)
        target = min(k, self.index.ntotal)
        extra = 1 if self.exact and target < self.index.ntotal else 0
        scores, ids = self.index.search(q, target + extra)
        if extra:
            for row in np.flatnonzero(scores[:, target - 1] == scores[:, target]):
                threshold = np.nextafter(scores[row, target - 1], np.float32("-inf"))
                _, found_scores, found_ids = self.index.range_search(q[row:row + 1], float(threshold))
                scores[row, :target], ids[row, :target] = (value[0] for value in topk(found_scores[None], found_ids, target))
        return topk(scores[:, :target], ids[:, :target], target)


def make_backends(names, devices, dtype, block_size, nprobes, ef_search):
    yield Dense("mmap", block_size=block_size)
    for name in dict.fromkeys(names):
        if name == "numpy":
            yield Dense(name, block_size=block_size, dtype=dtype)
        elif name == "torch":
            for device in devices:
                yield TorchBackend(name, device=device, dtype=dtype, block_size=block_size)
        elif name == "faiss-flat":
            yield FaissBackend(name)
        elif name == "faiss-ivf":
            for nprobe in nprobes:
                yield FaissBackend(name, nprobe=nprobe)
        elif name == "faiss-hnsw":
            for value in ef_search:
                yield FaissBackend(name, efSearch=value)
