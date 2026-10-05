/**
 * API client for AlphaHound device and analysis endpoints.
 * Handles file uploads, device communication, and spectrum analysis.
 * @class
 */
import { debug } from './log.js';
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
     * Gets what the AlphaHound reports about itself (port, temperature, compensation, dose, CPS, log size).
     * @returns {Promise<Object>}
     * @throws {Error} with .status set (400 = not connected)
     */
    async getDeviceDetails() {
        const response = await fetch('/device/details');
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            const err = new Error(error.detail || 'Failed to get device details');
            err.status = response.status;
            throw err;
        }
        return await response.json();
    }

    /**
     * Clears the AlphaHound dose-rate history.
     * @returns {Promise<{cleared: number}>}
     */
    async clearDoseLog() {
        const response = await fetch('/device/dose/log/clear', { method: 'POST' });
        if (!response.ok) throw new Error('Failed to clear dose log');
        return await response.json();
    }

    /**
     * Sends one read-only command (D, DA, DB or P) and returns the raw reply lines.
     * @param {string} command
     * @returns {Promise<{command: string, lines: string[]}>}
     */
    async probeDevice(command) {
        const response = await fetch('/device/probe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(typeof error.detail === 'string' ? error.detail : 'Probe failed');
        }
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

    /**
     * Writes the spectrum as a PCF (GADRAS, InterSpec) or CHN (Ortec) file.
     * The response carries X-Calibration-Max-Error-keV: how far the stored polynomial is from the real energy axis.
     * @param {'pcf'|'chn'} format
     * @param {Object} data - counts, energies, metadata, filename
     * @returns {Promise<Response>}
     */
    async exportSpectrumFile(format, data) {
        const response = await fetch(`/export/${format}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const errJson = await response.json().catch(() => ({}));
            throw new Error(errJson.detail || `${format.toUpperCase()} export failed`);
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
            body: JSON.stringify({ duration_minutes: durationMinutes, device: getActiveDevice() || 'alphahound' })
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

    /**
     * The spectra the server saved (finished, in progress, interrupted), newest first.
     * @returns {Promise<Array<{name: string, kind: string, size_bytes: number, modified: string}>>}
     */
    async listSavedRuns() {
        const response = await fetch('/device/acquisitions');
        if (!response.ok) throw new Error(`Could not list saved runs (HTTP ${response.status})`);
        return (await response.json()).runs || [];
    }

    /**
     * One saved run, analysed like an uploaded file.
     * @param {string} name - file name from listSavedRuns
     */
    async openSavedRun(name) {
        const response = await fetch(`/device/acquisitions/${encodeURIComponent(name)}`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `Could not open ${name}`);
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
     * Gets device events (alarms etc.) newer than sinceId.
     * @returns {Promise<{events: Array}>}
     */
    async getRadiacodeEvents(sinceId = 0) {
        const response = await fetch(`/radiacode/events?since_id=${sinceId}`);
        if (!response.ok) throw new Error('Failed to get events');
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
            const err = new Error(error.detail || 'Failed to get dose rate');
            err.status = response.status;   // 400 = server says the device is not connected
            throw err;
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

    /** The device's own alarm thresholds (read-only; they are set on the device). */
    async getRadiacodeAlarmLimits() {
        const response = await fetch('/radiacode/alarm-limits');
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Failed to read the alarm limits');
        }
        return await response.json();
    }

    // ==================== Phase 1: Quick Win Features ====================

    /**
     * Gets accumulated spectrum data (long-term monitoring).
     * @returns {Promise<Object>} Accumulated spectrum with metadata
     */
    async getAccumulatedSpectrum(analyze = false) {
        const response = await fetch(`/radiacode/spectrum/accumulated?analyze=${analyze ? 'true' : 'false'}`);
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
    setupDoseWebSocket(onDoseRate, onConnectionStatus, onCps, onMessage) {
        this.listeners.onDoseRate = onDoseRate;
        this.listeners.onConnectionStatus = onConnectionStatus;
        if (onCps !== undefined) this.listeners.onCps = onCps;
        if (onMessage !== undefined) this.listeners.onMessage = onMessage;

        if (this.doseWebSocket) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/dose`;

        if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('connecting');

        this.doseWebSocket = new WebSocket(wsUrl);

        this.doseWebSocket.onopen = () => {
            debug('[WebSocket] Connected');
            this.reconnectAttempts = 0;
            if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('connected');
        };

        this.doseWebSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (this.listeners.onDoseRate) this.listeners.onDoseRate(data.dose_rate);
            if (this.listeners.onCps && data.cps !== undefined) this.listeners.onCps(data.cps);
            if (this.listeners.onMessage) this.listeners.onMessage(data);
        };

        this.doseWebSocket.onerror = (error) => {
            console.error('[WebSocket] Error:', error);
        };

        this.doseWebSocket.onclose = () => {
            debug('[WebSocket] Closed');
            this.doseWebSocket = null;
            if (this.listeners.onConnectionStatus) this.listeners.onConnectionStatus('disconnected');
            this.attemptReconnect();
        };
    }

    attemptReconnect() {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        debug(`[WebSocket] Reconnecting in ${delay}ms...`);

        this.reconnectTimer = setTimeout(() => {
            this.reconnectAttempts++;
            this.setupDoseWebSocket(this.listeners.onDoseRate, this.listeners.onConnectionStatus, this.listeners.onCps,
                this.listeners.onMessage);
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
