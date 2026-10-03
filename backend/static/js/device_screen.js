/**
 * Replica of the AlphaHound AB+G display (128x128 monochrome OLED).
 *
 * Drawn from photographs of a real AB+G and from RadView's AB+G user guide and product page. The device
 * shows ONE of up to four mode "slots" (M1-M4, chosen in its Mode Selection menu); its left/right buttons, a
 * shake, and the serial E / Q commands step through those four slots. This replica models the same thing: four
 * slots, each holding a mode, and a current slot that E / Q (the GUI arrows) advance.
 *
 * What the serial link carries and what it does not:
 *  - carried: dose rate, gamma/beta/alpha count rates ('P'), the gamma spectrum ('G').
 *  - NOT carried: which slot or mode the device is on (it reports nothing when the mode changes: tested),
 *    its slot configuration, button presses, shakes, battery level, brightness, the light-tight sensor,
 *    alpha/beta pulse-height data (2D/3D spectroscopy), the radon estimate, the accelerometer.
 * So the replica cannot read the device's mode: set the slots and the current slot once to match the
 * device, and keep stepping with the GUI arrows (a physical button press or shake is invisible to us).
 * The battery and sun symbols are drawn dimmed: they are on the real screen but their state is not sent.
 * Colours come from a palette (see setPalette): the hardware's white-blue, or a tint of the active theme.
 */

import { DEVICE_SCREEN_PALETTE } from './palette.js';

const W = 128;
const H = 128;
const BG = '#000000';
const FONT = '"Segoe UI", "Helvetica Neue", Arial, sans-serif';
const UREM_TO_USV = 0.01;
const MAX_HISTORY_S = 3600;
const SLOT_COUNT = 4;
// The canvas is rendered at 4x with a faint grid between the 128x128 logical pixels, so it reads as an OLED
// and stays crisp at any size (drawing code keeps working in 128x128 units).
export const SCREEN_SCALE = 4;
const SCALE = SCREEN_SCALE;
// Gamma Spectroscopy shows a cursor energy at the top right; a fresh device starts it at 750 keV
export const DEFAULT_CURSOR_KEV = 750;
// Count-rate gauge: a flat arc ending +-39 degrees from vertical, four decades (1 ... 10K) over 78 degrees
export const GAUGE_HALF_SWEEP_DEG = 39;
export const GAUGE_DECADES = 4;

/**
 * All modes. Names follow the product page. `ab` marks modes that use the alpha/beta scintillator (the device
 * shows a check mark in the top bar for those and a crescent moon otherwise), `gamma` modes also show a gamma
 * symbol at the left of the top bar, and `needs` marks data the serial link does not carry.
 */
export const SCREEN_MODES = [
    { id: 1, name: 'Rolling Graph', ab: true },
    { id: 2, name: 'Low Power Sparkles', ab: true },
    { id: 3, name: 'Average Counts', ab: true },
    { id: 4, name: 'ABY Split Sparkles', ab: true },
    { id: 5, name: 'Basic AB 2D Spectroscopy', ab: true, needs: 'alpha/beta pulse heights' },
    { id: 6, name: 'Basic AB 3D Spectroscopy', ab: true, needs: 'alpha/beta pulse heights' },
    { id: 7, name: 'Radon Approximation', ab: true, needs: 'the device radon estimate' },
    { id: 9, name: 'Gamma Spectroscopy', ab: false, gamma: true },
    { id: 10, name: 'Spectrogram', ab: false, gamma: true },
    { id: 11, name: 'Analog Gauge', ab: true },
    { id: 12, name: 'Power Saver Mode', ab: false },
    { id: 13, name: 'G-Force', ab: false, needs: 'the accelerometer' },
];

/** Slots a new device is a reasonable guess for; the user sets the real ones once. */
export const DEFAULT_SLOTS = [4, 9, 1, 3];

/**
 * A rate as the device prints it. CPM is a whole number of counts in the last minute; CPS shows two decimals
 * below 1000 (86.29) and whole numbers above (2220).
 */
export function formatRateFor(perSecond, unit) {
    if (perSecond === null || perSecond === undefined || Number.isNaN(perSecond)) return '--';
    if (unit === 'CPM') return String(Math.round(perSecond * 60));
    return perSecond >= 1000 ? String(Math.round(perSecond)) : perSecond.toFixed(2);
}

/** Kept for callers that already have a CPS number: two decimals below 1000, whole numbers above. */
export function formatRate(v) {
    return formatRateFor(v, 'CPS');
}

/** A rate averaged over a window: whole numbers stay whole, fractions get two decimals ("461", "9307.50"). */
export function formatAverage(perSecond, unit) {
    if (perSecond === null || perSecond === undefined || Number.isNaN(perSecond)) return '--';
    const v = unit === 'CPM' ? perSecond * 60 : perSecond;
    if (v >= 100000) return String(Math.round(v));
    return Number.isInteger(Number(v.toFixed(2))) ? String(Math.round(v)) : v.toFixed(2);
}

/**
 * Dose readout text and unit for the header. The device prints uRem/h as a whole number ("5", "227") and
 * uSv with two decimals ("1.40").
 */
export function formatDose(uRemPerHour, unit) {
    const sv = unit === 'uSv';
    if (uRemPerHour === null || uRemPerHour === undefined || Number.isNaN(uRemPerHour)) {
        return { value: '--', unit: sv ? 'uSv' : 'µRem/h' };
    }
    if (sv) {
        const v = uRemPerHour * UREM_TO_USV;
        return { value: v >= 100 ? v.toFixed(0) : v.toFixed(2), unit: 'uSv' };
    }
    return { value: String(Math.max(0, Math.round(uRemPerHour))), unit: 'µRem/h' };
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

/**
 * Gauge needle angle in degrees from vertical (negative = left) for a count rate: 1 is the left end of the arc,
 * 10K the right end, 100 straight up; below 1 the needle rests at the left stop.
 */
export function gaugeAngleDeg(rate) {
    const decades = rate > 1 ? Math.min(GAUGE_DECADES, Math.log10(rate)) : 0;
    return -GAUGE_HALF_SWEEP_DEG + (decades / GAUGE_DECADES) * (2 * GAUGE_HALF_SWEEP_DEG);
}

/** Grey level 0..3 for a spectrogram cell from its share of the brightest cell (sqrt keeps weak cells visible). */
export function greyLevel(value, peak) {
    if (!(value > 0) || !(peak > 0)) return 0;
    const share = Math.sqrt(Math.min(1, value / peak));
    return share < 0.18 ? 0 : share < 0.42 ? 1 : share < 0.7 ? 2 : 3;
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
        this.pal = DEVICE_SCREEN_PALETTE;   // see setPalette: the real device's white-blue, or a tint of the theme
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

    /** Colours for the screen: DEVICE_SCREEN_PALETTE (as on the hardware) or screenPalette(theme) from palette.js. */
    setPalette(palette) {
        if (palette && palette.fg && palette.dim) this.pal = palette;
        this.draw();
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
            this._text('NO DEVICE', 64, 62, 11, this.pal.dim, 'center');
            this._text('connect an AlphaHound', 64, 78, 8, this.pal.dim, 'center');
            return;
        }
        switch (this.mode.id) {
            case 1: this._rollingGraph(now); break;
            case 2: this._lowPowerSparkles(); break;
            case 3: this._averageCounts(now); break;
            case 4: this._splitSparkles(); break;
            case 5: this._unavailable('AB 2D SPEC', ['no alpha/beta', 'pulse heights', 'over serial']); break;
            case 6: this._unavailable('AB 3D SPEC', ['no alpha/beta', 'pulse heights', 'over serial']); break;
            case 7: this._unavailable('RADON APPROX', ['calculated on', 'the device only']); break;
            case 9: this._gammaSpectrum(); break;
            case 10: this._spectrogram(); break;
            case 11: this._analogGauge(); break;
            case 12: this._sleep(); break;
            case 13: this._unavailable('G-FORCE', ['accelerometer', 'not on serial']); break;
            default: break;
        }
    }

    _text(str, x, y, size, color = this.pal.fg, align = 'left') {
        const ctx = this.ctx;
        ctx.fillStyle = color;
        ctx.font = `bold ${size}px ${FONT}`;
        ctx.textAlign = align;
        ctx.textBaseline = 'middle';
        ctx.fillText(str, x, y);
    }

    _line(x1, y1, x2, y2, color = this.pal.fg, width = 1) {
        const ctx = this.ctx;
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
    }

    _rect(x, y, w, h, color = this.pal.fg, r = 4) {
        const ctx = this.ctx;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x + 0.5, y + 0.5, w - 1, h - 1, r); else ctx.rect(x + 0.5, y + 0.5, w - 1, h - 1);
        ctx.stroke();
    }

    /** Battery outline (the level is not sent over serial, so it is drawn dimmed). */
    _battery(x, y) {
        const ctx = this.ctx;
        ctx.strokeStyle = this.pal.ghost;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, y + 2.5, 4, 8);
        ctx.fillStyle = this.pal.ghost;
        ctx.fillRect(x + 1.5, y + 0.5, 2, 2);
        ctx.fillRect(x + 1.5, y + 6.5, 2, 3);
    }

    /** Sun symbol of the light-tight sensor (not sent over serial: dimmed). */
    _sun(cx, cy) {
        const ctx = this.ctx;
        ctx.strokeStyle = this.pal.ghost;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, 1.8, 0, Math.PI * 2);
        ctx.stroke();
        for (let i = 0; i < 8; i++) {
            const a = (i * Math.PI) / 4;
            ctx.beginPath();
            ctx.moveTo(cx + Math.cos(a) * 3.2, cy + Math.sin(a) * 3.2);
            ctx.lineTo(cx + Math.cos(a) * 4.8, cy + Math.sin(a) * 4.8);
            ctx.stroke();
        }
    }

    /** Check mark (alpha/beta scintillator working) or crescent moon (a mode that does not use it). */
    _statusMark(cx, cy, check) {
        const ctx = this.ctx;
        ctx.strokeStyle = this.pal.fg;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        if (check) {
            ctx.moveTo(cx - 4, cy + 0.5);
            ctx.lineTo(cx - 1.5, cy + 3.5);
            ctx.lineTo(cx + 4, cy - 4);
        } else {
            ctx.arc(cx + 1, cy, 4.2, 0.62 * Math.PI, 1.38 * Math.PI);
            ctx.moveTo(cx + 1 - 4.2 * Math.cos(0.62 * Math.PI) * -1, cy);
            ctx.moveTo(cx + 3.2, cy - 3.2);
            ctx.arc(cx + 3.2, cy, 3.2, -0.5 * Math.PI, 0.5 * Math.PI, true);
        }
        ctx.stroke();
    }

    /**
     * Top bar, as on the device: [gamma glyph in gamma modes] dose and unit, a ")(" divider, battery, sun and a
     * status mark (check = alpha/beta scintillator in use, crescent moon = a mode that does not use it).
     * Battery level and the light-tight state are not sent over serial, so those two are drawn dimmed.
     */
    _header() {
        const mode = this.mode;
        if (mode.gamma) this._text('γ', 2, 9, 15, this.pal.fg, 'left');
        const d = formatDose(this.dose, this.unit);
        this._text(d.value, 56, 9, 15, this.pal.fg, 'right');
        this._text(d.unit, 59, 10, 8, this.pal.fg, 'left');
        const ctx = this.ctx;
        ctx.strokeStyle = this.pal.fg;
        ctx.lineWidth = 1;
        // ")(" divider between the dose reading and the status symbols
        ctx.beginPath();
        ctx.moveTo(92.5, 3);
        ctx.quadraticCurveTo(95.5, 10, 92.5, 17);
        ctx.moveTo(99.5, 3);
        ctx.quadraticCurveTo(96.5, 10, 99.5, 17);
        ctx.stroke();
        this._battery(101, 3);
        this._sun(112, 10);
        this._statusMark(121.5, 9.5, mode.ab && (this.cps !== null || mode.id === 11));
        ctx.fillStyle = this.pal.dim;
        ctx.fillRect(1, 17, 91, 1);
        ctx.fillRect(100, 17, 27, 1);
    }

    _total() {
        return this.cps ? this.cps.gamma + this.cps.beta + this.cps.alpha : null;
    }

    /** Bottom bar: "CPM:120" / "CPS:86.29" and the small curved tab at its right end. */
    _footer(perSecond = this._total()) {
        const ctx = this.ctx;
        ctx.strokeStyle = this.pal.dim;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(1, 106.5);
        ctx.lineTo(106, 106.5);
        ctx.quadraticCurveTo(111, 106.5, 111, 111.5);
        ctx.stroke();
        this._line(111.5, 111, 111.5, 124, this.pal.fg);
        this._text(`${this.rateUnit}:${formatRateFor(perSecond, this.rateUnit)}`, 2, 116.5, 14, this.pal.fg, 'left');
    }

    _sparkles(x, y, w, h, density) {
        const ctx = this.ctx;
        ctx.fillStyle = this.pal.fg;
        const n = Math.round(density * w * h * 0.55);
        for (let i = 0; i < n; i++) {
            ctx.fillRect(x + Math.floor(Math.random() * w), y + Math.floor(Math.random() * h), 1, 1);
        }
    }

    /** Mode "ABY Spark": alpha, beta and gamma sparkle panels, rate at the bottom. */
    _splitSparkles() {
        this._header();
        const labels = [['α', 'alpha'], ['β', 'beta'], ['γ', 'gamma']];
        const xs = [2, 44, 86];
        labels.forEach(([glyph, key], i) => {
            const rate = this.cps ? this.cps[key] : 0;
            this._sparkles(xs[i] + 2, 21, 36, 82, sparkleDensity(rate));
            this._rect(xs[i], 19, 40, 86, this.pal.fg, 6);
            this.ctx.fillStyle = BG;
            this.ctx.fillRect(xs[i] + 2, 21, 14, 15);
            this._text(glyph, xs[i] + 3, 28, 14, this.pal.fg, 'left');
        });
        this._footer();
    }

    /** Mode "LP Spark": nothing but an "LP" tag and one sparkle per count. */
    _lowPowerSparkles() {
        this._sparkles(0, 0, W, H, sparkleDensity(this._total() || 0, 400) * 0.6);
        this.ctx.fillStyle = BG;
        this.ctx.fillRect(2, 2, 24, 14);
        this._text('LP', 4, 9, 11, this.pal.fg, 'left');
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
        this._rect(1, 20, W - 2, 84, this.pal.fg, 3);
        const first = series.slice(0, Math.min(20, series.length)).sort((a, b) => a - b);
        const bkg = first.length ? first[Math.floor(first.length / 2)] : null;
        const yOf = (v) => 101 - (v / max) * 76;
        ctx.strokeStyle = this.pal.fg;
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
            ctx.fillStyle = this.pal.dim;
            for (let x = 3; x < W - 3; x += 4) ctx.fillRect(x, Math.round(yOf(bkg)), 2, 1);
            this._text('bkg', W - 5, Math.max(28, yOf(bkg) - 6), 10, this.pal.fg, 'right');
        }
        this._footer(pts.length ? pts[pts.length - 1].ab : null);
    }

    /** Mode "ABY AVG": alpha, beta and gamma averaged over a longer window (60 s here), total at the bottom. */
    _averageCounts(now) {
        this._header();
        const avgOf = (pick) => windowAverage(this.history, now, 60, pick);
        const rows = [['α', avgOf((h) => h.alpha)], ['β', avgOf((h) => h.beta)], ['γ', avgOf((h) => h.gamma)]];
        rows.forEach(([label, v], i) => {
            const top = 19 + i * 26;
            const mid = top + 12;
            // rounded left edge and a rule under each row, as on the device
            const ctx = this.ctx;
            ctx.strokeStyle = this.pal.fg;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(5.5, top + 1);
            ctx.quadraticCurveTo(1.5, top + 1, 1.5, top + 5);
            ctx.lineTo(1.5, top + 21);
            ctx.stroke();
            this._line(6, top + 24.5, W - 2, top + 24.5, this.pal.dim);
            this._text(`${label}:`, 5, mid, 15, this.pal.fg, 'left');
            this._text(formatAverage(v, this.rateUnit), 30, mid + 1, 16, this.pal.fg, 'left');
        });
        this._footer(avgOf((h) => h.total));
    }

    _unavailable(title, lines) {
        this._header();
        this._text(title, 64, 34, 12, this.pal.fg, 'center');
        lines.forEach((ln, i) => this._text(ln, 64, 58 + i * 13, 9, this.pal.dim, 'center'));
        this._footer();
    }

    /**
     * Mode "Y-spec": the gamma spectrum as a line, an open frame on the right, and a cursor ("x" on the curve)
     * with its energy at the top right. The cursor cannot be moved here; it starts where a new device's does.
     */
    _gammaSpectrum() {
        this._header();
        const ctx = this.ctx;
        // frame: top and right edges with rounded corners, a baseline, open on the left
        ctx.strokeStyle = this.pal.fg;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(1, 20.5);
        ctx.lineTo(118, 20.5);
        ctx.quadraticCurveTo(124.5, 20.5, 124.5, 26);
        ctx.lineTo(124.5, 98);
        ctx.quadraticCurveTo(124.5, 104.5, 118, 104.5);
        ctx.lineTo(1, 104.5);
        ctx.stroke();
        if (!this.spectrum) {
            this._text('NO SPECTRUM', 64, 52, 10, this.pal.dim, 'center');
            this._text('Get Current or', 64, 68, 8, this.pal.dim, 'center');
            this._text('Auto-refresh', 64, 79, 8, this.pal.dim, 'center');
            this._footer();
            return;
        }
        const e = this.spectrum.energies;
        const maxE = e && e.length ? e[e.length - 1] : this.spectrum.counts.length;
        const cols = W - 10;
        const bins = binSpectrum(this.spectrum.counts, cols);
        const max = Math.max(1, ...bins) * 1.05;
        const yOf = (c) => 103 - (c / max) * 76;
        ctx.beginPath();
        bins.forEach((c, i) => {
            if (i === 0) ctx.moveTo(4 + i, yOf(c)); else ctx.lineTo(4 + i, yOf(c));
        });
        ctx.stroke();
        // cursor
        const cursorKeV = maxE > DEFAULT_CURSOR_KEV ? DEFAULT_CURSOR_KEV : maxE / 2;
        const ci = Math.max(0, Math.min(cols - 1, Math.round((cursorKeV / maxE) * (cols - 1))));
        const cx = 4 + ci;
        const cy = yOf(bins[ci]);
        this._line(cx - 2, cy - 2, cx + 2, cy + 2, this.pal.fg, 1);
        this._line(cx - 2, cy + 2, cx + 2, cy - 2, this.pal.fg, 1);
        this._text(`${Math.round(cursorKeV)} keV`, 120, 28, 12, this.pal.fg, 'right');
        this._footer();
    }

    /** Mode "Spectrogram": successive gamma spectra as rows (newest on top) in four grey levels. */
    _spectrogram() {
        this._header();
        // five scale ticks under the top bar
        for (const x of [4, 34, 64, 94, 124]) this._line(x - 2, 20.5, x + 2, 20.5, this.pal.fg, 1);
        if (this.snapshots.length < 1) {
            this._text('NEEDS 2+ SPECTRA', 64, 52, 9, this.pal.dim, 'center');
            this._text('turn on Auto-refresh', 64, 68, 8, this.pal.dim, 'center');
            this._footer();
            return;
        }
        const ctx = this.ctx;
        const peak = Math.max(1e-9, ...this.snapshots.map((r) => Math.max(...r)));
        const shades = [null, this.pal.soft, this.pal.mid, this.pal.fg];
        this.snapshots.slice(0, 80).forEach((row, y) => {
            row.forEach((v, x) => {
                const level = greyLevel(v, peak);
                if (level > 0) {
                    ctx.fillStyle = shades[level];
                    ctx.fillRect(2 + x, 23 + y, 1, 1);
                }
            });
        });
        this._footer();
    }

    /**
     * Mode "Gauge": count rates on a log arc (1, 10, 100, 1K, 10K), one needle each for alpha, beta and gamma
     * from a pivot at the bottom centre. "bkg" and the unit sit at the lower right as on the device.
     */
    _analogGauge() {
        this._header();
        const ctx = this.ctx;
        const px = 64, py = 126, R = 98;
        const pos = (deg, r) => [px + Math.sin((deg * Math.PI) / 180) * r, py - Math.cos((deg * Math.PI) / 180) * r];
        ctx.strokeStyle = this.pal.fg;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const half = (GAUGE_HALF_SWEEP_DEG * Math.PI) / 180;
        ctx.arc(px, py, R, -Math.PI / 2 - half, -Math.PI / 2 + half);
        ctx.stroke();
        ['1', '10', '100', '1K', '10K'].forEach((label, k) => {
            const deg = -GAUGE_HALF_SWEEP_DEG + (k * 2 * GAUGE_HALF_SWEEP_DEG) / GAUGE_DECADES;
            const [x1, y1] = pos(deg, R - 4);
            const [x2, y2] = pos(deg, R + 2);
            this._line(x1, y1, x2, y2, this.pal.fg, 1);
            let [lx, ly] = pos(deg, R + 8);
            lx = Math.max(6, Math.min(W - 8, lx));
            this._text(label, lx, Math.max(24, ly), 8, this.pal.fg, 'center');
        });
        const unitRate = (perSecond) => (this.rateUnit === 'CPM' ? perSecond * 60 : perSecond);
        const needles = [['α', 'alpha'], ['β', 'beta'], ['γ', 'gamma']];
        needles.forEach(([glyph, key]) => {
            const rate = this.cps ? unitRate(this.cps[key]) : 0;
            const deg = gaugeAngleDeg(rate);
            const [tx, ty] = pos(deg, R - 24);
            this._line(px, py - 2, tx, ty, this.pal.fg, 1.4);
            const [gx, gy] = pos(deg, R - 12);
            ctx.fillStyle = BG;
            ctx.fillRect(gx - 5, gy - 6, 10, 12);
            this._text(glyph, gx, gy, 13, this.pal.fg, 'center');
        });
        this._text('bkg', 100, 80, 11, this.pal.fg, 'center');
        this._text(this.rateUnit, W - 3, 118, 14, this.pal.fg, 'right');
    }

    /** Power saver / sleep: the lowest-power screen, just the dose as large zero-padded digits. */
    _sleep() {
        this._text(formatSleepDose(this.dose, this.unit), 64, 56, 50, this.pal.fg, 'center');
        this._text(this.unit === 'uSv' ? 'uSv/h' : 'µRem/h', W - 3, H - 8, 9, this.pal.fg, 'right');
    }
}
