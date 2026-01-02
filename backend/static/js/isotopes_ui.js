
import { api } from './api.js';

export const isotopeUI = {
    init() {
        this.cacheDom();
        this.bindEvents();
    },

    cacheDom() {
        this.modal = document.getElementById('isotopes-modal');
        this.list = document.getElementById('custom-isotopes-list');
        this.btnOpen = document.getElementById('btn-manage-isotopes'); // In settings
        this.btnClose = document.getElementById('close-isotopes');
        this.form = document.getElementById('add-isotope-form');
        this.inputName = document.getElementById('iso-name');
        this.inputEnergies = document.getElementById('iso-energies');
    },

    bindEvents() {
        if (this.btnOpen) this.btnOpen.addEventListener('click', () => this.open());
        if (this.btnClose) this.btnClose.addEventListener('click', () => this.close());
        this.form.addEventListener('submit', (e) => this.handleAdd(e));

        // Import/Export buttons
        const btnImport = document.getElementById('btn-import-isotopes');
        const btnExport = document.getElementById('btn-export-isotopes');
        if (btnImport) btnImport.addEventListener('click', () => this.handleImport());
        if (btnExport) btnExport.addEventListener('click', () => this.handleExport());

        // Close on outside click
        window.addEventListener('click', (e) => {
            if (e.target === this.modal) this.close();
        });
    },

    async open() {
        this.modal.style.display = 'flex';
        await this.renderList();
    },

    close() {
        this.modal.style.display = 'none';
        this.form.reset();
    },

    async renderList() {
        this.list.innerHTML = '<p>Loading...</p>';
        try {
            const isotopes = await this.fetchCustomIsotopes();
            this.list.innerHTML = '';

            if (Object.keys(isotopes).length === 0) {
                this.list.innerHTML = '<p style="color:var(--text-secondary); padding:10px;">No custom isotopes added.</p>';
                return;
            }

            for (const [name, energies] of Object.entries(isotopes)) {
                const item = document.createElement('div');
                item.className = 'isotope-item';
                item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid var(--border-color);';

                item.innerHTML = `
                    <div>
                        <strong>${name}</strong>
                        <span style="font-size:0.85rem; color:var(--text-secondary); margin-left:8px;">
                            ${energies.join(', ')} keV
                        </span>
                    </div>
                    <button class="btn-delete-iso" data-name="${name}" style="background:transparent; border:none; color:#ef4444; cursor:pointer;"><img src="/static/icons/close.svg" class="icon" style="width: 14px; height: 14px;"></button>
                `;
                this.list.appendChild(item);
            }

            // Bind delete buttons
            this.list.querySelectorAll('.btn-delete-iso').forEach(btn => {
                btn.onclick = () => this.handleDelete(btn.dataset.name);
            });

        } catch (err) {
            this.list.innerHTML = `<p style="color:red">Error: ${err.message}</p>`;
        }
    },

    async handleAdd(e) {
        e.preventDefault();
        const name = this.inputName.value.trim();
        const energiesStr = this.inputEnergies.value;

        if (!name) return alert("Name required");

        // Parse energies
        const energies = energiesStr.split(',')
            .map(s => parseFloat(s.trim()))
            .filter(n => !isNaN(n) && n > 0);

        if (energies.length === 0) return alert("At least one valid energy (keV) required");

        try {
            await this.addCustomIsotope(name, energies);
            this.form.reset();
            this.renderList();
        } catch (err) {
            alert(err.message);
        }
    },

    async handleDelete(name) {
        if (!confirm(`Delete custom isotope ${name}?`)) return;
        try {
            await this.deleteCustomIsotope(name);
            this.renderList();
        } catch (err) {
            alert(err.message);
        }
    },

    // API Calls (Could be in api.js, but keeping it simple self-contained or moving later)
    async fetchCustomIsotopes() {
        const res = await fetch('/isotopes/custom');
        if (!res.ok) throw new Error("Failed to load");
        return await res.json();
    },

    async addCustomIsotope(name, energies) {
        const res = await fetch('/isotopes/custom', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, energies })
        });
        if (!res.ok) throw new Error("Failed to add");
    },

    async deleteCustomIsotope(name) {
        const res = await fetch(`/isotopes/custom/${name}`, { method: 'DELETE' });
        if (!res.ok) throw new Error("Failed to delete");
    },

    // Export all custom isotopes as downloadable JSON
    async handleExport() {
        try {
            const res = await fetch('/isotopes/custom/export');
            if (!res.ok) throw new Error("Export failed");
            const data = await res.json();

            if (data.count === 0) {
                alert("No custom isotopes to export.");
                return;
            }

            // Create downloadable file
            const blob = new Blob([JSON.stringify(data.isotopes, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'custom_isotopes.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            alert("Export error: " + err.message);
        }
    },

    // Import custom isotopes from JSON file
    async handleImport() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';

        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const data = JSON.parse(text);

                const res = await fetch('/isotopes/custom/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (!res.ok) throw new Error("Import failed");

                const result = await res.json();
                alert(`Successfully imported ${result.imported} isotope(s).`);
                this.renderList();
            } catch (err) {
                alert("Import error: " + err.message);
            }
        };

        input.click();
    }
};
