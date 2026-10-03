import { api } from './api.js';
import { resetDeviceUI, updateDeviceUI } from './device_features.js';
import { escapeHtml } from './html.js';
import { debug } from './log.js';
import { showToast } from './toast.js';

/**
 * Radiacode connection mode, BLE scan, connect, disconnect, spectrum, clear and dose reset.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.DoseRateChart
 * @param {*} deps.chartManager
 * @param {*} deps.ui
 * @param {*} deps.startRadiacodeDosePolling
 * @param {*} deps.stopRadiacodeDosePolling
 * @param {*} deps.getCurrentData
 * @param {*} deps.setCurrentData
 * @param {*} deps.getRcDoseChart
 * @param {*} deps.setRcDoseChart
 */
export function setupRadiacodeConnection({ DoseRateChart, chartManager, ui, startRadiacodeDosePolling, stopRadiacodeDosePolling, getCurrentData, setCurrentData, getRcDoseChart, setRcDoseChart } = {}) {
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
                debug('[Radiacode] BLE scan found:', devices);

                // Clear and populate dropdown
                deviceSelect.innerHTML = '<option value="">Select BLE Device...</option>';

                if (devices.length === 0) {
                    deviceSelect.innerHTML += '<option value="" disabled>No devices found</option>';
                    showToast('No Radiacode devices found. Make sure the device is powered on and in range.', 'warning');
                } else {
                    devices.forEach(device => {
                        const rssiInfo = device.rssi !== null ? ` (${device.rssi} dBm)` : '';
                        deviceSelect.innerHTML += `<option value="${escapeHtml(device.address)}">${escapeHtml(device.name)}${rssiInfo}</option>`;
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
                debug('[Radiacode] Connected:', result);

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
                    if (getRcDoseChart()) {
                        getRcDoseChart().destroy();
                        setRcDoseChart(null);
                    }

                    // Force layout reflow to ensure canvas has dimensions
                    rcChartCanvas.offsetHeight;

                    setRcDoseChart(new DoseRateChart(rcChartCanvas, {
                        label: 'Dose Rate',
                        colorVar: '--secondary-color', // Respect the current theme
                        maxPoints: 60
                    }));
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
                document.getElementById('rc-dose-total').textContent = 'Total --';
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
                debug('[Radiacode] Spectrum received:', data);

                setCurrentData(data);
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
        if (!getCurrentData()) return;
        let csv = 'Energy (keV),Counts\n';
        for (let i = 0; i < getCurrentData().energies.length; i++) {
            csv += `${getCurrentData().energies[i]},${getCurrentData().counts[i]}\n`;
        }
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'spectrum_data.csv';
        a.click();
        URL.revokeObjectURL(url);
    });
}
