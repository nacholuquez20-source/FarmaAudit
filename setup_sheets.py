"""Setup script to create Sesiones_Auditoria sheet in Google Sheets."""

import gspread
from google.oauth2.service_account import Credentials
import base64
import json
from config import get_settings

def setup_checklist_plantillas(sheet):
    """Create Checklist_Plantillas sheet with example data."""
    # Check if sheet already exists
    try:
        ws = sheet.worksheet("Checklist_Plantillas")
        print("[OK] Sheet 'Checklist_Plantillas' already exists")
        return
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Checklist_Plantillas' sheet...")

    # Create new worksheet
    ws = sheet.add_worksheet(title="Checklist_Plantillas", rows=100, cols=5)

    # Add headers
    headers = [
        "punto_orden",
        "area",
        "descripcion",
        "responsable_default",
        "severidad_default",
    ]
    ws.append_row(headers)

    # Add example data for pharmacy audit
    checklist_data = [
        [1, "Vidriera", "Verificar limpieza, orden y vigencia de productos expuestos. Sin productos vencidos ni sin precio.", "Encargado de local", "Media"],
        [2, "Gondola Dermocosmética", "Revisar orden de categorías, etiquetado de precios, productos bien orientados al frente.", "Repositor", "Baja"],
        [3, "Caja", "Control de fondo de caja, limpieza del mostrador, presencia de cartelería obligatoria (precios, AFIP).", "Cajero/a", "Alta"],
        [4, "Dispensario", "Verificar cadena de frío (heladera entre 2-8°C), orden de medicamentos por categoría, libro de psicotrópicos al día.", "Farmacéutico/a", "Alta"],
        [5, "Limpieza general", "Pisos, estanterías, baño de empleados. Presencia de elementos de limpieza correctamente almacenados.", "Personal de limpieza", "Media"],
        [6, "Vencimientos", "Muestra aleatoria de 10 productos en góndola. Ninguno vencido ni próximo a vencer (<30 días).", "Encargado de local", "Alta"],
    ]

    for row in checklist_data:
        ws.append_row(row)

    print("[OK] Checklist_Plantillas created with 6 audit points")


def setup_sesiones_auditoria_simple(sheet):
    """Create Sesiones_Auditoria sheet with correct headers."""
    # Check if Sesiones_Auditoria sheet already exists
    try:
        ws = sheet.worksheet("Sesiones_Auditoria")
        print("[OK] Sheet 'Sesiones_Auditoria' already exists")
        return
    except gspread.exceptions.WorksheetNotFound:
        print("[*] Creating 'Sesiones_Auditoria' sheet...")

    # Create new worksheet
    ws = sheet.add_worksheet(title="Sesiones_Auditoria", rows=1000, cols=10)

    # Add headers
    headers = [
        "id_sesion",
        "telefono_auditor",
        "sucursal_id",
        "punto_actual",
        "total_puntos",
        "hallazgos_json",
        "omitidos_json",
        "estado",
        "timestamp_inicio",
        "timestamp_ultimo_punto",
    ]

    ws.append_row(headers)
    print("[OK] Sheet created with headers:")
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

    # Setup both sheets
    setup_checklist_plantillas(sheet)
    setup_sesiones_auditoria_simple(sheet)
