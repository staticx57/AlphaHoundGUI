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
        const metaHtml = Object.entries(metadata || {}).map(([key, value]) => {
            // Format the key: replace underscores with spaces and convert to uppercase
            let displayKey = key.toUpperCase().replaceAll('_', ' ');

            // Format the value based on the key
            let displayValue = value || '-';
            if (key === 'count_time_minutes' && value > 0) {
                displayValue = `${parseFloat(value).toFixed(2)} min`;
            }

            return `
                <div class="stat-card">
                    <div class="stat-label">${displayKey}</div>
                    <div class="stat-value">${displayValue}</div>
                </div>
            `;
        }).join('');
        this.elements.metadataPanel.innerHTML = metaHtml;
    }

    renderPeaks(peaks) {
        if (peaks && peaks.length > 0) {
            this.elements.peaksContainer.style.display = 'block';
            this.elements.peaksTbody.innerHTML = peaks.map(peak => `
                <tr>
                    <td>${peak.energy.toFixed(2)}</td>
                    <td class="text-right">${peak.counts.toFixed(0)}</td>
                </tr>
            `).join('');
        } else {
            this.elements.peaksContainer.style.display = 'none';
        }
    }

    renderIsotopes(isotopes) {
        const legacyList = document.getElementById('legacy-isotopes-list');

        if (isotopes && isotopes.length > 0) {
            this.elements.isotopesContainer.style.display = 'block';

            // Render legacy peak-matching results with confidence bars
            legacyList.innerHTML = isotopes.map(iso => {
                const confidence = iso.confidence;
                const barColor = confidence > 70 ? '#10b981' :
                    confidence > 40 ? '#f59e0b' : '#ef4444';
                const confidenceLabel = confidence > 70 ? 'HIGH' :
                    confidence > 40 ? 'MEDIUM' : 'LOW';

                // Generate NNDC reference link
                // Format isotope name for NNDC URL: "Cs-137" -> "137Cs"
                const nndcUrl = this.getNNDCUrl(iso.isotope);

                return `
                    <div class="isotope-result-item">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                            <strong style="color: var(--text-primary);">${iso.isotope}</strong>
                            <span style="font-size: 0.75rem; color: ${barColor}; font-weight: 600;">${confidenceLabel}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div class="confidence-track">
                                <div style="width: ${Math.min(confidence, 100)}%; height: 100%; background: ${barColor}; border-radius: 3px; transition: width 0.3s ease;"></div>
                            </div>
                            <span style="font-size: 0.8rem; color: var(--text-secondary); min-width: 45px;">${confidence.toFixed(0)}%</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                            <span>${iso.matches}/${iso.total_lines} peaks matched</span>
                            <a href="${nndcUrl}" target="_blank" rel="noopener" style="color: #3b82f6; text-decoration: none; font-size: 0.7rem;" title="View on NNDC NuDat">📚 NNDC</a>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            this.elements.isotopesContainer.style.display = 'none';
            legacyList.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem; font-style: italic;">No isotopes identified</p>';
        }
    }

    renderDecayChains(chains) {
        if (chains && chains.length > 0) {
            this.elements.decayChainsContainer.style.display = 'block';
            this.elements.decayChainsList.innerHTML = chains.map(chain => {
                const confidenceClass = chain.confidence_level.toLowerCase() + '-confidence';
                const confidenceBadge = chain.confidence_level === 'HIGH' ? '<span style="color: #10b981;">●</span>' :
                    chain.confidence_level === 'MEDIUM' ? '<span style="color: #f59e0b;">●</span>' : '<span style="color: #ef4444;">●</span>';

                const membersHTML = Object.entries(chain.detected_members).map(([isotope, peaks]) => {
                    const energies = peaks.map(p => p.energy.toFixed(1)).join(', ');
                    return `<div style="margin: 0.3rem 0; padding-left: 1rem;">
                        <img src="/static/icons/check.svg" class="icon" style="width: 14px; height: 14px; margin-right: 0.25rem; filter: invert(1);"><strong>${isotope}</strong>: ${energies} keV
                    </div>`;
                }).join('');

                // Create graphical decay chain visualization
                const chainMembers = this.getChainMembers(chain.chain_name);
                const detectedSet = new Set(Object.keys(chain.detected_members));

                const chainGraphic = chainMembers.map((member, idx) => {
                    const isDetected = detectedSet.has(member);
                    const isParent = idx === 0;
                    const isStable = idx === chainMembers.length - 1;

                    const statusClass = isDetected ? 'detected' : (isStable ? 'stable' : '');

                    const arrow = idx < chainMembers.length - 1 ?
                        `<div style="color: var(--text-secondary); font-size: 1.2rem; padding: 0 0.25rem;">→</div>` : '';

                    return `
                        <div style="display: flex; align-items: center;">
                            <div class="decay-step-box ${statusClass}">
                                <div style="font-weight: ${isDetected ? '700' : '500'}; font-size: 0.85rem;">
                                    ${member}
                                </div>
                                ${isDetected ? '<div style="font-size: 0.65rem; margin-top: 2px;"><span style="font-size: 10px;">✓</span> DETECTED</div>' : ''}
                                ${isStable ? '<div style="font-size: 0.65rem; margin-top: 2px;">STABLE</div>' : ''}
                            </div>
                            ${arrow}
                        </div>
                    `;
                }).join('');

                return `
                    <div class="chain-card" style="border-left: 4px solid ${chain.confidence_level === 'HIGH' ? '#10b981' : '#f59e0b'};">
                        <div class="chain-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                            <h4 style="margin: 0; color: var(--text-color);">${confidenceBadge} ${chain.chain_name}</h4>
                            <span class="${confidenceClass}" style="padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">
                                ${chain.confidence_level} (${chain.confidence.toFixed(0)}%)
                            </span>
                        </div>
                        
                        <!-- Graphical Decay Chain -->
                        <div class="decay-sequence-box">
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem; font-weight: 600;">
                                <img src="/static/icons/atom.svg" class="icon" style="width: 14px; height: 14px; margin-right: 0.25rem; filter: invert(1);">DECAY SEQUENCE
                            </div>
                            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.25rem;">
                                ${chainGraphic}
                            </div>
                            <div style="margin-top: 0.75rem; font-size: 0.7rem; color: var(--text-secondary); display: flex; gap: 1rem;">
                                <span><span style="color: #10b981;">●</span> Detected</span>
                                <span><span style="color: #8b5cf6;">●</span> Stable End Product</span>
                                <span><span style="color: rgba(255,255,255,0.3);">●</span> Not Detected</span>
                            </div>
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
                            ${chain.references && chain.references.length > 0 ? `
                            <div style="margin-top: 0.5rem; font-size: 0.7rem;">
                                <strong>References:</strong>
                                ${chain.references.map(ref => `<a href="${ref.url}" target="_blank" rel="noopener" style="color: #3b82f6; margin-left: 0.5rem;">${ref.name}</a>`).join(' · ')}
                            </div>` : ''}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            this.elements.decayChainsContainer.style.display = 'none';
        }
    }

    // Helper to get decay chain members based on chain name
    getChainMembers(chainName) {
        const chains = {
            "U-238 Chain": [
                "U-238", "Th-234", "Pa-234m", "U-234", "Th-230",
                "Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214",
                "Po-214", "Pb-210", "Bi-210", "Po-210", "Pb-206"
            ],
            "Th-232 Chain": [
                "Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224",
                "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208",
                "Po-212", "Pb-208"
            ],
            "U-235 Chain": [
                "U-235", "Th-231", "Pa-231", "Ac-227", "Th-227",
                "Ra-223", "Rn-219", "Po-215", "Pb-211", "Bi-211",
                "Tl-207", "Pb-207"
            ]
        };
        return chains[chainName] || [];
    }

    /**
     * Generate NNDC NuDat3 URL for an isotope
     * Converts "Cs-137" -> "https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=137Cs"
     */
    getNNDCUrl(isotope) {
        // Parse isotope name: "Cs-137" -> element="Cs", mass="137"
        const match = isotope.match(/^([A-Za-z]+)-?(\d+)m?$/);
        if (match) {
            const [, element, mass] = match;
            return `https://www.nndc.bnl.gov/nudat3/decaysearchdirect.jsp?nuc=${mass}${element}`;
        }
        // Fallback for unusual formats
        return `https://www.nndc.bnl.gov/nudat3/`;
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
