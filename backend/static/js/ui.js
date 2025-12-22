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
        this.elements.dropZone.innerHTML = `
            <div class="upload-icon">⏳</div>
            <h2>${message}</h2>
            <p>Please wait while we parse the spectrum...</p>
        `;
    }

    resetDropZone() {
        setTimeout(() => {
            this.elements.dropZone.innerHTML = `
                <div class="upload-icon">
                    <img src="/static/icons/upload.svg" style="width: 48px; height: 48px;">
                </div>
                <h2>Drop new file to replace</h2>
                <p>or click to browse local files</p>
                <input type="file" id="file-input" accept=".n42,.xml,.csv">
            `;
        }, 1000);
    }

    showError(message) {
        this.elements.dropZone.innerHTML = `
            <div class="upload-icon">❌</div>
            <h2>Error. Try again.</h2>
            <p style="color: #ef4444; font-size: 0.8rem; margin-top: 0.5rem;">${message}</p>
            <input type="file" id="file-input" accept=".n42,.xml,.csv">
        `;
    }

    renderDashboard(data) {
        this.elements.dashboard.style.display = 'block';
        this.renderMetadata(data.metadata);
        this.renderDataQualityWarning(data.data_quality);
        this.renderPeaks(data.peaks);
        this.renderIsotopes(data.isotopes);
        this.renderDecayChains(data.decay_chains);
        if (data.xrf_detections) {
            this.renderXRF(data.xrf_detections);
        }
    }

    renderXRF(xrfData) {
        // Remove existing XRF container if any
        const existing = document.getElementById('xrf-container');
        if (existing) existing.remove();

        if (!xrfData || xrfData.length === 0) return;

        // Build HTML for each detected element
        const elementsHTML = xrfData.map((item, idx) => {
            const confidenceColor = item.confidence === 'HIGH' ? '#22c55e' :
                item.confidence === 'MEDIUM' ? '#f59e0b' : '#94a3b8';
            const confidenceLabel = item.confidence || 'LOW';

            // Build energy table rows
            const energyRows = (item.lines || []).map(line => `
                <tr style="font-size: 0.75rem; color: #93c5fd;">
                    <td style="padding: 2px 6px;">${line.shell}</td>
                    <td style="padding: 2px 6px; text-align: right;">${line.peak_energy?.toFixed(1) || '-'} keV</td>
                    <td style="padding: 2px 6px; text-align: right;">${line.xrf_energy?.toFixed(1) || '-'} keV</td>
                    <td style="padding: 2px 6px; text-align: center;">${line.delta_keV?.toFixed(1) || '-'}</td>
                </tr>
            `).join('');

            const interpretation = item.interpretation ?
                `<div style="font-size: 0.75rem; color: #93c5fd; font-style: italic; margin-top: 0.5rem;">${item.interpretation}</div>` : '';

            return `
                <div class="xrf-element" data-xrf-index="${idx}" style="
                    background: rgba(59, 130, 246, 0.15);
                    border: 1px solid #3b82f6;
                    border-radius: 8px;
                    padding: 0.75rem;
                    cursor: pointer;
                    transition: all 0.2s ease;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="color: #60a5fa; font-size: 1rem;">${item.element}</strong>
                        <span style="
                            background: ${confidenceColor}20;
                            color: ${confidenceColor};
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-size: 0.65rem;
                            font-weight: 700;
                            text-transform: uppercase;
                        ">${confidenceLabel}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #93c5fd; margin-top: 0.25rem;">
                        ${(item.lines || []).map(l => l.shell).join(', ')}
                    </div>
                    ${interpretation}
                    <div class="xrf-details" style="display: none; margin-top: 0.75rem; border-top: 1px solid rgba(59, 130, 246, 0.3); padding-top: 0.5rem;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="font-size: 0.65rem; color: #60a5fa; text-transform: uppercase;">
                                    <th style="padding: 2px 6px; text-align: left;">Shell</th>
                                    <th style="padding: 2px 6px; text-align: right;">Detected</th>
                                    <th style="padding: 2px 6px; text-align: right;">Reference</th>
                                    <th style="padding: 2px 6px; text-align: center;">Δ keV</th>
                                </tr>
                            </thead>
                            <tbody>${energyRows}</tbody>
                        </table>
                    </div>
                </div>
            `;
        }).join('');

        const xrfHTML = `
            <div id="xrf-container" style="
                background: rgba(59, 130, 246, 0.1);
                border: 1px solid #3b82f6;
                border-radius: 8px;
                padding: 1rem;
                margin-top: 1rem;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; font-weight: 600; color: #60a5fa;">
                        <span>⚡</span> XRF / Fluorescence Detected
                    </div>
                    <button id="btn-clear-xrf-highlight" style="
                        background: transparent;
                        border: 1px solid #3b82f6;
                        color: #60a5fa;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.7rem;
                        cursor: pointer;
                        display: none;
                    ">Clear Highlights</button>
                </div>
                <div style="font-size: 0.75rem; color: #93c5fd; opacity: 0.8; margin-bottom: 0.75rem; font-style: italic;">
                    Click an element to highlight its peaks on the chart.
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 0.75rem;">
                    ${elementsHTML}
                </div>
            </div>
        `;

        // Insert after decay chains
        if (this.elements.decayChainsContainer) {
            this.elements.decayChainsContainer.insertAdjacentHTML('afterend', xrfHTML);
        }

        // Restore clear button visibility if we had an active highlight
        if (window._selectedXRFIndex !== undefined && window._selectedXRFIndex !== null) {
            const btn = document.getElementById('btn-clear-xrf-highlight');
            if (btn) btn.style.display = 'inline-block';
        }

        // Store XRF data for click handlers
        window._xrfData = xrfData;

        // Add click handlers for each element
        document.querySelectorAll('.xrf-element').forEach(el => {
            el.addEventListener('click', () => {
                const idx = parseInt(el.dataset.xrfIndex);
                const item = xrfData[idx];

                // Toggle details visibility
                const details = el.querySelector('.xrf-details');
                const isExpanded = details.style.display !== 'none';
                details.style.display = isExpanded ? 'none' : 'block';

                // Highlight peaks on chart (use global chartManager)
                if (!isExpanded && item.lines && item.lines.length > 0 && window.chartManager) {
                    const peaks = item.lines.map(l => ({
                        energy: l.peak_energy,
                        element: item.element,
                        shell: l.shell
                    }));

                    window._selectedXRFIndex = idx; // Track for persistence
                    window.chartManager.highlightXRFPeaks(peaks);
                    document.getElementById('btn-clear-xrf-highlight').style.display = 'inline-block';
                }
            });
        });

        // Clear highlights button
        document.getElementById('btn-clear-xrf-highlight')?.addEventListener('click', (e) => {
            e.stopPropagation();
            window._selectedXRFIndex = null; // Clear persistence
            if (window.chartManager) {
                window.chartManager.clearXRFHighlights();
            }
            document.getElementById('btn-clear-xrf-highlight').style.display = 'none';
        });
    }




    renderDataQualityWarning(dataQuality) {
        // Remove existing warning if present
        const existingWarning = document.getElementById('data-quality-warning');
        if (existingWarning) existingWarning.remove();

        if (!dataQuality || !dataQuality.warnings || dataQuality.warnings.length === 0) {
            return;
        }

        const warningHTML = `
            <div id="data-quality-warning" style="
                background: rgba(245, 158, 11, 0.15);
                border: 1px solid #f59e0b;
                border-radius: 8px;
                padding: 0.75rem 1rem;
                margin-bottom: 1rem;
                color: #fbbf24;
            ">
                <div style="display: flex; align-items: center; gap: 0.5rem; font-weight: 600; margin-bottom: 0.5rem;">
                    <span style="font-size: 1.2rem;">⚠️</span>
                    <span>Data Quality Warning</span>
                    <span style="margin-left: auto; font-size: 0.75rem; color: var(--text-secondary);">
                        Max peak: ${dataQuality.max_peak_counts || 0} counts
                    </span>
                </div>
                <ul style="margin: 0; padding-left: 1.5rem; font-size: 0.85rem; color: var(--text-secondary);">
                    ${dataQuality.warnings.map(w => `<li>${w}</li>`).join('')}
                </ul>
                ${dataQuality.mda_cs137 ? `
                <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.8rem;">
                    <span style="color: #10b981;">📊 Detection Sensitivity (MDA):</span>
                    <span style="margin-left: 0.5rem;" title="Minimum Detectable Activity for Cs-137 at 95% confidence">
                        Cs-137: ${dataQuality.mda_cs137.readable}
                    </span>
                </div>
                ` : ''}
            </div>
        `;

        // Insert before isotopes container
        if (this.elements.isotopesContainer) {
            this.elements.isotopesContainer.insertAdjacentHTML('beforebegin', warningHTML);
        }
    }

    renderMetadata(metadata) {
        const keyMap = {
            'count_time_minutes': 'Collection Time',
            'start_time': 'Start Time',
            'live_time_s': 'Live Time',
            'real_time_s': 'Real Time',
            'energy_calibration_slope': 'Cal Slope',
            'energy_calibration_offset': 'Cal Offset',
            'calibration': 'Calibration',
            'duration_s': 'Duration'
        };

        const metaHtml = Object.entries(metadata || {}).map(([key, value]) => {
            let displayKey = keyMap[key] || key.toUpperCase().replaceAll('_', ' ');
            let displayValue = value || '-';

            // Handle object values (like calibration coefficients)
            if (value !== null && typeof value === 'object') {
                if (key === 'calibration' && value.a0 !== undefined) {
                    // Format calibration as readable string
                    displayValue = `${value.a1?.toFixed(2) || '?'} keV/ch`;
                } else {
                    // Generic object handling
                    displayValue = JSON.stringify(value);
                }
            } else if (key === 'count_time_minutes' && value > 0) {
                displayValue = `${parseFloat(value).toFixed(2)} min`;
            } else if (key === 'duration_s' && typeof value === 'number') {
                // Format duration - convert seconds to readable format
                if (value >= 3600) {
                    const hrs = Math.floor(value / 3600);
                    const mins = Math.floor((value % 3600) / 60);
                    displayValue = `${hrs}h ${mins}m`;
                } else if (value >= 60) {
                    displayValue = `${(value / 60).toFixed(1)} min`;
                } else {
                    displayValue = `${value.toFixed(1)}s`;
                }
            } else if (key.includes('time') && !isNaN(value) && typeof value === 'number') {
                displayValue = `${value.toFixed(1)}s`;
            }

            return `
                <div class="stat-card">
                    <div class="stat-label">${displayKey}</div>
                    <div class="stat-value" title="${typeof value === 'object' ? JSON.stringify(value) : value}">${displayValue}</div>
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

            // Store isotopes for click handlers
            window._isotopeData = isotopes;

            // Render legacy peak-matching results with confidence bars and factor breakdown
            legacyList.innerHTML = isotopes.map((iso, idx) => {
                const confidence = iso.confidence;
                const barColor = confidence > 70 ? '#10b981' :
                    confidence > 40 ? '#f59e0b' : '#ef4444';
                const confidenceLabel = iso.confidence_label || (confidence > 70 ? 'HIGH' :
                    confidence > 40 ? 'MEDIUM' : 'LOW');

                // Generate NNDC reference link
                const nndcUrl = this.getNNDCUrl(iso.isotope);

                // Build confidence factors tooltip if available
                let factorsHTML = '';
                if (iso.confidence_factors) {
                    const factors = iso.confidence_factors;
                    factorsHTML = `
                        <div class="confidence-factors" style="display: none; margin-top: 0.5rem; padding: 0.5rem; background: rgba(0,0,0,0.3); border-radius: 4px; font-size: 0.7rem;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                                <span>Energy Match:</span>
                                <span style="color: #3b82f6;">${(factors.energy_match * 100 / 0.25).toFixed(0)}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                                <span>Intensity Weight:</span>
                                <span style="color: #8b5cf6;">${(factors.intensity_weight * 100 / 0.25).toFixed(0)}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                                <span>Fit Quality:</span>
                                <span style="color: #10b981;">${(factors.fit_quality * 100 / 0.20).toFixed(0)}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                                <span>Signal/Noise:</span>
                                <span style="color: #f59e0b;">${(factors.snr_factor * 100 / 0.15).toFixed(0)}%</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span>Multi-Peak:</span>
                                <span style="color: #ec4899;">${(factors.consistency * 100 / 0.15).toFixed(0)}%</span>
                            </div>
                        </div>
                    `;
                }

                // Show analysis mode badge if available
                const modeBadge = iso.analysis_mode === 'enhanced' ?
                    '<span style="font-size: 0.6rem; background: #3b82f680; padding: 1px 4px; border-radius: 2px; margin-left: 4px;">Enhanced</span>' : '';

                return `
                    <div class="isotope-result-item" data-isotope="${iso.isotope}" data-iso-index="${idx}" style="cursor: pointer; transition: background 0.2s;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                            <strong style="color: var(--text-primary);">${iso.isotope}${modeBadge}</strong>
                            <div style="display: flex; align-items: center; gap: 0.5rem;">
                                <button class="btn-highlight-isotope" data-iso-idx="${idx}" style="
                                    background: rgba(245, 158, 11, 0.2);
                                    border: 1px solid #f59e0b;
                                    color: #f59e0b;
                                    padding: 2px 6px;
                                    border-radius: 4px;
                                    font-size: 0.6rem;
                                    cursor: pointer;
                                " title="Highlight peaks on chart">📍</button>
                                <span style="font-size: 0.75rem; color: ${barColor}; font-weight: 600; cursor: ${iso.confidence_factors ? 'pointer' : 'default'};" 
                                      ${iso.confidence_factors ? 'onclick="event.stopPropagation(); this.parentElement.parentElement.parentElement.querySelector(\'.confidence-factors\').style.display = this.parentElement.parentElement.parentElement.querySelector(\'.confidence-factors\').style.display === \'none\' ? \'block\' : \'none\'"' : ''}>
                                    ${confidenceLabel} ${iso.confidence_factors ? '▼' : ''}
                                </span>
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div class="confidence-track">
                                <div style="width: ${Math.min(confidence, 100)}%; height: 100%; background: ${barColor}; border-radius: 3px; transition: width 0.3s ease;"></div>
                            </div>
                            <span style="font-size: 0.8rem; color: var(--text-secondary); min-width: 45px;">${confidence.toFixed(0)}%</span>
                        </div>
                        ${factorsHTML}
                        ${iso.activity_estimate ? `
                        <div style="font-size: 0.7rem; color: #10b981; margin-top: 0.25rem; padding: 3px 6px; background: rgba(16, 185, 129, 0.1); border-radius: 4px; display: inline-block;" 
                             title="Estimated activity (±${iso.activity_estimate.uncertainty_pct?.toFixed(0) || '?'}% uncertainty)">
                            ⚛️ Est. Activity: ${iso.activity_estimate.readable}
                        </div>
                        ` : ''}
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                            <span>${iso.matches}/${iso.total_lines} peaks matched</span>
                            <a href="${nndcUrl}" target="_blank" rel="noopener" style="color: #3b82f6; text-decoration: none; font-size: 0.7rem;" title="View on NNDC NuDat" onclick="event.stopPropagation();">📚 NNDC</a>
                        </div>
                    </div>
                `;
            }).join('');

            // Add click handlers for isotope highlighting
            this._setupIsotopeHighlightHandlers(isotopes);
        } else {
            this.elements.isotopesContainer.style.display = 'none';
            legacyList.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem; font-style: italic;">No isotopes identified</p>';
        }
    }

    /**
     * Setup click handlers for isotope peak highlighting with multi-select support
     */
    _setupIsotopeHighlightHandlers(isotopes) {
        // Track selected isotopes
        if (!window._selectedIsotopes) {
            window._selectedIsotopes = new Set();
        }

        // Color palette
        const colors = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6'];

        document.querySelectorAll('.btn-highlight-isotope').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.dataset.isoIdx);
                const iso = isotopes[idx];
                if (!iso) return;

                const isoName = iso.isotope;
                const safeKey = isoName.replace(/[^a-zA-Z0-9]/g, '_');
                const chart = window.chartManager?.chart;

                if (!chart) {
                    console.error('[Isotope] No chart');
                    return;
                }

                // Toggle using centralized chartManager methods
                if (window._selectedIsotopes.has(isoName)) {
                    // Deselect
                    window._selectedIsotopes.delete(isoName);
                    window.chartManager.removeIsotopeHighlight(isoName);
                    btn.style.background = 'rgba(245, 158, 11, 0.2)';
                    btn.style.borderColor = '#f59e0b';
                    btn.textContent = '📍';
                } else {
                    // Select
                    window._selectedIsotopes.add(isoName);
                    const colorIdx = (window._selectedIsotopes.size - 1) % colors.length;
                    const color = colors[colorIdx];

                    window.chartManager.addIsotopeHighlight(isoName, iso.matched_peaks, iso.expected_peaks, color);

                    btn.style.background = color + '30';
                    btn.style.borderColor = color;
                    btn.textContent = '✓';
                }
            });
        });
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
                // Use chain_sequence from enhanced detection if available
                const chainSequence = chain.chain_sequence || [];
                const chainMembers = chainSequence.length > 0
                    ? chainSequence.map(s => s.nuclide)
                    : this.getChainMembers(chain.chain_name);
                const detectedSet = new Set(Object.keys(chain.detected_members));

                const chainGraphic = chainMembers.map((member, idx) => {
                    const isDetected = detectedSet.has(member);
                    const isParent = idx === 0;
                    const isStable = idx === chainMembers.length - 1;

                    // Get half-life and branching from sequence data
                    const seqInfo = chainSequence[idx] || {};
                    const halfLife = seqInfo.half_life || '';
                    const branchingToNext = seqInfo.branching_to_next;

                    const statusClass = isDetected ? 'detected' : (isStable ? 'stable' : '');

                    // Arrow with branching ratio if < 100%
                    let arrow = '';
                    if (idx < chainMembers.length - 1) {
                        const branchLabel = branchingToNext && branchingToNext < 0.99
                            ? `<div title="Branching Ratio: Probability of this decay mode" style="display:flex; flex-direction:column; align-items:center; cursor: help;">
                                 <span style="font-size: 0.5rem; color: var(--text-secondary); line-height: 1;">BRANCH</span>
                                 <span style="font-size: 0.65rem; color: #f59e0b; font-weight:bold;">${(branchingToNext * 100).toFixed(1)}%</span>
                               </div>`
                            : '';

                        arrow = `<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-secondary); font-size: 1.2rem; padding: 0 0.25rem; min-width: 24px;">
                            ${branchLabel}
                            <span style="margin-top: -2px;">→</span>
                        </div>`;
                    }

                    return `
                        <div style="display: flex; align-items: center;">
                            <div class="decay-step-box ${statusClass}">
                                <div style="font-weight: ${isDetected ? '700' : '500'}; font-size: 0.85rem;">
                                    ${member}
                                </div>
                                ${halfLife ? `<div style="font-size: 0.55rem; color: var(--text-secondary); margin-top: 1px;">${halfLife}</div>` : ''}
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
                        
                        ${chain.equilibrium_status && chain.equilibrium_status.in_equilibrium !== null ? `
                        <div style="margin: 0.5rem 0; padding: 0.5rem; background: ${chain.equilibrium_status.in_equilibrium ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)'}; border-radius: 6px; font-size: 0.8rem;">
                            <span style="color: ${chain.equilibrium_status.in_equilibrium ? '#10b981' : '#f59e0b'}; font-weight: 600;">
                                ${chain.equilibrium_status.in_equilibrium ? '⚖️ SECULAR EQUILIBRIUM' : '⚠️ DISEQUILIBRIUM'}
                            </span>
                            <span style="color: var(--text-secondary); margin-left: 0.5rem;" title="${chain.equilibrium_status.details}">
                                ${chain.equilibrium_status.details}
                            </span>
                        </div>
                        ` : ''}
                        
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
            "U-238": [
                "U-238", "Th-234", "Pa-234m", "U-234", "Th-230",
                "Ra-226", "Rn-222", "Po-218", "Pb-214", "Bi-214",
                "Po-214", "Pb-210", "Bi-210", "Po-210", "Pb-206"
            ],
            "Th-232": [
                "Th-232", "Ra-228", "Ac-228", "Th-228", "Ra-224",
                "Rn-220", "Po-216", "Pb-212", "Bi-212", "Tl-208",
                "Po-212", "Pb-208"
            ],
            "U-235": [
                "U-235", "Th-231", "Pa-231", "Ac-227", "Th-227",
                "Ra-223", "Rn-219", "Po-215", "Pb-211", "Bi-211",
                "Tl-207", "Pb-207"
            ],
            // Man-made sources
            "Am-241": ["Am-241"],
            "Cs-137": ["Cs-137", "Ba-137m"],
            "Co-60": ["Co-60"],
            "Ra-226": ["Ra-226", "Rn-222", "Pb-214", "Bi-214", "Pb-210"]
        };

        // Try exact match first
        if (chains[chainName]) return chains[chainName];

        // Extract parent isotope from names like "U-238 Decay Chain" or "Th-232 Chain"
        const match = chainName.match(/^([A-Za-z]+-\d+)/);
        if (match && chains[match[1]]) {
            return chains[match[1]];
        }

        return [];
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

            // Safety Warning / Distance Estimation
            // Limit: 2000 µRem/hr (2 mRem/hr)
            if (doseRate > 2000) {
                this.elements.doseDisplay.style.color = '#ef4444';
                // Estimate distance to drop to 2000 assuming point source Inverse Square Law
                // D_safe = D_current * sqrt(Rate_current / Limit)
                // Assuming current distance is ~10cm (handheld)
                const safeDistCm = 10 * Math.sqrt(doseRate / 2000);

                // Update or create alert
                let safetyAlert = document.getElementById('safety-alert');
                if (!safetyAlert) {
                    safetyAlert = document.createElement('div');
                    safetyAlert.id = 'safety-alert';
                    safetyAlert.style.cssText = 'position: fixed; top: 80px; right: 20px; background: #ef4444; color: white; padding: 10px; border-radius: 8px; font-weight: bold; z-index: 2000; box-shadow: 0 4px 12px rgba(0,0,0,0.5); animation: pulse 2s infinite;';
                    document.body.appendChild(safetyAlert);

                    // Add pulse animation
                    const style = document.createElement('style');
                    style.innerHTML = `@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }`;
                    document.head.appendChild(style);
                }
                safetyAlert.innerHTML = `⚠️ HIGH RADIATION<br><div style="font-size:0.8em; font-weight:normal; margin-top:4px;">Safe Distance (2 mR/hr):<br>Approx. ${(safeDistCm / 100).toFixed(1)} meters</div>`;
                safetyAlert.style.display = 'block';
            } else {
                this.elements.doseDisplay.style.color = '';
                const safetyAlert = document.getElementById('safety-alert');
                if (safetyAlert) safetyAlert.style.display = 'none';
            }
        } else {
            this.elements.doseDisplay.textContent = '-- µRem/hr';
        }
    }

    updateTemperature(temp) {
        const tempDisplay = document.getElementById('temp-display');
        if (tempDisplay) {
            if (temp !== null && temp !== undefined) {
                tempDisplay.textContent = `🌡️ ${temp.toFixed(1)}°C`;
                tempDisplay.style.display = 'inline';
            } else {
                tempDisplay.style.display = 'none';
            }
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
