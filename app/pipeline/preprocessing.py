"""Fingerprint image preprocessing: enhancement, segmentation, and normalization."""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FingerprintPreprocessor:
    """Full preprocessing pipeline for raw fingerprint images.

    Pipeline stages:
        1. Decode raw bytes -> grayscale
        2. DPI / size normalization
        3. Segmentation mask creation
        4. CLAHE + Gabor enhancement
    """

    # Gabor filter bank parameters
    _GABOR_KSIZE = 17
    _GABOR_SIGMA = 4.0
    _GABOR_LAMBD = 8.0
    _GABOR_GAMMA = 0.5
    _GABOR_NUM_ORIENTATIONS = 8

    def __init__(
        self,
        clahe_clip: float = 2.5,
        clahe_grid: int = 8,
        block_size: int = 16,
        variance_threshold: float = 100.0,
    ) -> None:
        self._clahe_clip = clahe_clip
        self._clahe_grid = clahe_grid
        self._block_size = block_size
        self._variance_threshold = variance_threshold

        # Pre-build the Gabor filter bank (immutable after init)
        self._gabor_kernels = self._build_gabor_bank()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enhance(self, image: np.ndarray) -> np.ndarray:
        """Apply CLAHE contrast enhancement followed by a Gabor filter bank.

        Args:
            image: Single-channel uint8 grayscale image.

        Returns:
            Enhanced grayscale image (uint8).
        """
        image = self._ensure_grayscale(image)

        # CLAHE
        clahe = cv2.createCLAHE(
            clipLimit=self._clahe_clip,
            tileGridSize=(self._clahe_grid, self._clahe_grid),
        )
        enhanced = clahe.apply(image)

        # Gabor filtering -- take the maximum response across orientations
        gabor_responses: List[np.ndarray] = []
        for kern in self._gabor_kernels:
            filtered = cv2.filter2D(enhanced, cv2.CV_64F, kern)
            gabor_responses.append(np.abs(filtered))

        combined = np.max(np.stack(gabor_responses, axis=0), axis=0)

        # Normalize back to uint8
        combined_norm = cv2.normalize(
            combined, None, 0, 255, cv2.NORM_MINMAX  # type: ignore[arg-type]
        )
        return combined_norm.astype(np.uint8)

    def segment(self, image: np.ndarray) -> np.ndarray:
        """Create a binary segmentation mask separating foreground from background.

        The image is divided into blocks of size ``block_size``.  Blocks whose
        local variance exceeds ``variance_threshold`` are considered foreground.

        Args:
            image: Single-channel uint8 grayscale image.

        Returns:
            Binary mask (uint8, 0 or 255) with the same dimensions as *image*.
        """
        image = self._ensure_grayscale(image)
        h, w = image.shape[:2]
        bs = self._block_size
        mask = np.zeros((h, w), dtype=np.uint8)

        img_f = image.astype(np.float64)

        for y in range(0, h, bs):
            for x in range(0, w, bs):
                block = img_f[y : y + bs, x : x + bs]
                if block.size == 0:
                    continue
                if np.var(block) > self._variance_threshold:
                    mask[y : y + bs, x : x + bs] = 255

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bs, bs))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        return mask

    def normalize(
        self,
        image: np.ndarray,
        target_dpi: int = 500,
        source_dpi: Optional[int] = None,
    ) -> np.ndarray:
        """Resize image so that its effective DPI matches *target_dpi*.

        If *source_dpi* is ``None`` the image is assumed to already be at
        *target_dpi* and only mean/variance normalization is applied.

        Args:
            image: Grayscale image.
            target_dpi: Desired DPI.
            source_dpi: Original DPI of the input image (if known).

        Returns:
            Normalized grayscale image (uint8).
        """
        image = self._ensure_grayscale(image)

        # DPI rescale
        if source_dpi is not None and source_dpi != target_dpi:
            scale = target_dpi / source_dpi
            new_w = max(1, int(round(image.shape[1] * scale)))
            new_h = max(1, int(round(image.shape[0] * scale)))
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Mean-variance normalization
        img_f = image.astype(np.float64)
        mean = np.mean(img_f)
        std = np.std(img_f)
        if std < 1e-6:
            return image
        normalized = (img_f - mean) / std
        # Map to 0-255
        normalized = (normalized - normalized.min()) / (
            normalized.max() - normalized.min() + 1e-8
        )
        return (normalized * 255).astype(np.uint8)

    def process(
        self,
        raw_image: bytes,
        width: int = 192,
        height: int = 192,
    ) -> np.ndarray:
        """Run the full preprocessing pipeline on raw image bytes.

        Steps:
            1. Decode bytes -> grayscale
            2. Normalize DPI / size
            3. Create segmentation mask and apply it
            4. Enhance (CLAHE + Gabor)
            5. Resize to (height, width)

        Args:
            raw_image: Raw image bytes (JPEG, PNG, BMP, or raw grayscale).
            width: Target output width.
            height: Target output height.

        Returns:
            Preprocessed grayscale image of shape ``(height, width)``, uint8.

        Raises:
            ValueError: If the image cannot be decoded.
        """
        # Decode
        arr = np.frombuffer(raw_image, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if image is None:
            # Attempt to interpret as raw grayscale
            total = len(raw_image)
            side = int(math.isqrt(total))
            if side * side == total:
                image = arr.reshape((side, side))
            else:
                raise ValueError(
                    f"Unable to decode image from {len(raw_image)} bytes."
                )

        logger.debug("Decoded image shape: %s", image.shape)

        # Normalize
        image = self.normalize(image)

        # Segment + mask
        mask = self.segment(image)
        image = cv2.bitwise_and(image, image, mask=mask)

        # Enhance
        image = self.enhance(image)

        # Resize to target dimensions
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)

        return image

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_grayscale(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    def _build_gabor_bank(self) -> List[np.ndarray]:
        kernels: List[np.ndarray] = []
        for i in range(self._GABOR_NUM_ORIENTATIONS):
            theta = i * math.pi / self._GABOR_NUM_ORIENTATIONS
            kern = cv2.getGaborKernel(
                ksize=(self._GABOR_KSIZE, self._GABOR_KSIZE),
                sigma=self._GABOR_SIGMA,
                theta=theta,
                lambd=self._GABOR_LAMBD,
                gamma=self._GABOR_GAMMA,
                psi=0,
                ktype=cv2.CV_64F,
            )
            kern /= 1.5 * kern.sum()
            kernels.append(kern)
        return kernels
