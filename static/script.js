document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadSection = document.getElementById('upload-section');
    const loadingState = document.getElementById('loading-state');
    const resultSection = document.getElementById('result-section');
    const btnReset = document.getElementById('btn-reset');
    const btnDownload = document.getElementById('btn-download');
    const tabs = document.querySelectorAll('.tab');
    const viewPanels = document.querySelectorAll('.view-panel');
    
    // Outputs
    const jsonOutput = document.getElementById('json-output');
    const markdownOutput = document.getElementById('markdown-output');
    const tablesContainer = document.getElementById('tables-container');
    const tableCountSpan = document.getElementById('table-count');

    const flagsContainer = document.getElementById('flags-container');
    const flagCountSpan = document.getElementById('flag-count');
    const riskBanner = document.getElementById('risk-banner');

    let currentJsonData = null;

    // Drag & Drop Events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFiles(e.target.files);
    });

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) handleFiles(files);
    }

    function handleFiles(files) {
        const file = files[0];
        if (file.type !== 'application/pdf') {
            alert('Please upload a valid PDF file.');
            return;
        }
        
        if (file.size > 16 * 1024 * 1024) {
            alert('File size exceeds 16MB limit.');
            return;
        }

        uploadFile(file);
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        // UI State Update
        dropZone.style.display = 'none';
        loadingState.style.display = 'block';

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || 'Failed to process file');
            }

            const data = await response.json();
            currentJsonData = data;
            displayResults(data);

        } catch (error) {
            console.error(error);
            alert(`Error: ${error.message}`);
            resetUI();
        }
    }

    function displayResults(data) {
        uploadSection.style.display = 'none';
        resultSection.style.display = 'flex';

        renderFraud(data.fraud_analysis);

        // Display JSON
        jsonOutput.textContent = JSON.stringify(data, null, 2);

        // Display Markdown
        markdownOutput.textContent = data.markdown || 'No markdown extracted.';

        // Display Tables
        tableCountSpan.textContent = data.table_count || 0;
        renderTables(data.tables);
    }

    function renderFraud(fraud) {
        flagsContainer.innerHTML = '';
        if (!fraud) {
            flagCountSpan.textContent = 0;
            riskBanner.className = 'risk-banner risk-unknown';
            document.getElementById('risk-score').textContent = '–';
            document.getElementById('risk-level').textContent = 'Not analysed';
            document.getElementById('risk-summary').textContent = 'Fraud analysis was unavailable for this document.';
            return;
        }
        const level = fraud.risk_level || 'low';
        riskBanner.className = `risk-banner risk-${level}`;
        document.getElementById('risk-score').textContent = fraud.risk_score;
        document.getElementById('risk-level').textContent = `${level.charAt(0).toUpperCase() + level.slice(1)} risk`;
        document.getElementById('risk-summary').textContent = fraud.flag_count
            ? `${fraud.flag_count} indicator(s) need review.`
            : 'No fraud indicators detected.';
        flagCountSpan.textContent = fraud.flag_count || 0;

        if (!fraud.flags || !fraud.flags.length) {
            flagsContainer.innerHTML = '<p style="color: var(--text-muted)">All consistency checks passed.</p>';
            return;
        }
        fraud.flags.forEach(flag => {
            const card = document.createElement('div');
            card.className = `flag-card sev-${flag.severity}`;
            const head = document.createElement('div');
            head.className = 'flag-head';
            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.textContent = flag.severity;
            const msg = document.createElement('span');
            msg.textContent = flag.message;
            head.append(badge, msg);
            card.appendChild(head);
            if (flag.evidence !== null && flag.evidence !== undefined) {
                const ev = document.createElement('code');
                ev.textContent = `${flag.rule}: ${typeof flag.evidence === 'string' ? flag.evidence : JSON.stringify(flag.evidence)}`;
                card.appendChild(ev);
            }
            flagsContainer.appendChild(card);
        });
    }

    function renderTables(tables) {
        tablesContainer.innerHTML = '';
        
        if (!tables || tables.length === 0) {
            tablesContainer.innerHTML = '<p style="color: var(--text-muted)">No tables extracted.</p>';
            return;
        }

        tables.forEach(table => {
            const wrapper = document.createElement('div');
            wrapper.className = 'table-wrapper';
            
            const title = document.createElement('h4');
            title.textContent = `Table ${table.table_index} (Page ${table.page_no})`;
            wrapper.appendChild(title);

            if (table.records && table.records.length > 0) {
                const tableEl = document.createElement('table');
                tableEl.className = 'data-table';
                
                // Header
                const thead = document.createElement('thead');
                const headerRow = document.createElement('tr');
                const keys = Object.keys(table.records[0]);
                keys.forEach(key => {
                    const th = document.createElement('th');
                    th.textContent = key;
                    headerRow.appendChild(th);
                });
                thead.appendChild(headerRow);
                tableEl.appendChild(thead);

                // Body
                const tbody = document.createElement('tbody');
                table.records.forEach(record => {
                    const tr = document.createElement('tr');
                    keys.forEach(key => {
                        const td = document.createElement('td');
                        td.textContent = record[key] !== null ? record[key] : '';
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                tableEl.appendChild(tbody);
                
                wrapper.appendChild(tableEl);
            } else {
                const empty = document.createElement('p');
                empty.textContent = 'Empty table structure.';
                empty.style.color = 'var(--text-muted)';
                wrapper.appendChild(empty);
            }

            tablesContainer.appendChild(wrapper);
        });
    }

    function resetUI() {
        uploadSection.style.display = 'block';
        dropZone.style.display = 'block';
        loadingState.style.display = 'none';
        resultSection.style.display = 'none';
        fileInput.value = '';
        currentJsonData = null;
    }

    // Event Listeners
    btnReset.addEventListener('click', resetUI);

    btnDownload.addEventListener('click', () => {
        if (!currentJsonData) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentJsonData, null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", "extracted_claim.json");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    });

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            viewPanels.forEach(p => p.classList.remove('active'));
            
            tab.classList.add('active');
            const target = tab.getAttribute('data-target');
            document.getElementById(target).classList.add('active');
        });
    });
});
