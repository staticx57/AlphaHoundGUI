export class AlphaHoundChart {
    constructor() {
        this.ctx = document.getElementById('spectrumChart')?.getContext('2d');
        this.chart = null;
        this.primaryColor = '#38bdf8'; // Default, should read from CSS
    }

    render(labels, dataPoints, peaks, scaleType = 'linear') {
        if (!this.ctx) return;
        if (this.chart) this.chart.destroy();

        // Annotations
        const annotations = {};
        if (peaks && peaks.length > 0) {
            peaks.slice(0, 10).forEach((peak, idx) => {
                annotations[`peak${idx}`] = {
                    type: 'point',
                    xValue: peak.energy,
                    yValue: peak.counts,
                    backgroundColor: 'rgba(255, 99, 132, 0.5)',
                    radius: 6,
                    borderColor: '#ff6384',
                    borderWidth: 2
                };
            });
        }

        this.chart = new Chart(this.ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Counts',
                    data: dataPoints,
                    borderColor: this.primaryColor,
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 2,
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
}

export const chartManager = new AlphaHoundChart();
