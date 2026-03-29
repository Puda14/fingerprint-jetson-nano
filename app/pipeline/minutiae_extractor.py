"""Minutiae extraction: abstract base, FingerNet ONNX backend, and crossing-number fallback."""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------


class MinutiaeType(Enum):
    """Fingerprint minutiae types."""

    RIDGE_ENDING = 0
    BIFURCATION = 1


@dataclass(frozen=True)
class Minutia:
    """A single minutia point with quality metadata.

    Attributes:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
        theta: Orientation angle in radians (-pi, pi].
        type: Minutiae classification.
        quality: Confidence / quality score in [0, 1].
    """

    x: float
    y: float
    theta: float
    type: MinutiaeType
    quality: float


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------


class MinutiaeExtractor(ABC):
    """Interface for minutiae extraction backends."""

    @abstractmethod
    def extract(self, image: np.ndarray) -> list[Minutia]:
        """Extract minutiae from a preprocessed grayscale image.

        Args:
            image: uint8 grayscale image.

        Returns:
            List of detected minutiae.
        """

    def filter_minutiae(
        self,
        minutiae: list[Minutia],
        image_shape: tuple[int, int],
        border_margin: int = 10,
        quality_threshold: float = 0.25,
        max_count: int = 200,
    ) -> list[Minutia]:
        """Remove false minutiae via border exclusion, quality gate, and cap.

        Args:
            minutiae: Raw detections.
            image_shape: (height, width) of the source image.
            border_margin: Pixels from the edge to exclude.
            quality_threshold: Minimum quality to keep.
            max_count: Maximum number of minutiae to return.

        Returns:
            Filtered and sorted (by quality descending) minutiae.
        """
        h, w = image_shape[:2]
        filtered: list[Minutia] = []
        for m in minutiae:
            if m.x < border_margin or m.x >= w - border_margin:
                continue
            if m.y < border_margin or m.y >= h - border_margin:
                continue
            if m.quality < quality_threshold:
                continue
            filtered.append(m)

        # Sort by quality (best first) and cap
        filtered.sort(key=lambda m: m.quality, reverse=True)
        return filtered[:max_count]


# ------------------------------------------------------------------
# FingerNet ONNX backend
# ------------------------------------------------------------------


class FingerNetExtractor(MinutiaeExtractor):
    """Minutiae extractor backed by a FingerNet ONNX model.

    The model is expected to produce:
        - minutiae_map  (H, W): heatmap of minutiae presence
        - orientation_map (H, W): per-pixel orientation in radians
        - type_map (H, W): 0 = ridge ending, 1 = bifurcation
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.5,
        nms_radius: int = 9,
    ) -> None:
        self._model_path = model_path
        self._confidence_threshold = confidence_threshold
        self._nms_radius = nms_radius
        self._session = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                self._model_path,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            logger.info("FingerNet ONNX model loaded from %s", self._model_path)
        except Exception as exc:
            logger.warning(
                "Failed to load FingerNet ONNX model from %s: %s",
                self._model_path,
                exc,
            )
            self._session = None

    def extract(self, image: np.ndarray) -> list[Minutia]:
        if self._session is None:
            logger.error("FingerNet model not loaded; returning empty minutiae list.")
            return []

        # Prepare input: (1, 1, H, W) float32 normalised to [0, 1]
        img = image.astype(np.float32) / 255.0
        if img.ndim == 2:
            img = img[np.newaxis, np.newaxis, :, :]
        elif img.ndim == 3:
            img = np.expand_dims(img.transpose(2, 0, 1), 0)

        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: img})

        minutiae_map: np.ndarray = outputs[0].squeeze()
        orientation_map: np.ndarray = outputs[1].squeeze()
        type_map: np.ndarray = (
            outputs[2].squeeze() if len(outputs) > 2 else np.zeros_like(minutiae_map)
        )

        # NMS on the heatmap
        minutiae_points = self._nms_extraction(minutiae_map, orientation_map, type_map)
        return self.filter_minutiae(minutiae_points, image.shape[:2])

    def _nms_extraction(
        self,
        heatmap: np.ndarray,
        orientation: np.ndarray,
        type_map: np.ndarray,
    ) -> list[Minutia]:
        """Non-maximum suppression on the minutiae heatmap."""
        r = self._nms_radius
        minutiae: list[Minutia] = []

        # Dilate to find local maxima
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)
        )
        dilated = cv2.dilate(heatmap.astype(np.float32), kernel)
        peaks = (heatmap >= dilated) & (heatmap >= self._confidence_threshold)

        ys, xs = np.nonzero(peaks)
        for y_val, x_val in zip(ys, xs):
            theta = float(orientation[y_val, x_val])
            mtype = (
                MinutiaeType.BIFURCATION
                if type_map[y_val, x_val] > 0.5
                else MinutiaeType.RIDGE_ENDING
            )
            quality = float(heatmap[y_val, x_val])
            minutiae.append(
                Minutia(
                    x=float(x_val),
                    y=float(y_val),
                    theta=theta,
                    type=mtype,
                    quality=quality,
                )
            )

        return minutiae


# ------------------------------------------------------------------
# Simple crossing-number (CN) fallback
# ------------------------------------------------------------------


class SimpleCNExtractor(MinutiaeExtractor):
    """Crossing-number based minutiae extractor using OpenCV thinning.

    This is a lightweight, dependency-free fallback that requires only
    OpenCV and numpy.  It is less accurate than a learned model but works
    without GPU or ONNX runtime.
    """

    _CN_ENDING = 1
    _CN_BIFURCATION = 3

    def __init__(
        self,
        binarize_block_size: int = 15,
        binarize_c: int = 10,
        quality_base: float = 0.6,
    ) -> None:
        self._binarize_block_size = binarize_block_size
        self._binarize_c = binarize_c
        self._quality_base = quality_base

    def extract(self, image: np.ndarray) -> list[Minutia]:
        gray = image
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

        # Binarize (adaptive threshold)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self._binarize_block_size,
            self._binarize_c,
        )

        # Thin / skeletonize
        skeleton = cv2.ximgproc.thinning(  # type: ignore[attr-defined]
            binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN  # type: ignore[attr-defined]
        )

        # Crossing number computation
        minutiae = self._crossing_number(skeleton)
        return self.filter_minutiae(minutiae, image.shape[:2])

    def _crossing_number(self, skeleton: np.ndarray) -> list[Minutia]:
        """Detect ridge endings and bifurcations via the crossing number."""
        h, w = skeleton.shape
        # Normalize to 0/1
        skel = (skeleton > 0).astype(np.uint8)

        # 8-connected neighbour offsets (clockwise from top-left)
        offsets = [
            (-1, -1), (-1, 0), (-1, 1), (0, 1),
            (1, 1), (1, 0), (1, -1), (0, -1),
        ]

        minutiae: list[Minutia] = []

        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if skel[y, x] == 0:
                    continue
                neighbours = [int(skel[y + dy, x + dx]) for dy, dx in offsets]
                # CN = 0.5 * sum |P_{i+1} - P_i|
                cn = 0
                for i in range(len(neighbours)):
                    cn += abs(
                        neighbours[(i + 1) % len(neighbours)] - neighbours[i]
                    )
                cn_val = cn // 2

                if cn_val == self._CN_ENDING:
                    theta = self._estimate_orientation(
                        skel, x, y, offsets, neighbours
                    )
                    minutiae.append(
                        Minutia(
                            x=float(x),
                            y=float(y),
                            theta=theta,
                            type=MinutiaeType.RIDGE_ENDING,
                            quality=self._estimate_quality(skel, x, y),
                        )
                    )
                elif cn_val == self._CN_BIFURCATION:
                    theta = self._estimate_orientation(
                        skel, x, y, offsets, neighbours
                    )
                    minutiae.append(
                        Minutia(
                            x=float(x),
                            y=float(y),
                            theta=theta,
                            type=MinutiaeType.BIFURCATION,
                            quality=self._estimate_quality(skel, x, y),
                        )
                    )

        return minutiae

    @staticmethod
    def _estimate_orientation(
        skel: np.ndarray,
        x: int,
        y: int,
        offsets: list[tuple[int, int]],
        neighbours: list[int],
    ) -> float:
        """Rough orientation from the first ridge-pixel neighbour direction."""
        for idx, val in enumerate(neighbours):
            if val == 1:
                dy, dx = offsets[idx]
                return math.atan2(float(dy), float(dx))
        return 0.0

    def _estimate_quality(
        self, skel: np.ndarray, x: int, y: int, radius: int = 8
    ) -> float:
        """Heuristic quality based on local ridge density around the minutia."""
        h, w = skel.shape
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        patch = skel[y0:y1, x0:x1]
        density = float(np.sum(patch)) / max(patch.size, 1)
        # Quality peaks at moderate density (~0.15-0.25)
        quality = 1.0 - abs(density - 0.2) / 0.2
        return float(np.clip(quality * self._quality_base + 0.4, 0.0, 1.0))
