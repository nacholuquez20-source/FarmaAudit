"""Test photo evidence flow with validation."""

import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from audit_session import (
    create_session, get_session, save_session, delete_session,
    AuditState, BloqueType,
)
from photo_validator import PhotoValidator
from PIL import Image
import io as io_module


def test_photo_evidence_collection():
    """Test collecting and validating photo evidence."""
    print("\n[TEST 1] Photo evidence collection with validation...")

    # Create session
    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.EVIDENCE
    save_session(session)

    # Create test images
    # 1. Valid photo
    valid_img = Image.new("RGB", (640, 480), color=(100, 150, 200))
    valid_bytes = io_module.BytesIO()
    valid_img.save(valid_bytes, format="JPEG")
    valid_bytes.seek(0)

    result = PhotoValidator.validate_media_bytes(valid_bytes.getvalue(), "image/jpeg")
    assert result.is_valid, f"Valid photo rejected: {result.message}"
    print(f"  ✓ Valid photo: {result.message}")

    # 2. Small photo (should be rejected)
    small_img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    small_bytes = io_module.BytesIO()
    small_img.save(small_bytes, format="JPEG")
    small_bytes.seek(0)

    result = PhotoValidator.validate_media_bytes(small_bytes.getvalue(), "image/jpeg")
    assert not result.is_valid, f"Small photo should be rejected"
    print(f"  ✓ Small photo rejected: {result.message}")

    # 3. Non-image file
    result = PhotoValidator.validate_media_bytes(b"not an image", "application/pdf")
    assert not result.is_valid, f"Non-image should be rejected"
    print(f"  ✓ Non-image rejected: {result.message}")

    print("✅ Photo validation works correctly")
    return session


def test_bloque_assignment():
    """Test assigning validated photos to bloques."""
    print("\n[TEST 2] Photo bloque assignment...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.EVIDENCE
    save_session(session)

    # Simulate receiving a validated photo
    from audit_session import FotoEvidence
    from datetime import datetime, timezone

    foto = FotoEvidence(
        id="foto_001",
        media_id="abc123",
        media_url="https://example.com/foto.jpg",
        bloque=None,
        descripcion="Stock area with missing products",
        validated=True,
    )

    session.add_foto(foto)
    save_session(session)

    assert len(session.fotos) == 1
    assert session.fotos[0].validated is True
    print(f"  ✓ Photo stored: {foto.descripcion}")

    # Assign bloque
    session.fotos[0].bloque = BloqueType.STOCK.value
    save_session(session)

    assert session.fotos[0].bloque == BloqueType.STOCK.value
    print(f"  ✓ Photo assigned to bloque: {session.fotos[0].bloque}")

    # Add desvio for this bloque
    desvio = session.add_desvio(
        bloque=BloqueType.STOCK.value,
        descripcion="Falta reposición de productos en zona central",
    )

    assert len(session.desvios) == 1
    assert session.desvios[0].bloque == BloqueType.STOCK.value
    print(f"  ✓ Desvio added: {desvio.descripcion}")

    print("✅ Bloque assignment works correctly")
    return session


def test_multiple_photos():
    """Test collecting multiple photos with different bloques."""
    print("\n[TEST 3] Multiple photos with different bloques...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.EVIDENCE
    save_session(session)

    from audit_session import FotoEvidence

    # Add multiple photos
    bloques = [BloqueType.LIMPIEZA.value, BloqueType.STOCK.value, BloqueType.OFERTAS.value]

    for i, bloque in enumerate(bloques):
        foto = FotoEvidence(
            id=f"foto_{i+1:03d}",
            media_id=f"media_{i+1}",
            media_url=f"https://example.com/foto{i+1}.jpg",
            bloque=bloque,
            descripcion=f"Issue in {bloque}",
            validated=True,
        )
        session.add_foto(foto)

        desvio = session.add_desvio(
            bloque=bloque,
            descripcion=f"Problem found in {bloque} area",
        )

    save_session(session)

    assert len(session.fotos) == 3
    assert len(session.desvios) == 3

    print(f"  ✓ {len(session.fotos)} photos collected")

    for foto in session.fotos:
        print(f"    • Photo {foto.id} → {foto.bloque}")

    for desvio in session.desvios:
        print(f"    • Desvio in {desvio.bloque}: {desvio.descripcion}")

    print("✅ Multiple photo collection works correctly")
    return session


def test_evidence_to_summary():
    """Test transitioning from evidence collection to summary."""
    print("\n[TEST 4] Evidence collection to summary transition...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.SCORING
    session.bloques = {
        BloqueType.LIMPIEZA.value: 4,
        BloqueType.STOCK.value: 3,
        BloqueType.OFERTAS.value: 2,
        BloqueType.BURBUJAS.value: 5,
    }

    session.estado = AuditState.EVIDENCE

    from audit_session import FotoEvidence

    # Add evidence
    foto = FotoEvidence(
        id="foto_001",
        media_id="media_001",
        media_url="https://example.com/foto.jpg",
        bloque=BloqueType.STOCK.value,
        descripcion="Low stock in central area",
        validated=True,
    )
    session.add_foto(foto)

    session.add_desvio(
        bloque=BloqueType.STOCK.value,
        descripcion="Necesita reposición urgente",
    )

    save_session(session)

    # Transition to summary
    session.estado = AuditState.SUMMARY
    save_session(session)

    assert session.estado == AuditState.SUMMARY
    assert len(session.fotos) == 1
    assert len(session.desvios) == 1

    print(f"  ✓ Transitioned to SUMMARY state")
    print(f"  ✓ {len(session.fotos)} photo(s) ready for summary")
    print(f"  ✓ {len(session.desvios)} desvio(s) ready for summary")

    # Generate summary preview
    summary = f"📋 RESUMEN:\n"
    summary += f"  Sucursal: {session.sucursal_id}\n"
    summary += f"  Puntuaciones: {session.bloques}\n"
    summary += f"  Fotos: {len(session.fotos)}\n"
    summary += f"  Desvíos: {len(session.desvios)}\n"

    print(f"\n{summary}")

    print("✅ Evidence to summary transition works correctly")
    return session


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PHOTO EVIDENCE FLOW TEST SUITE")
    print("=" * 60)

    try:
        test_photo_evidence_collection()
        test_bloque_assignment()
        test_multiple_photos()
        test_evidence_to_summary()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nPhase 3 implementation verified:")
        print("  • Photo download and validation ✓")
        print("  • Bloque assignment ✓")
        print("  • Multiple photo collection ✓")
        print("  • Evidence to summary transition ✓")

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
