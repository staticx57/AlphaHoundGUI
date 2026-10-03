/**
 * Dose units. The two supported devices speak different ones (the AlphaHound µRem/h, the Radiacode µSv/h), and people
 * think in either, so every readout can follow one preference: "auto" (each device's own unit, the default) or a
 * fixed µSv/h or µRem/h. Everything is converted from µSv (1 µSv = 100 µRem).
 *
 * Pure functions plus a small stored preference; no DOM.
 */

export const UREM_PER_USV = 100;

/** localStorage, or null when the browser blocks it (private window, blocked site data). */
export function safeStorage() {
    try { return globalThis.localStorage || null; } catch (e) { return null; }
}
export const DOSE_PREFS = ['auto', 'uSv', 'uRem'];
const PREF_KEY = 'doseUnit';

/** Which unit to show: the preference if it names one, otherwise the device's own. */
export function resolveUnit(pref, native) {
    return pref === 'uSv' || pref === 'uRem' ? pref : (native === 'uRem' ? 'uRem' : 'uSv');
}

export function unitLabel(unit) {
    return unit === 'uRem' ? 'µRem/h' : 'µSv/h';
}

const decimals = (v) => (v < 10 ? 2 : v < 100 ? 1 : 0);

/** A dose rate given in µSv/h as { value, unit, text }, scaled (n / µ / m prefix) so it reads naturally. */
export function formatDoseRate(uSvPerHour, unit) {
    const rem = unit === 'uRem';
    if (uSvPerHour === null || uSvPerHour === undefined || !Number.isFinite(uSvPerHour)) {
        return { value: '--', unit: unitLabel(unit), text: `-- ${unitLabel(unit)}` };
    }
    const v = Math.max(0, uSvPerHour) * (rem ? UREM_PER_USV : 1);
    let value, label;
    if (v >= 999.5) {                               // 999.6 would round to "1000": it belongs in the next prefix
        value = (v / 1000).toFixed(2); label = rem ? 'mRem/h' : 'mSv/h';
    } else if (!rem && v < 0.0995) {                // below 0.1 uSv/h (natural background is about 0.1) nSv/h reads better
        const n = v * 1000;
        value = n.toFixed(decimals(n)); label = 'nSv/h';
    } else {
        value = v.toFixed(decimals(v)); label = unitLabel(unit);
    }
    return { value, unit: label, text: `${value} ${label}` };
}

/** An accumulated dose given in µSv as text: nSv / µSv / mSv, or µRem / mRem / Rem. */
export function formatDoseTotal(uSv, unit) {
    if (uSv === null || uSv === undefined || !Number.isFinite(uSv)) return '--';
    if (unit === 'uRem') {
        const v = Math.max(0, uSv) * UREM_PER_USV;
        if (v >= 1e6) return `${(v / 1e6).toFixed(3)} Rem`;
        if (v >= 1000) return `${(v / 1000).toFixed(3)} mRem`;
        return `${v.toFixed(decimals(v))} µRem`;
    }
    const v = Math.max(0, uSv);
    if (v >= 1000) return `${(v / 1000).toFixed(3)} mSv`;
    if (v >= 1) return `${v.toFixed(2)} µSv`;
    return `${(v * 1000).toFixed(1)} nSv`;
}

/** Value typed in the given unit (per hour) -> µSv/h. */
export function toUSv(value, unit) {
    return unit === 'uRem' ? value / UREM_PER_USV : value;
}

/** µSv/h -> the given unit. */
export function fromUSv(uSv, unit) {
    return unit === 'uRem' ? uSv * UREM_PER_USV : uSv;
}

export function getDosePref(storage = safeStorage()) {
    try {
        const v = storage?.getItem(PREF_KEY);
        return DOSE_PREFS.includes(v) ? v : 'auto';
    } catch (e) {
        return 'auto';
    }
}

export function setDosePref(pref, storage = safeStorage()) {
    const value = DOSE_PREFS.includes(pref) ? pref : 'auto';
    try { storage?.setItem(PREF_KEY, value); } catch (e) { /* ignore */ }
    return value;
}
