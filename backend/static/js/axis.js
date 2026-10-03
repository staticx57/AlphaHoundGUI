/**
 * Axis helpers (pure functions, no DOM): round tick positions for the energy axis.
 *
 * Chart.js starts the ticks at an explicitly set axis minimum, so a spectrum whose calibration begins at
 * 5.56 keV got ticks at 169.2, 369.2, 569.2 ... These give 100, 200, 300 ... instead.
 */

/**
 * The "nice" step (1, 2 or 5 times a power of ten) whose tick count over `range` is closest to `target`.
 * (Rounding the raw step up gave only four ticks on a 1700 keV axis.)
 */
export function niceStep(range, target = 8) {
    if (!(range > 0) || !(target > 0)) return 1;
    const base = Math.floor(Math.log10(range / target));
    let best = null;
    for (let exp = base - 1; exp <= base + 1; exp++) {
        for (const m of [1, 2, 5]) {
            const step = m * Math.pow(10, exp);
            const miss = Math.abs(range / step - target);
            if (best === null || miss < best.miss - 1e-9) best = { step, miss };
        }
    }
    return Number(best.step.toPrecision(12));
}

/** Round tick values inside [min, max], never negative (an energy axis has no negative labels). */
export function roundTicks(min, max, target = 8) {
    if (!Number.isFinite(min) || !Number.isFinite(max) || !(max > min)) return [];
    const step = niceStep(max - min, target);
    const first = Math.ceil(min / step - 1e-9);
    const out = [];
    for (let i = first; i * step <= max + step * 1e-9; i++) {
        const v = Number((i * step).toPrecision(12));   // no 0.30000000000000004
        if (v >= 0) out.push(v);
    }
    return out;
}

/** Energy readout for a label: whole keV, never below zero. */
export function formatKeV(value) {
    return `${Math.max(0, Math.round(Number(value) || 0))} keV`;
}
