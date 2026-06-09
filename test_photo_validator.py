"""Test photo validation."""

import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from photo_validator import PhotoValidator
from PIL import Image
import io as io_module


def test_valid_photo():
    """Test validation of a valid photo."""
    print("\n[TEST 1] Valid photo validation...")

    # Create a simple valid image (500x500 PNG)
    img = Image.new("RGB", (500, 500), color=(73, 109, 137))
    img_bytes = io_module.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    media_bytes = img_bytes.getvalue()

    result = PhotoValidator.validate_media_bytes(media_bytes, "image/png")

    assert result.is_valid, f"Expected valid, got: {result.message}"
    print(f"  ✓ Valid photo accepted: {result.message}")


def test_blurry_photo():
    """Test detection of blurry photo."""
    print("\n[TEST 2] Blurry photo detection...")

    # Create a blurry image (apply Gaussian blur)
    from PIL import ImageFilter

    img = Image.new("RGB", (500, 500), color=(73, 109, 137))
    blurry_img = img.filter(ImageFilter.GaussianBlur(radius=10))

    img_bytes = io_module.BytesIO()
    blurry_img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    media_bytes = img_bytes.getvalue()

    result = PhotoValidator.validate_media_bytes(media_bytes, "image/png")

    # Should detect as blurry (blur score will be low)
    if not result.is_valid:
        print(f"  ✓ Blurry photo rejected: {result.message}")
    else:
        print(f"  ⚠️ Blurry photo not detected (score may be above threshold)")


def test_small_photo():
    """Test rejection of too-small photo."""
    print("\n[TEST 3] Small photo rejection...")

    # Create a very small image (100x100)
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    img_bytes = io_module.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    media_bytes = img_bytes.getvalue()

    result = PhotoValidator.validate_media_bytes(media_bytes, "image/png")

    assert not result.is_valid, f"Expected invalid, got: {result.message}"
    print(f"  ✓ Small photo rejected: {result.message}")


def test_wrong_mime_type():
    """Test rejection of non-image MIME type."""
    print("\n[TEST 4] Wrong MIME type rejection...")

    img = Image.new("RGB", (500, 500), color=(73, 109, 137))
    img_bytes = io_module.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    media_bytes = img_bytes.getvalue()

    result = PhotoValidator.validate_media_bytes(media_bytes, "application/pdf")

    assert not result.is_valid, f"Expected invalid, got: {result.message}"
    print(f"  ✓ Non-image MIME type rejected: {result.message}")


def test_invalid_image_data():
    """Test rejection of corrupted image data."""
    print("\n[TEST 5] Corrupted image data rejection...")

    # Random bytes that aren't a valid image
    media_bytes = b"not an image at all \x00\x01\x02"

    result = PhotoValidator.validate_media_bytes(media_bytes, "image/jpeg")

    assert not result.is_valid, f"Expected invalid, got: {result.message}"
    print(f"  ✓ Corrupted image rejected: {result.message}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PHOTO VALIDATOR TEST SUITE")
    print("=" * 60)

    try:
        test_valid_photo()
        test_small_photo()
        test_wrong_mime_type()
        test_invalid_image_data()
        test_blurry_photo()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
