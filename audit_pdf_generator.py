"""Generate PDF audit reports with ReportLab."""

import logging
from datetime import datetime
from typing import Optional, Dict, List
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from audit_session import AuditSession, BLOQUE_LABELS, BRAND_LABELS

logger = logging.getLogger(__name__)


def generate_audit_pdf(
    session: AuditSession,
    sucursal_nombre: str,
    auditor_nombre: Optional[str] = None,
    responsable_desvios: Optional[str] = None,
) -> bytes:
    """Generate PDF audit report.

    Args:
        session: AuditSession with all audit data
        sucursal_nombre: Name of the sucursal
        auditor_nombre: Auditor name (optional, from session)
        responsable_desvios: Name of person responsible for deviations

    Returns:
        PDF file bytes
    """

    # Create PDF in memory
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # Header
    header_style = ParagraphStyle(
        "CustomHeader",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#1e40af"),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    story.append(Paragraph("AUDITORÍA OPERATIVA PERFUMERÍA", header_style))
    story.append(Paragraph("Control para la Mejora Continua", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    # Audit Info Table
    audit_date = datetime.fromisoformat(session.started_at).strftime("%d/%m/%Y %H:%M")
    auditor = auditor_nombre or session.auditor_nombre or "No especificado"

    info_data = [
        ["SUCURSAL:", sucursal_nombre],
        ["AUDITOR:", auditor],
        ["FECHA:", audit_date],
        ["RESPONSABLE DESVÍOS:", responsable_desvios or "No especificado"],
        ["ID AUDITORÍA:", session.id_sesion],
    ]

    info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0e7ff")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 0.2 * inch))

    # Scores Table
    story.append(Paragraph("PUNTUACIONES POR BLOQUE", styles["Heading2"]))
    story.append(Spacer(1, 0.1 * inch))

    score_data = [["BLOQUE", "PUNTUACIÓN", "EVALUACIÓN"]]

    score_labels = {
        1: "Muy malo",
        2: "Malo",
        3: "Regular",
        4: "Bueno",
        5: "Excelente",
    }

    for bloque in session.bloques:
        score = session.bloques[bloque]
        bloque_label = BLOQUE_LABELS.get(bloque, bloque)
        eval_label = score_labels.get(score, "")

        score_data.append([bloque_label, f"{score}/5", eval_label])

    # Add overall score
    if session.bloques:
        avg_score = sum(session.bloques.values()) / len(session.bloques)
        score_data.append(["PROMEDIO GENERAL", f"{avg_score:.1f}/5", score_labels.get(round(avg_score), "")])

    score_table = Table(score_data, colWidths=[3 * inch, 1.2 * inch, 1.8 * inch])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b82f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f9ff")]),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 0.2 * inch))

    # Desvios/Findings
    if session.desvios:
        story.append(Paragraph(f"DESVÍOS ENCONTRADOS ({len(session.desvios)})", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))

        desvios_data = [["BLOQUE", "DESCRIPCIÓN", "FOTOS"]]

        for desvio in session.desvios:
            bloque_label = BLOQUE_LABELS.get(desvio.bloque, desvio.bloque)
            foto_count = len(desvio.fotos)
            desvios_data.append([
                bloque_label,
                desvio.descripcion[:60] + "..." if len(desvio.descripcion) > 60 else desvio.descripcion,
                f"{foto_count}" if foto_count > 0 else "-",
            ])

        desvios_table = Table(desvios_data, colWidths=[1.5 * inch, 3.5 * inch, 0.8 * inch])
        desvios_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dc2626")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (2, 0), (2, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fee2e2")]),
                ]
            )
        )
        story.append(desvios_table)
        story.append(Spacer(1, 0.2 * inch))

    # Evidence Summary
    story.append(Paragraph("EVIDENCIA RECOLECTADA", styles["Heading2"]))
    story.append(Spacer(1, 0.1 * inch))

    evidence_data = [
        ["Fotos capturadas:", str(len(session.fotos))],
        ["Notas/Textos:", str(len([d for d in session.desvios if "[AUDIO]" not in d.descripcion]))],
        ["Audios:", str(len([d for d in session.desvios if "[AUDIO]" in d.descripcion]))],
    ]

    evidence_table = Table(evidence_data, colWidths=[2 * inch, 1 * inch])
    evidence_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0e7ff")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
            ]
        )
    )
    story.append(evidence_table)
    story.append(Spacer(1, 0.3 * inch))

    # Footer
    story.append(Paragraph("_" * 80, styles["Normal"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Firma Auditor", ParagraphStyle("FooterLeft", parent=styles["Normal"], fontSize=9)))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph("Firma Encargado", ParagraphStyle("FooterRight", parent=styles["Normal"], fontSize=9)))

    # Build PDF
    doc.build(story)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    return pdf_bytes
