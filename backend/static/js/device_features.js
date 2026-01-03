/**
 * Device Features Module
 * 
 * Handles conditional UI rendering based on connected device capabilities.
 * Unsupported features are shown as disabled (greyed out, unclickable) buttons.
 */

// Device capability definitions
const DEVICE_CAPABILITIES = {
    alphahound: {
        timedAcquisition: true,
        serverManagedAcquisition: true,
        temperature: true,
        displayModeToggle: true,
        clearSpectrum: true,
        doseReset: false,
        deviceSettings: false,
        bleConnection: false
    },
    radiacode: {
        timedAcquisition: true,
        serverManagedAcquisition: true,
        temperature: false,
        displayModeToggle: false,
        clearSpectrum: true,
        doseReset: true,
        deviceSettings: true,
        brightness: true,
        sound: true,
        vibration: true,
        displayTimeout: true,
        language: true,
        accumulatedDose: true,
        deviceConfig: true,
        bleConnection: true,
        // Phase 1 features
        accumulatedSpectrum: true,
        displayOrientation: true,
        timeSync: true,
        hwSerial: true,
        // Phase 2
        energyCalibration: true,
        advancedSoundControl: true,
        advancedVibrationControl: true,
        powerControl: true,
        // Phase 3
        advancedInfo: true,
        textMessages: true,
        statusFlags: true,
        fwSignature: true
    },
};

// Current active device type
let activeDeviceType = null;

/**
 * Update UI elements based on device capabilities.
 * Elements with data-device-feature attributes will be enabled/disabled.
 * 
 * @param {string} deviceType - 'alphahound' or 'radiacode'
 */
export function updateDeviceUI(deviceType) {
    activeDeviceType = deviceType;
    const caps = DEVICE_CAPABILITIES[deviceType];

    if (!caps) {
        console.warn(`[DeviceFeatures] Unknown device type: ${deviceType}`);
        return;
    }

    console.log(`[DeviceFeatures] Updating UI for ${deviceType}`);

    // Enable the unified controls panel (remove disconnected state)
    const controlsPanel = document.getElementById('unified-device-controls');
    if (controlsPanel) {
        controlsPanel.classList.remove('device-disconnected');
    }

    // Find all elements with data-device-feature attribute
    document.querySelectorAll('[data-device-feature]').forEach(el => {
        const feature = el.dataset.deviceFeature;
        const supported = caps[feature] ?? false;

        // Apply disabled state based on capability
        el.disabled = !supported;
        el.classList.toggle('feature-disabled', !supported);

        // Update title to indicate why it's disabled
        if (!supported) {
            const originalTitle = el.dataset.originalTitle || el.title;
            el.dataset.originalTitle = originalTitle;
            el.title = `Not available on ${deviceType}`;
        } else if (el.dataset.originalTitle) {
            el.title = el.dataset.originalTitle;
        }

        // Control visibility via display style
        if (supported) {
            el.style.display = ''; // Reset to default/CSS value
        } else {
            el.style.display = 'none'; // Hide if not supported
        }
    });
}

/**
 * Reset all feature elements to disabled state (for when no device connected).
 * All controls become greyed out and disabled.
 */
export function resetDeviceUI() {
    activeDeviceType = null;

    // Add disconnected state to controls panel
    const controlsPanel = document.getElementById('unified-device-controls');
    if (controlsPanel) {
        controlsPanel.classList.add('device-disconnected');
    }

    // Disable all feature-gated elements
    document.querySelectorAll('[data-device-feature]').forEach(el => {
        el.disabled = true;
        el.classList.add('feature-disabled');
        el.style.display = 'none'; // Hide all feature elements on disconnect
        if (el.dataset.originalTitle) {
            el.title = el.dataset.originalTitle;
        }
    });
}

/**
 * Check if a specific feature is supported by the active device.
 * 
 * @param {string} feature - Feature name from DEVICE_CAPABILITIES
 * @returns {boolean} True if supported or no device active
 */
export function isFeatureSupported(feature) {
    if (!activeDeviceType) return true; // No device = allow all
    const caps = DEVICE_CAPABILITIES[activeDeviceType];
    return caps?.[feature] ?? false;
}

/**
 * Get current active device type.
 * 
 * @returns {string|null} 'alphahound', 'radiacode', or null
 */
export function getActiveDevice() {
    return activeDeviceType;
}

/**
 * Get capabilities for a device type.
 * 
 * @param {string} deviceType - 'alphahound' or 'radiacode'
 * @returns {Object} Capabilities object
 */
export function getCapabilities(deviceType) {
    return DEVICE_CAPABILITIES[deviceType] || {};
}

// Export for use in other modules
export { DEVICE_CAPABILITIES };
