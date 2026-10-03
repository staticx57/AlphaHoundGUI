import { DEFAULT_ALERTS, loadAlerts, saveAlerts } from './alerts.js';
import { notify } from './dialogs.js';
import { showToast } from './toast.js';
import { fromUSv, getDosePref, resolveUnit, safeStorage, setDosePref, toUSv, unitLabel } from './units.js';

/**
 * The dose-unit preference and the configurable alerts in the settings modal.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.ui
 * @param {*} deps.alertCenter
 */
export function setupDoseAndAlertSettings({ ui, alertCenter } = {}) {
    const $ = (id) => document.getElementById(id);
    const unitSel = $('pref-dose-unit');
    if (!unitSel) return;
    const showLimit = () => {
        const unit = resolveUnit(getDosePref(), 'uRem');
        const st = loadAlerts(safeStorage());
        $('pref-alert-dose-value').value = Number(fromUSv(st.doseUSvH, unit).toPrecision(4));
        $('pref-alert-dose-unit').textContent = unitLabel(unit);
    };
    const notifyHint = () => {
        const hint = $('pref-notify-state');
        if (!hint) return;
        const N = window.Notification;
        hint.textContent = !N ? 'Not supported by this browser.'
            : N.permission === 'denied' ? 'Blocked in the browser settings.' : '';
    };
    const load = () => {
        const st = loadAlerts(safeStorage());
        unitSel.value = getDosePref();
        $('pref-alert-dose').checked = st.doseEnabled;
        $('pref-alert-cps').checked = st.cpsEnabled;
        $('pref-alert-cps-value').value = st.cps;
        $('pref-alert-sound').checked = st.sound;
        $('pref-alert-notify').checked = st.notify;
        showLimit();
        notifyHint();
    };
    const store = () => {
        const unit = resolveUnit(getDosePref(), 'uRem');
        const st = loadAlerts(safeStorage());
        const limit = parseFloat($('pref-alert-dose-value').value);
        const cps = parseFloat($('pref-alert-cps-value').value);
        saveAlerts({
            doseEnabled: $('pref-alert-dose').checked,
            doseUSvH: limit > 0 ? toUSv(limit, unit) : st.doseUSvH,
            cpsEnabled: $('pref-alert-cps').checked,
            cps: cps > 0 ? cps : st.cps,
            sound: $('pref-alert-sound').checked,
            notify: $('pref-alert-notify').checked,
        }, safeStorage());
        alertCenter.reload();
    };
    unitSel.addEventListener('change', () => {
        const before = resolveUnit(getDosePref(), 'uRem');
        const limitUSv = toUSv(parseFloat($('pref-alert-dose-value').value) || 0, before);   // keep the limit when the unit changes
        if (limitUSv > 0) saveAlerts({ ...loadAlerts(safeStorage()), doseUSvH: limitUSv }, safeStorage());
        setDosePref(unitSel.value);
        showLimit();
        alertCenter.reload();
        ui.refreshMetadata();
        showToast('Dose unit updated; readouts change with their next reading.', 'info');
    });
    ['pref-alert-dose', 'pref-alert-dose-value', 'pref-alert-cps', 'pref-alert-cps-value', 'pref-alert-sound'].forEach((id) => {
        $(id).addEventListener('change', store);
    });
    $('pref-alert-notify').addEventListener('change', async (e) => {
        if (e.target.checked && window.Notification && Notification.permission === 'default') {
            try { await Notification.requestPermission(); } catch (err) { /* ignore */ }
        }
        if (e.target.checked && (!window.Notification || Notification.permission !== 'granted')) e.target.checked = false;
        notifyHint();
        store();
    });
    $('btn-alert-test')?.addEventListener('click', () => {
        alertCenter.test();
        showToast('Test alert: you should hear a beep if sound is on.', 'info');
    });
    $('btn-alert-reset')?.addEventListener('click', () => {
        saveAlerts({ ...DEFAULT_ALERTS }, safeStorage());
        setDosePref('auto');
        load();
        alertCenter.reload();
        ui.refreshMetadata();
    });
    $('btn-settings')?.addEventListener('click', load);
    load();
}
