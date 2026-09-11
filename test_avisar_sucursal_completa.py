"""Idempotencia del aviso de "sucursal completó el tour" (`_avisar_si_sucursal_completa`).

El panel admin puede reabrir una tarea ya avisada (CampaniaDetail.tsx,
`updateCampaniaTarea(..., {estado: 'Pendiente'})`). Sin guardia, recompletarla
sin que cambie ninguna evidencia (reintento de webhook, doble tap del
encargado) dispara el aviso y el PDF de nuevo. El fix guarda un fingerprint del
estado exacto ya avisado en un evento `nota` y lo chequea antes de re-avisar.

Run directly: venv/Scripts/python.exe test_avisar_sucursal_completa.py
"""

import sys
import io

if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from unittest.mock import AsyncMock, MagicMock

from models import Sucursal
from router import ConversationRouter


def _make_router():
    router = ConversationRouter.__new__(ConversationRouter)
    router.sheets = MagicMock()
    router._tiene_ventana_abierta = MagicMock(return_value=True)
    router._enviar_revision_sucursal = AsyncMock(return_value=None)
    return router


def _tarea(id_, id_sucursal, estado="Completada", evidencia_path="foto1.jpg"):
    return {
        "id": id_,
        "id_sucursal": id_sucursal,
        "estado": estado,
        "evidencia_path": evidencia_path,
        "campania_id": "campania-1",
        "campanias": {"tipo": "tour_interno", "creado_por_telefono": "+5491111111111", "nombre": "Tour Enero"},
    }


async def test_avisa_la_primera_vez():
    router = _make_router()
    tareas = [_tarea("t1", "s1"), _tarea("t2", "s1")]
    router.sheets.get_campania_tareas.return_value = tareas
    router.sheets.get_campania_eventos_por_tareas.return_value = {}
    router.sheets.get_sucursal.return_value = Sucursal(
        id="s1", nombre="Sucursal Centro", direccion="", responsable="", tel_responsable="", zona=""
    )

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    await router._avisar_si_sucursal_completa(meta_client, tareas[0])

    meta_client.send_text.assert_awaited_once()
    router._enviar_revision_sucursal.assert_awaited_once()
    router.sheets.save_campania_evento.assert_called_once()
    _, kwargs = router.sheets.save_campania_evento.call_args
    assert kwargs["metadata"]["marca"] == "sucursal_completa_notificada"
    print("[OK] test_avisa_la_primera_vez")


async def test_no_reavisa_si_se_recompleta_sin_cambios():
    """Reabrir una tarea ya avisada y recompletarla con LA MISMA evidencia
    (retry de webhook, doble tap) no debe volver a avisar."""
    router = _make_router()
    tareas = [_tarea("t1", "s1"), _tarea("t2", "s1")]
    fingerprint = "|".join(f"{t['id']}:{t['evidencia_path']}" for t in sorted(tareas, key=lambda t: t["id"]))
    router.sheets.get_campania_tareas.return_value = tareas
    router.sheets.get_campania_eventos_por_tareas.return_value = {
        "t1": [{"tipo": "nota", "metadata": {"marca": "sucursal_completa_notificada", "fingerprint": fingerprint}}]
    }

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    await router._avisar_si_sucursal_completa(meta_client, tareas[0])

    meta_client.send_text.assert_not_awaited()
    router._enviar_revision_sucursal.assert_not_awaited()
    router.sheets.save_campania_evento.assert_not_called()
    print("[OK] test_no_reavisa_si_se_recompleta_sin_cambios")


async def test_reavisa_si_la_evidencia_cambio():
    """Reabrir y recompletar con una FOTO NUEVA es una revisión genuina: debe
    avisar de nuevo, no quedar silenciado para siempre por el fingerprint viejo."""
    router = _make_router()
    tareas = [_tarea("t1", "s1", evidencia_path="foto_nueva.jpg"), _tarea("t2", "s1")]
    fingerprint_viejo = "t1:foto_vieja.jpg|t2:foto1.jpg"
    router.sheets.get_campania_tareas.return_value = tareas
    router.sheets.get_campania_eventos_por_tareas.return_value = {
        "t1": [{"tipo": "nota", "metadata": {"marca": "sucursal_completa_notificada", "fingerprint": fingerprint_viejo}}]
    }
    router.sheets.get_sucursal.return_value = Sucursal(
        id="s1", nombre="Sucursal Centro", direccion="", responsable="", tel_responsable="", zona=""
    )

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    await router._avisar_si_sucursal_completa(meta_client, tareas[0])

    meta_client.send_text.assert_awaited_once()
    router._enviar_revision_sucursal.assert_awaited_once()
    router.sheets.save_campania_evento.assert_called_once()
    print("[OK] test_reavisa_si_la_evidencia_cambio")


async def test_no_avisa_si_falta_una_tarea():
    router = _make_router()
    tareas = [_tarea("t1", "s1"), _tarea("t2", "s1", estado="Pendiente")]
    router.sheets.get_campania_tareas.return_value = tareas

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    await router._avisar_si_sucursal_completa(meta_client, tareas[0])

    meta_client.send_text.assert_not_awaited()
    router.sheets.get_campania_eventos_por_tareas.assert_not_called()
    print("[OK] test_no_avisa_si_falta_una_tarea")


if __name__ == "__main__":
    import asyncio

    async def _run_all():
        await test_avisa_la_primera_vez()
        await test_no_reavisa_si_se_recompleta_sin_cambios()
        await test_reavisa_si_la_evidencia_cambio()
        await test_no_avisa_si_falta_una_tarea()

    asyncio.run(_run_all())
    print("\n✅ ALL TESTS PASSED!")
