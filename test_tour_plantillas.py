"""Plantillas reutilizables para los puntos "desde cero" del Tour de Farmacias
(etapa-34). El checklist clásico ya tenía identidad estable entre lanzamientos
via `campania_acciones.tipo`; el hueco real era el punto tipeado a mano, sin
ninguna relación con el mismo punto tipeado de nuevo el mes siguiente.

Cubre: ofrecer "Usar plantilla" solo si hay alguna guardada, cargar sus puntos
con `plantilla_punto_id` ya seteado, y ofrecer guardar puntos nuevos como
plantilla (una sola vez por lanzamiento, y solo si hay contenido nuevo).

Run directly: venv/Scripts/python.exe test_tour_plantillas.py
"""

import sys
import io as io_module

if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io_module.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
from unittest.mock import MagicMock

from models import ConversationState, Conversacion, WhatsAppPayload
from router import ConversationRouter, TOUR_ACCIONES_DEFAULT


def _make_router():
    router = ConversationRouter.__new__(ConversationRouter)
    router.sheets = MagicMock()
    return router


def _conv(context: dict) -> Conversacion:
    return Conversacion(
        telefono="+5491111111111",
        estado_actual=ConversationState.AUDITOR_CAMPANIA_AGREGANDO_ACCION,
        ultimo_mensaje=json.dumps(context),
    )


def _payload(texto: str) -> WhatsAppPayload:
    return WhatsAppPayload(telefono="+5491111111111", tipo="text", contenido=texto)


async def test_no_ofrece_plantilla_si_no_hay_ninguna_guardada():
    router = _make_router()
    router.sheets.get_tour_plantillas.return_value = []
    meta_client = MagicMock()
    meta_client.send_quick_reply = MagicMock(side_effect=_as_coro())

    # Se ejercita directo el armado de botones vía _handle_auditor_campania_nombre,
    # que es donde se decide si va o no "Usar plantilla".
    conv = Conversacion(
        telefono="+5491111111111",
        estado_actual=ConversationState.AUDITOR_CAMPANIA_NOMBRE,
        ultimo_mensaje=json.dumps({"flujo": "auditor_campania", "tipo": "tour_interno"}),
    )
    await router._handle_auditor_campania_nombre(_payload("Tour Enero"), conv, meta_client)

    _, kwargs = meta_client.send_quick_reply.call_args
    ids = {b["id"] for b in kwargs["buttons"]} if "buttons" in kwargs else {b["id"] for b in meta_client.send_quick_reply.call_args.args[-1]}
    assert "tour_plantilla" not in ids
    print("[OK] test_no_ofrece_plantilla_si_no_hay_ninguna_guardada")


async def test_ofrece_plantilla_si_hay_guardadas():
    router = _make_router()
    router.sheets.get_tour_plantillas.return_value = [{"id": "p1", "nombre": "Dermocosmética"}]
    meta_client = MagicMock()
    meta_client.send_quick_reply = MagicMock(side_effect=_as_coro())

    conv = Conversacion(
        telefono="+5491111111111",
        estado_actual=ConversationState.AUDITOR_CAMPANIA_NOMBRE,
        ultimo_mensaje=json.dumps({"flujo": "auditor_campania", "tipo": "tour_interno"}),
    )
    await router._handle_auditor_campania_nombre(_payload("Tour Enero"), conv, meta_client)

    args, kwargs = meta_client.send_quick_reply.call_args
    botones = kwargs.get("buttons") or args[-1]
    ids = {b["id"] for b in botones}
    assert "tour_plantilla" in ids
    print("[OK] test_ofrece_plantilla_si_hay_guardadas")


async def test_elegir_plantilla_carga_puntos_con_identidad_estable():
    router = _make_router()
    router.sheets.get_tour_plantilla_puntos.return_value = [
        {"id": "punto-1", "descripcion": "Góndolas de dermocosmética ordenadas"},
        {"id": "punto-2", "descripcion": "Exhibidor de protector solar completo"},
    ]
    meta_client = MagicMock()
    meta_client.send_text = MagicMock(side_effect=_as_coro())
    meta_client.send_quick_reply = MagicMock(side_effect=_as_coro())

    context = {
        "flujo": "auditor_campania", "tipo": "tour_interno", "nombre": "Tour Enero",
        "substep": "elegir_plantilla", "plantillas_opciones": {"1": "plantilla-dermo"},
    }
    conv = _conv(context)
    result = await router._handle_auditor_campania_agregando_accion(_payload("1"), conv, meta_client)

    router.sheets.get_tour_plantilla_puntos.assert_called_once_with("plantilla-dermo")
    _, kwargs = router.sheets.update_conversacion.call_args
    guardado = json.loads(kwargs["ultimo_mensaje"])
    acciones = guardado["acciones"]
    assert len(acciones) == 2
    assert all(a["tipo"] == "custom" for a in acciones)
    assert {a["plantilla_punto_id"] for a in acciones} == {"punto-1", "punto-2"}
    assert result == "auditor_campania_accion_guardada"
    print("[OK] test_elegir_plantilla_carga_puntos_con_identidad_estable")


async def test_no_pregunta_guardar_plantilla_si_solo_uso_checklist():
    """El checklist clásico ya tiene identidad estable (tipo=vidriera, etc.) — no
    hay nada nuevo que guardar, no debe preguntar."""
    router = _make_router()
    meta_client = MagicMock()
    meta_client.send_text = MagicMock(side_effect=_as_coro())
    meta_client.send_quick_reply = MagicMock(side_effect=_as_coro())
    meta_client.send_list_message = MagicMock(side_effect=_as_coro())

    context = {
        "flujo": "auditor_campania", "tipo": "tour_interno", "nombre": "Tour Enero",
        "substep": "otra",
        "acciones": [{"tipo": t, "descripcion": d, "imagen_referencia_path": None} for t, d in TOUR_ACCIONES_DEFAULT],
        "frio_preguntado": True,
    }
    conv = _conv(context)
    await router._handle_auditor_campania_agregando_accion(_payload("no"), conv, meta_client)

    meta_client.send_quick_reply.assert_not_called()
    _, kwargs = router.sheets.update_conversacion.call_args
    assert kwargs["estado"] == ConversationState.AUDITOR_CAMPANIA_ALCANCE
    print("[OK] test_no_pregunta_guardar_plantilla_si_solo_uso_checklist")


async def test_pregunta_guardar_plantilla_si_hay_puntos_nuevos():
    router = _make_router()
    meta_client = MagicMock()
    meta_client.send_quick_reply = MagicMock(side_effect=_as_coro())

    context = {
        "flujo": "auditor_campania", "tipo": "tour_interno", "nombre": "Tour Enero",
        "substep": "otra",
        "acciones": [{"tipo": "custom", "descripcion": "Punto nuevo a mano", "imagen_referencia_path": None}],
        "frio_preguntado": True,
    }
    conv = _conv(context)
    result = await router._handle_auditor_campania_agregando_accion(_payload("no"), conv, meta_client)

    assert result == "auditor_campania_preguntando_guardar_plantilla"
    meta_client.send_quick_reply.assert_called_once()
    print("[OK] test_pregunta_guardar_plantilla_si_hay_puntos_nuevos")


async def test_guardar_plantilla_linkea_id_al_tour_actual():
    """Guardar la plantilla no solo la deja disponible para el proximo tour: el
    punto del tour que se esta armando AHORA tambien queda con identidad estable,
    sin esperar a que se relance."""
    router = _make_router()
    router.sheets.create_tour_plantilla_bot.return_value = [
        {"id": "punto-nuevo-1", "descripcion": "Punto nuevo a mano"},
    ]
    meta_client = MagicMock()
    meta_client.send_text = MagicMock(side_effect=_as_coro())
    meta_client.send_list_message = MagicMock(side_effect=_as_coro())

    context = {
        "flujo": "auditor_campania", "tipo": "tour_interno", "nombre": "Tour Enero",
        "substep": "nombre_plantilla",
        "acciones": [{"tipo": "custom", "descripcion": "Punto nuevo a mano", "imagen_referencia_path": None}],
    }
    conv = _conv(context)
    await router._handle_auditor_campania_agregando_accion(_payload("Plantilla Enero"), conv, meta_client)

    router.sheets.create_tour_plantilla_bot.assert_called_once_with(
        "Plantilla Enero", ["Punto nuevo a mano"], "+5491111111111"
    )
    # El ultimo update_conversacion (el de _pedir_alcance_campania) ya debe llevar
    # el plantilla_punto_id linkeado al punto que se acaba de guardar.
    _, kwargs = router.sheets.update_conversacion.call_args
    guardado = json.loads(kwargs["ultimo_mensaje"])
    assert guardado["acciones"][0]["plantilla_punto_id"] == "punto-nuevo-1"
    print("[OK] test_guardar_plantilla_linkea_id_al_tour_actual")


def _as_coro():
    async def _inner(*args, **kwargs):
        return True
    return _inner


if __name__ == "__main__":
    import asyncio

    async def _run_all():
        await test_no_ofrece_plantilla_si_no_hay_ninguna_guardada()
        await test_ofrece_plantilla_si_hay_guardadas()
        await test_elegir_plantilla_carga_puntos_con_identidad_estable()
        await test_no_pregunta_guardar_plantilla_si_solo_uso_checklist()
        await test_pregunta_guardar_plantilla_si_hay_puntos_nuevos()
        await test_guardar_plantilla_linkea_id_al_tour_actual()

    asyncio.run(_run_all())
    print("\n✅ ALL TESTS PASSED!")
