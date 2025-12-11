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
    document.getElementById('btn-analysis').addEventListener('click', () => {
        const panel = document.getElementById('analysis-panel');
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });

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
    const minutes = parseFloat(document.getElementById('count-time').value) || 5;
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
                const data = await api.getSpectrum(0);
                currentData = data;
                ui.renderDashboard(data);
                if (isPageVisible) chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
                return;
            }
            ui.updateAcquisitionTimer(elapsed, seconds);

            // Poll spectrum
            try {
                const data = await api.getSpectrum(0);
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
