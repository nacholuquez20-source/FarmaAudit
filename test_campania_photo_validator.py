"""El PhotoValidator (nitidez, tamaño mínimo) que ya usa la auditoría clásica
(audit_handlers.py) no estaba conectado al flujo de campaña/tour: una foto
borrosa o de 200x200 se aceptaba igual como evidencia de un punto del Tour de
Farmacias. Este test cubre `_handle_campania_esperando_evidencia`
(router.py), que ahora valida antes de subir/guardar cualquier cosa.

Run directly: venv/Scripts/python.exe test_campania_photo_validator.py
"""

import sys
import io as io_module

if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io_module.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from models import ConversationState, Conversacion, WhatsAppPayload
from router import ConversationRouter


def _make_router():
    router = ConversationRouter.__new__(ConversationRouter)
    router.sheets = MagicMock()
    router._continue_campania_flow = AsyncMock(return_value="ok")
    router._reenviar_punto_a_auditor = AsyncMock(return_value=None)
    router._avisar_si_sucursal_completa = AsyncMock(return_value=None)
    return router


def _png_bytes(size, blurry=False):
    img = Image.new("RGB", size, color=(73, 109, 137))
    if blurry:
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(radius=10))
    buf = io_module.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _setup_common(router):
    router.sheets.get_campania_tarea_by_id.return_value = {
        "id": "tarea-1", "id_sucursal": "s1", "vista_at": None,
    }
    conv = Conversacion(
        telefono="+5491111111111",
        estado_actual=ConversationState.CAMPANIA_ESPERANDO_EVIDENCIA,
        id_pendiente="tarea-1",
        ultimo_mensaje="{}",
    )
    encargado = {"id_sucursal": "s1", "nombre": "Juan"}
    return conv, encargado


async def test_foto_chica_se_rechaza_sin_guardar_nada():
    router = _make_router()
    conv, encargado = _setup_common(router)
    payload = WhatsAppPayload(telefono="+5491111111111", tipo="image", media_id="m1")

    meta_client = MagicMock()
    meta_client.download_media_with_metadata = AsyncMock(
        return_value=(_png_bytes((100, 100)), "image/png")
    )
    meta_client.send_text = AsyncMock(return_value=True)

    result = await router._handle_campania_esperando_evidencia(payload, conv, meta_client, encargado)

    assert result == "campania_evidencia_invalida_calidad"
    router.sheets.upload_campania_evidencia.assert_not_called()
    router.sheets.update_campania_tarea_fields.assert_not_called()
    router.sheets.save_campania_evento.assert_not_called()
    meta_client.send_text.assert_awaited_once()
    assert "Intentá con otra foto" in meta_client.send_text.call_args.args[1]
    print("[OK] test_foto_chica_se_rechaza_sin_guardar_nada")


async def test_foto_valida_se_guarda_normal():
    router = _make_router()
    conv, encargado = _setup_common(router)
    payload = WhatsAppPayload(telefono="+5491111111111", tipo="image", media_id="m1", contenido="")

    meta_client = MagicMock()
    meta_client.download_media_with_metadata = AsyncMock(
        return_value=(_png_bytes((500, 500)), "image/png")
    )
    meta_client.send_text = AsyncMock(return_value=True)
    router.sheets.upload_campania_evidencia.return_value = {"path": "evid.jpg", "thumb_path": "thumb.jpg"}

    result = await router._handle_campania_esperando_evidencia(payload, conv, meta_client, encargado)

    assert result == "ok"  # devuelto por _continue_campania_flow mockeado
    router.sheets.upload_campania_evidencia.assert_called_once()
    router.sheets.update_campania_tarea_fields.assert_called_once()
    router.sheets.save_campania_evento.assert_called_once()
    print("[OK] test_foto_valida_se_guarda_normal")


if __name__ == "__main__":
    import asyncio

    async def _run_all():
        await test_foto_chica_se_rechaza_sin_guardar_nada()
        await test_foto_valida_se_guarda_normal()

    asyncio.run(_run_all())
    print("\n✅ ALL TESTS PASSED!")
