"""Generate PDF audit reports with ReportLab."""

import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    Image as RLImage,
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

        # Build foto lookup: foto_id -> FotoEvidence
        foto_map = {f.id: f for f in session.fotos}

        for idx, desvio in enumerate(session.desvios, 1):
            bloque_label = BLOQUE_LABELS.get(desvio.bloque, desvio.bloque)
            score = session.bloques.get(desvio.bloque, 0)
            sc = _score_color(score)

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
            story.append(hdr)

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
            story.append(desc_table)

            # Fotos
            if photo_bytes and desvio.fotos:
                max_img_w = (usable_w - 0.3 * cm) / 2  # 2 columns
                max_img_h = 5 * cm
                images = []
                for foto_id in desvio.fotos:
                    raw = photo_bytes.get(foto_id)
                    if raw:
                        img = _rl_image(raw, max_img_w, max_img_h)
                        if img:
                            images.append(img)

                if images:
                    # Pad to even count for 2-column grid
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
                    story.append(photo_table)
                    story.append(Paragraph(
                        f"{len([x for x in images if x])} foto(s) de evidencia", small
                    ))

            story.append(Spacer(1, 8))

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
