(() => {
    const form = document.getElementById('create-scraper-form');
    if (!form) {
        return;
    }

    const companyInput = document.getElementById('company');
    const geminiInput = document.getElementById('gemini-key');
    const showKeyToggle = document.getElementById('show-key');
    const launchBtn = document.getElementById('launch-btn');
    const logBody = document.getElementById('log-body');
    const previewImg = document.getElementById('browser-preview');
    const previewPlaceholder = document.getElementById('preview-placeholder');
    const previewStageLabel = document.getElementById('preview-stage');
    const progressSteps = Array.from(document.querySelectorAll('.progress-step'));
    const resultCard = document.getElementById('result-card');
    const resultTitle = document.getElementById('result-title');
    const resultMessage = document.getElementById('result-message');
    const resultPath = document.getElementById('result-path');

    const defaultButtonLabel = launchBtn.querySelector('.default-label');
    const loadingButtonLabel = launchBtn.querySelector('.loading-label');

    let currentSource = null;
    const stageOrder = progressSteps.map(step => step.dataset.stage);

    function toggleButtonLoading(isLoading) {
        launchBtn.disabled = isLoading;
        defaultButtonLabel.classList.toggle('d-none', isLoading);
        loadingButtonLabel.classList.toggle('d-none', !isLoading);
    }

    function resetUI() {
        progressSteps.forEach(step => {
            step.classList.remove('active', 'completed', 'error');
        });
        if (logBody) {
            logBody.innerHTML = '';
        }
        appendLog({
            timestamp: new Date().toISOString(),
            message: 'Workflow initiated. Connecting to worker…',
            stage: 'queued'
        }, true);
        previewStageLabel.textContent = 'Spinning up';
        previewPlaceholder.textContent = 'Connecting browser';
        previewImg.classList.add('d-none');
        if (resultCard) {
            resultCard.classList.remove('visible');
        }
    }

    function setStage(stage, status) {
        if (!stage) return;
        const targetIndex = stageOrder.indexOf(stage);
        if (targetIndex === -1) return;

        progressSteps.forEach((step, index) => {
            step.classList.toggle('active', index === targetIndex);
            step.classList.toggle('completed', index < targetIndex);
            step.classList.toggle('error', index === targetIndex && status === 'error');
        });
    }

    function appendLog(event, replaceLast = false) {
        if (!logBody) return;
        const timestamp = event.timestamp ? new Date(event.timestamp) : new Date();
        const timeLabel = timestamp.toLocaleTimeString('en-US', { hour12: false });
        const message = event.message || 'Working…';
        const status = event.status || event.type;

        const line = document.createElement('div');
        line.className = 'log-line';
        line.innerHTML = `
            <span class="timestamp">${timeLabel}</span>
            <div>
                <div class="fw-semibold">${message}</div>
                <div class="text-muted small">${(event.stage || 'status').toUpperCase()}</div>
            </div>
        `;

        if (replaceLast && logBody.lastElementChild) {
            logBody.removeChild(logBody.lastElementChild);
        }

        logBody.appendChild(line);
        logBody.scrollTop = logBody.scrollHeight;

        if (status === 'error' && window.JobScraper?.showToast) {
            window.JobScraper.showToast(message, 'danger');
        }
    }

    function updatePreview(event) {
        if (!event || !event.image) return;
        previewImg.src = event.image;
        previewImg.classList.remove('d-none');
        previewPlaceholder.classList.add('d-none');
        previewStageLabel.textContent = (event.stage || 'Preview').replace(/_/g, ' ');
    }

    function updateResultCard(event) {
        if (!resultCard) return;
        resultCard.classList.add('visible');
        const success = event.status === 'success';
        const chip = resultCard.querySelector('.status-chip');
        chip.classList.remove('success', 'error', 'warning');
        chip.classList.add(success ? 'success' : 'error');
        chip.innerHTML = success
            ? '<i class="bi bi-check2-circle"></i> Complete'
            : '<i class="bi bi-x-circle"></i> Failed';

        resultTitle.textContent = success ? 'Scraper ready' : 'Workflow failed';
        resultMessage.textContent = event.message || (success
            ? 'Selectors validated and stored.'
            : 'We hit a snag while generating your scraper.');
        resultPath.textContent = event.script_file
            ? `Script saved to: ${event.script_file}`
            : event.config_url
                ? `Target job board: ${event.config_url}`
                : '';
    }

    function closeSource() {
        if (currentSource) {
            currentSource.close();
            currentSource = null;
        }
    }

    function connectToStream(jobId) {
        closeSource();
        currentSource = new EventSource(`/api/create-scraper/events/${jobId}`);

        currentSource.addEventListener('update', event => {
            const data = JSON.parse(event.data);
            setStage(data.stage, data.status);
            appendLog(data);
            if (data.stage === 'complete' && data.status === 'success') {
                updateResultCard(data);
            }
        });

        currentSource.addEventListener('preview', event => {
            const data = JSON.parse(event.data);
            updatePreview(data);
            setStage(data.stage, data.status);
            appendLog(data);
        });

        currentSource.addEventListener('complete', event => {
            const data = JSON.parse(event.data);
            setStage('complete', data.status);
            appendLog(data);
            updateResultCard(data);
        });

        currentSource.addEventListener('error', event => {
            try {
                const data = JSON.parse(event.data);
                setStage(data.stage, 'error');
                appendLog(data);
                updateResultCard(data);
            } catch (err) {
                console.error('SSE error payload', err);
            }
            toggleButtonLoading(false);
        });

        currentSource.addEventListener('finalized', event => {
            const data = JSON.parse(event.data);
            setStage('complete', data.status);
            appendLog(data);
            if (data.status !== 'success') {
                updateResultCard(data);
            }
            toggleButtonLoading(false);
            closeSource();
        });

        currentSource.addEventListener('closed', () => {
            toggleButtonLoading(false);
            closeSource();
        });

        currentSource.onerror = () => {
            toggleButtonLoading(false);
        };
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        event.stopPropagation();

        form.classList.add('was-validated');
        if (!form.checkValidity()) {
            return;
        }

        const payload = {
            company: companyInput.value.trim(),
            geminiApiKey: geminiInput.value.trim()
        };

        if (!payload.company || !payload.geminiApiKey) {
            return;
        }

        toggleButtonLoading(true);
        resetUI();

        try {
            const response = await fetch('/api/create-scraper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Unable to start workflow');
            }

            connectToStream(result.jobId);
        } catch (err) {
            toggleButtonLoading(false);
            if (window.JobScraper?.showToast) {
                window.JobScraper.showToast(err.message, 'danger');
            }
            appendLog({
                timestamp: new Date().toISOString(),
                message: err.message,
                stage: 'error',
                status: 'error'
            });
        }
    });

    if (showKeyToggle && geminiInput) {
        showKeyToggle.addEventListener('change', () => {
            geminiInput.type = showKeyToggle.checked ? 'text' : 'password';
        });
    }
})();
