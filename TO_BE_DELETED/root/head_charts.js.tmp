export class AlphaHoundChart {
    constructor() {
        this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        this.chart = null;
        this.primaryColor = '#38bdf8'; // Default, should read from CSS
        this.autoScale = true; // Default to auto-scale (zoom to data)
        this.decimationThreshold = 2048; // Decimate spectra larger than this
        this.isSyncing = false; // Guard to prevent recursion between chart and scrubber
        this.isUpdatingAnnotations = false; // Guard to prevent recursion during annotation updates
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

        if (this.chart) this.chart.destroy();

        // ... rest of render ...

        // Convert to {x, y} format for linear x-axis
        let chartData = labels.map((energy, idx) => ({
            x: parseFloat(energy),
            y: dataPoints[idx]
        }));

        // Performance: Decimate large spectra (>2048 points) to improve rendering
        if (chartData.length > this.decimationThreshold) {
            console.log(`[Performance] Decimating ${chartData.length} points to 1024`);
            chartData = this.decimateData(chartData, 1024);
        }

        // Calculate max energy based on mode
        const fullMaxEnergy = Math.max(...labels.map(e => parseFloat(e)));
        let maxEnergy = fullMaxEnergy;
        let maxY = undefined; // Let Chart.js auto-scale by default

        if (this.autoScale) {
            // ==========================================
            // X-AXIS AUTO-SCALE (Aggressive Data Detection)
            // ==========================================
            const maxCount = Math.max(...dataPoints);
            const totalCounts = dataPoints.reduce((a, b) => a + b, 0);

            // Method 1: Find where tail contains 1.0% of data (start of signal from right)
            let cumulativeCounts = 0;
            let percentileIndex = dataPoints.length - 1;
            for (let i = dataPoints.length - 1; i >= 0; i--) {
                cumulativeCounts += dataPoints[i];
                if (cumulativeCounts >= totalCounts * 0.01) {
                    percentileIndex = i;
                    break;
                }
            }

            // Method 2: Find last SIGNIFICANT data (above noise threshold)
            // Increased threshold to avoid extending scale for single random counts
            // min 2 counts, or 1.5% of max
            const noiseThreshold = Math.max(maxCount * 0.015, 2);

            let lastSignificantIndex = 0;
            for (let i = dataPoints.length - 1; i >= 0; i--) {
                if (dataPoints[i] > noiseThreshold) {
                    lastSignificantIndex = i;
                    break;
                }
            }

            // Use the LARGER of the two (safe approach - show more data)
            const dataEndIndex = Math.max(percentileIndex, lastSignificantIndex);

            // Ensure we include at least a reasonable energy range
            const calculatedEnergy = parseFloat(labels[dataEndIndex]) * 1.1;

            // Minimum zoom: at least 200 keV or 5% of full range
            const minZoom = Math.max(200, fullMaxEnergy * 0.05);
            maxEnergy = Math.max(calculatedEnergy, minZoom);

            // Cap at full range
            maxEnergy = Math.min(maxEnergy, fullMaxEnergy);

            // ==========================================
            // Y-AXIS AUTO-SCALE 
            // ==========================================
            // Find max count in the visible range only
            const visibleEndIndex = labels.findIndex(e => parseFloat(e) > maxEnergy);
            const visibleData = visibleEndIndex > 0 ? dataPoints.slice(0, visibleEndIndex) : dataPoints;
            const visibleMaxCount = Math.max(...visibleData);

            // 15% headroom above visible maximum peak
            maxY = visibleMaxCount * 1.15;
        }


        // Get theme colors from CSS variables
        const styles = getComputedStyle(document.documentElement);
        const annotationColor = styles.getPropertyValue('--chart-annotation-color').trim() || '#f59e0b';

        // Annotations - use display_energy for chart alignment (snapped to local max)
        const annotations = {};
        if (peaks && peaks.length > 0) {
            peaks.slice(0, 10).forEach((peak, idx) => {
                // Use display_energy (local max of raw data) if available, else use energy
                const displayX = peak.display_energy || peak.energy;
                annotations[`peak${idx}`] = {
                    type: 'point',
                    xValue: displayX,
                    yValue: peak.counts,
                    backgroundColor: annotationColor + '80', // Add transparency
                    radius: 6,
                    borderColor: annotationColor,
                    borderWidth: 2
                };
            });
        }

        // Calculate min energy (add left buffer for visual appeal)
        let minEnergy = 0;
        if (this.autoScale && labels.length > 0) {
            // Find first non-zero data point
            let firstNonZeroIndex = 0;
            for (let i = 0; i < dataPoints.length; i++) {
                if (dataPoints[i] > 0) {
                    firstNonZeroIndex = i;
                    break;
                }
            }
            // Add 5% left buffer (but never go below 0)
            const firstDataEnergy = parseFloat(labels[firstNonZeroIndex]);
            minEnergy = Math.max(0, firstDataEnergy - (maxEnergy * 0.05));
        }

        this.chart = new Chart(this.ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: 'Counts',
                    data: chartData,
                    borderColor: this.primaryColor,
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: {
                        type: 'linear',
                        min: 0,  // Always start at 0 keV - no negative energy
                        max: maxEnergy,
                        bounds: 'data',  // Prevent Chart.js from adding padding
                        title: { display: true, text: 'Energy (keV)', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#94a3b8',
                            includeBounds: true
                        }
                    },
                    y: {
                        type: scaleType,
                        min: scaleType === 'logarithmic' ? 1 : 0,
                        max: maxY, // Apply intelligent max if autoscale is active
                        beginAtZero: scaleType === 'linear',
                        title: { display: true, text: 'Counts', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8' }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: 'rgba(148, 163, 184, 0.2)',
                        borderWidth: 1
                    },
                    zoom: {
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'xy',
                            onZoom: () => this.updateScrubberFromChart()
                        },
                        pan: {
                            enabled: true,
                            mode: 'xy',
                            onPan: () => this.updateScrubberFromChart()
                        }
                    },
                    annotation: { annotations: annotations }
                }
            }
        });

        // Sync scrubber after initial/new render
        if (this.scrubberContainer && this.fullCounts) {
            this.updateScrubberFromChart();
        }
    }

    toggleAutoScale() {
        this.autoScale = !this.autoScale;
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

        this.chart = new Chart(this.ctx, {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: {
                        title: { display: true, text: 'Energy (keV)', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8' }
                    },
                    y: {
                        type: scaleType,
                        min: scaleType === 'logarithmic' ? 1 : 0,
                        beginAtZero: scaleType === 'linear',
                        title: { display: true, text: 'Counts', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8' }
                    }
                },
                plugins: {
                    legend: { display: true, labels: { color: '#94a3b8' } },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: 'rgba(148, 163, 184, 0.2)',
                        borderWidth: 1
                    },
                    zoom: {
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'xy',
                            onZoom: () => this.updateScrubberFromChart()
                        },
                        pan: {
                            enabled: true,
                            mode: 'xy',
                            onPan: () => this.updateScrubberFromChart()
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
        if (this.chart) {
            this.chart.resetZoom();
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

            // Clear any existing ROI highlights
            delete this.chart.options.plugins.annotation.annotations.roiHighlight;
            delete this.chart.options.plugins.annotation.annotations.roiLineStart;
            delete this.chart.options.plugins.annotation.annotations.roiLineEnd;

            // Add subtle background box
            this.chart.options.plugins.annotation.annotations.roiHighlight = {
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

            // Add vertical line at start of ROI
            this.chart.options.plugins.annotation.annotations.roiLineStart = {
                type: 'line',
                xMin: startEnergy,
                xMax: startEnergy,
                borderColor: annotationColor + 'CC',  // 80% opacity
                borderWidth: 2,
                borderDash: [4, 4],
                drawTime: 'afterDatasetsDraw'
            };

            // Add vertical line at end of ROI
            this.chart.options.plugins.annotation.annotations.roiLineEnd = {
                type: 'line',
                xMin: endEnergy,
                xMax: endEnergy,
                borderColor: annotationColor + 'CC',  // 80% opacity
                borderWidth: 2,
                borderDash: [4, 4],
                drawTime: 'afterDatasetsDraw'
            };

            // Force full chart update (no animation to prevent recursion)
            this.chart.update('none');
            console.log(`✓ ROI highlighted: ${startEnergy}-${endEnergy} keV`);
        } catch (err) {
            console.error('Error highlighting ROI:', err);
        }
    }

    /**
     * Clear ROI highlighting from the chart.
     */
    clearROIHighlight() {
        if (!this.chart) return;

        const annotations = this.chart.options.plugins.annotation.annotations || {};
        delete annotations.roiHighlight;
        delete annotations.roiLineStart;
        delete annotations.roiLineEnd;

        this.chart.options.plugins.annotation.annotations = annotations;
        this.chart.update('none');
    }

    /**
     * Highlight multiple ROI regions (e.g., for uranium ratio analysis).
     * @param {Array} regions - Array of {start, end, label, color} objects
     */
    highlightMultipleROI(regions) {
        if (!this.chart) return;

        const annotations = this.chart.options.plugins.annotation.annotations || {};

        // Remove existing ROI highlights
        Object.keys(annotations).filter(k => k.startsWith('roi_')).forEach(k => delete annotations[k]);

        // Add new ones
        regions.forEach((region, idx) => {
            annotations[`roi_${idx}`] = {
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

        this.chart.options.plugins.annotation.annotations = annotations;
        this.chart.update('none');
    }

    /**
     * Highlight XRF peaks on the chart with vertical lines.
     * @param {Array} peaks - Array of {energy, element, shell} objects
     * @param {string} color - Color for the lines (optional, defaults to theme's secondary color)
     * @param {boolean} skipUpdate - Whether to skip the chart update call
     */
    highlightXRFPeaks(peaks, color = null, skipUpdate = false) {
        // Guard against recursion
        if (this.isUpdatingAnnotations) {
            console.warn('[XRF Highlight] Blocked recursive call');
            return;
        }

        // Get themed color from CSS variable or use fallback
        const styles = getComputedStyle(document.documentElement);
        const themedColor = color || styles.getPropertyValue('--secondary-color').trim() || 'rgba(129, 140, 248, 0.9)';

        console.log('[XRF Highlight] Called with peaks:', peaks);

        if (!this.chart) {
            console.warn('[XRF Highlight] Chart not initialized');
            return;
        }

        this.isUpdatingAnnotations = true;
        try {
            // Ensure annotation plugin is configured
            if (!this.chart.options.plugins.annotation) {
                this.chart.options.plugins.annotation = { annotations: {} };
            }
            if (!this.chart.options.plugins.annotation.annotations) {
                this.chart.options.plugins.annotation.annotations = {};
            }

            const annotations = this.chart.options.plugins.annotation.annotations;

            // Remove existing XRF highlights
            Object.keys(annotations).filter(k => k.startsWith('xrf_')).forEach(k => delete annotations[k]);

            // Helper: Check for existing isotope annotations at this energy
            const countExistingAnnotationsAtEnergy = (energy) => {
                let count = 0;
                Object.keys(annotations).forEach(key => {
                    if (key.startsWith('iso_')) {
                        const ann = annotations[key];
                        if (ann.xMin && Math.abs(ann.xMin - energy) < 2.0) {
                            count++;
                        }
                    }
                });
                return count;
            };

            // Add vertical line for each XRF peak
            peaks.forEach((peak, idx) => {
                if (!peak.energy) {
                    console.warn(`[XRF Highlight] Peak ${idx} missing energy:`, peak);
                    return;
                }

                // Check for overlapping isotope annotations and offset label upward
                const overlapCount = countExistingAnnotationsAtEnergy(peak.energy);
                const yAdjust = -(overlapCount * 16); // Offset upward by 16px per existing annotation

                annotations[`xrf_${idx}`] = {
                    type: 'line',
                    xMin: peak.energy,
                    xMax: peak.energy,
                    borderColor: themedColor,
                    borderWidth: 2,
                    borderDash: [6, 3],
                    drawTime: 'afterDatasetsDraw',
                    label: {
                        display: true,
                        content: `${peak.element} ${peak.shell}`,
                        position: 'start',
                        yAdjust: yAdjust,
                        color: themedColor,
                        backgroundColor: 'rgba(0,0,0,0.7)',
                        font: { size: 9, weight: 'bold' },
                        padding: 3
                    }
                };
                console.log(`[XRF Highlight] Added annotation xrf_${idx} at ${peak.energy} keV`);
            });

            if (!skipUpdate) {
                this.chart.update('none');
            }
            console.log(`✓ XRF peaks highlighted: ${peaks.length} lines`);
        } finally {
            this.isUpdatingAnnotations = false;
        }
    }


    /**
     * Clear XRF peak highlighting from the chart.
     */
    clearXRFHighlights() {
        if (!this.chart || this.isUpdatingAnnotations) return;

        this.isUpdatingAnnotations = true;
        try {
            const annotations = this.chart.options.plugins.annotation.annotations || {};
            Object.keys(annotations).filter(k => k.startsWith('xrf_')).forEach(k => delete annotations[k]);
            this.chart.options.plugins.annotation.annotations = annotations;
            this.chart.update('none');
        } finally {
            this.isUpdatingAnnotations = false;
        }
    }

    // Removed unused highlightIsotopePeaks (replaced by addIsotopeHighlight)


    /**
     * Clear isotope peak highlighting from the chart.
     * @param {boolean} skipUpdate - If true, skip chart.update() (for batch operations)
     */
    clearIsotopeHighlights(skipUpdate = false) {
        if (!this.chart || this.isUpdatingAnnotations) return;

        this.isUpdatingAnnotations = true;
        try {
            const annotations = this.chart.options.plugins.annotation.annotations || {};
            Object.keys(annotations).filter(k => k.startsWith('iso_')).forEach(k => delete annotations[k]);
            this.chart.options.plugins.annotation.annotations = annotations;
            if (!skipUpdate) {
                this.chart.update('none');
            }
        } finally {
            this.isUpdatingAnnotations = false;
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
        if (!this.chart || this.isUpdatingAnnotations) {
            console.warn('[Isotope Highlight] Chart not initialized or recursion blocked');
            return;
        }

        this.isUpdatingAnnotations = true;
        try {
            // Ensure annotation plugin is configured
            if (!this.chart.options.plugins.annotation) {
                this.chart.options.plugins.annotation = { annotations: {} };
            }
            if (!this.chart.options.plugins.annotation.annotations) {
                this.chart.options.plugins.annotation.annotations = {};
            }

            const annotations = this.chart.options.plugins.annotation.annotations;

            // Create safe key from isotope name (remove special chars)
            const safeKey = isotopeName.replace(/[^a-zA-Z0-9]/g, '_');

            // Fallback color if none provided
            const baseColor = color || '#f59e0b';

            // Lighter color for unmatched expected peaks (35% alpha)
            const unmatchedColor = baseColor.startsWith('#')
                ? baseColor + '59'
                : baseColor.replace(/[\d.]+\)$/, '0.35)');

            // Build set of matched energies for quick lookup with tolerance
            const matchedEnergies = [];
            if (matchedPeaks) {
                matchedPeaks.forEach(p => {
                    const en = p.observed || p.expected || p.energy;
                    if (en) matchedEnergies.push(en);
                });
            }

            // Helper: Check if there's already an annotation (isotope or XRF) at this energy
            // Returns the count of existing annotations at this energy (for stacking)
            const countExistingAnnotationsAtEnergy = (energy) => {
                let count = 0;
                Object.keys(annotations).forEach(key => {
                    // Check other isotope annotations (not from this isotope)
                    if (key.startsWith('iso_') && !key.startsWith(`iso_${safeKey}`)) {
                        const ann = annotations[key];
                        if (ann.xMin && Math.abs(ann.xMin - energy) < 2.0) {
                            count++;
                        }
                    }
                    // Also check XRF annotations
                    if (key.startsWith('xrf_')) {
                        const ann = annotations[key];
                        if (ann.xMin && Math.abs(ann.xMin - energy) < 2.0) {
                            count++;
                        }
                    }
                });
                return count;
            };

            // First: Add ALL expected peaks in lighter saturation (unmatched)
            if (expectedPeaks && expectedPeaks.length > 0) {
                expectedPeaks.forEach((peak, idx) => {
                    const en = peak.energy || peak.expected || peak.observed;
                    if (!en) return;

                    // Skip if this energy was matched (within 2 keV tolerance)
                    const isMatched = matchedEnergies.some(me => Math.abs(me - en) < 2.0);
                    if (isMatched) return;

                    // Check for overlapping annotations and offset label upward
                    const overlapCount = countExistingAnnotationsAtEnergy(en);
                    const yAdjust = -(overlapCount * 16); // Offset upward (negative) by 16px per existing annotation

                    annotations[`iso_${safeKey}_exp_${idx}`] = {
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
                            position: 'start',
                            yAdjust: yAdjust,
                            color: unmatchedColor,
                            backgroundColor: 'rgba(0,0,0,0.5)',
                            font: { size: 8, weight: 'normal' },
                            padding: 2
                        }
                    };
                });
            }

            // Second: Add MATCHED peaks in full color
            if (matchedPeaks && matchedPeaks.length > 0) {
                matchedPeaks.forEach((peak, idx) => {
                    const en = peak.observed || peak.expected || peak.energy;
                    if (!en) return;

                    const label = `${isotopeName} ${en.toFixed(0)}`;

                    // Check for overlapping annotations and offset label upward
                    const overlapCount = countExistingAnnotationsAtEnergy(en);
                    const yAdjust = -(overlapCount * 16); // Offset upward (negative) by 16px per existing annotation

                    annotations[`iso_${safeKey}_${idx}`] = {
                        type: 'line',
                        xMin: en,
                        xMax: en,
                        borderColor: baseColor,
                        borderWidth: 2,
                        borderDash: [4, 4],
                        drawTime: 'afterDatasetsDraw',
                        label: {
                            display: true,
                            content: label,
                            position: 'start',
                            yAdjust: yAdjust,
                            color: baseColor,
                            backgroundColor: 'rgba(0,0,0,0.7)',
                            font: { size: 9, weight: 'bold' },
                            padding: 3
                        }
                    };
                });
            }

            if (!skipUpdate) {
                this.chart.update('none');
            }
            console.log(`✓ Added isotope highlight: ${isotopeName} (${matchedPeaks?.length || 0} matched, ${expectedPeaks?.length || 0} expected)`);
        } finally {
            this.isUpdatingAnnotations = false;
        }
    }

    /**
     * Remove isotope peak highlighting for a single isotope.
     * @param {string} isotopeName - Name of the isotope to remove
     */
    removeIsotopeHighlight(isotopeName) {
        if (!this.chart || !this.chart.options.plugins.annotation.annotations || this.isUpdatingAnnotations) return;

        this.isUpdatingAnnotations = true;
        try {
            const annotations = this.chart.options.plugins.annotation.annotations;
            const safeKey = isotopeName.replace(/[^a-zA-Z0-9]/g, '_');

            const keysToDelete = Object.keys(annotations).filter(k => k.startsWith('iso_' + safeKey));
            keysToDelete.forEach(k => delete annotations[k]);

            this.chart.update('none');
            console.log(`✓ Removed isotope highlight: ${isotopeName}`);
        } finally {
            this.isUpdatingAnnotations = false;
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

        // Bind event listeners
        this.zoomMinSlider.addEventListener('input', () => this.onScrubberChange());
        this.zoomMaxSlider.addEventListener('input', () => this.onScrubberChange());

        // Prevent min > max
        this.zoomMinSlider.addEventListener('input', () => {
            if (parseFloat(this.zoomMinSlider.value) >= parseFloat(this.zoomMaxSlider.value) - 2) {
                this.zoomMinSlider.value = parseFloat(this.zoomMaxSlider.value) - 2;
            }
        });
        this.zoomMaxSlider.addEventListener('input', () => {
            if (parseFloat(this.zoomMaxSlider.value) <= parseFloat(this.zoomMinSlider.value) + 2) {
                this.zoomMaxSlider.value = parseFloat(this.zoomMinSlider.value) + 2;
            }
        });

        console.log('[Scrubber] Initialized');
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
     */
    drawMiniPreview() {
        if (!this.previewCanvas || !this.fullCounts) return;

        const ctx = this.previewCanvas.getContext('2d');
        const width = this.previewCanvas.clientWidth;
        const height = this.previewCanvas.clientHeight;

        this.previewCanvas.width = width;
        this.previewCanvas.height = height;

        ctx.clearRect(0, 0, width, height);

        const maxCount = Math.max(...this.fullCounts);
        const step = Math.max(1, Math.floor(this.fullCounts.length / width));

        // Get accent color
        const styles = getComputedStyle(document.documentElement);
        const lineColor = styles.getPropertyValue('--primary-color').trim() || '#38bdf8';

        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 1;
        ctx.beginPath();

        for (let i = 0; i < width; i++) {
            const dataIdx = Math.floor(i * this.fullCounts.length / width);
            const val = this.fullCounts[dataIdx] || 0;
            const y = height - (val / maxCount) * height * 0.9;

            if (i === 0) {
                ctx.moveTo(i, y);
            } else {
                ctx.lineTo(i, y);
            }
        }
        ctx.stroke();

        // Fill
        ctx.lineTo(width, height);
        ctx.lineTo(0, height);
        ctx.closePath();
        ctx.fillStyle = lineColor + '20';
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

            // Update selection overlay
            this.updateSelectionOverlay(minPercent, maxPercent);

            // Update labels
            if (this.minLabel) this.minLabel.textContent = `${Math.round(minEnergy)} keV`;
            if (this.maxLabel) this.maxLabel.textContent = `${Math.round(maxEnergy)} keV`;
        } finally {
            this.isSyncing = false;
        }
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
            const minEnergy = xScale.min || 0;
            const maxEnergy = xScale.max || this.fullMaxEnergy;

            const minPercent = (minEnergy / this.fullMaxEnergy) * 100;
            const maxPercent = (maxEnergy / this.fullMaxEnergy) * 100;

            this.zoomMinSlider.value = Math.max(0, minPercent);
            this.zoomMaxSlider.value = Math.min(100, maxPercent);

            this.updateSelectionOverlay(minPercent, maxPercent);

            if (this.minLabel) this.minLabel.textContent = `${Math.round(minEnergy)} keV`;
            if (this.maxLabel) this.maxLabel.textContent = `${Math.round(maxEnergy)} keV`;
        } finally {
            this.isSyncing = false;
        }
    }
}

export class DoseRateChart {
    constructor() {
        this.ctx = document.getElementById('doseRateChart')?.getContext('2d');
        this.chart = null;
        this.data = new Array(300).fill(null); // 5 minutes history (assuming ~1Hz)
        this.labels = new Array(300).fill('');
        this.init();
    }

    init() {
        if (!this.ctx) return;
        if (typeof Chart === 'undefined') return; // Safety check

        // Get theme colors
        const styles = getComputedStyle(document.documentElement);
        // Default to accent color or fallbacks
        const lineColor = styles.getPropertyValue('--accent-color').trim() || '#10b981';

        this.chart = new Chart(this.ctx, {
            type: 'line',
            data: {
                labels: this.labels,
                datasets: [{
                    data: this.data,
                    borderColor: lineColor,
                    borderWidth: 2,
                    backgroundColor: lineColor + '20', // Transparent fill
                    fill: 'start',
                    pointRadius: 0,
                    tension: 0.4,
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
                    annotation: { display: false }
                },
                scales: {
                    x: { display: false }, // Tiny chart, no X axis
                    y: {
                        display: true,
                        position: 'right',
                        ticks: {
                            color: '#64748b',
                            font: { size: 10 },
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

    update(doseRate) {
        if (!this.chart) return;

        // Push new value, shift old
        this.data.push(doseRate);
        this.data.shift();

        // Update chart data reference (Chart.js optimizes this)
        this.chart.data.datasets[0].data = this.data;

        // Update color dynamically if theme changes
        // (Optional optimization: only do this if theme changed)
        const styles = getComputedStyle(document.documentElement);
        const lineColor = styles.getPropertyValue('--accent-color').trim() || '#10b981';
        this.chart.data.datasets[0].borderColor = lineColor;
        this.chart.data.datasets[0].backgroundColor = lineColor + '20';

        this.chart.update('none'); // Update without animation
    }
}

export const chartManager = new AlphaHoundChart();

// Expose globally for cross-module access (e.g., XRF highlighting from ui.js)
window.chartManager = chartManager;

