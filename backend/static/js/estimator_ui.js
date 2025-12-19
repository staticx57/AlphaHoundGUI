import { api } from './api.js';
import { ui } from './ui.js';

export class EstimatorUI {
    constructor() {
        this.callbacks = {};
        this.isOpen = false;
        this.detectorOptions = [];
    }

    init(callbacks) {
        this.callbacks = callbacks || {};
        this.modal = document.getElementById('estimator-modal');

        // Cache elements
        this.elements = {
            closeBtn: document.getElementById('close-estimator'),
            btnOpen: document.getElementById('btn-estimator-tool'),

            // Tabs
            tabProjection: document.getElementById('tab-projection'),
            tabTimeEst: document.getElementById('tab-time-est'),
            tabMDA: document.getElementById('tab-mda'),

            panelProjection: document.getElementById('panel-projection'),
            panelTimeEst: document.getElementById('panel-time-est'),
            panelMDA: document.getElementById('panel-mda'),

            // Projection Inputs
            currentTime: document.getElementById('est-current-time'),
            targetTime: document.getElementById('est-target-time'),
            factorDisplay: document.getElementById('est-factor'),
            projCountsDisplay: document.getElementById('est-proj-counts'),
            btnUpdateProj: document.getElementById('btn-calc-projection'),
            btnShowOverlay: document.getElementById('btn-show-projection'),

            // Time Estimator Inputs
            estTotalCounts: document.getElementById('est-total-counts'),
            estCPM: document.getElementById('est-cpm'),
            btnCalcTime: document.getElementById('btn-calc-time'),
            timeResultDiv: document.getElementById('time-est-result'),
            timeResultValue: document.getElementById('est-duration-result'),

            // MDA Inputs
            detectorSelect: document.getElementById('est-detector'),
            bgCounts: document.getElementById('est-bg-counts'),
            mdaTime: document.getElementById('est-mda-time'),
            btnCalcMDA: document.getElementById('btn-calc-mda'),
            mdaResult: document.getElementById('mda-result'),
            mdaValue: document.getElementById('mda-value')
        };

        this.setupListeners();
        this.loadDetectors();
    }

    setupListeners() {
        if (!this.elements.closeBtn) return;

        // Open/Close
        this.elements.btnOpen?.addEventListener('click', () => this.open());
        this.elements.closeBtn.addEventListener('click', () => {
            this.modal.style.display = 'none';
            this.isOpen = false;
        });

        // Tabs
        this.elements.tabProjection?.addEventListener('click', () => this.switchTab('projection'));
        this.elements.tabTimeEst?.addEventListener('click', () => this.switchTab('time'));
        this.elements.tabMDA?.addEventListener('click', () => this.switchTab('mda'));

        // Projection
        this.elements.btnUpdateProj?.addEventListener('click', () => this.updateProjectionStats());
        this.elements.btnShowOverlay?.addEventListener('click', () => {
            if (this.callbacks.onShowProjection) {
                const factor = this.calculateFactor();
                this.callbacks.onShowProjection(factor);
                this.modal.style.display = 'none';
            }
        });

        // Time Estimator
        this.elements.btnCalcTime?.addEventListener('click', () => this.calculateDuration());

        // MDA
        this.elements.btnCalcMDA?.addEventListener('click', () => this.calculateMDA());
    }

    async loadDetectors() {
        try {
            const data = await api.getDetectors();
            if (data && data.detectors) {
                this.detectorOptions = data.detectors;
                const html = data.detectors.map(d => `<option value="${d}">${d}</option>`).join('');

                // Populate Estimator Select
                if (this.elements.detectorSelect) this.elements.detectorSelect.innerHTML = html;

                // Populate ROI Select (GLOBAL UI)
                const roiSelect = document.getElementById('roi-detector');
                if (roiSelect) roiSelect.innerHTML = html;
            }
        } catch (e) {
            console.warn('[Estimator] Failed to load detectors:', e);
        }
    }

    open() {
        // Close other modals
        const decayModal = document.getElementById('decay-modal');
        if (decayModal) decayModal.style.display = 'none';

        this.modal.style.display = 'flex';
        this.isOpen = true;

        // Auto-populate current data
        if (this.callbacks.getCurrentData) {
            const data = this.callbacks.getCurrentData();
            if (data) {
                // Projection time
                const liveTime = (data.metadata ? (data.metadata.live_time || data.metadata.acquisition_time || 0) : 0);
                if (this.elements.currentTime) this.elements.currentTime.value = liveTime.toFixed(1);

                // Time Est Counts
                if (data.counts && this.elements.estTotalCounts) {
                    const total = data.counts.reduce((a, b) => a + b, 0);
                    this.elements.estTotalCounts.value = total;
                }
            }
        }

        this.updateProjectionStats();
    }

    switchTab(tab) {
        // Helper to reset tabs
        const tabs = ['projection', 'time', 'mda'];
        const tabTitle = {
            'projection': this.elements.tabProjection,
            'time': this.elements.tabTimeEst,
            'mda': this.elements.tabMDA
        };

        // Reset ALL
        tabs.forEach(t => {
            if (tabTitle[t]) {
                tabTitle[t].classList.remove('active');
                tabTitle[t].style.borderBottom = 'none';
                tabTitle[t].style.opacity = '0.7';
            }
        });
        this.elements.panelProjection.style.display = 'none';
        if (this.elements.panelTimeEst) this.elements.panelTimeEst.style.display = 'none';
        this.elements.panelMDA.style.display = 'none';

        // Activate Selected
        if (tab === 'projection') {
            this.elements.tabProjection.classList.add('active');
            this.elements.tabProjection.style.borderBottom = '2px solid var(--accent-color)';
            this.elements.tabProjection.style.opacity = '1';
            this.elements.panelProjection.style.display = 'block';
        } else if (tab === 'time') {
            this.elements.tabTimeEst.classList.add('active');
            this.elements.tabTimeEst.style.borderBottom = '2px solid var(--accent-color)';
            this.elements.tabTimeEst.style.opacity = '1';
            this.elements.panelTimeEst.style.display = 'block';
        } else {
            this.elements.tabMDA.classList.add('active');
            this.elements.tabMDA.style.borderBottom = '2px solid var(--accent-color)';
            this.elements.tabMDA.style.opacity = '1';
            this.elements.panelMDA.style.display = 'block';
        }
    }

    calculateFactor() {
        const current = parseFloat(this.elements.currentTime.value) || 1;
        const targetMin = parseFloat(this.elements.targetTime.value) || 1;
        const targetSec = targetMin * 60;
        return targetSec / current;
    }

    updateProjectionStats() {
        const factor = this.calculateFactor();
        this.elements.factorDisplay.textContent = factor.toFixed(2) + 'x';

        if (this.callbacks.getCurrentData) {
            const data = this.callbacks.getCurrentData();
            if (data && data.counts) {
                const currentTotal = data.counts.reduce((a, b) => a + b, 0);
                const projected = currentTotal * factor;

                // Format nicely
                let formatted = projected.toFixed(0);
                if (projected > 1e6) formatted = (projected / 1e6).toFixed(2) + ' M';
                else if (projected > 1e3) formatted = (projected / 1e3).toFixed(1) + ' k';

                this.elements.projCountsDisplay.textContent = formatted;
            }
        }
    }

    calculateDuration() {
        // T = Total / Rate
        const total = parseFloat(this.elements.estTotalCounts.value) || 0;
        const cpm = parseFloat(this.elements.estCPM.value) || 0;

        if (cpm <= 0) {
            ui.showError('Please enter a valid CPM > 0');
            return;
        }

        const minutes = total / cpm;
        const seconds = minutes * 60;
        const hours = minutes / 60;

        let result = '';
        if (hours >= 24) {
            result = (hours / 24).toFixed(1) + ' Days';
        } else if (hours >= 1) {
            result = hours.toFixed(1) + ' Hours';
        } else if (minutes >= 1) {
            result = minutes.toFixed(1) + ' Minutes';
        } else {
            result = seconds.toFixed(0) + ' Seconds';
        }

        this.elements.timeResultDiv.style.display = 'block';
        this.elements.timeResultValue.textContent = result;
    }

    async calculateMDA() {
        const bg = parseFloat(this.elements.bgCounts.value) || 0;
        const time = parseFloat(this.elements.mdaTime.value) || 60;
        const detector = this.elements.detectorSelect.value;
        const isoEnergy = prompt("Enter Isotope Energy (keV) to estimate efficiency:", "662"); // Quick hack for energy

        if (!isoEnergy) return;

        try {
            this.elements.btnCalcMDA.textContent = 'Calculating...';
            const result = await api.estimateMDA({
                background_counts: bg,
                live_time_s: time,
                detector: detector,
                energy_keV: parseFloat(isoEnergy)
            });

            this.elements.mdaResult.style.display = 'block';
            if (result.valid) {
                this.elements.mdaValue.textContent = result.mda_readable;
            } else {
                this.elements.mdaValue.textContent = "Error";
            }
        } catch (e) {
            ui.showError(e.message);
        } finally {
            this.elements.btnCalcMDA.textContent = 'Calculate MDA';
        }
    }
}

export const estimatorUI = new EstimatorUI();
