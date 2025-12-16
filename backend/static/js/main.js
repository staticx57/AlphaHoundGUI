// Updated: 2024-12-14 17:00 - N42 Export Fixed
import { api } from './api.js';
import { ui } from './ui.js';
import { chartManager, DoseRateChart } from './charts.js?v=2.3';
import { calUI } from './calibration.js';
import { isotopeUI } from './isotopes_ui.js';

// Global State
let currentData = null;
let isAcquiring = false;
let acquisitionInterval = null;
let acquisitionStartTime = null;
let overlaySpectra = [];
let compareMode = false;
let backgroundData = null; // New background state
let doseChart = null; // Live dose rate chart instance
let lastCheckpointTime = 0; // Checkpoint save tracking
const CHECKPOINT_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes between checkpoints
const colors = ['#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

// Settings
let currentSettings = {
    mode: 'simple',
    isotope_min_confidence: 40.0,
    chain_min_confidence: 30.0,
    energy_tolerance: 20.0,
    chain_min_isotopes_medium: 3,
    chain_min_isotopes_high: 4,
    max_isotopes: 5
};

// [STABILITY] Visibility Handling
let isPageVisible = true;
document.addEventListener('visibilitychange', () => {
    isPageVisible = !document.hidden;
    if (isPageVisible && currentData) {
        // Resume rendering
        const scale = chartManager.getScaleType();
        if (compareMode && overlaySpectra.length > 0) {
            chartManager.renderComparison(overlaySpectra, scale);
        } else {
            chartManager.render(currentData.energies, currentData.counts, currentData.peaks, scale);
        }
    }
});

// [STABILITY] Unload Safeguard
window.addEventListener('beforeunload', (e) => {
    if (isAcquiring) {
        e.preventDefault();
        e.returnValue = 'Recording in progress. Are you sure you want to leave?';
    }
});

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    loadSettings();
    // Initialize Dose Rate Chart (if element exists)
    doseChart = new DoseRateChart();

    await refreshPorts();
    await checkDeviceStatus();
    // Duplicate check removed
    setupEventListeners();
    isotopeUI.init();
});

/**
 * Loads analysis settings from localStorage.
 * Populates currentSettings with saved values and syncs UI controls.
 * @returns {void}
 */
function loadSettings() {
    const saved = localStorage.getItem('analysisSettings');
    if (saved) {
        currentSettings = JSON.parse(saved);

        // Sync UI with saved settings after DOM is ready
        setTimeout(() => {
            // Set mode radio
            const modeRadio = document.querySelector(`input[name="analysis-mode"][value="${currentSettings.mode}"]`);
            if (modeRadio) {
                modeRadio.checked = true;
                // Show advanced panel if in advanced mode
                if (currentSettings.mode === 'advanced') {
                    document.getElementById('advanced-settings').style.display = 'block';
                    // Also show ROI Analysis panel (Advanced Mode only)
                    const roiPanel = document.getElementById('roi-analysis-panel');
                    if (roiPanel) roiPanel.style.display = 'block';
                }
            }

            // Set slider values
            if (currentSettings.isotope_min_confidence !== undefined) {
                document.getElementById('isotope-confidence').value = currentSettings.isotope_min_confidence;
                document.getElementById('iso-conf-val').textContent = currentSettings.isotope_min_confidence;
            }
            if (currentSettings.chain_min_confidence !== undefined) {
                document.getElementById('chain-confidence').value = currentSettings.chain_min_confidence;
                document.getElementById('chain-conf-val').textContent = currentSettings.chain_min_confidence;
            }
            if (currentSettings.energy_tolerance !== undefined) {
                document.getElementById('energy-tolerance').value = currentSettings.energy_tolerance;
                document.getElementById('energy-tol-val').textContent = currentSettings.energy_tolerance;
            }
        }, 0);
    }
}

function setupEventListeners() {
    // File Upload
    document.getElementById('drop-zone').addEventListener('change', (e) => {
        if (e.target.id === 'file-input') handleFile(e.target.files[0]);
    });

    document.getElementById('btn-export-json').addEventListener('click', () => {
        if (!currentData) return;
        const blob = new Blob([JSON.stringify(currentData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'spectrum_data.json';
        a.click();
        URL.revokeObjectURL(url);
    });

    document.getElementById('btn-export-csv').addEventListener('click', () => {
        if (!currentData) return;
        let csv = 'Energy (keV),Counts\n';
        for (let i = 0; i < currentData.energies.length; i++) {
            csv += `${currentData.energies[i]},${currentData.counts[i]}\n`;
        }
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'spectrum_data.csv';
        a.click();
        URL.revokeObjectURL(url);
    });

    // PDF Export
    document.getElementById('btn-export-pdf').addEventListener('click', async () => {
        if (!currentData) return;
        const btn = document.getElementById('btn-export-pdf');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '⏳ Generating...';
        btn.disabled = true;

        try {
            const response = await fetch('/export/pdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: currentData.metadata?.filename || 'spectrum',
                    metadata: currentData.metadata || {},
                    energies: currentData.energies,
                    counts: currentData.counts,
                    peaks: currentData.peaks || [],
                    isotopes: currentData.isotopes || [],
                    decay_chains: currentData.decay_chains || []
                })
            });

            if (!response.ok) throw new Error('PDF generation failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(() => window.URL.revokeObjectURL(url), 1000);
        } catch (err) {
            alert('Error generating PDF: ' + err.message);
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });

    // N42 Export
    document.getElementById('btn-export-n42').addEventListener('click', async () => {
        if (!currentData) {
            alert('No spectrum data to export');
            return;
        }

        const btn = document.getElementById('btn-export-n42');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '⏳ Exporting...';
        btn.disabled = true;

        try {
            const response = await api.exportN42({
                counts: currentData.counts,
                energies: currentData.energies,
                metadata: {
                    live_time: currentData.metadata?.live_time || currentData.metadata?.acquisition_time || 1.0,
                    real_time: currentData.metadata?.real_time || currentData.metadata?.acquisition_time || 1.0,
                    start_time: currentData.metadata?.start_time || new Date().toISOString(),
                    source: currentData.metadata?.source || 'AlphaHound Device',
                    channels: currentData.counts.length
                },
                peaks: currentData.peaks || [],
                isotopes: currentData.isotopes || [],
                filename: currentData.metadata?.filename || 'spectrum'
            });

            if (!response.ok) throw new Error('N42 export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentData.metadata?.filename || 'spectrum'}.n42`;
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            alert('Error exporting N42: ' + err.message);
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });

    // Settings Modal
    document.getElementById('btn-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'flex';
    });

    document.getElementById('close-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'none';
    });

    // Simple/Advanced Mode Toggle
    document.querySelectorAll('input[name="analysis-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const advancedPanel = document.getElementById('advanced-settings');
            if (e.target.value === 'advanced') {
                advancedPanel.style.display = 'block';
                currentSettings.mode = 'advanced';
            } else {
                advancedPanel.style.display = 'none';
                currentSettings.mode = 'simple';
            }
        });
    });

    // Slider Value Displays
    document.getElementById('isotope-confidence')?.addEventListener('input', (e) => {
        document.getElementById('iso-conf-val').textContent = e.target.value;
    });

    document.getElementById('chain-confidence')?.addEventListener('input', (e) => {
        document.getElementById('chain-conf-val').textContent = e.target.value;
    });

    document.getElementById('energy-tolerance')?.addEventListener('input', (e) => {
        document.getElementById('energy-tol-val').textContent = e.target.value;
    });

    // Apply Settings
    document.getElementById('btn-apply-settings')?.addEventListener('click', () => {
        // Get current mode
        const mode = document.querySelector('input[name="analysis-mode"]:checked').value;

        // Update settings from UI
        currentSettings.mode = mode;
        if (mode === 'advanced') {
            currentSettings.isotope_min_confidence = parseFloat(document.getElementById('isotope-confidence').value);
            currentSettings.chain_min_confidence = parseFloat(document.getElementById('chain-confidence').value);
            currentSettings.energy_tolerance = parseFloat(document.getElementById('energy-tolerance').value);
        }

        // Save to localStorage
        localStorage.setItem('analysisSettings', JSON.stringify(currentSettings));

        // Toggle ROI Analysis panel visibility (Advanced Mode only)
        const roiPanel = document.getElementById('roi-analysis-panel');
        if (roiPanel) {
            roiPanel.style.display = (mode === 'advanced') ? 'block' : 'none';
        }

        // Close modal
        document.getElementById('settings-modal').style.display = 'none';

        // Re-analyze current data if loaded
        if (currentData) {
            showToast('Settings applied. Re-upload or re-acquire to see changes.', 'info');
        } else {
            showToast('Settings saved.', 'success');
        }
    });

    // Reset to Defaults
    document.getElementById('btn-reset-defaults')?.addEventListener('click', () => {
        document.getElementById('isotope-confidence').value = 40;
        document.getElementById('iso-conf-val').textContent = '40';
        document.getElementById('chain-confidence').value = 30;
        document.getElementById('chain-conf-val').textContent = '30';
        document.getElementById('energy-tolerance').value = 20;
        document.getElementById('energy-tol-val').textContent = '20';
    });

    // History Modal  
    document.getElementById('btn-history').addEventListener('click', () => {
        const modal = document.getElementById('history-modal');
        const historyList = document.getElementById('history-list');
        const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');

        if (history.length === 0) {
            historyList.innerHTML = '<p style="text-align: center; color: #94a3b8;">No file history yet</p>';
        } else {
            historyList.innerHTML = history.map(item => `
                <div class="history-item">
                    <div class="history-item-name">${item.filename}</div>
                    <div class="history-item-date">${new Date(item.timestamp).toLocaleString()}</div>
                    <div style="font-size: 0.875rem; margin-top: 0.5rem;">
                        ${item.preview.peakCount} peaks | ${item.preview.isotopes.join(', ') || 'No isotopes'}
                    </div>
                </div>
            `).join('');
        }
        modal.style.display = 'flex';
    });

    document.getElementById('close-history').addEventListener('click', () => {
        document.getElementById('history-modal').style.display = 'none';
    });

    // NOTE: Background subtraction listeners registered below with full set (btn-load-bg, btn-set-current-bg, btn-clear-bg)

    // Theme Toggle
    document.getElementById('btn-theme').addEventListener('click', () => {
        const themes = ['dark', 'light', 'nuclear', 'toxic', 'scifi', 'cyberpunk'];
        const current = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = themes[(themes.indexOf(current) + 1) % themes.length];
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
        if (currentData) {
            const scale = chartManager.getScaleType();
            chartManager.render(currentData.energies, currentData.counts, currentData.peaks, scale);
        }
    });

    // Chart Controls
    document.getElementById('btn-lin').addEventListener('click', (e) => {
        document.getElementById('btn-log').classList.remove('active');
        e.target.classList.add('active');
        updateChartScale('linear');
    });
    document.getElementById('btn-log').addEventListener('click', (e) => {
        document.getElementById('btn-lin').classList.remove('active');
        e.target.classList.add('active');
        updateChartScale('logarithmic');
    });
    document.getElementById('btn-reset-zoom').addEventListener('click', () => chartManager.resetZoom());

    // Auto-Scale Toggle
    document.getElementById('btn-auto-scale').addEventListener('click', (e) => {
        const isAutoScale = chartManager.toggleAutoScale();
        e.target.classList.toggle('active', isAutoScale);
        e.target.textContent = isAutoScale ? 'Auto-Scale' : 'Full Spectrum';
        // Re-render chart with new scale
        if (currentData) {
            chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
        }
        showToast(isAutoScale ? 'Auto-scale enabled (zoom to data)' : 'Full spectrum view enabled', 'info');
    });

    // Device Controls
    document.getElementById('btn-refresh-ports').addEventListener('click', refreshPorts);
    document.getElementById('btn-connect-device').addEventListener('click', connectDevice);
    document.getElementById('btn-disconnect-device').addEventListener('click', disconnectDevice);

    document.getElementById('btn-start-acquire').addEventListener('click', startAcquisition);
    document.getElementById('btn-stop-acquire').addEventListener('click', stopAcquisition);

    // Sidebar Toggles (Mobile/Top Bar)
    if (document.getElementById('btn-refresh-ports-top')) document.getElementById('btn-refresh-ports-top').addEventListener('click', refreshPorts);
    if (document.getElementById('btn-connect-top')) document.getElementById('btn-connect-top').addEventListener('click', connectDeviceTop);

    // Comparison
    document.getElementById('btn-compare').addEventListener('click', toggleCompareMode);
    document.getElementById('btn-add-file').addEventListener('click', () => {
        // [STABILITY] Memory Cap
        if (overlaySpectra.length >= 8) {
            alert('Maximum of 8 spectra allowed.');
            return;
        }
        document.getElementById('compare-file-input').click();
    });
    document.getElementById('compare-file-input').addEventListener('change', handleCompareFile);
    document.getElementById('btn-clear-overlays').addEventListener('click', () => {
        overlaySpectra = [];
        updateOverlayCount();
        chartManager.renderComparison([], 'linear');
    });

    // Background Subtraction
    document.getElementById('btn-load-bg').addEventListener('click', () => document.getElementById('bg-file-input').click());
    document.getElementById('bg-file-input').addEventListener('change', handleBackgroundFile);

    document.getElementById('btn-set-current-bg').addEventListener('click', () => {
        if (!currentData) return alert('No data loaded to use as background.');
        setBackground(currentData, 'Current Spectrum');
    });

    document.getElementById('btn-clear-bg').addEventListener('click', clearBackground);

    // SNIP Auto-Background Removal (Visual Only - preserves original analysis)
    document.getElementById('btn-snip-bg').addEventListener('click', async () => {
        if (!currentData || !currentData.counts) {
            alert('No spectrum loaded to remove background from.');
            return;
        }

        const btn = document.getElementById('btn-snip-bg');
        const statusEl = document.getElementById('bg-status');
        const originalText = btn.textContent;

        btn.textContent = '⏳ Processing...';
        btn.disabled = true;

        try {
            const response = await fetch('/analyze/snip-background', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    counts: currentData.counts,
                    iterations: 24,
                    reanalyze: false  // Visual only - don't re-analyze
                })
            });

            if (!response.ok) throw new Error('SNIP analysis failed');

            const result = await response.json();

            // Store original counts for potential restore
            if (!currentData._originalCounts) {
                currentData._originalCounts = [...currentData.counts];
            }

            // Sync peaks to background-subtracted data (visual fix)
            // Finds the new Y-value (net_counts) for each peak's energy
            const adjustedPeaks = currentData.peaks.map(p => {
                let bestIdx = 0;
                let minDiff = Infinity;

                // Find index corresponding to peak energy
                for (let i = 0; i < currentData.energies.length; i++) {
                    const diff = Math.abs(currentData.energies[i] - p.energy);
                    if (diff < minDiff) {
                        minDiff = diff;
                        bestIdx = i;
                    }
                }
                // Return copy with updated counts
                return { ...p, counts: result.net_counts[bestIdx] };
            });

            // Update ONLY the chart display - preserve analysis results
            chartManager.render(currentData.energies, result.net_counts, adjustedPeaks, chartManager.getScaleType());

            // Update status - make clear this is visual only
            statusEl.innerHTML = '✓ Background removed <em>(chart only - analysis unchanged)</em>';
            statusEl.style.color = '#10b981';
            document.getElementById('bg-active-indicator').style.display = 'inline';

            showToast('Background removed from chart (analysis preserved)', 'success');
        } catch (err) {
            console.error('SNIP background error:', err);
            statusEl.textContent = 'Error: ' + err.message;
            statusEl.style.color = '#ef4444';
            showToast('Failed to remove background', 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });

    // Calibration
    const btnCalibrate = document.getElementById('btn-calibrate-mode');
    if (btnCalibrate) btnCalibrate.addEventListener('click', () => calUI.show());

    // Listen for calibration application
    document.addEventListener('calibrationApplied', (e) => {
        applyCalibration(e.detail.slope, e.detail.intercept);
    });

    // NOTE: Scale toggle, reset zoom, and compare mode listeners are already registered above (lines 347-398)
    // Duplicate registrations removed to prevent double-execution

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
            if (compareMode) document.getElementById('btn-compare').click();
        }
    });

    // Peak Fitting
    document.getElementById('btn-run-fit').addEventListener('click', async () => {
        if (!currentData || !currentData.peaks) return;
        const resultsContainer = document.getElementById('analysis-results');
        resultsContainer.innerHTML = '<p>Fitting peaks...</p>';

        try {
            const response = await fetch('/analyze/fit-peaks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    energies: currentData.energies,
                    counts: currentData.counts,
                    peaks: currentData.peaks
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
            resultsContainer.innerHTML = `<p style="color: #ef4444;">Error: ${err.message}</p>`;
        }
    });

    // ML Identification
    document.getElementById('btn-ml-identify').addEventListener('click', async () => {
        if (!currentData || !currentData.counts) return alert('No data loaded');

        const resultsContainer = document.getElementById('analysis-results');
        resultsContainer.innerHTML = '<p>Running AI identification...</p>';

        try {
            const response = await fetch('/analyze/ml-identify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ counts: currentData.counts })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'ML identification failed');
            }

            const data = await response.json();

            if (data.predictions && data.predictions.length > 0) {
                // Quality badge based on top confidence
                const quality = data.quality || 'unknown';
                const qualityColors = {
                    'good': '#10b981',
                    'moderate': '#f59e0b',
                    'low_confidence': '#ef4444',
                    'no_match': '#6b7280'
                };
                const qualityLabels = {
                    'good': '✓ High Confidence',
                    'moderate': '⚠ Moderate',
                    'low_confidence': '⚠ Low Confidence',
                    'no_match': '? No Match'
                };
                const qualityBadge = quality !== 'unknown' ?
                    `<span style="color: ${qualityColors[quality]}; font-size: 0.8rem; margin-left: 0.5rem;">${qualityLabels[quality]}</span>` : '';

                resultsContainer.innerHTML = `
                    <h4 style="margin-top: 0;">ML Predictions (PyRIID)${qualityBadge}</h4>
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
            } else {
                resultsContainer.innerHTML = '<p>No ML predictions available.</p>';
            }
        } catch (err) {
            resultsContainer.innerHTML = `<p style="color: #ef4444;">Error: ${err.message}</p>`;
        }
    });

    // ML Identification Button in Isotopes Container (new enhanced button)
    const btnRunML = document.getElementById('btn-run-ml');
    if (btnRunML) {
        btnRunML.addEventListener('click', () => {
            document.getElementById('btn-ml-identify').click();
        });
    }

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
    btnRunML.addEventListener('click', async () => {
        if (!currentData || !currentData.counts) return alert('No spectrum data loaded');

        const mlList = document.getElementById('ml-isotopes-list');
        const btn = document.getElementById('btn-run-ml');
        const originalHTML = btn.innerHTML;

        btn.innerHTML = '<span style="font-size: 1.2rem;">⏳</span> Running...';
        btn.disabled = true;
        mlList.innerHTML = '<p style="color: var(--text-secondary);">Running AI identification (first run trains model ~10-30s)...</p>';

        try {
            const response = await fetch('/analyze/ml-identify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ counts: currentData.counts })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'ML identification failed');
            }

            const data = await response.json();

            if (data.predictions && data.predictions.length > 0) {
                mlList.innerHTML = data.predictions.map(pred => {
                    const confidence = pred.confidence;
                    const barColor = confidence > 70 ? '#10b981' :
                        confidence > 40 ? '#f59e0b' : '#8b5cf6';
                    const confidenceLabel = confidence > 70 ? 'HIGH' :
                        confidence > 40 ? 'MEDIUM' : 'LOW';

                    return `
                            <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: rgba(139, 92, 246, 0.1); border-radius: 6px; border-left: 3px solid ${barColor};">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                                    <strong style="color: var(--accent-color);">${pred.isotope}</strong>
                                    <span style="font-size: 0.75rem; color: ${barColor}; font-weight: 600;">${confidenceLabel}</span>
                                </div>
                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                    <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: ${Math.min(confidence, 100)}%; height: 100%; background: linear-gradient(90deg, #8b5cf6, ${barColor}); border-radius: 3px; transition: width 0.3s ease;"></div>
                                    </div>
                                    <span style="font-size: 0.8rem; color: var(--text-secondary); min-width: 50px;">${confidence.toFixed(1)}%</span>
                                </div>
                                <div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                    ${pred.method}
                                </div>
                            </div>
                        `;
                }).join('');
            } else {
                mlList.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">No ML predictions available for this spectrum</p>';
            }
        } catch (err) {
            mlList.innerHTML = `<p style="color: #ef4444;">❌ Error: ${err.message}</p>`;
        } finally {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });
}

// Calibration Tool
const calBtn = document.getElementById('btn-calibrate');
if (calBtn) {
    calBtn.addEventListener('click', () => {
        document.getElementById('calibration-modal').style.display = 'block';
    });
}

// NOTE: Device control listeners already registered in setupEventListeners() (lines 372-377)
// Duplicate registrations removed to prevent double-execution

// Get Current Spectrum button (downloads cumulative without clearing)
const btnGetCurrent = document.getElementById('btn-get-current');
if (btnGetCurrent) {
    btnGetCurrent.addEventListener('click', getCurrentSpectrum);
}

// Display mode control buttons (E = next, Q = prev)
const btnDisplayNext = document.getElementById('btn-display-next');
const btnDisplayPrev = document.getElementById('btn-display-prev');

if (btnDisplayNext) {
    btnDisplayNext.addEventListener('click', async () => {
        try {
            await fetch('/device/display/next', { method: 'POST' });
        } catch (e) {
            console.error('Display next error:', e);
        }
    });
}

if (btnDisplayPrev) {
    btnDisplayPrev.addEventListener('click', async () => {
        try {
            await fetch('/device/display/prev', { method: 'POST' });
        } catch (e) {
            console.error('Display prev error:', e);
        }
    });
}

// Clear Spectrum button (W command)
const btnClearSpectrum = document.getElementById('btn-clear-spectrum');
if (btnClearSpectrum) {
    btnClearSpectrum.addEventListener('click', async () => {
        if (!confirm('Clear all accumulated counts on the device?')) return;
        try {
            await fetch('/device/clear', { method: 'POST' });
            showToast('Spectrum cleared');
        } catch (e) {
            console.error('Clear spectrum error:', e);
        }
    });
}

// Top panel device controls (if they exist)
const refreshTop = document.getElementById('btn-refresh-ports-top');
const connectTop = document.getElementById('btn-connect-top');
const disconnectTop = document.getElementById('btn-disconnect-top');
const acquireTop = document.getElementById('btn-acquire-top');

if (refreshTop) refreshTop.addEventListener('click', refreshPorts);
if (connectTop) connectTop.addEventListener('click', connectDeviceTop);
if (disconnectTop) disconnectTop.addEventListener('click', disconnectDevice);
if (acquireTop) acquireTop.addEventListener('click', startAcquisition);

// Chart Click for Calibration
const chartCanvas = document.getElementById('spectrumChart');
if (chartCanvas) {
    chartCanvas.onclick = (evt) => {
        if (document.getElementById('calibration-modal').style.display === 'block') {
            const chart = chartManager.chart;
            const points = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
            if (points.length) {
                const index = points[0].index; // This is the channel index
                // Suggest this channel
                calUI.addPoint(index);
            }
        }
    };
}

// === ROI Analysis Event Handlers (Advanced Mode) ===

// Source type descriptions for display
const SOURCE_TYPE_INFO = {
    'uranium_glass': '🟢 Uranium Glass: Looking for U-238 decay chain (Th-234, Bi-214, Pa-234m). Ra-226 interference expected in 186 keV region.',
    'thoriated_lens': '🟠 Thoriated Lens: Looking for Th-232 decay chain (Ac-228, Tl-208). May also contain uranium.',
    'radium_dial': '☢️ Radium Dial: Looking for Ra-226 daughters (Bi-214, Pb-214) WITHOUT U-238 parents (Th-234).',
    'smoke_detector': '🔵 Smoke Detector: Looking for Am-241 at 60 keV.',
    'natural_background': '🌍 Natural Background: Looking for K-40 at 1461 keV.',
    'unknown': 'Standard Analysis: Detecting isotopes without specific source assumptions.',
    'auto': 'legacy' // fallback
};

// Update source info banner when selection changes
document.getElementById('roi-source-type')?.addEventListener('change', (e) => {
    const sourceType = e.target.value;
    const infoDiv = document.getElementById('roi-source-info');
    const infoText = document.getElementById('roi-source-info-text');

    if (sourceType !== 'auto') {
        infoText.textContent = SOURCE_TYPE_INFO[sourceType] || '';
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
});

// Analyze ROI Button
document.getElementById('btn-analyze-roi')?.addEventListener('click', async () => {
    if (!currentData || !currentData.counts) {
        return showToast('No spectrum data loaded', 'warning');
    }

    const isotope = document.getElementById('roi-isotope').value;
    const detector = document.getElementById('roi-detector').value;
    const acqTime = parseFloat(document.getElementById('roi-acq-time').value) || 600;

    // Safely get source type (handle missing element for older cached HTML)
    const sourceTypeElement = document.getElementById('roi-source-type');
    const sourceType = sourceTypeElement ? sourceTypeElement.value : 'unknown';

    const resultsDiv = document.getElementById('roi-results');
    resultsDiv.innerHTML = '<p style="color: var(--text-secondary);">Analyzing...</p>';

    try {
        const response = await fetch('/analyze/roi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                energies: currentData.energies,
                counts: currentData.counts,
                isotope: isotope,
                detector: detector,
                acquisition_time_s: acqTime,
                source_type: sourceType  // Pass source type for context
            })
        });

        if (!response.ok) throw new Error((await response.json()).detail || 'ROI analysis failed');
        const data = await response.json();


        // Format results
        const activityStr = data.activity_bq
            ? `<span style="color: var(--primary-color); font-weight: 600;">${data.activity_bq.toFixed(1)} Bq</span> (${data.activity_uci.toFixed(6)} μCi)`
            : '<span style="color: #ef4444;">Unable to calculate</span>';

        let htmlOutput = `
                <div style="color: var(--primary-color); font-weight: 600; margin-bottom: 0.25rem;">
                    ${data.isotope} (${data.energy_keV} keV): Net Counts ${data.net_counts.toFixed(0)} ± ${data.uncertainty_sigma.toFixed(1)}
                </div>
            `;

        // Show Advanced Fitting Metrics
        if (data.fit_success && data.resolution) {
            htmlOutput += `
                <div style="margin-bottom: 0.5rem; font-size: 0.85rem; color: #10b981;">
                   <strong>Resolution:</strong> ${data.resolution.toFixed(2)}% <span style="color:var(--text-secondary);">|</span> <strong>FWHM:</strong> ${data.fwhm.toFixed(2)} keV
                </div>
            `;
        }

        htmlOutput += `<div>Activity: ${activityStr}</div>`;

        // If U-235, automatically fetch uranium enrichment ratio
        if (isotope === 'U-235 (186 keV)') {
            try {
                const ratioResponse = await fetch('/analyze/uranium-ratio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        energies: currentData.energies,
                        counts: currentData.counts,
                        detector: detector,
                        acquisition_time_s: acqTime,
                        source_type: sourceType // Pass source type for uranium logic context
                    })
                });

                if (ratioResponse.ok) {
                    const ratioData = await ratioResponse.json();
                    const categoryColor = ratioData.category === 'Natural Uranium' ? '#22c55e' :
                        ratioData.category === 'Depleted Uranium' ? '#f59e0b' :
                            '#ef4444';

                    htmlOutput += `
                            <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                                <div style="color: var(--primary-color); font-weight: 600; margin-bottom: 0.5rem;">
                                    Ratio: 186 keV peak is <strong>${ratioData.ratio_percent.toFixed(1)}%</strong> of 93 keV peak (≥${ratioData.threshold_natural}%): 
                                    <span style="color: ${categoryColor};">${ratioData.category}</span>
                                </div>
                                <div style="color: var(--text-secondary); font-size: 0.85rem;">
                                    ${ratioData.description}
                                </div>
                                <div style="margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.8rem;">
                                    --- Peak Data ---<br>
                                    U-235 (186 keV): ${ratioData.u235_net_counts.toFixed(0)} ± ${ratioData.u235_uncertainty.toFixed(1)} counts<br>
                                    Th-234 (93 keV): ${ratioData.th234_net_counts.toFixed(0)} ± ${ratioData.th234_uncertainty.toFixed(1)} counts
                                </div>
                            </div>
                        `;
                }
            } catch (ratioErr) {
                console.warn('Failed to fetch uranium ratio:', ratioErr);
            }
        }

        htmlOutput += `
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); color: var(--text-secondary);">
                    --- Calculation Parameters ---<br>
                    Detector: ${data.detector}<br>
                    Window: ${data.roi_window[0]}-${data.roi_window[1]} keV | Efficiency: ${data.efficiency_percent.toFixed(2)}%<br>
                    Branching Ratio: ${(data.branching_ratio * 100).toFixed(1)}%
                </div>
            `;

        resultsDiv.innerHTML = htmlOutput;

        // Store last ROI for highlighting and Decay Tool
        window.lastROI = data.roi_window;
        window.lastROIResult = data;

    } catch (err) {
        resultsDiv.innerHTML = `<p style="color: #ef4444;">Error: ${err.message}</p>`;
    }
});

// Uranium Enrichment Button
document.getElementById('btn-uranium-ratio')?.addEventListener('click', async () => {
    if (!currentData || !currentData.counts) {
        return showToast('No spectrum data loaded', 'warning');
    }

    const detector = document.getElementById('roi-detector').value;
    const acqTime = parseFloat(document.getElementById('roi-acq-time').value) || 600;

    const resultsDiv = document.getElementById('roi-results');
    resultsDiv.innerHTML = '<p style="color: var(--text-secondary);">Analyzing uranium ratio...</p>';

    try {
        const response = await fetch('/analyze/uranium-ratio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                energies: currentData.energies,
                counts: currentData.counts,
                detector: detector,
                acquisition_time_s: acqTime
            })
        });

        if (!response.ok) throw new Error((await response.json()).detail || 'Uranium ratio analysis failed');
        const data = await response.json();

        // Color based on category
        let categoryColor = '#10b981';  // Natural = green
        if (data.category === 'Depleted Uranium') categoryColor = '#f59e0b';  // Yellow
        if (data.category === 'Enriched Uranium') categoryColor = '#ef4444';  // Red

        resultsDiv.innerHTML = `
                <div style="margin-bottom: 0.75rem;">
                    <span style="color: var(--primary-color);">U-235 (186 keV):</span> Net Counts ${data.u235_net_counts.toFixed(0)} (${data.u235_uncertainty.toFixed(1)}σ)
                </div>
                <div>
                    Ratio: 186 keV peak is <strong>${data.ratio_percent.toFixed(1)}%</strong> of 93 keV peak (≥${data.threshold_natural}%): 
                    <span style="color: ${categoryColor}; font-weight: 600;">${data.category}</span>
                </div>
                <div style="margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.8rem;">
                    ${data.description}
                </div>
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); color: var(--text-secondary);">
                    --- Peak Data ---<br>
                    U-235 (186 keV): ${data.u235_net_counts.toFixed(0)} ± ${data.u235_uncertainty.toFixed(1)} counts<br>
                    Th-234 (93 keV): ${data.th234_net_counts.toFixed(0)} ± ${data.th234_uncertainty.toFixed(1)} counts
                </div>
            `;

    } catch (err) {
        resultsDiv.innerHTML = `<p style="color: #ef4444;">Error: ${err.message}</p>`;
    }
});

// Highlight ROI Button
document.getElementById('btn-highlight-roi')?.addEventListener('click', () => {
    if (!window.lastROI) {
        return showToast('Run ROI analysis first', 'info');
    }
    const isotope = document.getElementById('roi-isotope').value;
    chartManager.highlightROI(window.lastROI[0], window.lastROI[1], isotope);
    showToast(`ROI highlighted: ${window.lastROI[0]}-${window.lastROI[1]} keV`, 'success');
});

// Clear Highlight Button
document.getElementById('btn-clear-highlight')?.addEventListener('click', () => {
    window.lastROI = null;
    chartManager.clearROIHighlight();
    showToast('ROI highlight cleared', 'info');
});


/**
 * Gets theme-aware colors for toast notifications.
 * @param {'success'|'warning'|'info'} type - The type of toast notification
 * @param {string} theme - The current theme name (dark, light, nuclear, toxic, scifi, cyberpunk)
 * @returns {{bg: string, border: string, shadow: string}} Color configuration object
 */
function getToastColors(type, theme) {
    // Define color schemes for each theme
    const themeColors = {
        'dark': {
            success: { bg: '#10b981', border: '#10b981', shadow: 'rgba(16, 185, 129, 0.3)' },
            warning: { bg: '#f59e0b', border: '#f59e0b', shadow: 'rgba(245, 158, 11, 0.3)' },
            info: { bg: '#3b82f6', border: '#3b82f6', shadow: 'rgba(59, 130, 246, 0.3)' }
        },
        'light': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.2)' },
            warning: { bg: '#f59e0b', border: '#d97706', shadow: 'rgba(245, 158, 11, 0.2)' },
            info: { bg: '#3b82f6', border: '#2563eb', shadow: 'rgba(59, 130, 246, 0.2)' }
        },
        'nuclear': {
            success: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' },
            warning: { bg: '#f59e0b', border: '#ea580c', shadow: 'rgba(245, 158, 11, 0.4)' },
            info: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' }
        },
        'toxic': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.4)' },
            warning: { bg: '#84cc16', border: '#65a30d', shadow: 'rgba(132, 204, 22, 0.4)' },
            info: { bg: '#22c55e', border: '#16a34a', shadow: 'rgba(34, 197, 94, 0.4)' }
        },
        'scifi': {
            success: { bg: '#00d9ff', border: '#3b82f6', shadow: 'rgba(0, 217, 255, 0.5)' },
            warning: { bg: '#a855f7', border: '#9333ea', shadow: 'rgba(168, 85, 247, 0.5)' },
            info: { bg: '#3b82f6', border: '#00d9ff', shadow: 'rgba(59, 130, 246, 0.5)' }
        },
        'cyberpunk': {
            success: { bg: '#fcee09', border: '#00f5ff', shadow: '0 0 20px rgba(252, 238, 9, 0.6), 0 0 40px rgba(0, 245, 255, 0.3)' },
            warning: { bg: '#ff006e', border: '#fcee09', shadow: '0 0 20px rgba(255, 0, 110, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' },
            info: { bg: '#00f5ff', border: '#fcee09', shadow: '0 0 20px rgba(0, 245, 255, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' }
        }
    };

    return themeColors[theme]?.[type] || themeColors['dark'][type];
}

/**
 * Displays a toast notification with theme-aware styling.
 * Toast automatically dismisses after 3 seconds.
 * @param {string} message - The message to display
 * @param {'success'|'warning'|'info'} [type='info'] - The type of toast
 * @returns {void}
 */
function showToast(message, type = 'info') {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const colors = getToastColors(type, currentTheme);

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // Special text color handling for cyberpunk theme
    const textColor = currentTheme === 'cyberpunk' && type === 'success' ? '#0d0208' : 'white';

    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 20px;
        background: ${colors.bg};
        color: ${textColor};
        border: 2px solid ${colors.border};
        border-radius: 8px;
        box-shadow: ${typeof colors.shadow === 'string' && colors.shadow.includes('0 0') ? colors.shadow : `0 4px 12px ${colors.shadow}`};
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
        font-size: 14px;
        max-width: 350px;
        font-weight: 500;
    `;

    document.body.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Device Lifecycle
async function initDevice() {
    // This function seems to be a placeholder or incomplete based on the provided snippet.
    // The original instruction had `initDevice() {file) {` which was syntactically incorrect.
    // Assuming it should be an empty function or a function that takes no arguments for now.
}

/**
 * Handles file upload and processing.
 * Uploads file to server, processes response, and renders dashboard.
 * @param {File} file - The file object to upload
 * @returns {Promise<void>}
 */
async function handleFile(file) {
    if (isAcquiring) {
        if (!confirm('Recording in progress. Stop?')) return;
        stopAcquisition();
    }
    ui.showLoading();
    try {
        const data = await api.uploadFile(file);
        currentData = data;
        ui.resetDropZone();
        ui.renderDashboard(data);

        if (backgroundData) {
            await refreshChartWithBackground();
        } else {
            if (isPageVisible) chartManager.render(data.energies, data.counts, data.peaks, 'linear');
        }
        saveToHistory(file.name, data);
    } catch (err) {
        ui.showError(err.message);
    }
}

function updateChartScale(type) {
    if (compareMode && overlaySpectra.length > 0) {
        chartManager.renderComparison(overlaySpectra, type);
    } else if (currentData) {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, type);
    }
}

/**
 * Refreshes the list of available serial ports.
 * Populates the port selection dropdowns in the UI.
 * @returns {Promise<void>}
 */
async function refreshPorts() {
    try {
        const data = await api.getPorts();
        ui.populatePorts(data.ports);
    } catch (err) {
        console.error(err);
    }
}

/**
 * Connects to the AlphaHound device on the selected port.
 * Sets up WebSocket for real-time dose rate streaming.
 * @returns {Promise<void>}
 */
async function connectDevice() {
    const port = document.getElementById('port-select').value;
    if (!port) return alert('Select a port');
    try {
        await api.connectDevice(port);
        ui.setDeviceConnected(true);
        api.setupDoseWebSocket(
            (rate) => {
                ui.updateDoseDisplay(rate);
                if (doseChart) doseChart.update(rate);
            },
            (status) => ui.updateConnectionStatus(status)
        );
    } catch (err) {
        alert(err.message);
    }
}

// Top Bar connect uses the top select box
async function connectDeviceTop() {
    const port = document.getElementById('port-select-top').value;
    if (!port) return alert('Select a port');
    try {
        await api.connectDevice(port);
        ui.setDeviceConnected(true);
        api.setupDoseWebSocket(
            (rate) => {
                ui.updateDoseDisplay(rate);
                if (doseChart) doseChart.update(rate);
            },
            (status) => ui.updateConnectionStatus(status)
        );
    } catch (err) {
        alert(err.message);
    }
}

/**
 * Disconnects from the AlphaHound device.
 * Stops any active acquisition and cleans up connection state.
 * @returns {Promise<void>}
 */
async function disconnectDevice() {
    try {
        await api.disconnectDevice();
        ui.setDeviceConnected(false);
        stopAcquisition();
    } catch (err) {
        console.error(err);
    }
}

/**
 * Checks if an AlphaHound device is currently connected.
 * Updates UI state and sets up WebSocket if connected.
 * @returns {Promise<void>}
 */
async function checkDeviceStatus() {
    try {
        const status = await api.getDeviceStatus();
        if (status.connected) {
            ui.setDeviceConnected(true);
            // Update temperature if available
            if (status.temperature) {
                ui.updateTemperature(status.temperature);
            }
            api.setupDoseWebSocket(
                (rate) => {
                    ui.updateDoseDisplay(rate);
                    if (doseChart) doseChart.update(rate);
                },
                (status) => ui.updateConnectionStatus(status)
            );
        } else {
            ui.setDeviceConnected(false);
        }
    } catch (err) {
        console.error(err);
    }
}

/**
 * Starts spectrum acquisition from the AlphaHound device.
 * Uses server-side managed acquisition for robustness against browser throttling.
 * @returns {Promise<void>}
 */
async function startAcquisition() {
    if (isAcquiring) return;
    const minutes = parseFloat(document.getElementById('count-time').value) || 5;
    const seconds = minutes * 60;

    try {
        // Start server-managed acquisition
        const result = await api.startManagedAcquisition(minutes);
        if (!result.success) {
            throw new Error(result.error || 'Failed to start acquisition');
        }

        isAcquiring = true;
        acquisitionStartTime = Date.now();

        document.getElementById('btn-start-acquire').style.display = 'none';
        document.getElementById('btn-stop-acquire').style.display = 'block';
        document.getElementById('acquisition-status').style.display = 'block';

        // Show server-managed acquisition indicators
        showServerManagedUI();

        // Poll server for status updates (timing is server-controlled)
        acquisitionInterval = setInterval(async () => {
            try {
                const status = await api.getAcquisitionStatus();

                // Update UI timer
                ui.updateAcquisitionTimer(status.elapsed_seconds, seconds);

                // Update spectrum display if data available
                if (status.spectrum_data) {
                    currentData = status.spectrum_data;
                    ui.renderDashboard(currentData);
                    if (isPageVisible) {
                        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
                    }
                }

                // Check if acquisition completed or stopped
                if (status.status === 'complete' || status.status === 'stopped') {
                    stopAcquisitionUI();

                    if (status.status === 'complete') {
                        showToast(`Acquisition complete! Saved: ${status.final_filename}`, 'success');
                    } else {
                        showToast(`Acquisition stopped. Saved: ${status.final_filename}`, 'info');
                    }

                    // Fetch final data
                    const finalData = await api.getAcquisitionData();
                    if (finalData) {
                        currentData = finalData;
                        ui.renderDashboard(currentData);
                        if (isPageVisible) {
                            chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
                        }
                    }
                    return;
                }

                // Check for errors
                if (status.status === 'error') {
                    stopAcquisitionUI();
                    showToast(`Acquisition error: ${status.error}`, 'error');
                    return;
                }

            } catch (e) {
                console.error('Status poll error:', e);
            }
        }, 2000);

        showToast(`Server-managed acquisition started for ${minutes} minutes`, 'info');

    } catch (err) {
        alert(err.message);
    }
}

/**
 * Stops the current spectrum acquisition.
 * Calls server to stop and finalize, then updates UI.
 * @returns {Promise<void>}
 */
async function stopAcquisition() {
    if (!isAcquiring) return;

    try {
        const result = await api.stopManagedAcquisition();

        if (result.success) {
            showToast(`Acquisition stopped. Saved: ${result.final_filename}`, 'success');
        }
    } catch (err) {
        console.error('Stop acquisition error:', err);
    }

    stopAcquisitionUI();
}

/**
 * Resets acquisition UI state.
 * Called after acquisition completes or stops.
 * @returns {void}
 */
function stopAcquisitionUI() {
    isAcquiring = false;
    clearInterval(acquisitionInterval);
    document.getElementById('btn-start-acquire').style.display = 'block';
    document.getElementById('btn-stop-acquire').style.display = 'none';
    document.getElementById('acquisition-status').style.display = 'none';
    document.getElementById('acquisition-timer').textContent = '0s';

    // Hide server-managed indicators
    const serverStatus = document.getElementById('acquisition-server-status');
    const serverInfo = document.getElementById('server-acquisition-info');
    if (serverStatus) serverStatus.style.display = 'none';
    if (serverInfo) serverInfo.style.display = 'none';
}

/**
 * Shows server-managed acquisition UI indicators.
 * @returns {void}
 */
function showServerManagedUI() {
    const serverStatus = document.getElementById('acquisition-server-status');
    const serverInfo = document.getElementById('server-acquisition-info');
    if (serverStatus) serverStatus.style.display = 'inline';
    if (serverInfo) serverInfo.style.display = 'block';
}

/**
 * Gets the current cumulative spectrum from the device without clearing.
 * Useful for checking what's accumulated on the device or resuming after browser disconnect.
 * @returns {Promise<void>}
 */
async function getCurrentSpectrum() {
    try {
        showToast('Fetching current spectrum from device...', 'info');

        const response = await fetch('/device/spectrum/current');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get spectrum');
        }

        const data = await response.json();
        currentData = data;

        // Show dashboard if hidden
        document.getElementById('drop-zone').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        ui.renderDashboard(data);
        if (isPageVisible) {
            chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
        }

        showToast('Current spectrum loaded (cumulative from device)', 'success');

    } catch (err) {
        console.error('Get current spectrum error:', err);
        showToast(`Error: ${err.message}`, 'warning');
    }
}

/**
 * Saves file analysis to localStorage history.
 * Maintains last 10 entries with preview data.
 * @param {string} filename - Name of the uploaded file
 * @param {Object} data - Parsed spectrum data with peaks and isotopes
 * @returns {void}
 */
function saveToHistory(filename, data) {
    const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');
    history.unshift({
        filename,
        timestamp: new Date().toISOString(),
        preview: {
            peakCount: data.peaks?.length || 0,
            isotopes: data.isotopes?.slice(0, 3).map(i => i.isotope) || []
        }
    });
    localStorage.setItem('fileHistory', JSON.stringify(history.slice(0, 10)));
}

/**
 * Toggles multi-spectrum comparison mode.
 * When enabled, allows overlaying up to 8 spectra on the chart.
 * @returns {void}
 */
function toggleCompareMode() {
    compareMode = !compareMode;
    const panel = document.getElementById('compare-panel');
    const btn = document.getElementById('btn-compare');
    if (compareMode) {
        panel.style.display = 'flex';
        btn.classList.add('active');
        if (currentData) {
            overlaySpectra.push({ name: 'Current', energies: currentData.energies, counts: currentData.counts, color: colors[0] });
            updateOverlayCount();
            chartManager.renderComparison(overlaySpectra, 'linear');
        }
    } else {
        panel.style.display = 'none';
        btn.classList.remove('active');
        overlaySpectra = [];
        if (currentData) chartManager.render(currentData.energies, currentData.counts, currentData.peaks, 'linear');
    }
}

async function handleCompareFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const data = await api.uploadFile(file);
        const color = colors[overlaySpectra.length % colors.length];
        overlaySpectra.push({
            name: file.name,
            energies: data.energies,
            counts: data.counts,
            color: color
        });
        updateOverlayCount();
        chartManager.renderComparison(overlaySpectra, chartManager.getScaleType());
    } catch (err) { alert(err.message); }
    e.target.value = '';
}

function updateOverlayCount() {
    document.getElementById('overlay-count').textContent = `${overlaySpectra.length} spectra loaded`;
}

/**
 * Handles background spectrum file selection for subtraction.
 * @param {Event} e - File input change event
 * @returns {Promise<void>}
 */
async function handleBackgroundFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const data = await api.uploadFile(file);
        setBackground(data, file.name);
    } catch (err) { alert(err.message); }
    e.target.value = '';
}

/**
 * Sets the background spectrum for subtraction.
 * Updates UI to show background is active.
 * @param {Object} data - Parsed background spectrum data
 * @param {string} name - Filename of the background
 * @returns {void}
 */
function setBackground(data, name) {
    backgroundData = data;
    document.getElementById('bg-status').textContent = `Loaded: ${name}`;
    document.getElementById('bg-active-indicator').style.display = 'inline';
    document.getElementById('btn-clear-bg').style.display = 'inline-block';

    // Refresh chart with subtraction
    refreshChartWithBackground();
}

/**
 * Clears the loaded background spectrum.
 * Reverts chart to show raw counts.
 * @returns {void}
 */
function clearBackground() {
    backgroundData = null;
    document.getElementById('bg-status').textContent = 'No background loaded.';
    document.getElementById('bg-active-indicator').style.display = 'none';
    document.getElementById('btn-clear-bg').style.display = 'none';

    if (currentData) {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
    }
}

/**
 * Refreshes chart with background subtraction applied.
 * Subtracts background counts from current spectrum.
 * @returns {Promise<void>}
 */
async function refreshChartWithBackground() {
    if (!currentData) return;

    if (backgroundData) {
        try {
            const result = await api.subtractBackground(currentData.counts, backgroundData.counts);
            // Render NET counts (using original energies)
            // Note: We might want to indicate it's net counts in the UI
            chartManager.render(currentData.energies, result.net_counts, currentData.peaks, chartManager.getScaleType());
        } catch (e) {
            console.error(e);
            alert('Background subtraction failed: ' + e.message);
        }
    } else {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
    }
}

/**
 * Applies energy calibration to the current spectrum.
 * Recalculates energies using linear formula: E = slope * channel + intercept.
 * @param {number} slope - Energy per channel (keV/ch)
 * @param {number} intercept - Energy offset (keV)
 * @returns {void}
 */
function applyCalibration(slope, intercept) {
    if (!currentData) return;
    // Recalculate energies: E = Slope * Ch + Intercept
    // Assuming currentData.counts corresponds to channels 0..N
    const channels = Array.from({ length: currentData.counts.length }, (_, i) => i);
    const newEnergies = channels.map(ch => slope * ch + intercept);

    currentData.energies = newEnergies;
    currentData.is_calibrated = true;
    currentData.metadata = currentData.metadata || {};
    currentData.metadata.calibration = { slope, intercept };

    // Rerender
    if (backgroundData) {
        refreshChartWithBackground();
    } else {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
    }
}

// ==========================================
// Decay Prediction Modal Logic
// ==========================================

const decayModal = document.getElementById('decay-modal');
const decayChartCtx = document.getElementById('decayChart').getContext('2d');
let decayChartInstance = null;

if (document.getElementById('btn-decay-tool')) {
    document.getElementById('btn-decay-tool').addEventListener('click', () => {
        decayModal.style.display = 'flex';

        // Auto-populate from last ROI if available
        if (window.lastROIResult && window.lastROIResult.activity_bq) {
            document.getElementById('decay-activity').value = window.lastROIResult.activity_bq.toFixed(2);
            showToast(`Loaded ${window.lastROIResult.activity_bq.toFixed(1)} Bq from last analysis`, 'info');
        }

        // Run initial default prediction
        runDecayPrediction();
    });
}

if (document.getElementById('close-decay')) {
    document.getElementById('close-decay').addEventListener('click', () => {
        decayModal.style.display = 'none';
    });
}

if (document.getElementById('btn-run-decay')) {
    document.getElementById('btn-run-decay').addEventListener('click', runDecayPrediction);
}

// Close on outside click
decayModal.addEventListener('click', (e) => {
    if (e.target === decayModal) decayModal.style.display = 'none';
});

async function runDecayPrediction() {
    const isotope = document.getElementById('decay-isotope').value;
    const activity = parseFloat(document.getElementById('decay-activity').value);
    const duration = parseFloat(document.getElementById('decay-duration').value);

    try {
        const response = await fetch('/analyze/decay-prediction', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                isotope: isotope,
                initial_activity_bq: activity,
                duration_days: duration * 365.25 // input is years
            })
        });

        if (!response.ok) throw new Error("Prediction failed");

        const result = await response.json();
        renderDecayChart(result);

    } catch (e) {
        console.error(e);
        alert("Error running prediction: " + e.message);
    }
}

function renderDecayChart(result) {
    if (decayChartInstance) {
        decayChartInstance.destroy();
    }

    const labels = result.time_points_days.map(d => (d / 365.25).toFixed(2)); // Years

    // Create datasets for each isotope
    const datasets = [];
    const colors = [
        '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
        '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#d946ef'
    ];

    let colorIdx = 0;
    for (const iso of result.isotopes) {
        // Skip isotopes with negligible activity if list is huge? 
        // For now show all.
        datasets.push({
            label: iso,
            data: result.activities[iso],
            borderColor: colors[colorIdx % colors.length],
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4
        });
        colorIdx++;
    }

    decayChartInstance = new Chart(decayChartCtx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                title: {
                    display: true,
                    text: `Decay Chain: ${result.isotopes[0]} over ${labels[labels.length - 1]} Years`,
                    color: '#94a3b8'
                },
                legend: {
                    position: 'right',
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Time (Years)', color: '#94a3b8' },
                    grid: { color: '#334155' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    type: 'logarithmic',
                    title: { display: true, text: 'Activity (Bq)', color: '#94a3b8' },
                    grid: { color: '#334155' },
                    ticks: {
                        color: '#94a3b8',
                        callback: function (value, index, values) {
                            // Clean up log scale ticks
                            // Show 10^x values clearly
                            const log10 = Math.log10(value);
                            if (Number.isInteger(log10)) {
                                return value.toExponential();
                            }
                            // Show a few intermediates if needed, otherwise hide
                            if (values.length < 5) return value.toPrecision(2);
                            return null; // hide cluttered ticks
                        }
                    }
                }
            }
        }
    });
}
