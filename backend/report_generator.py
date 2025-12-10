
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import datetime
import matplotlib.pyplot as plt

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
    story = []

    # Title
    title_style = styles['Title']
    story.append(Paragraph("N42 Spectrum Analysis Report", title_style))
    story.append(Spacer(1, 12))

    # Metadata Section
    story.append(Paragraph("<b>Metadata</b>", styles['Heading2']))
    meta_data = [["Property", "Value"]]
    
    # Add filename and timestamp
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

    # Spectrum Plot
    # We need to generate the plot using matplotlib and save it to a buffer
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
        
        img = Image(img_buffer, width=6*inch, height=3*inch)
        story.append(img)
        story.append(Spacer(1, 12))
    except Exception as e:
        story.append(Paragraph(f"<i>Error generating plot: {str(e)}</i>", styles['Normal']))
        story.append(Spacer(1, 12))

    # Isotopes Section
    if "isotopes" in data and data["isotopes"]:
        story.append(Paragraph("<b>Identified Isotopes</b>", styles['Heading2']))
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

    # Peaks Section (Top 20)
    if "peaks" in data and data["peaks"]:
        story.append(Paragraph("<b>Detected Peaks (Top 20 by Energy)</b>", styles['Heading2']))
        # Sort by energy
        sorted_peaks = sorted(data["peaks"], key=lambda x: x.get("energy", 0))[:20]
        
        peak_data = [["Energy (keV)", "Counts", "FWHM (keV)", "Net Area"]]
        for p in sorted_peaks:
            # Handle both raw peaks and fitted peaks if available
            # If the dict has 'fwhm', it's fitted. If not, maybe just 'energy' and 'counts'
            fwhm = p.get("fwhm", "-")
            net_area = p.get("net_area", "-")
            if isinstance(fwhm, (int, float)): fwhm = f"{fwhm:.2f}"
            if isinstance(net_area, (int, float)): net_area = f"{net_area:.0f}"
            
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

    # Footer
    story.append(Spacer(1, 24))
    story.append(Paragraph("<i>Generated by N42 Viewer</i>", styles['Normal']))

    doc.build(story)
    return buffer.getvalue()
