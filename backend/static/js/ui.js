import { api } from './api.js';

export class AlphaHoundUI {
    constructor() {
        this.elements = {
            dropZone: document.getElementById('drop-zone'),
            dashboard: document.getElementById('dashboard'),
            metadataPanel: document.getElementById('metadata-panel'),
            peaksContainer: document.getElementById('peaks-container'),
            peaksTbody: document.getElementById('peaks-tbody'),
            resultsContainer: document.getElementById('analysis-results'),
            doseDisplay: document.getElementById('dose-display'),
            acquisitionTimer: document.getElementById('acquisition-timer'),
            isotopesContainer: document.getElementById('isotopes-container'),
            isotopesTbody: document.getElementById('isotopes-tbody'),
            decayChainsContainer: document.getElementById('decay-chains-container'),
            decayChainsList: document.getElementById('decay-chains-list'),
            deviceConnected: document.getElementById('device-connected'),
            portSelectParent: document.getElementById('port-select')?.parentElement,
            btns: {
                refresh: document.getElementById('btn-refresh-ports'),
                connect: document.getElementById('btn-connect-device'),
                advanced: document.getElementById('btn-advanced')
            }
        };
    }

    showLoading(message = 'Processing...') {
        this.elements.dropZone.innerHTML = `<div class="upload-icon">⏳</div><h2>${message}</h2>`;
    }

    resetDropZone() {
        setTimeout(() => {
            this.elements.dropZone.innerHTML = '<div class="upload-icon"><img src="/static/icons/upload.svg" style="width: 64px; height: 64px;"></div><h2>Drop new file to replace</h2><input type="file" id="file-input" accept=".n42,.xml,.csv">';
        }, 1000);
    }

    showError(message) {
        alert(message);
        this.elements.dropZone.innerHTML = '<div class="upload-icon">❌</div><h2>Error. Try again.</h2><p>' + message + '</p><input type="file" id="file-input" accept=".n42,.xml,.csv">';
    }

    renderDashboard(data) {
        this.elements.dashboard.style.display = 'block';
        this.renderMetadata(data.metadata);
        this.renderPeaks(data.peaks);
        this.renderIsotopes(data.isotopes);
        this.renderDecayChains(data.decay_chains);
    }

    renderMetadata(metadata) {
        const metaHtml = Object.entries(metadata || {}).map(([key, value]) => `
            <div class="stat-card">
                <div class="stat-label">${key.toUpperCase().replace('_', ' ')}</div>
                <div class="stat-value">${value || '-'}</div>
            </div>
        `).join('');
        this.elements.metadataPanel.innerHTML = metaHtml;
    }

    renderPeaks(peaks) {
        if (peaks && peaks.length > 0) {
            this.elements.peaksContainer.style.display = 'block';
            this.elements.peaksTbody.innerHTML = peaks.map(peak => `
                <tr>
                    <td>${peak.energy.toFixed(2)}</td>
                    <td>${peak.counts.toFixed(0)}</td>
                </tr>
            `).join('');
        } else {
            this.elements.peaksContainer.style.display = 'none';
        }
    }

    renderIsotopes(isotopes) {
        if (isotopes && isotopes.length > 0) {
            this.elements.isotopesContainer.style.display = 'block';
            this.elements.isotopesTbody.innerHTML = isotopes.map(iso => {
                const confidenceClass = iso.confidence > 70 ? 'high-confidence' :
                    iso.confidence > 40 ? 'medium-confidence' : 'low-confidence';
                return `
                    <tr class="${confidenceClass}">
                        <td><strong>${iso.isotope}</strong></td>
                        <td>${iso.confidence.toFixed(0)}%</td>
                        <td>${iso.matches}/${iso.total_lines}</td>
                    </tr>
                `;
            }).join('');
        } else {
            this.elements.isotopesContainer.style.display = 'none';
        }
    }

    renderDecayChains(chains) {
        if (chains && chains.length > 0) {
            this.elements.decayChainsContainer.style.display = 'block';
            this.elements.decayChainsList.innerHTML = chains.map(chain => {
                const confidenceClass = chain.confidence_level.toLowerCase() + '-confidence';
                const confidenceBadge = chain.confidence_level === 'HIGH' ? '🟢' :
                    chain.confidence_level === 'MEDIUM' ? '🟡' : '🔴';

                const membersHTML = Object.entries(chain.detected_members).map(([isotope, peaks]) => {
                    const energies = peaks.map(p => p.energy.toFixed(1)).join(', ');
                    return `<div style="margin: 0.3rem 0; padding-left: 1rem;">
                        ✅ <strong>${isotope}</strong>: ${energies} keV
                    </div>`;
                }).join('');

                return `
                    <div class="chain-card" style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; border-left: 4px solid ${chain.confidence_level === 'HIGH' ? '#10b981' : '#f59e0b'};">
                        <div class="chain-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                            <h4 style="margin: 0; color: var(--text-color);">${confidenceBadge} ${chain.chain_name}</h4>
                            <span class="${confidenceClass}" style="padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">
                                ${chain.confidence_level} (${chain.confidence.toFixed(0)}%)
                            </span>
                        </div>
                        <div class="chain-details" style="font-size: 0.9rem; color: var(--text-secondary);">
                            <div style="margin-bottom: 0.5rem;">
                                <strong>Detected Members:</strong> ${chain.num_detected}/${chain.num_key_isotopes} key indicators
                            </div>
                            ${membersHTML}
                             <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                                <strong>Likely Sources:</strong>
                                <ul style="margin: 0.5rem 0 0 1.5rem; padding: 0;">
                                    ${chain.applications.map(app => `<li style="margin: 0.25rem 0;">${app}</li>`).join('')}
                                </ul>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            this.elements.decayChainsContainer.style.display = 'none';
        }
    }

    updateDoseDisplay(doseRate) {
        if (doseRate !== null && doseRate !== undefined) {
            this.elements.doseDisplay.textContent = `${doseRate.toFixed(2)} µRem/hr`;
        } else {
            this.elements.doseDisplay.textContent = '-- µRem/hr';
        }
    }

    updateConnectionStatus(status) {
        if (status === 'connected') {
            this.elements.doseDisplay.textContent = '-- µRem/hr';
        } else if (status === 'connecting') {
            this.elements.doseDisplay.textContent = 'Connecting...';
        } else {
            this.elements.doseDisplay.textContent = 'Disconnected';
        }
    }

    setDeviceConnected(isConnected) {
        if (isConnected) {
            if (this.elements.deviceConnected) this.elements.deviceConnected.style.display = 'block';
            if (this.elements.portSelectParent) this.elements.portSelectParent.style.display = 'none';
            if (this.elements.btns.refresh) this.elements.btns.refresh.style.display = 'none';
            if (this.elements.btns.connect) this.elements.btns.connect.style.display = 'none';
            if (this.elements.btns.advanced) this.elements.btns.advanced.style.display = 'none';
        } else {
            if (this.elements.deviceConnected) this.elements.deviceConnected.style.display = 'none';
            if (this.elements.portSelectParent) this.elements.portSelectParent.style.display = 'flex';
            if (this.elements.btns.refresh) this.elements.btns.refresh.style.display = 'block';
            if (this.elements.btns.connect) this.elements.btns.connect.style.display = 'block';
            if (this.elements.btns.advanced) this.elements.btns.advanced.style.display = 'block';
        }
    }

    populatePorts(ports) {
        const select = document.getElementById('port-select');
        if (ports && ports.length > 0) {
            const options = ports.map(p =>
                `<option value="${p.device}">${p.device} - ${p.description}</option>`
            ).join('');
            select.innerHTML = options;
        } else {
            select.innerHTML = '<option value="">No ports found</option>';
        }
    }

    updateAcquisitionTimer(elapsed, total) {
        this.elements.acquisitionTimer.textContent = `${Math.round(elapsed)}s / ${total.toFixed(0)}s`;
    }
}

export const ui = new AlphaHoundUI();
