
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import io
import datetime
import matplotlib
matplotlib.use("Agg")  # headless: reports render on server worker threads, never a GUI
import matplotlib.pyplot as plt

def _metadata_section(data, styles):
    story = [Paragraph("<b>Metadata</b>", styles['Heading2'])]
    meta_data = [["Property", "Value"]]

    # report time, then whatever the spectrum's metadata holds
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_data.append(["Report Generated", timestamp])

    if "metadata" in data:
        for k, v in data["metadata"].items():
            meta_data.append([str(k), str(v)])

    t_meta = Table(meta_data, colWidths=[2.5*inch, 4*inch])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))
    return story


def _plot_section(data, styles):
    """The spectrum plot (matplotlib, rendered to a PNG in memory); a failure becomes a note in the report."""
    story = []
    try:
        story.append(Paragraph("<b>Spectrum Plot</b>", styles['Heading2']))
        plt.figure(figsize=(8, 4))
        plt.plot(data["energies"], data["counts"], label="Spectrum", color="#38bdf8", linewidth=1)
        plt.xlabel("Energy (keV)")
        plt.ylabel("Counts")
        plt.title("Gamma Spectrum")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150)
        img_buffer.seek(0)
        plt.close()

        story.append(Image(img_buffer, width=6*inch, height=3*inch))
        story.append(Spacer(1, 12))
    except Exception as e:
        story.append(Paragraph(f"<i>Error generating plot: {str(e)}</i>", styles['Normal']))
        story.append(Spacer(1, 12))
    return story


def _isotope_section(data, styles):
    if not ("isotopes" in data and data["isotopes"]):
        return []
    story = [Paragraph("<b>Identified Isotopes</b>", styles['Heading2'])]
    iso_data = [["Isotope", "Confidence (%)", "Matches"]]
    for iso in data["isotopes"]:
        iso_data.append([
            iso.get("isotope", "Unknown"),
            f"{iso.get('confidence', 0):.1f}",
            f"{iso.get('matches', 0)}/{iso.get('total_lines', 0)}"
        ])

    t_iso = Table(iso_data, colWidths=[2*inch, 2*inch, 2*inch])
    t_iso.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.aliceblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(t_iso)
    story.append(Spacer(1, 12))
    return story


def _decay_chain_section(data, styles):
    if not ("decay_chains" in data and data["decay_chains"]):
        return []
    story = [Paragraph("<b>Detected Decay Chains</b>", styles['Heading2'])]
    for chain in data["decay_chains"]:
        chain_title = f"{chain.get('chain_name', 'Unknown')} - {chain.get('confidence_level', 'UNKNOWN')} ({chain.get('confidence', 0):.0f}%)"
        story.append(Paragraph(f"<b>{chain_title}</b>", styles['Heading3']))

        members_text = f"Detected: {chain.get('num_detected', 0)}/{chain.get('num_key_isotopes', 0)} key indicators"
        story.append(Paragraph(members_text, styles['Normal']))

        if chain.get('applications'):
            apps_text = "<b>Likely Sources:</b> " + ", ".join(chain['applications'][:3])
            story.append(Paragraph(apps_text, styles['Normal']))

        story.append(Spacer(1, 6))
    story.append(Spacer(1, 12))
    return story


def _peak_section(data, styles):
    """The first 20 peaks by energy: energy, counts, and the fitted FWHM and net area where the peak was fitted."""
    if not ("peaks" in data and data["peaks"]):
        return []
    story = [Paragraph("<b>Detected Peaks (Top 20 by Energy)</b>", styles['Heading2'])]
    sorted_peaks = sorted(data["peaks"], key=lambda x: x.get("energy", 0))[:20]

    peak_data = [["Energy (keV)", "Counts", "FWHM (keV)", "Net Area"]]
    for p in sorted_peaks:
        # raw peaks have only energy and counts; fitted ones also have fwhm and net_area
        fwhm = p.get("fwhm", "-")
        net_area = p.get("net_area", "-")
        if isinstance(fwhm, (int, float)):
            fwhm = f"{fwhm:.2f}"
        if isinstance(net_area, (int, float)):
            net_area = f"{net_area:.0f}"

        peak_data.append([
            f"{p.get('energy', 0):.2f}",
            f"{p.get('counts', 0):.0f}",
            str(fwhm),
            str(net_area)
        ])

    t_peak = Table(peak_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    t_peak.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(t_peak)
    return story


def generate_pdf_report(data):
    """
    Generate a PDF report for the spectrum data.

    Args:
        data (dict): Dictionary containing spectrum data (filename, metadata, peaks, isotopes, etc.)

    Returns:
        bytes: PDF file content
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    story = [Paragraph("N42 Spectrum Analysis Report", styles['Title']), Spacer(1, 12)]
    story += _metadata_section(data, styles)
    story += _plot_section(data, styles)
    story += _isotope_section(data, styles)
    story += _decay_chain_section(data, styles)
    story += _peak_section(data, styles)
    story += [Spacer(1, 24), Paragraph("<i>Generated by N42 Viewer</i>", styles['Normal'])]

    doc.build(story)
    return buffer.getvalue()
