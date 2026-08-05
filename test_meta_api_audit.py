"""Tests for the Meta WhatsApp Cloud API audit/fixes:

- MetaClient retry behaviour for transient send failures (connection errors,
  5xx) and the deliberate absence of retries for read timeouts / 4xx (to
  avoid duplicate message delivery).
- MetaClient.send_list_message's guard against exceeding Meta's real
  "max 10 rows total across all sections" limit for interactive lists.
- The 25-sucursal menu in router.ConversationRouter staying a plain numbered
  text message (not a broken multi-section interactive list), and that the
  handler receiving the reply still processes it correctly.

Run directly: venv/Scripts/python.exe test_meta_api_audit.py
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import meta_client as meta_client_module
from meta_client import MetaClient
from models import Auditor, ConversationState, Sucursal, WhatsAppPayload
from router import ConversationRouter


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None, text: str = ""):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.text = text or str(self._json_body)

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient whose post/get replay a scripted list
    of responses/exceptions, one per call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _next(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def post(self, *args, **kwargs):
        return await self._next("post", *args, **kwargs)

    async def get(self, *args, **kwargs):
        return await self._next("get", *args, **kwargs)


def _patched_client(script):
    holder = {}

    def factory(*args, **kwargs):
        client = _FakeAsyncClient(script)
        holder["client"] = client
        return client

    return factory, holder


def _make_meta_client() -> MetaClient:
    mc = MetaClient.__new__(MetaClient)
    mc.phone_number_id = "1234567890"
    mc.access_token = "fake-token"
    return mc


async def test_retry_succeeds_after_5xx():
    mc = _make_meta_client()
    ok_response = _FakeResponse(200, {"messages": [{"id": "wamid.123"}]})
    script = [_FakeResponse(500, text="server error"), ok_response]
    factory, holder = _patched_client(script)

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        msg_id = await mc.send_text_with_id("+5491111111111", "hola")

    assert msg_id == "wamid.123", f"expected message id from retried send, got {msg_id!r}"
    assert len(holder["client"].calls) == 2, "expected exactly one retry after a 5xx"
    print("[OK] test_retry_succeeds_after_5xx")


async def test_retry_succeeds_after_connect_error():
    mc = _make_meta_client()
    script = [httpx.ConnectError("boom"), _FakeResponse(200, {"messages": [{"id": "wamid.456"}]})]
    factory, holder = _patched_client(script)

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        msg_id = await mc.send_text_with_id("+5491111111111", "hola")

    assert msg_id == "wamid.456"
    assert len(holder["client"].calls) == 2
    print("[OK] test_retry_succeeds_after_connect_error")


async def test_no_retry_on_4xx():
    """A 4xx means Meta rejected/processed the request; retrying risks a
    duplicate send and won't fix a client error, so it must NOT be retried."""
    mc = _make_meta_client()
    script = [_FakeResponse(400, text="bad request")]
    factory, holder = _patched_client(script)

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        ok = await mc.send_text("+5491111111111", "hola")

    assert ok is False
    assert len(holder["client"].calls) == 1, "4xx must not be retried"
    print("[OK] test_no_retry_on_4xx")


async def test_no_retry_on_read_timeout():
    """A read timeout means we don't know if Meta already queued the
    message, so retrying could duplicate it — must not be retried."""
    mc = _make_meta_client()
    script = [httpx.ReadTimeout("timed out")]
    factory, holder = _patched_client(script)

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        ok = await mc.send_text("+5491111111111", "hola")

    assert ok is False, "unhandled ReadTimeout should be caught by the outer try/except and return False"
    assert len(holder["client"].calls) == 1, "read timeout must not be retried"
    print("[OK] test_no_retry_on_read_timeout")


async def test_send_list_message_rejects_more_than_10_rows():
    """Meta's real limit is 10 rows TOTAL across all sections (not 10 per
    section / 100 total) -- sending more must be refused client-side rather
    than firing a request Meta will reject."""
    mc = _make_meta_client()

    def _boom(*args, **kwargs):
        raise AssertionError("should not attempt an HTTP call for an invalid list message")

    options = [{"id": str(i), "title": f"Opcion {i}"} for i in range(15)]

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=_boom):
        ok = await mc.send_list_message(
            "+5491111111111",
            header="Header",
            body="Body",
            footer="",
            button_text="Ver",
            options=options,
        )

    assert ok is False
    print("[OK] test_send_list_message_rejects_more_than_10_rows")


async def test_send_list_message_accepts_10_rows():
    mc = _make_meta_client()
    script = [_FakeResponse(200)]
    factory, holder = _patched_client(script)
    options = [{"id": str(i), "title": f"Opcion {i}"} for i in range(10)]

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        ok = await mc.send_list_message(
            "+5491111111111",
            header="Header",
            body="Body",
            footer="",
            button_text="Ver",
            options=options,
        )

    assert ok is True
    print("[OK] test_send_list_message_accepts_10_rows")


async def test_send_text_truncates_to_meta_limit():
    mc = _make_meta_client()
    script = [_FakeResponse(200, {"messages": [{"id": "wamid.trunc"}]})]
    factory, holder = _patched_client(script)
    long_text = "x" * 5000

    with patch.object(meta_client_module.httpx, "AsyncClient", side_effect=factory):
        await mc.send_text_with_id("+5491111111111", long_text)

    sent_payload = holder["client"].calls[0][2]["json"]
    assert len(sent_payload["text"]["body"]) == MetaClient.MAX_TEXT_BODY_CHARS
    print("[OK] test_send_text_truncates_to_meta_limit")


def _make_sucursales(n: int):
    return [
        Sucursal(
            id=f"SC-{i:03d}",
            nombre=f"Farmacia {i}",
            direccion="",
            responsable="",
            tel_responsable="",
            zona=f"Zona{i % 3}",
        )
        for i in range(1, n + 1)
    ]


def _make_router_with_mock_sheets():
    router = ConversationRouter.__new__(ConversationRouter)
    router.sheets = MagicMock()
    return router


async def test_iniciar_seleccion_sucursal_sends_plain_text_for_25_sucursales():
    router = _make_router_with_mock_sheets()
    sucursales = _make_sucursales(25)
    router.sheets.get_auditor.return_value = Auditor(
        telefono="+5491111111111", nombre="Ana", cuadrilla="A", activo=True
    )
    router.sheets.get_conversacion.return_value = None
    router.sheets.get_all_sucursales.return_value = sucursales

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)
    meta_client.send_list_message = AsyncMock(return_value=True)

    payload = WhatsAppPayload(telefono="+5491111111111", tipo="text", contenido="hola")

    result = await router._iniciar_seleccion_sucursal(payload, meta_client)

    assert result == "sucursal_menu_sent"
    meta_client.send_list_message.assert_not_called()
    meta_client.send_text.assert_awaited_once()
    sent_text = meta_client.send_text.call_args.args[1]
    for i, s in enumerate(sucursales, 1):
        assert f"{i}. {s.nombre} ({s.zona})" in sent_text, f"menu missing line for sucursal {i}"

    router.sheets.update_conversacion.assert_called_once()
    _, kwargs = router.sheets.update_conversacion.call_args
    assert kwargs["estado"] == ConversationState.SELECCIONANDO_SUCURSAL_PERFUMERIA
    print("[OK] test_iniciar_seleccion_sucursal_sends_plain_text_for_25_sucursales")


async def test_handle_seleccion_processes_numeric_reply():
    router = _make_router_with_mock_sheets()
    sucursales = _make_sucursales(25)
    router.sheets.get_all_sucursales.return_value = sucursales
    router.sheets.get_checklist_perfumeria.return_value = {"PRES": [], "GOND": []}
    router.sheets.get_auditor.return_value = Auditor(
        telefono="+5491111111111", nombre="Ana", cuadrilla="A", activo=True
    )

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    conv = MagicMock()
    payload = WhatsAppPayload(telefono="+5491111111111", tipo="text", contenido="5")

    with patch(
        "router.AuditConversationHandler.enter_bloque", new=AsyncMock(return_value=None)
    ) as enter_bloque:
        result = await router._handle_seleccionando_sucursal_perfumeria(payload, conv, meta_client)

    assert result == "v2_audit_started", f"expected success, got {result!r}"
    router.sheets.create_sesion.assert_called_once()
    created_sesion = router.sheets.create_sesion.call_args.args[0]
    assert created_sesion.sucursal_id == sucursales[4].id, "choice '5' must resolve to sucursales[4] (1-indexed)"
    enter_bloque.assert_awaited_once()
    print("[OK] test_handle_seleccion_processes_numeric_reply")


async def test_handle_seleccion_rejects_out_of_range_choice():
    router = _make_router_with_mock_sheets()
    router.sheets.get_all_sucursales.return_value = _make_sucursales(25)

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)

    conv = MagicMock()
    payload = WhatsAppPayload(telefono="+5491111111111", tipo="text", contenido="99")

    result = await router._handle_seleccionando_sucursal_perfumeria(payload, conv, meta_client)

    assert result == "invalid_choice"
    router.sheets.create_sesion.assert_not_called()
    print("[OK] test_handle_seleccion_rejects_out_of_range_choice")


async def test_handle_seleccion_via_list_reply_style_id_still_works():
    """If _iniciar_seleccion_sucursal were ever switched to an interactive
    list whose row id equals the plain choice number, main.py already
    normalizes interactive.list_reply.id into payload.contenido (tipo="text")
    before routing -- so this handler needs no changes to accept it. Simulate
    that normalized payload directly."""
    router = _make_router_with_mock_sheets()
    sucursales = _make_sucursales(25)
    router.sheets.get_all_sucursales.return_value = sucursales
    router.sheets.get_checklist_perfumeria.return_value = {"PRES": []}
    router.sheets.get_auditor.return_value = Auditor(
        telefono="+5491111111111", nombre="Ana", cuadrilla="A", activo=True
    )

    meta_client = MagicMock()
    meta_client.send_text = AsyncMock(return_value=True)
    conv = MagicMock()
    # This is what main.py produces for interactive.list_reply: tipo="text",
    # contenido=<row id>.
    payload = WhatsAppPayload(telefono="+5491111111111", tipo="text", contenido="12")

    with patch("router.AuditConversationHandler.enter_bloque", new=AsyncMock(return_value=None)):
        result = await router._handle_seleccionando_sucursal_perfumeria(payload, conv, meta_client)

    assert result == "v2_audit_started"
    created_sesion = router.sheets.create_sesion.call_args.args[0]
    assert created_sesion.sucursal_id == sucursales[11].id
    print("[OK] test_handle_seleccion_via_list_reply_style_id_still_works")


async def main():
    tests = [
        test_retry_succeeds_after_5xx,
        test_retry_succeeds_after_connect_error,
        test_no_retry_on_4xx,
        test_no_retry_on_read_timeout,
        test_send_list_message_rejects_more_than_10_rows,
        test_send_list_message_accepts_10_rows,
        test_send_text_truncates_to_meta_limit,
        test_iniciar_seleccion_sucursal_sends_plain_text_for_25_sucursales,
        test_handle_seleccion_processes_numeric_reply,
        test_handle_seleccion_rejects_out_of_range_choice,
        test_handle_seleccion_via_list_reply_style_id_still_works,
    ]
    for t in tests:
        await t()
    print("\nALL TESTS PASSED!")
    return True


if __name__ == "__main__":
    try:
        ok = asyncio.run(main())
    except AssertionError as e:
        print(f"\n[FAILED] {e}")
        ok = False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        ok = False
    sys.exit(0 if ok else 1)
