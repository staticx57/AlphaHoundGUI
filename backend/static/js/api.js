/**
 * API client for AlphaHound device and analysis endpoints.
 * Handles file uploads, device communication, and spectrum analysis.
 * @class
 */
export class AlphaHoundAPI {
    /**
     * Creates an AlphaHoundAPI instance.
     * Initializes WebSocket state and event listeners.
     */
    constructor() {
        /** @type {WebSocket|null} */
        this.doseWebSocket = null;
        /** @type {number} */
        this.reconnectAttempts = 0;
        /** @type {number|null} */
        this.reconnectTimer = null;
        /** @type {{onDoseRate: Function|null, onConnectionStatus: Function|null}} */
        this.listeners = {
            onDoseRate: null,
            onConnectionStatus: null
        };
    }

    /**
     * Uploads a spectrum file (N42/CSV) for analysis.
     * @param {File} file - The file to upload
     * @returns {Promise<Object>} Parsed spectrum data with energies, counts, peaks, isotopes
     * @throws {Error} If upload fails
     */
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

    /**
     * Gets list of available serial ports.
     * @returns {Promise<{ports: string[]}>} Object containing array of port names
     */
    async getPorts() {
        const response = await fetch('/device/ports');
        return await response.json();
    }

    /**
     * Connects to AlphaHound device on specified port.
     * @param {string} port - Serial port name (e.g., 'COM3')
     * @returns {Promise<boolean>} True if connection successful
     * @throws {Error} If connection fails
     */
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

    /**
     * Disconnects from AlphaHound device.
     * Stops WebSocket monitoring.
     * @returns {Promise<void>}
     */
    async disconnectDevice() {
        await fetch('/device/disconnect', { method: 'POST' });
        this.stopDoseMonitoring();
    }

    /**
     * Gets current device connection status.
     * @returns {Promise<{connected: boolean, port: string|null}>} Connection status
     */
    async getDeviceStatus() {
        const response = await fetch('/device/status');
        return await response.json();
    }

    /**
     * Clears device spectrum buffer.
     * @returns {Promise<void>}
     */
    async clearDevice() {
        await fetch('/device/clear', { method: 'POST' });
    }

    /**
     * Gets current spectrum from device.
     * @param {number} countMinutes - Acquisition time in minutes
     * @param {number} [actualDurationSeconds] - Actual elapsed time in seconds (optional)
     * @returns {Promise<Object>} Spectrum data with energies, counts, peaks
     * @throws {Error} If poll fails
     */
    async getSpectrum(countMinutes, actualDurationSeconds = null) {
        const body = { count_minutes: countMinutes };
        if (actualDurationSeconds !== null) {
            body.actual_duration_s = actualDurationSeconds;
        }
        const response = await fetch('/device/spectrum', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (response.ok) {
            return await response.json();
        }
        throw new Error(`Poll failed: ${response.status} ${response.statusText}`);
    }

    /**
     * Performs Gaussian peak fitting on spectrum data.
     * @param {Object} data - Spectrum data with energies, counts, peaks
     * @returns {Promise<Object>} Fitted peak parameters
     * @throws {Error} If analysis fails
     */
    async fitPeaks(data) {
        const response = await fetch('/analyze/fit-peaks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error('Analysis failed');
        return await response.json();
    }

    /**
     * Subtracts background spectrum from source spectrum.
     * @param {number[]} sourceCounts - Source spectrum counts
     * @param {number[]} bgCounts - Background spectrum counts
     * @param {number} [scalingFactor=1.0] - Background scaling factor
     * @returns {Promise<{net_counts: number[]}>} Net counts after subtraction
     * @throws {Error} If subtraction fails
     */
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

    /**
     * Exports analysis report as PDF.
     * @param {Object} data - Report data including spectrum, peaks, isotopes
     * @returns {Promise<Response>} PDF file response
     * @throws {Error} If PDF generation fails
     */
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
