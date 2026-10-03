
/**
 * Drag and drop, the upload button and the file input.
 *
 * Everything shared with main.js is passed in, not imported: state through getters and setters, the
 * stateful singletons (ui, chartManager) as they are, and main.js functions it calls.
 *
 * @param {object} deps
 * @param {*} deps.handleFile
 * @param {*} deps.getCurrentData
 */
export function setupFileUpload({ handleFile, getCurrentData } = {}) {
    // File Upload & Drag-and-Drop
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    // Upload button in header
    const btnUpload = document.getElementById('btn-upload-file');
    if (btnUpload && fileInput) {
        btnUpload.addEventListener('click', () => fileInput.click());
    }

    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            if (e.dataTransfer.files.length) {
                handleFile(e.dataTransfer.files[0]);
            }
        });

        // Delegate click to file input - only if clicking on drop zone itself or allowed children
        dropZone.addEventListener('click', (e) => {
            // Get the current file input (may have been recreated)
            const currentFileInput = document.getElementById('file-input');
            // Only trigger if not clicking directly on the input itself
            if (currentFileInput && e.target !== currentFileInput && !e.target.closest('input[type="file"]')) {
                currentFileInput.click();
            }
        });
    }

    // Use event delegation for file input since it may be recreated
    document.addEventListener('change', (e) => {
        if (e.target && e.target.id === 'file-input') {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
                // Reset the input value so the same file can be selected again
                e.target.value = '';
            }
        }
    });

    document.getElementById('btn-export-json').addEventListener('click', () => {
        if (!getCurrentData()) return;
        const blob = new Blob([JSON.stringify(getCurrentData(), null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'spectrum_data.json';
        a.click();
        URL.revokeObjectURL(url);
    });
}
