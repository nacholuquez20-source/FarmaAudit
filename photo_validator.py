"""Photo validation for audit evidence."""

import logging
from typing import Tuple, Optional
from io import BytesIO
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


class PhotoValidationResult:
    """Result of photo validation."""

    def __init__(self, is_valid: bool, message: str, issues: list = None):
        self.is_valid = is_valid
        self.message = message
        self.issues = issues or []

    def __repr__(self):
        return f"PhotoValidationResult(valid={self.is_valid}, msg='{self.message}')"


class PhotoValidator:
    """Validates photos for audit evidence."""

    MIN_WIDTH = 320
    MIN_HEIGHT = 320
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    BLUR_THRESHOLD = 80.0  # Laplacian variance threshold

    @staticmethod
    def validate_media_bytes(
        media_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> PhotoValidationResult:
        """Validate photo from raw bytes."""

        issues = []

        # Check file size
        if len(media_bytes) > PhotoValidator.MAX_FILE_SIZE:
            issues.append(f"Archivo muy grande ({len(media_bytes) / 1024 / 1024:.1f}MB > 10MB)")
            return PhotoValidationResult(
                is_valid=False,
                message="❌ La foto es demasiado grande. Por favor envía una más pequeña.",
                issues=issues,
            )

        # Check if it's actually an image
        if not mime_type.startswith("image/"):
            issues.append(f"Tipo de archivo no soportado: {mime_type}")
            return PhotoValidationResult(
                is_valid=False,
                message="❌ Eso no es una foto. Por favor envía una imagen.",
                issues=issues,
            )

        # Try to open and validate image
        try:
            image = Image.open(BytesIO(media_bytes))
            image.load()  # Force load to catch corrupted images

            # Check dimensions
            width, height = image.size
            if width < PhotoValidator.MIN_WIDTH or height < PhotoValidator.MIN_HEIGHT:
                issues.append(
                    f"Imagen muy pequeña ({width}x{height} < {PhotoValidator.MIN_WIDTH}x{PhotoValidator.MIN_HEIGHT})"
                )
                return PhotoValidationResult(
                    is_valid=False,
                    message=f"❌ La foto es muy pequeña ({width}x{height}). Necesito mejor calidad.",
                    issues=issues,
                )

            # Check for blur (Laplacian variance method)
            blur_score = PhotoValidator._detect_blur(image)
            if blur_score < PhotoValidator.BLUR_THRESHOLD:
                issues.append(f"Foto borrosa (score: {blur_score:.1f} < {PhotoValidator.BLUR_THRESHOLD})")
                return PhotoValidationResult(
                    is_valid=False,
                    message=f"❌ La foto está borrosa. Por favor envía una más clara.",
                    issues=issues,
                )

        except Exception as e:
            logger.error(f"Photo validation error: {e}")
            issues.append(f"Error validando imagen: {str(e)}")
            return PhotoValidationResult(
                is_valid=False,
                message="❌ No puedo procesar esa imagen. Por favor intenta de nuevo.",
                issues=issues,
            )

        # All checks passed
        return PhotoValidationResult(
            is_valid=True,
            message="✅ Foto guardada correctamente.",
        )

    @staticmethod
    def _detect_blur(image: Image.Image) -> float:
        """Detect blur using edge detection variance method.

        Returns a score where higher = sharper. Threshold ~80 for good quality.
        """
        try:
            # Convert to grayscale if needed
            if image.mode != "L":
                image = image.convert("L")

            # Resize for faster computation
            image.thumbnail((640, 640))

            # Apply edge detection (Laplacian)
            edges = image.filter(ImageFilter.FIND_EDGES)

            # Convert to pixel data and calculate variance
            pixels = list(edges.getdata())
            if not pixels:
                return PhotoValidator.BLUR_THRESHOLD

            # Calculate variance of edge pixels
            mean = sum(pixels) / len(pixels)
            variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)

            return float(variance)
        except Exception as e:
            logger.warning(f"Blur detection failed: {e}, assuming sharp image")
            return PhotoValidator.BLUR_THRESHOLD  # Assume sharp on error
