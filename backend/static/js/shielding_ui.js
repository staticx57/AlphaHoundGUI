/** Shielding and emissions modal: material and thickness in, transmission and alpha/beta reach out. State lives here. */
import { notifyAuto } from './dialogs.js';
import { formatLength, formatPercent, describeShielding, describeEmissions } from './shielding_view.js';

const MAX_LINES_SHOWN = 12;
let materials = null;                // [{key, name, density_g_cm3}] from the server, loaded once

function cell(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function table(headers, rows) {
    const t = document.createElement('table');
    t.className = 'data-table';
    const head = t.createTHead().insertRow();
    headers.forEach((h) => head.appendChild(cell('th', h)));
    const body = t.createTBody();
    rows.forEach((r) => {
        const tr = body.insertRow();
        r.forEach((v) => tr.appendChild(cell('td', v)));
    });
    return t;
}

async function postJson(url, payload) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join('; ') : body.detail;
        throw new Error(detail || `Request failed (${response.status})`);
    }
    return body;
}

async function loadMaterials() {
    if (materials) return;
    const response = await fetch('/analyze/shielding/materials');
    if (!response.ok) throw new Error('Could not load the material list');
    materials = (await response.json()).materials;
    const select = document.getElementById('shield-material');
    select.replaceChildren(...materials.map((m) => {
        const option = document.createElement('option');
        option.value = m.key;
        option.textContent = `${m.name} (${m.density_g_cm3} g/cm³)`;
        return option;
    }));
    select.value = 'lead';
}

function syncMode() {
    const isotope = document.getElementById('shield-mode').value === 'isotope';
    document.getElementById('shield-isotope-field').style.display = isotope ? '' : 'none';
    document.getElementById('shield-energy-field').style.display = isotope ? 'none' : '';
}

function renderShielding(result, materialName, into) {
    const sentence = document.createElement('p');
    sentence.textContent = describeShielding(result, materialName);
    into.appendChild(sentence);
    if (!Array.isArray(result.lines)) return;
    const shown = [...result.lines].sort((a, b) => b.intensity_percent - a.intensity_percent).slice(0, MAX_LINES_SHOWN);
    into.appendChild(table(['Energy (keV)', 'Intensity', 'Gets through', 'Half-value layer'],
        shown.map((l) => [l.energy_kev.toFixed(1), `${Number(l.intensity_percent.toPrecision(3))} %`, formatPercent(l.transmission), formatLength(l.half_value_layer_cm)])));
    if (result.lines.length > shown.length) {
        into.appendChild(cell('p', `${result.lines.length - shown.length} weaker lines not shown; they are included in the total.`)).className = 'settings-hint';
    }
}

function renderEmissions(emissions, into) {
    const heading = cell('h4', 'Alpha and beta emissions');
    heading.style.margin = '1.25rem 0 0.5rem';
    into.append(heading, cell('p', describeEmissions(emissions)));
    if (emissions.alphas.length) {
        into.appendChild(table(['Alpha energy (MeV)', 'Intensity', 'Range in air'],
            emissions.alphas.map((a) => [(a.energy_kev / 1000).toFixed(3), `${Number(a.intensity_percent.toPrecision(3))} %`, formatLength(a.range_air_cm)])));
    }
    if (emissions.betas.length) {
        into.appendChild(table(['Beta endpoint (keV)', 'Mean (keV)', 'Intensity', 'Farthest in air', 'Farthest in aluminium'],
            emissions.betas.map((b) => [b.endpoint_energy_kev.toFixed(0), b.mean_energy_kev.toFixed(0), `${Number(b.intensity_percent.toPrecision(3))} %`,
                formatLength(b.max_range_air_cm), formatLength(b.max_range_aluminium_mm / 10)])));
    }
}

export async function runShielding() {
    const out = document.getElementById('shield-result');
    const isotopeMode = document.getElementById('shield-mode').value === 'isotope';
    const thickness = parseFloat(document.getElementById('shield-thickness').value);
    const material = document.getElementById('shield-material').value;
    const materialName = materials?.find((m) => m.key === material)?.name;
    if (!(thickness >= 0)) return notifyAuto('The thickness must be zero or more.');
    const request = { material, thickness_cm: thickness };
    if (isotopeMode) {
        request.isotope = document.getElementById('shield-isotope').value.trim();
        if (!request.isotope) return notifyAuto('Enter an isotope, for example Cs-137.');
    } else {
        request.energy_kev = parseFloat(document.getElementById('shield-energy').value);
        if (!(request.energy_kev > 0)) return notifyAuto('Enter a photon energy in keV.');
    }
    out.replaceChildren(cell('p', 'Calculating…'));
    try {
        // an isotope with no gamma lines (Sr-90) still has emissions to show: its shielding request fails, its emissions do not
        const shieldingRequest = postJson('/analyze/shielding', request).catch((e) => ({ error: e.message }));
        const emissionsRequest = isotopeMode
            ? fetch(`/analyze/emissions?isotope=${encodeURIComponent(request.isotope)}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
            : Promise.resolve(null);
        const [shielding, emissions] = await Promise.all([shieldingRequest, emissionsRequest]);
        const fragment = document.createDocumentFragment();
        if (shielding.error) {
            fragment.appendChild(cell('p', emissions ? `Gamma shielding: ${shielding.error}` : shielding.error));
        } else {
            renderShielding(shielding, materialName, fragment);
        }
        if (emissions) renderEmissions(emissions, fragment);
        if (shielding.error && !emissions) notifyAuto(`Error: ${shielding.error}`);
        out.replaceChildren(fragment);
    } catch (err) {
        out.replaceChildren();
        notifyAuto(`Error: ${err.message}`);
    }
}

export function setupShieldingTool() {
    const modal = document.getElementById('shield-modal');
    const open = document.getElementById('btn-shield-tool');
    if (!modal || !open) return;
    const close = () => { modal.style.display = 'none'; open.focus(); };
    open.addEventListener('click', async () => {
        modal.style.display = 'flex';
        try {
            await loadMaterials();
        } catch (err) {
            notifyAuto(`Error: ${err.message}`);
        }
        syncMode();
        document.getElementById('shield-isotope').focus();
    });
    document.getElementById('close-shield').addEventListener('click', close);
    modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
    modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
    document.getElementById('shield-mode').addEventListener('change', syncMode);
    document.getElementById('btn-run-shield').addEventListener('click', runShielding);
    modal.querySelectorAll('input').forEach((input) => input.addEventListener('keydown', (e) => { if (e.key === 'Enter') runShielding(); }));
}
