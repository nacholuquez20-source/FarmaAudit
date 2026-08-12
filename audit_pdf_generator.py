"""Generate PDF audit reports with ReportLab."""

import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from audit_session import BLOQUE_LABELS, AuditSession

logger = logging.getLogger(__name__)

# Brand colors
NAVY   = colors.HexColor("#1e3a6d")
ORANGE = colors.HexColor("#f15a29")
GREEN  = colors.HexColor("#2a9d5f")
RED    = colors.HexColor("#dc2626")
AMBER  = colors.HexColor("#d97706")
LIGHT_BLUE = colors.HexColor("#eff6ff")
LIGHT_RED  = colors.HexColor("#fef2f2")
LIGHT_AMB  = colors.HexColor("#fffbeb")
LIGHT_GRN  = colors.HexColor("#f0fdf4")
GREY   = colors.HexColor("#6b7280")
LINE   = colors.HexColor("#e5e7eb")


def _score_color(score: int):
    if score <= 2: return RED
    if score == 3: return AMBER
    return GREEN


def _score_bg(score: int):
    if score <= 2: return LIGHT_RED
    if score == 3: return LIGHT_AMB
    return LIGHT_GRN


def _score_label(score: int) -> str:
    return {1: "Muy malo", 2: "Malo", 3: "Regular", 4: "Bueno", 5: "Excelente"}.get(score, "")


def _rl_image(img_bytes: bytes, max_w: float, max_h: float) -> Optional[RLImage]:
    """Return a ReportLab Image scaled to fit within max_w x max_h."""
    try:
        from PIL import Image as PILImage
        pil = PILImage.open(BytesIO(img_bytes))
        # Convert to RGB if needed (RGBA, palette mode, etc.)
        if pil.mode not in ("RGB", "L"):
            pil = pil.convert("RGB")
        orig_w, orig_h = pil.size
        ratio = min(max_w / orig_w, max_h / orig_h)
        w, h = orig_w * ratio, orig_h * ratio
        buf = BytesIO()
        pil.save(buf, format="JPEG", quality=80, optimize=True)
        buf.seek(0)
        return RLImage(buf, width=w, height=h)
    except Exception as e:
        logger.warning(f"Could not embed image in PDF: {e}")
        return None


def generate_audit_pdf(
    session: AuditSession,
    sucursal_nombre: str,
    auditor_nombre: Optional[str] = None,
    responsable_desvios: Optional[str] = None,
    photo_bytes: Optional[Dict[str, bytes]] = None,  # {foto_id: raw_bytes}
) -> bytes:
    """Generate PDF audit report with per-bloque scores and embedded photos."""

    buf = BytesIO()
    page_w, page_h = A4
    margin = 1.5 * cm
    usable_w = page_w - 2 * margin

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    styles = getSampleStyleSheet()

    # ── Custom styles ──────────────────────────────────────────────────────────
    h1 = ParagraphStyle("H1", parent=styles["Normal"],
                        fontSize=18, fontName="Helvetica-Bold",
                        textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)
    sub = ParagraphStyle("Sub", parent=styles["Normal"],
                         fontSize=10, textColor=GREY, alignment=TA_CENTER, spaceAfter=8)
    section = ParagraphStyle("Section", parent=styles["Normal"],
                              fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"],
                           fontSize=9, leading=13, textColor=colors.black)
    small = ParagraphStyle("Small", parent=styles["Normal"],
                            fontSize=8, textColor=GREY)
    sig_style = ParagraphStyle("Sig", parent=styles["Normal"],
                                fontSize=9, alignment=TA_CENTER)

    story = []

    # ── Header ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("FarmaAudit", h1))
    story.append(Paragraph("Informe de Auditoría Operativa — Perfumería", sub))

    # Thin color bar
    bar = Table([[""]], colWidths=[usable_w], rowHeights=[4])
    bar.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), NAVY)]))
    story.append(bar)
    story.append(Spacer(1, 10))

    # ── Audit info ─────────────────────────────────────────────────────────────
    audit_date = ""
    if session.started_at:
        try:
            audit_date = datetime.fromisoformat(session.started_at).strftime("%d/%m/%Y %H:%M")
        except Exception:
            audit_date = session.started_at

    info_rows = [
        ["Sucursal", sucursal_nombre],
        ["Auditor",  auditor_nombre or session.auditor_nombre or "—"],
        ["Fecha",    audit_date or "—"],
        ["Responsable desvíos", responsable_desvios or "—"],
        ["ID auditoría", session.id_sesion],
    ]
    col1 = 3.5 * cm
    col2 = usable_w - col1
    info_table = Table(info_rows, colWidths=[col1, col2])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",  (0, 0), (-1, -1), colors.black),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    # ── Scores ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("Puntuaciones por área", section))

    score_header = [
        Paragraph("<b>Área</b>", body),
        Paragraph("<b>Puntaje</b>", body),
        Paragraph("<b>Evaluación</b>", body),
        Paragraph("<b>Indicador</b>", body),
    ]
    score_rows = [score_header]
    score_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]

    for i, bloque in enumerate(session.bloques, start=1):
        score = session.bloques[bloque]
        filled   = "●" * score
        empty    = "○" * (5 - score)
        score_rows.append([
            BLOQUE_LABELS.get(bloque, bloque),
            f"{score}/5",
            _score_label(score),
            Paragraph(f'<font color="{_score_color(score).hexval()}">{filled}</font>'
                      f'<font color="#d1d5db">{empty}</font>', body),
        ])
        score_styles.append(("BACKGROUND", (1, i), (3, i), _score_bg(score)))

    if session.bloques:
        avg = sum(session.bloques.values()) / len(session.bloques)
        avg_r = round(avg)
        score_rows.append([
            Paragraph("<b>Promedio general</b>", body),
            Paragraph(f"<b>{avg:.1f}/5</b>", body),
            Paragraph(f"<b>{_score_label(avg_r)}</b>", body),
            "",
        ])
        last = len(score_rows) - 1
        score_styles += [
            ("FONTNAME",   (0, last), (-1, last), "Helvetica-Bold"),
            ("BACKGROUND", (1, last), (3, last), _score_bg(avg_r)),
        ]

    score_table = Table(
        score_rows,
        colWidths=[usable_w * 0.38, usable_w * 0.12, usable_w * 0.22, usable_w * 0.28],
    )
    score_table.setStyle(TableStyle(score_styles))
    story.append(score_table)
    story.append(Spacer(1, 14))

    # ── Desvíos con fotos ──────────────────────────────────────────────────────
    if session.desvios:
        story.append(Paragraph(f"Hallazgos encontrados ({len(session.desvios)})", section))

        # Cada hallazgo muestra SU propia foto (Desvio.fotos, poblado desde el
        # flujo libre de evidencia — ver audit_handlers.py). Antes no existia
        # ese vinculo y se mostraba una galeria generica de todas las fotos del
        # bloque al final, sin decir cual foto correspondia a cual hallazgo.
        foto_by_id = {f.id: f for f in session.fotos}
        max_img_w = (usable_w - 0.3 * cm) / 2  # 2 columns
        max_img_h = 5 * cm

        bloques_con_desvios: List[str] = []
        desvios_por_bloque: Dict[str, List] = {}
        for desvio in session.desvios:
            if desvio.bloque not in desvios_por_bloque:
                desvios_por_bloque[desvio.bloque] = []
                bloques_con_desvios.append(desvio.bloque)
            desvios_por_bloque[desvio.bloque].append(desvio)

        idx = 0
        for bloque in bloques_con_desvios:
            bloque_label = BLOQUE_LABELS.get(bloque, bloque)
            score = session.bloques.get(bloque, 0)
            sc = _score_color(score)

            for desvio in desvios_por_bloque[bloque]:
                idx += 1

                # Cada hallazgo se arma en su propia lista y se agrega con
                # KeepTogether: sin esto ReportLab puede cortar un hallazgo a
                # la mitad justo antes de su foto en el salto de pagina.
                item_flowables = []

                # Desvío header bar
                hdr_data = [[
                    Paragraph(
                        f'<font color="white"><b>#{idx} — {bloque_label}</b>  '
                        f'Puntaje: {score}/5 — {_score_label(score)}</font>',
                        ParagraphStyle("DH", parent=styles["Normal"], fontSize=9,
                                       fontName="Helvetica-Bold", textColor=colors.white),
                    ),
                ]]
                hdr = Table(hdr_data, colWidths=[usable_w])
                hdr.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), sc),
                    ("TOPPADDING",    (0,0), (-1,-1), 5),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                    ("LEFTPADDING",   (0,0), (-1,-1), 8),
                ]))
                item_flowables.append(hdr)

                # Descripción
                desc = desvio.descripcion[:500] + "…" if len(desvio.descripcion) > 500 else desvio.descripcion
                desc_data = [[Paragraph(desc, body)]]
                desc_table = Table(desc_data, colWidths=[usable_w])
                desc_table.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0), (-1,-1), _score_bg(score)),
                    ("TOPPADDING",    (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING",   (0,0), (-1,-1), 8),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 8),
                ]))
                item_flowables.append(desc_table)

                # Fotos ligadas a ESTE hallazgo puntual (no a todo el bloque).
                images = []
                if photo_bytes:
                    for foto_id in desvio.fotos:
                        foto = foto_by_id.get(foto_id)
                        if not foto:
                            continue
                        raw = photo_bytes.get(foto.id)
                        if raw:
                            img = _rl_image(raw, max_img_w, max_img_h)
                            if img:
                                images.append(img)

                if images:
                    item_flowables.append(Spacer(1, 4))
                    if len(images) % 2 != 0:
                        images.append("")
                    rows = [images[i:i+2] for i in range(0, len(images), 2)]
                    photo_table = Table(rows, colWidths=[max_img_w, max_img_w])
                    photo_table.setStyle(TableStyle([
                        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
                        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                        ("TOPPADDING",    (0,0), (-1,-1), 4),
                        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                    ]))
                    item_flowables.append(photo_table)

                item_flowables.append(Spacer(1, 8))
                story.append(KeepTogether(item_flowables))

    else:
        story.append(Paragraph("✅ No se encontraron hallazgos críticos en esta auditoría.", body))

    # ── Evidence summary ───────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(Paragraph("Evidencia recolectada", section))
    ev_data = [
        ["Fotos capturadas", str(len(session.fotos))],
        ["Desvíos registrados", str(len(session.desvios))],
    ]
    ev_table = Table(ev_data, colWidths=[col1, col2])
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LIGHT_BLUE),
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("GRID",       (0,0), (-1,-1), 0.5, LINE),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(ev_table)

    # ── Signatures ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 24))
    sig_line = "_" * 38
    sig_table = Table(
        [[Paragraph(sig_line, sig_style), Paragraph(sig_line, sig_style)],
         [Paragraph("Firma Auditor", sig_style), Paragraph("Firma Responsable / Encargado", sig_style)]],
        colWidths=[usable_w / 2, usable_w / 2],
    )
    sig_table.setStyle(TableStyle([
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(sig_table)

    # ── Build ──────────────────────────────────────────────────────────────────
    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result


def _fmt_fecha(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)[:16]


ESTADO_SESION_LABELS = {
    "completa": "Completa",
    "en_curso": "En curso",
    "en_bloque": "En curso",
    "confirmando_bloque": "En curso",
    "stock_loop": "En curso",
    "en_stock_item": "En curso",
    "desvio_libre": "En curso",
    "compromisos": "En curso",
    "esperando_confirmacion": "En curso",
    "esperando_edicion": "En curso",
    "cancelada": "Cancelada",
    "expirada": "Expirada",
}


def generate_controles_summary_pdf(
    sesiones: List[Dict[str, Any]],
    fichas: List[Dict[str, Any]],
    sucursales_by_id: Dict[str, str],
    auditores_by_tel: Dict[str, str],
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
) -> bytes:
    """Generate a summary PDF of all audit controls performed, with links to full fichas."""

    buf = BytesIO()
    page_w, page_h = A4
    margin = 1.5 * cm
    usable_w = page_w - 2 * margin

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Normal"],
                        fontSize=18, fontName="Helvetica-Bold",
                        textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)
    sub = ParagraphStyle("Sub", parent=styles["Normal"],
                         fontSize=10, textColor=GREY, alignment=TA_CENTER, spaceAfter=8)
    section = ParagraphStyle("Section", parent=styles["Normal"],
                              fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=14, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.5, leading=11)
    body_link = ParagraphStyle("BodyLink", parent=body, textColor=NAVY, fontName="Helvetica-Bold")
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=GREY)

    story = []
    story.append(Paragraph("FarmaAudit", h1))
    story.append(Paragraph("Resumen de Controles Realizados", sub))

    bar = Table([[""]], colWidths=[usable_w], rowHeights=[4])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY)]))
    story.append(bar)
    story.append(Spacer(1, 8))

    rango = "Todo el periodo disponible"
    if fecha_desde or fecha_hasta:
        rango = f"Desde {fecha_desde or '—'} hasta {fecha_hasta or '—'}"
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} — {rango} — "
        f"{len(sesiones)} control(es), {len(fichas)} con ficha completa disponible",
        small,
    ))

    # ── Tabla de controles (sesiones de auditoría) ──────────────────────────────
    story.append(Paragraph(f"Controles realizados ({len(sesiones)})", section))

    header = [Paragraph(f"<b>{h}</b>", body) for h in
              ["Fecha", "Sucursal", "Auditor", "Estado", "Puntos evaluados"]]
    rows = [header]
    for s in sesiones:
        sucursal_nombre = sucursales_by_id.get(s.get("sucursal_id", ""), s.get("sucursal_id", "—"))
        auditor_nombre = auditores_by_tel.get(str(s.get("telefono_auditor", "")), s.get("telefono_auditor", "—"))
        estado_label = ESTADO_SESION_LABELS.get(s.get("estado", ""), s.get("estado", "—"))
        puntos = f"{s.get('punto_actual', 0)}/{s.get('total_puntos', 0)}"
        rows.append([
            Paragraph(_fmt_fecha(s.get("timestamp_inicio")), body),
            Paragraph(str(sucursal_nombre), body),
            Paragraph(str(auditor_nombre), body),
            Paragraph(estado_label, body),
            Paragraph(puntos, body),
        ])

    if len(rows) == 1:
        rows.append([Paragraph("Sin controles registrados en este periodo.", body), "", "", "", ""])

    table = Table(rows, colWidths=[usable_w * 0.22, usable_w * 0.28, usable_w * 0.24, usable_w * 0.14, usable_w * 0.12], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(table)

    # ── Tabla de fichas completas (con link de descarga) ────────────────────────
    story.append(Paragraph(f"Fichas completas disponibles ({len(fichas)})", section))
    if not fichas:
        story.append(Paragraph(
            "Todavia no hay fichas en PDF con foto y detalle completo guardadas para este periodo. "
            "Las auditorias que se completen de aqui en adelante van a aparecer en esta seccion.",
            body,
        ))
    else:
        fheader = [Paragraph(f"<b>{h}</b>", body) for h in
                   ["Fecha", "Sucursal", "Auditor", "Desvios", "Ficha"]]
        frows = [fheader]
        for f in fichas:
            sucursal_nombre = sucursales_by_id.get(f.get("sucursal_id", ""), f.get("sucursal_id", "—"))
            link = f.get("url_pdf") or ""
            link_cell = Paragraph(f'<link href="{link}">Ver ficha completa</link>', body_link) if link else Paragraph("—", body)
            frows.append([
                Paragraph(_fmt_fecha(f.get("fecha_auditoria")), body),
                Paragraph(str(sucursal_nombre), body),
                Paragraph(str(f.get("auditor_nombre") or "—"), body),
                Paragraph(str(f.get("desvios_count", 0)), body),
                link_cell,
            ])

        ftable = Table(frows, colWidths=[usable_w * 0.2, usable_w * 0.28, usable_w * 0.22, usable_w * 0.12, usable_w * 0.18], repeatRows=1)
        ftable.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(ftable)
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "Los links de ficha son temporales (validos por unos dias desde que se genero este PDF).",
            small,
        ))

    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result


def _severidad_color(severidad: Optional[str]):
    return {"Alta": RED, "Media": AMBER, "Baja": GREEN}.get(severidad or "", GREY)


def _severidad_bg(severidad: Optional[str]):
    return {"Alta": LIGHT_RED, "Media": LIGHT_AMB, "Baja": LIGHT_GRN}.get(severidad or "", colors.HexColor("#f8fafc"))


def _horas_transcurridas(desde: Optional[str], hasta: Optional[str]) -> Optional[float]:
    if not desde or not hasta:
        return None
    try:
        t0 = datetime.fromisoformat(str(desde).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(hasta).replace("Z", "+00:00"))
        return (t1 - t0).total_seconds() / 3600
    except Exception:
        return None


def _fmt_horas(horas: Optional[float]) -> str:
    if horas is None:
        return "—"
    if horas < 1:
        return f"{int(horas * 60)} min"
    if horas < 48:
        return f"{horas:.1f} h"
    return f"{horas / 24:.1f} dias"


def generate_respuestas_pdf(
    sucursal_nombre: str,
    items: List[Dict[str, Any]],
    encargado_nombre: Optional[str] = None,
    auditor_nombre: Optional[str] = None,
    desvios_abiertos_restantes: Optional[int] = None,
) -> bytes:
    """Informe de las correcciones que un encargado mando por WhatsApp para un
    grupo de desvios, con lo detectado y lo respondido enfrentados item por
    item (circuito de vuelta auditor <- encargado, ver plan en memoria).

    Cada item de `items` describe un desvio ya respondido:
        id_gestion: str
        desvio_descripcion: str
        severidad: 'Alta' | 'Media' | 'Baja'
        detectado_at: str ISO o None       — cuando se creo la gestion
        foto_detectada_bytes: bytes o None — foto original del hallazgo
        respuesta_comentario: str o None
        respuesta_foto_bytes: bytes o None — foto de la correccion
        respuesta_at: str ISO o None       — cuando respondio el encargado

    Es deliberadamente independiente de AuditSession: no describe una
    auditoria en curso, describe una tanda de respuestas ya guardadas en
    desvio_eventos, así que no hay sesión que pasarle.
    """
    buf = BytesIO()
    page_w, page_h = A4
    margin = 1.5 * cm
    usable_w = page_w - 2 * margin

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Normal"],
                        fontSize=18, fontName="Helvetica-Bold",
                        textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)
    sub = ParagraphStyle("Sub", parent=styles["Normal"],
                         fontSize=10, textColor=GREY, alignment=TA_CENTER, spaceAfter=8)
    section = ParagraphStyle("Section", parent=styles["Normal"],
                              fontSize=11, fontName="Helvetica-Bold",
                              textColor=NAVY, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.black)
    label = ParagraphStyle("Label", parent=styles["Normal"], fontSize=8, fontName="Helvetica-Bold", textColor=GREY)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=GREY)
    caption = ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER, textColor=GREY)

    story = []
    story.append(Paragraph("FarmaAudit", h1))
    story.append(Paragraph("Respuestas del encargado a desvios pendientes", sub))

    bar = Table([[""]], colWidths=[usable_w], rowHeights=[4])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY)]))
    story.append(bar)
    story.append(Spacer(1, 10))

    col1 = 3.8 * cm
    col2 = usable_w - col1
    info_rows = [
        ["Sucursal", sucursal_nombre],
        ["Encargado", encargado_nombre or "—"],
        ["Auditor", auditor_nombre or "—"],
        ["Generado", datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Desvios en este informe", str(len(items))],
    ]
    if desvios_abiertos_restantes is not None:
        info_rows.append(["Desvios aun abiertos en la sucursal", str(desvios_abiertos_restantes)])

    info_table = Table(info_rows, colWidths=[col1, col2])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    max_img_w = (usable_w - 0.6 * cm) / 2
    max_img_h = 6 * cm

    for idx, item in enumerate(items, start=1):
        severidad = item.get("severidad")
        sc = _severidad_color(severidad)
        bg = _severidad_bg(severidad)

        # Cada item se arma en su propia lista y se agrega con KeepTogether:
        # sin esto, ReportLab puede cortar un item a la mitad justo antes de
        # la tabla de fotos (el header y la descripcion quedan en una pagina,
        # las fotos solas al inicio de la siguiente, con un hueco enorme).
        item_flowables = []

        hdr_data = [[
            Paragraph(
                f'<font color="white"><b>#{idx} — {severidad or "Sin severidad"}</b></font>',
                ParagraphStyle("DH", parent=styles["Normal"], fontSize=9,
                               fontName="Helvetica-Bold", textColor=colors.white),
            ),
        ]]
        hdr = Table(hdr_data, colWidths=[usable_w])
        hdr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), sc),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))
        item_flowables.append(hdr)

        desc = item.get("desvio_descripcion") or "—"
        desc_table = Table([[Paragraph(desc, body)]], colWidths=[usable_w])
        desc_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ]))
        item_flowables.append(desc_table)
        item_flowables.append(Spacer(1, 6))

        # Detectado vs. respondido, enfrentados en dos columnas.
        detectado_img = _rl_image(item["foto_detectada_bytes"], max_img_w, max_img_h) if item.get("foto_detectada_bytes") else None
        respuesta_img = _rl_image(item["respuesta_foto_bytes"], max_img_w, max_img_h) if item.get("respuesta_foto_bytes") else None

        horas = _horas_transcurridas(item.get("detectado_at"), item.get("respuesta_at"))

        left_cell = [
            Paragraph("DETECTADO", label),
            Paragraph(_fmt_fecha(item.get("detectado_at")), small),
        ]
        if detectado_img:
            left_cell.append(Spacer(1, 4))
            left_cell.append(detectado_img)

        right_cell = [
            Paragraph("RESPUESTA DEL ENCARGADO", label),
            Paragraph(_fmt_fecha(item.get("respuesta_at")), small),
        ]
        comentario = item.get("respuesta_comentario")
        if comentario:
            right_cell.append(Spacer(1, 3))
            right_cell.append(Paragraph(comentario, body))
        if respuesta_img:
            right_cell.append(Spacer(1, 4))
            right_cell.append(respuesta_img)
        if not comentario and not respuesta_img:
            right_cell.append(Spacer(1, 3))
            right_cell.append(Paragraph("Sin detalle registrado.", small))

        compare_table = Table([[left_cell, right_cell]], colWidths=[usable_w / 2, usable_w / 2])
        compare_table.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("LINEAFTER",     (0, 0), (0, -1), 0.5, LINE),
            ("GRID",          (0, 0), (-1, -1), 0.5, LINE),
        ]))
        item_flowables.append(compare_table)

        item_flowables.append(Spacer(1, 3))
        item_flowables.append(Paragraph(f"Tiempo de respuesta: {_fmt_horas(horas)}", caption))

        story.append(KeepTogether(item_flowables))
        story.append(Spacer(1, 14))

    doc.build(story)
    result = buf.getvalue()
    buf.close()
    return result
