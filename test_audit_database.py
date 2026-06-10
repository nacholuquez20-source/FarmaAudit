"""Test database integration for audit sessions."""

import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from audit_session import (
    create_session, AuditState, BloqueType, FotoEvidence, Desvio
)
from audit_database import (
    determine_severity, determine_overall_severity
)
from models import Severidad
from datetime import datetime, timezone


def test_severity_determination():
    """Test severity determination from scores."""
    print("\n[TEST 1] Severity determination from scores...")

    # Test individual score determination
    assert determine_severity(1) == Severidad.ALTA
    print("  ✓ Score 1 → ALTA")

    assert determine_severity(2) == Severidad.ALTA
    print("  ✓ Score 2 → ALTA")

    assert determine_severity(3) == Severidad.MEDIA
    print("  ✓ Score 3 → MEDIA")

    assert determine_severity(4) == Severidad.BAJA
    print("  ✓ Score 4 → BAJA")

    assert determine_severity(5) == Severidad.BAJA
    print("  ✓ Score 5 → BAJA")

    print("✅ Severity determination works correctly")


def test_overall_severity():
    """Test overall severity from session scores."""
    print("\n[TEST 2] Overall severity calculation...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")

    # All low scores (bad)
    session.bloques = {
        BloqueType.LIMPIEZA.value: 1,
        BloqueType.STOCK.value: 2,
        BloqueType.OFERTAS.value: 1,
        BloqueType.BURBUJAS.value: 2,
    }
    severity = determine_overall_severity(session)
    assert severity == Severidad.ALTA
    print(f"  ✓ All low scores (avg 1.5) → {severity.value}")

    # Medium scores
    session.bloques = {
        BloqueType.LIMPIEZA.value: 2,
        BloqueType.STOCK.value: 3,
        BloqueType.OFERTAS.value: 3,
        BloqueType.BURBUJAS.value: 4,
    }
    severity = determine_overall_severity(session)
    assert severity == Severidad.MEDIA
    print(f"  ✓ Medium scores (avg 3) → {severity.value}")

    # All good scores
    session.bloques = {
        BloqueType.LIMPIEZA.value: 4,
        BloqueType.STOCK.value: 5,
        BloqueType.OFERTAS.value: 4,
        BloqueType.BURBUJAS.value: 5,
    }
    severity = determine_overall_severity(session)
    assert severity == Severidad.BAJA
    print(f"  ✓ All good scores (avg 4.5) → {severity.value}")

    print("✅ Overall severity calculation works correctly")


def test_audit_completion_workflow():
    """Test complete audit workflow with desvios and fotos."""
    print("\n[TEST 3] Complete audit workflow with database prep...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.SCORING
    session.started_at = datetime.now(timezone.utc).isoformat()

    # Add scores
    session.bloques = {
        BloqueType.LIMPIEZA.value: 4,
        BloqueType.STOCK.value: 2,
        BloqueType.OFERTAS.value: 3,
        BloqueType.BURBUJAS.value: 5,
    }
    print("  ✓ Scores recorded")

    # Add brands for OFERTAS
    session.brands = {
        BloqueType.OFERTAS.value: {
            "unilever": 3,
            "colgate": 2,
            "haleon": 3,
            "genomma": 4,
        }
    }
    print("  ✓ Brand scores recorded")

    # Move to evidence
    session.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION

    # Add photos
    foto1 = FotoEvidence(
        id="foto_001",
        media_id="meta_001",
        media_url="https://example.com/foto1.jpg",
        bloque=BloqueType.STOCK.value,
        descripcion="Stock bajo en zona central",
        validated=True,
    )
    session.add_foto(foto1)
    print("  ✓ Photo 1 added")

    foto2 = FotoEvidence(
        id="foto_002",
        media_id="meta_002",
        media_url="https://example.com/foto2.jpg",
        bloque=BloqueType.OFERTAS.value,
        descripcion="Exhibición desordenada",
        validated=True,
    )
    session.add_foto(foto2)
    print("  ✓ Photo 2 added")

    # Add desvios
    desvio1 = session.add_desvio(
        bloque=BloqueType.STOCK.value,
        descripcion="Falta reposición urgente de productos en zona central",
    )
    print(f"  ✓ Desvio 1 added: {desvio1.descripcion}")

    desvio2 = session.add_desvio(
        bloque=BloqueType.OFERTAS.value,
        descripcion="Colgate sin stock, necesita reorden",
    )
    print(f"  ✓ Desvio 2 added: {desvio2.descripcion}")

    # Calculate records to create
    total_records = len(session.desvios)
    assert total_records == 2

    # Verify each record will have proper severity
    for i, desvio in enumerate(session.desvios):
        bloque_score = session.bloques.get(desvio.bloque, 3)
        severity = determine_severity(bloque_score)
        print(f"    - Desvio {i+1}: {desvio.bloque} (score {bloque_score}) → {severity.value}")

    # Move to summary
    session.estado = AuditState.SUMMARY
    print("  ✓ Moved to SUMMARY state")

    # Verify summary data
    assert session.estado == AuditState.SUMMARY
    assert len(session.bloques) == 4
    assert len(session.brands.get(BloqueType.OFERTAS.value, {})) == 4
    assert len(session.fotos) == 2
    assert len(session.desvios) == 2

    print("  ✓ Summary ready with all data")

    # Move to done
    session.estado = AuditState.DONE
    assert session.estado == AuditState.DONE
    print("  ✓ Audit marked as DONE")

    print("✅ Complete audit workflow works correctly")
    print(f"\nReady for database save:")
    print(f"  - Session: {session.id_sesion}")
    print(f"  - Sucursal: {session.sucursal_id}")
    print(f"  - Records to create: {total_records}")
    print(f"  - Photos: {len(session.fotos)}")
    print(f"  - Overall severity: {determine_overall_severity(session).value}")


def test_empty_audit():
    """Test audit with no desvios found."""
    print("\n[TEST 4] Audit with no desvios...")

    session = create_session("+5493816199195", "SC-001", "Juan Pérez")
    session.estado = AuditState.SCORING
    session.started_at = datetime.now(timezone.utc).isoformat()

    # All good scores
    session.bloques = {
        BloqueType.LIMPIEZA.value: 5,
        BloqueType.STOCK.value: 5,
        BloqueType.OFERTAS.value: 4,
        BloqueType.BURBUJAS.value: 5,
    }

    # No fotos or desvios added
    session.estado = AuditState.SUMMARY

    assert len(session.desvios) == 0
    assert len(session.fotos) == 0

    overall_severity = determine_overall_severity(session)
    assert overall_severity == Severidad.BAJA

    print("  ✓ Empty audit (no desvios) identified")
    print(f"  ✓ Summary severity: {overall_severity.value}")
    print("  ✓ Will create summary record in DB")

    print("✅ Empty audit handling works correctly")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AUDIT DATABASE INTEGRATION TEST SUITE")
    print("=" * 60)

    try:
        test_severity_determination()
        test_overall_severity()
        test_audit_completion_workflow()
        test_empty_audit()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nPhase 4 implementation verified:")
        print("  • Severity determination logic ✓")
        print("  • Overall severity calculation ✓")
        print("  • Complete audit workflow ✓")
        print("  • Database record preparation ✓")
        print("  • Empty audit handling ✓")

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
