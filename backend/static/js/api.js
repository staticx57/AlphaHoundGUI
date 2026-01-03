/**
 * API client for AlphaHound device and analysis endpoints.
 * Handles file uploads, device communication, and spectrum analysis.
 * @class
 */
import { getActiveDevice } from './device_features.js';

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

    /**
     * Exports spectrum data as N42 XML file.
     * @param {Object} data - Spectrum data including counts, energies, metadata
     * @returns {Promise<Response>} N42 XML file response
     * @throws {Error} If N42 export fails
     */
    async exportN42(data) {
        const response = await fetch('/export/n42', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const errJson = await response.json();
            throw new Error(errJson.detail || 'N42 export failed');
        }
        return response;
    }

    // ============================================================
    // Server-Side Managed Acquisition API
    // ============================================================

    /**
     * Starts a server-managed acquisition.
     * Acquisition runs independently of browser - survives tab throttling, display sleep.
     * @param {number} durationMinutes - How long to acquire (in minutes)
     * @returns {Promise<Object>} Status object with success flag
     * @throws {Error} If start fails
     */
    async startManagedAcquisition(durationMinutes) {
        const response = await fetch('/device/acquisition/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duration_minutes: durationMinutes })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start acquisition');
        }
        return await response.json();
    }

    /**
     * Gets current acquisition status from server.
     * @returns {Promise<Object>} State including status, elapsed_seconds, progress_percent
     */
    async getAcquisitionStatus() {
        const response = await fetch('/device/acquisition/status');
        return await response.json();
    }

    /**
     * Stops current acquisition and finalizes.
     * @returns {Promise<Object>} Status with final_filename
     * @throws {Error} If stop fails
     */
    async stopManagedAcquisition() {
        const response = await fetch('/device/acquisition/stop', {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to stop acquisition');
        }
        return await response.json();
    }

    /**
     * Gets latest spectrum data from active acquisition.
     * Use for UI updates without affecting timing.
     * @returns {Promise<Object>} Spectrum data (counts, energies, peaks, isotopes)
     */
    async getAcquisitionData() {
        const response = await fetch('/device/acquisition/data');
        if (!response.ok) {
            return null; // No data available
        }
        return await response.json();
    }

    // Estimator / Detectors
    async getDetectors() {
        const response = await fetch('/detectors');
        return await response.json();
    }

    async estimateMDA(params) {
        const response = await fetch('/analyze/mda', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        if (!response.ok) throw new Error('MDA Analysis failed');
        return await response.json();
    }

    // ============================================================
    // Radiacode Device API
    // ============================================================

    /**
     * Checks if Radiacode library is available on server.
     * @returns {Promise<{available: boolean, ble_available: boolean, message: string}>}
     */
    async checkRadiacodeAvailable() {
        const response = await fetch('/radiacode/available');
        return await response.json();
    }

    /**
     * Scans for nearby Radiacode BLE devices.
     * @param {number} timeout - Scan timeout in seconds (default: 5)
     * @returns {Promise<Array<{name: string, address: string, rssi: number}>>} List of discovered devices
     * @throws {Error} If BLE not available or scan fails
     */
    async scanRadiacodeBLE(timeout = 5.0) {
        const response = await fetch(`/radiacode/scan-ble?timeout=${timeout}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'BLE scan failed');
        }
        return await response.json();
    }

    /**
     * Connects to Radiacode device.
     * @param {boolean} useBluetooth - Use Bluetooth instead of USB
     * @param {string|null} bluetoothMac - Bluetooth MAC address (required if useBluetooth=true)
     * @returns {Promise<Object>} Connection status and device info
     * @throws {Error} If connection fails
     */
    async connectRadiacode(useBluetooth = false, bluetoothMac = null) {
        const response = await fetch('/radiacode/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                use_bluetooth: useBluetooth,
                bluetooth_mac: bluetoothMac
            })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Radiacode connection failed');
        }
        return await response.json();
    }

    /**
     * Disconnects from Radiacode device.
     * @returns {Promise<Object>} Disconnect status
     */
    async disconnectRadiacode() {
        const response = await fetch('/radiacode/disconnect', { method: 'POST' });
        return await response.json();
    }

    /**
     * Gets Radiacode connection status.
     * @returns {Promise<Object>} Status including connected, device_info
     */
    async getRadiacodeStatus() {
        const response = await fetch('/radiacode/status');
        return await response.json();
    }

    /**
     * Gets current dose rate from Radiacode.
     * @returns {Promise<{dose_rate_uSv_h: number}>}
     * @throws {Error} If device not connected
     */
    async getRadiacodeDose() {
        const response = await fetch('/radiacode/dose');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get dose rate');
        }
        return await response.json();
    }

    /**
     * Gets spectrum from Radiacode with optional analysis.
     * @param {boolean} analyze - Run peak detection and isotope ID
     * @returns {Promise<Object>} Spectrum data with counts, energies, peaks, isotopes
     * @throws {Error} If device not connected
     */
    async getRadiacodeSpectrum(analyze = true) {
        const response = await fetch(`/radiacode/spectrum?analyze=${analyze}`);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get spectrum');
        }
        return await response.json();
    }

    /**
     * Clears spectrum on Radiacode device.
     * @returns {Promise<Object>} Status
     * @throws {Error} If clear fails
     */
    async clearRadiacodeSpectrum() {
        const response = await fetch('/radiacode/clear', { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to clear spectrum');
        }
        return await response.json();
    }

    /**
     * Resets dose accumulator on Radiacode device.
     * @returns {Promise<Object>} Status
     * @throws {Error} If reset fails
     */
    async resetRadiacodeDose() {
        const response = await fetch('/radiacode/reset-dose', { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to reset dose');
        }
        return await response.json();
    }

    /**
     * Set Radiacode display brightness (0-9).
     * @param {number} level - Brightness level
     * @returns {Promise<Object>} Status
     */
    async setRadiacodeBrightness(level) {
        const response = await fetch(`/radiacode/settings/brightness?level=${level}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set brightness');
        }
        return await response.json();
    }

    /**
     * Enable or disable sound alerts.
     * @param {boolean} enabled - True to enable sound
     * @returns {Promise<Object>} Status
     */
    async setRadiacodeSound(enabled) {
        const response = await fetch(`/radiacode/settings/sound?enabled=${enabled}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set sound');
        }
        return await response.json();
    }

    /**
     * Enable or disable vibration alerts.
     * @param {boolean} enabled - True to enable vibration
     * @returns {Promise<Object>} Status
     */
    async setRadiacodeVibration(enabled) {
        const response = await fetch(`/radiacode/settings/vibration?enabled=${enabled}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set vibration');
        }
        return await response.json();
    }

    /**
     * Set display auto-off timeout.
     * @param {number} seconds - Timeout in seconds
     * @returns {Promise<Object>} Status
     */
    async setRadiacodeDisplayTimeout(seconds) {
        const response = await fetch('/radiacode/settings/display-timeout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seconds })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set display timeout');
        }
        return await response.json();
    }

    /**
     * Set device language.
     * @param {string} language - 'en' or 'ru'
     * @returns {Promise<Object>} Status
     */
    async setRadiacodeLanguage(language) {
        const response = await fetch('/radiacode/settings/language', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ language })
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set language');
        }
        return await response.json();
    }

    /**
     * Get extended device info including accumulated dose and configuration.
     * @returns {Promise<Object>} Extended info
     */
    async getRadiacodeExtendedInfo() {
        const response = await fetch('/radiacode/info/extended');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get extended info');
        }
        return await response.json();
    }

    // ==================== Phase 1: Quick Win Features ====================

    /**
     * Gets accumulated spectrum data (long-term monitoring).
     * @returns {Promise<Object>} Accumulated spectrum with metadata
     */
    async getAccumulatedSpectrum() {
        const response = await fetch('/radiacode/spectrum/accumulated');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get accumulated spectrum');
        }
        return await response.json();
    }

    /**
     * Sets device display orientation.
     * @param {string} direction - 'normal', 'reversed', or 'auto'
     * @returns {Promise<Object>} Success status
     */
    async setDisplayDirection(direction) {
        const response = await fetch(`/radiacode/settings/display-direction?direction=${encodeURIComponent(direction)}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set display direction');
        }
        return await response.json();
    }

    /**
     * Synchronizes device clock with computer time.
     * @returns {Promise<Object>} Success status
     */
    async syncDeviceTime() {
        const response = await fetch('/radiacode/time/sync', {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to sync device time');
        }
        return await response.json();
    }

    /**
     * Gets hardware serial number.
     * @returns {Promise<{hw_serial_number: string}>}
     */
    async getHardwareSerial() {
        const response = await fetch('/radiacode/info/hw-serial');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get hardware serial');
        }
        return await response.json();
    }

    // ==================== Phase 2: Advanced Controls ====================

    /**
     * Get current energy calibration coefficients
     */
    async getEnergyCalibration() {
        const response = await fetch('/radiacode/calibration/energy');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get calibration');
        }
        return await response.json();
    }

    /**
     * Set energy calibration coefficients
     */
    async setEnergyCalibration(a0, a1, a2) {
        const response = await fetch(`/radiacode/calibration/energy?a0=${a0}&a1=${a1}&a2=${a2}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set calibration');
        }
        return await response.json();
    }

    /**
     * Set advanced sound control flags
     */
    async setSoundControl(search, detector, clicks) {
        const response = await fetch(`/radiacode/settings/sound-control?search=${search}&detector=${detector}&clicks=${clicks}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set sound control');
        }
        return await response.json();
    }

    /**
     * Set advanced vibration control flags
     */
    async setVibrationControl(search, detector) {
        const response = await fetch(`/radiacode/settings/vibration-control?search=${search}&detector=${detector}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to set vibration control');
        }
        return await response.json();
    }

    /**
     * Power off the Radiacode device
     */
    async powerOffDevice() {
        const response = await fetch('/radiacode/power/off', { method: 'POST' });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to power off device');
        }
        return await response.json();
    }

    // ==================== Phase 3: Info & Diagnostics ====================

    /**
     * Get device status flags
     */
    async getStatusFlags() {
        const response = await fetch('/radiacode/status/flags');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get status flags');
        }
        return await response.json();
    }

    /**
     * Get firmware signature info
     */
    async getFirmwareSignature() {
        const response = await fetch('/radiacode/info/fw-signature');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get firmware signature');
        }
        return await response.json();
    }

    /**
     * Get device text message/alert
     */
    async getTextMessage() {
        const response = await fetch('/radiacode/messages');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get text message');
        }
        return await response.json();
    }

    // ==================== Phase 4: System Features ====================

    /**
     * Get available SFR commands
     */
    async getAvailableCommands() {
        const response = await fetch('/radiacode/capabilities/commands');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get commands');
        }
        return await response.json();
    }

    /**
     * Get base time reference
     */
    async getBaseTime() {
        const response = await fetch('/radiacode/info/base-time');
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to get base time');
        }
        return await response.json();
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

    // ============================================================
    // Unified Device-Agnostic API Wrappers
    // Automatically route to correct device based on active connection
    // ============================================================

    /**
     * Clears spectrum on active device (device-agnostic).
     * Routes to correct endpoint based on connected device.
     * @returns {Promise<void>}
     * @throws {Error} If no device connected or operation fails
     */
    async clearSpectrumUnified() {
        const device = getActiveDevice();
        if (!device) throw new Error('No device connected');

        if (device === 'alphahound') {
            return this.clearDevice();
        } else if (device === 'radiacode') {
            return this.clearRadiacodeSpectrum();
        }
        throw new Error(`Unknown device type: ${device}`);
    }

    /**
     * Gets spectrum from active device (device-agnostic).
     * @param {number} countMinutes - Acquisition duration in minutes
     * @param {number} [actualDurationSeconds] - Actual elapsed time (AlphaHound only)
     * @returns {Promise<Object>} Spectrum data
     * @throws {Error} If no device connected or operation fails
     */
    async getSpectrumUnified(countMinutes, actualDurationSeconds = null) {
        const device = getActiveDevice();
        if (!device) throw new Error('No device connected');

        if (device === 'alphahound') {
            return this.getSpectrum(countMinutes, actualDurationSeconds);
        } else if (device === 'radiacode') {
            return this.getRadiacodeSpectrum();
        }
        throw new Error(`Unknown device type: ${device}`);
    }

    /**
     * Resets dose on active device (device-agnostic).
     * Only works for Radiacode.
     * @returns {Promise<void>}
     * @throws {Error} If device doesn't support dose reset or operation fails
     */
    async resetDoseUnified() {
        const device = getActiveDevice();
        if (!device) throw new Error('No device connected');

        if (device === 'radiacode') {
            return this.resetRadiacodeDose();
        }
        throw new Error('Reset Dose not supported on this device');
    }

    /**
     * Disconnects from active device (device-agnostic).
     * @returns {Promise<void>}
     */
    async disconnectUnified() {
        const device = getActiveDevice();
        if (!device) return; // Already disconnected

        if (device === 'alphahound') {
            return this.disconnectDevice();
        } else if (device === 'radiacode') {
            return this.disconnectRadiacode();
        }
    }

    /**
     * Gets current spectrum from active device without new acquisition (device-agnostic).
     * @returns {Promise<Object>} Spectrum data
     * @throws {Error} If no device connected or operation fails
     */
    async getCurrentSpectrumUnified() {
        const device = getActiveDevice();
        if (!device) throw new Error('No device connected');

        if (device === 'alphahound') {
            const response = await fetch('/device/spectrum/current');
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to get spectrum');
            }
            return await response.json();
        } else if (device === 'radiacode') {
            return this.getRadiacodeSpectrum(true);
        }
        throw new Error(`Unknown device type: ${device}`);
    }
}

export const api = new AlphaHoundAPI();
