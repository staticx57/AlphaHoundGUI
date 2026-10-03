import { debug } from './log.js';
import { roundTicks, formatKeV } from './axis.js';
import { chartTheme, themeGlowPlugin } from './chart_theme.js';
export class AlphaHoundChart {
    constructor() {
        this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        this.chart = null;
        // Read primary color from theme CSS variable
        this.updateThemeColors();
        this.autoScale = true; // Default to auto-scale (zoom to data)
        this.decimationThreshold = 2048; // Decimate spectra larger than this
        this.isSyncing = false; // Unified guard for all chart updates and event reactions
        this.annotations = {}; // Master state for annotations (source of truth)
        this.labelOffsets = {}; // Track vertical offsets for label stacking { xValue: offset }
        this.userZoom = null;        // the energy window the user chose (scrubber, wheel, pan); kept across live updates
        this.preserveZoom = false;   // true while a live acquisition re-renders the same spectrum
        this._programmatic = false;  // true while our own code moves the axis (not a user action)
    }

    /**
     * Convert hex color to rgba with specified opacity
     */
    hexToRgba(hex, alpha = 1) {
        const h = hex.replace('#', '');
        const r = parseInt(h.substring(0, 2), 16);
        const g = parseInt(h.substring(2, 4), 16);
        const b = parseInt(h.substring(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    /**
     * Update theme-dependent colors from CSS variables
     * Call this when theme changes to refresh chart colors
     */
    updateThemeColors() {
        this.primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#38bdf8';

        // Update the existing chart: colours, and the theme's character (line weight, glow, grid style, font)
        if (this.chart && this.chart.data.datasets[0]) {
            const th = chartTheme();
            const ds = this.chart.data.datasets[0];
            const single = this.chart.data.datasets.length === 1;   // the comparison view keeps its own per-spectrum colours
            if (single) {
                ds.borderColor = this.primaryColor;
                ds.backgroundColor = this.hexToRgba(this.primaryColor, 0.1);
                ds.borderWidth = Math.max(1, th.lineWidth - 0.25);
                ds.stepped = th.stepped ? 'middle' : false;
            }
            const opts = this.chart.options;
            for (const axis of Object.values(opts.scales || {})) {
                if (axis.title) axis.title.color = th.textSecondary;
                if (axis.grid) { axis.grid.color = th.grid; axis.grid.borderDash = th.gridDash; }
                if (axis.ticks) { axis.ticks.color = th.textSecondary; axis.ticks.font = { family: th.font }; }
            }
            const pl = opts.plugins || {};
            if (pl.themeGlow) pl.themeGlow.blur = th.glow;
            if (pl.legend && pl.legend.labels) { pl.legend.labels.color = th.textSecondary; pl.legend.labels.font = { family: th.font }; }
            if (pl.tooltip) {
                Object.assign(pl.tooltip, {
                    backgroundColor: th.card, titleColor: th.text, bodyColor: th.text,
                    titleFont: { family: th.font }, bodyFont: { family: th.font }, borderColor: th.grid,
                });
            }
            this.chart.update('none'); // Update without animation
        }

        // Redraw zoom scrubber mini preview with new theme colors
        if (this.previewCanvas && this.fullCounts) {
            this.drawMiniPreview();
        }
    }

    /**
     * Deep clone an object to break Proxy links from Chart.js.
     */
    _clone(obj) {
        if (!obj || typeof obj !== 'object') return obj;
        try {
            return JSON.parse(JSON.stringify(obj));
        } catch (e) {
            const result = Array.isArray(obj) ? [] : {};
            for (const key in obj) {
                if (Object.prototype.hasOwnProperty.call(obj, key)) {
                    result[key] = (typeof obj[key] === 'object' && obj[key] !== null)
                        ? this._clone(obj[key])
                        : obj[key];
                }
            }
            return result;
        }
    }

    /**
     * Calculate vertical offset for labels to prevent overlapping.
     * @param {number} xValue - Energy value where label is placed
     * @param {number} proximityThreshold - Threshold in keV to consider labels "overlapping"
     * @returns {number} Y-offset in pixels
     */
    _getVerticalOffset(xValue, proximityThreshold = 50) {
        let maxOffset = 0;
        const keys = Object.keys(this.labelOffsets);

        for (const existingX of keys) {
            if (Math.abs(parseFloat(existingX) - xValue) < proximityThreshold) {
                maxOffset = Math.max(maxOffset, this.labelOffsets[existingX] + 32);
            }
        }

        this.labelOffsets[xValue] = maxOffset;
        debug(`[LabelStack] x=${xValue.toFixed(1)}, offset=${maxOffset}`);
        return maxOffset;
    }

    /**
     * Decimate large dataset to improve rendering performance.
     * Uses LTTB (Largest-Triangle-Three-Buckets) inspired downsampling.
     * @param {Array} data - Array of {x, y} points
     * @param {number} targetPoints - Target number of points
     * @returns {Array} Decimated data
     */
    decimateData(data, targetPoints = 1024) {
        if (data.length <= targetPoints) return data;

        const bucketSize = Math.floor(data.length / targetPoints);
        const result = [data[0]]; // Always include first point

        for (let i = 1; i < targetPoints - 1; i++) {
            const bucketStart = i * bucketSize;
            const bucketEnd = Math.min((i + 1) * bucketSize, data.length);

            // Find point with max Y value in bucket (preserve peaks)
            let maxY = -Infinity;
            let maxPoint = data[bucketStart];
            for (let j = bucketStart; j < bucketEnd; j++) {
                if (data[j].y > maxY) {
                    maxY = data[j].y;
                    maxPoint = data[j];
                }
            }
            result.push(maxPoint);
        }

        result.push(data[data.length - 1]); // Always include last point
        return result;
    }

    render(labels, dataPoints, peaks, scaleType = 'linear') {
        // Robustness: Try to get context if missing (e.g. if loaded before DOM)
        if (!this.ctx) {
            this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        }
        if (!this.ctx) return;

        // Safety: Check if Chart.js is loaded
        if (typeof Chart === 'undefined') {
            console.error('Chart.js not loaded');
            return;
        }

        // Validate inputs
        if (!Array.isArray(labels) || !Array.isArray(dataPoints)) {
            console.error('Invalid input to render:', { labels, dataPoints });
            return;
        }

        // Prepare data
        // In auto-scale view, channels below the detector threshold (noise pile) are not drawn,
        // leaving a clean margin between the y-axis and the data. Full Spectrum draws everything.
        const lowCut = (this.autoScale && typeof this.displayMinKeV === 'number') ? this.displayMinKeV : null;
        const chartData = labels.map((l, i) => ({
            x: l,
            y: (lowCut !== null && parseFloat(l) < lowCut) ? null : dataPoints[i]
        })); this.labelOffsets = {};
        const peakData = (peaks || []).map(p => ({ x: p.energy, y: p.counts || p.count || 0 }));

        // Get theme colors for peaks and chart line
        const styles = getComputedStyle(document.documentElement);
        const peakColor = styles.getPropertyValue('--chart-peak-color').trim() || '#ef4444';
        // Re-read primary color at render time to ensure theme-correct colors
        this.primaryColor = styles.getPropertyValue('--primary-color').trim() || '#38bdf8';

        // Auto-Scale / Zoom Logic
        const fullMaxEnergy = labels.length > 0 ? labels[labels.length - 1] : 3000;
        this.fullMaxEnergy = fullMaxEnergy;
        let maxEnergy = fullMaxEnergy;
        let maxY = (dataPoints.length > 0 ? Math.max(...dataPoints) : 100) * 1.15;

        if (this.autoScale) {
            // Primary: Peak-based zoom (show all detected peaks with 10% padding)
            if (peaks && peaks.length > 0) {
                const maxPeakEnergy = Math.max(...peaks.map(p => p.energy || 0));
                // 10% padding after rightmost peak
                maxEnergy = Math.min(maxPeakEnergy * 1.10, fullMaxEnergy);
            } else {
                // Fallback: Data-based (99.5% percentile) when no peaks detected
                const totalCounts = dataPoints.reduce((a, b) => a + b, 0);
                let cumulativeCounts = 0;
                let percentileIndex = dataPoints.length - 1;
                for (let i = dataPoints.length - 1; i >= 0; i--) {
                    cumulativeCounts += dataPoints[i];
                    if (cumulativeCounts >= totalCounts * 0.995) {
                        percentileIndex = i;
                        break;
                    }
                }
                maxEnergy = Math.min(parseFloat(labels[percentileIndex]) * 1.15, fullMaxEnergy);
            }

            // Ensure minimum zoom of 200 keV
            maxEnergy = Math.max(maxEnergy, 200);

            // Y-AXIS AUTO-SCALE: headroom over the visible range, ignoring channels below the
            // detector threshold (their noise pile would otherwise set the scale)
            const lowLimit = (typeof this.displayMinKeV === 'number') ? this.displayMinKeV : -Infinity;
            const visibleData = dataPoints.filter((_, i) => {
                const e = parseFloat(labels[i]);
                return e >= lowLimit && e <= maxEnergy;
            });
            const visibleMaxCount = visibleData.length ? Math.max(...visibleData) : Math.max(...dataPoints);
            maxY = visibleMaxCount * 1.15;
        }

        if (maxY <= 0) maxY = 100;

        // Calculate min energy (add left buffer for visual appeal, from git version)
        let minEnergy = 0;
        if (this.autoScale && labels.length > 0) {
            let firstNonZeroIndex = 0;
            for (let i = 0; i < dataPoints.length; i++) {
                if (dataPoints[i] > 0) {
                    firstNonZeroIndex = i;
                    break;
                }
            }
            const firstDataEnergy = parseFloat(labels[firstNonZeroIndex]);
            minEnergy = Math.max(0, firstDataEnergy - (maxEnergy * 0.05));
            // Start just below the detector's lower threshold when known (Full Spectrum shows all)
            // with a small margin so the first data does not sit on the y-axis
            if (typeof this.displayMinKeV === 'number') {
                const margin = Math.max(5, 0.03 * (maxEnergy - this.displayMinKeV));
                // may go slightly below 0 keV: negative tick labels are hidden (see x ticks callback)
                minEnergy = this.displayMinKeV - margin;
            }
        }

        if (this.chart) {
            // [STABILITY] Non-destructive update 
            this.chart.data.datasets[0].data = chartData;

            // Handle Peaks as Annotations (as done in git version, but theme-aware)
            // Clear old peak annotations from master state
            Object.keys(this.annotations).forEach(k => {
                if (k.startsWith('peak')) delete this.annotations[k];
            });

            if (peaks && peaks.length > 0) {
                peaks.slice(0, 15).forEach((peak, idx) => {
                    // Find closest chart data point to peak energy
                    let closestIdx = 0;
                    let closestDiff = Infinity;
                    for (let i = 0; i < chartData.length; i++) {
                        const diff = Math.abs(chartData[i].x - peak.energy);
                        if (diff < closestDiff) {
                            closestDiff = diff;
                            closestIdx = i;
                        }
                    }

                    // Find LOCAL MAXIMUM within ±10 channels of closest point
                    const searchRadius = 10;
                    let maxIdx = closestIdx;
                    let maxY = chartData[closestIdx]?.y || 0;
                    for (let i = Math.max(0, closestIdx - searchRadius); i < Math.min(chartData.length, closestIdx + searchRadius); i++) {
                        if (chartData[i].y > maxY) {
                            maxY = chartData[i].y;
                            maxIdx = i;
                        }
                    }

                    const actualX = chartData[maxIdx]?.x ?? peak.energy;
                    const actualY = chartData[maxIdx]?.y ?? (peak.counts || peak.count || 0);
                    debug(`[Peak ${idx}] peak.energy=${peak.energy.toFixed(1)}, peakX=${actualX.toFixed(1)}, peakY=${actualY.toFixed(0)}`);

                    this.annotations[`peak${idx}`] = {
                        type: 'point',
                        xValue: actualX,
                        yValue: actualY,
                        backgroundColor: peakColor + '80',
                        radius: 6,
                        borderColor: peakColor,
                        borderWidth: 2,
                        drawTime: 'afterDatasetsDraw'
                    };
                });
            }

            // Scale Management: Detect mode switch to snap view
            const xScale = this.chart.options.scales.x;
            const yScale = this.chart.options.scales.y;
            const modeSwitched = this._lastRenderMode !== this.autoScale;
            debug(`[Chart] autoScale=${this.autoScale}, lastRenderMode=${this._lastRenderMode}, modeSwitched=${modeSwitched}, fullMaxEnergy=${fullMaxEnergy}`);
            this._lastRenderMode = this.autoScale;

            // Apply the scale type BEFORE zooming. zoomScale() triggers chart.update(), which
            // rebuilds chart.options, so assigning through a reference taken earlier is lost
            // (that is why Log/Linear appeared to do nothing).
            if (this.chart.options.scales.y.type !== scaleType) {
                this.chart.options.scales.y.type = scaleType;
                this.chart.update('none');
            }

            // A window the user chose (scrubber, wheel, pan) survives live updates of the same spectrum: without this every
            // refresh of a running acquisition snapped the chart back to the auto range while the scrubber showed the user's pick.
            const keepWindow = this.preserveZoom && this.userZoom && this.userZoom.axis === `${labels.length}:${fullMaxEnergy}`;
            this._programmatic = true;
            try {
                if (keepWindow) {
                    const lowLimit = (typeof this.displayMinKeV === 'number') ? this.displayMinKeV : -Infinity;
                    let top = 0;
                    for (let i = 0; i < dataPoints.length; i++) {
                        const e = parseFloat(labels[i]);
                        if (e >= Math.max(this.userZoom.min, lowLimit) && e <= this.userZoom.max && dataPoints[i] > top) top = dataPoints[i];
                    }
                    const yTop = (top > 0 ? top : 1) * 1.15;
                    this.chart.zoomScale('x', { min: this.userZoom.min, max: this.userZoom.max }, 'none');
                    this.chart.zoomScale('y', { min: scaleType === 'logarithmic' ? 1 : 0, max: yTop }, 'none');
                } else if (this.autoScale) {
                    debug(`[Chart] AutoScale: setting x=[${minEnergy}, ${maxEnergy}], y=[0, ${maxY}]`);
                    // Use zoom plugin's zoomScale for programmatic zoom
                    this.chart.zoomScale('x', { min: minEnergy, max: maxEnergy }, 'none');
                    this.chart.zoomScale('y', { min: scaleType === 'logarithmic' ? 1 : 0, max: maxY }, 'none');
                } else {
                    // Full spectrum mode - reset to full scale
                    const fullYMax = (dataPoints.length > 0 ? Math.max(...dataPoints) : 100) * 1.15;
                    debug(`[Chart] FullSpectrum: setting x=[0, ${fullMaxEnergy}], y=[0, ${fullYMax}]`);
                    this.chart.zoomScale('x', { min: 0, max: fullMaxEnergy }, 'none');
                    this.chart.zoomScale('y', { min: scaleType === 'logarithmic' ? 1 : 0, max: fullYMax }, 'none');
                }
            } finally {
                this._programmatic = false;
            }

            this.chart.options.scales.y.type = scaleType;
            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            this.chart.update('none');
        } else {
            // First time render - Initialize master annotations
            if (peaks && peaks.length > 0) {
                peaks.slice(0, 15).forEach((peak, idx) => {
                    // Find closest chart data point to peak energy
                    let closestIdx = 0;
                    let closestDiff = Infinity;
                    for (let i = 0; i < chartData.length; i++) {
                        const diff = Math.abs(chartData[i].x - peak.energy);
                        if (diff < closestDiff) {
                            closestDiff = diff;
                            closestIdx = i;
                        }
                    }

                    // Find LOCAL MAXIMUM within ±10 channels of closest point
                    const searchRadius = 10;
                    let maxIdx = closestIdx;
                    let maxY = chartData[closestIdx]?.y || 0;
                    for (let i = Math.max(0, closestIdx - searchRadius); i < Math.min(chartData.length, closestIdx + searchRadius); i++) {
                        if (chartData[i].y > maxY) {
                            maxY = chartData[i].y;
                            maxIdx = i;
                        }
                    }

                    const actualX = chartData[maxIdx]?.x ?? peak.energy;
                    const actualY = chartData[maxIdx]?.y ?? (peak.counts || peak.count || 0);

                    this.annotations[`peak${idx}`] = {
                        type: 'point',
                        xValue: actualX,
                        yValue: actualY,
                        backgroundColor: peakColor + '80',
                        radius: 6,
                        borderColor: peakColor,
                        borderWidth: 2,
                        drawTime: 'afterDatasetsDraw'
                    };
                });
            }

            const th = chartTheme();
            this.chart = new Chart(this.ctx, {
                type: 'line',
                plugins: [themeGlowPlugin],
                data: {
                    datasets: [
                        {
                            label: 'Counts',
                            data: chartData,
                            borderColor: this.primaryColor,
                            backgroundColor: this.hexToRgba(this.primaryColor, 0.1),
                            borderWidth: Math.max(1, th.lineWidth - 0.25),
                            pointRadius: 0,
                            fill: true,
                            stepped: th.stepped ? 'middle' : false,   // a blocky histogram in themes that draw that way
                            tension: 0 // Straight lines through data points (no bezier)
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                        axis: 'x'
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            min: minEnergy,
                            max: maxEnergy,
                            bounds: 'data',
                            title: { display: true, text: 'Energy (keV)', color: th.textSecondary },
                            grid: { color: th.grid, borderDash: th.gridDash },
                            ticks: {
                                color: th.textSecondary, font: { family: th.font }, includeBounds: false,
                                // The auto-scale margin can start the axis just below 0 keV; don't label it
                                callback: (value) => (value < 0 ? '' : Number(value).toLocaleString())
                            },
                            // Round positions (100, 200, 300 keV) instead of steps counted from the axis minimum
                            afterBuildTicks: (scale) => {
                                scale.ticks = roundTicks(scale.min, scale.max).map((value) => ({ value }));
                            }
                        },
                        y: {
                            type: scaleType,
                            min: scaleType === 'logarithmic' ? 1 : 0,
                            max: maxY,
                            beginAtZero: scaleType === 'linear',
                            title: { display: true, text: 'Counts', color: th.textSecondary },
                            grid: { color: th.grid, borderDash: th.gridDash },
                            ticks: { color: th.textSecondary, font: { family: th.font } }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        themeGlow: { blur: th.glow },
                        tooltip: {
                            backgroundColor: th.card,
                            titleColor: th.text,
                            bodyColor: th.text,
                            titleFont: { family: th.font },
                            bodyFont: { family: th.font },
                            borderColor: th.grid,
                            borderWidth: 1
                        },
                        zoom: {
                            zoom: {
                                wheel: { enabled: true },
                                pinch: { enabled: true },
                                mode: 'xy',
                                onZoom: () => this._userMoved()
                            },
                            pan: {
                                enabled: true,
                                mode: 'xy',
                                onPan: () => this._userMoved()
                            },
                            limits: {
                                y: { min: scaleType === 'logarithmic' ? 1 : 0 }
                            }
                        },
                        annotation: {
                            annotations: this._clone(this.annotations)
                        }
                    }
                }
            });
        }

        // Sync scrubber after render
        if (this.scrubberContainer && this.fullCounts) {
            this.updateScrubberFromChart();
        }
    }

    toggleAutoScale() {
        this.autoScale = !this.autoScale;
        this.userZoom = null;
        // Note: render() will call resetZoom on mode switch, no need to do it here
        return this.autoScale;
    }

    renderComparison(overlaySpectra, scaleType = 'linear') {
        if (!this.ctx) return;
        if (this.chart) this.chart.destroy();

        const datasets = overlaySpectra.map(spectrum => ({
            label: spectrum.name,
            data: spectrum.counts,
            borderColor: spectrum.color,
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            tension: 0.1
        }));

        const labels = overlaySpectra.length > 0 ? overlaySpectra[0].energies : [];

        const th = chartTheme();
        this.chart = new Chart(this.ctx, {
            plugins: [themeGlowPlugin],
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: {
                        title: { display: true, text: 'Energy (keV)', color: th.textSecondary },
                        grid: { color: th.grid, borderDash: th.gridDash },
                        ticks: { color: th.textSecondary, font: { family: th.font } }
                    },
                    y: {
                        type: scaleType,
                        min: scaleType === 'logarithmic' ? 1 : 0,
                        beginAtZero: scaleType === 'linear',
                        title: { display: true, text: 'Counts', color: th.textSecondary },
                        grid: { color: th.grid, borderDash: th.gridDash },
                        ticks: { color: th.textSecondary, font: { family: th.font } }
                    }
                },
                plugins: {
                    legend: { display: true, labels: { color: th.textSecondary, font: { family: th.font } } },
                    themeGlow: { blur: th.glow },
                    tooltip: {
                        backgroundColor: th.card,
                        titleColor: th.text,
                        bodyColor: th.text,
                        titleFont: { family: th.font },
                        bodyFont: { family: th.font },
                        borderColor: th.grid,
                        borderWidth: 1
                    },
                    annotation: { annotations: {} },
                    zoom: {
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'xy',
                            onZoom: () => this._userMoved()
                        },
                        pan: {
                            enabled: true,
                            mode: 'xy',
                            onPan: () => this._userMoved()
                        },
                        limits: {
                            y: { min: 0 }
                        }
                    }
                }
            }
        });

        // Sync scrubber after comparison render
        if (this.scrubberContainer && this.fullCounts) {
            this.updateScrubberFromChart();
        }
    }

    getScaleType() {
        return (this.chart && this.chart.options.scales.y.type) ? this.chart.options.scales.y.type : 'linear';
    }

    resetZoom() {
        this.userZoom = null;
        if (this.chart) {
            this.autoScale = false;
            this._lastRenderMode = false;
            this.chart.resetZoom();

            // Re-apply full spectrum limits manually to ensure they stick
            const fullMaxX = this.fullMaxEnergy || 3000;

            // Recalculate Y-axis max from CURRENT chart data
            const chartData = this.chart.data.datasets[0]?.data || [];
            const currentMaxY = chartData.length > 0
                ? Math.max(...chartData.map(p => p.y)) * 1.15
                : 100;

            this.chart.options.scales.x.min = 0;
            this.chart.options.scales.x.max = fullMaxX;
            this.chart.options.scales.y.max = currentMaxY;

            // Notify UI via button state if possible (main.js handles the button usually)
            const btn = document.getElementById('btn-auto-scale');
            if (btn) {
                btn.classList.remove('active');
                btn.textContent = 'Full Spectrum';
            }

            this.chart.update();
            this.updateScrubberFromChart();
        }
    }

    /**
     * Highlight an ROI region on the chart with subtle overlay.
     * @param {number} startEnergy - Start of ROI window (keV)
     * @param {number} endEnergy - End of ROI window (keV)
     * @param {string} [label] - Optional label for the ROI
     */
    highlightROI(startEnergy, endEnergy, label = 'ROI') {
        if (!this.chart) {
            console.warn('Chart not initialized');
            return;
        }
        if (this.isSyncing) return;
        this.isSyncing = true;
        try {
            // Check if annotation plugin is available
            if (!this.chart.options.plugins.annotation) {
                console.error('Annotation plugin not initialized');
                return;
            }

            // Ensure annotations object exists
            if (!this.chart.options.plugins.annotation.annotations) {
                this.chart.options.plugins.annotation.annotations = {};
            }

            // Get theme color
            const styles = getComputedStyle(document.documentElement);
            const annotationColor = styles.getPropertyValue('--chart-annotation-color').trim() || '#f59e0b';

            // Clear any existing ROI highlights from master state
            delete this.annotations.roiHighlight;
            delete this.annotations.roiLineStart;
            delete this.annotations.roiLineEnd;

            // Add subtle background box to master
            this.annotations.roiHighlight = {
                type: 'box',
                xMin: startEnergy,
                xMax: endEnergy,
                backgroundColor: annotationColor + '14',  // Very subtle (8% opacity)
                borderColor: 'transparent',
                drawTime: 'beforeDatasetsDraw',
                label: {
                    display: true,
                    content: label,
                    position: { x: 'center', y: 'end' },  // Bottom center
                    backgroundColor: annotationColor + 'E6',  // 90% opacity
                    color: '#fff',
                    font: { size: 10, weight: 'bold' },
                    padding: { top: 2, bottom: 2, left: 6, right: 6 },
                    borderRadius: 3
                }
            };

            // Add vertical line at start of ROI to master
            this.annotations.roiLineStart = {
                type: 'line',
                xMin: startEnergy,
                xMax: startEnergy,
                borderColor: annotationColor + 'CC',  // 80% opacity
                borderWidth: 2,
                borderDash: [4, 4],
                drawTime: 'afterDatasetsDraw'
            };

            // Add vertical line at end of ROI to master
            this.annotations.roiLineEnd = {
                type: 'line',
                xMin: endEnergy,
                xMax: endEnergy,
                borderColor: annotationColor + 'CC',  // 80% opacity
                borderWidth: 2,
                borderDash: [4, 4],
                drawTime: 'afterDatasetsDraw'
            };

            // Sync chart configuration with cloned master state
            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);

            // Force full chart update (no animation to prevent recursion)
            this.chart.update('none');
            debug(`✓ ROI highlighted: ${startEnergy}-${endEnergy} keV`);
        } catch (err) {
            console.error('Error highlighting ROI:', err);
        } finally {
            this.isSyncing = false;
        }
    }

    clearROIHighlight() {
        if (!this.chart || !this.chart.options.plugins.annotation?.annotations) return;
        if (this.isSyncing) return;

        this.isSyncing = true;
        try {
            delete this.annotations.roiHighlight;
            delete this.annotations.roiLineStart;
            delete this.annotations.roiLineEnd;

            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            this.chart.update('none');
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Highlight multiple ROI regions (e.g., for uranium ratio analysis).
     * @param {Array} regions - Array of {start, end, label, color} objects
     */
    highlightMultipleROI(regions) {
        if (!this.chart) return;
        if (this.isSyncing) return;

        this.isSyncing = true;
        try {
            // Remove existing ROI highlights from master
            Object.keys(this.annotations).filter(k => k.startsWith('roi_')).forEach(k => delete this.annotations[k]);

            // Add new ones to master
            regions.forEach((region, idx) => {
                this.annotations[`roi_${idx}`] = {
                    type: 'box',
                    xMin: region.start,
                    xMax: region.end,
                    backgroundColor: region.color || 'rgba(249, 115, 22, 0.25)',
                    borderColor: region.borderColor || 'rgba(249, 115, 22, 0.9)',
                    borderWidth: 2,
                    label: {
                        display: !!region.label,
                        content: region.label || '',
                        position: 'start',
                        color: region.labelColor || '#f97316',
                        font: { size: 10, weight: 'bold' }
                    }
                };
            });

            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            this.chart.update('none');
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Highlight XRF peaks on the chart with vertical lines.
     * @param {Array} peaks - Array of {energy, element, shell} objects
     * @param {string} color - Color for the lines (optional, defaults to theme's secondary color)
     * @param {boolean} skipUpdate - Whether to skip the chart update call
     */
    highlightXRFPeaks(peaks, color = null, skipUpdate = false) {
        // Guard against recursion
        if (this.isSyncing) {
            console.warn('[XRF Highlight] Blocked recursive call');
            return;
        }

        // Get themed color from CSS variable or use fallback
        const styles = getComputedStyle(document.documentElement);
        const themedColor = color || styles.getPropertyValue('--secondary-color').trim() || 'rgba(129, 140, 248, 0.9)';

        debug('[XRF Highlight] Called with peaks:', peaks);

        if (!this.chart) {
            console.warn('[XRF Highlight] Chart not initialized');
            return;
        }

        this.isSyncing = true;
        try {
            // Reset label offsets for fresh stacking calculation
            this.labelOffsets = {};

            // 1. Remove existing XRF highlights from master
            Object.keys(this.annotations).filter(k => k.startsWith('xrf_')).forEach(k => delete this.annotations[k]);

            // 2. Add new ones to master
            const styles = getComputedStyle(document.documentElement);
            const xrfColor = styles.getPropertyValue('--chart-xrf-color').trim() || '#8b5cf6';
            const themedColor = xrfColor; // Assuming themedColor logic exists or use standard

            peaks.forEach((peak, idx) => {
                const en = peak.energy;
                const safeName = (peak.element || 'X').replace(/[^a-zA-Z0-9]/g, '_');
                const yOffset = this._getVerticalOffset(en);

                this.annotations[`xrf_${safeName}_${idx}`] = {
                    type: 'line',
                    xMin: en,
                    xMax: en,
                    borderColor: themedColor,
                    borderWidth: 2,
                    borderDash: [6, 3],
                    drawTime: 'afterDatasetsDraw',
                    label: {
                        display: true,
                        content: `${peak.element || ''} ${peak.shell || ''}`,
                        position: 'end',
                        yAdjust: yOffset, // STACKING (positive = downward from top)
                        color: themedColor,
                        backgroundColor: 'rgba(0,0,0,0.7)',
                        font: { size: 9, weight: 'bold' },
                        padding: 3
                    }
                };
            });

            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            if (!skipUpdate) this.chart.update('none');
            debug(`✓ XRF peaks highlighted: ${peaks.length} lines`);
        } finally {
            this.isSyncing = false;
        }
    }

    clearXRFHighlights() {
        if (!this.chart || this.isSyncing) return;
        this.isSyncing = true;
        try {
            Object.keys(this.annotations).filter(k => k.startsWith('xrf_')).forEach(k => delete this.annotations[k]);
            this.labelOffsets = {}; // Reset stacking on clear
            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            this.chart.update('none');
        } finally {
            this.isSyncing = false;
        }
    }

    // Removed unused highlightIsotopePeaks (replaced by addIsotopeHighlight)


    /**
     * Clear isotope peak highlighting from the chart.
     * @param {boolean} skipUpdate - If true, skip chart.update() (for batch operations)
     */
    clearIsotopeHighlights(skipUpdate = false) {
        if (!this.chart || this.isSyncing) return;
        this.isSyncing = true;
        try {
            Object.keys(this.annotations).filter(k => k.startsWith('iso_')).forEach(k => delete this.annotations[k]);
            this.labelOffsets = {}; // Reset stacking on clear
            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            if (!skipUpdate) this.chart.update('none');
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Add isotope peak highlighting for a single isotope (for multi-select support).
     * Does NOT clear existing highlights - adds to them.
     * @param {string} isotopeName - Name of the isotope (used as unique key prefix)
     * @param {Array} matchedPeaks - Array of {energy, isotope, intensity} objects (peaks actually detected)
     * @param {Array} expectedPeaks - Array of {energy, intensity} objects (all expected peaks)
     * @param {string} color - Color for this isotope's lines
     */
    addIsotopeHighlight(isotopeName, matchedPeaks, expectedPeaks, color, skipUpdate = false) {
        if (!this.chart || (this.isSyncing && !skipUpdate)) {
            console.warn('[Isotope Highlight] recursion blocked');
            return;
        }

        const wasSyncing = this.isSyncing;
        this.isSyncing = true;
        try {
            // NOTE: Do NOT reset labelOffsets here - this function ADDS to existing highlights
            // so we need to accumulate offsets for proper stacking

            // 1. Remove existing ones for this isotope from master
            const safeKey = isotopeName.replace(/[^a-zA-Z0-9]/g, '_');
            Object.keys(this.annotations).forEach(k => {
                if (k.startsWith(`iso_${safeKey}`)) delete this.annotations[k];
            });

            // 2. Add new ones to master
            const styles = getComputedStyle(document.documentElement);
            const isoColor = color || styles.getPropertyValue('--chart-isotope-color').trim() || '#3b82f6';

            // Safe color parsing for the unmatched line (opacity)
            let unmatchedColor;
            if (isoColor.startsWith('#')) {
                unmatchedColor = isoColor.length === 7 ? isoColor + '59' : isoColor;
            } else if (isoColor.startsWith('rgba')) {
                unmatchedColor = isoColor.replace(/[\d.]+\)$/, '0.35)');
            } else if (isoColor.startsWith('rgb')) {
                unmatchedColor = isoColor.replace(/\)$/, ', 0.35)').replace(/^rgb/, 'rgba');
            } else {
                unmatchedColor = isoColor + '80';
            }

            // Build set of matched energies
            const matchedEnergies = (matchedPeaks || []).map(p => p.observed || p.expected || p.energy).filter(Number.isFinite);

            // First: Add ALL expected peaks in lighter saturation (unmatched)
            if (expectedPeaks) {
                expectedPeaks.forEach((peak, idx) => {
                    const en = peak.energy || peak.expected;
                    if (!Number.isFinite(en)) return;
                    const isMatched = matchedEnergies.some(me => Math.abs(me - en) < 2.0);
                    if (isMatched) return;

                    this.annotations[`iso_${safeKey}_exp_${idx}`] = {
                        type: 'line',
                        xMin: en,
                        xMax: en,
                        borderColor: unmatchedColor,
                        borderWidth: 1.5,
                        borderDash: [6, 6],
                        drawTime: 'afterDatasetsDraw',
                        label: {
                            display: true,
                            content: `(${en.toFixed(0)})`,
                            position: 'end',
                            color: unmatchedColor,
                            backgroundColor: 'rgba(0,0,0,0.5)',
                            font: { size: 8, weight: 'normal' },
                            padding: 2
                        }
                    };
                });
            }

            // Second: Add MATCHED peaks in full color
            if (matchedPeaks) {
                matchedPeaks.forEach((peak, idx) => {
                    const en = peak.observed || peak.expected || peak.energy;
                    if (!Number.isFinite(en)) return;

                    const yOffset = this._getVerticalOffset(en);

                    this.annotations[`iso_${safeKey}_${idx}`] = {
                        type: 'line',
                        xMin: en,
                        xMax: en,
                        borderColor: isoColor,
                        borderWidth: 2,
                        borderDash: [4, 4],
                        drawTime: 'afterDatasetsDraw',
                        label: {
                            display: true,
                            content: `${isotopeName} ${en.toFixed(0)}`,
                            position: 'end',
                            yAdjust: yOffset, // STACKING (positive = downward from top)
                            color: isoColor,
                            backgroundColor: 'rgba(0,0,0,0.7)',
                            font: { size: 9, weight: 'bold' },
                            padding: 3
                        }
                    };
                });
            }

            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            if (!skipUpdate) this.chart.update('none');
            debug(`✓ Added isotope highlight: ${isotopeName}`);
        } finally {
            this.isSyncing = wasSyncing;
        }
    }

    removeIsotopeHighlight(isotopeName) {
        if (!this.chart || this.isSyncing) return;
        this.isSyncing = true;
        try {
            const safeKey = isotopeName.replace(/[^a-zA-Z0-9]/g, '_');
            Object.keys(this.annotations).forEach(k => {
                if (k.startsWith(`iso_${safeKey}`)) delete this.annotations[k];
            });
            this.chart.options.plugins.annotation.annotations = this._clone(this.annotations);
            this.chart.update('none');
            debug(`✓ Removed isotope highlight: ${isotopeName}`);
        } finally {
            this.isSyncing = false;
        }
    }


    /**
     * Initialize the zoom scrubber with event listeners.
     * Call this after first render.
     */
    initScrubber() {
        this.scrubberContainer = document.getElementById('zoom-scrubber');
        this.zoomMinSlider = document.getElementById('zoom-min');
        this.zoomMaxSlider = document.getElementById('zoom-max');
        this.selectionDiv = document.getElementById('scrubber-selection');
        this.minLabel = document.getElementById('zoom-min-label');
        this.maxLabel = document.getElementById('zoom-max-label');
        this.previewCanvas = document.getElementById('scrubber-preview');

        if (!this.scrubberContainer || !this.zoomMinSlider) return;

        // One handler per slider: keep the handles apart FIRST, then move the chart (the other order showed the
        // chart a position the handle was about to be pushed back from)
        const GAP = 2;   // percent
        this.zoomMinSlider.addEventListener('input', () => {
            const hi = parseFloat(this.zoomMaxSlider.value);
            if (parseFloat(this.zoomMinSlider.value) > hi - GAP) this.zoomMinSlider.value = hi - GAP;
            this.onScrubberChange();
        });
        this.zoomMaxSlider.addEventListener('input', () => {
            const lo = parseFloat(this.zoomMinSlider.value);
            if (parseFloat(this.zoomMaxSlider.value) < lo + GAP) this.zoomMaxSlider.value = lo + GAP;
            this.onScrubberChange();
        });

        debug('[Scrubber] Initialized');
    }

    /**
     * Show the scrubber and draw mini preview.
     * @param {Array} energies - Full energy array
     * @param {Array} counts - Full counts array
     */
    showScrubber(energies, counts) {
        if (!this.scrubberContainer) this.initScrubber();
        if (!this.scrubberContainer) return;

        this.fullEnergies = energies;
        this.fullCounts = counts;
        this.fullMaxEnergy = Math.max(...energies);

        this.scrubberContainer.style.display = 'block';
        this.drawMiniPreview();
        this.updateScrubberFromChart();
    }

    /**
     * Hide the scrubber.
     */
    hideScrubber() {
        if (this.scrubberContainer) {
            this.scrubberContainer.style.display = 'none';
        }
    }

    /**
     * Draw mini spectrum preview on scrubber canvas.
     *
     * The sliders and the chart both work in energy (a slider position is a fraction of the highest energy), so the preview
     * must too: drawing it by channel number put every peak in the wrong place whenever the calibration has an offset or a
     * quadratic term (a real Radiacode spectrum: the 236 keV peak at 9.4 % of the bar instead of 8.4 %), and the user
     * placed the handles on peaks that the chart then did not show. Each pixel column takes the largest count among the
     * channels that land in it, so narrow peaks survive the downsampling.
     */
    drawMiniPreview() {
        if (!this.previewCanvas || !this.fullCounts || !this.fullEnergies || !(this.fullMaxEnergy > 0)) return;

        const ctx = this.previewCanvas.getContext('2d');
        const width = this.previewCanvas.clientWidth;
        const height = this.previewCanvas.clientHeight;
        if (!(width > 0) || !(height > 0)) return;

        this.previewCanvas.width = width;
        this.previewCanvas.height = height;
        ctx.clearRect(0, 0, width, height);

        const energies = this.fullEnergies;
        const counts = this.fullCounts;
        // channels below the detector threshold are a noise pile that would flatten everything else
        const lowCut = (typeof this.displayMinKeV === 'number') ? this.displayMinKeV : -Infinity;
        const cols = new Array(width).fill(null);
        let maxCount = 0;
        for (let i = 0; i < counts.length; i++) {
            const e = Number(energies[i]);
            if (!(e >= lowCut) || !(e >= 0)) continue;
            const x = Math.min(width - 1, Math.floor((e / this.fullMaxEnergy) * width));
            const v = Number(counts[i]) || 0;
            if (cols[x] === null || v > cols[x]) cols[x] = v;
            if (v > maxCount) maxCount = v;
        }
        if (maxCount <= 0) maxCount = 1;

        // columns between two channels (fewer channels than pixels) are interpolated
        const known = [];
        for (let x = 0; x < width; x++) if (cols[x] !== null) known.push(x);
        if (!known.length) return;
        const yOf = (v) => height - (v / maxCount) * height * 0.9;

        const styles = getComputedStyle(document.documentElement);
        const lineColor = styles.getPropertyValue('--primary-color').trim() || '#38bdf8';
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        known.forEach((x, k) => {
            if (k === 0) ctx.moveTo(x, yOf(cols[x])); else ctx.lineTo(x, yOf(cols[x]));
        });
        ctx.stroke();

        // Fill with 12% opacity of line color
        ctx.lineTo(known[known.length - 1], height);
        ctx.lineTo(known[0], height);
        ctx.closePath();
        ctx.fillStyle = this.hexToRgba(lineColor, 0.12);
        ctx.fill();
    }

    /**
     * Handle scrubber slider changes and update chart zoom.
     */
    onScrubberChange() {
        if (!this.chart || !this.fullMaxEnergy || this.isSyncing) return;

        this.isSyncing = true;
        try {

            const minPercent = parseFloat(this.zoomMinSlider.value);
            const maxPercent = parseFloat(this.zoomMaxSlider.value);

            const minEnergy = (minPercent / 100) * this.fullMaxEnergy;
            const maxEnergy = (maxPercent / 100) * this.fullMaxEnergy;

            // Update chart scales
            this.chart.options.scales.x.min = minEnergy;
            this.chart.options.scales.x.max = maxEnergy;
            this.chart.update('none');
            this._rememberWindow(minEnergy, maxEnergy);

            // Update selection overlay
            this.updateSelectionOverlay(minPercent, maxPercent);

            // Update labels
            if (this.minLabel) this.minLabel.textContent = formatKeV(minEnergy);
            if (this.maxLabel) this.maxLabel.textContent = formatKeV(maxEnergy);
        } finally {
            this.isSyncing = false;
        }
    }

    /** Keep the window the user picked, tagged with the axis it applies to (a different spectrum drops it). */
    _rememberWindow(min, max) {
        const n = this.fullEnergies ? this.fullEnergies.length : 0;
        this.userZoom = { min, max, axis: `${n}:${this.fullMaxEnergy}` };
    }

    /** The user zoomed or panned the chart with the mouse / fingers. */
    _userMoved() {
        if (this._programmatic) return;
        if (this.chart && this.fullMaxEnergy) {
            const xs = this.chart.scales.x;
            this._rememberWindow(xs.min, xs.max);
        }
        this.updateScrubberFromChart();
    }

    /**
     * Update the selection overlay div position.
     */
    updateSelectionOverlay(minPercent, maxPercent) {
        if (!this.selectionDiv) return;
        this.selectionDiv.style.left = `${minPercent}%`;
        this.selectionDiv.style.width = `${maxPercent - minPercent}%`;
    }

    /**
     * Sync scrubber sliders from current chart zoom state.
     * Call this after wheel zoom or pan.
     */
    updateScrubberFromChart() {
        if (!this.chart || !this.fullMaxEnergy || !this.zoomMinSlider || this.isSyncing) return;

        this.isSyncing = true;
        try {

            const xScale = this.chart.options.scales.x;
            // the auto-scale margin can put the axis minimum slightly below 0 keV: the zoom bar starts at 0
            const minEnergy = Math.max(0, xScale.min || 0);
            const maxEnergy = xScale.max || this.fullMaxEnergy;

            const minPercent = (minEnergy / this.fullMaxEnergy) * 100;
            const maxPercent = (maxEnergy / this.fullMaxEnergy) * 100;

            this.zoomMinSlider.value = Math.max(0, minPercent);
            this.zoomMaxSlider.value = Math.min(100, maxPercent);

            this.updateSelectionOverlay(minPercent, maxPercent);

            if (this.minLabel) this.minLabel.textContent = formatKeV(minEnergy);
            if (this.maxLabel) this.maxLabel.textContent = formatKeV(maxEnergy);
        } finally {
            this.isSyncing = false;
        }
    }
}

/** A translucent version of a line colour for the area under it. */
function dimFill(lineColor) {
    return lineColor.startsWith('#') ? lineColor + '20' :
        lineColor.startsWith('rgba') ? lineColor.replace(/[\d.]+\)$/, '0.2)') :
            lineColor.replace(/\)$/, ', 0.2)').replace(/^rgb/, 'rgba');
}

export class DoseRateChart {
    /**
     * Create a DoseRateChart instance.
     * @param {HTMLCanvasElement|string} canvas - Canvas element or element ID
     * @param {object} options - Optional configuration
     * @param {string} options.label - Chart label
     * @param {string} options.color - Line color (defaults to theme accent)
     * @param {number} options.maxPoints - Maximum data points to display (default 300)
     */
    constructor(canvas, options = {}) {
        // Support both canvas element and ID string
        if (typeof canvas === 'string') {
            this.ctx = document.getElementById(canvas)?.getContext('2d');
        } else if (canvas instanceof HTMLCanvasElement) {
            this.ctx = canvas.getContext('2d');
        } else {
            // Fallback for backward compatibility
            this.ctx = document.getElementById('doseRateChart')?.getContext('2d');
        }

        this.options = options;
        this.chart = null;
        const maxPoints = options.maxPoints || 300;
        this.data = new Array(maxPoints).fill(null);
        this.labels = new Array(maxPoints).fill('');
        this.init();
    }

    init() {
        if (!this.ctx) return;
        if (typeof Chart === 'undefined') return; // Safety check

        // Get theme colors
        const styles = getComputedStyle(document.documentElement);
        // Use provided color preference, color variable name, or fallback to accent color
        let lineColor;
        if (this.options.colorVar) {
            lineColor = styles.getPropertyValue(this.options.colorVar).trim();
        }
        if (!lineColor) {
            lineColor = this.options.color || styles.getPropertyValue('--accent-color').trim() || '#10b981';
        }

        const th = chartTheme();
        this.chart = new Chart(this.ctx, {
            type: 'line',
            plugins: [themeGlowPlugin],
            data: {
                labels: this.labels,
                datasets: [{
                    data: this.data,
                    borderColor: lineColor,
                    borderWidth: this.options.lineWidth || th.lineWidth,
                    backgroundColor: dimFill(lineColor),
                    fill: 'start',
                    pointRadius: 0,
                    tension: Math.min(0.4, th.tension),
                    stepped: th.stepped ? 'before' : false,
                    spanGaps: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false, // Performance optimization
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    annotation: { display: false },
                    themeGlow: { blur: th.glow }
                },
                scales: {
                    x: { display: false }, // Tiny chart, no X axis
                    y: {
                        display: !this.options.hideAxis,
                        position: 'right',
                        ticks: {
                            color: styles.getPropertyValue('--text-secondary').trim() || '#64748b',
                            font: { size: 10, family: th.font },
                            maxTicksLimit: 3
                        },
                        grid: { display: false },
                        border: { display: false },
                        beginAtZero: true
                    }
                }
            }
        });
    }

    /** Re-read the theme (colour, line character, glow, font) after a theme switch. */
    refreshTheme() {
        if (!this.chart) return;
        const styles = getComputedStyle(document.documentElement);
        const th = chartTheme();
        let lineColor = this.options.colorVar ? styles.getPropertyValue(this.options.colorVar).trim() : '';
        if (!lineColor) lineColor = this.options.color || styles.getPropertyValue('--accent-color').trim() || '#10b981';
        const d = this.chart.data.datasets[0];
        d.borderColor = lineColor;
        d.backgroundColor = dimFill(lineColor);
        d.borderWidth = this.options.lineWidth || th.lineWidth;
        d.tension = Math.min(0.4, th.tension);
        d.stepped = th.stepped ? 'before' : false;
        this.chart.options.plugins.themeGlow.blur = th.glow;
        const y = this.chart.options.scales.y;
        y.ticks.color = styles.getPropertyValue('--text-secondary').trim() || '#64748b';
        y.ticks.font = { size: 10, family: th.font };
        this.chart.update('none');
    }

    /**
     * Add a new data point to the chart.
     * @param {number} value - The value to add
     */
    addDataPoint(value) {
        this.update(value);
    }

    update(doseRate) {
        if (!this.chart || this.isSyncing) return;
        this.isSyncing = true;

        try {
            // Push new value, shift old
            this.data.push(doseRate);
            this.data.shift();

            // Update chart data reference (Chart.js optimizes this)
            this.chart.data.datasets[0].data = this.data;

            // Update color dynamically if theme changes
            const styles = getComputedStyle(document.documentElement);
            let lineColor;
            if (this.options.colorVar) {
                lineColor = styles.getPropertyValue(this.options.colorVar).trim();
            }
            if (!lineColor) {
                lineColor = this.options.color || styles.getPropertyValue('--accent-color').trim() || '#10b981';
            }
            this.chart.data.datasets[0].borderColor = lineColor;
            this.chart.data.datasets[0].backgroundColor = lineColor.startsWith('#') ? lineColor + '20' :
                lineColor.startsWith('rgba') ? lineColor.replace(/[\d.]+\)$/, '0.2)') :
                    lineColor.replace(/\)$/, ', 0.2)').replace(/^rgb/, 'rgba');

            this.chart.update('none'); // Update without animation
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Destroy the chart instance.
     */
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
}

export const chartManager = new AlphaHoundChart();

// Expose globally for cross-module access (e.g., XRF highlighting from ui.js)
window.chartManager = chartManager;

