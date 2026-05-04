import json

from models import RespuestaPregunta, RespuestaPreguntaEstado
from router import ConversationRouter


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
