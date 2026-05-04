"""Setup script to create Sesiones_Auditoria sheet in Google Sheets."""

import gspread
from google.oauth2.service_account import Credentials
import base64
import json
from config import get_settings

def setup_checklist_plantillas(sheet):
    """Create Checklist_Plantillas sheet with block-based audit items (A1-D5)."""
    # Check if sheet already exists and replace it
    try:
        ws = sheet.worksheet("Checklist_Plantillas")
        print("[*] Clearing existing 'Checklist_Plantillas' sheet...")
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Checklist_Plantillas' sheet...")
        ws = sheet.add_worksheet(title="Checklist_Plantillas", rows=100, cols=5)

    # Add headers for block-based checklist
    headers = ["item_id", "bloque", "bloque_nombre", "descripcion", "peso"]
    ws.append_row(headers)

    # Block-based audit items (18 items across 4 blocks)
    checklist_data = [
        # BLOQUE A: IMAGEN (6 items)
        ["A1", "A", "IMAGEN", "Limpieza y orden general del local", 5],
        ["A2", "A", "IMAGEN", "Orden y limpieza de góndolas / exhibidores", 5],
        ["A3", "A", "IMAGEN", "Orden y limpieza de Dispensario", 5],
        ["A4", "A", "IMAGEN", "Orden y limpieza de Caja", 5],
        ["A5", "A", "IMAGEN", "Uniforme / imagen del personal", 5],
        ["A6", "A", "IMAGEN", "Presencia del farmacéutico a cargo", 5],

        # BLOQUE B: CONDICIONES EDILICIAS (4 items)
        ["B1", "B", "CONDICIONES EDILICIAS", "Estado general del piso, techo y escaleras", 5],
        ["B2", "B", "CONDICIONES EDILICIAS", "Estado de iluminación (general, góndolas, vidriera)", 5],
        ["B3", "B", "CONDICIONES EDILICIAS", "Estado de luces de emergencia y salidas", 5],
        ["B4", "B", "CONDICIONES EDILICIAS", "Baño del personal: limpieza y dotación", 5],

        # BLOQUE C: ATENCIÓN AL CLIENTE (3 items)
        ["C1", "C", "ATENCIÓN AL CLIENTE", "Atención del farmacéutico", 5],
        ["C2", "C", "ATENCIÓN AL CLIENTE", "Atención de Cajero/a", 5],
        ["C3", "C", "ATENCIÓN AL CLIENTE", "Tiempo de espera / fluidez del servicio", 5],

        # BLOQUE D: DISPENSARIO / HABILITACIONES (5 items)
        ["D1", "D", "DISPENSARIO / HABILITACIONES", "Psicotrópicos: libro de recetas al día, archivado correcto", 5],
        ["D2", "D", "DISPENSARIO / HABILITACIONES", "Control de libros de psicotrópicos y duplicados", 5],
        ["D3", "D", "DISPENSARIO / HABILITACIONES", "Habilitación municipal / provincial vigente y visible", 5],
        ["D4", "D", "DISPENSARIO / HABILITACIONES", "Indumentaria del personal habilitado (farmacéutico)", 5],
        ["D5", "D", "DISPENSARIO / HABILITACIONES", "Temperatura del ambiente: registro actualizado", 5],
    ]

    for row in checklist_data:
        ws.append_row(row)

    print("[OK] Checklist_Plantillas created with 18 block-based audit items (A1-D5)")


def setup_sesiones_auditoria_simple(sheet):
    """Create Sesiones_Auditoria sheet with block-based audit headers."""
    # Check if Sesiones_Auditoria sheet already exists and update it
    try:
        ws = sheet.worksheet("Sesiones_Auditoria")
        print("[*] Updating existing 'Sesiones_Auditoria' sheet...")
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Sesiones_Auditoria' sheet...")
        ws = sheet.add_worksheet(title="Sesiones_Auditoria", rows=1000, cols=15)

    # Add headers for block-based audit sessions
    headers = [
        "id_sesion",
        "telefono_auditor",
        "sucursal_id",
        "estado",
        "timestamp_inicio",
        "timestamp_ultimo_punto",
        "punto_actual",
        "total_puntos",
        "hallazgos_json",
        "omitidos_json",
        "bloque_actual",
        "resultados_json",
        "stock_total",
        "stock_actual",
        "stock_items_json",
        "desvios_libres_json",
        "compromisos_firmados",
    ]

    ws.append_row(headers)
    print("[OK] Sheet created with headers:")
    for i, h in enumerate(headers, 1):
        print(f"   {i}. {h}")


def setup_control_stock(sheet):
    """Create Control_Stock sheet for stock verification."""
    # Check if Control_Stock sheet already exists
    try:
        ws = sheet.worksheet("Control_Stock")
        print("[OK] Sheet 'Control_Stock' already exists")
        return
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Control_Stock' sheet...")

    # Create new worksheet
    ws = sheet.add_worksheet(title="Control_Stock", rows=1000, cols=10)

    # Add headers
    headers = [
        "id",
        "auditoria_id",
        "sucursal_id",
        "fecha",
        "auditor",
        "producto",
        "stock_fisico",
        "stock_sistema",
        "diferencia",
        "alerta",
    ]

    ws.append_row(headers)
    print("[OK] Control_Stock sheet created with headers:")
    for i, h in enumerate(headers, 1):
        print(f"   {i}. {h}")


def setup_checklist_perfumeria(sheet):
    """Create Checklist_Perfumeria sheet with perfumery-specific blocks."""
    try:
        ws = sheet.worksheet("Checklist_Perfumeria")
        print("[*] Clearing existing 'Checklist_Perfumeria' sheet...")
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Checklist_Perfumeria' sheet...")
        ws = sheet.add_worksheet(title="Checklist_Perfumeria", rows=100, cols=7)

    # Add headers
    headers = ["bloque_id", "bloque_nombre", "punto_orden", "tipo_respuesta", "pregunta", "peso", "critico"]
    ws.append_row(headers)

    # Block-based perfumery audit items
    checklist_data = [
        # BLOQUE 1: PRESENTACION Y VIDRIERA
        ["PRES", "PRESENTACION Y VIDRIERA", 1, "foto_si_no", "¿Vidriera limpia y ordenada?", 5, "FALSE"],
        ["PRES", "PRESENTACION Y VIDRIERA", 2, "foto_si_no", "¿Productos exhibidos correctamente?", 4, "TRUE"],
        ["PRES", "PRESENTACION Y VIDRIERA", 3, "si_no", "¿Iluminación adecuada en vidriera?", 3, "FALSE"],

        # BLOQUE 2: GONDOLAS Y PUNTERAS
        ["GOND", "GONDOLAS Y PUNTERAS", 1, "foto_si_no", "¿Góndolas limpias y ordenadas?", 5, "FALSE"],
        ["GOND", "GONDOLAS Y PUNTERAS", 2, "foto_si_no", "¿Punteras organizadas correctamente?", 5, "TRUE"],
        ["GOND", "GONDOLAS Y PUNTERAS", 3, "foto_si_no", "¿Hay productos caídos o desordenados?", 4, "FALSE"],

        # BLOQUE 3: STOCK Y PROBADORES
        ["STOCK", "STOCK Y PROBADORES", 1, "numero_audio", "¿Stock físico de perfumes? (cantidades por producto)", 8, "TRUE"],
        ["STOCK", "STOCK Y PROBADORES", 2, "foto_si_no", "¿Probadores disponibles y limpios?", 6, "TRUE"],
        ["STOCK", "STOCK Y PROBADORES", 3, "numero_audio", "¿Stock de probadores completo?", 5, "FALSE"],

        # BLOQUE 4: REVISTA DE VENTAS
        ["REVISTA", "REVISTA DE VENTAS", 1, "lista_texto", "¿Qué productos están en la revista de ventas? (envía lista o foto)", 7, "TRUE"],
        ["REVISTA", "REVISTA DE VENTAS", 2, "si_no", "¿Precios coinciden con revista?", 4, "FALSE"],
        ["REVISTA", "REVISTA DE VENTAS", 3, "si_no", "¿Promociones vigentes están activas?", 3, "FALSE"],

        # BLOQUE 5: UNIFORME Y PERSONAL
        ["PERSONAL", "UNIFORME Y PERSONAL", 1, "foto_si_no", "¿Personal con uniforme completo?", 3, "FALSE"],
        ["PERSONAL", "UNIFORME Y PERSONAL", 2, "si_no", "¿Limpieza personal adecuada?", 3, "FALSE"],
        ["PERSONAL", "UNIFORME Y PERSONAL", 3, "si_no", "¿Asesor de perfumería disponible?", 5, "TRUE"],

        # BLOQUE 6: CONDICIONES GENERALES
        ["COND", "CONDICIONES GENERALES", 1, "si_no", "¿Temperatura ambiente adecuada?", 3, "FALSE"],
        ["COND", "CONDICIONES GENERALES", 2, "si_no", "¿Iluminación general del área?", 3, "FALSE"],
        ["COND", "CONDICIONES GENERALES", 3, "foto_si_no", "¿Piso limpio y sin obstáculos?", 4, "FALSE"],

        # BLOQUE 7: ATENCIÓN AL CLIENTE
        ["ATENCION", "ATENCIÓN AL CLIENTE", 1, "si_no", "¿Personal disponible para asesorar?", 5, "TRUE"],
        ["ATENCION", "ATENCIÓN AL CLIENTE", 2, "si_no", "¿Ofrece probadores a clientes?", 4, "FALSE"],
        ["ATENCION", "ATENCIÓN AL CLIENTE", 3, "si_no", "¿Trato profesional y amable?", 5, "TRUE"],

        # BLOQUE 8: OBSERVACIONES EXTRAS
        ["EXTRAS", "OBSERVACIONES EXTRAS", 1, "mixto", "¿Hallazgos, problemas o sugerencias? (texto/audio/foto)", 0, "FALSE"],
    ]

    for row in checklist_data:
        ws.append_row(row)

    print("[OK] Checklist_Perfumeria created with 8 blocks and 23 items")


if __name__ == "__main__":
    settings = get_settings()

    # Decode service account JSON
    service_account_json = base64.b64decode(
        settings.google_service_account_json
    ).decode('utf-8')
    service_account_info = json.loads(service_account_json)

    # Authenticate with Google Sheets
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet
    sheet = client.open_by_key(settings.google_sheets_id)

    # Setup all sheets
    setup_checklist_plantillas(sheet)
    setup_sesiones_auditoria_simple(sheet)
    setup_control_stock(sheet)
    setup_checklist_perfumeria(sheet)
