import { notifyAuto } from './dialogs.js';
import { escapeHtml } from './html.js';
import { spectrumSignature } from './summary.js';

/**
 * The analysis panel, peak fitting, AI identification and the peaks toggle.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.ui
 * @param {*} deps.isCompareMode
 * @param {*} deps.getCurrentData
 */
export function setupAnalysisPanels({ ui, isCompareMode, getCurrentData } = {}) {
    // Analysis Panel Toggle
    document.getElementById('btn-analysis').addEventListener('click', () => {
        const panel = document.getElementById('analysis-panel');
        const btn = document.getElementById('btn-analysis');
        const isOpen = panel.style.display !== 'none';

        panel.style.display = isOpen ? 'none' : 'flex';
        if (isOpen) {
            btn.classList.remove('active');
        } else {
            btn.classList.add('active');
            // Close compare if open
            if (isCompareMode()) document.getElementById('btn-compare').click();
        }
    });

    // Peak Fitting
    document.getElementById('btn-run-fit').addEventListener('click', async () => {
        if (!getCurrentData() || !getCurrentData().peaks) return;
        const resultsContainer = document.getElementById('analysis-results');
        resultsContainer.innerHTML = '<p>Fitting peaks...</p>';

        try {
            const response = await fetch('/analyze/fit-peaks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    energies: getCurrentData().energies,
                    counts: getCurrentData().counts,
                    peaks: getCurrentData().peaks
                })
            });

            if (!response.ok) throw new Error('Analysis failed');
            const data = await response.json();

            if (data.fits && data.fits.length > 0) {
                resultsContainer.innerHTML = `
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9rem;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-color); text-align: left;">
                                <th style="padding: 4px;">Energy</th>
                                <th style="padding: 4px;">FWHM</th>
                                <th style="padding: 4px;">Net Area</th>
                                <th style="padding: 4px;">Resolution</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.fits.map(fit => {
                    const res = (fit.fwhm / fit.energy) * 100;
                    return `
                                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                        <td style="padding: 4px;">${fit.energy.toFixed(2)} keV</td>
                                        <td style="padding: 4px;">${fit.fwhm.toFixed(2)} keV</td>
                                        <td style="padding: 4px;">${fit.net_area.toFixed(0)}</td>
                                        <td style="padding: 4px;">${res.toFixed(1)}%</td>
                                    </tr>
                                `;
                }).join('')}
                        </tbody>
                    </table>
                `;
            } else {
                resultsContainer.innerHTML = '<p>No peaks fitted successfully.</p>';
            }
        } catch (err) {
            resultsContainer.innerHTML = `<p style="color: #ef4444;">Error: ${escapeHtml(err.message)}</p>`;
        }
    });

    // ML Identification: one request path for every button (analysis panel, isotopes box, summary card)
    const aiTableHtml = (data) => {
        const quality = data.quality || 'unknown';
        const qualityColors = { good: '#10b981', moderate: '#f59e0b', low_confidence: '#ef4444', no_match: '#6b7280' };
        const qualityLabels = {
            good: '<img src="/static/icons/check.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> High Confidence',
            moderate: '<img src="/static/icons/warning.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> Moderate',
            low_confidence: '<img src="/static/icons/warning.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> Low Confidence',
            no_match: '? No Match'
        };
        const badge = quality !== 'unknown' ?
            `<span style="color: ${qualityColors[quality]}; font-size: 0.8rem; margin-left: 0.5rem;">${qualityLabels[quality]}</span>` : '';
        return `
            <h4 style="margin-top: 0;">ML Predictions${badge}</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                <thead>
                    <tr style="border-bottom: 1px solid var(--border-color); text-align: left;">
                        <th style="padding: 4px;">Isotope</th>
                        <th style="padding: 4px;">Confidence</th>
                        <th style="padding: 4px;">Method</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.predictions.map(pred => `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); ${pred.suppressed ? 'opacity: 0.5;' : ''}">
                            <td style="padding: 4px;"><strong>${pred.isotope}</strong>${pred.suppressed ? ' <span style="font-size:0.7rem;color:#ef4444;">(suppressed)</span>' : ''}</td>
                            <td style="padding: 4px;">${pred.confidence.toFixed(1)}%</td>
                            <td style="padding: 4px;">${pred.method}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            <p style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem;">
                Note: First run trains the model (~10-30s). Subsequent runs are instant.
            </p>
        `;
    };

    let aiRunning = false;
    /** @param {{table?: boolean}} [opts] table: also write the full predictions table into the analysis panel */
    async function runAiIdentify({ table = false } = {}) {
        if (!getCurrentData() || !getCurrentData().counts) return notifyAuto('No spectrum data loaded');
        if (aiRunning) return;
        aiRunning = true;
        const signature = spectrumSignature(getCurrentData().counts);
        const tableBox = document.getElementById('analysis-results');
        const runButton = document.getElementById('btn-run-ml');
        const original = runButton ? runButton.innerHTML : '';
        if (runButton) {
            runButton.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 16px; height: 16px;"> Running...';
            runButton.disabled = true;
        }
        ui.setAiState({ status: 'running', signature });
        if (table && tableBox) tableBox.innerHTML = '<p>Running AI identification...</p>';
        try {
            const response = await fetch('/analyze/ml-identify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ counts: getCurrentData().counts, energies: getCurrentData().energies })
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'ML identification failed');
            }
            const data = await response.json();
            ui.setAiState({ status: 'done', predictions: data.predictions || [], quality: data.quality, signature });
            if (table && tableBox) {
                tableBox.innerHTML = data.predictions && data.predictions.length
                    ? aiTableHtml(data) : '<p>No ML predictions available.</p>';
            }
        } catch (err) {
            ui.setAiState({ status: 'error', error: err.message, signature });
            if (table && tableBox) tableBox.innerHTML = `<p style="color: #ef4444;">Error: ${escapeHtml(err.message)}</p>`;
        } finally {
            aiRunning = false;
            if (runButton) {
                runButton.innerHTML = original;
                runButton.disabled = false;
            }
        }
    }
    document.getElementById('btn-ml-identify').addEventListener('click', () => runAiIdentify({ table: true }));
    document.getElementById('btn-run-ml')?.addEventListener('click', () => runAiIdentify());
    document.getElementById('btn-rs-ai')?.addEventListener('click', () => runAiIdentify());

    // Detected Peaks Toggle
    const btnTogglePeaks = document.getElementById('btn-toggle-peaks');
    const peaksScrollArea = document.getElementById('peaks-scroll-area');
    if (btnTogglePeaks && peaksScrollArea) {
        btnTogglePeaks.addEventListener('click', () => {
            if (peaksScrollArea.style.display === 'none') {
                peaksScrollArea.style.display = 'block';
                btnTogglePeaks.textContent = 'Hide';
            } else {
                peaksScrollArea.style.display = 'none';
                btnTogglePeaks.textContent = 'Show';
            }
        });
    }
}
