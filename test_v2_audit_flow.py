"""End-to-end test for v2 perfumery audit flow."""

import asyncio
import sys

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from audit_session import (
    AuditSession, AuditState, create_session, get_session, save_session,
    delete_session, BloqueType, BLOQUE_ORDER, BRAND_ORDER, FotoEvidence
)
from audit_handlers import AuditConversationHandler
from models import WhatsAppPayload
from photo_validator import PhotoValidationResult


class MockMetaClient:
    """Mock Meta client for testing."""

    def __init__(self):
        self.sent_messages = []

    async def send_text(self, telefono: str, text: str) -> dict:
        """Mock send_text that records messages."""
        self.sent_messages.append({
            'telefono': telefono,
            'text': text,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        return {'status': 'ok'}

    async def send_list_message(self, telefono, header, body, footer, button_text, options) -> dict:
        self.sent_messages.append({
            'telefono': telefono,
            'text': f"[LIST] {header}: {body}",
            'options': options,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        return {'status': 'ok'}

    async def send_quick_reply(self, telefono, body, buttons) -> dict:
        self.sent_messages.append({
            'telefono': telefono,
            'text': f"[BUTTONS] {body}",
            'buttons': buttons,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        return {'status': 'ok'}

    async def download_media_with_metadata(self, media_id: str):
        """Mock media download — la validacion real de la foto se mockea por
        separado (ver PhotoValidator.validate_media_bytes en los tests que la
        usan), asi que los bytes devueltos acá nunca se inspeccionan."""
        return b"fake-image-bytes", "image/jpeg"


async def test_complete_audit_flow():
    """Test complete audit flow from start to finish."""

    print("\n" + "="*60)
    print("TEST: Complete v2 Audit Flow")
    print("="*60)

    telefono = "+5491234567890"
    sucursal_id = "SC-001"

    # Clean up any previous session
    delete_session(telefono)

    meta_client = MockMetaClient()

    # Step 1: Initialize audit
    print("\n[1] Initializing audit with sucursal_id...")
    payload = WhatsAppPayload(
        telefono=telefono,
        tipo="text",
        contenido=sucursal_id,
        media_id=None,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    result = await AuditConversationHandler.handle_init(payload, meta_client)
    print(f"    Result: {result}")
    assert result == "audit_started", f"Expected 'audit_started', got '{result}'"

    # Verify session was created
    session = get_session(telefono)
    assert session is not None, "Session should be created"
    assert session.estado == AuditState.SCORING, f"Should be in SCORING state, got {session.estado}"
    print(f"    Session created: {session.id_sesion}")
    print(f"    Current bloque: {session.get_current_bloque()}")

    # Step 2: Score each bloque
    print("\n[2] Scoring bloques...")
    for i, bloque in enumerate(BLOQUE_ORDER):
        print(f"    [{i+1}/4] Scoring {bloque}...")

        score = 4  # Score all bloques as 4
        payload = WhatsAppPayload(
            telefono=telefono,
            tipo="text",
            contenido=str(score),
            media_id=None,
            media_url=None,
            context_message_id=None,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        if bloque == BloqueType.OFERTAS.value:
            # For OFERTAS, we expect handle_score to return and move to SCORING_BRANDS
            result = await AuditConversationHandler.handle_score(payload, meta_client, session)
            print(f"        Score received, moved to per-brand evidence")
            assert result == "moved_to_brand_evidence", f"Expected moved_to_brand_evidence, got {result}"
            assert session.estado == AuditState.SCORING_BRANDS

            # Report a known brand + a brand not in BRAND_ORDER, foto -> tag -> comentario
            marcas_a_reportar = [BRAND_ORDER[0], "Marca No Contemplada"]
            with patch(
                "photo_validator.PhotoValidator.validate_media_bytes",
                return_value=PhotoValidationResult(is_valid=True, message="ok"),
            ):
                for marca_idx, marca in enumerate(marcas_a_reportar):
                    print(f"            [{marca_idx+1}/{len(marcas_a_reportar)}] Reportando marca {marca}...")

                    foto_payload = WhatsAppPayload(
                        telefono=telefono, tipo="image", contenido="",
                        media_id=f"media_marca_{marca_idx}", media_url=None,
                        context_message_id=None, timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    foto_result = await AuditConversationHandler.handle_ofertas_marca_evidence(
                        foto_payload, meta_client, session
                    )
                    assert foto_result == "photo_received_awaiting_marca", \
                        f"Expected photo_received_awaiting_marca, got {foto_result}"
                    assert session.estado == AuditState.SCORING_BRANDS_TAG

                    tag_payload = WhatsAppPayload(
                        telefono=telefono, tipo="text", contenido=marca,
                        media_id=None, media_url=None,
                        context_message_id=None, timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    tag_result = await AuditConversationHandler.handle_ofertas_marca_tag(
                        tag_payload, meta_client, session
                    )
                    assert tag_result == "marca_tagged", f"Expected marca_tagged, got {tag_result}"
                    assert session.estado == AuditState.SCORING_BRANDS_COMMENT

                    comment_payload = WhatsAppPayload(
                        telefono=telefono, tipo="text", contenido="Buena exhibición, sin observaciones.",
                        media_id=None, media_url=None,
                        context_message_id=None, timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    comment_result = await AuditConversationHandler.handle_ofertas_marca_comment(
                        comment_payload, meta_client, session
                    )
                    assert comment_result == "marca_comment_saved", \
                        f"Expected marca_comment_saved, got {comment_result}"
                    assert session.estado == AuditState.SCORING_BRANDS

            marcas_guardadas = {
                d.marca for d in session.desvios if d.bloque == BloqueType.OFERTAS.value and d.marca
            }
            assert marcas_guardadas == set(marcas_a_reportar), \
                f"Expected {marcas_a_reportar}, got {marcas_guardadas}"
        else:
            result = await AuditConversationHandler.handle_score(payload, meta_client, session)
            print(f"        Score received, transitioned to evidence collection")
            assert result == "score_saved", f"Expected score_saved, got {result}"
            assert session.estado == AuditState.BLOQUE_EVIDENCE_COLLECTION

        # If not the last bloque, send SIGUIENTE to move to next
        if i < len(BLOQUE_ORDER) - 1:
            siguiente_payload = WhatsAppPayload(
                telefono=telefono,
                tipo="text",
                contenido="SIGUIENTE",
                media_id=None,
                media_url=None,
                context_message_id=None,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

            if bloque == BloqueType.OFERTAS.value:
                # OFERTAS ya tiene fotos (una por marca reportada arriba) —
                # no hace falta agregar una foto generica antes de avanzar.
                result = await AuditConversationHandler.handle_ofertas_marca_evidence(
                    siguiente_payload, meta_client, session
                )
            else:
                # Photo is mandatory per bloque: add one before advancing
                session.add_foto(FotoEvidence(
                    id=f"foto_test_{bloque.lower()}",
                    media_id=f"media_test_{bloque.lower()}",
                    bloque=bloque,
                    validated=True,
                ))
                save_session(session)

                result = await AuditConversationHandler.handle_bloque_evidence(
                    siguiente_payload, meta_client, session
                )
            print(f"        SIGUIENTE sent, moved to next bloque")
            assert result == "next_bloque", f"Expected next_bloque, got {result}"

    # Verify session state before confirmation
    session = get_session(telefono)
    print(f"\n[3] Pre-confirmation check:")
    print(f"    Estado: {session.estado}")
    print(f"    Bloques scored: {session.bloques}")
    print(f"    Desvios: {len(session.desvios)}")
    print(f"    Fotos: {len(session.fotos)}")

    # Step 3: Confirm and save
    print("\n[4] Confirming audit...")
    confirm_payload = WhatsAppPayload(
        telefono=telefono,
        tipo="text",
        contenido="1",  # Answer "1" for yes
        media_id=None,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    result = await AuditConversationHandler.handle_confirmation(confirm_payload, meta_client, session)
    print(f"    Result: {result}")

    # Verify audit is marked as done
    session = get_session(telefono)
    assert session.estado == AuditState.DONE, f"Session should be DONE, got {session.estado}"

    print("\n[SUCCESS] Complete audit flow test passed!")
    print(f"\nAudit summary:")
    print(f"  ID: {session.id_sesion}")
    print(f"  Sucursal: {session.sucursal_id}")
    print(f"  Bloques scored: {len(session.bloques)}/{len(BLOQUE_ORDER)}")
    print(f"  Desvios found: {len(session.desvios)}")
    print(f"  Fotos collected: {len(session.fotos)}")
    print(f"  Estado final: {session.estado.value}")

    # Cleanup
    delete_session(telefono)
    print("\n[OK] Session cleaned up")

    return True


async def test_evidence_collection():
    """Test evidence collection (photos, texts, audio)."""

    print("\n" + "="*60)
    print("TEST: Evidence Collection")
    print("="*60)

    telefono = "+5491234567891"
    delete_session(telefono)
    meta_client = MockMetaClient()

    # Create and initialize session
    print("\n[1] Initializing session...")
    session = create_session(
        telefono=telefono,
        sucursal_id="SC-002",
        auditor_nombre="Test Auditor"
    )
    session.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION
    session.bloques["LIMPIEZA"] = 3
    save_session(session)
    print(f"    Session created: {session.id_sesion}")

    # Test text note
    print("\n[2] Adding text note...")
    text_payload = WhatsAppPayload(
        telefono=telefono,
        tipo="text",
        contenido="Gondola en malas condiciones",
        media_id=None,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    result = await AuditConversationHandler.handle_bloque_evidence(text_payload, meta_client, session)
    print(f"    Result: {result}")

    session = get_session(telefono)
    assert len(session.desvios) == 1, "Should have 1 desvio"
    assert session.desvios[0].descripcion == "Gondola en malas condiciones"
    print(f"    Desvio saved: {session.desvios[0].descripcion}")

    # Test audio
    print("\n[3] Adding audio...")
    audio_payload = WhatsAppPayload(
        telefono=telefono,
        tipo="audio",
        contenido="Transcription test",
        media_id="media_12345",
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    result = await AuditConversationHandler.handle_bloque_evidence(audio_payload, meta_client, session)
    print(f"    Result: {result}")

    session = get_session(telefono)
    assert len(session.desvios) == 2, "Should have 2 desvios"
    assert "[AUDIO]" in session.desvios[-1].descripcion
    print(f"    Audio saved: {session.desvios[-1].descripcion[:50]}...")

    # Test SIGUIENTE without photo → must be blocked (photo is mandatory)
    print("\n[4] Testing SIGUIENTE keyword...")
    siguiente_payload = WhatsAppPayload(
        telefono=telefono,
        tipo="text",
        contenido="SIGUIENTE",
        media_id=None,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    result = await AuditConversationHandler.handle_bloque_evidence(siguiente_payload, meta_client, session)
    print(f"    Result (sin foto): {result}")
    assert result == "photo_required", f"Expected photo_required, got {result}"

    # Add mandatory photo and retry SIGUIENTE
    session = get_session(telefono)
    session.add_foto(FotoEvidence(
        id="foto_test_limpieza",
        media_id="media_test_limpieza",
        bloque="LIMPIEZA",
        validated=True,
    ))
    save_session(session)

    result = await AuditConversationHandler.handle_bloque_evidence(siguiente_payload, meta_client, session)
    print(f"    Result (con foto): {result}")
    assert result == "next_bloque", f"Expected next_bloque, got {result}"

    session = get_session(telefono)
    assert session.estado == AuditState.SCORING, "Should be back in SCORING"
    assert session.current_bloque_index == 1, "Should have moved to next bloque"
    print(f"    Moved to next bloque: {session.get_current_bloque()}")

    delete_session(telefono)
    print("\n[SUCCESS] Evidence collection test passed!")

    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("WhatsApp Audit v2 - End-to-End Tests")
    print("="*60)

    try:
        # Note: Full flow test skipped because save_audit_to_database requires DB
        # await test_complete_audit_flow()

        # Run evidence collection test
        await test_evidence_collection()

        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
        return True

    except AssertionError as e:
        print(f"\n[FAILED] {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
