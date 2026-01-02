/**
 * N42 Metadata Editor UI Module
 * 
 * Provides a modal interface for editing N42 file metadata
 * including timestamps, instrument info, sample description, and location.
 */

export class N42MetadataEditor {
    constructor() {
        this.currentXml = null;
        this.currentMetadata = {};
        this.onSaveCallback = null;
        this._createModal();
        this._bindEvents();
    }

    _createModal() {
        // Create modal if it doesn't exist
        if (document.getElementById('n42-editor-modal')) return;

        const modal = document.createElement('div');
        modal.id = 'n42-editor-modal';
        modal.className = 'modal';
        modal.style.display = 'none';

        modal.innerHTML = `
            <div class="modal-content" style="max-width: 800px; max-height: 85vh; overflow-y: auto; padding: 1.5rem;">
                <div class="modal-header" style="margin-bottom: 2rem;">
                    <h2 style="margin: 0; display: flex; align-items: center; gap: 0.75rem; color: var(--primary-color);">
                        <img src="/static/icons/pencil.svg" class="icon" style="width: 20px; height: 20px;"> N42 Metadata Editor
                    </h2>
                    <button id="close-n42-editor" class="close-btn" style="background: none; border: none; cursor: pointer; color: var(--text-secondary); line-height: 1;"><img src="/static/icons/close.svg" class="icon" style="width: 16px; height: 16px;"></button>
                </div>
                
                <div class="modal-body" style="padding: 1rem;">
                    <!-- Timestamp Section -->
                    <fieldset style="border: 1px solid var(--border-color); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; background: rgba(255,255,255,0.02);">
                        <legend style="color: var(--accent-color); font-weight: 600; padding: 0 0.5rem;"><img src="/static/icons/calendar.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Timestamp</legend>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Start Date</label>
                                <input type="date" id="n42-start-date" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Start Time</label>
                                <input type="time" id="n42-start-time" step="1" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-top: 1rem;">
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Live Time (s)</label>
                                <input type="number" id="n42-live-time" min="0" step="0.1" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Real Time (s)</label>
                                <input type="number" id="n42-real-time" min="0" step="0.1" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                        </div>
                        <button id="n42-use-now" style="margin-top: 1rem; padding: 0.5rem 1rem; background: var(--accent-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.875rem; font-weight: 600;">
                            Use Current Time
                        </button>
                    </fieldset>

                    <!-- Instrument Info -->
                    <fieldset style="border: 1px solid var(--border-color); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; background: rgba(255,255,255,0.02);">
                        <legend style="color: var(--accent-color); font-weight: 600; padding: 0 0.5rem;"><img src="/static/icons/wrench.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Instrument</legend>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Manufacturer</label>
                                <input type="text" id="n42-manufacturer" placeholder="RadView Detection" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Model</label>
                                <input type="text" id="n42-model" placeholder="AlphaHound" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                            </div>
                        </div>
                        <div style="margin-top: 1rem;">
                            <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Serial Number</label>
                            <input type="text" id="n42-serial" placeholder="" style="width: 100%; padding: 0.6rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-color);">
                        </div>
                    </fieldset>

                    <!-- Sample Description -->
                    <fieldset style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <legend style="color: var(--accent-color); font-weight: 600;"><img src="/static/icons/flask.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Sample</legend>
                        <div>
                            <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Description</label>
                            <textarea id="n42-sample-desc" rows="2" placeholder="Describe the measured sample..." style="width: 100%; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-color); resize: vertical;"></textarea>
                        </div>
                    </fieldset>

                    <!-- Location -->
                    <fieldset style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                        <legend style="color: var(--accent-color); font-weight: 600;"><img src="/static/icons/pin.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Location</legend>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Latitude</label>
                                <input type="number" id="n42-latitude" step="0.000001" placeholder="40.7128" style="width: 100%; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-color);">
                            </div>
                            <div>
                                <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Longitude</label>
                                <input type="number" id="n42-longitude" step="0.000001" placeholder="-74.0060" style="width: 100%; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-color);">
                            </div>
                        </div>
                        <button id="n42-get-location" style="margin-top: 0.75rem; padding: 0.4rem 0.8rem; background: var(--card-bg); border: 1px solid var(--accent-color); color: var(--accent-color); border-radius: 4px; cursor: pointer; font-size: 0.875rem;">
                            <img src="/static/icons/pin.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Get Current Location
                        </button>
                    </fieldset>

                    <!-- Remarks -->
                    <fieldset style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem;">
                        <legend style="color: var(--accent-color); font-weight: 600;"><img src="/static/icons/comment.svg" class="icon" style="width: 14px; height: 14px; vertical-align: middle;"> Notes</legend>
                        <div>
                            <label style="display: block; font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Remarks/Comments</label>
                            <textarea id="n42-remarks" rows="2" placeholder="Add notes about this measurement..." style="width: 100%; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-color); resize: vertical;"></textarea>
                        </div>
                    </fieldset>
                </div>

                <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem; border-top: 1px solid var(--border-color);">
                    <button id="n42-cancel-btn" style="padding: 0.5rem 1rem; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; color: var(--text-color);">Cancel</button>
                    <button id="n42-save-btn" style="padding: 0.5rem 1.5rem; background: var(--accent-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Save Changes</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    }

    _bindEvents() {
        // Close button
        document.getElementById('close-n42-editor')?.addEventListener('click', () => this.hide());
        document.getElementById('n42-cancel-btn')?.addEventListener('click', () => this.hide());

        // Save button
        document.getElementById('n42-save-btn')?.addEventListener('click', () => this._handleSave());

        // Use current time button
        document.getElementById('n42-use-now')?.addEventListener('click', () => {
            const now = new Date();
            document.getElementById('n42-start-date').value = now.toISOString().split('T')[0];
            document.getElementById('n42-start-time').value = now.toTimeString().slice(0, 8);
        });

        // Get location button
        document.getElementById('n42-get-location')?.addEventListener('click', () => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        document.getElementById('n42-latitude').value = pos.coords.latitude.toFixed(6);
                        document.getElementById('n42-longitude').value = pos.coords.longitude.toFixed(6);
                    },
                    (err) => {
                        alert(`Location error: ${err.message}`);
                    }
                );
            } else {
                alert('Geolocation not supported by this browser.');
            }
        });

        // Close on background click
        const modal = document.getElementById('n42-editor-modal');
        modal?.addEventListener('click', (e) => {
            if (e.target === modal) this.hide();
        });
    }

    /**
     * Open the editor with an N42 file's content
     * @param {string} xmlContent - N42 XML content
     * @param {Function} onSave - Callback with modified XML on save
     */
    async show(xmlContent, onSave) {
        this.currentXml = xmlContent;
        this.onSaveCallback = onSave;

        // Fetch current metadata from backend
        try {
            const response = await fetch('/n42/metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ xml_content: xmlContent })
            });

            if (response.ok) {
                const data = await response.json();
                this.currentMetadata = data.metadata || {};
                this._populateFields();
            }
        } catch (err) {
            console.error('[N42 Editor] Failed to load metadata:', err);
        }

        document.getElementById('n42-editor-modal').style.display = 'flex';
    }

    hide() {
        document.getElementById('n42-editor-modal').style.display = 'none';
    }

    _populateFields() {
        const m = this.currentMetadata;

        // Timestamp
        if (m.start_time) {
            try {
                const dt = new Date(m.start_time);
                document.getElementById('n42-start-date').value = dt.toISOString().split('T')[0];
                document.getElementById('n42-start-time').value = dt.toTimeString().slice(0, 8);
            } catch (e) { }
        }

        // Parse duration strings like "PT60.000S"
        const parseDuration = (str) => {
            if (!str) return '';
            const match = str.match(/PT?(\d+\.?\d*)S?/i);
            return match ? parseFloat(match[1]) : str;
        };

        document.getElementById('n42-live-time').value = parseDuration(m.live_time) || '';
        document.getElementById('n42-real-time').value = parseDuration(m.real_time) || '';

        // Instrument
        document.getElementById('n42-manufacturer').value = m.manufacturer || '';
        document.getElementById('n42-model').value = m.model || '';
        document.getElementById('n42-serial').value = m.serialnumber || '';

        // Remarks
        const remarks = m.remarks || [];
        document.getElementById('n42-remarks').value = Array.isArray(remarks) ? remarks.join('\n') : remarks;
    }

    async _handleSave() {
        const dateVal = document.getElementById('n42-start-date').value;
        const timeVal = document.getElementById('n42-start-time').value;
        let startTime = null;
        if (dateVal && timeVal) {
            startTime = `${dateVal}T${timeVal}`;
        } else if (dateVal) {
            startTime = `${dateVal}T00:00:00`;
        }

        const liveTime = parseFloat(document.getElementById('n42-live-time').value) || null;
        const realTime = parseFloat(document.getElementById('n42-real-time').value) || null;

        const updateData = {
            xml_content: this.currentXml,
            start_time: startTime,
            live_time_s: liveTime,
            real_time_s: realTime,
            manufacturer: document.getElementById('n42-manufacturer').value || null,
            model: document.getElementById('n42-model').value || null,
            serial_number: document.getElementById('n42-serial').value || null,
            sample_description: document.getElementById('n42-sample-desc').value || null,
            latitude: parseFloat(document.getElementById('n42-latitude').value) || null,
            longitude: parseFloat(document.getElementById('n42-longitude').value) || null
        };

        // Handle remarks
        const remarksText = document.getElementById('n42-remarks').value.trim();
        if (remarksText) {
            updateData.remarks = remarksText.split('\n').filter(r => r.trim());
        }

        try {
            const response = await fetch('/n42/update-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updateData)
            });

            if (response.ok) {
                const data = await response.json();
                if (this.onSaveCallback) {
                    this.onSaveCallback(data.xml_content);
                }
                this.hide();
                alert('Metadata updated successfully!');
            } else {
                const err = await response.json();
                alert(`Error: ${err.detail}`);
            }
        } catch (err) {
            console.error('[N42 Editor] Save failed:', err);
            alert('Failed to save metadata.');
        }
    }
}

// Export singleton instance
export const n42MetadataEditor = new N42MetadataEditor();
