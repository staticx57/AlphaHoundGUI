import { api } from './api.js';
import { ui } from './ui.js';
import { chartManager } from './charts.js';

export class CalibrationUI {
    constructor() {
        this.points = []; // Array of {channel, energy, rowId}
        this.elements = {
            modal: document.getElementById('calibration-modal'),
            tbody: document.getElementById('cal-points-tbody'),
            btnCalculate: document.getElementById('btn-cal-calculate'),
            btnApply: document.getElementById('btn-cal-apply'),
            btnClose: document.getElementById('close-calibration'),
            results: document.getElementById('cal-results'),
            slope: document.getElementById('cal-slope'),
            intercept: document.getElementById('cal-intercept')
        };
        this.setupListeners();
    }

    setupListeners() {
        if (this.elements.btnClose) this.elements.btnClose.addEventListener('click', () => this.hide());
        if (this.elements.btnCalculate) this.elements.btnCalculate.addEventListener('click', () => this.calculate());
        if (this.elements.btnApply) this.elements.btnApply.addEventListener('click', () => this.apply());
    }

    show() {
        this.elements.modal.style.display = 'flex';
    }

    hide() {
        this.elements.modal.style.display = 'none';
    }

    addPoint(channel, energy = '') {
        const id = Date.now();
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
            alert("Need at least 2 points to calibrate.");
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
            alert(e.message);
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
        alert(`Calibration Applied: E = ${this.tempResult.params.slope.toFixed(4)} * Ch + ${this.tempResult.params.intercept.toFixed(4)}`);
    }
}

// Global instance for inline onclick handlers
window.calibrationUI = new CalibrationUI();
export const calUI = window.calibrationUI;
