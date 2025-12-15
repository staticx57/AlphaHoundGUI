export class AlphaHoundChart {
    constructor() {
        this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        this.chart = null;
        this.primaryColor = '#38bdf8'; // Default, should read from CSS
        this.autoScale = true; // Default to auto-scale (zoom to data)
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
        const chartData = labels.map((energy, idx) => ({
            x: parseFloat(energy),
            y: dataPoints[idx]
        }));

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

        // Annotations
        const annotations = {};
        if (peaks && peaks.length > 0) {
            peaks.slice(0, 10).forEach((peak, idx) => {
                annotations[`peak${idx}`] = {
                    type: 'point',
                    xValue: peak.energy,
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
                        min: minEnergy,
                        max: maxEnergy,
                        title: { display: true, text: 'Energy (keV)', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8' }
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
                        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' },
                        pan: { enabled: true, mode: 'xy' }
                    },
                    annotation: { annotations: annotations }
                }
            }
        });
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
                        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' },
                        pan: { enabled: true, mode: 'xy' }
                    }
                }
            }
        });
    }

    getScaleType() {
        return (this.chart && this.chart.options.scales.y.type) ? this.chart.options.scales.y.type : 'linear';
    }

    resetZoom() {
        if (this.chart) this.chart.resetZoom();
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

            // Force full chart update
            this.chart.update('default');
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
        this.chart.update();
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
        this.chart.update();
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

