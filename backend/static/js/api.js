export class AlphaHoundAPI {
    constructor() {
        this.doseWebSocket = null;
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.listeners = {
            onDoseRate: null,
            onConnectionStatus: null
        };
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
        return await response.json();
    }

    async getPorts() {
        const response = await fetch('/device/ports');
        return await response.json();
    }

    async connectDevice(port) {
        const response = await fetch('/device/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Connection failed');
        }
        return true;
    }

    async disconnectDevice() {
        await fetch('/device/disconnect', { method: 'POST' });
        this.stopDoseMonitoring();
    }

    async getDeviceStatus() {
        const response = await fetch('/device/status');
        return await response.json();
    }

    async clearDevice() {
        await fetch('/device/clear', { method: 'POST' });
    }

    async getSpectrum(countMinutes) {
        const response = await fetch('/device/spectrum', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count_minutes: countMinutes })
        });
        if (response.ok) {
            return await response.json();
        }
        throw new Error(`Poll failed: ${response.status} ${response.statusText}`);
    }

    async fitPeaks(data) {
        const response = await fetch('/analyze/fit-peaks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error('Analysis failed');
        return await response.json();
    }

    async subtractBackground(sourceCounts, bgCounts, scalingFactor = 1.0) {
        const response = await fetch('/analyze/subtract-background', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_counts: sourceCounts,
                background_counts: bgCounts,
                scaling_factor: scalingFactor
            })
        });
        if (!response.ok) throw new Error('Background subtraction failed');
        return await response.json();
    }

    async exportPDF(data) {
        const response = await fetch('/export/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const errJson = await response.json();
            throw new Error(errJson.detail || 'PDF generation failed');
        }
        return response;
    }

    // WebSocket Logic
    setupDoseWebSocket(onDoseRate, onConnectionStatus) {
        this.listeners.onDoseRate = onDoseRate;
        this.listeners.onConnectionStatus = onConnectionStatus;

        if (this.doseWebSocket) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/dose`;

        if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('connecting');

        this.doseWebSocket = new WebSocket(wsUrl);

        this.doseWebSocket.onopen = () => {
            console.log('[WebSocket] Connected');
            this.reconnectAttempts = 0;
            if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('connected');
        };

        this.doseWebSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (this.listeners.onDoseRate) this.listeners.onDoseRate(data.dose_rate);
        };

        this.doseWebSocket.onerror = (error) => {
            console.error('[WebSocket] Error:', error);
        };

        this.doseWebSocket.onclose = () => {
            console.log('[WebSocket] Closed');
            this.doseWebSocket = null;
            if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('disconnected');
            this.attemptReconnect();
        };
    }

    attemptReconnect() {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        console.log(`[WebSocket] Reconnecting in ${delay}ms...`);

        this.reconnectTimer = setTimeout(() => {
            this.reconnectAttempts++;
            this.setupDoseWebSocket(this.listeners.onDoseRate, this.listeners.onConnectionStatus);
        }, delay);
    }

    stopDoseMonitoring() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.reconnectAttempts = 0;

        if (this.doseWebSocket) {
            this.doseWebSocket.onclose = null;
            this.doseWebSocket.close();
            this.doseWebSocket = null;
        }
    }
}

export const api = new AlphaHoundAPI();
