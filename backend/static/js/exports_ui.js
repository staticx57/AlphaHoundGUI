import { api } from './api.js';
import { notifyAuto } from './dialogs.js';
import { n42MetadataEditor } from './n42_editor.js';
import { chnAvailability } from './export_support.js';

/**
 * PDF and N42 export and the N42 metadata editor buttons.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.ui
 * @param {*} deps.getCurrentData
 */
export function setupExports({ ui, getCurrentData } = {}) {
    // PDF Export
    document.getElementById('btn-export-pdf').addEventListener('click', async () => {
        if (!getCurrentData()) return;
        const btn = document.getElementById('btn-export-pdf');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Generating...';
        btn.disabled = true;

        try {
            const response = await fetch('/export/pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: getCurrentData().metadata?.filename || 'spectrum',
                    metadata: getCurrentData().metadata || {},
                    energies: getCurrentData().energies,
                    counts: getCurrentData().counts,
                    peaks: getCurrentData().peaks || [],
                    isotopes: getCurrentData().isotopes || [],
                    decay_chains: getCurrentData().decay_chains || []
                })
            });

            if (!response.ok) throw new Error('PDF generation failed');

            // Download it: window.open() after an await is blocked as a pop-up by many browsers, and a URL revoked after
            // one second can leave the new tab empty.
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const base = String(getCurrentData().metadata?.filename || 'spectrum').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, '_');
            const link = document.createElement('a');
            link.href = url;
            link.download = `${base || 'spectrum'}_report.pdf`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => window.URL.revokeObjectURL(url), 30000);
        } catch (err) {
            notifyAuto('Error generating PDF: ' + err.message);
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });

    // N42 Export
    document.getElementById('btn-export-n42').addEventListener('click', async () => {
        if (!getCurrentData()) {
            notifyAuto('No spectrum data to export');
            return;
        }

        const btn = document.getElementById('btn-export-n42');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Exporting...';
        btn.disabled = true;

        try {
            const response = await api.exportN42({
                ...getCurrentData(),
                // Ensure we use the best metadata available (including potential edits)
                metadata: {
                    ...getCurrentData().metadata,
                    // Ensure critical fields are set if missing
                    live_time: getCurrentData().metadata?.live_time || getCurrentData().metadata?.acquisition_time || 1.0,
                    real_time: getCurrentData().metadata?.real_time || getCurrentData().metadata?.acquisition_time || 1.0,
                    start_time: getCurrentData().metadata?.start_time || new Date().toISOString(),
                    source: getCurrentData().metadata?.source || 'AlphaHound Device',
                    channels: getCurrentData().counts.length
                }
            });

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            // Use existing filename or generate one
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            a.download = (getCurrentData().metadata?.filename || `spectrum_export_${timestamp}`).replace('.n42', '') + '.n42';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            // Revert button
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        } catch (err) {
            notifyAuto('Error exporting N42: ' + err.message);
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });

    // CHN holds only a quadratic energy axis: say so on the button before it is clicked, for the AlphaHound's cubic axis
    const chnButton = document.getElementById('btn-export-chn');
    const defaultChnTitle = chnButton?.title || '';
    document.addEventListener('spectrum-rendered', (e) => {
        if (!chnButton) return;
        const { ok, reason } = chnAvailability(e.detail?.energies);
        chnButton.disabled = !ok;
        chnButton.title = ok ? defaultChnTitle : reason;
    });

    // PCF (GADRAS, InterSpec) and CHN (Ortec) export
    for (const format of ['pcf', 'chn']) {
        const btn = document.getElementById(`btn-export-${format}`);
        btn?.addEventListener('click', async () => {
            const data = getCurrentData();
            if (!data) return notifyAuto('No spectrum data to export');
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Exporting...';
            btn.disabled = true;
            try {
                const meta = data.metadata || {};
                const response = await api.exportSpectrumFile(format, {
                    counts: data.counts,
                    energies: data.energies,
                    filename: meta.filename || 'spectrum',
                    metadata: { ...meta, start_time: meta.start_time || new Date().toISOString(), source: meta.source || 'AlphaHound Device' }
                });
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const base = String(meta.filename || `spectrum_export_${new Date().toISOString().replace(/[:.]/g, '-')}`)
                    .replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, '_');
                const link = document.createElement('a');
                link.href = url;
                link.download = `${base || 'spectrum'}.${format}`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(() => window.URL.revokeObjectURL(url), 30000);

                const error = parseFloat(response.headers.get('X-Calibration-Max-Error-keV'));
                if (error > 0.5) {
                    notifyAuto(`Warning: ${format.toUpperCase()} stores the energy axis as a quadratic, which is up to ${error.toFixed(1)} keV off this spectrum's axis.`);
                }
            } catch (err) {
                notifyAuto(`Error exporting ${format.toUpperCase()}: ${err.message}`);
            } finally {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });
    }

    // Edit N42 Metadata Button
    const btnEditN42 = document.getElementById('btn-edit-n42');
    btnEditN42?.addEventListener('click', async () => {
        if (!getCurrentData()) return ui.showError('No spectrum loaded to edit');

        // Prevent multiple simultaneous clicks
        if (btnEditN42.disabled) return;

        // Use stored raw XML or generate it
        let xmlContent = getCurrentData()._rawXml;

        if (!xmlContent) {
            // Generate template from current data
            const toast = document.createElement('div');
            toast.textContent = 'Generating metadata template...';
            toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#3b82f6;color:white;padding:12px 24px;border-radius:8px;z-index:9999;box-shadow:0 4px 6px rgba(0,0,0,0.1);';
            document.body.appendChild(toast);

            // declared before the try: the catch below restores the button from it too
            const originalHtml = btnEditN42.innerHTML;
            try {
                // Set loading state
                btnEditN42.disabled = true;
                btnEditN42.style.opacity = '0.7';
                btnEditN42.innerHTML = '<span class="spinner-inline"></span> Generating...';

                // We use export_n42 logic to generate the XML string
                const response = await api.exportN42({
                    ...getCurrentData(),
                    metadata: getCurrentData().metadata || {}
                });
                if (response.ok) {
                    xmlContent = await response.text();
                    getCurrentData()._rawXml = xmlContent;
                }

                // Restore button
                btnEditN42.disabled = false;
                btnEditN42.style.opacity = '1';
                btnEditN42.innerHTML = originalHtml;
            } catch (e) {
                console.error(e);
                btnEditN42.disabled = false;
                btnEditN42.style.opacity = '1';
                btnEditN42.innerHTML = originalHtml;
            }
            toast.remove();
        }

        if (xmlContent) {
            n42MetadataEditor.show(xmlContent, (newXml) => {
                getCurrentData()._rawXml = newXml;

                // Show success message
                const toast = document.createElement('div');
                toast.textContent = 'N42 Metadata Updated';
                toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#10b981;color:white;padding:12px 24px;border-radius:8px;z-index:9999;box-shadow:0 4px 6px rgba(0,0,0,0.1);animation: slideIn 0.3s ease-out;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            });
        } else {
            ui.showError('Could not initialize N42 editor');
        }
    });
}
