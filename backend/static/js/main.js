// Updated: 2024-12-14 17:00 - N42 Export Fixed
import { api } from './api.js';
import { ui } from './ui.js?v=2.9';
import { chartManager, DoseRateChart } from './charts.js?v=3.8';
import { calUI } from './calibration.js';
import { isotopeUI } from './isotopes_ui.js';
import { n42MetadataEditor } from './n42_editor.js';
import { estimatorUI } from './estimator_ui.js';
import { updateDeviceUI, resetDeviceUI } from './device_features.js';

// Expose chartManager globally for cross-module access (e.g., XRF highlighting from ui.js)
window.chartManager = chartManager;

// Global State
let currentData = null;
let isAcquiring = false;
let acquisitionInterval = null;
let acquisitionStartTime = null;
let overlaySpectra = [];
let compareMode = false;
let backgroundData = null; // New background state
let doseChart = null; // Live dose rate chart instance
let rcDoseChart = null; // Radiacode dose rate chart instance
let lastCheckpointTime = 0; // Checkpoint save tracking
const CHECKPOINT_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes between checkpoints
let radiacodeDoseInterval = null;  // Radiacode dose rate polling interval
const colors = ['#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

// ============================================================
// Radiacode Dose Rate Polling
// ============================================================
function startRadiacodeDosePolling() {
    if (radiacodeDoseInterval) return;  // Already polling

    console.log('[Radiacode] Starting dose rate polling');

    // Poll immediately, then every 2 seconds
    pollRadiacodeDose();
    radiacodeDoseInterval = setInterval(pollRadiacodeDose, 2000);
}

function stopRadiacodeDosePolling() {
    if (radiacodeDoseInterval) {
        console.log('[Radiacode] Stopping dose rate polling');
        clearInterval(radiacodeDoseInterval);
        radiacodeDoseInterval = null;
    }
}

async function pollRadiacodeDose() {
    try {
        const result = await api.getRadiacodeDose();
        const doseEl = document.getElementById('rc-dose-display');
        if (doseEl && result.dose_rate_uSv_h !== undefined) {
            // Format dose rate with proper precision
            const dose = result.dose_rate_uSv_h;
            let displayValue;
            if (dose >= 1000) {
                displayValue = (dose / 1000).toFixed(2) + ' mSv/h';
            } else if (dose >= 1) {
                displayValue = dose.toFixed(2) + ' μSv/h';
            } else {
                displayValue = (dose * 1000).toFixed(1) + ' nSv/h';
            }
            doseEl.textContent = displayValue;

            // Update sparkline chart if initialized
            if (rcDoseChart) {
                rcDoseChart.addDataPoint(dose);
            }
        }

        // Update device info periodically (every 10 polls ~20 seconds)
        if (!pollRadiacodeDose._pollCount) pollRadiacodeDose._pollCount = 0;
        pollRadiacodeDose._pollCount++;
        if (pollRadiacodeDose._pollCount % 10 === 0) {
            try {
                const extendedInfo = await api.getRadiacodeExtendedInfo();
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
                console.log('[Radiacode] Extended info unavailable:', extErr.message);
            }
        }
    } catch (err) {
        // Don't spam errors - just log once
        if (!pollRadiacodeDose._hasError) {
            console.warn('[Radiacode] Dose poll error:', err.message);
            pollRadiacodeDose._hasError = true;
        }
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
    console.log('[Theme] Re-applied isotope highlights for', window._selectedIsotopes.size, 'isotopes');

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
    console.log(`[UI Mode] Applying "${mode}" mode: ${config.description}`);

    // First, hide elements that should be hidden in this mode
    if (config.hideElements && config.hideElements.length > 0) {
        config.hideElements.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.style.display = 'none';
                console.log(`[UI Mode] Hiding: ${id}`);
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
                console.log(`[UI Mode] Showing: ${id}`);
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
            showToast('Getting accumulated spectrum...', 'info');
            const data = await api.getAccumulatedSpectrum();

            // Backend now returns fully analyzed data with energies, counts, peaks, isotopes
            currentData = data;

            // Show dashboard if hidden (in case this is first load)
            document.getElementById('drop-zone').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';

            // Render full dashboard with all analysis (peaks, isotopes, XRF)
            ui.renderDashboard(data);
            chartManager.render(data.energies, data.counts, data.peaks || [], 'linear');

            const durationMin = (data.duration / 60).toFixed(1);
            showToast(`Accumulated spectrum: ${durationMin} min, ${(data.peaks || []).length} peaks`, 'success');
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
        console.log('[Radiacode] HW serial unavailable:', err.message);
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
        if (!confirm('Power off the Radiacode device?\n\nYou will need to manually power it back on.')) {
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
        const result = await api.getTextMessage();
        const banner = document.getElementById('rc-message-banner');
        const textEl = document.getElementById('rc-message-text');

        if (result.has_message && result.message) {
            textEl.textContent = result.message;
            banner.style.display = 'block';
        } else {
            banner.style.display = 'none';
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
    // Initialize Dose Rate Chart (if element exists)
    doseChart = new DoseRateChart();

    await refreshPorts();
    await checkDeviceStatus();
    // Duplicate check removed
    setupEventListeners();
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
    // File Upload & Drag-and-Drop
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    // Upload button in header
    const btnUpload = document.getElementById('btn-upload-file');
    if (btnUpload && fileInput) {
        btnUpload.addEventListener('click', () => fileInput.click());
    }

    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            if (e.dataTransfer.files.length) {
                handleFile(e.dataTransfer.files[0]);
            }
        });

        // Delegate click to file input - only if clicking on drop zone itself or allowed children
        dropZone.addEventListener('click', (e) => {
            // Get the current file input (may have been recreated)
            const currentFileInput = document.getElementById('file-input');
            // Only trigger if not clicking directly on the input itself
            if (currentFileInput && e.target !== currentFileInput && !e.target.closest('input[type="file"]')) {
                currentFileInput.click();
            }
        });
    }

    // Use event delegation for file input since it may be recreated
    document.addEventListener('change', (e) => {
        if (e.target && e.target.id === 'file-input') {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
                // Reset the input value so the same file can be selected again
                e.target.value = '';
            }
        }
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

    // UI Complexity Mode change listener
    document.querySelectorAll('input[name="ui-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const newMode = e.target.value;
            applyUIMode(newMode);
            console.log(`[Settings] UI Mode changed to: ${newMode}`);
        });
    });

    // ============================================================
    // Device Type Tab Switching (AlphaHound / Radiacode)
    // Now toggles connection rows, not entire panels
    // ============================================================
    const tabAlphahound = document.getElementById('tab-alphahound');
    const tabRadiacode = document.getElementById('tab-radiacode');
    const alphahoundRow = document.getElementById('alphahound-connection-row');
    const radiacodeRow = document.getElementById('radiacode-connection-row');
    const deviceTitle = document.getElementById('device-title');

    if (tabAlphahound && tabRadiacode && alphahoundRow && radiacodeRow) {
        tabAlphahound.addEventListener('click', () => {
            // Update tab active state
            tabAlphahound.classList.add('active');
            tabRadiacode.classList.remove('active');

            // Show AlphaHound connection, hide Radiacode
            alphahoundRow.style.display = 'flex';
            radiacodeRow.style.display = 'none';

            // Update title
            if (deviceTitle) deviceTitle.textContent = 'AlphaHound Device';
        });

        tabRadiacode.addEventListener('click', () => {
            // Update tab active state
            tabRadiacode.classList.add('active');
            tabAlphahound.classList.remove('active');

            // Show Radiacode connection, hide AlphaHound
            radiacodeRow.style.display = 'flex';
            alphahoundRow.style.display = 'none';

            // Update title
            if (deviceTitle) deviceTitle.textContent = 'Radiacode Device';
        });
    }



    // Radiacode connection mode toggle (show/hide BLE controls)
    document.querySelectorAll('input[name="rc-conn-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const bleControls = document.getElementById('rc-ble-controls');
            if (bleControls) {
                bleControls.style.display = e.target.value === 'bluetooth' ? 'flex' : 'none';
            }
        });
    });

    // Radiacode BLE Scan Button
    const btnScanBle = document.getElementById('btn-scan-ble');
    if (btnScanBle) {
        btnScanBle.addEventListener('click', async () => {
            const deviceSelect = document.getElementById('rc-ble-devices');
            if (!deviceSelect) return;

            btnScanBle.disabled = true;
            btnScanBle.innerHTML = '<img src="/static/icons/refresh.svg" class="icon spin" style="width: 14px; height: 14px;"> Scanning...';

            try {
                const devices = await api.scanRadiacodeBLE(5.0);
                console.log('[Radiacode] BLE scan found:', devices);

                // Clear and populate dropdown
                deviceSelect.innerHTML = '<option value="">Select BLE Device...</option>';

                if (devices.length === 0) {
                    deviceSelect.innerHTML += '<option value="" disabled>No devices found</option>';
                    showToast('No Radiacode devices found. Make sure the device is powered on and in range.', 'warning');
                } else {
                    devices.forEach(device => {
                        const rssiInfo = device.rssi !== null ? ` (${device.rssi} dBm)` : '';
                        deviceSelect.innerHTML += `<option value="${device.address}">${device.name}${rssiInfo}</option>`;
                    });
                    showToast(`Found ${devices.length} Radiacode device(s)`, 'success');
                }
            } catch (err) {
                console.error('[Radiacode] BLE scan error:', err);
                showToast(`BLE scan failed: ${err.message}`, 'error');
            } finally {
                btnScanBle.disabled = false;
                btnScanBle.innerHTML = '<img src="/static/icons/refresh.svg" class="icon" style="width: 14px; height: 14px;"> Scan';
            }
        });
    }

    // Radiacode Connect Button
    const btnConnectRadiacode = document.getElementById('btn-connect-radiacode');
    if (btnConnectRadiacode) {
        btnConnectRadiacode.addEventListener('click', async () => {
            const useBluetooth = document.querySelector('input[name="rc-conn-mode"]:checked')?.value === 'bluetooth';

            // Get BLE address from dropdown or manual input
            let bluetoothMac = null;
            if (useBluetooth) {
                const deviceSelect = document.getElementById('rc-ble-devices');
                const manualMac = document.getElementById('rc-bluetooth-mac')?.value?.trim();
                bluetoothMac = deviceSelect?.value || manualMac || null;

                if (!bluetoothMac) {
                    showToast('Please scan for devices and select one, or enter a MAC address manually', 'warning');
                    return;
                }
            }

            btnConnectRadiacode.disabled = true;
            btnConnectRadiacode.textContent = 'Connecting...';

            try {
                const result = await api.connectRadiacode(useBluetooth, bluetoothMac);
                console.log('[Radiacode] Connected:', result);

                // Show connected panel
                const connectedPanel = document.getElementById('radiacode-connected');
                if (connectedPanel) connectedPanel.style.display = 'grid';

                // Update model display
                const modelSpan = document.getElementById('rc-device-model');
                if (modelSpan && result.device_info) {
                    modelSpan.textContent = result.device_info.model || 'Radiacode';
                }

                btnConnectRadiacode.textContent = 'Connected';
                showToast('Radiacode connected successfully', 'success');

                // Initialize dose rate sparkline chart
                const rcChartCanvas = document.getElementById('rcDoseRateChart');
                if (rcChartCanvas) {
                    // Destroy existing chart if any to avoid conflicts
                    if (rcDoseChart) {
                        rcDoseChart.destroy();
                        rcDoseChart = null;
                    }

                    // Force layout reflow to ensure canvas has dimensions
                    rcChartCanvas.offsetHeight;

                    rcDoseChart = new DoseRateChart(rcChartCanvas, {
                        label: 'Dose Rate',
                        colorVar: '--secondary-color', // Respect the current theme
                        maxPoints: 60
                    });
                }

                // Disable acquisition buttons during initialization
                const acquireBtn = document.getElementById('btn-acquire-spectrum');
                const getAccumulatedBtn = document.getElementById('btn-get-accumulated');
                const getCurrentBtn = document.getElementById('btn-get-current');

                if (acquireBtn) acquireBtn.disabled = true;
                if (getAccumulatedBtn) getAccumulatedBtn.disabled = true;
                if (getCurrentBtn) getCurrentBtn.disabled = true;

                // Show initializing toast
                showToast('Device initializing... (2s)', 'info');

                // Start dose rate polling after a brief delay to allow device data stream to initialize
                // The Radiacode library needs ~2 seconds after connection before data_buf() returns data
                setTimeout(() => {
                    startRadiacodeDosePolling();

                    // Re-enable acquisition buttons after initialization
                    if (acquireBtn) acquireBtn.disabled = false;
                    if (getAccumulatedBtn) getAccumulatedBtn.disabled = false;
                    if (getCurrentBtn) getCurrentBtn.disabled = false;

                    showToast('Device ready for acquisition', 'success');
                }, 2000);

                // Show disconnect button, hide connect button (keep connection row visible!)
                document.getElementById('btn-connect-radiacode').style.display = 'none';
                document.getElementById('btn-disconnect-device').style.display = 'inline-block';

                // Hide drop zone since Upload button in header is sufficient
                const dropZone = document.getElementById('drop-zone');
                if (dropZone) dropZone.style.display = 'none';

                // Update UI for Radiacode device capabilities
                updateDeviceUI('radiacode');
            } catch (err) {
                console.error('[Radiacode] Connect error:', err);
                showToast(`Connection failed: ${err.message}`, 'error');
                btnConnectRadiacode.textContent = 'Connect';
            } finally {
                btnConnectRadiacode.disabled = false;
            }
        });
    }

    // Radiacode Disconnect Button
    const btnDisconnectRadiacode = document.getElementById('btn-disconnect-radiacode');
    if (btnDisconnectRadiacode) {
        btnDisconnectRadiacode.addEventListener('click', async () => {
            try {
                stopRadiacodeDosePolling();  // Stop polling first
                await api.disconnectRadiacode();
                const connectedPanel = document.getElementById('radiacode-connected');
                if (connectedPanel) connectedPanel.style.display = 'none';
                document.getElementById('btn-connect-radiacode').textContent = 'Connect';
                document.getElementById('rc-dose-display').textContent = '--';
                showToast('Radiacode disconnected', 'info');

                // Reset device feature UI
                resetDeviceUI();
            } catch (err) {
                console.error('[Radiacode] Disconnect error:', err);
            }
        });
    }

    // Radiacode Get Spectrum Button
    const btnRcGetSpectrum = document.getElementById('btn-rc-get-spectrum');
    if (btnRcGetSpectrum) {
        btnRcGetSpectrum.addEventListener('click', async () => {
            btnRcGetSpectrum.disabled = true;
            btnRcGetSpectrum.textContent = 'Loading...';

            try {
                const data = await api.getRadiacodeSpectrum(true);
                console.log('[Radiacode] Spectrum received:', data);

                currentData = data;
                ui.renderDashboard(data);
                chartManager.render(data.energies, data.counts, data.peaks, 'linear');
                chartManager.showScrubber(data.energies, data.counts);  // Show zoom slider

                showToast('Spectrum loaded from Radiacode', 'success');
            } catch (err) {
                console.error('[Radiacode] Spectrum error:', err);
                showToast(`Failed to get spectrum: ${err.message}`, 'error');
            } finally {
                btnRcGetSpectrum.disabled = false;
                btnRcGetSpectrum.innerHTML = '<img src="/static/icons/chart.svg" class="icon"> Get Spectrum';
            }
        });
    }

    // Radiacode Clear Spectrum Button
    const btnRcClear = document.getElementById('btn-rc-clear');
    if (btnRcClear) {
        btnRcClear.addEventListener('click', async () => {
            try {
                await api.clearRadiacodeSpectrum();
                showToast('Radiacode spectrum cleared', 'info');
            } catch (err) {
                console.error('[Radiacode] Clear error:', err);
                showToast(`Failed to clear: ${err.message}`, 'error');
            }
        });
    }

    // Radiacode Reset Dose Button (Radiacode-only feature)
    const btnRcResetDose = document.getElementById('btn-rc-reset-dose');
    if (btnRcResetDose) {
        btnRcResetDose.addEventListener('click', async () => {
            try {
                await api.resetRadiacodeDose();
                showToast('Radiacode dose reset', 'info');
            } catch (err) {
                console.error('[Radiacode] Reset dose error:', err);
                showToast(`Failed to reset dose: ${err.message}`, 'error');
            }
        });
    }

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
        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Generating...';
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
        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Exporting...';
        btn.disabled = true;

        try {
            const response = await api.exportN42({
                ...currentData,
                // Ensure we use the best metadata available (including potential edits)
                metadata: {
                    ...currentData.metadata,
                    // Ensure critical fields are set if missing
                    live_time: currentData.metadata?.live_time || currentData.metadata?.acquisition_time || 1.0,
                    real_time: currentData.metadata?.real_time || currentData.metadata?.acquisition_time || 1.0,
                    start_time: currentData.metadata?.start_time || new Date().toISOString(),
                    source: currentData.metadata?.source || 'AlphaHound Device',
                    channels: currentData.counts.length
                }
            });

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            // Use existing filename or generate one
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            a.download = (currentData.metadata?.filename || `spectrum_export_${timestamp}`).replace('.n42', '') + '.n42';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            // Revert button
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        } catch (err) {
            alert('Error exporting N42: ' + err.message);
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    });

    // Edit N42 Metadata Button
    const btnEditN42 = document.getElementById('btn-edit-n42');
    btnEditN42?.addEventListener('click', async () => {
        if (!currentData) return ui.showError('No spectrum loaded to edit');

        // Prevent multiple simultaneous clicks
        if (btnEditN42.disabled) return;

        // Use stored raw XML or generate it
        let xmlContent = currentData._rawXml;

        if (!xmlContent) {
            // Generate template from current data
            const toast = document.createElement('div');
            toast.textContent = 'Generating metadata template...';
            toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#3b82f6;color:white;padding:12px 24px;border-radius:8px;z-index:9999;box-shadow:0 4px 6px rgba(0,0,0,0.1);';
            document.body.appendChild(toast);

            try {
                // Set loading state
                const originalHtml = btnEditN42.innerHTML;
                btnEditN42.disabled = true;
                btnEditN42.style.opacity = '0.7';
                btnEditN42.innerHTML = '<span class="spinner-inline"></span> Generating...';

                // We use export_n42 logic to generate the XML string
                const response = await api.exportN42({
                    ...currentData,
                    metadata: currentData.metadata || {}
                });
                if (response.ok) {
                    xmlContent = await response.text();
                    currentData._rawXml = xmlContent;
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
                currentData._rawXml = newXml;

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

        // Apply UI Complexity Mode (controls panel visibility)
        const uiModeRadio = document.querySelector('input[name="ui-mode"]:checked');
        const uiMode = uiModeRadio ? uiModeRadio.value : 'simple';
        currentSettings.uiMode = uiMode;
        applyUIMode(uiMode);

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
            historyList.innerHTML = history.map((item, index) => {
                // Check if item has data (legacy support check)
                const hasData = item.data && item.data.energies;
                const statusClass = hasData ? '' : 'opacity: 0.5; cursor: not-allowed;';
                const statusTitle = hasData ? 'Click to load' : 'Old history item (no data)';

                return `
                <div class="history-item" data-index="${index}" style="${statusClass}" title="${statusTitle}">
                    <div class="history-item-name">${item.filename}</div>
                    <div class="history-item-date">${new Date(item.timestamp).toLocaleString()}</div>
                    <div style="font-size: 0.875rem; margin-top: 0.5rem;">
                        ${item.preview.peakCount} peaks | ${(item.preview.isotopes || []).join(', ') || 'No isotopes'}
                    </div>
                </div>
            `;
            }).join('');

            // Add click listeners
            document.querySelectorAll('.history-item').forEach(el => {
                el.addEventListener('click', () => {
                    const index = parseInt(el.getAttribute('data-index'));
                    loadFromHistory(index);
                });
            });
        }
        modal.style.display = 'flex';
    });

    document.getElementById('close-history').addEventListener('click', () => {
        document.getElementById('history-modal').style.display = 'none';
    });

    // NOTE: Background subtraction listeners registered below with full set (btn-load-bg, btn-set-current-bg, btn-clear-bg)

    // Theme Dropdown
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        // Set initial value from localStorage
        const savedTheme = localStorage.getItem('theme') || 'dark';
        themeSelect.value = savedTheme;
        document.documentElement.setAttribute('data-theme', savedTheme);

        themeSelect.addEventListener('change', (e) => {
            const newTheme = e.target.value;
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            if (currentData) {
                const scale = chartManager.getScaleType();
                chartManager.render(currentData.energies, currentData.counts, currentData.peaks, scale);

                // Re-apply isotope highlights after theme change re-renders chart
                reapplyIsotopeHighlights();
            }
        });
    }

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
        console.log('[Main] Auto-scale button clicked, currentData exists:', !!currentData);
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

    // Unified Device Control Buttons
    // These work with both AlphaHound and Radiacode automatically

    // Clear Spectrum button
    document.getElementById('btn-clear-spectrum')?.addEventListener('click', async () => {
        try {
            await api.clearSpectrumUnified();
            showToast('Spectrum cleared', 'success');
        } catch (err) {
            showToast(err.message || 'Failed to clear spectrum', 'error');
        }
    });

    // Reset Dose button (Radiacode only)
    document.getElementById('btn-reset-dose')?.addEventListener('click', async () => {
        try {
            await api.resetDoseUnified();
            showToast('Dose reset successfully', 'success');
        } catch (err) {
            showToast(err.message || 'Failed to reset dose', 'error');
        }
    });

    // Disconnect button (unified)
    document.getElementById('btn-disconnect-device').addEventListener('click', async () => {
        try {
            // Stop polling FIRST (before API call) - critical for clean disconnect
            stopRadiacodeDosePolling();
            await api.disconnectUnified();
            ui.setDeviceConnected(false);
            stopAcquisition();
            resetDeviceUI();

            // Show connect button, hide disconnect button (keep connection row visible!)
            document.getElementById('btn-connect-radiacode').style.display = 'inline-block';
            document.getElementById('btn-disconnect-device').style.display = 'none';
        } catch (err) {
            console.error('Disconnect error:', err);
        }
    });

    // Radiacode Settings Event Handlers
    const rcBrightness = document.getElementById('rc-brightness');
    if (rcBrightness) {
        // Live update brightness value display
        rcBrightness.addEventListener('input', (e) => {
            const valueEl = document.getElementById('rc-brightness-value');
            if (valueEl) valueEl.textContent = e.target.value;
        });

        // Send to device on change complete
        rcBrightness.addEventListener('change', async (e) => {
            try {
                await api.setRadiacodeBrightness(parseInt(e.target.value));
                console.log(`[Radiacode] Brightness set to ${e.target.value}`);
            } catch (err) {
                console.error('[Radiacode] Failed to set brightness:', err);
                showToast(`Failed to set brightness: ${err.message}`, 'error');
            }
        });
    }

    const rcSound = document.getElementById('rc-sound');
    if (rcSound) {
        rcSound.addEventListener('change', async (e) => {
            try {
                await api.setRadiacodeSound(e.target.checked);
                console.log(`[Radiacode] Sound ${e.target.checked ? 'enabled' : 'disabled'}`);
            } catch (err) {
                console.error('[Radiacode] Failed to set sound:', err);
                showToast(`Failed to set sound: ${err.message}`, 'error');
                e.target.checked = !e.target.checked; // Revert on error
            }
        });
    }

    const rcVibration = document.getElementById('rc-vibration');
    if (rcVibration) {
        rcVibration.addEventListener('change', async (e) => {
            try {
                await api.setRadiacodeVibration(e.target.checked);
                console.log(`[Radiacode] Vibration ${e.target.checked ? 'enabled' : 'disabled'}`);
            } catch (err) {
                console.error('[Radiacode] Failed to set vibration:', err);
                showToast(`Failed to set vibration: ${err.message}`, 'error');
                e.target.checked = !e.target.checked; // Revert on error
            }
        });
    }

    const rcDisplayTimeout = document.getElementById('rc-display-timeout');
    if (rcDisplayTimeout) {
        rcDisplayTimeout.addEventListener('blur', async (e) => {
            try {
                const seconds = parseInt(e.target.value) || 0;
                await api.setRadiacodeDisplayTimeout(seconds);
                console.log(`[Radiacode] Display timeout set to ${seconds}s`);
            } catch (err) {
                console.error('[Radiacode] Failed to set display timeout:', err);
                showToast(`Failed to set timeout: ${err.message}`, 'error');
            }
        });
    }

    const rcLanguage = document.getElementById('rc-language');
    if (rcLanguage) {
        rcLanguage.addEventListener('change', async (e) => {
            try {
                await api.setRadiacodeLanguage(e.target.value);
                console.log(`[Radiacode] Language set to ${e.target.value}`);
                showToast('Language updated on device', 'success');
            } catch (err) {
                console.error('[Radiacode] Failed to set language:', err);
                showToast(`Failed to set language: ${err.message}`, 'error');
            }
        });
    }

    const btnViewConfig = document.getElementById('btn-view-config');
    if (btnViewConfig) {
        btnViewConfig.addEventListener('click', async () => {
            try {
                const info = await api.getRadiacodeExtendedInfo();
                if (info.configuration) {
                    alert(`Radiacode Configuration:\n\n${info.configuration}`);
                } else {
                    alert('Configuration data not available');
                }
            } catch (err) {
                console.error('[Radiacode] Failed to get configuration:', err);
                showToast(`Failed to get configuration: ${err.message}`, 'error');
            }
        });
    }

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

        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 14px; height: 14px;"> Processing...';
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
            statusEl.innerHTML = '<img src="/static/icons/check.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Background removed <em>(chart only - analysis unchanged)</em>';
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
                    'good': '<img src="/static/icons/check.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> High Confidence',
                    'moderate': '<img src="/static/icons/warning.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> Moderate',
                    'low_confidence': '<img src="/static/icons/warning.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> Low Confidence',
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

        btn.innerHTML = '<img src="/static/icons/hourglass.svg" class="icon spin" style="width: 16px; height: 16px;"> Running...';
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
            mlList.innerHTML = `<p style="color: #ef4444;"><img src="/static/icons/error.svg" class="icon" style="width: 14px; height: 14px; filter: invert(41%) sepia(93%) saturate(1352%) hue-rotate(336deg);"> Error: ${err.message}</p>`;
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
        document.getElementById('calibration-modal').style.display = 'flex';
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
            activityStr = `<span style="color: var(--primary-color); font-weight: 600;">${data.activity_bq.toFixed(1)} Bq</span> (${data.activity_uci.toFixed(6)} μCi)`;
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

        // Confidence Bar
        if (data.confidence !== undefined) {
            const confPercent = Math.round(data.confidence * 100);
            const confColor = data.confidence > 0.7 ? '#10b981' :
                data.confidence > 0.4 ? '#f59e0b' : '#ef4444';

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
    // Input is in minutes, convert to seconds for API
    const acqTimeMinutes = parseFloat(document.getElementById('roi-acq-time').value) || 10;
    const acqTime = acqTimeMinutes * 60;

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

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(formatErrorMessage(errData));
        }
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
            info: { bg: '#3b82f6', border: '#3b82f6', shadow: 'rgba(59, 130, 246, 0.3)' },
            error: { bg: '#ef4444', border: '#ef4444', shadow: 'rgba(239, 68, 68, 0.3)' }
        },
        'light': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.2)' },
            warning: { bg: '#f59e0b', border: '#d97706', shadow: 'rgba(245, 158, 11, 0.2)' },
            info: { bg: '#3b82f6', border: '#2563eb', shadow: 'rgba(59, 130, 246, 0.2)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.2)' }
        },
        'nuclear': {
            success: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' },
            warning: { bg: '#f59e0b', border: '#ea580c', shadow: 'rgba(245, 158, 11, 0.4)' },
            info: { bg: '#fbbf24', border: '#f59e0b', shadow: 'rgba(251, 191, 36, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'toxic': {
            success: { bg: '#10b981', border: '#059669', shadow: 'rgba(16, 185, 129, 0.4)' },
            warning: { bg: '#84cc16', border: '#65a30d', shadow: 'rgba(132, 204, 22, 0.4)' },
            info: { bg: '#22c55e', border: '#16a34a', shadow: 'rgba(34, 197, 94, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'scifi': {
            success: { bg: '#00d9ff', border: '#3b82f6', shadow: 'rgba(0, 217, 255, 0.5)' },
            warning: { bg: '#a855f7', border: '#9333ea', shadow: 'rgba(168, 85, 247, 0.5)' },
            info: { bg: '#3b82f6', border: '#00d9ff', shadow: 'rgba(59, 130, 246, 0.5)' },
            error: { bg: '#ef4444', border: '#f87171', shadow: 'rgba(239, 68, 68, 0.5)' }
        },
        'cyberpunk': {
            success: { bg: '#fcee09', border: '#00f5ff', shadow: '0 0 20px rgba(252, 238, 9, 0.6), 0 0 40px rgba(0, 245, 255, 0.3)' },
            warning: { bg: '#ff006e', border: '#fcee09', shadow: '0 0 20px rgba(255, 0, 110, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' },
            info: { bg: '#00f5ff', border: '#fcee09', shadow: '0 0 20px rgba(0, 245, 255, 0.6), 0 0 40px rgba(252, 238, 9, 0.3)' },
            error: { bg: '#ff006e', border: '#ef4444', shadow: '0 0 20px rgba(255, 0, 110, 0.6), 0 0 40px rgba(239, 68, 68, 0.3)' }
        },
        // Vintage Equipment Themes
        'eberline': {
            success: { bg: '#c9a227', border: '#e07b39', shadow: 'rgba(201, 162, 39, 0.4)' },
            warning: { bg: '#e07b39', border: '#ff6b35', shadow: 'rgba(224, 123, 57, 0.4)' },
            info: { bg: '#c9a227', border: '#e07b39', shadow: 'rgba(201, 162, 39, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'fluke': {
            success: { bg: '#ffc107', border: '#ff9800', shadow: 'rgba(255, 193, 7, 0.4)' },
            warning: { bg: '#ff9800', border: '#ff5722', shadow: 'rgba(255, 152, 0, 0.4)' },
            info: { bg: '#ffc107', border: '#ff9800', shadow: 'rgba(255, 193, 7, 0.4)' },
            error: { bg: '#ff5722', border: '#f44336', shadow: 'rgba(255, 87, 34, 0.4)' }
        },
        'oscilloscope': {
            success: { bg: '#33ff66', border: '#00cc44', shadow: 'rgba(51, 255, 102, 0.5)' },
            warning: { bg: '#66cc88', border: '#33ff66', shadow: 'rgba(102, 204, 136, 0.4)' },
            info: { bg: '#00cc44', border: '#33ff66', shadow: 'rgba(0, 204, 68, 0.5)' },
            error: { bg: '#ff6666', border: '#ff3333', shadow: 'rgba(255, 102, 102, 0.5)' }
        },
        'nixie': {
            success: { bg: '#ff9500', border: '#ff6a00', shadow: '0 0 15px rgba(255, 149, 0, 0.6)' },
            warning: { bg: '#ff6a00', border: '#ff4400', shadow: '0 0 15px rgba(255, 106, 0, 0.6)' },
            info: { bg: '#ff7700', border: '#ff9500', shadow: '0 0 15px rgba(255, 119, 0, 0.6)' },
            error: { bg: '#ff4400', border: '#cc0000', shadow: '0 0 15px rgba(255, 68, 0, 0.6)' }
        },
        'civildefense': {
            success: { bg: '#ffd000', border: '#ffaa00', shadow: 'rgba(255, 208, 0, 0.5)' },
            warning: { bg: '#ffaa00', border: '#ff6600', shadow: 'rgba(255, 170, 0, 0.5)' },
            info: { bg: '#ffd000', border: '#ffaa00', shadow: 'rgba(255, 208, 0, 0.5)' },
            error: { bg: '#ff4400', border: '#cc0000', shadow: 'rgba(255, 68, 0, 0.5)' }
        },
        'tektronix': {
            success: { bg: '#00a2e8', border: '#66ccff', shadow: 'rgba(0, 162, 232, 0.5)' },
            warning: { bg: '#66ccff', border: '#00a2e8', shadow: 'rgba(102, 204, 255, 0.4)' },
            info: { bg: '#00a2e8', border: '#66ccff', shadow: 'rgba(0, 162, 232, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'keithley': {
            success: { bg: '#4a90d9', border: '#7eb8f0', shadow: 'rgba(74, 144, 217, 0.4)' },
            warning: { bg: '#7eb8f0', border: '#4a90d9', shadow: 'rgba(126, 184, 240, 0.4)' },
            info: { bg: '#4a90d9', border: '#7eb8f0', shadow: 'rgba(74, 144, 217, 0.4)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'ludlum': {
            success: { bg: '#d4915c', border: '#c44536', shadow: 'rgba(212, 145, 92, 0.5)' },
            warning: { bg: '#c44536', border: '#ff5c47', shadow: 'rgba(196, 69, 54, 0.5)' },
            info: { bg: '#d4915c', border: '#c44536', shadow: 'rgba(212, 145, 92, 0.5)' },
            error: { bg: '#ff5c47', border: '#cc0000', shadow: 'rgba(255, 92, 71, 0.5)' }
        },
        'hp': {
            success: { bg: '#d4a574', border: '#e8c49a', shadow: 'rgba(212, 165, 116, 0.5)' },
            warning: { bg: '#e8c49a', border: '#d4a574', shadow: 'rgba(232, 196, 154, 0.4)' },
            info: { bg: '#d4a574', border: '#e8c49a', shadow: 'rgba(212, 165, 116, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'victoreen': {
            success: { bg: '#7cb68a', border: '#9ed4aa', shadow: 'rgba(124, 182, 138, 0.5)' },
            warning: { bg: '#9ed4aa', border: '#7cb68a', shadow: 'rgba(158, 212, 170, 0.4)' },
            info: { bg: '#7cb68a', border: '#9ed4aa', shadow: 'rgba(124, 182, 138, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
        },
        'canberra': {
            success: { bg: '#26a69a', border: '#4dd0c5', shadow: 'rgba(38, 166, 154, 0.5)' },
            warning: { bg: '#4dd0c5', border: '#26a69a', shadow: 'rgba(77, 208, 197, 0.4)' },
            info: { bg: '#26a69a', border: '#4dd0c5', shadow: 'rgba(38, 166, 154, 0.5)' },
            error: { bg: '#ef4444', border: '#dc2626', shadow: 'rgba(239, 68, 68, 0.4)' }
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

        // Auto-populate ROI acquisition time from metadata (if available)
        autoPopulateROITime(data);

        // Store raw XML for N42 files to enable editing
        if (file.name.toLowerCase().endsWith('.n42') || file.name.toLowerCase().endsWith('.xml')) {
            try {
                currentData._rawXml = await file.text();
                console.log(`[Main] Stored raw XML (${currentData._rawXml.length} chars)`);
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
        console.log(`[ROI] Auto-populated acquisition time: ${timeSeconds}s → ${timeMinutes} min`);
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

        // Update UI for AlphaHound device capabilities
        updateDeviceUI('alphahound');
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

        // Reset device feature UI
        resetDeviceUI();
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
                        ui.renderDashboard(currentData);
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

        // Use unified API wrapper
        const data = await api.getCurrentSpectrumUnified();
        currentData = data;

        // Show dashboard if hidden
        document.getElementById('drop-zone').style.display = 'none';
        document.getElementById('dashboard').style.display = 'block';

        ui.renderDashboard(data);
        if (isPageVisible) {
            chartManager.render(data.energies, data.counts, data.peaks, chartManager.getScaleType());
            // Show zoom scrubber
            chartManager.showScrubber(data.energies, data.counts);
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
        alert('This history item is invalid or from an older version (no data stored).');
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

// Decay Tool Logic moved to setupDecayTool() below


// Globals for Decay Chart
let decayChartInstance = null;


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

        if (!response.ok) {
            let errorMsg = "Prediction failed";
            try {
                const err = await response.json();
                if (err.detail) errorMsg = err.detail;
            } catch (ignore) { }
            throw new Error(errorMsg);
        }

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

    const ctx = document.getElementById('decayChart');
    if (!ctx) return console.error('Decay chart canvas not found');

    decayChartInstance = new Chart(ctx.getContext('2d'), {
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
