/**
 * Radiation channels panel: live gamma / beta / alpha count rates.
 *
 * Our own presentation of what the device reports (the rates of its three detectors), built from the app's
 * themed parts rather than a copy of anyone else's screen:
 *  - one card per channel: live rate, a log-scale meter with a peak-hold marker, the 1-minute average and the peak;
 *  - a share-of-counts bar (how much of the total each channel contributes);
 *  - a history chart (selectable window, linear or log) drawn in the active theme's character (see chart_theme.js).
 * Colours come from the theme palette (palette.js) and are published as --ch-gamma / --ch-beta / --ch-alpha on the
 * panel, so every piece of CSS that uses them follows theme switches. Each channel also has its own line pattern
 * (solid, dashed, dotted), so the chart never relies on colour alone.
 */

import { channelPalette, readThemeColors } from './palette.js';
import { chartTheme, themeGlowPlugin, withAlpha } from './chart_theme.js';

export const CHANNELS = [
    { key: 'gamma', symbol: 'γ', name: 'Gamma', dash: [] },
    { key: 'beta', symbol: 'β', name: 'Beta', dash: [7, 4] },
    { key: 'alpha', symbol: 'α', name: 'Alpha', dash: [2, 3] },
];
export const WINDOWS = [60, 300, 1800];            // seconds
export const METER_DECADES = 4;                    // the meter spans 1 ... 10,000 counts per second
const MAX_HISTORY_S = 1800 + 60;

/** Position (0..1) of a rate on the log meter: 1 cps is the left end, 10,000 cps the right end. */
export function logFraction(perSecond) {
    if (!(perSecond > 1)) return 0;
    return Math.min(1, Math.log10(perSecond) / METER_DECADES);
}

/** A rate for display: CPM as whole counts per minute, CPS with two decimals below 1000 and whole numbers above. */
export function formatChannelRate(perSecond, unit) {
    if (perSecond === null || perSecond === undefined || !Number.isFinite(perSecond)) return '--';
    if (unit === 'CPM') return Math.round(perSecond * 60).toLocaleString('en-US');
    return perSecond >= 1000 ? Math.round(perSecond).toLocaleString('en-US') : perSecond.toFixed(2);
}

/** Each channel's share of the total (0..1, summing to 1); all zero when nothing was counted. */
export function composition(cps) {
    const g = Math.max(0, +cps?.gamma || 0), b = Math.max(0, +cps?.beta || 0), a = Math.max(0, +cps?.alpha || 0);
    const total = g + b + a;
    if (!(total > 0)) return { gamma: 0, beta: 0, alpha: 0 };
    return { gamma: g / total, beta: b / total, alpha: a / total };
}

function within(history, now, windowS) {
    const out = [];
    for (let i = history.length - 1; i >= 0; i--) {
        if (now - history[i].t > windowS * 1000) break;
        out.push(history[i]);
    }
    return out.reverse();
}

/** Mean of one channel over the last windowS seconds (null when there are no samples). */
export function meanOf(history, now, windowS, key) {
    const pts = within(history, now, windowS);
    return pts.length ? pts.reduce((s, p) => s + p[key], 0) / pts.length : null;
}

/** Highest value of one channel over the last windowS seconds (null when there are no samples). */
export function peakOf(history, now, windowS, key) {
    const pts = within(history, now, windowS);
    return pts.length ? Math.max(...pts.map((p) => p[key])) : null;
}

/**
 * Chart points for a window: x is seconds relative to now (negative), values are bucket means so a 30-minute
 * window stays at most `maxPoints` long. The newest sample is always the last point.
 */
export function windowSeries(history, now, windowS, maxPoints = 240) {
    const pts = within(history, now, windowS);
    const out = { x: [], gamma: [], beta: [], alpha: [] };
    if (!pts.length) return out;
    const size = Math.max(1, Math.ceil(pts.length / maxPoints));
    for (let i = 0; i < pts.length; i += size) {
        const bucket = pts.slice(i, i + size);
        const mean = (key) => bucket.reduce((s, p) => s + p[key], 0) / bucket.length;
        out.x.push(((bucket[bucket.length - 1].t - now) / 1000));
        for (const ch of CHANNELS) out[ch.key].push(mean(ch.key));
    }
    return out;
}

function readStored(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
}
function store(key, value) {
    try { localStorage.setItem(key, String(value)); } catch (e) { /* ignore */ }
}

export class ChannelPanel {
    /**
     * @param {Document|HTMLElement} root  where the panel's elements live
     * @param {{onUnitChange?: Function}} [options]
     */
    constructor(root = document, options = {}) {
        this.root = root;
        this.onUnitChange = options.onUnitChange || null;
        this.panel = root.querySelector('.ch-panel');
        this.unit = readStored('ahRateUnit', 'CPS') === 'CPM' ? 'CPM' : 'CPS';
        const win = Number(readStored('ahChWindow', '300'));
        this.windowS = WINDOWS.includes(win) ? win : 300;
        this.scale = readStored('ahChScale', 'linear') === 'log' ? 'log' : 'linear';
        this.history = [];
        this.last = null;
        this.chart = null;
        this.chartTimer = null;
        this._bindControls();
        this.refreshTheme();
        this._syncControls();
        this._renderEmpty();
    }

    _bindControls() {
        const on = (selector, handler) => this.root.querySelectorAll(selector).forEach((el) => el.addEventListener('click', handler));
        on('[data-ch-unit-btn]', (e) => { this.setUnit(e.currentTarget.dataset.chUnitBtn); if (this.onUnitChange) this.onUnitChange(this.unit); });
        on('[data-ch-window]', (e) => this.setWindow(Number(e.currentTarget.dataset.chWindow)));
        on('[data-ch-scale]', (e) => this.setScale(e.currentTarget.dataset.chScale));
    }

    _syncControls() {
        const press = (selector, attr, value) => this.root.querySelectorAll(selector).forEach((el) => {
            el.setAttribute('aria-pressed', String(el.dataset[attr] === String(value)));
        });
        press('[data-ch-unit-btn]', 'chUnitBtn', this.unit);
        press('[data-ch-window]', 'chWindow', this.windowS);
        press('[data-ch-scale]', 'chScale', this.scale);
        this.root.querySelectorAll('[data-ch-unit]').forEach((el) => { el.textContent = this.unit.toLowerCase(); });
    }

    setUnit(unit) {
        this.unit = unit === 'CPM' ? 'CPM' : 'CPS';
        store('ahRateUnit', this.unit);
        this._syncControls();
        this._render();
        this._updateChart();
    }

    setWindow(seconds) {
        if (!WINDOWS.includes(seconds)) return;
        this.windowS = seconds;
        store('ahChWindow', seconds);
        this._syncControls();
        this._render();
        this._updateChart();
    }

    setScale(scale) {
        this.scale = scale === 'log' ? 'log' : 'linear';
        store('ahChScale', this.scale);
        this._syncControls();
        this._updateChart();
    }

    /** Recompute the theme-derived colours and character; call again after a theme switch. */
    refreshTheme() {
        this.theme = chartTheme();
        this.colors = channelPalette(readThemeColors());
        if (this.panel) {
            for (const ch of CHANNELS) this.panel.style.setProperty(`--ch-${ch.key}`, this.colors[ch.key]);
        }
        if (this.chart) {
            this._applyThemeToChart();
            this.chart.update('none');
        }
    }

    /** Add one reading ({gamma, beta, alpha} counts per second) and redraw. */
    update(cps, now = Date.now()) {
        if (!cps) { this.showNoData(); return; }
        const sample = { t: now, gamma: +cps.gamma || 0, beta: +cps.beta || 0, alpha: +cps.alpha || 0 };
        this.history.push(sample);
        const cutoff = now - MAX_HISTORY_S * 1000;
        while (this.history.length && this.history[0].t < cutoff) this.history.shift();
        this.last = sample;
        this.now = now;
        this._render();
        this._scheduleChart();
    }

    showNoData() {
        this.last = null;
        this._renderEmpty();
    }

    /** Forget everything (device disconnected). */
    reset() {
        this.history = [];
        this.last = null;
        this._renderEmpty();
        if (this.chart) {
            this.chart.data.datasets.forEach((d) => { d.data = []; });
            this.chart.update('none');
        }
    }

    destroy() {
        if (this.chartTimer) clearTimeout(this.chartTimer);
        if (this.chart) this.chart.destroy();
        this.chart = null;
    }

    _el(id) { return this.root.querySelector(`#${id}`); }

    _renderEmpty() {
        for (const ch of CHANNELS) {
            const card = this.root.querySelector(`.ch-card[data-channel="${ch.key}"]`);
            const reading = this._el(`ah-cps-${ch.key}`);
            if (reading) reading.textContent = '--';
            if (!card) continue;
            card.classList.remove('ch-active');
            const fill = card.querySelector('.ch-meter-fill');
            const peak = card.querySelector('.ch-meter-peak');
            if (fill) fill.style.width = '0%';
            if (peak) peak.style.left = '0%';
            card.querySelectorAll('[data-ch="avg"], [data-ch="peak"]').forEach((el) => { el.textContent = '--'; });
            card.querySelector('.ch-meter')?.setAttribute('aria-valuenow', '0');
        }
        const total = this._el('ah-cps-total');
        if (total) total.textContent = '--';
        this.root.querySelectorAll('[data-mix]').forEach((el) => { el.style.flexGrow = '0'; });
        this.root.querySelectorAll('[data-mix-label]').forEach((el) => { el.textContent = `${CHANNELS.find((c) => c.key === el.dataset.mixLabel).symbol} --`; });
    }

    _render() {
        if (!this.last) return;
        const now = this.now ?? Date.now();
        for (const ch of CHANNELS) {
            const rate = this.last[ch.key];
            const card = this.root.querySelector(`.ch-card[data-channel="${ch.key}"]`);
            const reading = this._el(`ah-cps-${ch.key}`);
            if (reading) reading.textContent = formatChannelRate(rate, this.unit);
            if (!card) continue;
            card.classList.toggle('ch-active', rate > 0);
            const peak = peakOf(this.history, now, this.windowS, ch.key);
            const fill = card.querySelector('.ch-meter-fill');
            const marker = card.querySelector('.ch-meter-peak');
            if (fill) fill.style.width = `${(logFraction(rate) * 100).toFixed(1)}%`;
            if (marker) marker.style.left = `${(logFraction(peak) * 100).toFixed(1)}%`;
            card.querySelector('.ch-meter')?.setAttribute('aria-valuenow', (logFraction(rate) * METER_DECADES).toFixed(2));
            const avg = meanOf(this.history, now, 60, ch.key);
            card.querySelector('[data-ch="avg"]').textContent = formatChannelRate(avg, this.unit);
            card.querySelector('[data-ch="peak"]').textContent = formatChannelRate(peak, this.unit);
        }
        const total = this.last.gamma + this.last.beta + this.last.alpha;
        const totalEl = this._el('ah-cps-total');
        if (totalEl) totalEl.textContent = formatChannelRate(total, this.unit);
        const mix = composition(this.last);
        for (const ch of CHANNELS) {
            const seg = this.root.querySelector(`[data-mix="${ch.key}"]`);
            if (seg) seg.style.flexGrow = String(mix[ch.key]);
            const label = this.root.querySelector(`[data-mix-label="${ch.key}"]`);
            if (label) label.textContent = `${ch.symbol} ${total > 0 ? Math.round(mix[ch.key] * 100) : '--'}%`;
        }
    }

    // ------------------------------------------------------------------ chart

    _scheduleChart() {
        if (this.chartTimer) return;
        this.chartTimer = setTimeout(() => { this.chartTimer = null; this._updateChart(); }, 1000);
    }

    _ensureChart() {
        if (this.chart) return this.chart;
        const canvas = this._el('ch-chart');
        if (!canvas || typeof Chart === 'undefined') return null;
        const t = this.theme;
        this.chart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            plugins: [themeGlowPlugin],
            data: {
                datasets: CHANNELS.map((ch) => ({
                    label: ch.name, data: [], pointRadius: 0, pointHoverRadius: 3, spanGaps: true, fill: false,
                    borderDash: ch.dash, borderColor: this.colors[ch.key], backgroundColor: 'transparent',
                    borderWidth: t.lineWidth, tension: t.tension, stepped: t.stepped ? 'before' : false,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                parsing: false,
                interaction: { mode: 'index', intersect: false, axis: 'x' },
                scales: { x: { type: 'linear', ticks: {}, grid: {}, border: {} }, y: { type: 'linear', ticks: {}, grid: {}, border: {} } },
                plugins: { legend: { display: false }, tooltip: {}, themeGlow: { blur: 0 } },
            },
        });
        this._applyThemeToChart();
        return this.chart;
    }

    /** Everything about the chart that depends on the theme: fonts, grid, line character, colours. */
    _applyThemeToChart() {
        const chart = this.chart;
        const t = this.theme;
        const o = chart.options;
        const tick = { color: t.textSecondary, font: { family: t.font, size: 10 }, maxTicksLimit: 6 };
        const grid = { color: t.grid, borderDash: t.gridDash, drawTicks: false };
        const border = { color: t.grid };
        o.scales.x.ticks = { ...tick, callback: (v) => (v === 0 ? 'now' : this.windowS >= 300 ? `${Math.round(v / 60)} min` : `${v}s`) };
        o.scales.y.ticks = { ...tick };
        o.scales.x.grid = grid; o.scales.y.grid = grid;
        o.scales.x.border = border; o.scales.y.border = border;
        o.plugins.themeGlow.blur = t.glow;
        o.plugins.tooltip = {
            backgroundColor: t.card, titleColor: t.text, bodyColor: t.text, borderColor: t.grid, borderWidth: 1,
            titleFont: { family: t.font }, bodyFont: { family: t.font }, displayColors: true, usePointStyle: false,
            callbacks: {
                title: (items) => (items.length ? `${Math.round(items[0].parsed.x)} s` : ''),
                label: (item) => `${item.dataset.label}: ${formatChannelRate(item.parsed.y / (this.unit === 'CPM' ? 60 : 1), this.unit)} ${this.unit.toLowerCase()}`,
            },
        };
        chart.data.datasets.forEach((d, i) => {
            const ch = CHANNELS[i];
            d.borderColor = this.colors[ch.key];
            d.borderWidth = t.lineWidth;
            d.tension = t.tension;
            d.stepped = t.stepped ? 'before' : false;
            d.backgroundColor = ch.key === 'gamma' ? withAlpha(this.colors.gamma, 0.1) : 'transparent';
            d.fill = ch.key === 'gamma' ? 'origin' : false;
        });
    }

    _updateChart() {
        const chart = this._ensureChart();
        if (!chart) return;
        const now = this.now ?? Date.now();
        const series = windowSeries(this.history, now, this.windowS);
        const k = this.unit === 'CPM' ? 60 : 1;
        const log = this.scale === 'log';
        chart.data.datasets.forEach((d, i) => {
            const key = CHANNELS[i].key;
            d.data = series.x.map((x, j) => {
                const v = series[key][j] * k;
                return { x, y: log && !(v > 0) ? null : v };
            });
        });
        const y = chart.options.scales.y;
        y.type = log ? 'logarithmic' : 'linear';
        y.min = log ? 0.1 * k : 0;
        y.beginAtZero = !log;
        chart.options.scales.x.min = -this.windowS;
        chart.options.scales.x.max = 0;
        chart.update('none');
    }
}
