import { api } from './api.js';
import { ui } from './ui.js';
import { chartManager } from './charts.js';
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
    await refreshPorts();
    await checkDeviceStatus();
    await checkDeviceStatus();
    setupEventListeners();
    isotopeUI.init();
});

function loadSettings() {
    const saved = localStorage.getItem('analysisSettings');
    if (saved) {
        currentSettings = JSON.parse(saved);
        // In full impl, update UI inputs here
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

    // Settings Modal
    document.getElementById('btn-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'flex';
    });

    document.getElementById('close-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'none';
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

    // Background Subtraction
    document.getElementById('bg-file-input').addEventListener('change', handleBackgroundFile);
    document.getElementById('btn-clear-bg').addEventListener('click', clearBackground);

    // Theme Toggle
    document.getElementById('btn-theme').addEventListener('click', () => {
        const themes = ['dark', 'light', 'nuclear', 'toxic'];
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

    // Calibration
    const btnCalibrate = document.getElementById('btn-calibrate-mode');
    if (btnCalibrate) btnCalibrate.addEventListener('click', () => calUI.show());

    // Listen for calibration application
    document.addEventListener('calibrationApplied', (e) => {
        applyCalibration(e.detail.slope, e.detail.intercept);
    });

    // Scale Toggle (Linear/Log)
    document.getElementById('btn-lin').addEventListener('click', () => {
        document.getElementById('btn-lin').classList.add('active');
        document.getElementById('btn-log').classList.remove('active');
        updateChartScale('linear');
    });

    document.getElementById('btn-log').addEventListener('click', () => {
        document.getElementById('btn-lin').classList.remove('active');
        document.getElementById('btn-log').classList.add('active');
        updateChartScale('logarithmic');
    });

    // Reset Zoom
    document.getElementById('btn-reset-zoom').addEventListener('click', () => {
        if (chartManager.chart) chartManager.chart.resetZoom();
    });

    // Compare Mode Toggle
    document.getElementById('btn-compare').addEventListener('click', toggleCompareMode);
    document.getElementById('btn-add-file').addEventListener('click', () => {
        document.getElementById('compare-file-input').click();
    });
    document.getElementById('compare-file-input').addEventListener('change', handleCompareFile);
    document.getElementById('btn-clear-overlays').addEventListener('click', () => {
        overlaySpectra = [];
        updateOverlayCount();
        if (chartManager.chart) chartManager.chart.destroy();
    });

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
        resultsContainer.innerHTML = '<p>🤖 Running AI identification...</p>';

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
                resultsContainer.innerHTML = `
                    <h4 style="margin-top: 0;">ML Predictions (PyRIID)</h4>
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
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                    <td style="padding: 4px;"><strong>${pred.isotope}</strong></td>
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
        btnRunML.addEventListener('click', async () => {
            if (!currentData || !currentData.counts) return alert('No spectrum data loaded');

            const mlList = document.getElementById('ml-isotopes-list');
            const btn = document.getElementById('btn-run-ml');
            const originalHTML = btn.innerHTML;

            btn.innerHTML = '<span style="font-size: 1.2rem;">⏳</span> Running...';
            btn.disabled = true;
            mlList.innerHTML = '<p style="color: var(--text-secondary);">🤖 Running AI identification (first run trains model ~10-30s)...</p>';

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

    // Device Controls
    document.getElementById('btn-refresh-ports').addEventListener('click', refreshPorts);
    document.getElementById('btn-connect-device').addEventListener('click', connectDevice);
    document.getElementById('btn-disconnect-device').addEventListener('click', disconnectDevice);
    document.getElementById('btn-start-acquire').addEventListener('click', startAcquisition);
    document.getElementById('btn-stop-acquire').addEventListener('click', stopAcquisition);

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
}

// Logic Functions
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

async function refreshPorts() {
    try {
        const data = await api.getPorts();
        ui.populatePorts(data.ports);
    } catch (err) {
        console.error(err);
    }
}

async function connectDevice() {
    const port = document.getElementById('port-select').value;
    if (!port) return alert('Select a port');
    try {
        await api.connectDevice(port);
        ui.setDeviceConnected(true);
        api.setupDoseWebSocket(
            (rate) => ui.updateDoseDisplay(rate),
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
            (rate) => ui.updateDoseDisplay(rate),
            (status) => ui.updateConnectionStatus(status)
        );
    } catch (err) {
        alert(err.message);
    }
}

async function disconnectDevice() {
    try {
        await api.disconnectDevice();
        ui.setDeviceConnected(false);
        stopAcquisition();
    } catch (err) {
        console.error(err);
    }
}

async function checkDeviceStatus() {
    try {
        const status = await api.getDeviceStatus();
        if (status.connected) {
            ui.setDeviceConnected(true);
            api.setupDoseWebSocket(
                (rate) => ui.updateDoseDisplay(rate),
                (status) => ui.updateConnectionStatus(status)
            );
        } else {
            ui.setDeviceConnected(false);
        }
    } catch (err) {
        console.error(err);
    }
}

async function startAcquisition() {
    if (isAcquiring) return;
    const minutes = parseFloat(document.getElementById('input-count-duration').value) || 5;
    const seconds = minutes * 60;

    try {
        await api.clearDevice();
        isAcquiring = true;
        acquisitionStartTime = Date.now();

        document.getElementById('btn-start-acquire').style.display = 'none';
        document.getElementById('btn-stop-acquire').style.display = 'block';
        document.getElementById('acquisition-status').style.display = 'block';

        acquisitionInterval = setInterval(async () => {
            const elapsed = (Date.now() - acquisitionStartTime) / 1000;
            if (elapsed >= seconds) {
                stopAcquisition();
                alert('Acquisition Complete');
                // Final fetch
                const data = await api.getSpectrum(minutes);
                currentData = data;
                ui.renderDashboard(data);
                if (isPageVisible) chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
                return;
            }
            ui.updateAcquisitionTimer(elapsed, seconds);

            // Poll spectrum
            try {
                const data = await api.getSpectrum(minutes);
                currentData = data;
                ui.renderDashboard(data);
                if (isPageVisible) chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
            } catch (e) { console.error(e); }
        }, 2000);

    } catch (err) {
        alert(err.message);
    }
}

function stopAcquisition() {
    isAcquiring = false;
    clearInterval(acquisitionInterval);
    document.getElementById('btn-start-acquire').style.display = 'block';
    document.getElementById('btn-stop-acquire').style.display = 'none';
    document.getElementById('acquisition-status').style.display = 'none';
    document.getElementById('acquisition-timer').textContent = '0s';
}

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

// Background Logic
async function handleBackgroundFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const data = await api.uploadFile(file);
        setBackground(data, file.name);
    } catch (err) { alert(err.message); }
    e.target.value = '';
}

function setBackground(data, name) {
    backgroundData = data;
    document.getElementById('bg-status').textContent = `Loaded: ${name}`;
    document.getElementById('bg-active-indicator').style.display = 'inline';
    document.getElementById('btn-clear-bg').style.display = 'inline-block';

    // Refresh chart with subtraction
    refreshChartWithBackground();
}

function clearBackground() {
    backgroundData = null;
    document.getElementById('bg-status').textContent = 'No background loaded.';
    document.getElementById('bg-active-indicator').style.display = 'none';
    document.getElementById('btn-clear-bg').style.display = 'none';

    if (currentData) {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
    }
}

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
