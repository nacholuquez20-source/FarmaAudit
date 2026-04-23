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
