"""Modo de input por estado: que una palabra de control nunca se coma un dato.

Este bug se repitio 3 veces en contextos distintos ("siguiente" guardado como
marca, una campania llamada "Tour" que abandonaba el borrador, "estado" dentro
de un punto). Las tres veces se parcheo el caso puntual. Estos tests cierran la
clase entera: el de exhaustividad obliga a declarar el modo de CADA estado nuevo
al momento de escribirlo, en vez de descubrirlo cuando rompe en produccion.
"""

from models import ConversationState, InputMode, STATE_INPUT_MODE, espera_dato_libre

# Palabras que el router interpreta como navegacion global (router.py,
# `triggers_globales_habilitados`). Son exactamente las que no deben poder
# secuestrar un estado que espera un dato.
PALABRAS_DE_CONTROL = {
    "hola", "inicio", "empezar", "comenzar", "start",
    "auditoria", "auditoría", "audit", "auditar", "perfumeria", "perfumería",
    "desvios", "desvíos", "pendientes", "revision", "revisión",
    "campaña", "campana", "campañas", "campanas",
    "tour", "seguimiento", "estado", "avance",
}


def test_todos_los_estados_declaran_su_modo():
    """Un estado nuevo sin modo declarado hace fallar este test a proposito."""
    sin_declarar = [e.name for e in ConversationState if e not in STATE_INPUT_MODE]
    assert not sin_declarar, (
        "Estos estados no declaran su InputMode en STATE_INPUT_MODE (models.py): "
        f"{sin_declarar}. Decidí si esperan un dato dictado por el usuario "
        "(FREE_TEXT) o una opcion de menu (COMMAND) antes de mergear."
    )


def test_no_hay_modos_invalidos():
    invalidos = {
        estado.name: modo
        for estado, modo in STATE_INPUT_MODE.items()
        if modo not in (InputMode.COMMAND, InputMode.FREE_TEXT)
    }
    assert not invalidos, f"Modos invalidos: {invalidos}"


class TestRegresionesReales:
    """Los tres casos que ya rompieron en produccion."""

    def test_nombre_de_campania_acepta_la_palabra_tour(self):
        # Una auditora llamando "Tour" a un tour es el nombre mas obvio posible.
        assert espera_dato_libre(ConversationState.AUDITOR_CAMPANIA_NOMBRE)

    def test_punto_de_campania_acepta_palabras_de_control(self):
        # "revisar estado de la heladera" es la descripcion natural de un punto.
        assert espera_dato_libre(ConversationState.AUDITOR_CAMPANIA_AGREGANDO_ACCION)

    def test_comentario_de_evidencia_acepta_palabras_de_control(self):
        # El encargado escribe el comentario junto a la foto.
        assert espera_dato_libre(ConversationState.CAMPANIA_ESPERANDO_EVIDENCIA)


class TestLatentesDetectados:
    """Estados que tipean texto libre y todavia no habian roto, pero podian."""

    def test_alcance_acepta_nombres_de_sucursal_tipeados(self):
        # substep "esperando_nombres": `_resolver_sucursales_por_nombre`.
        assert espera_dato_libre(ConversationState.AUDITOR_CAMPANIA_ALCANCE)

    def test_sumar_sucursales_acepta_nombres_tipeados(self):
        # Nombres separados por coma sobre un tour ya lanzado.
        assert espera_dato_libre(ConversationState.AUDITOR_SEGUIMIENTO_SUMANDO_SUCURSALES)

    def test_respuestas_de_auditoria_son_dato(self):
        for estado in (
            ConversationState.EN_AUDITORIA,
            ConversationState.EN_BLOQUE,
            ConversationState.DESVIO_LIBRE,
            ConversationState.RECOLECTANDO_RESPUESTA,
        ):
            assert espera_dato_libre(estado), f"{estado.name} recibe texto dictado"


class TestMenusSiguenNavegando:
    """El arreglo no debe romper la navegacion: en un menu, 'tour' es un comando."""

    def test_estados_de_menu_aceptan_comandos_globales(self):
        for estado in (
            ConversationState.IDLE,
            ConversationState.AUDITOR_ELIGIENDO_MODULO,
            ConversationState.ENCARGADO_ELIGIENDO_MODULO,
            ConversationState.CAMPANIA_LISTANDO_TAREAS,
            ConversationState.AUDITOR_SEGUIMIENTO_ELIGIENDO,
        ):
            assert not espera_dato_libre(estado), (
                f"{estado.name} es un menu: las palabras de control tienen que navegar"
            )


def test_default_conservador_para_estado_no_declarado():
    """Si alguien agrega un estado y esquiva el test, que falle del lado seguro:
    perder una navegacion es molesto, perder el dato del usuario es el bug."""

    class EstadoFantasma(str):
        pass

    assert espera_dato_libre(EstadoFantasma("estado_que_no_existe"))


def test_los_estados_free_text_tienen_salida_explicita():
    """Un estado FREE_TEXT ignora las palabras de control a proposito, asi que
    solo es seguro mientras exista una salida que funcione en cualquier estado.
    `_universal_escape` corre antes del ruteo y no depende del modo de input; si
    alguien saca estas palabras, los estados FREE_TEXT se vuelven trampas.

    El saludo no esta en esta lista a proposito: abrir el menu pisa el borrador
    en curso (`update_conversacion` limpia `ultimo_mensaje`), y descartar trabajo
    sin confirmacion es justamente lo que la salida de emergencia evita.

    Se lee el fuente en vez de importar router: router arrastra modulos que
    reasignan sys.stdout (fix de encoding de Windows) y eso rompe la captura de
    pytest — el mismo motivo por el que test_imports.py solo corre como script.
    """
    from pathlib import Path

    router_src = Path(__file__).with_name("router.py").read_text(encoding="utf-8")
    cuerpo = router_src.split("def _is_escape_intent")[1].split("def ")[0]

    for palabra in ("salir", "menu", "cancelar todo", "basta", "reiniciar"):
        assert f'"{palabra}"' in cuerpo, (
            f"'{palabra}' dejo de ser salida de emergencia en _is_escape_intent: "
            "los estados FREE_TEXT se quedan sin forma de salir"
        )


def test_las_palabras_de_control_estan_documentadas():
    """Guardia de sincronizacion: si se agrega un trigger global nuevo al router
    sin sumarlo aca, este test deja de proteger ese caso."""
    import re
    from pathlib import Path

    router_src = Path(__file__).with_name("router.py").read_text(encoding="utf-8")
    # [-1]: lo que viene DESPUES del `if triggers_globales_habilitados:`, que es
    # donde estan los `trigger in {...}`. Antes de esa linea vive la condicion
    # (`payload.tipo == "text"`), que no es un trigger.
    bloque = router_src.split("triggers_globales_habilitados")[-1].split("if payload.context_message_id")[0]
    triggers_en_router = set(re.findall(r'"([a-záéíóúñ ]{2,30})"', bloque))
    no_cubiertas = {
        t for t in triggers_en_router
        if t not in PALABRAS_DE_CONTROL and " " not in t
    }
    assert not no_cubiertas, (
        f"Triggers globales nuevos en router.py no listados en PALABRAS_DE_CONTROL: "
        f"{no_cubiertas}"
    )
