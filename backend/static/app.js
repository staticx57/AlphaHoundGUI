const fileInput = document.getElementById('file-input');
const dropZone = document.getElementById('drop-zone');
const dashboard = document.getElementById('dashboard');
const metadataPanel = document.getElementById('metadata-panel');
const peaksContainer = document.getElementById('peaks-container');
const peaksTbody = document.getElementById('peaks-tbody');
const ctx = document.getElementById('spectrumChart').getContext('2d');
let chart = null;
let currentData = null;

// File Upload Handling
fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

// Drag and Drop
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--primary-color)';
});

dropZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border-color)';
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border-color)';
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

async function handleFile(file) {
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        dropZone.innerHTML = '<div class="upload-icon">⏳</div><h2>Processing...</h2>';

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        currentData = data;
        renderDashboard(data);

        // Reset upload zone text but keep it accessible for new uploads
        setTimeout(() => {
            dropZone.innerHTML = '<div class="upload-icon">📂</div><h2>Drop new file to replace</h2><input type="file" id="file-input" accept=".n42,.xml,.csv">';
            document.getElementById('file-input').addEventListener('change', (e) => handleFile(e.target.files[0]));
        }, 1000);

    } catch (err) {
        alert(err.message);
        dropZone.innerHTML = '<div class="upload-icon">❌</div><h2>Error. Try again.</h2><p>' + err.message + '</p><input type="file" id="file-input" accept=".n42,.xml,.csv">';
        document.getElementById('file-input').addEventListener('change', (e) => handleFile(e.target.files[0]));
    }
}

function renderDashboard(data) {
    dashboard.style.display = 'block';

    // Metadata
    const metaHtml = Object.entries(data.metadata || {}).map(([key, value]) => `
        <div class="stat-card">
            <div class="stat-label">${key.toUpperCase().replace('_', ' ')}</div>
            <div class="stat-value">${value || '-'}</div>
        </div>
    `).join('');
    metadataPanel.innerHTML = metaHtml;

    // Peaks Table
    if (data.peaks && data.peaks.length > 0) {
        peaksContainer.style.display = 'block';
        peaksTbody.innerHTML = data.peaks.map(peak => `
            <tr>
                <td>${peak.energy.toFixed(2)}</td>
                <td>${peak.counts.toFixed(0)}</td>
            </tr>
        `).join('');
    } else {
        peaksContainer.style.display = 'none';
    }

    // Isotopes Table
    const isotopesContainer = document.getElementById('isotopes-container');
    const isotopesTbody = document.getElementById('isotopes-tbody');
    if (data.isotopes && data.isotopes.length > 0) {
        isotopesContainer.style.display = 'block';
        isotopesTbody.innerHTML = data.isotopes.map(iso => {
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
        isotopesContainer.style.display = 'none';
    }

    // Chart
    renderChart(data.energies, data.counts, data.peaks, 'linear');
}

function renderChart(labels, dataPoints, peaks, scaleType) {
    if (chart) chart.destroy();

    const primaryColor = getComputedStyle(document.body).getPropertyValue('--primary-color').trim();
    const secondaryColor = getComputedStyle(document.body).getPropertyValue('--secondary-color').trim();

    // Create annotations for peaks
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

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Counts',
                data: dataPoints,
                borderColor: primaryColor,
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
            interaction: {
                intersect: false,
                mode: 'index',
            },
            scales: {
                x: {
                    title: { display: true, text: 'Energy (keV)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    type: scaleType,
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
                        wheel: {
                            enabled: true,
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'xy',
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                    }
                },
                annotation: {
                    annotations: annotations
                }
            }
        }
    });
}

// Log/Linear Toggles
document.getElementById('btn-lin').addEventListener('click', () => {
    document.getElementById('btn-lin').classList.add('active');
    document.getElementById('btn-log').classList.remove('active');
    if (currentData) renderChart(currentData.energies, currentData.counts, currentData.peaks, 'linear');
});

document.getElementById('btn-log').addEventListener('click', () => {
    document.getElementById('btn-lin').classList.remove('active');
    document.getElementById('btn-log').classList.add('active');
    if (currentData) renderChart(currentData.energies, currentData.counts, currentData.peaks, 'logarithmic');
});

// Reset Zoom
document.getElementById('btn-reset-zoom').addEventListener('click', () => {
    if (chart) chart.resetZoom();
});

// Export JSON
document.getElementById('btn-export-json').addEventListener('click', () => {
    if (!currentData) return;
    const dataStr = JSON.stringify(currentData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'spectrum_data.json';
    a.click();
    URL.revokeObjectURL(url);
});

// Export CSV
document.getElementById('btn-export-csv').addEventListener('click', () => {
    if (!currentData) return;

    let csv = 'Energy (keV),Counts\n';
    for (let i = 0; i < currentData.energies.length; i++) {
        csv += `${currentData.energies[i]},${currentData.counts[i]}\n`;
    }

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'spectrum_data.csv';
    a.click();
    URL.revokeObjectURL(url);
});

// Export PDF
document.getElementById('btn-export-pdf').addEventListener('click', async () => {
    if (!currentData) return;

    try {
        const btn = document.getElementById('btn-export-pdf');
        const originalText = btn.innerHTML;
        btn.innerHTML = '⏳ Generating...';
        btn.disabled = true;

        const response = await fetch('/export/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: currentData.metadata?.filename || 'spectrum',
                metadata: currentData.metadata || {},
                energies: currentData.energies,
                counts: currentData.counts,
                peaks: currentData.peaks || [],
                isotopes: currentData.isotopes || []
            })
        });

        if (!response.ok) {
            const errJson = await response.json();
            throw new Error(errJson.detail || 'PDF generation failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = (currentData.metadata?.filename || 'spectrum') + '_report.pdf';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);

        btn.innerHTML = originalText;
        btn.disabled = false;
    } catch (err) {
        alert('Error generating PDF: ' + err.message);
        const btn = document.getElementById('btn-export-pdf');
        btn.innerHTML = '📄 Export PDF';
        btn.disabled = false;
    }
});

// Theme Toggle
const themeBtn = document.getElementById('btn-theme');
const currentTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', currentTheme);

themeBtn.addEventListener('click', () => {
    const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    // Update chart colors if chart exists
    if (currentData) {
        renderChart(currentData.energies, currentData.counts, currentData.peaks,
            chart.options.scales.y.type);
    }
});

// File History Management
function saveToHistory(filename, data) {
    const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');
    history.unshift({
        filename,
        timestamp: new Date().toISOString(),
        preview: {
            peakCount: data.peaks?.length || 0,
            isotopes: data.isotopes?.slice(0, 3).map(i => i.isotope) || []
        }
    });
    // Keep only last 10 files
    localStorage.setItem('fileHistory', JSON.stringify(history.slice(0, 10)));
}

// Show history modal
document.getElementById('btn-history').addEventListener('click', () => {
    const modal = document.getElementById('history-modal');
    const historyList = document.getElementById('history-list');
    const history = JSON.parse(localStorage.getItem('fileHistory') || '[]');

    if (history.length === 0) {
        historyList.innerHTML = '<p style="text-align: center; color: #94a3b8;">No file history yet</p>';
    } else {
        historyList.innerHTML = history.map((item, idx) => `
            <div class="history-item" data-index="${idx}">
                <div class="history-item-name">${item.filename}</div>
                <div class="history-item-date">${new Date(item.timestamp).toLocaleString()}</div>
                <div style="font-size: 0.875rem; margin-top: 0.5rem;">
                    ${item.preview.peakCount} peaks | ${item.preview.isotopes.join(', ') || 'No isotopes'}
                </div>
            </div>
        `).join('');
    }

    modal.style.display = 'flex';
});

document.getElementById('close-history').addEventListener('click', () => {
    document.getElementById('history-modal').style.display = 'none';
});

// Close modal on backdrop click
document.getElementById('history-modal').addEventListener('click', (e) => {
    if (e.target.id === 'history-modal') {
        e.target.style.display = 'none';
    }
});

// Update handleFile to save history
const originalHandleFile = handleFile;
handleFile = async function (file) {
    await originalHandleFile.call(this, file);
    if (currentData) {
        saveToHistory(file.name, currentData);
    }
};

// Multi-file Comparison Mode
let compareMode = false;
let overlaySpectra = [];
const colors = [
    '#38bdf8', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6',
    '#ec4899', '#14b8a6', '#f97316'
];

document.getElementById('btn-compare').addEventListener('click', () => {
    compareMode = !compareMode;
    const comparePanel = document.getElementById('compare-panel');
    const btn = document.getElementById('btn-compare');

    if (compareMode) {
        comparePanel.style.display = 'flex';
        btn.classList.add('active');
        // Add current spectrum to overlays if exists
        if (currentData) {
            overlaySpectra.push({
                name: 'Spectrum 1',
                energies: currentData.energies,
                counts: currentData.counts,
                color: colors[0]
            });
            updateOverlayCount();
            renderComparisonChart('linear');
        }
    } else {
        comparePanel.style.display = 'none';
        btn.classList.remove('active');
        overlaySpectra = [];
        // Re-render original chart if data exists
        if (currentData) {
            renderChart(currentData.energies, currentData.counts, currentData.peaks, 'linear');
        }
    }
});

document.getElementById('btn-add-file').addEventListener('click', () => {
    document.getElementById('compare-file-input').click();
});

document.getElementById('compare-file-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Upload failed');
        }

        const data = await response.json();
        const colorIndex = overlaySpectra.length % colors.length;

        overlaySpectra.push({
            name: file.name,
            energies: data.energies,
            counts: data.counts,
            color: colors[colorIndex]
        });

        updateOverlayCount();
        renderComparisonChart(chart ? chart.options.scales.y.type : 'linear');

        // Reset file input
        e.target.value = '';
    } catch (err) {
        alert('Error loading file: ' + err.message);
    }
});

document.getElementById('btn-clear-overlays').addEventListener('click', () => {
    overlaySpectra = [];
    updateOverlayCount();
    if (chart) chart.destroy();
});

function updateOverlayCount() {
    document.getElementById('overlay-count').textContent = `${overlaySpectra.length} spectra loaded`;
}

function renderComparisonChart(scaleType) {
    if (chart) chart.destroy();

    const primaryColor = getComputedStyle(document.body).getPropertyValue('--primary-color').trim();

    const datasets = overlaySpectra.map((spectrum, idx) => ({
        label: spectrum.name,
        data: spectrum.counts,
        borderColor: spectrum.color,
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.1
    }));

    // Use first spectrum's energies as labels
    const labels = overlaySpectra.length > 0 ? overlaySpectra[0].energies : [];

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            scales: {
                x: {
                    title: { display: true, text: 'Energy (keV)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    type: scaleType,
                    title: { display: true, text: 'Counts', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#94a3b8'
                    }
                },
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
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                    }
                }
            }
        }
    });
}

// Update scale toggles to work with comparison mode
const originalLinBtn = document.getElementById('btn-lin');
const originalLogBtn = document.getElementById('btn-log');

originalLinBtn.addEventListener('click', () => {
    originalLinBtn.classList.add('active');
    originalLogBtn.classList.remove('active');
    if (compareMode && overlaySpectra.length > 0) {
        renderComparisonChart('linear');
    } else if (currentData) {
        renderChart(currentData.energies, currentData.counts, currentData.peaks, 'linear');
    }
}, { once: false });

originalLogBtn.addEventListener('click', () => {
    originalLinBtn.classList.remove('active');
    originalLogBtn.classList.add('active');
    if (compareMode && overlaySpectra.length > 0) {
        renderComparisonChart('logarithmic');
    } else if (currentData) {
        renderChart(currentData.energies, currentData.counts, currentData.peaks, 'logarithmic');
    }
}, { once: false });


// ========== AlphaHound Device Control (Sidebar) ==========
// Credit: Based on AlphaHound Python Interface by NuclearGeekETH
// Device: RadView Detection AlphaHound™

let doseWebSocket = null;
let acquisitionInterval = null;
let acquisitionStartTime = null;
let isAcquiring = false;

// Sidebar Elements
const deviceSidebar = document.getElementById('device-sidebar');
const btnDevice = document.getElementById('btn-device');
const closeSidebar = document.getElementById('close-device-sidebar');

// Open Sidebar
btnDevice.addEventListener('click', async () => {
    deviceSidebar.classList.toggle('open');
    if (deviceSidebar.classList.contains('open')) {
        await refreshPorts();
        await checkDeviceStatus();
    }
});

// Close Sidebar
closeSidebar.addEventListener('click', () => {
    deviceSidebar.classList.remove('open');
});

// Show User Success/Error
function showDeviceAlert(msg, type = 'error') {
    const el = document.getElementById('device-alert');
    if (!el) return; // safety
    el.textContent = msg;
    el.className = `ephemeral-message ${type}`;
    el.style.display = 'block';
    setTimeout(() => el.style.display = 'none', 3000);
}

// Refresh serial ports
document.getElementById('btn-refresh-ports').addEventListener('click', refreshPorts);

async function refreshPorts() {
    try {
        const response = await fetch('/device/ports');
        const data = await response.json();
        const select = document.getElementById('port-select');

        if (data.ports && data.ports.length > 0) {
            select.innerHTML = data.ports.map(p =>
                `<option value="${p.device}">${p.device} - ${p.description}</option>`
            ).join('');
        } else {
            select.innerHTML = '<option value="">No ports found</option>';
        }
    } catch (err) {
        showDeviceAlert('Error loading ports: ' + err.message);
        document.getElementById('port-select').innerHTML = '<option value="">Error loading ports</option>';
    }
}

// Connect to device
document.getElementById('btn-connect-device').addEventListener('click', async () => {
    console.log("Connect button clicked");
    const port = document.getElementById('port-select').value;
    if (!port) {
        showDeviceAlert('Please select a port');
        return;
    }

    try {
        const response = await fetch('/device/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port })
        });

        if (response.ok) {
            showDeviceConnected();
            startDoseMonitoring();
            showDeviceAlert('Connected successfully', 'success');
        } else {
            const error = await response.json();
            showDeviceAlert('Connection failed: ' + error.detail);
        }
    } catch (err) {
        showDeviceAlert('Connection error: ' + err.message);
    }
});

// ========== Advanced Analysis ==========

let analysisMode = false;

document.getElementById('btn-analysis').addEventListener('click', () => {
    analysisMode = !analysisMode;
    const panel = document.getElementById('analysis-panel');
    const btn = document.getElementById('btn-analysis');

    if (analysisMode) {
        panel.style.display = 'flex';
        panel.style.flexDirection = 'column';
        btn.classList.add('active');
        // Hide compare panel if open
        if (compareMode) document.getElementById('btn-compare').click();
    } else {
        panel.style.display = 'none';
        btn.classList.remove('active');
    }
});

document.getElementById('btn-run-fit').addEventListener('click', async () => {
    if (!currentData || !currentData.peaks) return;

    const resultsContainer = document.getElementById('analysis-results');
    resultsContainer.innerHTML = '<p>Fitting peaks...</p>';

    try {
        const response = await fetch('/analyze/fit-peaks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                energies: currentData.energies,
                counts: currentData.counts,
                peaks: currentData.peaks
            })
        });

        if (!response.ok) throw new Error('Analysis failed');

        const data = await response.json();

        if (data.fits && data.fits.length > 0) {
            resultsContainer.innerHTML = `
                <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9rem;">
                    <thead>
                        <tr style="border-bottom: 1px solid var(--border-color); text-align: left;">
                            <th style="padding: 4px;">Energy</th>
                            <th style="padding: 4px;">FWHM</th>
                            <th style="padding: 4px;">Net Area</th>
                            <th style="padding: 4px;">Resolution</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.fits.map(fit => {
                const res = (fit.fwhm / fit.energy) * 100;
                return `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <td style="padding: 4px;">${fit.energy.toFixed(2)} keV</td>
                                <td style="padding: 4px;">${fit.fwhm.toFixed(2)} keV</td>
                                <td style="padding: 4px;">${fit.net_area.toFixed(0)}</td>
                                <td style="padding: 4px;">${res.toFixed(1)}%</td>
                            </tr>
                        `}).join('')}
                    </tbody>
                </table>
            `;
        } else {
            resultsContainer.innerHTML = '<p>No peaks fitted successfully.</p>';
        }

    } catch (err) {
        resultsContainer.innerHTML = `<p style="color: #ef4444;">Error: ${err.message}</p>`;
    }
});

// Disconnect from device
document.getElementById('btn-disconnect-device').addEventListener('click', async () => {
    try {
        await fetch('/device/disconnect', { method: 'POST' });
        showDeviceDisconnected();
        stopDoseMonitoring();
        stopAcquisition(); // safety stop
    } catch (err) {
        showDeviceAlert('Disconnect error: ' + err.message);
    }
});

// Start Live Acquisition
document.getElementById('btn-start-acquire').addEventListener('click', async () => {
    if (isAcquiring) return;

    const countMinutes = parseFloat(document.getElementById('count-time').value) || 1;
    const countSeconds = countMinutes * 60;

    // 1. Clear Device
    try {
        await fetch('/device/clear', { method: 'POST' });
    } catch (e) {
        showDeviceAlert("Failed to clear device: " + e.message);
        return;
    }

    // 2. Start UI State
    isAcquiring = true;
    document.getElementById('btn-start-acquire').style.display = 'none';
    document.getElementById('btn-stop-acquire').style.display = 'block';
    document.getElementById('acquisition-status').style.display = 'block';

    acquisitionStartTime = Date.now();

    // 3. Polling Loop
    acquisitionInterval = setInterval(async () => {
        const elapsed = (Date.now() - acquisitionStartTime) / 1000;
        const remaining = Math.max(0, countSeconds - elapsed);

        document.getElementById('acquisition-timer').textContent =
            `${elapsed.toFixed(0)}s / ${countSeconds.toFixed(0)}s`;

        // Fetch spectrum (snapshot)
        try {
            // Using count_minutes=0 tells backend "just give me what you have now"
            // Note: Our backend fix requires count_minutes to be in JSON body
            const res = await fetch('/device/spectrum', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count_minutes: 0 })
            });

            if (res.ok) {
                const data = await res.json();
                currentData = data;
                renderDashboard(data); // "Building the graph"
            }
        } catch (e) {
            console.error("Poll error:", e);
        }

        // Auto-stop when time is up
        if (elapsed >= countSeconds) {
            stopAcquisition();
            showDeviceAlert("Acquisition Complete", 'success');
        }
    }, 2000); // Poll every 2 seconds
});

// Stop Acquisition
const stopAcquisition = () => {
    isAcquiring = false;
    clearInterval(acquisitionInterval);

    document.getElementById('btn-start-acquire').style.display = 'block';
    document.getElementById('btn-stop-acquire').style.display = 'none';
    // keep status visible for a moment? or hide.
    document.getElementById('acquisition-status').style.display = 'none';
};

document.getElementById('btn-stop-acquire').addEventListener('click', stopAcquisition);

// Clear device spectrum button
document.getElementById('btn-clear-device').addEventListener('click', async () => {
    if (!confirm('Clear spectrum on device?')) return;
    try {
        await fetch('/device/clear', { method: 'POST' });
        showDeviceAlert('Device spectrum cleared', 'success');

        // Also clear chart?
        if (chart) {
            // Maybe not, user might want to keep looking
        }
    } catch (err) {
        showDeviceAlert('Clear error: ' + err.message);
    }
});

// UI state management
function showDeviceConnected() {
    document.getElementById('device-disconnected').style.display = 'none';
    document.getElementById('device-connected').style.display = 'block';
}

function showDeviceDisconnected() {
    document.getElementById('device-disconnected').style.display = 'block';
    document.getElementById('device-connected').style.display = 'none';
}

// WebSocket dose monitoring
function startDoseMonitoring() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dose`;

    doseWebSocket = new WebSocket(wsUrl);

    doseWebSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.dose_rate !== null) {
            document.getElementById('dose-display').textContent =
                `${data.dose_rate.toFixed(2)} µRem/hr`;
        } else {
            document.getElementById('dose-display').textContent = '-- µRem/hr';
        }
    };

    doseWebSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    doseWebSocket.onclose = () => {
        console.log('Dose monitoring WebSocket closed');
    };
}

function stopDoseMonitoring() {
    if (doseWebSocket) {
        doseWebSocket.close();
        doseWebSocket = null;
    }
    document.getElementById('dose-display').textContent = '-- µRem/hr';
}

// Check device status o sidebar open
async function checkDeviceStatus() {
    try {
        const response = await fetch('/device/status');
        const data = await response.json();

        if (data.connected) {
            showDeviceConnected();
            startDoseMonitoring();
        } else {
            showDeviceDisconnected();
        }
    } catch (err) {
        console.error('Status check error:', err);
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    refreshPorts();
    checkDeviceStatus();
});
