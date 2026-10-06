import { notifyAuto } from './dialogs.js';

export class CalibrationUI {
    constructor() {
        this.points = []; // Array of {id, channel, energy}
        this.nextId = 1;
        this.elements = {
            modal: document.getElementById('calibration-modal'),
            tbody: document.getElementById('cal-points-tbody'),
            btnCalculate: document.getElementById('btn-cal-calculate'),
            btnApply: document.getElementById('btn-cal-apply'),
            btnClose: document.getElementById('close-calibration'),
            results: document.getElementById('cal-results'),
            slope: document.getElementById('cal-slope'),
            intercept: document.getElementById('cal-intercept'),
            presetSelect: document.getElementById('cal-preset-select'),
            presetBtn: document.getElementById('btn-cal-preset'),
            presetNote: document.getElementById('cal-preset-note'),
            kevPerChannel: document.getElementById('cal-kev-per-channel'),
            offset: document.getElementById('cal-offset'),
            linearBtn: document.getElementById('btn-cal-linear'),
            poly: document.getElementById('cal-poly'),
            polyBtn: document.getElementById('btn-cal-poly'),
            presets: document.getElementById('cal-presets')
        };
        this.getSpectrum = () => null;   // set by the page: the spectrum on screen (its channel count and counts)
        this.setupListeners();
    }

    setupListeners() {
        if (this.elements.btnClose) this.elements.btnClose.addEventListener('click', () => this.hide());
        if (this.elements.btnCalculate) this.elements.btnCalculate.addEventListener('click', () => this.calculate());
        if (this.elements.btnApply) this.elements.btnApply.addEventListener('click', () => this.apply());
        if (this.elements.presetBtn) this.elements.presetBtn.addEventListener('click', () => this.usePreset());
        if (this.elements.linearBtn) this.elements.linearBtn.addEventListener('click', () => this.useLinear());
        if (this.elements.polyBtn) this.elements.polyBtn.addEventListener('click', () => this.usePolynomial());
    }

    show() {
        this.elements.modal.style.display = 'flex';
        this.loadPresets();
    }

    /**
     * The known axes for this spectrum's channel count, the best fit first and preselected: the server scores each by how well the spectrum
     * fits the known sources on that axis (so a RadiaCode capture with channel numbers only is recognised as one).
     */
    async loadPresets() {
        const el = this.elements;
        const spectrum = this.getSpectrum();
        const channels = spectrum?.counts?.length || 0;
        if (!el.presets || !el.presetSelect || !channels) return;
        el.presetSelect.innerHTML = '';
        el.presetNote.textContent = '';
        try {
            const listed = await (await fetch(`/analyze/energy-presets?channels=${channels}`)).json();
            const presets = Array.isArray(listed.presets) ? listed.presets : [];
            this._presets = presets;
            el.presetSelect.disabled = !presets.length;
            el.presetBtn.disabled = !presets.length;
            if (!presets.length) {
                el.presetNote.textContent = `No known axis for ${channels} channels: enter the energy per channel, or the polynomial, below.`;
                return;
            }
            let order = presets;
            let note = '';
            const response = await fetch('/analyze/energy-presets/suggest', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ counts: spectrum.counts })
            });
            const ranked = response.ok ? (await response.json()).suggestions || [] : [];
            if (ranked.length) {
                order = ranked.map((r) => presets.find((p) => p.key === r.key)).filter(Boolean);
                const best = ranked[0];
                note = best.score >= 10
                    ? `Best fit: ${best.name}. A known source stands ${best.score.toFixed(0)} standard errors over the noise on that axis.`
                    : 'No known source fits either axis: the file may come from another detector. Enter its axis below.';
            }
            el.presetSelect.innerHTML = order.map((p) => `<option value="${p.key}">${p.name}</option>`).join('');
            const chosen = order[0];
            el.presetNote.textContent = `${note} ${chosen?.note || ''}`.trim();
            el.presetSelect.onchange = () => {
                const now = presets.find((p) => p.key === el.presetSelect.value);
                el.presetNote.textContent = now?.note || '';
            };
        } catch (e) {
            el.presetNote.textContent = `Could not load the known axes: ${e.message}`;
        }
    }

    /** Ask the server for the energies of this spectrum's channels on an axis, and apply them. */
    async useAxis(request) {
        const channels = this.getSpectrum()?.counts?.length;
        if (!channels) { notifyAuto('Load a spectrum first.'); return; }
        try {
            const response = await fetch('/analyze/energy-axis', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channels, ...request })
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail;
                throw new Error(detail || `Request failed (${response.status})`);
            }
            document.dispatchEvent(new CustomEvent('calibrationApplied', {
                detail: { energies: body.energies, label: body.label, approximate: body.approximate, coefficients: body.coefficients }
            }));
            this.hide();
        } catch (e) {
            notifyAuto(e.message);
        }
    }

    usePreset() {
        const key = this.elements.presetSelect.value;
        if (key) this.useAxis({ preset: key });
    }

    useLinear() {
        const slope = parseFloat(this.elements.kevPerChannel.value);
        if (!(slope > 0)) { notifyAuto('Enter the energy per channel (keV), above zero.'); return; }
        this.useAxis({ kev_per_channel: slope, offset_keV: parseFloat(this.elements.offset.value) || 0 });
    }

    usePolynomial() {
        const coefficients = this.elements.poly.value.split(/[\s,;]+/).filter(Boolean).map(Number);
        if (!coefficients.length || coefficients.some((c) => !Number.isFinite(c))) {
            notifyAuto('Enter the coefficients as numbers, lowest order first, for example 0, 2.38, 0.0004.');
            return;
        }
        this.useAxis({ coefficients });
    }

    hide() {
        this.elements.modal.style.display = 'none';
    }

    /** True while the dialog is showing; the chart then takes clicks as calibration points. */
    isOpen() {
        return this.elements.modal.style.display !== 'none';
    }

    addPoint(channel, energy = '') {
        const id = this.nextId++;
        this.points.push({ id, channel, energy });
        this.renderTable();
    }

    removePoint(id) {
        this.points = this.points.filter(p => p.id !== id);
        this.renderTable();
    }

    updatePoint(id, field, value) {
        const point = this.points.find(p => p.id === id);
        if (point) {
            point[field] = value;
        }
    }

    renderTable() {
        this.elements.tbody.innerHTML = this.points.map(p => `
            <tr data-id="${p.id}">
                <td>${parseFloat(p.channel).toFixed(2)}</td>
                <td><input type="number" value="${p.energy}" placeholder="e.g. 662" onchange="calibrationUI.updatePoint(${p.id}, 'energy', this.value)" style="width: 80px;"></td>
                <td><button onclick="calibrationUI.removePoint(${p.id})" style="color: red; background: transparent; border: none; cursor: pointer;"><img src="/static/icons/close.svg" class="icon" style="width: 14px; height: 14px;"></button></td>
            </tr>
        `).join('');
    }

    async calculate() {
        // Filter valid points
        const validPoints = this.points.filter(p => p.channel && p.energy);
        if (validPoints.length < 2) {
            notifyAuto("Need at least 2 points to calibrate.");
            return;
        }

        const channels = validPoints.map(p => parseFloat(p.channel));
        const energies = validPoints.map(p => parseFloat(p.energy));

        try {
            const response = await fetch('/analyze/calibrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channels: channels,
                    known_energies: energies
                })
            });

            if (!response.ok) throw new Error("Calibration failed");

            const result = await response.json();
            this.tempResult = result; // Store for apply

            this.elements.results.style.display = 'block';
            this.elements.slope.textContent = result.params.slope.toFixed(4);
            this.elements.intercept.textContent = result.params.intercept.toFixed(4);
            this.elements.btnApply.style.display = 'inline-block';

        } catch (e) {
            notifyAuto(e.message);
        }
    }

    apply() {
        if (!this.tempResult) return;

        // We need to signal the main app to update the current data
        // For simplicity, we'll emit a custom event or callback
        // Or access global state if strictly necessary, but nicer to use event
        const event = new CustomEvent('calibrationApplied', {
            detail: {
                slope: this.tempResult.params.slope,
                intercept: this.tempResult.params.intercept
            }
        });
        document.dispatchEvent(event);
        this.hide();
    }
}

// Global instance for inline onclick handlers
window.calibrationUI = new CalibrationUI();
export const calUI = window.calibrationUI;
