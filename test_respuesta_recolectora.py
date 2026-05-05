import json
import asyncio
from datetime import date

from models import (
    ConversationState,
    Gestion,
    GestionState,
    RespuestaPregunta,
    RespuestaPreguntaEstado,
    SesionAuditoria,
    Severidad,
    WhatsAppPayload,
)
from router import ConversationRouter
from supabase_manager import SupabaseManager


class _FakeTable:
    def __init__(self, calls, name):
        self.calls = calls
        self.name = name

    def insert(self, payload):
        self.calls.append((self.name, payload))
        return self

    def execute(self):
        return None


class _FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return _FakeTable(self.calls, name)


class _FailingCollectorSheets:
    def create_respuesta_pregunta(self, respuesta):
        raise RuntimeError("missing respuesta_pregunta")


class _FakeMetaClient:
    def __init__(self):
        self.messages = []

    async def send_text(self, phone, text):
        self.messages.append((phone, text))


def test_respuesta_pregunta_deserializes_messages():
    respuesta = RespuestaPregunta(
        id="resp-1",
        id_sesion="ses-1",
        telefono_auditor="5491111111111",
        pregunta_numero=1,
        bloque_id="PRES",
        estado=RespuestaPreguntaEstado.RECOLECTANDO,
        timestamp_inicio="2026-05-04T12:00:00+00:00",
        timestamp_ultimo_mensaje="2026-05-04T12:00:10+00:00",
        mensajes_json=json.dumps([
            {"tipo": "text", "contenido": "Vidriera desordenada", "media_ids": []},
            {"tipo": "image", "contenido": "[Foto recibida]", "media_ids": [{"url": "https://example.test/foto.jpg"}]},
        ]),
    )

    mensajes = respuesta.get_mensajes()

    assert len(mensajes) == 2
    assert mensajes[0].tipo == "text"
    assert mensajes[1].media_ids[0]["url"].endswith("foto.jpg")


def test_respuesta_pregunta_accepts_supabase_user_id_column():
    respuesta = RespuestaPregunta(**{
        "id": "resp-1",
        "id_sesion": "ses-1",
        "telefono_auditor": "5491111111111",
        "user_id_auditor": None,
        "pregunta_numero": 1,
        "bloque_id": "ATENCION",
        "estado": "recolectando",
        "timestamp_inicio": "2026-05-04T12:00:00+00:00",
        "timestamp_ultimo_mensaje": "2026-05-04T12:00:10+00:00",
    })

    assert respuesta.user_id_auditor is None


def test_whatsapp_payload_keeps_reply_context_id():
    payload = WhatsAppPayload(
        telefono="5491111111111",
        tipo="text",
        contenido="aclaracion sobre este bloque",
        message_id="wamid.inbound",
        context_message_id="wamid.bot-block",
    )

    assert payload.context_message_id == "wamid.bot-block"


def test_create_gestion_writes_to_frontend_table():
    manager = object.__new__(SupabaseManager)
    manager.client = _FakeClient()

    manager.create_gestion(Gestion(
        id_gestion="",
        id_reporte="rep-1",
        id_sucursal="suc-1",
        sucursal="Sucursal Centro",
        desvio="Vidriera desordenada",
        severidad=Severidad.MEDIA,
        responsable="Encargado",
        tel_responsable="5491111111111",
        plazo_fecha=date(2026, 5, 11),
        plan_accion="",
        estado=GestionState.ABIERTA,
    ))

    assert manager.client.calls[0][0] == "gestion"


def test_validate_respuesta_rejects_short_text():
    router = ConversationRouter.__new__(ConversationRouter)

    result = router._validate_respuesta_completitud(
        bloque_id="PRES",
        respuesta_consolidada="ok",
        media_urls=[],
        mensajes=[],
    )

    assert result["es_valida"] is False
    assert "corta" in result["razon"]


def test_validate_respuesta_requires_photo_for_gondola():
    router = ConversationRouter.__new__(ConversationRouter)

    result = router._validate_respuesta_completitud(
        bloque_id="GOND",
        respuesta_consolidada="Gondola con faltantes visibles y desorden.",
        media_urls=[],
        mensajes=[],
    )

    assert result["es_valida"] is False
    assert "foto" in result["razon"].lower()


def test_validate_respuesta_accepts_positive_no_deviation_without_photo():
    router = ConversationRouter.__new__(ConversationRouter)

    result = router._validate_respuesta_completitud(
        bloque_id="GOND",
        respuesta_consolidada="Todo ok, sin desvio.",
        media_urls=[],
        mensajes=[],
    )

    assert result["es_valida"] is True


def test_respuesta_summary_counts_media_and_text():
    summary = ConversationRouter._format_respuesta_collection_summary(
        mensajes=[
            {"tipo": "text", "contenido": "Gondola con faltantes", "media_ids": []},
            {"tipo": "audio", "contenido": "[Audio recibido]", "media_ids": [{"tipo": "audio", "url": "signed"}]},
            {"tipo": "image", "contenido": "[Foto recibida]", "media_ids": [{"tipo": "image", "url": "signed"}]},
        ],
        respuesta_consolidada="Gondola con faltantes",
    )

    assert "Mensajes de texto: 1" in summary
    assert "1 audio(s)" in summary
    assert "1 foto(s)" in summary


def test_collector_failure_does_not_fall_back_to_legacy():
    router = ConversationRouter.__new__(ConversationRouter)
    router.sheets = _FailingCollectorSheets()
    meta = _FakeMetaClient()

    handled = asyncio.run(router._try_start_respuesta_collection(
        WhatsAppPayload(telefono="5491111111111", tipo="text", contenido="respuesta"),
        SesionAuditoria(
            id_sesion="ses-1",
            telefono_auditor="5491111111111",
            sucursal_id="suc-1",
            estado=ConversationState.EN_BLOQUE_PERFUMERIA.value,
            timestamp_inicio="2026-05-04T12:00:00+00:00",
            timestamp_ultimo_punto="2026-05-04T12:00:00+00:00",
        ),
        "ATENCION",
        ConversationState.EN_BLOQUE_PERFUMERIA,
        meta,
    ))

    assert handled is True
    assert "no voy a avanzar de bloque" in meta.messages[0][1]


def test_perfumeria_fallback_detects_clear_deviation():
    desvio = ConversationRouter._build_perfumeria_fallback_desvio(
        "GONDOLAS",
        "Las gondolas estan desordenadas con poca variedad de productos",
    )

    assert desvio is not None
    assert desvio["severidad"] == "Baja"
    assert "desordenadas" in desvio["desvio"]


def test_perfumeria_fallback_ignores_ok_response():
    desvio = ConversationRouter._build_perfumeria_fallback_desvio(
        "ATENCION",
        "todo ok, esta correcto",
    )

    assert desvio is None


def test_perfumeria_fallback_ignores_no_deviation_phrase():
    desvio = ConversationRouter._build_perfumeria_fallback_desvio(
        "ATENCION",
        "no hay desvio",
    )

    assert desvio is None


def test_human_finish_intent_accepts_natural_variants():
    assert ConversationRouter._is_finish_intent("ya terminé")
    assert ConversationRouter._is_finish_intent("pasemos al siguiente")
    assert ConversationRouter._is_finish_intent("nada más")


def test_human_cancel_intent_accepts_natural_variants():
    assert ConversationRouter._is_cancel_intent("me equivoqué")
    assert ConversationRouter._is_cancel_intent("borrar esto")


def test_first_collector_image_uses_image_path():
    media = ConversationRouter._first_collector_image([
        {"tipo": "audio", "path": "auditoria/ses/resp/audio.ogg", "mime_type": "audio/ogg"},
        {"tipo": "image", "path": "auditoria/ses/resp/foto.jpg", "mime_type": "image/jpeg"},
    ])

    assert media is not None
    assert media["path"].endswith("foto.jpg")
