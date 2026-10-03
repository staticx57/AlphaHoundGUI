/**
 * The metadata cards above a spectrum: what each key is called, how its value reads, and which keys belong together.
 *
 * The backend sends raw keys (mean_dose_rate_uSv_h, exposure_covered_s, ...) and the cards used to show them as
 * KEY.toUpperCase() with underscores turned into spaces ("MEAN DOSE RATE USV H"), values unrounded
 * ("1.482912", "271.456789") and one card per number (six for one dose figure). The card labels are set in capitals
 * by CSS, which also turns a unit symbol into nonsense (µSv/h -> ΜSV/H), so units never go in a label: they go in
 * the value ("1.48 µSv/h").
 *
 * Pure functions, no DOM: describeMetadata() returns cards that ui.js draws.
 */

import { formatDoseRate, formatDoseTotal, UREM_PER_USV } from './units.js';

const ACRONYMS = { cps: 'CPS', cpm: 'CPM', id: 'ID', n42: 'N42', utc: 'UTC', mac: 'MAC', bg: 'BG', mda: 'MDA', usb: 'USB', ble: 'BLE', fwhm: 'FWHM', roi: 'ROI' };

// trailing key tokens that are a unit, longest first; the label drops them and the value gets them
const UNIT_SUFFIXES = [
    [['usv', 'h'], 'µSv/h'], [['urem', 'h'], 'µRem/h'], [['msv', 'h'], 'mSv/h'], [['nsv', 'h'], 'nSv/h'],
    [['usv'], 'µSv'], [['urem'], 'µRem'], [['kev'], 'keV'], [['cps'], 'cps'], [['cpm'], 'cpm'],
    [['pct'], '%'], [['hz'], 'Hz'], [['min'], 'min'], [['s'], 's'], [['h'], 'h'], [['mm'], 'mm'], [['cm'], 'cm'], [['c'], '°C'],
];

const LABELS = {
    source: 'Source', manufacturer: 'Manufacturer', model: 'Model', instrument_model: 'Model', instrument_manufacturer: 'Manufacturer',
    serial_number: 'Serial number', channels: 'Channels', start_time: 'Start time', filename: 'File', calibration: 'Calibration',
    energy_calibration_slope: 'Calibration slope', energy_calibration_offset: 'Calibration offset',
    count_time_minutes: 'Collection time', duration_s: 'Duration', device_duration_s: 'Device duration',
    live_time: 'Live time', real_time: 'Real time', acquisition_time: 'Acquisition time', live_time_s: 'Live time', real_time_s: 'Real time',
};

const TIPS = {
    count_time_minutes: 'Time since the acquisition started (wall clock), in minutes.',
    acquisition_time: 'Time since the acquisition started (wall clock).',
    live_time: 'Time the detector was able to count (real time minus dead time).',
    real_time: 'Elapsed wall-clock time of the measurement.',
    live_time_s: 'Time the detector was able to count (real time minus dead time).',
    real_time_s: 'Elapsed wall-clock time of the measurement.',
    device_duration_s: 'Accumulation time reported by the instrument itself (independent of this app’s clock).',
    duration_s: 'Accumulation time reported by the instrument.',
};

const DOSE_KEYS = ['exposure_uSv', 'mean_dose_rate_uSv_h', 'max_dose_rate_uSv_h', 'exposure_covered_s', 'exposure_method', 'exposure_during_acquisition'];
const RATE_KEYS = ['mean_cps_gamma', 'mean_cps_beta', 'mean_cps_alpha', 'max_cps_total'];

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** "mean_dose_rate_uSv_h" -> { label: "Mean dose rate", unit: "µSv/h" } (the unit is null when the key has none). */
export function humanizeKey(key) {
    let tokens = String(key).split('_').filter(Boolean);
    let unit = null;
    const lower = tokens.map((t) => t.toLowerCase());
    for (const [suffix, symbol] of UNIT_SUFFIXES) {
        if (tokens.length > suffix.length && suffix.every((t, i) => lower[lower.length - suffix.length + i] === t)) {
            unit = symbol;
            tokens = tokens.slice(0, tokens.length - suffix.length);
            break;
        }
    }
    const words = tokens.map((t) => ACRONYMS[t.toLowerCase()] || t.toLowerCase());
    const text = words.join(' ');
    return { label: text.charAt(0).toUpperCase() + text.slice(1), unit };
}

/** 5 -> "5", 1234567 -> "1,234,567", 1.482912 -> "1.483", 271.456789 -> "271.5", 0.00012345 -> "0.0001235". */
export function formatNumber(v) {
    if (!isNum(v)) return String(v);
    if (Number.isInteger(v)) return v.toLocaleString('en-US');
    const abs = Math.abs(v);
    if (abs < 1) return Number(v.toPrecision(4)).toLocaleString('en-US', { maximumFractionDigits: 10 });   // 4 significant digits
    const digits = abs >= 100 ? 1 : abs >= 10 ? 2 : 3;
    return Number(v.toFixed(digits)).toLocaleString('en-US', { maximumFractionDigits: 8 });
}

/** Seconds as "45.0s", "5.0 min", "1h 5m" (the forms the cards always used). */
export function formatSeconds(v) {
    if (v >= 3600) return `${Math.floor(v / 3600)}h ${Math.floor((v % 3600) / 60)}m`;
    if (v >= 60) return `${(v / 60).toFixed(1)} min`;
    return `${v.toFixed(1)}s`;
}

function rateText(v, doseUnit) { return formatDoseRate(v, doseUnit).text; }

function valueFor(key, value, unit, doseUnit) {
    if (value === null || value === undefined || value === '') return { value: '–' };
    if (typeof value === 'boolean') return { value: value ? 'Yes' : 'No' };
    if (key === 'start_time' && typeof value === 'string' && !Number.isNaN(Date.parse(value))) {
        return { value: new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }), title: value };
    }
    if (typeof value === 'object') {
        if (key === 'calibration' && value.a0 !== undefined) return { value: `${isNum(value.a1) ? value.a1.toFixed(2) : '?'} keV/ch` };
        return { value: JSON.stringify(value) };
    }
    if (!isNum(value)) return { value: String(value) };
    if (key === 'channels') return { value: String(value) };
    if (key === 'count_time_minutes') return { value: `${value.toFixed(2)} min` };
    if (unit === 's' || /(^|_)time$/.test(key)) return { value: formatSeconds(value) };
    if (unit === 'µSv/h') return { value: rateText(value, doseUnit) };
    if (unit === 'µRem/h') return { value: rateText(value / UREM_PER_USV, doseUnit) };
    if (unit === 'µSv') return { value: formatDoseTotal(value, doseUnit) };
    if (unit === 'µRem') return { value: formatDoseTotal(value / UREM_PER_USV, doseUnit) };
    return { value: unit ? `${formatNumber(value)} ${unit}` : formatNumber(value) };
}

/**
 * Cards for a metadata object. Related keys are folded into one card (acquisition time; dose; count rates) and
 * placeholders that say nothing (serial number "UNKNOWN", a source that only repeats manufacturer + model) are left out.
 *
 * @param {object} metadata
 * @param {{doseUnit?: 'uSv'|'uRem'}} [options] unit for dose values (default uSv)
 * @returns {{key: string, label: string, value: string, detail?: string, rows?: {k: string, v: string}[], title?: string, tip?: boolean}[]}
 */
export function describeMetadata(metadata, { doseUnit = 'uSv' } = {}) {
    const md = { ...(metadata || {}) };
    const cards = [];
    const take = (k) => { const v = md[k]; delete md[k]; return v; };

    // --- time: live = real = acquisition time usually, so one explained card instead of four unexplained ones
    const timeNotes = take('time_notes');
    const secs = (k) => (isNum(md[k]) ? md[k] : null);
    const same = (a, b) => a !== null && b !== null && Math.abs(a - b) < 0.5;
    const acq = secs('acquisition_time'), live = secs('live_time'), real = secs('real_time');
    const cmin = isNum(md.count_time_minutes) ? md.count_time_minutes * 60 : null;
    if (acq !== null && same(acq, live) && same(acq, real) && (cmin === null || same(acq, cmin))) {
        ['acquisition_time', 'live_time', 'real_time', 'count_time_minutes'].forEach(take);
        cards.push({
            key: 'acquisition_time', label: 'Acquisition time', value: formatSeconds(acq).replace(/^(\d+\.\d) min$/, (m, mins) => `${mins} min (${acq.toFixed(0)} s)`),
            tip: true,
            title: timeNotes || 'Live time and real time are identical here: neither device reports dead time, so live time is taken to equal real time (= elapsed time since the acquisition started).',
        });
    } else if (live !== null && real !== null && same(live, real) && acq === null) {
        ['live_time', 'real_time'].forEach(take);
        cards.push({
            key: 'live_time', label: 'Live = real time', value: formatSeconds(live).replace(/^(\d+\.\d) min$/, (m, mins) => `${mins} min (${live.toFixed(0)} s)`), tip: true,
            title: 'Live and real time are identical in this file (no dead time recorded).',
        });
    }

    // --- dose: one card for the exposure figure and the rates it was integrated from
    const hasDose = DOSE_KEYS.some((k) => k in md);
    let doseCard = null;
    if (hasDose) {
        const exposure = take('exposure_uSv'), mean = take('mean_dose_rate_uSv_h'), max = take('max_dose_rate_uSv_h');
        const covered = take('exposure_covered_s'), method = take('exposure_method'), summary = take('exposure_during_acquisition');
        const rows = [['Mean rate', mean], ['Max rate', max]].filter(([, v]) => isNum(v)).map(([k, v]) => ({ k, v: rateText(v, doseUnit) }));
        const parts = [];
        if (isNum(covered)) parts.push(`from ${formatSeconds(covered)} of readings`);
        if (typeof method === 'string' && method) parts.push(method);
        doseCard = {
            key: 'exposure', label: 'Dose this acquisition',
            value: isNum(exposure) ? formatDoseTotal(exposure, doseUnit) : (typeof summary === 'string' && summary ? summary : '–'),
            rows, tip: true,
            title: `Dose integrated over the acquisition (${parts.length ? parts.join(', ') : 'integrated instrument dose rate'}). The mean and maximum are of the dose-rate readings.`,
        };
    }

    // --- count rates (AlphaHound): one card with the three channels
    let rateCard = null;
    if (RATE_KEYS.some((k) => k in md)) {
        const g = take('mean_cps_gamma'), b = take('mean_cps_beta'), a = take('mean_cps_alpha'), peak = take('max_cps_total');
        const rows = [['γ Gamma', g], ['β Beta', b], ['α Alpha', a]].filter(([, v]) => isNum(v)).map(([k, v]) => ({ k, v: formatNumber(v) }));
        rateCard = {
            key: 'count_rates', label: 'Mean count rate (CPS)', value: rows.length ? '' : '–', rows,
            detail: isNum(peak) ? `Peak total ${formatNumber(peak)} cps` : undefined, tip: true,
            title: 'Mean gamma, beta and alpha count rates during the acquisition, in counts per second (AlphaHound), and the highest gamma + beta + alpha rate seen.',
        };
    }

    // --- placeholders and repeats
    const manufacturer = md.manufacturer ?? md.instrument_manufacturer;
    const model = md.model ?? md.instrument_model;
    if (typeof md.source === 'string' && manufacturer && model
        && md.source.trim().toLowerCase() === `${manufacturer} ${model}`.trim().toLowerCase()) delete md.source;
    if (md.instrument_model !== undefined && md.model !== undefined) delete md.instrument_model;
    if (md.instrument_manufacturer !== undefined && md.manufacturer !== undefined) delete md.instrument_manufacturer;
    if (typeof md.serial_number === 'string' && /^(unknown|n\/a|none|)$/i.test(md.serial_number.trim())) delete md.serial_number;

    for (const [key, raw] of Object.entries(md)) {
        const { label, unit } = LABELS[key] ? { label: LABELS[key], unit: humanizeKey(key).unit } : humanizeKey(key);
        const { value, title } = valueFor(key, raw, unit, doseUnit);
        cards.push({ key, label, value, ...(TIPS[key] ? { tip: true, title: TIPS[key] } : title ? { title } : {}) });
    }
    if (doseCard) cards.push(doseCard);
    if (rateCard) cards.push(rateCard);
    return cards;
}
