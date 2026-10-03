/**
 * Theme-derived colours for the alpha / beta / gamma channels and the device-screen replica.
 *
 * Nothing here is a fixed colour. The channel colours come from the active theme's own palette
 * (--primary-color, --secondary-color, --accent-color) and are nudged apart when the theme's colours are too
 * similar (an oscilloscope theme is all greens, a Nixie theme all oranges): first by lightness, then by hue, until
 * the three are distinguishable and readable on the theme's background. Charts also give each channel its own line
 * pattern, so they never rely on colour alone.
 *
 * Pure functions (no DOM) except readThemeColors(), so they can be tested for every theme.
 */

export function parseColor(input) {
    if (typeof input !== 'string') return null;
    const s = input.trim().toLowerCase();
    let m = s.match(/^#([0-9a-f]{3})$/);
    if (m) {
        const [r, g, b] = m[1].split('').map((c) => parseInt(c + c, 16));
        return { r, g, b };
    }
    m = s.match(/^#([0-9a-f]{6})(?:[0-9a-f]{2})?$/);
    if (m) {
        return { r: parseInt(m[1].slice(0, 2), 16), g: parseInt(m[1].slice(2, 4), 16), b: parseInt(m[1].slice(4, 6), 16) };
    }
    m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/);
    if (m) return { r: Math.round(+m[1]), g: Math.round(+m[2]), b: Math.round(+m[3]) };
    return null;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function toHex({ r, g, b }) {
    return '#' + [r, g, b].map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('');
}

export function rgbToHsl({ r, g, b }) {
    const rn = r / 255, gn = g / 255, bn = b / 255;
    const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
    const l = (max + min) / 2;
    const d = max - min;
    if (d === 0) return { h: 0, s: 0, l };
    const s = d / (1 - Math.abs(2 * l - 1));
    let h;
    if (max === rn) h = ((gn - bn) / d) % 6;
    else if (max === gn) h = (bn - rn) / d + 2;
    else h = (rn - gn) / d + 4;
    return { h: (h * 60 + 360) % 360, s, l };
}

export function hslToRgb({ h, s, l }) {
    const hh = ((h % 360) + 360) % 360;
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
    const m = l - c / 2;
    const [r, g, b] = hh < 60 ? [c, x, 0] : hh < 120 ? [x, c, 0] : hh < 180 ? [0, c, x]
        : hh < 240 ? [0, x, c] : hh < 300 ? [x, 0, c] : [c, 0, x];
    return { r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 };
}

export function relativeLuminance({ r, g, b }) {
    const lin = (v) => {
        const c = v / 255;
        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two colours (1 to 21). */
export function contrastRatio(a, b) {
    const la = relativeLuminance(a), lb = relativeLuminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * How different two colours look, on a scale where 1 is "clearly different". Hue only counts when both colours
 * are saturated (the hue of a grey is meaningless).
 */
export function colorDistance(a, b) {
    const ha = rgbToHsl(a), hb = rgbToHsl(b);
    const dh = Math.min(Math.abs(ha.h - hb.h), 360 - Math.abs(ha.h - hb.h)) * Math.min(ha.s, hb.s);
    return Math.hypot(dh / 50, (ha.s - hb.s) * 2.2, (ha.l - hb.l) * 3.2);
}

/** Move a colour's lightness away from the background until it reads at least `min`:1 against it. */
export function ensureContrast(rgb, bg, min = 3) {
    if (contrastRatio(rgb, bg) >= min) return rgb;
    const hsl = rgbToHsl(rgb);
    const bgLight = relativeLuminance(bg) > 0.4;      // light theme: darken; dark theme: lighten
    let out = rgb;
    for (let i = 0; i < 40 && contrastRatio(out, bg) < min; i++) {
        hsl.l = clamp(hsl.l + (bgLight ? -0.03 : 0.03), 0.05, 0.95);
        out = hslToRgb(hsl);
    }
    return out;
}

const TARGET_DISTANCE = 1.0;

function minDistance(candidate, others) {
    return others.length ? Math.min(...others.map((o) => colorDistance(candidate, o))) : Infinity;
}

/**
 * The candidate itself if it is distinct enough from `others`; otherwise the smallest change (least hue shift and
 * lightness shift, so it still belongs to the theme) that is. A single-hue theme ends up with tints and shades of its
 * colour plus a modest hue drift; a multi-hue theme usually needs no change at all.
 */
function separate(candidate, others, bg) {
    const base = ensureContrast(candidate, bg);
    if (minDistance(base, others) >= TARGET_DISTANCE) return base;
    const hsl = rgbToHsl(candidate);
    let best = base, bestScore = minDistance(base, others), bestCost = Infinity;
    for (let dh = -75; dh <= 75; dh += 15) {
        for (let dl = -0.36; dl <= 0.361; dl += 0.06) {
            for (const ds of [0, -0.25, -0.45]) {
                const variant = ensureContrast(hslToRgb({
                    h: hsl.h + dh, s: clamp(hsl.s + ds, 0.12, 1), l: clamp(hsl.l + dl, 0.3, 0.88),
                }), bg);
                const score = minDistance(variant, others);
                // hue drift costs the most (it leaves the theme's colour family), lightness and saturation less
                const cost = (Math.abs(dh) / 20) ** 2 + (Math.abs(dl) / 0.24) ** 2 + (Math.abs(ds) / 0.35) ** 2;
                if (score >= TARGET_DISTANCE) {
                    if (cost < bestCost) { best = variant; bestCost = cost; bestScore = score; }
                } else if (bestCost === Infinity && score > bestScore) {
                    best = variant; bestScore = score;
                }
            }
        }
    }
    return best;
}

/**
 * Colours for gamma, beta and alpha from a theme's palette. gamma = primary, beta = secondary, alpha = accent,
 * each separated from the ones before it (see the file comment) and readable on `bg`.
 * Inputs are CSS colour strings; returns '#rrggbb' strings.
 */
export function channelPalette({ primary, secondary, accent, bg }) {
    const fallbackBg = { r: 15, g: 23, b: 42 };
    const bgRgb = parseColor(bg) || fallbackBg;
    const p = parseColor(primary) || { r: 56, g: 189, b: 248 };
    const s = parseColor(secondary) || p;
    const a = parseColor(accent) || p;
    const gamma = ensureContrast(p, bgRgb);
    const beta = separate(s, [gamma], bgRgb);
    const alpha = separate(a, [gamma, beta], bgRgb);
    return { gamma: toHex(gamma), beta: toHex(beta), alpha: toHex(alpha) };
}

/**
 * `n` series colours for a theme: the first three are the channel colours (gamma, beta, alpha), further ones step round the
 * hue wheel from the theme's primary colour (golden angle, alternating lightness), each readable on the background and
 * nudged until it differs from those already chosen. Charts with many lines also vary the line pattern; colour is never the
 * only cue.
 */
export function seriesPalette(theme, n) {
    const base = channelPalette(theme);
    const bg = parseColor(theme.bg) || { r: 15, g: 23, b: 42 };
    const out = [base.gamma, base.beta, base.alpha].slice(0, Math.max(0, n));
    const hsl0 = rgbToHsl(parseColor(base.gamma));
    const sat = clamp(Math.max(0.5, hsl0.s), 0.5, 0.9);
    let hue = hsl0.h;
    while (out.length < n) {
        hue += 137.508;
        const used = out.map(parseColor);
        let chosen = null;
        for (let tweak = 0; tweak < 12; tweak++) {
            const l = [0.62, 0.5, 0.72, 0.42][(out.length + tweak) % 4];
            const candidate = ensureContrast(hslToRgb({ h: hue + tweak * 11, s: sat, l }), bg);
            if (minDistance(candidate, used) >= 0.55) { chosen = candidate; break; }
            if (!chosen || minDistance(candidate, used) > minDistance(chosen, used)) chosen = candidate;
        }
        out.push(toHex(chosen));
    }
    return out;
}

/** The look of the device-screen replica in a theme: a bright tint of the theme colour on black, like a phosphor. */
export function screenPalette({ primary }) {
    const hsl = rgbToHsl(parseColor(primary) || { r: 56, g: 189, b: 248 });
    const fg = hslToRgb({ h: hsl.h, s: hsl.s * 0.6, l: 0.88 });
    const dim = hslToRgb({ h: hsl.h, s: hsl.s * 0.75, l: 0.5 });
    const rgba = (c, a) => `rgba(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)}, ${a})`;
    return { fg: toHex(fg), dim: toHex(dim), ghost: rgba(fg, 0.4), soft: rgba(fg, 0.3), mid: rgba(fg, 0.62) };
}

/** The look of the real device (white with a blue tint), for a faithful replica. */
export const DEVICE_SCREEN_PALETTE = {
    fg: '#d6f2ff', dim: '#4f7f99', ghost: 'rgba(214, 242, 255, 0.40)', soft: 'rgba(214, 242, 255, 0.30)', mid: 'rgba(214, 242, 255, 0.62)',
};

/** Resolved theme colours from the CSS custom properties on `root` (custom properties are resolved when computed). */
export function readThemeColors(root = document.documentElement) {
    const styles = getComputedStyle(root);
    const get = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
    return {
        primary: get('--primary-color', '#38bdf8'),
        secondary: get('--secondary-color', '#818cf8'),
        accent: get('--accent-color', '#38bdf8'),
        bg: get('--bg-color', '#0f172a'),
        card: get('--card-bg', '#1e293b'),
        text: get('--text-primary', get('--text-color', '#f8fafc')),
        textSecondary: get('--text-secondary', '#94a3b8'),
        border: get('--border-color', 'rgba(148, 163, 184, 0.2)'),
    };
}
