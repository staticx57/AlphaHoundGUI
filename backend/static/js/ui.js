import { escapeHtml } from './html.js';
import { formatDoseRate, resolveUnit, getDosePref, UREM_PER_USV } from './units.js';
import { describeMetadata } from './metadata_cards.js';
import {
    summarizeIdentification, compareIdentifications, peakMatches, summaryFacts, formatCount, formatDuration,
    spectrumSignature, spectrumChange, confidenceLabel, describeSpectrum, chainLink,
} from './summary.js';

export class AlphaHoundUI {
    constructor() {
        this.elements = {
            dropZone: document.getElementById('drop-zone'),
            dashboard: document.getElementById('dashboard'),
            metadataPanel: document.getElementById('metadata-panel'),
            peaksContainer: document.getElementById('peaks-container'),
            peaksTbody: document.getElementById('peaks-tbody'),
            excessTbody: document.getElementById('excess-tbody'),
            resultsContainer: document.getElementById('analysis-results'),
            doseDisplay: document.getElementById('rc-dose-display'), // shared live-dose readout in the unified device panel
            acquisitionTimer: document.getElementById('acquisition-timer'),
            isotopesContainer: document.getElementById('isotopes-container'),
            resultsRow: document.getElementById('results-row'),
            summary: document.getElementById('result-summary'),
            decayChainsContainer: document.getElementById('decay-chains-container'),
            decayChainsList: document.getElementById('decay-chains-list'),
            deviceConnected: document.getElementById('unified-device-controls'),
            portSelectParent: document.getElementById('port-select')?.parentElement,
            btns: {
                refresh: document.getElementById('btn-refresh-ports'),
                connect: document.getElementById('btn-connect-device'),
                disconnect: document.getElementById('btn-disconnect-alphahound'),
                row: document.getElementById('alphahound-connection-row')
            }
        };
        this._sig = null;                           // fingerprint of the spectrum on screen
        this._lineSummary = null;                   // the headline from line matching
        this.aiState = { status: 'idle' };          // neural-net identification of the spectrum on screen
        this._selectedPeak = null;                  // index of the peak highlighted on the chart
    }

    /**
     * Theme colors as CSS variable references (with dark-theme fallbacks).
     * Returns `var(--x, fallback)` strings rather than resolved values so inline
     * styles built from them keep following the theme if it is switched later.
     * Only suitable for CSS contexts (not canvas / Chart.js).
     */
    getThemeColors() {
        const v = (name, fallback) => `var(${name}, ${fallback})`;
        return {
            detected: v('--status-detected', '#10b981'),
            detectedBg: v('--status-detected-bg', 'rgba(16, 185, 129, 0.2)'),
            stable: v('--status-stable', '#8b5cf6'),
            stableBg: v('--status-stable-bg', 'rgba(139, 92, 246, 0.2)'),
            undetected: v('--status-undetected', 'rgba(255, 255, 255, 0.3)'),
            confidenceHigh: v('--confidence-high', '#10b981'),
            confidenceMedium: v('--confidence-medium', '#f59e0b'),
            confidenceLow: v('--confidence-low', '#ef4444'),
            xrfPrimary: v('--xrf-primary', '#3b82f6'),
            xrfHigh: v('--xrf-high', '#22c55e'),
            xrfMedium: v('--xrf-medium', '#f59e0b'),
            xrfLow: v('--xrf-low', '#94a3b8')
        };
    }

    showLoading(message = 'Processing...') {
        this.elements.dropZone.innerHTML = `
            <div class="upload-icon"><img src="/static/icons/hourglass.svg" class="icon spin" style="width: 48px; height: 48px;"></div>
            <h2>${escapeHtml(message)}</h2>
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
                <input type="file" id="file-input" accept=".n42,.xml,.csv" aria-label="Choose a spectrum file">
            `;
        }, 1000);
    }

    showError(message) {
        this.elements.dropZone.innerHTML = `
            <div class="upload-icon"><img src="/static/icons/error.svg" style="width: 48px; height: 48px; filter: invert(1);"></div>
            <h2>Error. Try again.</h2>
            <p style="color: #ef4444; font-size: 0.8rem; margin-top: 0.5rem;">${escapeHtml(message)}</p>
            <input type="file" id="file-input" accept=".n42,.xml,.csv" aria-label="Choose a spectrum file">
        `;
    }

    /** @param {{live?: boolean}} [opts] live: an update of the acquisition in progress (the same spectrum, still growing) */
    /**
     * Offer the ROI panel the detector profile of the spectrum now on screen (the server resolves it from the file's
     * metadata: AlphaHound CsI / BGO, Radiacode 103 / 103G / 110), so efficiency and resolution are those of the instrument
     * that took it. A live update keeps whatever the user chose.
     */
    syncRoiDetector(data) {
        const select = document.getElementById('roi-detector');
        const wanted = data?.detector_profile;
        if (!select || !wanted) return;
        if (![...select.options].some((o) => o.value === wanted)) {
            const option = document.createElement('option');
            option.value = wanted;
            option.textContent = wanted;
            select.appendChild(option);
        }
        select.value = wanted;
    }

    renderDashboard(data, { live = false } = {}) {
        // Detector lower threshold (keV): auto-scale view starts here and ignores the noise below it
        if (window.chartManager) {
            window.chartManager.displayMinKeV = (typeof data?.display_min_keV === 'number') ? data.display_min_keV : null;
            window.chartManager.unassignedExcess = Array.isArray(data?.unassigned_excess) ? data.unassigned_excess : [];
        }
        this.elements.dashboard.style.display = 'block';
        document.dispatchEvent(new CustomEvent('spectrum-rendered', { detail: data }));   // export buttons that depend on the data listen
        // A different spectrum invalidates the AI answer; a live acquisition growing only makes it outdated.
        const signature = spectrumSignature(data.counts);
        if (!live || spectrumChange(this._sig, signature) === 'new') this.aiState = { status: 'idle' };
        if (this._selectedPeak !== null) {            // peaks are rebuilt: the marked one no longer maps to a row
            window.chartManager?.clearROIHighlight();
            this._selectedPeak = null;
        }
        this._sig = signature;
        if (window.chartManager) {
            window.chartManager.preserveZoom = live;                 // a live update keeps the window the user chose
            if (!live) window.chartManager.userZoom = null;          // a different spectrum starts from the auto view
        }
        if (!live) this.syncRoiDetector(data);
        this.renderMetadata(data.metadata);
        this.renderDataQualityWarning(data.data_quality);
        this.renderPeaks(data.peaks, data.isotopes, data.unassigned_excess);
        this.renderIsotopes(data.isotopes);
        this.renderSummary(data);
        this.renderAiResults();
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
            // Reference the CSS variables (not resolved values) so the badge follows theme switches
            const confidenceColor = item.confidence === 'HIGH' ? 'var(--xrf-high)' :
                item.confidence === 'MEDIUM' ? 'var(--xrf-medium)' : 'var(--xrf-low)';
            const confidenceLabel = item.confidence || 'LOW';

            // Build energy table rows
            const energyRows = (item.lines || []).map(line => `
                <tr style="font-size: 0.75rem; color: var(--xrf-text);">
                    <td style="padding: 2px 6px;">${line.shell}</td>
                    <td style="padding: 2px 6px; text-align: right;">${line.peak_energy?.toFixed(1) || '-'} keV</td>
                    <td style="padding: 2px 6px; text-align: right;">${line.xrf_energy?.toFixed(1) || '-'} keV</td>
                    <td style="padding: 2px 6px; text-align: center;">${line.delta_keV?.toFixed(1) || '-'}</td>
                </tr>
            `).join('');

            const interpretation = item.interpretation ?
                `<div style="font-size: 0.75rem; color: var(--xrf-text); font-style: italic; margin-top: 0.5rem;">${item.interpretation}</div>` : '';

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
                        <strong style="color: var(--xrf-accent); font-size: 1rem;">${item.element}</strong>
                        <span style="
                            background: color-mix(in srgb, ${confidenceColor} 20%, transparent);
                            color: ${confidenceColor};
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-size: 0.65rem;
                            font-weight: 700;
                            text-transform: uppercase;
                        ">${confidenceLabel}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--xrf-text); margin-top: 0.25rem;">
                        ${(item.lines || []).map(l => l.shell).join(', ')}
                    </div>
                    ${interpretation}
                    <div class="xrf-details" style="display: none; margin-top: 0.75rem; border-top: 1px solid rgba(59, 130, 246, 0.3); padding-top: 0.5rem;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="font-size: 0.65rem; color: var(--xrf-accent); text-transform: uppercase;">
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
                    <div style="display: flex; align-items: center; gap: 0.5rem; font-weight: 600; color: var(--xrf-accent);">
                        <img src="/static/icons/bolt.svg" class="icon" style="width: 16px; height: 16px;"> XRF / Fluorescence Detected
                    </div>
                    <button id="btn-clear-xrf-highlight" style="
                        background: transparent;
                        border: 1px solid #3b82f6;
                        color: var(--xrf-accent);
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.7rem;
                        cursor: pointer;
                        display: none;
                    ">Clear Highlights</button>
                </div>
                <div style="font-size: 0.75rem; color: var(--xrf-text); margin-bottom: 0.75rem; font-style: italic;">
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
                    <img src="/static/icons/warning.svg" class="icon" style="width: 20px; height: 20px; filter: invert(1);">
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
                    <span style="color: #10b981;"><img src="/static/icons/chart.svg" class="icon" style="width: 14px; height: 14px; margin-right: 4px;"> Detection Sensitivity (MDA):</span>
                    <span style="margin-left: 0.5rem;" title="Minimum Detectable Activity for Cs-137 at 95% confidence">
                        Cs-137: ${dataQuality.mda_cs137.readable}
                    </span>
                </div>
                ` : ''}
            </div>
        `;

        // Insert above the peaks / identification row
        const anchor = this.elements.resultsRow || this.elements.isotopesContainer;
        if (anchor) anchor.insertAdjacentHTML('beforebegin', warningHTML);
    }

    renderMetadata(metadata) {
        this._metadata = metadata;
        const cards = describeMetadata(metadata, { doseUnit: resolveUnit(getDosePref(), 'uSv') });
        const el = (tag, className, text) => {
            const node = document.createElement(tag);
            if (className) node.className = className;
            if (text !== undefined) node.textContent = text;
            return node;
        };
        this.elements.metadataPanel.replaceChildren(...cards.map((card) => {
            const box = el('div', 'stat-card');
            box.dataset.key = card.key;
            const label = el('div', 'stat-label', card.label);
            if (card.tip) {
                const tip = el('span', 'info-tip', '\u24d8');
                tip.tabIndex = 0;
                tip.setAttribute('role', 'img');
                tip.setAttribute('aria-label', card.title);
                tip.title = card.title;
                label.append(' ', tip);
            }
            const value = el('div', 'stat-value', card.value);
            if (card.title) value.title = card.title;
            box.append(label, value);
            if (card.rows && card.rows.length) {
                const list = el('dl', 'stat-rows');
                for (const row of card.rows) list.append(el('dt', '', row.k), el('dd', '', row.v));
                box.append(list);
            }
            if (card.detail) box.append(el('div', 'stat-detail', card.detail));
            return box;
        }));
    }

    /** Redraw the cards (the dose unit preference changed). */
    refreshMetadata() {
        if (this._metadata) this.renderMetadata(this._metadata);
    }

    renderPeaks(peaks, isotopes, excess) {
        this._peaks = Array.isArray(peaks) ? peaks : [];
        this._excess = Array.isArray(excess) ? excess : [];
        if (this.elements.excessTbody) this.elements.excessTbody.innerHTML = '';
        if (!this._peaks.length && !this._excess.length) {
            this.elements.peaksContainer.style.display = 'none';
            return;
        }
        this.elements.peaksContainer.style.display = 'block';
        const matches = peakMatches(this._peaks, isotopes);
        const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
        const excessRows = this._excess.map((ex, j) => `
                <tr class="peak-row peak-excess" data-excess-index="${j}" tabindex="0" role="button" aria-pressed="false"
                    aria-label="${Number(ex.energy).toFixed(0)} keV: unassigned excess, highlight it on the chart">
                    <td>${Number(ex.energy).toFixed(0)}</td>
                    <td class="text-right">\u2013</td>
                    <td class="text-right">${Number(ex.fwhm_expected).toFixed(1)}</td>
                    <td class="peak-matches"><span class="peak-excess-tag" title="Structure the fitted peaks do not explain: an escape peak, Compton backscatter or an unresolved line. It stands ${Number(ex.significance).toFixed(0)} standard errors over the continuum. It is not used to identify anything.">unassigned excess &middot; ${Number(ex.significance).toFixed(0)}&sigma;</span></td>
                </tr>`).join('');
        this.elements.peaksTbody.innerHTML = this._peaks.map((peak, i) => {
            const fwhm = Number(peak.fwhm);
            const fwhmText = Number.isFinite(fwhm) && fwhm > 0 ? fwhm.toFixed(1) : '\u2013';
            const weak = peak.fit_valid === false;
            const names = matches[i];
            const matchHtml = names.length
                ? names.map((n) => `<span class="peak-match">${esc(n)}</span>`).join('')
                : '<span class="peak-nomatch" aria-label="no match">\u2013</span>';
            const selected = this._selectedPeak === i;
            return `
                <tr class="peak-row${selected ? ' selected' : ''}" data-peak-index="${i}" tabindex="0" role="button"
                    aria-pressed="${selected}" aria-label="${peak.energy.toFixed(1)} keV: highlight this peak on the chart">
                    <td>${peak.energy.toFixed(2)}</td>
                    <td class="text-right">${peak.counts.toFixed(0)}</td>
                    <td class="text-right${weak ? ' peak-weak' : ''}"${weak ? ' title="Peak fit is poor: treat the width as approximate"' : ''}>${fwhmText}</td>
                    <td class="peak-matches">${matchHtml}</td>
                </tr>`;
        }).join('');
        if (this.elements.excessTbody) this.elements.excessTbody.innerHTML = excessRows;
        this.elements.excessTbody?.querySelectorAll('.peak-excess').forEach((row) => {
            const toggle = () => this._toggleExcessHighlight(Number(row.dataset.excessIndex));
            row.addEventListener('click', toggle);
            row.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
            });
        });
        this.elements.peaksTbody.querySelectorAll('.peak-row').forEach((row) => {
            const toggle = () => this._togglePeakHighlight(Number(row.dataset.peakIndex));
            row.addEventListener('click', toggle);
            row.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
            });
        });
    }

    /** Mark an unassigned excess on the spectrum (click again to clear); the band is its expected FWHM either side. */
    _toggleExcessHighlight(index) {
        const ex = this._excess?.[index];
        const chart = window.chartManager;
        if (!ex || !chart) return;
        const row = this.elements.excessTbody?.querySelector(`.peak-excess[data-excess-index="${index}"]`);
        const same = row?.classList.contains('selected');
        this._selectedPeak = null;
        chart.clearROIHighlight();
        document.querySelectorAll('#peaks-tbody .peak-row, #excess-tbody .peak-row').forEach((r) => {
            r.classList.remove('selected');
            r.setAttribute('aria-pressed', 'false');
        });
        if (!same && row) {
            chart.highlightROI(ex.energy - ex.fwhm_expected, ex.energy + ex.fwhm_expected, `${Number(ex.energy).toFixed(0)} keV (unassigned)`);
            row.classList.add('selected');
            row.setAttribute('aria-pressed', 'true');
        }
    }

    /** Mark a peak on the spectrum (click again to clear); the band is one FWHM either side. */
    _togglePeakHighlight(index) {
        const peak = this._peaks?.[index];
        const chart = window.chartManager;
        if (!peak || !chart) return;
        const same = this._selectedPeak === index;
        this._selectedPeak = same ? null : index;
        this.elements.excessTbody?.querySelectorAll('.peak-excess.selected').forEach((r) => {
            r.classList.remove('selected');
            r.setAttribute('aria-pressed', 'false');
        });
        if (same) {
            chart.clearROIHighlight();
        } else {
            const half = Math.max(Number(peak.fwhm) || 0, 6);
            chart.highlightROI(peak.energy - half, peak.energy + half, `${peak.energy.toFixed(1)} keV`);
        }
        this.elements.peaksTbody.querySelectorAll('.peak-row').forEach((row) => {
            const on = Number(row.dataset.peakIndex) === this._selectedPeak;
            row.classList.toggle('selected', on);
            row.setAttribute('aria-pressed', String(on));
        });
    }

    /** The answer, above the chart: most likely isotope, how sure, and the numbers around it. */
    renderSummary(data) {
        const el = this.elements.summary;
        if (!el) return;
        const set = (id, text) => { const n = document.getElementById(id); if (n) n.textContent = text; };
        const line = summarizeIdentification({ isotopes: data.isotopes, isCalibrated: data.is_calibrated });
        this._lineSummary = line;
        el.hidden = false;
        el.dataset.state = line.state;
        const conf = document.getElementById('rs-conf');
        const bar = document.getElementById('rs-bar-fill');
        if (line.state === 'found') {
            set('rs-name', line.name);
            set('rs-conf', `${line.label} \u00b7 ${line.confidence.toFixed(0)}%`);
            conf.dataset.level = line.label.toLowerCase();
            conf.hidden = false;
            bar.style.width = `${Math.min(100, line.confidence)}%`;
            bar.parentElement.dataset.level = line.label.toLowerCase();
            bar.parentElement.hidden = false;
            set('rs-note', line.also.length
                ? 'Also possible: ' + line.also.map((a) => `${a.name} (${a.confidence.toFixed(0)}%)`).join(', ')
                : 'No other isotope matched.');
        } else {
            const text = line.state === 'uncalibrated' ? 'No energy calibration' : 'No isotope identified';
            set('rs-name', text);
            conf.hidden = true;
            bar.parentElement.hidden = true;
            set('rs-note', line.state === 'uncalibrated'
                ? 'Peaks are shown in channels; calibrate the spectrum to identify isotopes.'
                : 'No known gamma lines matched the detected peaks. A longer acquisition or a stronger source helps.');
        }
        document.getElementById('spectrumChart')?.setAttribute('aria-label', describeSpectrum({
            counts: data.counts, peaks: data.peaks, metadata: data.metadata, isCalibrated: data.is_calibrated,
        }));
        const facts = summaryFacts({ counts: data.counts, metadata: data.metadata, peaks: data.peaks });
        set('rs-peaks', String(facts.peaks));
        set('rs-counts', formatCount(facts.total));
        set('rs-rate', facts.rate === null ? '--' : `${facts.rate >= 100 ? facts.rate.toFixed(0) : facts.rate.toFixed(1)} cps`);
        set('rs-live', formatDuration(facts.live));
        const warnings = data.data_quality?.warnings?.length || 0;
        const flag = document.getElementById('rs-flag');
        if (flag) {
            flag.hidden = warnings === 0;
            flag.textContent = warnings ? `${warnings} data-quality warning${warnings > 1 ? 's' : ''}` : '';
        }
    }

    /**
     * The neural-net answer: status idle | running | done | error, with predictions and the spectrum signature it was
     * computed on. Ignored if the spectrum was replaced while it ran.
     */
    setAiState(state) {
        if (state.signature && spectrumChange(state.signature, this._sig) === 'new') return;
        this.aiState = state;
        this.renderAiResults();
    }

    renderAiResults() {
        const list = document.getElementById('ml-isotopes-list');
        const state = this.aiState || { status: 'idle' };
        const stale = state.status === 'done' && state.signature && state.signature.total !== this._sig?.total;
        if (list) {
            const colors = this.getThemeColors();
            const note = (text) => `<p class="ai-note">${text}</p>`;
            if (state.status === 'running') {
                list.innerHTML = note('Running AI identification (the first run trains the model, about 10-30 s)\u2026');
            } else if (state.status === 'error') {
                list.innerHTML = `<p class="ai-note ai-error"><img src="/static/icons/error.svg" class="icon" style="width: 14px; height: 14px;"> ${escapeHtml(state.error)}</p>`;
            } else if (state.status === 'done' && state.predictions?.length) {
                const quality = { good: 'High confidence', moderate: 'Moderate confidence', low_confidence: 'Low confidence', no_match: 'No match' }[state.quality] || '';
                list.innerHTML = (stale ? note('The spectrum has grown since this ran. Run it again for an up-to-date answer.') : '')
                    + (quality ? `<div class="ai-quality" data-quality="${state.quality}">${quality}</div>` : '')
                    + state.predictions.map((pred) => {
                        const c = pred.confidence;
                        const color = c > 70 ? colors.confidenceHigh : c > 40 ? colors.confidenceMedium : colors.confidenceLow;
                        return `
                            <div class="ai-pred${pred.suppressed ? ' suppressed' : ''}${stale ? ' stale' : ''}" style="--ai-color: ${color};">
                                <div class="ai-pred-head"><strong>${pred.isotope}</strong>${pred.suppressed ? '<span class="ai-sup">suppressed</span>' : ''}
                                    <span class="ai-pred-level">${confidenceLabel(c)}</span></div>
                                <div class="ai-pred-row"><div class="confidence-track"><div class="ai-pred-fill" style="width: ${Math.min(c, 100)}%;"></div></div>
                                    <span class="ai-pred-pct">${c.toFixed(1)}%</span></div>
                                <div class="ai-pred-method">${pred.method || ''}</div>
                            </div>`;
                    }).join('');
            } else if (state.status === 'done') {
                list.innerHTML = note('No AI predictions for this spectrum.');
            } else {
                list.innerHTML = note('Not run yet. Click <b>AI Identify</b> for a second opinion from a neural network.');
            }
        }
        this._renderAiSummary(state, stale);
    }

    _renderAiSummary(state, stale) {
        const text = document.getElementById('rs-ai-text');
        const verdict = document.getElementById('rs-ai-verdict');
        const btn = document.getElementById('btn-rs-ai');
        if (!text || !verdict) return;
        verdict.hidden = true;
        verdict.dataset.state = '';
        btn.disabled = state.status === 'running';
        btn.textContent = state.status === 'done' ? 'Run again' : 'Run AI check';
        if (state.status === 'running') {
            text.textContent = 'Running\u2026';
        } else if (state.status === 'error') {
            text.textContent = 'Failed';
        } else if (state.status === 'done' && state.predictions?.length) {
            const top = state.predictions.find((p) => !p.suppressed) || state.predictions[0];
            text.textContent = `${top.isotope} (${top.confidence.toFixed(0)}%)${stale ? ', earlier spectrum' : ''}`;
            const cmp = compareIdentifications(this._lineSummary, state.predictions);
            const words = { agree: 'agrees with line matching', partial: 'partly agrees', differ: 'differs: check the peaks' };
            if (words[cmp.state] && !stale) {
                verdict.textContent = words[cmp.state];
                verdict.dataset.state = cmp.state;
                verdict.hidden = false;
            }
        } else if (state.status === 'done') {
            text.textContent = 'No answer';
        } else {
            text.textContent = 'Not run';
        }
    }

    renderIsotopes(isotopes) {
        const legacyList = document.getElementById('legacy-isotopes-list');

        if (isotopes && isotopes.length > 0) {
            this.elements.isotopesContainer.style.display = 'block';

            // Store isotopes for click handlers
            window._isotopeData = isotopes;

            // Get theme-aware colors
            const colors = this.getThemeColors();

            // Render legacy peak-matching results with confidence bars and factor breakdown
            legacyList.innerHTML = isotopes.map((iso, idx) => {
                const confidence = iso.confidence;
                const barColor = confidence > 70 ? colors.confidenceHigh :
                    confidence > 40 ? colors.confidenceMedium : colors.confidenceLow;
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
                                " title="Highlight peaks on chart"><img src="/static/icons/pin.svg" class="icon" style="width: 12px; height: 12px;"></button>
                                <span style="font-size: 0.75rem; color: ${barColor}; font-weight: 600; cursor: ${iso.confidence_factors ? 'pointer' : 'default'};" 
                                      ${iso.confidence_factors ? 'onclick="event.stopPropagation(); this.parentElement.parentElement.parentElement.querySelector(\'.confidence-factors\').style.display = this.parentElement.parentElement.parentElement.querySelector(\'.confidence-factors\').style.display === \'none\' ? \'block\' : \'none\'"' : ''}>
                                    ${confidenceLabel} ${iso.confidence_factors ? '<img src="/static/icons/chevron-down.svg" class="icon" style="width: 10px; height: 10px; vertical-align: middle;">' : ''}
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
                            <img src="/static/icons/atom.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> Est. Activity: ${iso.activity_estimate.readable}
                        </div>
                        ` : ''}
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                            ${iso.role === 'series'
                                ? `<span title="${iso.isotope} has no gamma line of its own. This is the verdict on its decay series, at the confidence of the best member that does: ${iso.series_basis}.">Series verdict, from ${iso.series_basis}${iso.total_lines ? ` &middot; ${iso.matches}/${iso.total_lines} lines of its members matched` : ''}</span>`
                                : `<span>${iso.matches}/${iso.total_lines} peaks matched</span>`}
                            <a href="${nndcUrl}" target="_blank" rel="noopener" style="color: #3b82f6; text-decoration: none; font-size: 0.7rem;" title="View on NNDC NuDat" onclick="event.stopPropagation();"><img src="/static/icons/book.svg" class="icon" style="width: 12px; height: 12px; vertical-align: middle;"> NNDC</a>
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
                    btn.innerHTML = '<img src="/static/icons/pin.svg" class="icon" style="width: 12px; height: 12px;">';
                } else {
                    // Select
                    window._selectedIsotopes.add(isoName);
                    const colorIdx = (window._selectedIsotopes.size - 1) % colors.length;
                    const color = colors[colorIdx];

                    window.chartManager.addIsotopeHighlight(isoName, iso.matched_peaks, iso.expected_peaks, color);

                    btn.style.background = color + '30';
                    btn.style.borderColor = color;
                    btn.innerHTML = '<img src="/static/icons/check.svg" class="icon" style="width: 12px; height: 12px;">';
                }
            });
        });
    }


    renderDecayChains(chains) {
        if (chains && chains.length > 0) {
            this.elements.decayChainsContainer.style.display = 'block';

            // Get theme-aware colors
            const colors = this.getThemeColors();

            this.elements.decayChainsList.innerHTML = chains.map(chain => {
                const confidenceClass = chain.confidence_level.toLowerCase() + '-confidence';
                const confidenceBadge = chain.confidence_level === 'HIGH' ? `<span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.confidenceHigh};"></span>` :
                    chain.confidence_level === 'MEDIUM' ? `<span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.confidenceMedium};"></span>` : `<span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.confidenceLow};"></span>`;

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
                const memberStatus = chain.member_status;   // decided on the server, from the isotope table and the chain's lines (see _attach_member_status)
                const legacyDetected = new Set(Object.keys(chain.detected_members));   // a chain saved before member_status existed

                const chainGraphic = chainMembers.map((member, idx) => {
                    const entry = memberStatus ? memberStatus[member] : null;
                    const isDetected = memberStatus ? entry?.state === 'detected' : legacyDetected.has(member);
                    const isStable = idx === chainMembers.length - 1;

                    // Get half-life and branching from sequence data
                    const seqInfo = chainSequence[idx] || {};
                    const halfLife = seqInfo.half_life || '';

                    const inferredFrom = entry?.state === 'inferred' ? entry.from : null;
                    const statusClass = isDetected ? 'detected' : (inferredFrom ? 'inferred' : (isStable ? 'stable' : ''));

                    // Between two entries: an arrow (with the branching share when the decay has alternatives), or, when the next
                    // entry is the OTHER product of the same parent (Bi-212 -> Po-212 or Tl-208), "or" and its share
                    let arrow = '';
                    if (idx < chainMembers.length - 1) {
                        const link = chainLink(chainSequence, idx);
                        const pct = link.percent === null ? '' : link.percent.toFixed(1) + '%';
                        if (link.kind === 'branch') {
                            arrow = `<div title="${chainMembers[idx + 1]} is an alternative decay product of ${link.from} (${pct}), not a later step after ${member}" style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 0.35rem; min-width: 24px; cursor: help;">
                                <span style="font-size: 0.7rem; color: #f59e0b; font-weight: bold;">or</span>
                                ${pct ? `<span style="font-size: 0.6rem; color: #f59e0b;">${pct}</span>` : ''}
                            </div>`;
                        } else {
                            const branchLabel = link.percent !== null
                                ? `<div title="Branching Ratio: Probability of this decay mode" style="display:flex; flex-direction:column; align-items:center; cursor: help;">
                                     <span style="font-size: 0.5rem; color: var(--text-secondary); line-height: 1;">BRANCH</span>
                                     <span style="font-size: 0.65rem; color: #f59e0b; font-weight:bold;">${pct}</span>
                                   </div>`
                                : '';
                            arrow = `<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-secondary); font-size: 1.2rem; padding: 0 0.25rem; min-width: 24px;">
                                ${branchLabel}
                                <img src="/static/icons/arrow-right.svg" class="icon" style="width: 16px; height: 16px;">
                            </div>`;
                        }
                    }

                    return `
                        <div style="display: flex; align-items: center;">
                            <div class="decay-step-box ${statusClass}"${inferredFrom ? ` title="${member} has no gamma line of its own and was not identified. It is inferred because ${inferredFrom}, which it feeds, was detected (assumes the series was not chemically split)."` : (isDetected && entry?.source ? ` title="${entry.matches}/${entry.total_lines} gamma lines matched (${entry.source})"` : '')}>
                                <div style="font-weight: ${isDetected ? '700' : '500'}; font-size: 0.85rem;">
                                    ${member}
                                </div>
                                ${halfLife ? `<div style="font-size: 0.55rem; color: var(--text-secondary); margin-top: 1px;">${halfLife}</div>` : ''}
                                ${isDetected ? `<div style="font-size: 0.65rem; margin-top: 2px;"><img src="/static/icons/check.svg" class="icon" style="width: 10px; height: 10px; vertical-align: middle;"> DETECTED${entry?.total_lines ? ` ${entry.matches}/${entry.total_lines}` : ''}</div>` : ''}
                                ${inferredFrom ? '<div style="font-size: 0.65rem; margin-top: 2px;">INFERRED</div>' : ''}
                                ${isStable ? '<div style="font-size: 0.65rem; margin-top: 2px;">STABLE</div>' : ''}
                            </div>
                            ${arrow}
                        </div>
                    `;
                }).join('');

                return `
                    <div class="chain-card" style="border-left: 4px solid ${chain.confidence_level === 'HIGH' ? colors.confidenceHigh : colors.confidenceMedium};">
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
                                <span><span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.detected}; vertical-align: middle;"></span> Detected</span>
                                ${Object.values(memberStatus || {}).some(m => m.state === 'inferred') ? `<span><span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; border: 2px dotted ${colors.detected}; vertical-align: middle; box-sizing: border-box;"></span> Inferred (not measured: implied by a detected member it feeds)</span>` : ''}
                                <span><span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.stable}; vertical-align: middle;"></span> Stable End Product</span>
                                <span><span class="status-dot" style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: ${colors.undetected}; vertical-align: middle;"></span> Not Detected</span>
                            </div>
                        </div>
                        
                        ${chain.equilibrium_status && chain.equilibrium_status.in_equilibrium !== null ? `
                        <div style="margin: 0.5rem 0; padding: 0.5rem; background: ${chain.equilibrium_status.in_equilibrium ? colors.detectedBg : 'rgba(245, 158, 11, 0.1)'}; border-radius: 6px; font-size: 0.8rem;">
                            <span style="color: ${chain.equilibrium_status.in_equilibrium ? colors.detected : colors.confidenceMedium}; font-weight: 600;">
                                ${chain.equilibrium_status.in_equilibrium ? '<img src="/static/icons/balance.svg" class="icon" style="width: 14px; height: 14px; margin-right: 4px;"> SECULAR EQUILIBRIUM' : '<img src="/static/icons/warning.svg" class="icon" style="width: 14px; height: 14px; margin-right: 4px; filter: invert(1);"> DISEQUILIBRIUM'}
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
                            ${chain.applications && chain.applications.length > 0 ? `
                            <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                                <strong>Likely Sources:</strong>
                                <ul style="margin: 0.5rem 0 0 1.5rem; padding: 0;">
                                    ${chain.applications.map(app => `<li style="margin: 0.25rem 0;">${app}</li>`).join('')}
                                </ul>
                            </div>` : ''}
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

    /** @param {number|null} doseRate the AlphaHound's dose rate in uRem/h; shown in the unit chosen in Settings */
    updateDoseDisplay(doseRate) {
        if (!this.elements.doseDisplay) return;
        const unit = resolveUnit(getDosePref(), 'uRem');
        if (doseRate !== null && doseRate !== undefined) {
            this.elements.doseDisplay.textContent = formatDoseRate(doseRate / UREM_PER_USV, unit).text;
        } else {
            this.elements.doseDisplay.textContent = formatDoseRate(null, unit).text;
        }
    }

    updateTemperature(temp) {
        const tempDisplay = document.getElementById('temp-display');
        if (tempDisplay) {
            if (temp !== null && temp !== undefined) {
                tempDisplay.innerHTML = `<img src="/static/icons/thermometer.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle; margin-right: 2px;"> ${temp.toFixed(1)}°C`;
                tempDisplay.style.display = 'inline';
            } else {
                tempDisplay.style.display = 'none';
            }
        }
    }

    updateConnectionStatus(status) {
        if (!this.elements.doseDisplay) return;
        if (status === 'connected') {
            this.elements.doseDisplay.textContent = formatDoseRate(null, resolveUnit(getDosePref(), 'uRem')).text;
        } else if (status === 'connecting') {
            this.elements.doseDisplay.textContent = 'Connecting...';
        } else {
            this.elements.doseDisplay.textContent = 'Disconnected';
        }
    }

    setDeviceConnected(isConnected) {
        // Connection row visibility - show connect UI when disconnected
        if (isConnected) {
            if (this.elements.portSelectParent) this.elements.portSelectParent.style.display = 'none';
            if (this.elements.btns.refresh) this.elements.btns.refresh.style.display = 'none';
            if (this.elements.btns.connect) this.elements.btns.connect.style.display = 'none';
            if (this.elements.btns.disconnect) this.elements.btns.disconnect.style.display = 'inline-block';
            if (this.elements.btns.row) this.elements.btns.row.classList.add('ah-connected');
        } else {
            if (this.elements.portSelectParent) this.elements.portSelectParent.style.display = 'flex';
            if (this.elements.btns.refresh) this.elements.btns.refresh.style.display = 'block';
            if (this.elements.btns.connect) this.elements.btns.connect.style.display = 'block';
            if (this.elements.btns.disconnect) this.elements.btns.disconnect.style.display = 'none';
            if (this.elements.btns.row) this.elements.btns.row.classList.remove('ah-connected');
        }
        // Note: Panel always visible, device_features.js handles greyed/enabled state
    }

    populatePorts(ports) {
        const select = document.getElementById('port-select');
        if (ports && ports.length > 0) {
            // "COM5 - Standard Serial over Bluetooth link (COM5)" is too long for a phone: shorten it, keep the rest as a tooltip
            const shorten = (d) => String(d || '')
                .replace(/\s*\(COM\d+\)\s*$/i, '')
                .replace(/Standard Serial over Bluetooth link/i, 'Bluetooth serial')
                .replace(/USB Serial Device/i, 'USB serial')
                .replace(/Intel\(R\) Active Management Technology - SOL/i, 'Intel AMT');
            const options = ports.map(p =>
                `<option value="${p.device}" title="${String(p.description || '').replace(/"/g, '&quot;')}">${p.device} \u00b7 ${shorten(p.description)}</option>`
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
