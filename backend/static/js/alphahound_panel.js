import { api } from './api.js';
import { confirmDialog } from './dialogs.js';
import { showToast } from './toast.js';

/**
 * The AlphaHound details panel buttons.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.disconnectDevice
 * @param {*} deps.refreshAlphaHoundDetails
 * @param {*} deps.runAhProbe
 * @param {*} deps.startAhAutoRefresh
 * @param {*} deps.stopAhAutoRefresh
 */
export function setupAlphaHoundPanelListeners({ disconnectDevice, refreshAlphaHoundDetails, runAhProbe, startAhAutoRefresh, stopAhAutoRefresh } = {}) {
    document.getElementById('btn-disconnect-alphahound')?.addEventListener('click', disconnectDevice);
    document.getElementById('btn-dose-csv')?.addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = '/device/dose/log.csv';
        a.download = '';
        document.body.appendChild(a);
        a.click();
        a.remove();
    });
    document.getElementById('btn-dose-clear')?.addEventListener('click', async () => {
        if (!(await confirmDialog('Clear the recorded dose-rate history?', { title: 'Clear dose log', okLabel: 'Clear', danger: true }))) return;
        try {
            const r = await api.clearDoseLog();
            showToast(`Dose log cleared (${r.cleared} readings)`, 'success');
            refreshAlphaHoundDetails();
        } catch (err) {
            showToast(err.message || 'Failed to clear dose log', 'error');
        }
    });
    document.getElementById('btn-probe')?.addEventListener('click', runAhProbe);
    document.getElementById('ah-auto-refresh')?.addEventListener('change', (e) => {
        if (e.target.checked) startAhAutoRefresh(); else stopAhAutoRefresh();
    });
    document.getElementById('ah-auto-interval')?.addEventListener('change', () => {
        if (document.getElementById('ah-auto-refresh')?.checked) startAhAutoRefresh();
    });
}
