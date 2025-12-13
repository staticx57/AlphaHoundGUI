export class AlphaHoundChart {
    constructor() {
        this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        this.chart = null;
        this.primaryColor = '#38bdf8'; // Default, should read from CSS
        this.autoScale = true; // Default to auto-scale (zoom to data)
    }

    render(labels, dataPoints, peaks, scaleType = 'linear') {
        if (!this.ctx) return;
        if (this.chart) this.chart.destroy();

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
            // STAGE 1: X-AXIS AUTO-SCALE (Trim Noise)
            // ==========================================
            const maxCount = Math.max(...dataPoints);

            // Calculate noise threshold more intelligently
            // Use median of non-zero values to avoid being skewed by large peaks
            const nonZeroCounts = dataPoints.filter(c => c > 0);
            const sortedCounts = [...nonZeroCounts].sort((a, b) => a - b);
            const medianCount = sortedCounts[Math.floor(sortedCounts.length / 2)] || 0;

            // Threshold: 3x median or 2% of max, whichever is higher (more aggressive noise filtering)
            const noiseThreshold = Math.max(medianCount * 3, maxCount * 0.02, 2);

            // Scan from right to find last significant data
            for (let i = dataPoints.length - 1; i >= 0; i--) {
                if (dataPoints[i] > noiseThreshold) {
                    maxEnergy = Math.min(parseFloat(labels[i]) * 1.10, fullMaxEnergy); // 10% margin
                    break;
                }
            }

            // CRITICAL: Ensure detected peaks are not truncated
            // If we have detected peaks, extend X-axis to include the rightmost peak + 10% margin
            if (peaks && peaks.length > 0) {
                const maxPeakEnergy = Math.max(...peaks.map(p => p.energy));
                // Extend maxEnergy to include all peaks with 10% headroom
                maxEnergy = Math.max(maxEnergy, Math.min(maxPeakEnergy * 1.10, fullMaxEnergy));
            }

            // ==========================================
            // Y-AXIS: ADD HEADROOM (NEVER CLIP)
            // ==========================================
            // Always show the full data range, just add buffer at top for readability
            maxY = maxCount * 1.15; // 15% headroom above maximum peak
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

