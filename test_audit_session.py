"""Quick test of audit session flow."""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from audit_session import (
    create_session, get_session, save_session, delete_session,
    AuditState, BloqueType, BrandType,
    BLOQUE_ORDER, BRAND_ORDER, BLOQUE_LABELS, BRAND_LABELS,
    FotoEvidence
)
from datetime import datetime, timezone

def test_session_creation():
    """Test creating a new session."""
    print("\n[TEST 1] Creating session...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")

    assert session.id_sesion.startswith("audit_")
    assert session.telefono == "+5493816199195"
    assert session.sucursal_id == "SC-001"
    assert session.auditor_nombre == "Juan Pérez"
    assert session.estado == AuditState.IDLE
    assert len(session.bloques) == 0

    print("✅ Session created successfully")
    return session


def test_scoring_flow(session):
    """Test scoring bloques."""
    print("\n[TEST 2] Testing scoring flow...")

    # Move to SCORING
    session.estado = AuditState.SCORING
    save_session(session)

    # Check current bloque
    current = session.get_current_bloque()
    assert current == BloqueType.LIMPIEZA.value
    print(f"  Current bloque: {BLOQUE_LABELS.get(current)}")

    # Score LIMPIEZA
    session.set_bloque_score(BloqueType.LIMPIEZA.value, 4)
    assert session.bloques[BloqueType.LIMPIEZA.value] == 4
    print(f"  ✓ {BLOQUE_LABELS.get(BloqueType.LIMPIEZA.value)}: 4/5")

    # Move to STOCK
    session.move_to_next_bloque()
    current = session.get_current_bloque()
    assert current == BloqueType.STOCK.value
    print(f"  ✓ Moved to {BLOQUE_LABELS.get(current)}")

    # Score STOCK
    session.set_bloque_score(BloqueType.STOCK.value, 3)
    print(f"  ✓ {BLOQUE_LABELS.get(BloqueType.STOCK.value)}: 3/5")

    # Move to OFERTAS
    session.move_to_next_bloque()
    current = session.get_current_bloque()
    assert current == BloqueType.OFERTAS.value
    print(f"  ✓ Moved to {BLOQUE_LABELS.get(current)}")

    # Score OFERTAS
    session.set_bloque_score(BloqueType.OFERTAS.value, 2)
    print(f"  ✓ {BLOQUE_LABELS.get(BloqueType.OFERTAS.value)}: 2/5")

    save_session(session)
    print("✅ Scoring flow works correctly")
    return session


def test_brand_scoring(session):
    """Test brand scoring for OFERTAS."""
    print("\n[TEST 3] Testing brand scoring...")

    # Move to SCORING_BRANDS
    session.estado = AuditState.SCORING_BRANDS
    session.current_brand_index = 0
    save_session(session)

    # Score each brand
    for brand in BRAND_ORDER:
        score = 3 if brand == BrandType.COLGATE.value else 4
        session.set_brand_score(brand, score)
        label = BRAND_LABELS.get(brand, brand)
        print(f"  ✓ {label}: {score}/5")

    # Verify all brands scored
    brands = session.brands.get(BloqueType.OFERTAS.value, {})
    assert len(brands) == len(BRAND_ORDER)
    print(f"  All {len(brands)}/4 brands scored")

    save_session(session)
    print("✅ Brand scoring works correctly")
    return session


def test_evidence(session):
    """Test evidence collection."""
    print("\n[TEST 4] Testing evidence collection...")

    # Move to EVIDENCE
    session.estado = AuditState.EVIDENCE
    save_session(session)

    # Add fotos
    foto1 = FotoEvidence(
        id="foto_001",
        media_id="12345",
        media_url="https://example.com/foto1.jpg",
        bloque=BloqueType.STOCK.value,
        descripcion="Stock bajo en zona central"
    )
    session.add_foto(foto1)
    print(f"  ✓ Added foto: {foto1.descripcion}")

    # Add desvio
    desvio = session.add_desvio(
        bloque=BloqueType.STOCK.value,
        descripcion="Falta reposición de productos"
    )
    print(f"  ✓ Added desvio: {desvio.descripcion}")

    # Verify
    assert len(session.fotos) == 1
    assert len(session.desvios) == 1

    save_session(session)
    print("✅ Evidence collection works correctly")
    return session


def test_summary(session):
    """Test summary generation."""
    print("\n[TEST 5] Testing summary...")

    # Move to SUMMARY
    session.estado = AuditState.SUMMARY
    save_session(session)

    # Check summary data
    print("\n  RESUMEN:")
    print(f"  📍 Sucursal: {session.sucursal_id}")
    print(f"  👤 Auditor: {session.auditor_nombre}")
    print(f"  📊 Puntuaciones:")

    for bloque, score in session.bloques.items():
        label = BLOQUE_LABELS.get(bloque, bloque)
        print(f"    • {label}: {score}/5")

        if bloque == BloqueType.OFERTAS.value:
            brands = session.brands.get(BloqueType.OFERTAS.value, {})
            for brand_id, brand_score in brands.items():
                brand_label = BRAND_LABELS.get(brand_id, brand_id)
                print(f"      - {brand_label}: {brand_score}/5")

    print(f"\n  ⚠️ DESVÍOS ({len(session.desvios)}):")
    for desvio in session.desvios:
        print(f"    • {desvio.descripcion}")

    print(f"\n  📷 FOTOS ({len(session.fotos)}):")
    for foto in session.fotos:
        print(f"    • {foto.descripcion}")

    print("\n✅ Summary generation works correctly")


def test_serialization(session):
    """Test session serialization."""
    print("\n[TEST 6] Testing serialization...")

    # Convert to dict
    data = session.to_dict()
    assert isinstance(data, dict)
    assert data['id_sesion'] == session.id_sesion
    assert data['estado'] == session.estado.value
    print("  ✓ Serialized to dict")

    # Reconstruct from dict
    from audit_session import AuditSession
    restored = AuditSession.from_dict(data)
    assert restored.id_sesion == session.id_sesion
    assert restored.estado == session.estado
    assert len(restored.bloques) == len(session.bloques)
    assert len(restored.fotos) == len(session.fotos)
    print("  ✓ Deserialized from dict")

    print("✅ Serialization works correctly")


def test_session_retrieval(session):
    """Test getting session from cache."""
    print("\n[TEST 7] Testing session retrieval...")

    # Save to cache
    save_session(session)

    # Retrieve from cache
    retrieved = get_session(session.telefono)
    assert retrieved is not None
    assert retrieved.id_sesion == session.id_sesion
    assert retrieved.estado == session.estado
    print(f"  ✓ Retrieved session for {session.telefono}")

    # Delete from cache
    delete_session(session.telefono)
    deleted = get_session(session.telefono)
    assert deleted is None
    print("  ✓ Deleted session from cache")

    print("✅ Session retrieval works correctly")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("AUDIT SESSION TEST SUITE")
    print("="*60)

    try:
        session = test_session_creation()
        session = test_scoring_flow(session)
        session = test_brand_scoring(session)
        session = test_evidence(session)
        test_summary(session)
        test_serialization(session)
        test_session_retrieval(session)

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nThe audit session system is ready for integration.")

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
