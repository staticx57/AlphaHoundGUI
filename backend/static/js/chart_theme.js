/**
 * What a theme means for a chart, beyond its colours.
 *
 * Every theme defines colours; some also have a character (a phosphor oscilloscope glows and draws a dotted
 * graticule, an instrument theme is crisp and monospaced, a Nixie theme is thick and warm). The "character" is set
 * in style.css as --ch-* custom properties per theme, and read here so that every chart (channel history, dose
 * sparklines, the spectrum) is drawn the way its theme would draw it: line weight, smoothing, glow, grid style, the
 * number font and the tick/grid colours, not only the hue.
 */

/** "2 4" -> [2, 4]; "0", "none" or "" -> [] (a solid line). */
export function parseDash(text) {
    if (typeof text !== 'string') return [];
    const parts = text.trim().split(/[\s,]+/).map(Number).filter((n) => Number.isFinite(n) && n > 0);
    return parts.length ? parts : [];
}

/** A number from a custom property such as "1.75" or "9px"; `fallback` if it is not one. */
export function parseToken(text, fallback) {
    const n = parseFloat(typeof text === 'string' ? text : '');
    return Number.isFinite(n) ? n : fallback;
}

/** The resolved look of the active theme for charts. */
export function chartTheme(root = document.documentElement) {
    const styles = getComputedStyle(root);
    const get = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
    return {
        font: get('--ch-font', get('--font-family', 'system-ui, sans-serif')),
        text: get('--text-primary', '#f8fafc'),
        textSecondary: get('--text-secondary', '#94a3b8'),
        grid: get('--border-color', 'rgba(148, 163, 184, 0.2)'),
        card: get('--card-bg', '#1e293b'),
        bg: get('--bg-color', '#0f172a'),
        primary: get('--primary-color', '#38bdf8'),
        lineWidth: parseToken(get('--ch-line-w', ''), 1.75),
        glow: parseToken(get('--ch-glow', ''), 0),
        tension: parseToken(get('--ch-tension', ''), 0.25),
        stepped: parseToken(get('--ch-step', ''), 0) === 1,
        gridDash: parseDash(get('--ch-grid-dash', '0')),
    };
}

/**
 * Chart.js plugin: a soft glow around each line in themes that have one (phosphor, neon, Nixie). Enabled per
 * chart with options.plugins.themeGlow.blur (0 = off). The shadow takes the line's own colour.
 */
export const themeGlowPlugin = {
    id: 'themeGlow',
    beforeDatasetDraw(chart, args) {
        const blur = chart.options?.plugins?.themeGlow?.blur || 0;
        if (!blur || args.meta?.type !== 'line') return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.shadowBlur = blur;
        ctx.shadowColor = chart.data.datasets[args.index]?.borderColor || '#fff';
    },
    afterDatasetDraw(chart, args) {
        const blur = chart.options?.plugins?.themeGlow?.blur || 0;
        if (!blur || args.meta?.type !== 'line') return;
        chart.ctx.restore();
    },
};

/** '#rrggbb' + alpha -> 'rgba(...)' (a translucent fill under a line); non-hex colours are returned unchanged. */
export function withAlpha(color, alpha) {
    const m = /^#([0-9a-f]{6})$/i.exec(color || '');
    if (!m) return color;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
