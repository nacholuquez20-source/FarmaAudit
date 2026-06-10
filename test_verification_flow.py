"""Tests for in-floor verification of previous desvíos (VERIFY_PREVIOUS state)."""

import asyncio
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from audit_session import (
    AuditSession, AuditState, create_session, get_session, save_session,
    delete_session,
)
from audit_handlers import AuditConversationHandler
from models import WhatsAppPayload


class MockMetaClient:
    def __init__(self):
        self.texts = []
        self.lists = []
        self.quick_replies = []

    async def send_text(self, telefono, text):
        self.texts.append(text)
        return True

    async def send_list_message(self, telefono, header, body, footer, button_text, options):
        self.lists.append({"header": header, "body": body, "options": options})
        return True

    async def send_quick_reply(self, telefono, body, buttons):
        self.quick_replies.append({"body": body, "buttons": buttons})
        return True

    async def download_media_with_metadata(self, media_id):
        return b"fakebytes", "image/jpeg"


def make_payload(telefono, tipo="text", contenido="", media_id=None):
    return WhatsAppPayload(
        telefono=telefono,
        tipo=tipo,
        contenido=contenido,
        media_id=media_id,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def make_db_mock(pendientes=None):
    db = MagicMock()
    db.get_gestiones_pendientes_bloque.return_value = pendientes if pendientes is not None else []
    db.upload_desvio_evidencia.return_value = {
        "path": "gestion/g1/whatsapp-x.jpg",
        "thumb_path": "gestion/g1/whatsapp-x-thumb.jpg",
        "bucket": "desvio-evidencias",
    }
    db.create_signed_evidencia_url.return_value = "https://signed.example/x.jpg"
    db.update_gestion_fields.return_value = True
    return db


def pendientes_fixture():
    return [
        {"id_gestion": "g1", "desvio": "Góndolas desorganizadas", "severidad": "Media",
         "estado": "Abierta", "plazo_fecha": "2026-06-15"},
        {"id_gestion": "g2", "desvio": "Productos vencidos", "severidad": "Baja",
         "estado": "Vencida", "plazo_fecha": "2026-06-01"},
    ]


def make_verifying_session(telefono, pendientes):
    """Session already in VERIFY_PREVIOUS with a loaded queue."""
    delete_session(telefono)
    session = create_session(telefono, "SC-001", "Test Auditor")
    session.estado = AuditState.VERIFY_PREVIOUS
    session.pending_verifications = [
        {"id_gestion": g["id_gestion"], "desvio": g["desvio"], "severidad": g["severidad"],
         "estado": g["estado"], "plazo_fecha": g["plazo_fecha"]}
        for g in pendientes
    ]
    session.current_verification_index = 0
    save_session(session)
    return session


async def test_enter_bloque_sin_pendientes():
    """Without pending gestiones the flow goes straight to SCORING (regression)."""
    telefono = "+5491100000001"
    delete_session(telefono)
    session = create_session(telefono, "SC-001", "Test Auditor")
    meta = MockMetaClient()

    with patch("audit_handlers.SupabaseManager", return_value=make_db_mock([])):
        result = await AuditConversationHandler.enter_bloque(meta, session)

    assert result == "scoring_started", f"Expected scoring_started, got {result}"
    assert session.estado == AuditState.SCORING
    assert len(meta.lists) == 1, "Scoring list message should be sent"
    assert "Paso 1 de 4" in meta.lists[0]["header"]
    delete_session(telefono)


async def test_enter_bloque_con_pendientes():
    """With pending gestiones the flow enters VERIFY_PREVIOUS and sends buttons."""
    telefono = "+5491100000002"
    delete_session(telefono)
    session = create_session(telefono, "SC-001", "Test Auditor")
    meta = MockMetaClient()

    with patch("audit_handlers.SupabaseManager", return_value=make_db_mock(pendientes_fixture())):
        result = await AuditConversationHandler.enter_bloque(meta, session)

    assert result == "verification_started", f"Expected verification_started, got {result}"
    assert session.estado == AuditState.VERIFY_PREVIOUS
    assert len(session.pending_verifications) == 2
    assert len(meta.quick_replies) == 1
    buttons = [b["id"] for b in meta.quick_replies[0]["buttons"]]
    assert buttons == ["verif_resuelto", "verif_persiste", "verif_omitir"]
    assert "1/2" in meta.quick_replies[0]["body"]
    delete_session(telefono)


async def test_resuelto_con_foto():
    """Resuelto + valid photo: upload, evento verificacion_auditoria, estado Resuelta."""
    telefono = "+5491100000003"
    session = make_verifying_session(telefono, pendientes_fixture())
    meta = MockMetaClient()
    db = make_db_mock()

    valid = MagicMock(is_valid=True, message="ok")
    with patch("audit_handlers.SupabaseManager", return_value=db), \
         patch("audit_handlers.PhotoValidator.validate_media_bytes", return_value=valid):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_resuelto"), meta, session
        )
        assert result == "verification_resuelto_awaiting_photo"
        assert session.awaiting_verification_photo is True

        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, tipo="image", media_id="m1"), meta, session
        )

    assert result == "next_verification", f"Expected next_verification, got {result}"
    db.upload_desvio_evidencia.assert_called_once()
    evento_kwargs = db.save_encargado_evento.call_args.kwargs
    assert evento_kwargs["tipo"] == "verificacion_auditoria"
    assert evento_kwargs["id_gestion"] == "g1"
    assert evento_kwargs["metadata"]["foto_path"] == "gestion/g1/whatsapp-x.jpg"
    db.update_gestion_fields.assert_called_once_with("g1", {"estado": "Resuelta"})
    assert session.verified_resueltos == 1
    assert session.current_verification_index == 1
    # Photo prompt (with "sin foto" button) + next verification card
    assert len(meta.quick_replies) == 2
    assert meta.quick_replies[0]["buttons"][0]["id"] == "verif_sin_foto"
    assert meta.quick_replies[-1]["buttons"][0]["id"] == "verif_resuelto"
    delete_session(telefono)


async def test_resuelto_sin_foto():
    """Resuelto + OMITIR: evento without evidence, estado Resuelta."""
    telefono = "+5491100000004"
    session = make_verifying_session(telefono, pendientes_fixture())
    session.awaiting_verification_photo = True
    save_session(session)
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="omitir"), meta, session
        )

    assert result == "next_verification"
    db.upload_desvio_evidencia.assert_not_called()
    evento_kwargs = db.save_encargado_evento.call_args.kwargs
    assert evento_kwargs["tipo"] == "verificacion_auditoria"
    assert "foto_path" not in evento_kwargs["metadata"]
    db.update_gestion_fields.assert_called_once_with("g1", {"estado": "Resuelta"})
    delete_session(telefono)


async def test_persiste_escala_severidad():
    """Persiste: evento reincidencia + severity escalated, estado untouched."""
    telefono = "+5491100000005"
    session = make_verifying_session(telefono, pendientes_fixture())
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_persiste"), meta, session
        )

    assert result == "next_verification"
    evento_kwargs = db.save_encargado_evento.call_args.kwargs
    assert evento_kwargs["tipo"] == "reincidencia"
    assert evento_kwargs["metadata"]["severidad_anterior"] == "Media"
    assert evento_kwargs["metadata"]["severidad_nueva"] == "Alta"
    db.update_gestion_fields.assert_called_once_with("g1", {"severidad": "Alta"})
    assert session.verified_persisten == 1
    delete_session(telefono)


async def test_omitir_sin_escrituras():
    """Omitir: zero DB writes, just advances."""
    telefono = "+5491100000006"
    session = make_verifying_session(telefono, pendientes_fixture())
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_omitir"), meta, session
        )

    assert result == "next_verification"
    db.save_encargado_evento.assert_not_called()
    db.update_gestion_fields.assert_not_called()
    assert session.current_verification_index == 1
    delete_session(telefono)


async def test_cola_agotada_pasa_a_scoring():
    """When the queue is exhausted, flow transitions to SCORING with list message."""
    telefono = "+5491100000007"
    session = make_verifying_session(telefono, pendientes_fixture()[:1])
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_omitir"), meta, session
        )

    assert result == "scoring_started", f"Expected scoring_started, got {result}"
    assert session.estado == AuditState.SCORING
    assert session.pending_verifications == []
    assert len(meta.lists) == 1, "Scoring list message should be sent"
    assert any("Verificación completada" in t for t in meta.texts)
    delete_session(telefono)


async def test_serializacion_round_trip():
    """to_dict/from_dict preserves the new verification fields."""
    telefono = "+5491100000008"
    session = make_verifying_session(telefono, pendientes_fixture())
    session.awaiting_verification_photo = True
    session.verified_resueltos = 1
    session.verified_persisten = 2

    data = session.to_dict()
    restored = AuditSession.from_dict(data)

    assert restored.estado == AuditState.VERIFY_PREVIOUS
    assert restored.pending_verifications == session.pending_verifications
    assert restored.current_verification_index == 0
    assert restored.awaiting_verification_photo is True
    assert restored.verified_resueltos == 1
    assert restored.verified_persisten == 2
    delete_session(telefono)


async def test_error_db_no_bloquea():
    """A Supabase failure must not block the audit: warn and advance."""
    telefono = "+5491100000009"
    session = make_verifying_session(telefono, pendientes_fixture())
    meta = MockMetaClient()
    db = make_db_mock()
    db.save_encargado_evento.side_effect = Exception("supabase down")

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_persiste"), meta, session
        )

    assert result == "next_verification", f"Expected next_verification, got {result}"
    assert session.verified_persisten == 0
    assert session.current_verification_index == 1
    assert any("No pude registrar" in t for t in meta.texts)
    delete_session(telefono)


async def test_input_invalido():
    """Unexpected input during verification re-prompts the buttons."""
    telefono = "+5491100000010"
    session = make_verifying_session(telefono, pendientes_fixture())
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="hola que tal"), meta, session
        )

    assert result == "verification_invalid_input"
    assert session.current_verification_index == 0
    delete_session(telefono)


async def test_desvio_management_sin_activos():
    """'desvios' command with no active desvíos anywhere: friendly message, no session."""
    telefono = "+5491100000020"
    delete_session(telefono)
    meta = MockMetaClient()
    db = make_db_mock()
    db.get_sucursales_con_pendientes.return_value = []

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.start_desvio_management(
            make_payload(telefono, contenido="desvios"), meta, "Test Auditor"
        )

    assert result == "no_active_desvios"
    assert get_session(telefono) is None
    assert any("No hay desvíos activos" in t for t in meta.texts)


async def test_desvio_management_menu_y_seleccion():
    """'desvios' shows sucursal menu; valid pick loads urgency-sorted queue."""
    telefono = "+5491100000021"
    delete_session(telefono)
    meta = MockMetaClient()
    db = make_db_mock()
    db.get_sucursales_con_pendientes.return_value = [
        {"id_sucursal": "SUC015", "sucursal": "Plazoleta Roca", "count": 3},
        {"id_sucursal": "SUC016", "sucursal": "Plazoleta San Martín", "count": 2},
    ]
    db.get_gestiones_pendientes_sucursal.return_value = [
        {"id_gestion": "g_baja", "desvio": "Detalle menor", "severidad": "Baja",
         "estado": "Abierta", "plazo_fecha": "2026-06-20", "bloque": "LIMPIEZA"},
        {"id_gestion": "g_vencida", "desvio": "Vencido viejo", "severidad": "Baja",
         "estado": "Vencida", "plazo_fecha": "2026-05-01", "bloque": None},
        {"id_gestion": "g_alta", "desvio": "Crítico", "severidad": "Alta",
         "estado": "Abierta", "plazo_fecha": "2026-06-25", "bloque": "STOCK"},
    ]

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.start_desvio_management(
            make_payload(telefono, contenido="desvios"), meta, "Test Auditor"
        )
        assert result == "desvio_management_menu_sent"
        session = get_session(telefono)
        assert session.estado == AuditState.VERIFY_SELECT_SUCURSAL
        assert session.verification_only is True
        # Menu is a native list message with row ids verif_suc_N
        assert len(meta.lists) == 1
        menu_options = meta.lists[-1]["options"]
        assert menu_options[0]["id"] == "verif_suc_1"
        assert menu_options[0]["title"] == "Plazoleta Roca"
        assert "3" in menu_options[0]["description"]

        # Invalid input re-prompts with the menu again
        result = await AuditConversationHandler.handle_verify_sucursal_selection(
            make_payload(telefono, contenido="99"), meta, session
        )
        assert result == "verify_sucursal_invalid_input"
        assert len(meta.lists) == 2

        # List reply id selects the sucursal
        result = await AuditConversationHandler.handle_verify_sucursal_selection(
            make_payload(telefono, contenido="verif_suc_1"), meta, session
        )

    assert result == "verification_started"
    assert session.estado == AuditState.VERIFY_PREVIOUS
    assert session.sucursal_id == "SUC015"
    orden = [v["id_gestion"] for v in session.pending_verifications]
    assert orden == ["g_vencida", "g_alta", "g_baja"], f"Urgency order wrong: {orden}"
    # First quick reply shows bloque line for standalone when available
    assert len(meta.quick_replies) == 1
    delete_session(telefono)


async def test_desvio_management_finaliza_sin_scoring():
    """Standalone queue exhausted: session deleted, no scoring list sent."""
    telefono = "+5491100000022"
    session = make_verifying_session(telefono, pendientes_fixture()[:1])
    session.verification_only = True
    save_session(session)
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="verif_persiste"), meta, session
        )

    assert result == "verification_management_done", f"Expected done, got {result}"
    assert get_session(telefono) is None
    assert len(meta.lists) == 0, "No scoring list in standalone mode"
    evento_kwargs = db.save_encargado_evento.call_args.kwargs
    assert evento_kwargs["metadata"]["origen"] == "gestion_desvios_wsp"


async def test_desvio_management_cancelar():
    """'cancelar' during standalone verification deletes the session."""
    telefono = "+5491100000023"
    session = make_verifying_session(telefono, pendientes_fixture())
    session.verification_only = True
    save_session(session)
    meta = MockMetaClient()
    db = make_db_mock()

    with patch("audit_handlers.SupabaseManager", return_value=db):
        result = await AuditConversationHandler.handle_verification(
            make_payload(telefono, contenido="cancelar"), meta, session
        )

    assert result == "desvio_management_cancelled"
    assert get_session(telefono) is None
    db.save_encargado_evento.assert_not_called()


TESTS = [
    test_enter_bloque_sin_pendientes,
    test_enter_bloque_con_pendientes,
    test_resuelto_con_foto,
    test_resuelto_sin_foto,
    test_persiste_escala_severidad,
    test_omitir_sin_escrituras,
    test_cola_agotada_pasa_a_scoring,
    test_serializacion_round_trip,
    test_error_db_no_bloquea,
    test_input_invalido,
    test_desvio_management_sin_activos,
    test_desvio_management_menu_y_seleccion,
    test_desvio_management_finaliza_sin_scoring,
    test_desvio_management_cancelar,
]


async def main():
    print("=" * 60)
    print("Verification Flow (Cierre en piso) - Tests")
    print("=" * 60)
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            await test()
            print(f"[PASS] {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"[ERROR] {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
