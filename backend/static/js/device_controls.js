import { api } from './api.js';
import { confirmDialog, infoDialog, notifyAuto } from './dialogs.js';
import { debug } from './log.js';
import { showToast } from './toast.js';

/**
 * The unified device buttons and the Radiacode device settings.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.connectDevice
 * @param {*} deps.refreshPorts
 * @param {*} deps.showRadiacodeDisconnectedUI
 * @param {*} deps.startAcquisition
 * @param {*} deps.stopAcquisition
 * @param {*} deps.stopRadiacodeDosePolling
 */
export function setupDeviceControls({ connectDevice, refreshPorts, showRadiacodeDisconnectedUI, startAcquisition, stopAcquisition, stopRadiacodeDosePolling } = {}) {
    // Device Controls
    document.getElementById('btn-refresh-ports').addEventListener('click', refreshPorts);
    document.getElementById('btn-connect-device').addEventListener('click', connectDevice);

    // Unified Device Control Buttons
    // These work with both AlphaHound and Radiacode automatically

    // Clear Spectrum button
    document.getElementById('btn-clear-spectrum')?.addEventListener('click', async () => {
        if (!(await confirmDialog('Clear all accumulated counts on the device?', { title: 'Clear spectrum', okLabel: 'Clear', danger: true }))) return;
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
            stopAcquisition();
            showRadiacodeDisconnectedUI();
            showToast('Disconnected', 'info');
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
                debug(`[Radiacode] Brightness set to ${e.target.value}`);
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
                debug(`[Radiacode] Sound ${e.target.checked ? 'enabled' : 'disabled'}`);
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
                debug(`[Radiacode] Vibration ${e.target.checked ? 'enabled' : 'disabled'}`);
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
                debug(`[Radiacode] Display timeout set to ${seconds}s`);
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
                debug(`[Radiacode] Language set to ${e.target.value}`);
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
                    infoDialog('Radiacode configuration', info.configuration);
                } else {
                    notifyAuto('Configuration data not available');
                }
            } catch (err) {
                console.error('[Radiacode] Failed to get configuration:', err);
                showToast(`Failed to get configuration: ${err.message}`, 'error');
            }
        });
    }

    document.getElementById('btn-start-acquire').addEventListener('click', startAcquisition);
    document.getElementById('btn-stop-acquire').addEventListener('click', stopAcquisition);
}
