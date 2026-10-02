/**
 * Replica of the AlphaHound AB+G display (128x128 monochrome OLED).
 *
 * Built from RadView's AB+G user guide and product page. The device shows ONE of up to four mode
 * "slots" (M1-M4, chosen in its Mode Selection menu); its left/right buttons, a shake, and the serial
 * E / Q commands step through those four slots. This replica models the same thing: four slots, each
 * holding a mode, and a current slot that E / Q (the GUI arrows) advance.
 *
 * What the serial link carries and what it does not:
 *  - carried: dose rate, gamma/beta/alpha count rates ('P'), the gamma spectrum ('G').
 *  - NOT carried: which slot or mode the device is on (it reports nothing when the mode changes: tested),
 *    its slot configuration, button presses, shakes, battery level, brightness, the light-leak sensor,
 *    alpha/beta pulse-height data (2D/3D spectroscopy), the radon estimate, the accelerometer.
 * So the replica cannot read the device's mode: set the slots and the current slot once to match the
 * device, and keep stepping with the GUI arrows (a physical button press or shake is invisible to us).
 */

const W = 128;
const H = 128;
const FG = '#d6f2ff';
const DIM = '#4f7f99';
const BG = '#000000';
const UREM_TO_USV = 0.01;
const MAX_HISTORY_S = 3600;
const SLOT_COUNT = 4;
// The canvas is rendered at 4x with a faint grid between the 128x128 logical pixels, so it reads as an OLED
// and stays crisp at any size (drawing code keeps working in 128x128 units).
export const SCREEN_SCALE = 4;
const SCALE = SCREEN_SCALE;

/**
 * All modes. Names follow the product page; `ab` marks modes that use the alpha/beta scintillator
 * (the device shows a check mark in the top bar for those and an X otherwise), `needs` marks data the
 * serial link does not carry.
 */
export const SCREEN_MODES = [
    { id: 1, name: 'Rolling Graph', ab: true },
    { id: 2, name: 'Low Power Sparkles', ab: true },
    { id: 3, name: 'Average Counts', ab: true },
    { id: 4, name: 'ABY Split Sparkles', ab: true },
    { id: 5, name: 'Basic AB 2D Spectroscopy', ab: true, needs: 'alpha/beta pulse heights' },
    { id: 6, name: 'Basic AB 3D Spectroscopy', ab: true, needs: 'alpha/beta pulse heights' },
    { id: 7, name: 'Radon Approximation', ab: true, needs: 'the device radon estimate' },
    { id: 9, name: 'Gamma Spectroscopy', ab: false },
    { id: 10, name: 'Spectrogram', ab: false },
    { id: 11, name: 'Analog Gauge', ab: false },
    { id: 12, name: 'Power Saver Mode', ab: false },
    { id: 13, name: 'G-Force', ab: false, needs: 'the accelerometer' },
];

/** Slots a new device is a reasonable guess for; the user sets the real ones once. */
export const DEFAULT_SLOTS = [4, 9, 1, 3];

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

/** Sleep-mode readout: the dose as a zero-padded whole number of at least three digits (uRem/h) or uSv/h. */
export function formatSleepDose(uRemPerHour, unit) {
    if (uRemPerHour === null || uRemPerHour === undefined || Number.isNaN(uRemPerHour)) return '---';
    const v = unit === 'uSv' ? uRemPerHour * UREM_TO_USV : uRemPerHour;
    return String(Math.max(0, Math.round(v))).padStart(3, '0');
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

/** Validate a stored slot list: exactly SLOT_COUNT known mode ids, else the defaults. */
export function sanitizeSlots(slots) {
    const ok = Array.isArray(slots) && slots.length === SLOT_COUNT
        && slots.every((id) => SCREEN_MODES.some((m) => m.id === Number(id)));
    return ok ? slots.map(Number) : DEFAULT_SLOTS.slice();
}

export class DeviceScreen {
    constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.ctx = canvas ? canvas.getContext('2d') : null;
        if (canvas) {
            canvas.width = W * SCALE;
            canvas.height = H * SCALE;
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
        this.slots = DEFAULT_SLOTS.slice();
        this.slotIndex = 0;
        this.onModeChange = null;
        try {
            this.slots = sanitizeSlots(JSON.parse(localStorage.getItem('ahScreenSlots')));
            const saved = Number(localStorage.getItem('ahScreenSlot'));
            if (Number.isInteger(saved) && saved >= 0 && saved < SLOT_COUNT) this.slotIndex = saved;
        } catch (e) { /* storage unavailable or empty: use the defaults */ }
    }

    /** The mode shown right now: the one in the current slot. */
    get mode() { return SCREEN_MODES.find((m) => m.id === this.slots[this.slotIndex]); }

    _save() {
        try {
            localStorage.setItem('ahScreenSlots', JSON.stringify(this.slots));
            localStorage.setItem('ahScreenSlot', String(this.slotIndex));
        } catch (e) { /* ignore */ }
    }

    _changed() {
        this._save();
        if (this.onModeChange) this.onModeChange(this.mode, this.slotIndex);
        this.draw();
    }

    /** Put a mode into a slot (what the device's Mode Selection menu does). */
    setSlotMode(slotIndex, modeId) {
        const i = Number(slotIndex);
        if (!(i >= 0 && i < SLOT_COUNT) || !SCREEN_MODES.some((m) => m.id === Number(modeId))) return false;
        this.slots[i] = Number(modeId);
        this._changed();
        return true;
    }

    /** Declare which slot the device is on (use this to re-sync after a physical button press or shake). */
    setSlot(slotIndex) {
        const i = Number(slotIndex);
        if (!(i >= 0 && i < SLOT_COUNT)) return false;
        this.slotIndex = i;
        this._changed();
        return true;
    }

    /** Assign a mode to the CURRENT slot. */
    setMode(id) { return this.setSlotMode(this.slotIndex, id); }

    /** Next (+1) or previous (-1) slot, wrapping like the device's buttons and the E / Q commands. */
    step(delta) {
        return this.setSlot((this.slotIndex + (delta >= 0 ? 1 : SLOT_COUNT - 1)) % SLOT_COUNT);
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
                ab: this.cps.beta + this.cps.alpha,
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
        ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
        this._render(now);
        this._pixelGrid();
    }

    /** A faint dark grid between the logical pixels (drawn in device pixels, over everything). */
    _pixelGrid() {
        const ctx = this.ctx;
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = 'rgba(0, 0, 0, 0.30)';
        for (let i = 0; i <= W; i++) {
            ctx.fillRect(i * SCALE - 1, 0, 1, H * SCALE);
            ctx.fillRect(0, i * SCALE - 1, W * SCALE, 1);
        }
        ctx.restore();
    }

    _render(now) {
        const ctx = this.ctx;
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
            case 5: this._unavailable('AB 2D SPEC', ['no alpha/beta', 'pulse heights', 'over serial'], 'brand'); break;
            case 6: this._unavailable('AB 3D SPEC', ['no alpha/beta', 'pulse heights', 'over serial'], 'brand'); break;
            case 7: this._unavailable('RADON APPROX', ['calculated on', 'the device only'], 'brand'); break;
            case 9: this._gammaSpectrum(); break;
            case 10: this._spectrogram(); break;
            case 11: this._analogGauge(); break;
            case 12: this._sleep(); break;
            case 13: this._unavailable('G-FORCE', ['accelerometer', 'not on serial'], 'dose'); break;
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

    /**
     * Top bar. 'dose': the dose rate and unit (as in most modes); 'brand': the "RadView" title (average,
     * spectroscopy and radon modes). The right-hand mark follows the device's rule: a check when the mode
     * uses the alpha/beta scintillator and it is reporting, an X otherwise. Battery level and the light-tight
     * sun symbol are not sent over serial, so they are not drawn.
     */
    _header(kind = 'dose') {
        if (kind === 'brand') {
            this._text('RadView', 2, 8, 11, FG, 'left');
        } else {
            const d = formatDose(this.dose, this.unit);
            this._text(d.value, 2, 8, 14, FG, 'left');
            this._text(d.unit, 92, 9, 9, FG, 'right');
        }
        const ctx = this.ctx;
        const working = this.mode.ab && this.cps !== null;
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (working) {
            ctx.moveTo(112, 9); ctx.lineTo(116, 13); ctx.lineTo(124, 4);
        } else {
            ctx.moveTo(113, 4); ctx.lineTo(123, 13);
            ctx.moveTo(123, 4); ctx.lineTo(113, 13);
        }
        ctx.stroke();
        ctx.fillStyle = FG;
        ctx.fillRect(1, 17, W - 2, 1);
    }

    _total() {
        return this.cps ? this.cps.gamma + this.cps.beta + this.cps.alpha : null;
    }

    _rateText(perSecond) {
        return perSecond === null || perSecond === undefined ? '--'
            : formatRate(this.rateUnit === 'CPM' ? perSecond * 60 : perSecond);
    }

    _footer(perSecond = this._total()) {
        this.ctx.fillStyle = FG;
        this.ctx.fillRect(1, 106, W - 2, 1);
        this._text(`${this.rateUnit}:${this._rateText(perSecond)}`, 2, 118, 13, FG, 'left');
    }

    _sparkles(x, y, w, h, density) {
        const ctx = this.ctx;
        ctx.fillStyle = FG;
        const n = Math.round(density * w * h * 0.55);
        for (let i = 0; i < n; i++) {
            ctx.fillRect(x + Math.floor(Math.random() * w), y + Math.floor(Math.random() * h), 1, 1);
        }
    }

    /** Mode "ABY Spark": alpha, beta and gamma sparkle panels, rate at the bottom. */
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

    /** Mode "LP Spark": nothing but an "LP" tag and one sparkle per count. */
    _lowPowerSparkles() {
        this._sparkles(0, 0, W, H, sparkleDensity(this._total() || 0, 400) * 0.6);
        this.ctx.fillStyle = BG;
        this.ctx.fillRect(2, 2, 24, 14);
        this._text('LP', 4, 9, 11, FG, 'left');
    }

    /**
     * Mode "Rolling": the alpha + beta count rate as a scaling step graph with a "bkg" level
     * (the guide: alpha and beta combined, gamma not included; the device takes a background first).
     */
    _rollingGraph(now) {
        this._header();
        const pts = this.history.filter((h) => now - h.t <= 120 * 1000);
        const series = pts.map((p) => p.ab);
        const max = Math.max(1, ...series) * 1.15;
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, FG, 3);
        const first = series.slice(0, Math.min(20, series.length)).sort((a, b) => a - b);
        const bkg = first.length ? first[Math.floor(first.length / 2)] : null;
        const yOf = (v) => 101 - (v / max) * 76;
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1;
        ctx.beginPath();
        let lastY = null;
        series.forEach((v, i) => {
            const x = 3 + ((W - 6) * i) / Math.max(1, series.length - 1);
            const y = yOf(v);
            if (i === 0) ctx.moveTo(x, y); else { ctx.lineTo(x, lastY); ctx.lineTo(x, y); }   // hold, then step
            lastY = y;
        });
        ctx.stroke();
        if (bkg !== null) {
            ctx.fillStyle = DIM;
            for (let x = 3; x < W - 3; x += 4) ctx.fillRect(x, Math.round(yOf(bkg)), 2, 1);
            this._text('bkg', W - 5, Math.max(28, yOf(bkg) - 6), 9, FG, 'right');
        }
        this._footer(pts.length ? pts[pts.length - 1].ab : null);
    }

    /** Mode "ABY AVG": alpha, beta and total over a longer window (60 s here). */
    _averageCounts(now) {
        this._header('brand');
        const avgOf = (pick) => windowAverage(this.history, now, 60, pick);
        const rows = [['α:', avgOf((h) => h.alpha)], ['β:', avgOf((h) => h.beta)],
            [`${this.rateUnit}:`, avgOf((h) => h.total)]];
        rows.forEach(([label, v], i) => {
            const y = 33 + i * 24;
            this._rect(1, y - 11, W - 2, 22, FG, 3);
            this._text(label, 5, y, 11, FG, 'left');
            this._text(this._rateText(v), W - 5, y, 12, FG, 'right');
        });
        this._footer(avgOf((h) => h.total));
    }

    _unavailable(title, lines, headerKind) {
        this._header(headerKind);
        this._text(title, 64, 34, 12, FG, 'center');
        lines.forEach((ln, i) => this._text(ln, 64, 58 + i * 13, 9, DIM, 'center'));
        this._footer();
    }

    _gammaSpectrum() {
        this._header();
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, FG, 3);
        if (!this.spectrum) {
            this._text('NO SPECTRUM', 64, 52, 10, DIM, 'center');
            this._text('Get Current or', 64, 68, 8, DIM, 'center');
            this._text('Auto-refresh', 64, 79, 8, DIM, 'center');
            this._footer();
            return;
        }
        const bins = binSpectrum(this.spectrum.counts, W - 6);
        const max = Math.max(1, ...bins);
        ctx.strokeStyle = FG;
        ctx.lineWidth = 1;
        ctx.beginPath();
        bins.forEach((c, i) => {
            const y = 102 - Math.round(Math.sqrt(c / max) * 78);
            if (i === 0) ctx.moveTo(3 + i, y); else ctx.lineTo(3 + i, y);
        });
        ctx.stroke();
        const e = this.spectrum.energies;
        if (e && e.length) this._text(`${Math.round(e[e.length - 1])} keV`, W - 4, 27, 8, DIM, 'right');
        this._footer();
    }

    _spectrogram() {
        this._header();
        const ctx = this.ctx;
        this._rect(1, 20, W - 2, 84, FG, 3);
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

    /** Power saver / sleep: the lowest-power screen, just the dose as large zero-padded digits. */
    _sleep() {
        this._text(formatSleepDose(this.dose, this.unit), 64, 56, 46, FG, 'center');
        this._text(this.unit === 'uSv' ? 'uSv/h' : 'uRem/h', W - 3, H - 8, 9, FG, 'right');
    }
}
