// ========== AlphaHound Device Control ==========
// Credit: Based on AlphaHound Python Interface by NuclearGeekETH
// Device: RadView Detection AlphaHound™

let doseWebSocket = null;

// Device modal handlers
document.getElementById('btn-device').addEventListener('click', async () => {
    const modal = document.getElementById('device-modal');
    modal.style.display = 'flex';
    await refreshPorts();
    await checkDeviceStatus();
});

document.getElementById('close-device').addEventListener('click', () => {
    document.getElementById('device-modal').style.display = 'none';
});

document.getElementById('device-modal').addEventListener('click', (e) => {
    if (e.target.id === 'device-modal') {
        e.target.style.display = 'none';
    }
});

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
        alert('Error loading ports: ' + err.message);
    }
}

// Connect to device
document.getElementById('btn-connect-device').addEventListener('click', async () => {
    const port = document.getElementById('port-select').value;
    if (!port) {
        alert('Please select a port');
        return;
    }

    try {
        const response = await fetch('/device/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port })
        });

        if (response.ok) {
            const data = await response.json();
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

// Disconnect from device
document.getElementById('btn-disconnect-device').addEventListener('click', async () => {
    try {
        await fetch('/device/disconnect', { method: 'POST' });
        showDeviceDisconnected();
        stopDoseMonitoring();
    } catch (err) {
        alert('Disconnect error: ' + err.message);
    }
});

// Acquire spectrum from device
document.getElementById('btn-acquire-spectrum').addEventListener('click', async () => {
    try {
        document.getElementById('btn-acquire-spectrum').disabled = true;
        document.getElementById('btn-acquire-spectrum').textContent = '⏳ Acquiring...';

        const response = await fetch('/device/spectrum', { method: 'POST' });

        if (response.ok) {
            const data = await response.json();
            currentData = data;
            renderDashboard(data);
            document.getElementById('device-modal').style.display = 'none';
        } else {
            const error = await response.json();
            alert('Acquisition failed: ' + error.detail);
        }
    } catch (err) {
        alert('Acquisition error: ' + err.message);
    } finally {
        document.getElementById('btn-acquire-spectrum').disabled = false;
        document.getElementById('btn-acquire-spectrum').textContent = '📊 Acquire Spectrum';
    }
});

// Clear device spectrum
document.getElementById('btn-clear-device').addEventListener('click', async () => {
    if (!confirm('Clear spectrum on device?')) return;

    try {
        await fetch('/device/clear', { method: 'POST' });
        alert('Device spectrum cleared');
    } catch (err) {
        alert('Clear error: ' + err.message);
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

// Check device status on modal open
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
