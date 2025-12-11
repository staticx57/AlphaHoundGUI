const dropZone = document.getElementById('drop-zone');
const dashboard = document.getElementById('dashboard');
const metadataPanel = document.getElementById('metadata-panel');
const peaksContainer = document.getElementById('peaks-container');
const peaksTbody = document.getElementById('peaks-tbody');
const ctx = document.getElementById('spectrumChart').getContext('2d');
let chart = null;
let currentData = null;

// ========== Analysis Settings Management ==========
let currentSettings = {
    mode: 'simple',
    isotope_min_confidence: 40.0,
    chain_min_confidence: 30.0,
    energy_tolerance: 20.0,
    chain_min_isotopes_medium: 3,
    chain_min_isotopes_high: 4,
    max_isotopes: 5
};

// Load settings from localStorage on startup
function loadSettings() {
    const saved = localStorage.getItem('analysisSettings');
    if (saved) {
        currentSettings = JSON.parse(saved);
        updateSettingsUI();
    }
}

// Save settings to localStorage
function saveSettings() {
    localStorage.setItem('analysisSettings', JSON.stringify(currentSettings));
}

// Update settings UI to reflect current settings
function updateSettingsUI() {
    // Set mode radio button
    const modeRadios = document.getElementsByName('analysis-mode');
    modeRadios.forEach(radio => {
        if (radio.value === currentSettings.mode) {
            radio.checked = true;
        }
    });

    // Update slider values
    const isoSlider = document.getElementById('isotope-confidence');
    const chainSlider = document.getElementById('chain-confidence');
    const tolSlider = document.getElementById('energy-tolerance');

    if (isoSlider) {
        isoSlider.value = currentSettings.isotope_min_confidence;
        document.getElementById('iso-conf-val').textContent = currentSettings.isotope_min_confidence;
    }
    if (chainSlider) {
        chainSlider.value = currentSettings.chain_min_confidence;
        document.getElementById('chain-conf-val').textContent = currentSettings.chain_min_confidence;
    }
    if (tolSlider) {
        tolSlider.value = currentSettings.energy_tolerance;
        document.getElementById('energy-tol-val').textContent = currentSettings.energy_tolerance;
    }

    // Show/hide advanced settings based on mode
    toggleAdvancedSettings(currentSettings.mode === 'advanced');
}

// Toggle advanced settings visibility
function toggleAdvancedSettings(show) {
    const advancedDiv = document.getElementById('advanced-settings');
    if (advancedDiv) {
        advancedDiv.style.display = show ? 'block' : 'none';
    }
}

// Initialize settings on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();

    // Settings modal controls
    document.getElementById('btn-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'flex';
        updateSettingsUI();
    });

    document.getElementById('close-settings').addEventListener('click', () => {
        document.getElementById('settings-modal').style.display = 'none';
    });

    // Mode toggle
    document.getElementsByName('analysis-mode').forEach(radio => {
        radio.addEventListener('change', (e) => {
            currentSettings.mode = e.target.value;
            toggleAdvancedSettings(e.target.value === 'advanced');
        });
    });

    // Threshold sliders with live updates
    document.getElementById('isotope-confidence').addEventListener('input', (e) => {
        document.getElementById('iso-conf-val').textContent = e.target.value;
        currentSettings.isotope_min_confidence = parseFloat(e.target.value);
    });

    document.getElementById('chain-confidence').addEventListener('input', (e) => {
        document.getElementById('chain-conf-val').textContent = e.target.value;
        currentSettings.chain_min_confidence = parseFloat(e.target.value);
    });

    document.getElementById('energy-tolerance').addEventListener('input', (e) => {
        document.getElementById('energy-tol-val').textContent = e.target.value;
        currentSettings.energy_tolerance = parseFloat(e.target.value);
    });

    // Reset to defaults button
    document.getElementById('btn-reset-defaults').addEventListener('click', () => {
        currentSettings = {
            mode: 'simple',
            isotope_min_confidence: 40.0,
            chain_min_confidence: 30.0,
            energy_tolerance: 20.0,
            chain_min_isotopes_medium: 3,
            chain_min_isotopes_high: 4,
            max_isotopes: 5
        };
        updateSettingsUI();
        alert('Settings reset to defaults! Click "Apply Settings" to save.');
    });

    // Apply settings button
    document.getElementById('btn-apply-settings').addEventListener('click', () => {
        saveSettings();
        document.getElementById('settings-modal').style.display = 'none';
        alert('Settings saved! Re-upload your file or acquire a new spectrum to apply changes.');
    });
});

// File Upload Handling - Use event delegation to handle dynamically recreated input
dropZone.addEventListener('change', (e) => {
    if (e.target.id === 'file-input') {
        handleFile(e.target.files[0]);
    }
});


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
        }, 1000);

    } catch (err) {
        alert(err.message);
        dropZone.innerHTML = '<div class="upload-icon">❌</div><h2>Error. Try again.</h2><p>' + err.message + '</p><input type="file" id="file-input" accept=".n42,.xml,.csv">';
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


    // Decay Chains Display
    const decayChainsContainer = document.getElementById('decay-chains-container');
    const decayChainsList = document.getElementById('decay-chains-list');

    console.log('Decay chains data:', data.decay_chains);
    console.log('Decay chains container:', decayChainsContainer);

    if (data.decay_chains && data.decay_chains.length > 0) {
        console.log('Displaying', data.decay_chains.length, 'decay chains');
        decayChainsContainer.style.display = 'block';

        decayChainsList.innerHTML = data.decay_chains.map(chain => {
            const confidenceClass = chain.confidence_level.toLowerCase() + '-confidence';
            const confidenceBadge = chain.confidence_level === 'HIGH' ? '🟢' :
                chain.confidence_level === 'MEDIUM' ? '🟡' : '🔴';

            // Format detected members
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
                        
                        ${chain.notes ? `<div style="margin-top: 0.5rem; font-style: italic; color: var(--accent-color);">
                            ℹ️ ${chain.notes}
                        </div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    } else {
        console.log('No decay chains detected or empty array');
        decayChainsContainer.style.display = 'none';
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

// Theme Toggle (cycles through: dark → light → nuclear → toxic)
const themeBtn = document.getElementById('btn-theme');
const themes = ['dark', 'light', 'nuclear', 'toxic'];
const currentTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', currentTheme);

themeBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const currentIndex = themes.indexOf(current);
    const nextIndex = (currentIndex + 1) % themes.length;
    const newTheme = themes[nextIndex];

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    console.log(`[Theme] Switched to: ${newTheme}`);

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


// ========== AlphaHound Device Control (Top Panel) ==========
// Credit: Based on AlphaHound Python Interface by NuclearGeekETH
// Device: RadView Detection AlphaHound™

let doseWebSocket = null;
let acquisitionInterval = null;
let acquisitionStartTime = null;
let isAcquiring = false;

// Initialize device controls on page load
document.addEventListener('DOMContentLoaded', async () => {
    await refreshPorts();
});

// Show User Success/Error (using alert since no alert element in top panel)
function showDeviceAlert(msg, type = 'error') {
    if (type === 'error') {
        alert(msg);
    } else {
        console.log('[Device] ' + msg);
    }
}

// Refresh serial ports
document.getElementById('btn-refresh-ports').addEventListener('click', refreshPorts);

async function refreshPorts() {
    console.log('[Device] Refreshing ports...');
    try {
        const response = await fetch('/device/ports');
        const data = await response.json();
        console.log('[Device] API response:', data);
        const select = document.getElementById('port-select');

        if (data.ports && data.ports.length > 0) {
            console.log(`[Device] Found ${data.ports.length} ports`);
            const options = data.ports.map(p =>
                `<option value="${p.device}">${p.device} - ${p.description}</option>`
            ).join('');
            select.innerHTML = options;
            console.log('[Device] Ports populated in dropdown');
        } else {
            console.log('[Device] No ports found in API response');
            const noPorts = '<option value="">No ports found</option>';
            select.innerHTML = noPorts;
        }
    } catch (err) {
        console.error('[Device] Error refreshing ports:', err);
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

// Acquire Spectrum from device with stop capability
let acquisitionAbortController = null;

document.getElementById('btn-start-acquire').addEventListener('click', async () => {
    console.log("[Device] Acquire Spectrum button clicked");
    const btnStart = document.getElementById('btn-start-acquire');
    const btnStop = document.getElementById('btn-stop-acquire');
    const originalText = btnStart.innerHTML;
    const countMinutes = parseFloat(document.getElementById('count-time').value) || 5;

    try {
        // Create abort controller for stopping acquisition
        acquisitionAbortController = new AbortController();

        // Show stop button, hide start button
        btnStart.style.display = 'none';
        btnStop.style.display = 'inline-block';
        btnStop.innerHTML = `⏹️ Stop (${countMinutes} min)`;

        // Call the spectrum acquisition endpoint
        const response = await fetch('/device/spectrum', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count_minutes: countMinutes }),
            signal: acquisitionAbortController.signal
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Spectrum acquisition failed');
        }

        const data = await response.json();
        console.log("[Device] Spectrum acquired:", data);

        // Display the spectrum in the dashboard
        currentData = data;
        renderDashboard(data);

        // Show success message
        alert(`Spectrum acquired successfully! ${data.peaks.length} peaks detected after ${countMinutes} minute(s).`);

        // Reset buttons
        btnStart.innerHTML = originalText;
        btnStart.style.display = 'inline-block';
        btnStop.style.display = 'none';
    } catch (err) {
        if (err.name === 'AbortError') {
            console.log("[Device] Acquisition stopped by user");
            // Note: Backend should return partial spectrum on abort
            alert('Acquisition stopped. Attempting to retrieve partial spectrum...');
        } else {
            console.error("[Device] Spectrum acquisition error:", err);
            alert('Error acquiring spectrum: ' + err.message);
        }
        // Reset buttons
        btnStart.innerHTML = originalText;
        btnStart.style.display = 'inline-block';
        btnStop.style.display = 'none';
    }
});

// Stop acquisition button
document.getElementById('btn-stop-acquire').addEventListener('click', () => {
    console.log("[Device] Stop button clicked");
    stopAcquisition();
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

        // Check if time is up BEFORE polling again
        if (elapsed >= countSeconds) {
            stopAcquisition();
            showDeviceAlert("Acquisition Complete", 'success');
            console.log("[Device] Acquisition Complete");
            return;
        }

        const remaining = Math.max(0, countSeconds - elapsed);

        document.getElementById('acquisition-timer').textContent =
            `${Math.round(elapsed)}s / ${countSeconds.toFixed(0)}s`;

        // Fetch spectrum (snapshot)
        try {
            // Using count_minutes=0 tells backend "just give me what you have now"
            const res = await fetch('/device/spectrum', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count_minutes: 0 })
            });

            if (res.ok) {
                const data = await res.json();
                currentData = data;
                renderDashboard(data); // "Building the graph"
            } else {
                console.error(`[Device] Poll failed: ${res.status} ${res.statusText}`);
            }
        } catch (e) {
            console.error("[Device] Poll error:", e);
        }
    }, 2000); // Poll every 2 seconds
});

// Stop Acquisition
const stopAcquisition = () => {
    isAcquiring = false;
    clearInterval(acquisitionInterval);
    acquisitionInterval = null;
    acquisitionStartTime = null;

    document.getElementById('btn-start-acquire').style.display = 'block';
    document.getElementById('btn-stop-acquire').style.display = 'none';
    document.getElementById('acquisition-status').style.display = 'none';

    // Reset timer display
    document.getElementById('acquisition-timer').textContent = '0s';
};

// UI state management
function showDeviceConnected() {
    const connectedDiv = document.getElementById('device-connected');
    const portSelect = document.getElementById('port-select');
    const refreshBtn = document.getElementById('btn-refresh-ports');
    const connectBtn = document.getElementById('btn-connect-device');
    const advancedBtn = document.getElementById('btn-advanced');

    if (connectedDiv) connectedDiv.style.display = 'block';
    if (portSelect) portSelect.parentElement.style.display = 'none';
    if (refreshBtn) refreshBtn.style.display = 'none';
    if (connectBtn) connectBtn.style.display = 'none';
    if (advancedBtn) advancedBtn.style.display = 'none';
}

function showDeviceDisconnected() {
    const connectedDiv = document.getElementById('device-connected');
    const portSelect = document.getElementById('port-select');
    const refreshBtn = document.getElementById('btn-refresh-ports');
    const connectBtn = document.getElementById('btn-connect-device');
    const advancedBtn = document.getElementById('btn-advanced');

    if (connectedDiv) connectedDiv.style.display = 'none';
    if (portSelect) portSelect.parentElement.style.display = 'flex';
    if (refreshBtn) refreshBtn.style.display = 'block';
    if (connectBtn) connectBtn.style.display = 'block';
    if (advancedBtn) advancedBtn.style.display = 'block';
}

// WebSocket dose monitoring
function startDoseMonitoring() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dose`;

    doseWebSocket = new WebSocket(wsUrl);

    doseWebSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.dose_rate !== null) {
            const doseText = `${data.dose_rate.toFixed(2)} µRem/hr`;
            const doseDisplay = document.getElementById('dose-display');
            if (doseDisplay) doseDisplay.textContent = doseText;
        } else {
            const emptyText = '-- µRem/hr';
            const doseDisplay = document.getElementById('dose-display');
            if (doseDisplay) doseDisplay.textContent = emptyText;
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

// New Top Panel Event Listeners
if (document.getElementById('btn-refresh-ports-top')) {
    document.getElementById('btn-refresh-ports-top').addEventListener('click', refreshPorts);
}

if (document.getElementById('btn-connect-top')) {
    document.getElementById('btn-connect-top').addEventListener('click', async () => {
        const port = document.getElementById('port-select-top').value;
        if (!port) { alert('Please select a port'); return; }
        // Reuse connect logic - simulate click on main button or copy logic
        // Copying logic for simplicity and reliability
        try {
            const response = await fetch('/device/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ port })
            });
            if (response.ok) {
                showDeviceConnected();
                startDoseMonitoring();
            } else {
                const error = await response.json();
                alert('Connection failed: ' + error.detail);
            }
        } catch (err) {
            alert('Connection error: ' + err.message);
        }
    });
}

if (document.getElementById('btn-disconnect-top')) {
    document.getElementById('btn-disconnect-top').addEventListener('click', () => {
        document.getElementById('btn-disconnect-device').click();
    });
}

if (document.getElementById('btn-acquire-top')) {
    document.getElementById('btn-acquire-top').addEventListener('click', () => {
        // Scroll to dashboard if hidden
        document.getElementById('dashboard').style.display = 'block';
        document.getElementById('btn-start-acquire').click();
    });
}

if (document.getElementById('btn-device-more')) {
    document.getElementById('btn-device-more').addEventListener('click', () => {
        document.getElementById('device-sidebar').classList.add('open');
    });
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    refreshPorts();
    checkDeviceStatus();
});
