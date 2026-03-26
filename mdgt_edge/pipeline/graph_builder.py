"""Dynamic k-NN graph construction for MDGTv2 minutiae sets."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from mdgt_edge.pipeline.minutiae_extractor import Minutia, MinutiaeType

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data container
# ------------------------------------------------------------------


@dataclass(frozen=True)
class GraphData:
    """Graph representation of a minutiae set ready for model inference.

    Attributes:
        node_features: (N, 5) per-minutia features
            [x_norm, y_norm, cos(theta), sin(theta), type_norm].
        edge_index: (N, k) k-NN indices for each node.
        relational_features: (N, N, 7) pairwise relational PE
            [dx, dy, d, cos(alpha), sin(alpha), cos(dtheta), sin(dtheta)].
        num_nodes: Number of minutiae.
    """

    node_features: np.ndarray
    edge_index: np.ndarray
    relational_features: np.ndarray
    num_nodes: int


# ------------------------------------------------------------------
# Builder
# ------------------------------------------------------------------


class DynamicGraphBuilder:
    """Constructs a DGCNN-style dynamic k-NN graph from minutiae.

    Typical usage::

        builder = DynamicGraphBuilder(image_size=192)
        graph = builder.build(minutiae, k=16)
    """

    def __init__(self, image_size: int = 192) -> None:
        self._image_size = float(image_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_feature_matrix(self, minutiae: list[Minutia]) -> np.ndarray:
        """Create the (N, 5) node feature matrix.

        Columns:
            0: x / image_size  (normalised)
            1: y / image_size  (normalised)
            2: cos(theta)
            3: sin(theta)
            4: type_norm  (0.0 = ridge ending, 1.0 = bifurcation)

        Args:
            minutiae: List of extracted minutiae.

        Returns:
            ndarray of shape (N, 5), float32.
        """
        n = len(minutiae)
        if n == 0:
            return np.empty((0, 5), dtype=np.float32)

        features = np.empty((n, 5), dtype=np.float32)
        for i, m in enumerate(minutiae):
            features[i, 0] = m.x / self._image_size
            features[i, 1] = m.y / self._image_size
            features[i, 2] = math.cos(m.theta)
            features[i, 3] = math.sin(m.theta)
            features[i, 4] = 1.0 if m.type == MinutiaeType.BIFURCATION else 0.0
        return features

    def compute_relational_features(self, minutiae: list[Minutia]) -> np.ndarray:
        """Compute the (N, N, 7) pairwise relational positional encoding.

        For each pair (i, j):
            0: dx   = (x_j - x_i) / image_size
            1: dy   = (y_j - y_i) / image_size
            2: d    = Euclidean distance / image_size
            3: cos(alpha)  where alpha = atan2(dy, dx)
            4: sin(alpha)
            5: cos(dtheta) where dtheta = theta_j - theta_i
            6: sin(dtheta)

        Args:
            minutiae: List of extracted minutiae.

        Returns:
            ndarray of shape (N, N, 7), float32.
        """
        n = len(minutiae)
        if n == 0:
            return np.empty((0, 0, 7), dtype=np.float32)

        xs = np.array([m.x for m in minutiae], dtype=np.float64)
        ys = np.array([m.y for m in minutiae], dtype=np.float64)
        thetas = np.array([m.theta for m in minutiae], dtype=np.float64)

        # Pairwise differences -- shape (N, N)
        dx = (xs[np.newaxis, :] - xs[:, np.newaxis]) / self._image_size
        dy = (ys[np.newaxis, :] - ys[:, np.newaxis]) / self._image_size
        dist = np.sqrt(dx ** 2 + dy ** 2)

        alpha = np.arctan2(dy, dx)
        dtheta = thetas[np.newaxis, :] - thetas[:, np.newaxis]

        rel = np.stack(
            [
                dx,
                dy,
                dist,
                np.cos(alpha),
                np.sin(alpha),
                np.cos(dtheta),
                np.sin(dtheta),
            ],
            axis=-1,
        ).astype(np.float32)

        return rel

    def build_knn_graph(self, features: np.ndarray, k: int = 16) -> np.ndarray:
        """Build a k-NN graph from the node feature matrix.

        Uses spatial (x, y) features for neighbour lookup.  If N <= k,
        every node is connected to every other node.

        Args:
            features: (N, 5) node features.
            k: Number of nearest neighbours per node.

        Returns:
            (N, k_eff) int32 index array, where k_eff = min(k, N-1).
        """
        n = features.shape[0]
        if n <= 1:
            return np.empty((n, 0), dtype=np.int32)

        k_eff = min(k, n - 1)

        # Spatial coordinates
        coords = features[:, :2].astype(np.float64)

        # Pairwise squared Euclidean distance
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]  # (N, N, 2)
        sq_dist = np.sum(diff ** 2, axis=-1)  # (N, N)

        # Set self-distance to infinity
        np.fill_diagonal(sq_dist, np.inf)

        # k nearest neighbours per row
        indices = np.argpartition(sq_dist, k_eff, axis=1)[:, :k_eff]

        # Sort each row by distance for deterministic ordering
        row_idx = np.arange(n)[:, np.newaxis]
        selected_dists = sq_dist[row_idx, indices]
        sort_order = np.argsort(selected_dists, axis=1)
        indices = np.take_along_axis(indices, sort_order, axis=1)

        return indices.astype(np.int32)

    def build(self, minutiae: list[Minutia], k: int = 16) -> GraphData:
        """Full graph construction pipeline.

        Args:
            minutiae: Detected minutiae.
            k: k-NN neighbourhood size.

        Returns:
            A ``GraphData`` instance ready for model inference.

        Raises:
            ValueError: If the minutiae list is empty.
        """
        if not minutiae:
            raise ValueError("Cannot build graph from an empty minutiae list.")

        node_features = self.build_feature_matrix(minutiae)
        relational_features = self.compute_relational_features(minutiae)
        edge_index = self.build_knn_graph(node_features, k=k)

        logger.debug(
            "Graph built: %d nodes, k_eff=%d", len(minutiae), edge_index.shape[1]
        )

        return GraphData(
            node_features=node_features,
            edge_index=edge_index,
            relational_features=relational_features,
            num_nodes=len(minutiae),
        )
