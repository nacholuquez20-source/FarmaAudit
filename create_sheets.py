#!/usr/bin/env python3
"""Create all required Google Sheets with proper headers."""

from sheets import SheetsManager

SHEETS_CONFIG = {
    "Maestro_Auditores": [
        "ID", "Nombre", "Sucursal", "Telefono", "Rol", "Fecha_Creacion"
    ],
    "Maestro_Sucursales": [
        "ID", "Nombre", "Codigo_Interno", "Direccion", "Responsable", "Telefono"
    ],
    "Catalogo_Areas": [
        "ID", "Nombre", "SubItems", "Notas"
    ],
    "Conversaciones": [
        "ID_Temp", "Telefono_Auditor", "Estado", "Hallazgo_Temp", "Timestamp", "Timeout_At"
    ],
    "Pendientes": [
        "ID_Temp", "Telefono_Auditor", "Sucursal_ID", "Area", "Subitem",
        "Descripcion", "Severidad", "Confianza", "Foto_URL", "Timestamp", "Expires_At"
    ],
    "Reportes": [
        "ID", "Auditor_ID", "Auditor_Nombre", "Sucursal_ID", "Sucursal_Nombre",
        "Area", "Subitem", "Descripcion", "Severidad", "Confianza", "Foto_URL",
        "Timestamp", "Estado", "Responsable_ID", "Responsable_Nombre", "Vencimiento"
    ],
    "Gestion": [
        "ID", "Reporte_ID", "Estado", "Responsable_ID", "Responsable_Nombre",
        "Plan_Accion", "Fecha_Compromiso", "Fecha_Cierre", "Notas", "Timestamp"
    ],
}

def create_sheets():
    """Create all required sheets with headers."""
    try:
        m = SheetsManager()
        workbook = m.workbook

        # Get existing sheet titles
        existing = {ws.title for ws in workbook.worksheets()}

        # Create each sheet
        for sheet_name, headers in SHEETS_CONFIG.items():
            if sheet_name in existing:
                print(f"[SKIP] {sheet_name} (ya existe)")
                # Update headers if needed
                ws = workbook.worksheet(sheet_name)
                if ws.cell(1, 1).value is None:
                    ws.append_row(headers)
                    print(f"       Headers agregados")
            else:
                # Create new sheet
                ws = workbook.add_worksheet(sheet_name, rows=1000, cols=30)
                ws.append_row(headers)
                print(f"[OK] {sheet_name} creada con headers")

        # Delete default "Hoja 1" if empty
        try:
            default = workbook.worksheet("Hoja 1")
            if not default.cell(1, 1).value:
                workbook.del_worksheet(default)
                print(f"[OK] Hoja 1 (vacia) eliminada")
        except:
            pass

        print("\n[OK] Todas las hojas creadas exitosamente!")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    print("Creando hojas en Google Sheets...\n")
    create_sheets()
