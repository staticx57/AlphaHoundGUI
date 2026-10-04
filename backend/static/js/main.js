// Updated: 2024-12-14 17:00 - N42 Export Fixed
import { debug } from './log.js';
import { escapeHtml } from './html.js';
import { api } from './api.js';
import { ui } from './ui.js?v=3.0';
import { chartManager, DoseRateChart } from './charts.js?v=4.6';
import { calUI } from './calibration.js';
import { isotopeUI } from './isotopes_ui.js';
import { estimatorUI } from './estimator_ui.js';
import { updateDeviceUI, resetDeviceUI, getActiveDevice } from './device_features.js';
import { DeviceScreen, SCREEN_MODES } from './device_screen.js';
import { notifyAuto, confirmDialog, setNotifier } from './dialogs.js';
import { ChannelPanel } from './channels.js';
import { formatAlarmLimits, formatDoseRate, formatDoseTotal, resolveUnit, getDosePref, UREM_PER_USV, safeStorage } from './units.js';
import { AlertCenter } from './alerts.js';
import { initA11y } from './a11y.js';
import { loadDecayEngines, runDecayPrediction, redrawDecayChart } from './decay_tool.js';
import { showToast } from './toast.js';

initA11y();
import { readThemeColors, screenPalette, DEVICE_SCREEN_PALETTE } from './palette.js';
import { setupDeviceTabs } from './device_tabs.js';
import { setupExports } from './exports_ui.js';
import { setupShieldingTool } from './shielding_ui.js';
import { setupCalibrationNotice } from './calibration_notice.js';
import { setupAnalysisPanels } from './analysis_panels.js';
import { setupSettingsAndHistory } from './settings_history.js';
import { setupThemeAndChartControls } from './chart_controls.js';
import { setupDeviceControls } from './device_controls.js';
import { setupSnipAndCalibration } from './snip_calibration.js';
import { setupFileUpload } from './file_upload.js';
import { setupUiModeListener } from './ui_mode_listener.js';
import { setupAlphaHoundPanelListeners } from './alphahound_panel.js';
import { setupRadiacodeConnection } from './radiacode_panel.js';
import { setupComparisonAndBackground } from './comparison_background.js';

// Expose chartManager globally for cross-module access (e.g., XRF highlighting from ui.js)
window.chartManager = chartManager;

// Global State
let currentData = null;
let isAcquiring = false;
let acquisitionInterval = null;
let overlaySpectra = [];
let compareMode = false;
let backgroundData = null; // New background state
let rcDoseChart = null; // Radiacode dose rate chart instance
let deviceScreen = null; // AlphaHound display replica
let ahDetailsInterval = null; // AlphaHound details refresh timer
let ahAutoRefreshTimer = null; // AlphaHound spectrum auto-refresh timer
let ahAutoRefreshBusy = false;
// Dose / count-rate alerts for both devices; the readout is tinted while the dose alert is active
const alertCenter = new AlertCenter(document, safeStorage(), (key, active) => {
    if (key === 'dose') document.getElementById('rc-dose-display')?.classList.toggle('dose-alert', active);
});
let channelPanel = null; // AlphaHound gamma / beta / alpha channel panel (cards, meter, share bar, history chart)
let radiacodeDoseInterval = null;  // Radiacode dose rate polling interval

// Multi-line chart colors - hardcoded for visual distinction across different data series
// NOTE: These cannot use CSS variables as Chart.js colors are set at initialization time,
// not dynamically updated on theme change. Would require destroying/recreating all charts on theme switch.
const colors = ['#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

// ============================================================
// Radiacode Dose Rate Polling
// ============================================================
function startRadiacodeDosePolling() {
    if (radiacodeDoseInterval) return;  // Already polling

    debug('[Radiacode] Starting dose rate polling');
    pollRadiacodeDose._pollCount = 0;

    // Poll immediately, then every 2 seconds
    pollRadiacodeDose();
    radiacodeDoseInterval = setInterval(pollRadiacodeDose, 2000);
}

function stopRadiacodeDosePolling() {
    if (radiacodeDoseInterval) {
        debug('[Radiacode] Stopping dose rate polling');
        clearInterval(radiacodeDoseInterval);
        radiacodeDoseInterval = null;
    }
}

async function pollRadiacodeDose() {
    try {
        const result = await api.getRadiacodeDose();
        const doseEl = document.getElementById('rc-dose-display');
        if (doseEl && result.dose_rate_uSv_h !== undefined) {
            const dose = result.dose_rate_uSv_h;
            doseEl.textContent = formatDoseRate(dose, resolveUnit(getDosePref(), 'uSv')).text;
            alertCenter.updateDose(dose);

            // Update sparkline chart if initialized
            if (rcDoseChart) {
                rcDoseChart.addDataPoint(dose);
            }
        }

        // Update device info on the first poll, then every 10 polls (~20 seconds)
        pollRadiacodeDose._pollCount = (pollRadiacodeDose._pollCount || 0) + 1;
        if (pollRadiacodeDose._pollCount === 1) refreshRadiacodeAlarmLimits();
        if (pollRadiacodeDose._pollCount === 1 || pollRadiacodeDose._pollCount % 10 === 0) {
            try {
                const extendedInfo = await api.getRadiacodeExtendedInfo();
                const accumEl = document.getElementById('rc-accumulated-dose');
                const accum = extendedInfo.accumulated_dose_uSv;
                const sess = extendedInfo.session_dose;
                const doseUnit = resolveUnit(getDosePref(), 'uSv');
                const fmtDose = (v) => formatDoseTotal(v, doseUnit);
                if (accumEl && (accum === null || accum === undefined) && sess) {
                    // This firmware does not serve the device's own dose counter over this connection:
                    // show the app's running total (integrated dose rate since connect / Reset Dose).
                    const mins = (sess.covered_seconds / 60).toFixed(1);
                    accumEl.textContent = fmtDose(sess.dose_uSv) + ' (session)';
                    accumEl.title = 'Integrated from the device dose-rate readings since you connected or pressed Reset Dose ('
                        + mins + ' min of readings). The device’s own dose counter is not available over this connection.';
                } else if (accumEl && (accum === null || accum === undefined)) {
                    accumEl.textContent = 'n/a';
                    accumEl.title = 'The RadiaCode interface does not report the device dose counter.';
                } else if (accumEl && typeof accum === 'number') {
                    accumEl.textContent = fmtDose(accum);
                }
                // The same total next to the live dose rate, where it is visible without opening Device Settings
                const totalEl = document.getElementById('rc-dose-total');
                if (totalEl && accumEl) {
                    totalEl.textContent = 'Total ' + accumEl.textContent;
                    totalEl.title = accumEl.title || 'Accumulated dose';
                }
                // Update device info in settings panel
                if (extendedInfo.device_info) {
                    const snEl = document.getElementById('rc-serial-number');
                    const fwEl = document.getElementById('rc-firmware-version');
                    if (snEl && extendedInfo.device_info.serial_number) {
                        // Serial could be string, array, or object
                        const sn = extendedInfo.device_info.serial_number;
                        let serialValue;
                        if (typeof sn === 'string') {
                            serialValue = sn;
                        } else if (Array.isArray(sn)) {
                            serialValue = sn.join('-');
                        } else if (typeof sn === 'object' && sn !== null) {
                            // Try common property names or stringify
                            serialValue = sn.value || sn.serial || sn.number || JSON.stringify(sn);
                        } else {
                            serialValue = String(sn);
                        }
                        snEl.textContent = serialValue;
                    }
                    if (fwEl && extendedInfo.device_info.firmware_version) {
                        // Firmware is nested: [[major, minor, date], [major, minor, date]]
                        // Extract target (second element) or flatten as best we can
                        const fw = extendedInfo.device_info.firmware_version;
                        let fwValue;
                        if (Array.isArray(fw) && fw.length >= 2 && Array.isArray(fw[1])) {
                            // Format: [[boot], [target]] -> "major.minor"
                            fwValue = `${fw[1][0]}.${fw[1][1]}`;
                        } else if (Array.isArray(fw)) {
                            fwValue = fw.flat().join('.');
                        } else if (typeof fw === 'string') {
                            fwValue = fw;
                        } else {
                            fwValue = JSON.stringify(fw);
                        }
                        fwEl.textContent = fwValue;
                    }
                }
                // Fetch HW serial (Phase 1)
                fetchHardwareSerial();
                // Check for device messages (Phase 3)
                checkDeviceMessages();
            } catch (extErr) {
                // Extended info is optional, don't break on failure
                debug('[Radiacode] Extended info unavailable:', extErr.message);
            }
        }
        pollRadiacodeDose._notConnectedCount = 0;
        await pollRadiacodeEvents();
    } catch (err) {
        // Don't spam errors - just log once
        if (!pollRadiacodeDose._hasError) {
            console.warn('[Radiacode] Dose poll error:', err.message);
            pollRadiacodeDose._hasError = true;
        }
        // The server answers 400 "not connected" when the device was disconnected (unplugged,
        // Bluetooth dropped, server restarted). Three in a row: stop pretending we are connected.
        if (err.status === 400 && /not connected/i.test(err.message || '')) {
            pollRadiacodeDose._notConnectedCount = (pollRadiacodeDose._notConnectedCount || 0) + 1;
            if (pollRadiacodeDose._notConnectedCount >= 3) {
                pollRadiacodeDose._notConnectedCount = 0;
                handleRadiacodeLost();
            }
        }
    }
}

/**
 * Resets the UI to the disconnected state. Used after a user Disconnect and when the
 * connection is lost behind our back (Bluetooth drop, unplug, server restart).
 */
function showRadiacodeDisconnectedUI() {
    stopRadiacodeDosePolling();
    alertCenter.reset(['dose']);
    ui.setDeviceConnected(false);
    resetDeviceUI();
    const connectBtn = document.getElementById('btn-connect-radiacode');
    if (connectBtn) {
        connectBtn.textContent = 'Connect';   // it read "Connected" after a successful connect
        connectBtn.disabled = false;
        connectBtn.style.display = 'inline-block';
    }
    const disconnectBtn = document.getElementById('btn-disconnect-device');
    if (disconnectBtn) disconnectBtn.style.display = 'none';
    const doseEl = document.getElementById('rc-dose-display');
    if (doseEl) doseEl.textContent = '--';
    const totalEl = document.getElementById('rc-dose-total');
    if (totalEl) totalEl.textContent = 'Total --';
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) dropZone.style.display = '';
}

/** Toasts new device alarm events (dose-rate / dose / count-rate thresholds, battery, temperature). */
async function pollRadiacodeEvents() {
    try {
        const { events } = await api.getRadiacodeEvents(pollRadiacodeEvents._lastId || 0);
        const first = pollRadiacodeEvents._lastId === undefined;
        for (const ev of events) {
            pollRadiacodeEvents._lastId = Math.max(pollRadiacodeEvents._lastId || 0, ev.id);
            // Events logged before this page loaded are history: do not replay them as toasts.
            if (ev.alarm && !first) {
                showToast(`Radiacode alarm: ${ev.name.replace(/_/g, ' ').toLowerCase()}`, 'error');
            }
        }
        if (first) pollRadiacodeEvents._lastId = pollRadiacodeEvents._lastId || 0;
    } catch (err) {
        // events are optional; never break dose polling
    }
}

function handleRadiacodeLost() {
    if (!isAcquiring) {
        showRadiacodeDisconnectedUI();
        showToast('Radiacode connection lost. Reconnect to continue.', 'warning');
    } else {
        // An acquisition is running on the server; it reports its own error state.
        showRadiacodeDisconnectedUI();
        showToast('Radiacode disconnected during acquisition.', 'error');
    }
}

// Settings
let currentSettings = {
    mode: 'simple',  // Analysis mode: simple/advanced
    uiMode: 'simple', // UI complexity: simple/advanced/expert
    isotope_min_confidence: 40.0,
    chain_min_confidence: 30.0,
    energy_tolerance: 20.0,
    chain_min_isotopes_medium: 3,
    chain_min_isotopes_high: 4,
    max_isotopes: 5
};

/**
 * Re-apply isotope highlights after chart re-renders (e.g., theme change)
 * Uses the cached isotope data stored during isotope detection
 */
function reapplyIsotopeHighlights() {
    if (!window._selectedIsotopes || window._selectedIsotopes.size === 0) return;
    if (!window._isotopeData || !window.chartManager?.chart) return;

    const chart = window.chartManager.chart;
    const colors = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6'];
    let colorIdx = 0;

    window._selectedIsotopes.forEach(isoName => {
        const iso = window._isotopeData.find(i => i.isotope === isoName);
        if (!iso) return;

        const color = colors[colorIdx % colors.length];
        colorIdx++;

        // Use skipUpdate=true for everything except the last isotope if we wanted to be efficient,
        // but since we call chart.update('none') at the end anyway, we can just pass skipUpdate=true to all.
        window.chartManager.addIsotopeHighlight(isoName, iso.matched_peaks, iso.expected_peaks, color, true);
    });

    chart.update('none');
    debug('[Theme] Re-applied isotope highlights for', window._selectedIsotopes.size, 'isotopes');

    // Also re-apply XRF highlights if active
    if (window._selectedXRFIndex !== undefined && window._selectedXRFIndex !== null && window._xrfData && window.chartManager) {
        const item = window._xrfData[window._selectedXRFIndex];
        if (item && item.lines) {
            const peaks = item.lines.map(l => ({
                energy: l.peak_energy,
                element: item.element,
                shell: l.shell
            }));
            window.chartManager.highlightXRFPeaks(peaks, null, true);
            const clearBtn = document.getElementById('btn-clear-xrf-highlight');
            if (clearBtn) clearBtn.style.display = 'inline-block';
        }
    }
}

// UI Mode Panel Configuration
// Maps UI complexity mode to visible panels/sections
// Panel IDs must match actual element IDs in index.html
const UI_MODE_CONFIG = {
    simple: {
        description: 'Basic spectrum analysis for hobbyists',
        showElements: [],
        hideElements: [
            'roi-analysis-panel',
            'advanced-settings',
            'calibration-section',
            'background-section',
            'btn-edit-n42',
            'btn-estimator-tool'
        ]
    },
    advanced: {
        description: 'Extended analysis with calibration and ROI',
        showElements: [
            'roi-analysis-panel',
            'calibration-section',
            'background-section',
            'btn-edit-n42'
        ],
        hideElements: [
            'advanced-settings',
            'btn-estimator-tool'
        ]
    },
    expert: {
        description: 'Full access to all analysis tools',
        showElements: [
            'roi-analysis-panel',
            'advanced-settings',
            'calibration-section',
            'background-section',
            'btn-edit-n42',
            'btn-estimator-tool'
        ],
        hideElements: []
    }
};


/**
 * Applies UI complexity mode by showing/hiding panels.
 * @param {string} mode - 'simple', 'advanced', or 'expert'
 */
function applyUIMode(mode = 'simple') {
    const config = UI_MODE_CONFIG[mode] || UI_MODE_CONFIG.simple;
    debug(`[UI Mode] Applying "${mode}" mode: ${config.description}`);

    // First, hide elements that should be hidden in this mode
    if (config.hideElements && config.hideElements.length > 0) {
        config.hideElements.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.display = 'none';
                debug(`[UI Mode] Hiding: ${id}`);
            } else {
                console.warn(`[UI Mode] Element not found: ${id}`);
            }
        });
    }

    // Then, show elements that should be visible in this mode
    if (config.showElements && config.showElements.length > 0) {
        config.showElements.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.display = ''; // Reset to default/CSS
                debug(`[UI Mode] Showing: ${id}`);
            } else {
                console.warn(`[UI Mode] Element not found: ${id}`);
            }
        });
    }

    // Update currentSettings and persist
    currentSettings.uiMode = mode;
    localStorage.setItem('analysisSettings', JSON.stringify(currentSettings));
}

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
        reapplyIsotopeHighlights();
    }
});

// [STABILITY] Unload Safeguard
window.addEventListener('beforeunload', (e) => {
    if (isAcquiring) {
        e.preventDefault();
        e.returnValue = 'Recording in progress. Are you sure you want to leave?';
    }
});

// ==================== Phase 1: Quick Win Features ====================

// Get Accumulated Spectrum
const btnGetAccumulated = document.getElementById('btn-get-accumulated');
if (btnGetAccumulated) {
    btnGetAccumulated.addEventListener('click', async () => {
        try {
            // The accumulated spectrum spans everything since the device's last accumulation reset.
            // Only identify it if the user measured a single source over that period.
            const analyze = await confirmDialog(
                'Analyze the accumulated spectrum for isotopes?\n\n' +
                'Analyze: the device was reset and then used on a single source.\n' +
                'Just view: it may mix several locations or sources.',
                { title: 'Accumulated spectrum', okLabel: 'Analyze', cancelLabel: 'Just view' });
            showToast('Getting accumulated spectrum...', 'info');
            const data = await api.getAccumulatedSpectrum(analyze);

            // Backend now returns fully analyzed data with energies, counts, peaks, isotopes
            currentData = data;

            // Show dashboard if hidden (in case this is first load)
            document.getElementById('drop-zone').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';

            // Render full dashboard with all analysis (peaks, isotopes, XRF)
            ui.renderDashboard(data);
            chartManager.render(data.energies, data.counts, data.peaks || [], 'linear');

            const durationMin = (data.duration / 60).toFixed(1);
            showToast(`Accumulated spectrum loaded (${durationMin} min of device history${analyze ? ', analyzed' : ', view only'})`, 'success');
            (data.warnings || []).forEach(w => showToast(w, 'info'));
        } catch (err) {
            console.error('Failed to get accumulated spectrum:', err);
            showToast(err.message || 'Failed to get accumulated spectrum', 'error');
        }
    });
}

// Display Orientation
const displayDirectionSelect = document.getElementById('rc-display-direction');
if (displayDirectionSelect) {
    displayDirectionSelect.addEventListener('change', async (e) => {
        try {
            const direction = e.target.value;
            await api.setDisplayDirection(direction);
            showToast(`Display orientation set to ${direction}`, 'success');
        } catch (err) {
            console.error('Failed to set display direction:', err);
            showToast(err.message || 'Failed to set display orientation', 'error');
        }
    });
}

// Sync Device Time
const btnSyncTime = document.getElementById('btn-sync-time');
if (btnSyncTime) {
    btnSyncTime.addEventListener('click', async () => {
        try {
            await api.syncDeviceTime();
            showToast('Device time synchronized with computer', 'success');
        } catch (err) {
            console.error('Failed to sync time:', err);
            showToast(err.message || 'Failed to sync device time', 'error');
        }
    });
}

// Fetch HW Serial on connection (update pollRadiacodeDose to also fetch hw_serial)
async function fetchHardwareSerial() {
    try {
        const result = await api.getHardwareSerial();
        const hwSerialEl = document.getElementById('rc-hw-serial');
        if (hwSerialEl && result.hw_serial_number) {
            hwSerialEl.textContent = result.hw_serial_number;
        }
    } catch (err) {
        debug('[Radiacode] HW serial unavailable:', err.message);
    }
}

// ==================== Phase 2: Advanced Controls ====================

// Get Energy Calibration
const btnGetCalibration = document.getElementById('btn-get-calibration');
if (btnGetCalibration) {
    btnGetCalibration.addEventListener('click', async () => {
        try {
            const calibration = await api.getEnergyCalibration();
            document.getElementById('rc-cal-a0').value = calibration.a0.toFixed(4);
            document.getElementById('rc-cal-a1').value = calibration.a1.toFixed(4);
            document.getElementById('rc-cal-a2').value = calibration.a2.toFixed(7);
            showToast('Calibration retrieved', 'success');
        } catch (err) {
            console.error('Failed to get calibration:', err);
            showToast(err.message || 'Failed to get calibration', 'error');
        }
    });
}

// Set Energy Calibration
const btnSetCalibration = document.getElementById('btn-set-calibration');
if (btnSetCalibration) {
    btnSetCalibration.addEventListener('click', async () => {
        const a0 = parseFloat(document.getElementById('rc-cal-a0').value);
        const a1 = parseFloat(document.getElementById('rc-cal-a1').value);
        const a2 = parseFloat(document.getElementById('rc-cal-a2').value);

        if (isNaN(a0) || isNaN(a1) || isNaN(a2)) {
            showToast('Enter all calibration values', 'warning');
            return;
        }

        try {
            await api.setEnergyCalibration(a0, a1, a2);
            showToast('Calibration applied', 'success');
        } catch (err) {
            console.error('Failed to set calibration:', err);
            showToast(err.message || 'Failed to set calibration', 'error');
        }
    });
}

// Power Off Device (with confirmation)
const btnPowerOff = document.getElementById('btn-power-off');
if (btnPowerOff) {
    btnPowerOff.addEventListener('click', async () => {
        if (!(await confirmDialog('Power off the Radiacode device?\n\nYou will need to power it back on by hand.',
            { title: 'Power off', okLabel: 'Power off', danger: true }))) {
            return;
        }

        try {
            await api.powerOffDevice();
            showToast('Device powering off...', 'warning');
            // Reset UI since device will disconnect
            stopRadiacodeDosePolling();
            resetDeviceUI();
            document.getElementById('btn-connect-radiacode').style.display = 'inline-block';
            document.getElementById('btn-disconnect-device').style.display = 'none';
        } catch (err) {
            console.error('Failed to power off device:', err);
            showToast(err.message || 'Failed to power off', 'error');
        }
    });
}

// ==================== End Phase 2 Features ====================

// ==================== Phase 3: Diagnostics GUI ====================

// Refresh Diagnostics
/** Show the device's own alarm thresholds (read-only) in the diagnostics; quietly "not available" if the firmware will not say. */
async function refreshRadiacodeAlarmLimits() {
    const el = document.getElementById('rc-alarm-limits');
    if (!el) return;
    try {
        const rows = formatAlarmLimits(await api.getRadiacodeAlarmLimits(), resolveUnit(getDosePref(), 'uSv'));
        el.replaceChildren(...(rows.length ? rows.map((r) => {
            const line = document.createElement('div');
            line.textContent = `${r.label}: ${r.value}`;
            return line;
        }) : [document.createTextNode('not available on this device')]));
    } catch (e) {
        el.textContent = 'not available';
    }
}

const btnRefreshDiagnostics = document.getElementById('btn-refresh-diagnostics');
if (btnRefreshDiagnostics) {
    btnRefreshDiagnostics.addEventListener('click', async () => {
        try {
            // Fetch all diagnostics in parallel
            const [statusResult, fwSigResult, baseTimeResult] = await Promise.all([
                api.getStatusFlags().catch(e => ({ status_flags: 'Error' })),
                api.getFirmwareSignature().catch(e => ({ fw_signature: 'Error' })),
                api.getBaseTime().catch(e => ({ base_time: 'Error' }))
            ]);

            // Update UI
            document.getElementById('rc-status-flags').textContent = statusResult.status_flags || '--';
            document.getElementById('rc-fw-signature').textContent = fwSigResult.fw_signature || '--';
            document.getElementById('rc-base-time').textContent = baseTimeResult.base_time || '--';
            await checkDeviceMessages();
            await refreshRadiacodeAlarmLimits();

            showToast('Diagnostics refreshed', 'success');
        } catch (err) {
            console.error('Failed to refresh diagnostics:', err);
            showToast('Failed to refresh diagnostics', 'error');
        }
    });
}

// Check for text messages periodically (add to poll function)
async function checkDeviceMessages() {
    try {
        // The device's TEXT_MESSAGE is a status log (e.g. "BLE: client connected"), not a radiation
        // alarm, so it is shown quietly under Advanced Diagnostics rather than as an alert banner.
        const result = await api.getTextMessage();
        const textEl = document.getElementById('rc-device-status-text');
        if (textEl) {
            textEl.textContent = (result.has_message && result.message) ? result.message : '--';
        }
    } catch (err) {
        // Silently fail - messages are optional
    }
}

// ==================== End Phase 3 Features ====================

// ==================== End Phase 1 Features ====================

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    loadSettings();

    await refreshPorts();
    await checkDeviceStatus();
    await checkRadiacodeStatus();
    // Nothing connected: hide the controls that only exist for a connected device (Reset Dose on the AlphaHound tab, ...)
    if (!getActiveDevice()) resetDeviceUI();
    // Duplicate check removed
    setupEventListeners();
    setupAlphaHoundPanelListeners({ disconnectDevice, refreshAlphaHoundDetails, runAhProbe, startAhAutoRefresh, stopAhAutoRefresh });
    // Decay Tool Logic Inlined
    const decayModal = document.getElementById('decay-modal');
    if (decayModal && document.getElementById('btn-decay-tool')) {
        document.getElementById('btn-decay-tool').addEventListener('click', () => {
            // Close other modals
            if (estimatorUI && estimatorUI.modal) estimatorUI.modal.style.display = 'none';

            decayModal.style.display = 'flex';
            if (window.lastROIResult && window.lastROIResult.activity_bq) {
                document.getElementById('decay-activity').value = window.lastROIResult.activity_bq.toFixed(2);
                try { showToast('Loaded ' + window.lastROIResult.activity_bq.toFixed(1) + ' Bq', 'info'); } catch (e) { }
            }
            runDecayPrediction();
        });
        document.getElementById('close-decay').addEventListener('click', () => decayModal.style.display = 'none');
        decayModal.addEventListener('click', (e) => { if (e.target === decayModal) decayModal.style.display = 'none'; });
    }
    if (document.getElementById('btn-run-decay')) {
        document.getElementById('btn-run-decay').addEventListener('click', runDecayPrediction);
    }
    loadDecayEngines();
    setupShieldingTool();
    setupCalibrationNotice({ getCurrentData: () => currentData, isAcquiring: () => isAcquiring, applyAnalysis });
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
            // Set analysis mode radio
            const modeRadio = document.querySelector(`input[name="analysis-mode"][value="${currentSettings.mode}"]`);
            if (modeRadio) {
                modeRadio.checked = true;
                // Show advanced panel if in advanced mode
                if (currentSettings.mode === 'advanced') {
                    document.getElementById('advanced-settings').style.display = 'block';
                }
            }

            // Set UI complexity mode radio
            const uiMode = currentSettings.uiMode || 'simple';
            const uiModeRadio = document.querySelector(`input[name="ui-mode"][value="${uiMode}"]`);
            if (uiModeRadio) {
                uiModeRadio.checked = true;
            }
            applyUIMode(uiMode);

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
    } else {
        // No saved settings - apply default UI mode after DOM ready
        setTimeout(() => {
            applyUIMode('simple');
        }, 0);
    }
}

function setupEventListeners() {
    setupFileUpload({ handleFile, getCurrentData: () => currentData });
    setupUiModeListener({ applyUIMode });
    setupDeviceTabs();
    setupRadiacodeConnection({ DoseRateChart, startRadiacodeDosePolling, getCurrentData: () => currentData, getRcDoseChart: () => rcDoseChart, setRcDoseChart: (value) => { rcDoseChart = value; } });
    setupExports({ ui, getCurrentData: () => currentData });
    setupSettingsAndHistory({ ui, alertCenter, applyUIMode, loadFromHistory, getCurrentData: () => currentData, getSettings: () => currentSettings });
    setupThemeAndChartControls({ chartManager, reapplyIsotopeHighlights, updateChartScale, getCurrentData: () => currentData });
    setupDeviceControls({ connectDevice, refreshPorts, showRadiacodeDisconnectedUI, startAcquisition, stopAcquisition, stopRadiacodeDosePolling });
    setupComparisonAndBackground({ chartManager, clearBackground, handleBackgroundFile, handleCompareFile, setBackground, toggleCompareMode, updateOverlayCount, getCurrentData: () => currentData, getOverlaySpectra: () => overlaySpectra, setOverlaySpectra: (value) => { overlaySpectra = value; } });
    setupSnipAndCalibration({ chartManager, applyCalibration, getCurrentData: () => currentData });
    setupAnalysisPanels({ ui, isCompareMode: () => compareMode, getCurrentData: () => currentData });
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
            if (deviceScreen) deviceScreen.step(1);
        } catch (e) {
            console.error('Display next error:', e);
        }
    });
}

if (btnDisplayPrev) {
    btnDisplayPrev.addEventListener('click', async () => {
        try {
            await fetch('/device/display/prev', { method: 'POST' });
            if (deviceScreen) deviceScreen.step(-1);
        } catch (e) {
            console.error('Display prev error:', e);
        }
    });
}

// Clear Spectrum: handled once, device-aware, in setupEventListeners() (api.clearSpectrumUnified)

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
    'uranium_glass': 'Uranium Glass: Looking for U-238 decay chain (Th-234, Bi-214, Pa-234m). Ra-226 interference expected in 186 keV region.',
    'uranium_ore': 'Uranium Ore: Full U-238 decay chain in secular equilibrium. U-235 visible at 186 keV (~0.72% natural).',
    'thoriated_lens': 'Thoriated Lens: Looking for Th-232 decay chain (Ac-228, Tl-208). May also contain uranium.',
    'radium_dial': 'Radium Dial: Looking for Ra-226 daughters (Bi-214, Pb-214) WITHOUT U-238 parents (Th-234).',
    'smoke_detector': 'Smoke Detector: Looking for Am-241 at 60 keV.',
    'natural_background': 'Natural Background: Looking for K-40 at 1461 keV.',
    'takumar_lens': 'Takumar Lens: ThO2 glass with trace uranium. Analyzing Th-234 (93 keV) for thorium activity.',
    'cesium_source': 'Cesium-137: Calibration source at 662 keV. Half-life 30.17 years.',
    'cobalt_source': 'Cobalt-60: Dual peaks at 1173/1332 keV. Half-life 5.27 years.',
    'unknown': 'Standard Analysis: Detecting isotopes without specific source assumptions.',
    'auto': 'legacy' // fallback
};

// Update source info banner when selection changes
document.getElementById('roi-source-type')?.addEventListener('change', (e) => {
    const sourceType = e.target.value;
    const infoDiv = document.getElementById('roi-source-info');
    const infoText = document.getElementById('roi-source-info-text');
    const isotopeSelect = document.getElementById('roi-isotope');

    if (sourceType !== 'auto') {
        infoText.textContent = SOURCE_TYPE_INFO[sourceType] || '';
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }

    // Auto-switch isotope based on source type
    const SOURCE_ISOTOPE_MAP = {
        'uranium_glass': 'U-235 (186 keV)',
        'uranium_ore': 'U-235 (186 keV)',
        'thoriated_lens': 'Th-234 (93 keV)',
        'takumar_lens': 'Th-234 (93 keV)',
        'radium_dial': 'Bi-214 (609 keV)',
        'smoke_detector': 'Am-241 (60 keV)',
        'cesium_source': 'Cs-137 (662 keV)',
        'cobalt_source': 'Co-60 (1173 keV)',
        'natural_background': 'K-40 (1461 keV)'
    };

    if (isotopeSelect && SOURCE_ISOTOPE_MAP[sourceType]) {
        isotopeSelect.value = SOURCE_ISOTOPE_MAP[sourceType];
        showToast(`Auto-selected ${SOURCE_ISOTOPE_MAP[sourceType]} for ${sourceType.replace(/_/g, ' ')}`, 'info');
    }
});

/**
 * Robust error formatting for FastAPI/Pydantic errors.
 * Handles both simple string details and structured validation arrays.
 */
function formatErrorMessage(errData) {
    if (!errData) return 'Unknown error';
    const detail = errData.detail || errData;

    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map(d => {
            const loc = d.loc ? d.loc.join('.') : 'input';
            return `${loc}: ${d.msg}`;
        }).join('<br>');
    }
    if (typeof detail === 'object') return JSON.stringify(detail);
    return String(detail);
}

// Analyze ROI Button
document.getElementById('btn-analyze-roi')?.addEventListener('click', async () => {
    if (!currentData || !currentData.counts) {
        return showToast('No spectrum data loaded', 'warning');
    }

    const isotope = document.getElementById('roi-isotope').value;
    const detector = document.getElementById('roi-detector').value;
    // Input is in minutes, convert to seconds for API
    const acqTimeMinutes = parseFloat(document.getElementById('roi-acq-time').value) || 10;
    const acqTime = acqTimeMinutes * 60;

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

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(formatErrorMessage(errData));
        }
        const data = await response.json();


        // Format results
        // Format results
        let activityStr;
        if (data.activity_bq) {
            activityStr = `<span style="color: var(--primary-color); font-weight: 600;">${data.activity_bq.toFixed(1)}${data.activity_uncertainty_bq ? ' ± ' + data.activity_uncertainty_bq.toFixed(1) : ''} Bq</span> (${data.activity_uci.toFixed(6)} μCi)`;
        } else if (data.mda_bq) {
            activityStr = `<span style="color: var(--text-secondary);">&lt; ${data.mda_bq.toFixed(1)} Bq (Limit)</span>`;
        } else {
            activityStr = '<span style="color: var(--text-secondary);">Not Detected</span>';
        }

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
        if (data.detection_status) {
            htmlOutput += `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.15rem;">${data.detection_status}${data.snr ? ` (SNR ${data.snr})` : ''}</div>`;
        }

        // Confidence Bar
        if (data.confidence !== undefined) {
            const confPercent = Math.round(data.confidence * 100);
            // Get theme-aware confidence color
            const styles = getComputedStyle(document.documentElement);
            const confColor = data.confidence > 0.7 ? styles.getPropertyValue('--confidence-high').trim() || '#10b981' :
                data.confidence > 0.4 ? styles.getPropertyValue('--confidence-medium').trim() || '#f59e0b' :
                    styles.getPropertyValue('--confidence-low').trim() || '#ef4444';

            htmlOutput += `
                <div style="margin-top: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 2px;">
                        <span>Confidence</span>
                        <span style="color: ${confColor}; font-weight: bold;">${confPercent}%</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div style="width: ${confPercent}%; height: 100%; background: ${confColor}; transition: width 0.3s ease;"></div>
                    </div>
                </div>
             `;
        }

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
                    // Get theme-aware category colors
                    const styles = getComputedStyle(document.documentElement);
                    const categoryColor = ratioData.category === 'Natural Uranium' ? styles.getPropertyValue('--xrf-high').trim() || '#22c55e' :
                        ratioData.category === 'Depleted Uranium' ? styles.getPropertyValue('--confidence-medium').trim() || '#f59e0b' :
                            styles.getPropertyValue('--confidence-low').trim() || '#ef4444';

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
                    Branching Ratio: ${(data.branching_ratio * 100).toFixed(1)}%${data.effective_branching_ratio > data.branching_ratio + 1e-6 ? ` (${(data.effective_branching_ratio * 100).toFixed(1)}% with the lines blended into this peak)` : ''}<br>
                    Background: ${data.background_method || 'n/a'}
                </div>
            `;

        // Render enhanced analysis if present
        if (data.enhanced_analysis && data.enhanced_analysis.insights) {
            htmlOutput += `
                <div style="margin-top: 0.75rem; padding: 0.75rem; background: rgba(16, 185, 129, 0.1); border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <div style="font-weight: 600; color: #10b981; margin-bottom: 0.5rem;"><img src="/static/icons/chart.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Source-Specific Insights</div>
            `;
            for (const insight of data.enhanced_analysis.insights) {
                const warningStyle = insight.warning ? 'color: #f59e0b;' : '';
                htmlOutput += `
                    <div style="margin-bottom: 0.3rem; ${warningStyle}">
                        ${insight.icon || '•'} <strong>${insight.label}:</strong> ${insight.value}
                    </div>
                `;
            }
            htmlOutput += `</div>`;
        }

        resultsDiv.innerHTML = htmlOutput;

        // What limits the result (neighbouring peaks, how the background was found, ...): as text, never as markup
        const notes = [...(data.limiting_factors || []), ...(data.warnings || [])];
        if (notes.length) {
            const list = document.createElement('ul');
            list.id = 'roi-notes';
            list.style.cssText = 'margin: 0.6rem 0 0 1.2rem; padding: 0; font-size: 0.78rem; color: var(--text-secondary);';
            notes.forEach((note) => {
                const item = document.createElement('li');
                item.textContent = note;
                list.appendChild(item);
            });
            resultsDiv.appendChild(list);
        }

        // Store last ROI for highlighting and Decay Tool
        window.lastROI = data.roi_window;
        window.lastROIResult = data;

    } catch (err) {
        resultsDiv.innerHTML = `<p style="color: #ef4444;">Error: ${escapeHtml(err.message)}</p>`;
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


setNotifier(showToast);

/**
 * Handles file upload and processing.
 * Uploads file to server, processes response, and renders dashboard.
 * @param {File} file - The file object to upload
 * @returns {Promise<void>}
 */
async function handleFile(file) {
    if (isAcquiring) {
        if (!(await confirmDialog('A recording is in progress. Stop it and load this file?', { title: 'Recording in progress', okLabel: 'Stop recording', danger: true }))) return;
        stopAcquisition();
    }
    ui.showLoading();
    try {
        const data = await api.uploadFile(file);
        currentData = data;
        ui.resetDropZone();
        ui.renderDashboard(data);
        (data.warnings || []).forEach(w => showToast(w, 'warning'));

        // Auto-populate ROI acquisition time from metadata (if available)
        autoPopulateROITime(data);

        // Store raw XML for N42 files to enable editing
        if (file.name.toLowerCase().endsWith('.n42') || file.name.toLowerCase().endsWith('.xml')) {
            try {
                currentData._rawXml = await file.text();
                debug(`[Main] Stored raw XML (${currentData._rawXml.length} chars)`);
            } catch (e) {
                console.warn('[Main] Failed to read raw XML for editing:', e);
            }
        }

        if (backgroundData) {
            await refreshChartWithBackground();
        } else {
            if (isPageVisible) chartManager.render(data.energies, data.counts, data.peaks, 'linear');
        }
        // Show zoom scrubber with mini preview
        chartManager.showScrubber(data.energies, data.counts);
        saveToHistory(file.name, data);
    } catch (err) {
        ui.showError(err.message);
    }
}

/**
 * Auto-populates ROI acquisition time input from spectrum metadata.
 * Looks for live_time, real_time, or acquisition_time in metadata.
 * Converts seconds to minutes for the UI.
 * @param {Object} data - The spectrum data object with metadata
 */
function autoPopulateROITime(data) {
    if (!data || !data.metadata) return;

    const input = document.getElementById('roi-acq-time');
    if (!input) return;

    // Try to get acquisition time from various metadata fields (in seconds)
    let timeSeconds = null;
    const m = data.metadata;

    if (m.live_time && m.live_time > 0) {
        timeSeconds = m.live_time;
    } else if (m.real_time && m.real_time > 0) {
        timeSeconds = m.real_time;
    } else if (m.acquisition_time && m.acquisition_time > 0) {
        timeSeconds = m.acquisition_time;
    } else if (m.count_time && m.count_time > 0) {
        timeSeconds = m.count_time;
    }

    if (timeSeconds && timeSeconds > 0) {
        // Convert to minutes and set with 1 decimal place
        const timeMinutes = (timeSeconds / 60).toFixed(1);
        input.value = timeMinutes;
        debug(`[ROI] Auto-populated acquisition time: ${timeSeconds}s → ${timeMinutes} min`);
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
    if (!port) return notifyAuto('Select a port');
    try {
        await api.connectDevice(port);
        ui.setDeviceConnected(true);
        startAlphaHoundMonitoring();

        // Update UI for AlphaHound device capabilities
        updateDeviceUI('alphahound');
    } catch (err) {
        notifyAuto(err.message);
    }
}

// ============================================================
// AlphaHound: live dose sparkline, per-channel CPS, details panel, display replica
// ============================================================

const ahSet = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
};
/** The AlphaHound's dose (given in uRem/h) in the chosen unit first, the other in brackets. */
const fmtDoseText = (uRem) => {
    if (uRem === null || uRem === undefined) return '--';
    const uSv = uRem / UREM_PER_USV;
    const first = resolveUnit(getDosePref(), 'uRem');
    return `${formatDoseRate(uSv, first).text} (${formatDoseRate(uSv, first === 'uRem' ? 'uSv' : 'uRem').text})`;
};
let ahDetailsFailures = 0;

/** The live-dose sparkline canvas is shared with the Radiacode: (re)create its chart for the AlphaHound. */
function ensureDoseSparkline() {
    const canvas = document.getElementById('rcDoseRateChart');
    if (!canvas) return;
    if (rcDoseChart) {
        rcDoseChart.destroy();
        rcDoseChart = null;
    }
    canvas.offsetHeight;  // force layout so the canvas has dimensions
    rcDoseChart = new DoseRateChart(canvas, { label: 'Dose Rate', colorVar: '--secondary-color', maxPoints: 60 });
}

/** Our channel panel (cards, log meter, share bar, history chart): created once, reused across connections. */
function ensureChannelPanel() {
    if (!channelPanel) {
        channelPanel = new ChannelPanel(document, {
            onUnitChange: (unit) => { if (deviceScreen) deviceScreen.setRateUnit(unit); },
        });
    }
    return channelPanel;
}

function resetChannelPanel() {
    if (channelPanel) channelPanel.reset();
}

/** Replica colours: a tint of the active theme (default) or the hardware's own white-blue. */
function applyScreenColors() {
    if (!deviceScreen) return;
    const mode = document.getElementById('ah-screen-colors')?.value || 'theme';
    deviceScreen.setPalette(mode === 'device' ? DEVICE_SCREEN_PALETTE : screenPalette(readThemeColors()));
}

/** A theme switch changes more than colours: redraw everything that reads the theme. */
window.addEventListener('themechange', () => {
    if (channelPanel) channelPanel.refreshTheme();
    applyScreenColors();
    if (rcDoseChart) rcDoseChart.refreshTheme();
    redrawDecayChart();
});

/** Create the display replica once (the canvas lives in the AlphaHound details panel). */
function ensureDeviceScreen() {
    if (deviceScreen) return deviceScreen;
    const canvas = document.getElementById('ah-screen');
    if (!canvas) return null;
    deviceScreen = new DeviceScreen(canvas, {
        unit: document.getElementById('ah-screen-dose-unit')?.value,
        rateUnit: channelPanel ? channelPanel.unit : (() => { try { return localStorage.getItem('ahRateUnit'); } catch (e) { return null; } })(),
    });
    const modeSelect = document.getElementById('ah-screen-mode');
    const slotSelect = document.getElementById('ah-screen-slot');
    if (slotSelect) {
        slotSelect.innerHTML = [1, 2, 3, 4].map((n) => `<option value="${n}">M${n}</option>`).join('');
        slotSelect.value = String(deviceScreen.slotIndex + 1);
        slotSelect.addEventListener('change', () => deviceScreen.setSlot(Number(slotSelect.value) - 1));
    }
    if (modeSelect) {
        modeSelect.innerHTML = SCREEN_MODES.map((m) => `<option value="${m.id}">${m.id} · ${m.name}</option>`).join('');
        modeSelect.value = String(deviceScreen.mode.id);
        // choosing a mode assigns it to the slot that is currently selected
        modeSelect.addEventListener('change', () => deviceScreen.setMode(modeSelect.value));
    }
    deviceScreen.onModeChange = (m, slot) => {
        if (modeSelect) modeSelect.value = String(m.id);
        if (slotSelect) slotSelect.value = String(slot + 1);
    };
    document.getElementById('ah-screen-dose-unit')?.addEventListener('change', (e) => deviceScreen.setUnit(e.target.value));
    const colorsSelect = document.getElementById('ah-screen-colors');
    if (colorsSelect) {
        try { colorsSelect.value = localStorage.getItem('ahScreenColors') || 'theme'; } catch (e) { /* default */ }
        colorsSelect.addEventListener('change', () => {
            try { localStorage.setItem('ahScreenColors', colorsSelect.value); } catch (e) { /* ignore */ }
            applyScreenColors();
        });
    }
    applyScreenColors();
    // The arrows press the same buttons as the existing display controls: E/Q go to the device and the replica steps
    document.getElementById('btn-screen-prev')?.addEventListener('click', () => document.getElementById('btn-display-prev')?.click());
    document.getElementById('btn-screen-next')?.addEventListener('click', () => document.getElementById('btn-display-next')?.click());
    deviceScreen.start();
    return deviceScreen;
}

function onAlphaHoundCps(cps) {
    if (!cps) {
        if (channelPanel) channelPanel.showNoData();
        return;
    }
    if (channelPanel) channelPanel.update(cps);
    alertCenter.updateCps((+cps.gamma || 0) + (+cps.beta || 0) + (+cps.alpha || 0));
    if (deviceScreen) deviceScreen.setReadings({ cps });
}

/** Start everything that follows an AlphaHound connection (also used when a refresh restores it). */
function startAlphaHoundMonitoring() {
    ensureDoseSparkline();
    ensureChannelPanel();
    ensureDeviceScreen();
    if (deviceScreen) deviceScreen.setConnected(true);
    api.setupDoseWebSocket(
        (rate) => {
            ui.updateDoseDisplay(rate);
            alertCenter.updateDose(rate / UREM_PER_USV);
            if (rcDoseChart) rcDoseChart.update(rate);
            if (deviceScreen) deviceScreen.setReadings({ dose: rate });
            ahSet('ah-dose', fmtDoseText(rate));
        },
        (status) => ui.updateConnectionStatus(status),
        (cps) => onAlphaHoundCps(cps),
        (msg) => {
            if (msg.dose_rate_avg !== undefined) ahSet('ah-dose-avg', fmtDoseText(msg.dose_rate_avg));
        }
    );
    startAlphaHoundDetails();
}

async function refreshAlphaHoundDetails() {
    try {
        const d = await api.getDeviceDetails();
        ahDetailsFailures = 0;
        ahSet('ah-port', d.port ? `${d.port} @ ${d.baudrate}` : '--');
        setTitleChip(d.port ? `${d.port} · connected` : '');
        ahSet('ah-temp', d.temperature != null ? `${d.temperature.toFixed(1)} \u00b0C` : '--');
        ahSet('ah-comp', d.comp_factor != null ? d.comp_factor.toFixed(4) : '--');
        ahSet('ah-dose', fmtDoseText(d.dose_rate_uRem_h));
        ahSet('ah-dose-avg', fmtDoseText(d.dose_rate_avg_uRem_h));
        ahSet('ah-log-count', `${d.dose_log_entries} readings`);
        if (d.temperature != null) ui.updateTemperature(d.temperature);
    } catch (err) {
        // 400 = the server says the device is gone (unplugged, server restarted): stop pretending after 3 in a row
        if (err.status === 400 && ++ahDetailsFailures >= 3) handleAlphaHoundLost();
    }
}

function handleAlphaHoundLost() {
    ahDetailsFailures = 0;
    stopAlphaHoundDetails();
    api.stopDoseMonitoring();
    ui.setDeviceConnected(false);
    resetDeviceUI();
    ui.updateConnectionStatus('disconnected');
    showToast('AlphaHound connection lost. Reconnect to continue.', 'warning');
}

function startAlphaHoundDetails() {
    ahDetailsFailures = 0;
    refreshAlphaHoundDetails();
    if (!ahDetailsInterval) ahDetailsInterval = setInterval(refreshAlphaHoundDetails, 5000);
}

/** Small "COM8 . connected" tag next to the device name (the connection box is hidden while connected). */
function setTitleChip(text) {
    const chip = document.getElementById('ah-title-chip');
    if (!chip) return;
    chip.textContent = text;
    chip.style.display = text ? 'inline-block' : 'none';
}

function stopAlphaHoundDetails() {
    setTitleChip('');
    alertCenter.reset();
    if (ahDetailsInterval) {
        clearInterval(ahDetailsInterval);
        ahDetailsInterval = null;
    }
    stopAhAutoRefresh();
    const auto = document.getElementById('ah-auto-refresh');
    if (auto) auto.checked = false;
    if (deviceScreen) deviceScreen.setConnected(false);
    resetChannelPanel();
    ['ah-port', 'ah-temp', 'ah-comp', 'ah-dose', 'ah-dose-avg', 'ah-cps-gamma', 'ah-cps-beta', 'ah-cps-alpha', 'ah-cps-total',
        'ah-log-count'].forEach((id) => ahSet(id, '--'));
}

// Auto-refresh of the cumulative spectrum (the manufacturer's AlphaView and the original driver GUI both offer it)
function stopAhAutoRefresh() {
    if (ahAutoRefreshTimer) {
        clearInterval(ahAutoRefreshTimer);
        ahAutoRefreshTimer = null;
    }
}

function startAhAutoRefresh() {
    stopAhAutoRefresh();
    const seconds = Math.min(600, Math.max(5, parseInt(document.getElementById('ah-auto-interval')?.value, 10) || 10));
    ahAutoRefreshTimer = setInterval(ahAutoRefreshTick, seconds * 1000);
    ahAutoRefreshTick();
}

async function ahAutoRefreshTick() {
    if (ahAutoRefreshBusy || isAcquiring || document.hidden) return;
    ahAutoRefreshBusy = true;
    try {
        // A server-managed acquisition polls the device itself: never compete with it for the serial port
        const status = await api.getAcquisitionStatus().catch(() => null);
        if (status && status.is_active) return;
        await getCurrentSpectrum({ quiet: true });
    } finally {
        ahAutoRefreshBusy = false;
    }
}

async function runAhProbe() {
    const cmd = document.getElementById('ah-probe-cmd').value;
    const btn = document.getElementById('btn-probe');
    const out = document.getElementById('ah-probe-output');
    btn.disabled = true;
    out.textContent = `> ${cmd} ...`;
    try {
        const r = await api.probeDevice(cmd);
        out.textContent = `> ${cmd}\n` + (r.lines.length ? r.lines.join('\n') : '(no reply)');
    } catch (err) {
        out.textContent = `Error: ${err.message}`;
    } finally {
        btn.disabled = false;
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

        // Reset device feature UI
        resetDeviceUI();
        stopAlphaHoundDetails();
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
            updateDeviceUI('alphahound');  // enable controls when restoring a live connection after refresh
            // Update temperature if available
            if (status.temperature) {
                ui.updateTemperature(status.temperature);
            }
            startAlphaHoundMonitoring();
        } else {
            ui.setDeviceConnected(false);
        }
    } catch (err) {
        console.error(err);
    }
}

/**
 * Restores the Radiacode UI after a page refresh while the server is still connected.
 * Mirrors the post-connect setup in the Connect handler, without toasts or the init delay.
 * @returns {Promise<void>}
 */
async function checkRadiacodeStatus() {
    try {
        const status = await api.getRadiacodeStatus();
        if (!status.connected) return;
        const connectBtn = document.getElementById('btn-connect-radiacode');
        if (connectBtn) {
            connectBtn.textContent = 'Connected';
            connectBtn.style.display = 'none';
        }
        const disconnectBtn = document.getElementById('btn-disconnect-device');
        if (disconnectBtn) disconnectBtn.style.display = 'inline-block';
        const dropZone = document.getElementById('drop-zone');
        if (dropZone) dropZone.style.display = 'none';
        const rcChartCanvas = document.getElementById('rcDoseRateChart');
        if (rcChartCanvas && !rcDoseChart) {
            rcDoseChart = new DoseRateChart(rcChartCanvas, {
                label: 'Dose Rate',
                colorVar: '--secondary-color',
                maxPoints: 60
            });
        }
        ui.setDeviceConnected(true);
        updateDeviceUI('radiacode');
        startRadiacodeDosePolling();
    } catch (err) {
        console.error('[Radiacode] Status restore error:', err);
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

                // Exposure received during this acquisition (integrated dose rate)
                const expEl = document.getElementById('acquisition-exposure');
                if (expEl) {
                    const ex = status.exposure;
                    expEl.textContent = ex
                        ? '· ' + formatDoseTotal(ex.exposure_uSv, resolveUnit(getDosePref(), 'uSv'))
                        : '';
                }

                // Update spectrum display if data available
                if (status.spectrum_data) {
                    currentData = status.spectrum_data;
                    ui.renderDashboard(currentData, { live: true });
                    if (isPageVisible) {
                        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
                        // Ensure scrubber is visible and updated
                        chartManager.showScrubber(currentData.energies, currentData.counts);
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
                        ui.renderDashboard(currentData, { live: true });
                        if (isPageVisible) {
                            chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
                            // Ensure scrubber is visible and updated
                            chartManager.showScrubber(currentData.energies, currentData.counts);
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
        notifyAuto(err.message);
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
    if (serverStatus) serverStatus.style.display = 'none';
}

/**
 * Shows server-managed acquisition UI indicators.
 * @returns {void}
 */
function showServerManagedUI() {
    const serverStatus = document.getElementById('acquisition-server-status');
    if (serverStatus) serverStatus.style.display = 'inline';
}

/**
 * Gets the current cumulative spectrum from the device without clearing.
 * Useful for checking what's accumulated on the device or resuming after browser disconnect.
 * @returns {Promise<void>}
 */
async function getCurrentSpectrum(opts = {}) {
    // quiet: used by the AlphaHound auto-refresh, which must not toast every few seconds
    const quiet = !!opts && opts.quiet === true;
    try {
        if (!quiet) showToast('Fetching current spectrum from device...', 'info');

        // Use unified API wrapper
        const data = await api.getCurrentSpectrumUnified();
        currentData = data;
        if (deviceScreen && data.counts) deviceScreen.setSpectrum(data.counts, data.energies);

        // Show dashboard if hidden
        document.getElementById('drop-zone').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        ui.renderDashboard(data);
        if (isPageVisible) {
            chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
            // Show zoom scrubber
            chartManager.showScrubber(data.energies, data.counts);
        }

        if (!quiet) {
            showToast('Current spectrum loaded (cumulative from device)', 'success');
            (data.warnings || []).forEach(w => showToast(w, 'warning'));
        }

    } catch (err) {
        console.error('Get current spectrum error:', err);
        if (!quiet) showToast(`Error: ${err.message}`, 'warning');
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

    // Create history entry with FULL data
    // Limit data size if necessary, but 4096 floats is small enough (~32KB)
    const entry = {
        filename,
        timestamp: new Date().toISOString(),
        preview: {
            peakCount: data.peaks?.length || 0,
            isotopes: data.isotopes?.slice(0, 3).map(i => i.isotope) || []
        },
        data: {
            energies: data.energies,
            counts: data.counts,
            peaks: data.peaks,
            metadata: data.metadata,
            isotopes: data.isotopes,
            decay_chains: data.decay_chains,
            detector: data.detector,
            roi_window: data.roi_window,
            efficiency_percent: data.efficiency_percent,
            branching_ratio: data.branching_ratio,
            is_calibrated: data.is_calibrated,
            enhanced_analysis: data.enhanced_analysis
        }
    };

    history.unshift(entry);

    // Store last 10 entries
    // Check total size might be good in future, but 10 * 100KB = 1MB is safe
    try {
        localStorage.setItem('fileHistory', JSON.stringify(history.slice(0, 10)));
    } catch (e) {
        console.warn('History storage failed (quota exceeded?):', e);
        // Fallback: try saving fewer items or just preview
        const minimized = history.slice(0, 5);
        try {
            localStorage.setItem('fileHistory', JSON.stringify(minimized));
        } catch (e2) {
            console.error('History storage critically failed:', e2);
        }
    }
}

/**
 * Loads a spectrum from history.
 * @param {number} index - Index in the history array
 */
function loadFromHistory(index) {
    const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');
    if (index < 0 || index >= history.length) return;

    const item = history[index];
    if (!item.data || !item.data.counts) {
        notifyAuto('This history item is invalid or from an older version (no data stored).');
        return;
    }

    const data = item.data;

    // Restore currentData
    currentData = data;

    // Update UI
    ui.renderDashboard(data);

    // Show chart if visible
    if (isPageVisible) {
        chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
        chartManager.showScrubber(data.energies, data.counts);
    }

    // Close modal
    document.getElementById('history-modal').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';

    showToast(`Loaded "${item.filename}" from history`, 'success');
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
    } catch (err) { notifyAuto(err.message); }
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
    } catch (err) { notifyAuto(err.message); }
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
    const bgIndicator = document.getElementById('bg-active-indicator');
    if (bgIndicator) bgIndicator.style.display = 'inline';
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
            notifyAuto('Background subtraction failed: ' + e.message);
        }
    } else {
        chartManager.render(currentData.energies, currentData.counts, currentData.peaks, chartManager.getScaleType());
    }
}

/**
 * Takes a spectrum that the server analysed again (the energy axis was corrected) as the current one and shows it.
 * @param {object} data - the analysis result
 * @returns {void}
 */
function applyAnalysis(data) {
    currentData = data;
    ui.renderDashboard(data);
    if (backgroundData) {
        refreshChartWithBackground();
    } else {
        chartManager.render(data.energies, data.counts, data.peaks || [], chartManager.getScaleType());
    }
}

/**
 * Applies a hand-made linear energy calibration (E = slope * channel + intercept) to the current spectrum: the server analyses it again on the
 * new axis, so the peaks, isotopes and chains follow it (they used to keep the energies of the old axis while the chart showed the new one).
 * @param {number} slope - Energy per channel (keV/ch)
 * @param {number} intercept - Energy offset (keV)
 * @returns {Promise<void>}
 */
async function applyCalibration(slope, intercept) {
    if (!currentData) return;
    const energies = currentData.counts.map((_, ch) => slope * ch + intercept);
    try {
        const response = await fetch('/analyze/reanalyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                energies,
                counts: currentData.counts,
                metadata: { ...(currentData.metadata || {}), calibration: { slope, intercept } },
                live_time: Number(currentData.metadata?.live_time) || 0,
            }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail;
            throw new Error(detail || `Request failed (${response.status})`);
        }
        applyAnalysis(body);
        showToast(`Calibration applied: E = ${slope.toFixed(4)} * Ch + ${intercept.toFixed(4)}`, 'success');
    } catch (err) {
        showToast(`Could not apply the calibration: ${err.message}`, 'error');
    }
}


// Initialize Estimator with Callbacks
document.addEventListener('DOMContentLoaded', () => {
    estimatorUI.init({
        getCurrentData: () => currentData,
        onShowProjection: (factor) => {
            if (!currentData || !currentData.counts) return;

            // Calculate projected counts
            const projectedCounts = currentData.counts.map(c => c * factor);

            // Add to overlay
            if (!overlaySpectra) overlaySpectra = [];

            // Generate a color (simple rotation)
            const color = colors[overlaySpectra.length % colors.length];

            overlaySpectra.push({
                name: `Projection (${factor.toFixed(1)}x)`,
                energies: currentData.energies,
                counts: projectedCounts,
                color: color
            });

            // Enable Compare Mode UI
            compareMode = true;
            document.getElementById('compare-panel').style.display = 'flex';
            document.getElementById('btn-compare').classList.add('active');
            updateOverlayCount();

            // Render
            chartManager.renderComparison(overlaySpectra, chartManager.getScaleType());
        }
    });

    // Decay Tool Listeners handled earlier (Lines 1961+)

    // Also ensure populateDetectorOptions is called for other dropdowns if needed
    // But estimatorUI handles its own dropdowns.
});

// setupDecayTool removed (inlined)
