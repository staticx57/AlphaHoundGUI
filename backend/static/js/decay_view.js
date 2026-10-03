/**
 * Decay prediction modal: unit handling and the sentences around the chart (pure functions, no DOM).
 */

const DAYS_PER = { seconds: 1 / 86400, minutes: 1 / 1440, hours: 1 / 24, days: 1, years: 365.25 };
export const DURATION_UNITS = Object.keys(DAYS_PER);

/** A duration typed as `value` `unit` -> days (the API takes days). NaN for an unknown unit. */
export function durationToDays(value, unit) {
    const factor = DAYS_PER[unit];
    return factor === undefined ? NaN : Number(value) * factor;
}

/** 4 significant digits with the prefix that fits: 0.0123 -> "12.3 mBq", 1234 -> "1.234 kBq", 5e6 -> "5 MBq". */
export function formatBq(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
    if (value === 0) return '0 Bq';
    const abs = Math.abs(value);
    const steps = [[1e12, 'TBq'], [1e9, 'GBq'], [1e6, 'MBq'], [1e3, 'kBq'], [1, 'Bq'], [1e-3, 'mBq'], [1e-6, 'µBq'], [1e-9, 'nBq']];
    const [scale, unit] = steps.find(([s]) => abs >= s) || steps[steps.length - 1];
    return `${Number((value / scale).toPrecision(4))} ${unit}`;
}

/** What produced the curves and what was left out, as one line under the chart. */
export function describeDecayResult(result) {
    if (!result) return { info: '', warnings: [] };
    const names = result.isotopes || Object.keys(result.series || {});
    const omitted = result.omitted || [];
    const engine = result.engine_used
        ? `${result.engine_used}${result.engine_version ? ' ' + result.engine_version : ''}` : 'unknown engine';
    const parts = [`Computed with ${engine}`];
    if (result.data_source) parts.push(`data: ${result.data_source}`);
    parts.push(`${names.length} nuclide${names.length === 1 ? '' : 's'} shown`);
    if (omitted.length) {
        const list = omitted.slice(0, 6).join(', ') + (omitted.length > 6 ? `, +${omitted.length - 6} more` : '');
        parts.push(`${omitted.length} below 0.1 % of the start left out (${list})`);
    }
    return { info: parts.join(' · '), warnings: Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [] };
}

/** Values for a log axis: zero (a nuclide not yet populated) has no place on it, so it becomes a gap rather than a plunge. */
export function forLogAxis(values) {
    return (values || []).map((v) => (typeof v === 'number' && v > 0 ? v : null));
}

/** Lower and upper limit for the activity axis: six decades under the start, a little above the highest value. */
export function activityAxisRange(result) {
    const start = Number(result?.initial_activity) > 0 ? Number(result.initial_activity) : 1;
    let top = start;
    for (const series of Object.values(result?.series || {})) {
        for (const v of series) if (v > top) top = v;
    }
    return { min: start * 1e-6, max: top * 1.5 };
}
