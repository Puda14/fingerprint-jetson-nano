"""FAISS-backed vector index for fingerprint embedding search.

Auto-selects FlatIP (inner product) for small galleries (<5000) and
IVFFlat for larger ones.  Gracefully degrades when ``faiss`` is not
installed by falling back to a pure-numpy brute-force search.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Try to import faiss; set a flag so callers can check availability.
try:
    import faiss  # type: ignore[import-untyped]

    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None  # type: ignore[assignment]
    _FAISS_AVAILABLE = False
    logger.warning(
        "faiss is not installed; FAISSIndexManager will use a numpy fallback."
    )


class FAISSIndexManager:
    """Manages a FAISS index for 1:N fingerprint identification.

    The index stores L2-normalised embeddings and performs **inner-product**
    (cosine similarity) search.

    Selection heuristic:
        * N < 5000  -> ``IndexFlatIP``  (brute-force, exact)
        * N >= 5000 -> ``IndexIVFFlat`` (nlist=min(sqrt(N), 64), nprobe=8)
    """

    IVF_THRESHOLD = 5000

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim
        self._index: Any = None  # faiss.Index or None
        self._id_map: dict[int, int] = {}  # faiss internal idx -> fp_id
        self._reverse_map: dict[int, int] = {}  # fp_id -> faiss internal idx
        self._next_internal_id = 0

        # Numpy fallback storage
        self._np_embeddings: np.ndarray | None = None
        self._np_ids: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Build / rebuild
    # ------------------------------------------------------------------

    def build_index(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        """Build (or rebuild) the index from scratch.

        Args:
            embeddings: (N, dim) float32 L2-normalised embeddings.
            ids: (N,) int array of fingerprint IDs.
        """
        n = embeddings.shape[0]
        embeddings = self._ensure_f32_contiguous(embeddings)

        if _FAISS_AVAILABLE:
            self._build_faiss_index(embeddings, ids, n)
        else:
            self._build_numpy_index(embeddings, ids)

        logger.info("Index built with %d entries (dim=%d).", n, self._dim)

    def _build_faiss_index(
        self, embeddings: np.ndarray, ids: np.ndarray, n: int
    ) -> None:
        if n < self.IVF_THRESHOLD:
            index = faiss.IndexFlatIP(self._dim)
        else:
            nlist = min(int(math.sqrt(n)), 64)
            quantizer = faiss.IndexFlatIP(self._dim)
            index = faiss.IndexIVFFlat(quantizer, self._dim, nlist)
            index.nprobe = 8
            index.train(embeddings)

        index.add(embeddings)
        self._index = index
        self._id_map = {i: int(ids[i]) for i in range(n)}
        self._reverse_map = {int(ids[i]): i for i in range(n)}
        self._next_internal_id = n

    def _build_numpy_index(self, embeddings: np.ndarray, ids: np.ndarray) -> None:
        self._np_embeddings = embeddings.copy()
        self._np_ids = ids.copy()

    # ------------------------------------------------------------------
    # Incremental add
    # ------------------------------------------------------------------

    def add(self, embedding: np.ndarray, fp_id: int) -> None:
        """Add a single embedding to the index.

        Args:
            embedding: (dim,) float32 L2-normalised vector.
            fp_id: Fingerprint identifier.
        """
        embedding = self._ensure_f32_contiguous(
            embedding.reshape(1, self._dim)
        )

        if _FAISS_AVAILABLE:
            if self._index is None:
                self._index = faiss.IndexFlatIP(self._dim)
            self._index.add(embedding)
            internal = self._next_internal_id
            self._id_map[internal] = fp_id
            self._reverse_map[fp_id] = internal
            self._next_internal_id += 1
        else:
            if self._np_embeddings is None:
                self._np_embeddings = embedding
                self._np_ids = np.array([fp_id], dtype=np.int64)
            else:
                self._np_embeddings = np.vstack([self._np_embeddings, embedding])
                self._np_ids = np.append(self._np_ids, fp_id)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self, query: np.ndarray, top_k: int = 5
    ) -> list[tuple[int, float]]:
        """Search the index for the closest embeddings.

        Args:
            query: (dim,) float32 L2-normalised query vector.
            top_k: Number of results.

        Returns:
            List of ``(fp_id, similarity_score)`` ordered by descending score.
        """
        query = self._ensure_f32_contiguous(query.reshape(1, self._dim))

        if _FAISS_AVAILABLE:
            return self._search_faiss(query, top_k)
        return self._search_numpy(query, top_k)

    def _search_faiss(
        self, query: np.ndarray, top_k: int
    ) -> list[tuple[int, float]]:
        if self._index is None or self._index.ntotal == 0:
            return []
        k = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(query, k)
        results: list[tuple[int, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            fp_id = self._id_map.get(int(idx), -1)
            results.append((fp_id, float(dist)))
        return results

    def _search_numpy(
        self, query: np.ndarray, top_k: int
    ) -> list[tuple[int, float]]:
        if self._np_embeddings is None or len(self._np_embeddings) == 0:
            return []
        scores = (self._np_embeddings @ query.T).squeeze()
        k = min(top_k, len(scores))
        top_indices = np.argpartition(-scores, k)[:k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]
        results: list[tuple[int, float]] = []
        for idx in top_indices:
            results.append((int(self._np_ids[idx]), float(scores[idx])))  # type: ignore[index]
        return results

    # ------------------------------------------------------------------
    # Rebuild (after deletion)
    # ------------------------------------------------------------------

    def remove_and_rebuild(
        self, embeddings: np.ndarray, ids: np.ndarray
    ) -> None:
        """Full rebuild of the index (used after deletions).

        Args:
            embeddings: (N, dim) float32 embeddings of remaining entries.
            ids: (N,) int IDs.
        """
        self._index = None
        self._id_map.clear()
        self._reverse_map.clear()
        self._next_internal_id = 0
        self._np_embeddings = None
        self._np_ids = None
        if embeddings.shape[0] > 0:
            self.build_index(embeddings, ids)
        logger.info("Index rebuilt with %d entries.", embeddings.shape[0])

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist the index to disk.

        For the FAISS backend the ``.faiss`` file is written alongside a
        numpy ``.npz`` file containing the id maps.  For the numpy fallback
        only the ``.npz`` is written.
        """
        npz_path = path + ".npz"
        if _FAISS_AVAILABLE and self._index is not None:
            faiss.write_index(self._index, path)
            np.savez(
                npz_path,
                id_keys=np.array(list(self._id_map.keys()), dtype=np.int64),
                id_vals=np.array(list(self._id_map.values()), dtype=np.int64),
                next_id=np.array([self._next_internal_id]),
            )
        else:
            np.savez(
                npz_path,
                embeddings=self._np_embeddings,
                ids=self._np_ids,
            )
        logger.info("Index saved to %s", path)

    def load(self, path: str) -> None:
        """Load a previously saved index.

        Args:
            path: Path used in the corresponding ``save()`` call.
        """
        npz_path = path + ".npz"

        if _FAISS_AVAILABLE and os.path.exists(path):
            self._index = faiss.read_index(path)
            if os.path.exists(npz_path):
                data = np.load(npz_path)
                keys = data["id_keys"]
                vals = data["id_vals"]
                self._id_map = dict(zip(keys.tolist(), vals.tolist()))
                self._reverse_map = {v: k for k, v in self._id_map.items()}
                self._next_internal_id = int(data["next_id"][0])
            logger.info(
                "FAISS index loaded from %s (%d vectors).",
                path,
                self._index.ntotal,
            )
        elif os.path.exists(npz_path):
            data = np.load(npz_path)
            self._np_embeddings = data.get("embeddings")
            self._np_ids = data.get("ids")
            count = 0 if self._np_embeddings is None else len(self._np_embeddings)
            logger.info("Numpy fallback index loaded from %s (%d vectors).", npz_path, count)
        else:
            logger.warning("No index found at %s", path)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of embeddings in the index."""
        if _FAISS_AVAILABLE and self._index is not None:
            return self._index.ntotal
        if self._np_embeddings is not None:
            return len(self._np_embeddings)
        return 0

    @staticmethod
    def _ensure_f32_contiguous(arr: np.ndarray) -> np.ndarray:
        arr = arr.astype(np.float32)
        if not arr.flags["C_CONTIGUOUS"]:
            arr = np.ascontiguousarray(arr)
        return arr
