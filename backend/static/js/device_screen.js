/**
 * Replica of the AlphaHound AB+G display (128x128 monochrome OLED).
 *
 * The device has 11 display modes (RadView's product page lists them as Mode 1-7 and 9-12; there is
 * no Mode 8). Each is redrawn here from the data this app actually receives over the serial link:
 * dose rate, gamma/beta/alpha count rates ('P' reply) and the gamma spectrum ('G' reply).
 *
 * Not available over serial, so shown as such rather than invented: the alpha/beta spectra
 * (Modes 5 and 6), the radon approximation (Mode 7), battery level and screen brightness.
 *
 * The device does not report which mode it is showing or when its buttons are pressed, so the
 * replica keeps its own mode: step it with the GUI buttons (which also send E/Q to the device)
 * or pick the mode the device is on from the selector.
 */

const W = 128;
const H = 128;
const FG = '#d6f2ff';
const DIM = '#4f7f99';
const BG = '#000000';
const UREM_TO_USV = 0.01;
const MAX_HISTORY_S = 3600;

export const SCREEN_MODES = [
    { id: 1, name: 'Rolling Graph' },
    { id: 2, name: 'Low Power Sparkles' },
    { id: 3, name: 'Average Counts' },
    { id: 4, name: 'ABY Split Sparkles' },
    { id: 5, name: 'Basic AB 2D Spectroscopy' },
    { id: 6, name: 'Basic AB 3D Spectroscopy' },
    { id: 7, name: 'Radon Approximation' },
    { id: 9, name: 'Gamma Spectroscopy' },
    { id: 10, name: 'Spectrogram' },
    { id: 11, name: 'Analog Gauge' },
    { id: 12, name: 'Power Saver Mode' },
];

/** Format a count rate the way the device does: 2 decimals below 1000, whole numbers above. */
export function formatRate(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '--';
    return v >= 1000 ? String(Math.round(v)) : v.toFixed(2);
}

/** Dose readout text and unit for the header. */
export function formatDose(uRemPerHour, unit) {
    if (uRemPerHour === null || uRemPerHour === undefined || Number.isNaN(uRemPerHour)) {
        return { value: '--', unit: unit === 'uSv' ? 'uSv' : 'uRem/h' };
    }
    if (unit === 'uSv') {
        const v = uRemPerHour * UREM_TO_USV;
        return { value: v >= 100 ? v.toFixed(0) : v.toFixed(2), unit: 'uSv' };
    }
    const v = uRemPerHour;
    return { value: v >= 100 ? v.toFixed(0) : (v >= 10 ? v.toFixed(1) : v.toFixed(2)), unit: 'uRem/h' };
}

/** Probability that a pixel is lit for a given count rate (more counts, denser sparkles). */
export function sparkleDensity(cps, ref = 100) {
    if (!(cps > 0)) return 0;
    return 1 - Math.exp(-cps / ref);
}

/** Mean of the samples newer than windowS seconds before `now` (null when there are none). */
export function windowAverage(history, now, windowS, pick = (h) => h.total) {
    let sum = 0;
    let n = 0;
    for (let i = history.length - 1; i >= 0; i--) {
        if (now - history[i].t > windowS * 1000) break;
        sum += pick(history[i]);
        n++;
    }
    return n ? sum / n : null;
}

/** Bin a spectrum into `bins` columns (sums of counts). */
export function binSpectrum(counts, bins) {
    const out = new Array(bins).fill(0);
    const n = counts.length;
    for (let i = 0; i < n; i++) {
        out[Math.min(bins - 1, Math.floor((i * bins) / n))] += counts[i];
    }
    return out;
}

export class DeviceScreen {
    constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.ctx = canvas ? canvas.getContext('2d') : null;
        if (canvas) {
            canvas.width = W;
            canvas.height = H;
        }
        this.unit = options.unit === 'uSv' ? 'uSv' : 'uRem';
        this.rateUnit = options.rateUnit === 'CPM' ? 'CPM' : 'CPS';
        this.connected = false;
        this.dose = null;
        this.cps = null;
        this.history = [];
        this.spectrum = null;      // {counts, energies}
        this.snapshots = [];       // gamma rate per energy bin between successive spectra
        this._prevSpectrum = null; // {counts, t}
        this.timer = null;
        this.modeIndex = 0;
        this.onModeChange = null;
        try {
            const saved = Number(localStorage.getItem('ahScreenMode'));
            const idx = SCREEN_MODES.findIndex((m) => m.id === saved);
            if (idx >= 0) this.modeIndex = idx;
        } catch (e) { /* storage unavailable: start on the first mode */ }
    }

    get mode() { return SCREEN_MODES[this.modeIndex]; }

    setMode(id) {
        const idx = SCREEN_MODES.findIndex((m) => m.id === Number(id));
        if (idx < 0) return false;
        this.modeIndex = idx;
        try { localStorage.setItem('ahScreenMode', String(SCREEN_MODES[idx].id)); } catch (e) { /* ignore */ }
        if (this.onModeChange) this.onModeChange(this.mode);
        this.draw();
        return true;
    }

    /** Next (+1) or previous (-1) mode, wrapping like the device's buttons. */
    step(delta) {
        const n = SCREEN_MODES.length;
        return this.setMode(SCREEN_MODES[(this.modeIndex + (delta >= 0 ? 1 : -1) + n) % n].id);
    }

    setUnit(unit) { this.unit = unit === 'uSv' ? 'uSv' : 'uRem'; this.draw(); }
    setRateUnit(unit) { this.rateUnit = unit === 'CPM' ? 'CPM' : 'CPS'; this.draw(); }

    setConnected(connected) {
        this.connected = !!connected;
        if (!connected) {
            this.dose = null;
            this.cps = null;
            this.history = [];
            this.spectrum = null;
            this.snapshots = [];
            this._prevSpectrum = null;
        }
        this.draw();
    }

    /** Feed one reading: dose in uRem/h and/or {gamma, beta, alpha} counts per second. */
    setReadings({ dose, cps } = {}, now = performance.now()) {
        if (dose !== undefined) this.dose = dose;
        if (cps) {
            this.cps = { gamma: cps.gamma || 0, beta: cps.beta || 0, alpha: cps.alpha || 0 };
            this.history.push({
                t: now, total: this.cps.gamma + this.cps.beta + this.cps.alpha,
                gamma: this.cps.gamma, beta: this.cps.beta, alpha: this.cps.alpha,
            });
            const cutoff = now - MAX_HISTORY_S * 1000;
            while (this.history.length && this.history[0].t < cutoff) this.history.shift();
        }
    }

    /** Feed the latest cumulative gamma spectrum (and its energy axis). */
    setSpectrum(counts, energies, now = performance.now()) {
        if (!counts || !counts.length) return;
        this.spectrum = { counts: counts.slice(), energies: energies ? energies.slice() : null };
        const prev = this._prevSpectrum;
        if (prev && prev.counts.length === counts.length && now > prev.t) {
            const dt = (now - prev.t) / 1000;
            const delta = counts.map((c, i) => Math.max(0, c - prev.counts[i]) / dt);
            this.snapshots.unshift(binSpectrum(delta, W - 4));
            if (this.snapshots.length > H - 24) this.snapshots.length = H - 24;
        }
        this._prevSpectrum = { counts: counts.slice(), t: now };
    }

    start(intervalMs = 250) {
        this.stop();
        this.draw();
        this.timer = setInterval(() => { if (!document.hidden) this.draw(); }, intervalMs);
    }

    stop() {
        if (this.timer) clearInterval(this.timer);
        this.timer = null;
    }

    // ---------------------------------------------------------------- drawing

    draw(now = performance.now()) {
        const ctx = this.ctx;
        if (!ctx) return;
        ctx.imageSmoothingEnabled = false;
        ctx.fillStyle = BG;
        ctx.fillRect(0, 0, W, H);
        if (!this.connected) {
            this._text('NO DEVICE', 64, 62, 11, DIM, 'center');
            this._text('connect an AlphaHound', 64, 78, 8, DIM, 'center');
            return;
        }
        switch (this.mode.id) {
            case 1: this._rollingGraph(now); break;
            case 2: this._lowPowerSparkles(); break;
            case 3: this._averageCounts(now); break;
            case 4: this._splitSparkles(); break;
            case 5: this._unavailable('AB 2D SPEC', ['no alpha/beta', 'spectrum over', 'serial link']); break;
            case 6: this._unavailable('AB 3D SPEC', ['no alpha/beta', 'spectrum over', 'serial link']); break;
            case 7: this._unavailable('RADON APPROX', ['calculated on', 'the device only']); break;
            case 9: this._gammaSpectrum(); break;
            case 10: this._spectrogram(); break;
            case 11: this._analogGauge(); break;
            case 12: this._powerSaver(); break;
            default: break;
        }
    }

    _text(str, x, y, size, color = FG, align = 'left') {
        const ctx = this.ctx;
        ctx.fillStyle = color;
        ctx.font = `bold ${size}px "Courier New", Consolas, monospace`;
        ctx.textAlign = align;
        ctx.textBaseline = 'middle';
        ctx.fillText(str, x, y);
    }

    _rect(x, y, w, h, color = FG, r = 4) {
        const ctx = this.ctx;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x + 0.5, y + 0.5, w - 1, h - 1, r); else ctx.rect(x + 0.5, y + 0.5, w - 1, h - 1);
        ctx.stroke();
    }

    _header() {
        const d = formatDose(this.dose, this.unit);
        this._text(d.value, 2, 8, 14, FG, 'left');
        this._text(d.unit, 92, 9, 9, FG, 'right');
        // connection check mark (the device shows a status tick here; battery and brightness are not
        // reported over serial so they are not drawn)
        const ctx = this.ctx;
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(112, 9); ctx.lineTo(116, 13); ctx.lineTo(124, 4);
        ctx.stroke();
        ctx.fillStyle = FG;
        ctx.fillRect(1, 17, W - 2, 1);
    }

    _total() {
        return this.cps ? this.cps.gamma + this.cps.beta + this.cps.alpha : null;
    }

    _footer() {
        const total = this._total();
        const v = total === null ? null : (this.rateUnit === 'CPM' ? total * 60 : total);
        this.ctx.fillStyle = FG;
        this.ctx.fillRect(1, 106, W - 2, 1);
        this._text(`${this.rateUnit}:${formatRate(v)}`, 2, 118, 13, FG, 'left');
    }

    _sparkles(x, y, w, h, density) {
        const ctx = this.ctx;
        ctx.fillStyle = FG;
        const n = Math.round(density * w * h * 0.55);
        for (let i = 0; i < n; i++) {
            ctx.fillRect(x + Math.floor(Math.random() * w), y + Math.floor(Math.random() * h), 1, 1);
        }
    }

    _splitSparkles() {
        this._header();
        const labels = [['α', 'alpha'], ['β', 'beta'], ['γ', 'gamma']];
        const xs = [1, 44, 87];
        labels.forEach(([glyph, key], i) => {
            const rate = this.cps ? this.cps[key] : 0;
            this._sparkles(xs[i] + 2, 21, 36, 82, sparkleDensity(rate));
            this._rect(xs[i], 19, 40, 86, FG, 5);
            this.ctx.fillStyle = BG;
            this.ctx.fillRect(xs[i] + 2, 21, 13, 14);
            this._text(glyph, xs[i] + 3, 28, 13, FG, 'left');
        });
        this._footer();
    }

    _lowPowerSparkles() {
        this._sparkles(0, 0, W, H, sparkleDensity(this._total() || 0, 400) * 0.6);
        const d = formatDose(this.dose, this.unit);
        this.ctx.fillStyle = BG;
        this.ctx.fillRect(W - 54, H - 14, 54, 14);
        this._text(d.value, W - 2, H - 7, 11, FG, 'right');
    }

    _rollingGraph(now) {
        this._header();
        const pts = this.history.filter((h) => now - h.t <= 120 * 1000);
        const max = Math.max(1, ...pts.map((p) => p.total)) * 1.1;
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, DIM, 3);
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1;
        ctx.beginPath();
        pts.forEach((p, i) => {
            const x = 3 + ((W - 6) * i) / Math.max(1, pts.length - 1);
            const y = 102 - (p.total / max) * 78;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
        this._text(formatRate(max / 1.1), W - 4, 27, 8, DIM, 'right');
        this._footer();
    }

    _averageCounts(now) {
        this._header();
        const rows = [['10s', 10], ['1m', 60], ['5m', 300]];
        rows.forEach(([label, secs], i) => {
            const avg = windowAverage(this.history, now, secs);
            const v = avg === null ? null : (this.rateUnit === 'CPM' ? avg * 60 : avg);
            const y = 30 + i * 22;
            this._text(`AVG ${label}`, 2, y, 9, DIM, 'left');
            this._text(formatRate(v), W - 3, y + 9, 13, FG, 'right');
        });
        this._footer();
    }

    _unavailable(title, lines) {
        this._header();
        this._text(title, 64, 34, 12, FG, 'center');
        lines.forEach((ln, i) => this._text(ln, 64, 58 + i * 13, 9, DIM, 'center'));
        this._footer();
    }

    _gammaSpectrum() {
        this._header();
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, DIM, 3);
        if (!this.spectrum) {
            this._text('NO SPECTRUM', 64, 52, 10, DIM, 'center');
            this._text('Get Current or', 64, 68, 8, DIM, 'center');
            this._text('Auto-refresh', 64, 79, 8, DIM, 'center');
            this._footer();
            return;
        }
        const bins = binSpectrum(this.spectrum.counts, W - 6);
        const max = Math.max(1, ...bins);
        ctx.fillStyle = FG;
        bins.forEach((c, i) => {
            const h = Math.round(Math.sqrt(c / max) * 78);
            if (h > 0) ctx.fillRect(3 + i, 102 - h, 1, h);
        });
        const e = this.spectrum.energies;
        if (e && e.length) this._text(`${Math.round(e[e.length - 1])}keV`, W - 4, 27, 8, DIM, 'right');
        this._footer();
    }

    _spectrogram() {
        this._header();
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, DIM, 3);
        if (this.snapshots.length < 1) {
            this._text('NEEDS 2+ SPECTRA', 64, 52, 9, DIM, 'center');
            this._text('turn on Auto-refresh', 64, 68, 8, DIM, 'center');
            this._footer();
            return;
        }
        const peak = Math.max(1e-9, ...this.snapshots.map((r) => Math.max(...r)));
        ctx.fillStyle = FG;
        this.snapshots.slice(0, 82).forEach((row, y) => {
            row.forEach((v, x) => {
                if (Math.random() < Math.sqrt(v / peak)) ctx.fillRect(3 + x, 22 + y, 1, 1);
            });
        });
        this._footer();
    }

    _analogGauge() {
        const ctx = this.ctx;
        const cx = 64, cy = 80, r = 50;
        const a0 = Math.PI * 5 / 6;                        // canvas angles grow clockwise: 150 deg = lower left
        const sweep = Math.PI * 4 / 3;                     // 240 deg over the top to the lower right
        const lo = 0, hi = 4;                              // log10 uRem/h: 1 .. 10000
        const angle = (v) => a0 + ((Math.log10(Math.max(1, v)) - lo) / (hi - lo)) * sweep;
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, r, a0, a0 + sweep);
        ctx.stroke();
        [1, 10, 100, 1000, 10000].forEach((v) => {
            const a = angle(v);
            ctx.beginPath();
            ctx.moveTo(cx + Math.cos(a) * (r - 7), cy + Math.sin(a) * (r - 7));
            ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
            ctx.stroke();
            const label = v >= 1000 ? `${v / 1000}k` : String(v);
            this._text(label, cx + Math.cos(a) * (r - 15), cy + Math.sin(a) * (r - 15), 8, DIM, 'center');
        });
        const dose = this.dose === null ? 0 : this.dose;
        const na = angle(Math.min(10000, Math.max(1, dose)));
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(na) * (r - 10), cy + Math.sin(na) * (r - 10));
        ctx.stroke();
        ctx.fillStyle = FG;
        ctx.beginPath();
        ctx.arc(cx, cy, 3, 0, Math.PI * 2);
        ctx.fill();
        const d = formatDose(this.dose, this.unit);
        this._text(`${d.value} ${d.unit}`, 64, 119, 11, FG, 'center');
    }

    _powerSaver() {
        this._text('PWR SAVE', 64, 60, 9, DIM, 'center');
        const d = formatDose(this.dose, this.unit);
        this._text(d.value, 4, H - 7, 8, DIM, 'left');
    }
}
