"""Tests de W1 (persistencia de sesión) y W4 (robustez de la entrada del auditor).

Cubren los defectos que quedaron expuestos al volver WhatsApp el único canal de
captura: la sesión que se perdía en cada redeploy, el menú que ofrecía 10 de 25
sucursales, "no sirve" confirmando la auditoría, y el filler conversacional que
terminaba como desvío real en la tabla `gestion`.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

# Impide que estos tests escriban en el Supabase real: la máquina de desarrollo
# tiene credenciales de producción en .env. La persistencia se prueba contra un
# cliente falso (ver FakeClient).
os.environ.setdefault("PYTEST_CURRENT_TEST", "test_audit_hardening")

import audit_session
from audit_session import (
    AuditSession, AuditState, FotoEvidence,
    create_session, get_session, save_session, delete_session,
)
from audit_handlers import (
    AuditConversationHandler,
    _es_afirmativo, _es_negativo, _es_asentimiento,
)
from models import WhatsAppPayload

TEL = "+5493810000000"


# ---------------------------------------------------------------- fakes

class MockMetaClient:
    def __init__(self):
        self.texts = []
        self.lists = []
        self.quick_replies = []

    async def send_text(self, telefono, text):
        self.texts.append(text)
        return True

    async def send_list_message(self, telefono, header, body, footer, button_text, options):
        # Igual que el cliente real: se niega a mandar más filas de las que
        # Meta permite en total.
        if len(options) > 10:
            return False
        self.lists.append({"header": header, "options": options})
        return True

    async def send_quick_reply(self, telefono, body, buttons):
        self.quick_replies.append({"body": body, "buttons": buttons})
        return True


class FakeTable:
    """Lo mínimo de la API de supabase-py que usa audit_session."""

    def __init__(self, store):
        self._store = store
        self._op = None
        self._row = None
        self._filters = {}

    def upsert(self, row, on_conflict=None):
        self._op, self._row = "upsert", row
        return self

    def select(self, cols="*"):
        self._op = "select"
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, n):
        return self

    def _matches(self, row):
        return all(row.get(c) == v for c, v in self._filters.items())

    def execute(self):
        if self._op == "upsert":
            self._store[self._row["telefono"]] = self._row
            return SimpleNamespace(data=[self._row])
        if self._op == "select":
            return SimpleNamespace(data=[r for r in self._store.values() if self._matches(r)])
        if self._op == "delete":
            for tel in [t for t, r in list(self._store.items()) if self._matches(r)]:
                self._store.pop(tel)
        return SimpleNamespace(data=[])


class FakeClient:
    def __init__(self):
        self.rows = {}

    def table(self, name):
        return FakeTable(self.rows)


def make_payload(telefono=TEL, tipo="text", contenido="", media_id=None):
    return WhatsAppPayload(
        telefono=telefono,
        tipo=tipo,
        contenido=contenido,
        media_id=media_id,
        media_url=None,
        context_message_id=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def make_sucursales(n):
    return [{"id": f"SUC{i:03d}", "nombre": f"Farmacia {i}"} for i in range(1, n + 1)]


# ---------------------------------------------------------------- W1

def test_sesion_sobrevive_al_redeploy():
    """El test de fuego de W1: reiniciar el proceso no puede perder la auditoría."""
    fake = FakeClient()
    with patch("audit_session._client", return_value=fake):
        delete_session(TEL)
        s = create_session(TEL, "SUC025", "Auditora Test")
        s.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION
        s.set_bloque_score("LIMPIEZA", 4)
        s.add_foto(FotoEvidence(id="foto_1", media_id="m1", bloque="LIMPIEZA", validated=True))
        s.add_desvio("LIMPIEZA", "Góndola con polvo")
        save_session(s)

        # Redeploy: el proceso arranca de cero y el cache en memoria está vacío.
        audit_session._sessions_cache.clear()

        recuperada = get_session(TEL)
        assert recuperada is not None, "la sesión se perdió al reiniciar"
        assert recuperada.estado == AuditState.BLOQUE_EVIDENCE_COLLECTION
        assert recuperada.bloques["LIMPIEZA"] == 4
        assert recuperada.sucursal_id == "SUC025"
        assert len(recuperada.fotos) == 1
        assert recuperada.fotos[0].media_id == "m1"
        assert len(recuperada.desvios) == 1
        assert recuperada.desvios[0].descripcion == "Góndola con polvo"


def test_sesion_vencida_no_se_recupera():
    fake = FakeClient()
    with patch("audit_session._client", return_value=fake):
        delete_session(TEL)
        s = create_session(TEL, "SUC001", "Auditora Test")
        s.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        save_session(s)
        audit_session._sessions_cache.clear()

        assert get_session(TEL) is None, "una sesión vencida no debería revivir"
        assert TEL not in fake.rows, "la fila vencida tiene que borrarse"


def test_sin_base_sigue_funcionando_en_memoria():
    """La degradación es deliberada: sin Supabase el bot no se cae."""
    with patch("audit_session._client", return_value=None):
        delete_session(TEL)
        s = create_session(TEL, "SUC002", "Auditora Test")
        s.set_bloque_score("STOCK", 3)
        save_session(s)

        recuperada = get_session(TEL)
        assert recuperada is not None
        assert recuperada.bloques["STOCK"] == 3


def test_fila_con_campos_desconocidos_se_puede_leer():
    """Una fila escrita por una versión anterior tiene que seguir siendo legible."""
    data = AuditSession(id_sesion="a1", telefono=TEL, sucursal_id="SUC003").to_dict()
    data["campo_que_ya_no_existe"] = "viejo"
    recuperada = AuditSession.from_dict(data)
    assert recuperada.sucursal_id == "SUC003"


# ---------------------------------------------------------------- W4.1

async def _menu_con(n):
    meta = MockMetaClient()
    await AuditConversationHandler._send_audit_sucursal_menu(meta, TEL, make_sucursales(n))
    return meta


def test_menu_ofrece_las_25_sucursales():
    meta = asyncio.run(_menu_con(25))
    assert not meta.lists, "25 sucursales no entran en una lista interactiva de Meta"
    assert len(meta.texts) == 1
    texto = meta.texts[0]
    faltantes = [s["nombre"] for s in make_sucursales(25) if s["nombre"] not in texto]
    assert not faltantes, f"quedaron sucursales fuera del menú: {faltantes}"


def test_menu_chico_usa_lista_interactiva():
    meta = asyncio.run(_menu_con(6))
    assert len(meta.lists) == 1
    assert len(meta.lists[0]["options"]) == 6


# ---------------------------------------------------------------- W4.2

def _session_eligiendo_sucursal(n=25):
    delete_session(TEL)
    s = create_session(TEL, "", "Auditora Test")
    s.estado = AuditState.SELECT_SUCURSAL
    s.verification_menu = make_sucursales(n)
    save_session(s)
    return s


def test_sticker_no_inicia_auditoria():
    """Antes elegía la primera sucursal: "" está contenido en cualquier nombre."""
    s = _session_eligiendo_sucursal()
    meta = MockMetaClient()
    payload = make_payload(tipo="sticker", contenido="")
    result = asyncio.run(
        AuditConversationHandler.handle_select_sucursal(payload, meta, s)
    )
    assert result == "invalid_sucursal_selection"
    assert s.sucursal_id == "", "no se puede elegir sucursal sin texto"
    assert meta.texts, "el bot tiene que explicar qué espera"


def test_numero_fuera_de_rango_no_elige():
    s = _session_eligiendo_sucursal()
    meta = MockMetaClient()
    payload = make_payload(contenido="99")
    result = asyncio.run(
        AuditConversationHandler.handle_select_sucursal(payload, meta, s)
    )
    assert result == "invalid_sucursal_selection"
    assert s.sucursal_id == ""


def test_nombre_ambiguo_pide_precision():
    """"Farmacia 1" matchea 1, 10..19: hay que listar, no elegir la primera."""
    s = _session_eligiendo_sucursal()
    meta = MockMetaClient()
    payload = make_payload(contenido="farmacia 1")
    result = asyncio.run(
        AuditConversationHandler.handle_select_sucursal(payload, meta, s)
    )
    assert result == "ambiguous_sucursal_selection"
    assert s.sucursal_id == ""


def test_numero_valido_elige_sucursal():
    s = _session_eligiendo_sucursal()
    meta = MockMetaClient()
    payload = make_payload(contenido="22")
    asyncio.run(AuditConversationHandler.handle_select_sucursal(payload, meta, s))
    assert s.sucursal_id == "SUC022"


# ---------------------------------------------------------------- W4.3

def test_no_sirve_no_confirma_la_auditoria():
    """El bug: "si" estaba contenido en "sirve" y confirmaba el envío."""
    assert not _es_afirmativo("no sirve")
    assert _es_negativo("no sirve")


def test_afirmativas_y_negativas():
    for texto in ["si", "sí", "SI", "1", "✅ Sí, enviar", "confirmo"]:
        assert _es_afirmativo(texto), f"{texto!r} debería ser afirmativo"
    for texto in ["no", "2", "❌ No, editar", "no, editar", "cambiar"]:
        assert not _es_afirmativo(texto), f"{texto!r} no debería confirmar"
        assert _es_negativo(texto), f"{texto!r} debería ser negativo"


def test_asentimientos():
    for texto in ["ok", "listo", "gracias", "dale", "perfecto"]:
        assert _es_asentimiento(texto), f"{texto!r} es puro acuse de recibo"
    for texto in ["góndola sucia", "faltan precios en la punta"]:
        assert not _es_asentimiento(texto), f"{texto!r} es contenido real"


# ---------------------------------------------------------------- W4.7

def _session_recolectando():
    delete_session(TEL)
    s = create_session(TEL, "SUC010", "Auditora Test")
    s.estado = AuditState.BLOQUE_EVIDENCE_COLLECTION
    s.add_foto(FotoEvidence(id="f1", media_id="m1", bloque="LIMPIEZA", validated=True))
    save_session(s)
    return s


def test_ok_no_crea_desvio():
    """Un "ok" suelto terminaba en la tabla `gestion` como desvío real."""
    s = _session_recolectando()
    meta = MockMetaClient()
    result = asyncio.run(
        AuditConversationHandler.handle_bloque_evidence(make_payload(contenido="ok"), meta, s)
    )
    assert result == "acknowledgement_ignored"
    assert len(s.desvios) == 0
    assert meta.texts, "el bot igual tiene que contestar"


def test_descripcion_real_si_crea_desvio():
    s = _session_recolectando()
    meta = MockMetaClient()
    result = asyncio.run(
        AuditConversationHandler.handle_bloque_evidence(
            make_payload(contenido="Góndola de shampoo sin precios"), meta, s
        )
    )
    assert result == "note_saved"
    assert len(s.desvios) == 1
    assert s.desvios[0].descripcion == "Góndola de shampoo sin precios"


def test_tras_escribir_otro_se_acepta_cualquier_texto():
    """Si el auditor pidió escribir una nota, su texto vale aunque sea corto."""
    s = _session_recolectando()
    s.awaiting_note_text = True
    meta = MockMetaClient()
    result = asyncio.run(
        AuditConversationHandler.handle_bloque_evidence(make_payload(contenido="ok"), meta, s)
    )
    assert result == "note_saved"
    assert len(s.desvios) == 1
    assert s.awaiting_note_text is False


# ---------------------------------------------------------------- W4.5

def test_media_no_soportada_recibe_respuesta():
    """Antes el bot se quedaba mudo ante un documento o un video."""
    s = _session_recolectando()
    meta = MockMetaClient()
    result = asyncio.run(
        AuditConversationHandler.handle_bloque_evidence(
            make_payload(tipo="document", contenido=""), meta, s
        )
    )
    assert result == "unsupported_media"
    assert meta.texts, "el bot no puede quedarse callado"


# ---------------------------------------------------------------- runner

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0

    print("=" * 60)
    print("W1 + W4 — persistencia de sesión y robustez de entrada")
    print("=" * 60)

    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"[ERROR] {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
