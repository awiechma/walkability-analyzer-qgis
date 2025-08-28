import os
import tempfile
from datetime import datetime

from qgis.core import (
    QgsMessageLog, Qgis, QgsProject, QgsMapSettings, QgsMapRendererParallelJob,
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtWidgets import QMessageBox

# --- Force Reportlab ---
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    )
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_CENTER
except ImportError:
    msg = (
        "ReportLab ist nicht installiert – der PDF-Export kann nicht ausgeführt werden.\n\n"
        "Installationshinweise:\n"
        "• Windows (OSGeo4W Shell):\n"
        "    python3 -m pip install --user reportlab\n"
        "• Linux:\n"
        "    python3 -m pip install --user reportlab\n"
        "  oder (Debian/Ubuntu):\n"
        "    sudo apt-get install python3-reportlab\n"
    
        "Bitte QGIS anschließend neu starten."
    )
    QMessageBox.critical(None, "Walkability Analyzer – PDF-Export", msg)
    QgsMessageLog.logMessage("ReportLab not available – aborting PDF export.", "Walkability", Qgis.Critical)
    raise

# ======================================================================
# Public Export Function
# ======================================================================

def export_walkability_pdf(analysis_data, output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'], fontSize=20, spaceAfter=14,
        alignment=TA_CENTER, textColor=colors.HexColor("#0f4068")
    )
    heading_style = ParagraphStyle(
        'Heading', parent=styles['Heading2'], fontSize=14, spaceAfter=10,
        textColor=colors.HexColor("#0f4068")
    )
    sub_style = ParagraphStyle('Subtle', parent=styles['Normal'], fontSize=9, textColor=colors.grey)

    story = []
    story.extend(_pdf_header(analysis_data, title_style, styles))

    map_img_path = _grab_current_canvas_png()
    if not map_img_path:
        QgsMessageLog.logMessage("Kein Canvas-Screenshot – nutze Offscreen-Fallback.", "Walkability", Qgis.Warning)
        map_img_path = _render_offscreen_fallback_png(analysis_data)

    if map_img_path and os.path.exists(map_img_path):
        story.append(Spacer(1, 6))
        story.append(Paragraph("Kartenausschnitt", heading_style))
        story.append(Spacer(1, 4))
        story.append(_rl_image_scaled(map_img_path, target_width_cm=17))
        story.append(Spacer(1, 6))

        legend_tbl = _build_pdf_legend(analysis_data, styles)
        if legend_tbl:
            story.append(legend_tbl)
            story.append(Spacer(1, 8))

        story.append(Paragraph("Hinweis: Der Kartenausschnitt entspricht der aktuellen Ansicht in QGIS.", sub_style))
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 12))
    else:
        QgsMessageLog.logMessage("PDF Export: Kein Kartenbild – Karte wird ausgelassen.", "Walkability", Qgis.Warning)

    story.extend(_pdf_summary(analysis_data, heading_style, styles))
    story.extend(_pdf_detailed_results(analysis_data, heading_style, styles))
    story.extend(_pdf_service_details(analysis_data, heading_style, styles))
    story.extend(_pdf_recommendations(analysis_data, heading_style, styles))
    story.extend(_pdf_footer(styles))

    doc.build(story)
    QgsMessageLog.logMessage(f"PDF successfully created: {output_path}", "Walkability", Qgis.Info)

# ======================================================================
# Map
# ======================================================================

def _grab_current_canvas_png(width_px=1800, height_px=1100):
    try:
        canvas = iface.mapCanvas() if iface else None
        if not canvas:
            QgsMessageLog.logMessage("Kein aktives MapCanvas verfügbar.", "Walkability", Qgis.Warning)
            return None

        img = QImage(canvas.size(), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        canvas.render(painter)
        painter.end()

        if width_px and height_px:
            img = img.scaled(width_px, height_px, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        if not img.save(tmp.name, "PNG"):
            QgsMessageLog.logMessage("Canvas: Speichern des Screenshots fehlgeschlagen.", "Walkability", Qgis.Warning)
            return None

        return tmp.name
    except Exception as e:
        QgsMessageLog.logMessage(f"Canvas grab error: {e}", "Walkability", Qgis.Critical)
        return None


def _render_offscreen_fallback_png(analysis_data, width_px=1600, height_px=1000, bg_color=Qt.white):
    try:
        layers = (analysis_data.get("layers") or {})
        render_layers = [l for l in (layers.get("isochrone"), layers.get("pois"), layers.get("center")) if l and l.isValid()]
        if not render_layers:
            return None

        proj = QgsProject.instance()
        dest_crs = proj.crs() if proj and proj.crs().isValid() else render_layers[0].crs()

        extent = None
        for lyr in render_layers:
            try:
                e = lyr.extent()
                extent = e if extent is None else extent.united(e)
            except Exception:
                pass
        if extent is None or extent.isEmpty():
            return None

        ms = QgsMapSettings()
        ms.setLayers(render_layers)
        ms.setDestinationCrs(dest_crs)
        ms.setTransformContext(proj.transformContext())
        ms.setBackgroundColor(bg_color)
        ms.setOutputSize(QSize(width_px, height_px))
        ms.setExtent(extent)

        job = QgsMapRendererParallelJob(ms)
        job.start(); job.waitForFinished()

        img = job.renderedImage()
        if img is None or img.isNull():
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        if not img.save(tmp.name, "PNG"):
            return None
        return tmp.name
    except Exception as e:
        QgsMessageLog.logMessage(f"Offscreen fallback error: {e}", "Walkability", Qgis.Warning)
        return None

# ======================================================================
# Legend for PDF
# ======================================================================

def _build_pdf_legend(analysis_data, styles):
    try:
        POI_COLOR_MAP = {
            'Supermarkt': '#228B22',
            'Apotheke':   '#DC143C',
            'Arzt':       '#4169E1',
            'Schule':     '#FF8C00',
            'Restaurant': '#8A2BE2',
            'Bank':       '#B8860B',
        }

        layers = analysis_data.get("layers") or {}
        pois = layers.get("pois")
        present_labels = []

        if pois and pois.isValid() and pois.renderer():
            try:
                cats = getattr(pois.renderer(), "categories", lambda: [])()
                if cats:
                    present_labels = [str(c.label()) for c in cats]
            except Exception:
                present_labels = []

        if not present_labels:
            present_labels = list(analysis_data.get("service_types", []))

        entries = [(POI_COLOR_MAP[label], f"POI: {label}") for label in POI_COLOR_MAP.keys() if label in present_labels]
        if not entries:
            return None

        data = [["", "Layer"]] + [["", label] for _, label in entries]
        table = Table(data, colWidths=[0.8 * cm, 15.2 * cm])
        ts = [
            ('FONTNAME', (1, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#efefef")),
        ]
        for row_idx, (hexcol, _) in enumerate(entries, start=1):
            try:
                ts.append(('BACKGROUND', (0, row_idx), (0, row_idx), colors.HexColor(hexcol)))
            except Exception:
                ts.append(('BACKGROUND', (0, row_idx), (0, row_idx), colors.black))

        table.setStyle(TableStyle(ts))
        return table
    except Exception as e:
        QgsMessageLog.logMessage(f"Legend build error: {e}", "Walkability", Qgis.Warning)
        return None

# ======================================================================
# PDF-Blocks
# ======================================================================

def _rl_image_scaled(path, target_width_cm=17):
    try:
        img = RLImage(path)
        img._restrictSize(target_width_cm * cm, 10000 * cm)
        img.hAlign = 'CENTER'
        return img
    except Exception:
        return RLImage(path, width=target_width_cm * cm)


def _pdf_header(analysis_data, title_style, styles):
    story = [Paragraph("Walkability Analyse", title_style), Spacer(1, 10)]
    coords = analysis_data.get('coordinates') or [0, 0]
    time_limit = analysis_data.get('time_limit', 15)
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    info_data = [
        ["Standort:", f"{coords[1]:.4f}, {coords[0]:.4f}"],
        ["Maximale Gehzeit:", f"{time_limit} Minuten"],
        ["Analyse-Zeitpunkt:", timestamp],
    ]

    table = Table(info_data, colWidths=[5 * cm, 10.5 * cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story += [table, Spacer(1, 10), HRFlowable(width="100%", thickness=1, color=colors.lightgrey), Spacer(1, 10)]
    return story


def _pdf_summary(analysis_data, heading_style, styles):
    story = [Paragraph("Zusammenfassung", heading_style)]
    score_data = analysis_data.get('score', {})
    total_score = float(score_data.get('total_score', 0))

    if total_score >= 80:
        rating, badge = "Sehr gute Walkability", colors.HexColor("#3cb371")
    elif total_score >= 60:
        rating, badge = "Gute Walkability", colors.HexColor("#ffa500")
    elif total_score >= 40:
        rating, badge = "Durchschnittliche Walkability", colors.HexColor("#f0e68c")
    else:
        rating, badge = "Schwache Walkability", colors.HexColor("#dc143c")

    summary_data = [
        ["Walkability Score", f"{total_score:.1f}/100"],
        ["Bewertung", rating],
        ["Gefundene Services (gesamt)", str(score_data.get('total_services', 0))],
        ["Analysierte Service-Typen", str(len(analysis_data.get('service_types', [])))],
    ]

    t = Table(summary_data, colWidths=[8 * cm, 7.5 * cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('BACKGROUND', (0, 1), (-1, 1), badge),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e6f2ff")),
    ]))
    story += [t, Spacer(1, 12)]
    return story


def _pdf_detailed_results(analysis_data, heading_style, styles):
    story = [Paragraph("Detaillierte Ergebnisse", heading_style)]
    score_data = analysis_data.get('score', {})

    rows = [["Service-Typ", "Anzahl", "Nächste (m)", "Score", "Gewicht"]]
    for st, s in (score_data.get('service_scores') or {}).items():
        nearest_m = s.get('nearest_m', -1.0)
        rows.append([
            st,
            f"{s.get('count', 0)}",
            "–" if nearest_m is None or nearest_m < 0 else f"{nearest_m:.0f}",
            f"{s.get('raw_score', 0.0):.1f}",
            f"{s.get('weight', 1.0):.2f}",
        ])

    t = Table(rows, colWidths=[6.5 * cm, 2.0 * cm, 3.0 * cm, 2.5 * cm, 1.5 * cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#efefef")),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
    ]))
    story += [t, Spacer(1, 12)]
    return story


def _pdf_service_details(analysis_data, heading_style, styles):
    story = [Paragraph("Service-Details", heading_style)]
    services = analysis_data.get('services', {})
    for st, pois in (services or {}).items():
        if not pois:
            continue
        story.append(Paragraph(f"{st} ({len(pois)} gefunden):", styles['Heading3']))
        shown = min(10, len(pois))
        for i in range(shown):
            poi = pois[i] or {}
            name = poi.get('name') or 'Unbenannt'
            subtype = poi.get('osm_type') or poi.get('type', '')
            text = name + (f" ({subtype})" if subtype else "")
            story.append(Paragraph(text, styles['Normal']))
        if len(pois) > shown:
            story.append(Paragraph(f"… und {len(pois) - shown} weitere", styles['Normal']))
        story.append(Spacer(1, 6))
    story.append(Spacer(1, 6))
    return story


def _pdf_recommendations(analysis_data, heading_style, styles):
    story = [Paragraph("Empfehlungen", heading_style)]

    score = analysis_data.get('score', {}) or {}
    total = float(score.get('total_score', 0.0))

    if total >= 80:
        general = "Sehr gute Walkability mit breiter Service-Abdeckung."
    elif total >= 60:
        general = "Gute Walkability. Insgesamt solide Abdeckung; kleinere Ergänzungen sind sinnvoll."
    elif total >= 40:
        general = "Durchschnittliche Walkability. Zusätzliche Angebote würden die Lage verbessern."
    else:
        general = "Schwache Walkability. Deutliche Verbesserungen in der Service-Infrastruktur sind erforderlich."

    story.append(Paragraph(general, styles['Normal']))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Spezifische Vorschläge:", styles['Heading4']))

    svc_scores = score.get('service_scores', {}) or {}
    rec_lines = []

    for st, s in svc_scores.items():
        c = int(s.get('count', 0))
        if c < 1:
            rec_lines.append(f"{st}: Mindestens eine Einrichtung im Einzugsgebiet wäre wünschenswert.")
        elif c == 1:
            rec_lines.append(f"{st}: Grundversorgung vorhanden; mehr Auswahl würde den Score verbessern.")

    if svc_scores:
        worst_st, worst = min(svc_scores.items(), key=lambda kv: float(kv[1].get('raw_score', 0.0)))
        rec_lines.append(f"Priorität: {worst_st} hat den niedrigsten Score ({float(worst.get('raw_score', 0.0)):.1f}/100). Angebot ausbauen.")

    if not rec_lines:
        rec_lines = ["Allgemein: Service-Vielfalt erhöhen (keine spezifischen Defizite erkannt)."]

    from reportlab.platypus import ListFlowable, ListItem
    bullets = ListFlowable(
        [ListItem(Paragraph(text, styles['Normal'])) for text in rec_lines],
        bulletType='bullet', start='•'
    )
    story.append(bullets)
    story.append(Spacer(1, 10))
    return story


def _pdf_footer(styles):
    story = [
        HRFlowable(width="100%", thickness=1, color=colors.lightgrey),
        Spacer(1, 8),
    ]
    footer_text = (
        "<b>Walkability Analyzer</b><br/>"
        "QGIS Plugin – OpenRouteService & OpenStreetMap<br/>"
        "Analyse basiert auf Fußgänger-Isochronen und OSM-POI-Daten<br/>"
        f"<i>Generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}</i>"
    )
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.grey)
    story.append(Paragraph(footer_text, footer_style))
    return story
