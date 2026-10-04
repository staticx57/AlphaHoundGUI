/**
 * Which export formats can hold a spectrum's energy axis (pure functions, no DOM).
 *
 * CHN stores the calibration as three polynomial coefficients, so it can only hold an axis a quadratic reproduces. The server refuses
 * anything more than CHN_MAX_ERROR_KEV off (the AlphaHound's cubic axis is hundreds of keV off a quadratic); this is the same test,
 * so the button can say so before it is clicked.
 */
export const CHN_MAX_ERROR_KEV = 1.0;

/** Largest distance (keV) between an energy axis and the least-squares quadratic through it; 0 for no or a too-short axis. */
export function quadraticMisfitKeV(energies) {
    const n = Array.isArray(energies) ? energies.length : 0;
    if (n < 4 || !energies.every(Number.isFinite)) return 0;
    // centred, scaled channel index: keeps the normal equations well conditioned
    const half = (n - 1) / 2;
    const t = (i) => (i - half) / half;
    const m = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    const b = [0, 0, 0];
    for (let i = 0; i < n; i++) {
        const row = [1, t(i), t(i) * t(i)];
        for (let r = 0; r < 3; r++) {
            b[r] += row[r] * energies[i];
            for (let c = 0; c < 3; c++) m[r][c] += row[r] * row[c];
        }
    }
    const coef = solve3(m, b);
    let worst = 0;
    for (let i = 0; i < n; i++) {
        worst = Math.max(worst, Math.abs(energies[i] - (coef[0] + coef[1] * t(i) + coef[2] * t(i) * t(i))));
    }
    return worst;
}

function solve3(a, b) {                       // Gaussian elimination with partial pivoting
    const m = a.map((row, i) => [...row, b[i]]);
    for (let col = 0; col < 3; col++) {
        let pivot = col;
        for (let r = col + 1; r < 3; r++) if (Math.abs(m[r][col]) > Math.abs(m[pivot][col])) pivot = r;
        [m[col], m[pivot]] = [m[pivot], m[col]];
        for (let r = col + 1; r < 3; r++) {
            const f = m[r][col] / m[col][col];
            for (let c = col; c < 4; c++) m[r][c] -= f * m[col][c];
        }
    }
    const x = [0, 0, 0];
    for (let r = 2; r >= 0; r--) {
        let s = m[r][3];
        for (let c = r + 1; c < 3; c++) s -= m[r][c] * x[c];
        x[r] = s / m[r][r];
    }
    return x;
}

/** {ok, error_kev, reason}: can CHN hold this axis? `reason` is the sentence for the button's tooltip when it cannot. */
export function chnAvailability(energies) {
    const error = quadraticMisfitKeV(energies);
    if (error <= CHN_MAX_ERROR_KEV) return { ok: true, error_kev: error, reason: '' };
    return {
        ok: false,
        error_kev: error,
        reason: `CHN stores only a quadratic energy axis, which is up to ${error < 10 ? error.toFixed(1) : Math.round(error)} keV off this spectrum's axis. Use PCF or N42.`,
    };
}
