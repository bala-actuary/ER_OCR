/* Electoral Roll OCR — Alpine.js application */

function app() {
  return {
    // ── Navigation ────────────────────────────────────────────────
    activeTab: 'workflow',
    darkMode: true,
    serverOk: true,
    showSetup: false,

    tabs: [
      { id: 'workflow', label: '▶ Workflow',  badge: false },
      { id: 'logs',     label: '📋 Live Logs', badge: false },
      { id: 'data',     label: '📁 Data',     badge: false },
      { id: 'history',  label: '🕐 History',  badge: false },
    ],

    toasts: [],

    // ── Setup tab ────────────────────────────────────────────────
    setupChecks: null,
    checkingSetup: false,
    installJobs: {},       // dep_key -> { job_id, status }

    // ── Workflow tab ──────────────────────────────────────────────
    acs: [],
    selectedAc: '',
    acStatus: null,
    systemResources: null,

    // Options
    splitForce: false,
    splitInfoOpen: false,
    extractWorkers: 4,
    extractPart: '',
    extractCrossCheck: false,
    extractLimit: 0,
    extractPage: '',
    extractReset: false,
    extractInfoOpen: false,
    mergeForce: false,

    // Preview
    previewRows: null,
    previewLoading: false,
    previewFile: '',

    // Queue
    queueItems: [],
    queueRunning: false,
    queuePollTimer: null,

    // ── Live Logs tab ─────────────────────────────────────────────
    recentJobs: [],
    activeJobId: '',
    logLines: [],
    autoScroll: true,
    eventSource: null,
    activeJobStatus: '',
    etaText: '',
    etaPollTimer: null,

    // ── Data tab ──────────────────────────────────────────────────
    dataAcs: [],
    expandedAc: '',

    // ── History tab ───────────────────────────────────────────────
    logFiles: [],
    selectedLogFile: '',
    logFileContent: [],
    logFileTotalLines: 0,

    // =================================================================
    // Init
    // =================================================================
    async init() {
      // Restore dark mode from localStorage
      const saved = localStorage.getItem('darkMode');
      this.darkMode = saved === null ? true : saved === 'true';
      this._applyDarkMode();

      await this.runSetupCheck();
      await this.loadAcs();
      await this.loadRecentJobs();
      await this.loadDataAcs();
      await this.loadLogFiles();
      await this.pollQueue();
    },

    // =================================================================
    // Dark mode
    // =================================================================
    toggleDark() {
      this.darkMode = !this.darkMode;
      localStorage.setItem('darkMode', this.darkMode);
      this._applyDarkMode();
    },
    _applyDarkMode() {
      document.documentElement.classList.toggle('dark', this.darkMode);
    },

    // =================================================================
    // Setup tab
    // =================================================================
    async runSetupCheck() {
      this.checkingSetup = true;
      try {
        const r = await fetch('/api/setup/check');
        this.setupChecks = await r.json();
        // Badge the Setup tab if anything is broken
        this.tabs[0].badge = !this.setupChecks.all_ok;
        this.serverOk = true;
      } catch (e) {
        this.serverOk = false;
      } finally {
        this.checkingSetup = false;
      }
    },

    async installDep(depKey) {
      const endpoints = {
        ocr_packages:     '/api/setup/install/packages',
        tesseract_binary: '/api/setup/install/tesseract',
        tamil_tessdata:   '/api/setup/install/tessdata',
      };
      const url = endpoints[depKey];
      if (!url) return;

      const r = await fetch(url, { method: 'POST' });
      const data = await r.json();
      this.installJobs[depKey] = { job_id: data.job_id, status: 'running' };
      this.openJobInLogs(data.job_id);
      this.toast(`Installing ${depKey}...`, 'info');

      // Poll for completion
      const poll = setInterval(async () => {
        const jr = await fetch(`/api/jobs/${data.job_id}`);
        const jd = await jr.json();
        this.installJobs[depKey].status = jd.status;
        if (jd.status !== 'running' && jd.status !== 'pending') {
          clearInterval(poll);
          if (jd.status === 'done') {
            this.toast(`${depKey} installed successfully`, 'success');
            await this.runSetupCheck();
          } else {
            this.toast(`${depKey} install failed — check Live Logs`, 'error');
          }
        }
      }, 2000);
    },

    // =================================================================
    // Workflow tab
    // =================================================================
    async loadAcs() {
      try {
        const r = await fetch('/api/acs');
        this.acs = await r.json();
      } catch (e) {}
    },

    async selectAc(ac) {
      this.selectedAc = ac;
      this.acStatus = null;
      this.previewRows = null;
      this.previewFile = '';
      if (!ac) return;

      const [statusR, resR] = await Promise.all([
        fetch(`/api/acs/${ac}/status`),
        fetch(`/api/system/resources?ac=${ac}`),
      ]);
      this.acStatus = await statusR.json();
      this.systemResources = await resR.json();

      // Pre-fill workers from recommendation
      if (this.systemResources?.cpu_recommended_workers) {
        this.extractWorkers = this.systemResources.cpu_recommended_workers;
      }
    },

    async createAc() {
      const ac = prompt('Enter AC number in AC-xxx format (e.g., AC-188):');
      if (!ac) return;
      if (!/^AC-\d{1,3}$/.test(ac.trim())) {
        this.toast('AC must be in AC-xxx format (e.g., AC-188)', 'warning');
        return;
      }
      try {
        const r = await fetch('/api/acs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ac: ac.trim() }),
        });
        if (!r.ok) {
          const err = await r.json();
          this.toast(err.detail || 'Failed to create AC', 'error');
          return;
        }
        this.toast(`${ac.trim()} created — add PDF files to Input/ER_Downloads/${ac.trim()}/`, 'success');
        await this.loadAcs();
        this.selectedAc = ac.trim();
        await this.selectAc(ac.trim());
      } catch (e) {
        this.toast('Network error', 'error');
      }
    },

    workersColor() {
      if (!this.systemResources) return 'workers-green';
      const rec = this.systemResources.cpu_recommended_workers;
      if (this.extractWorkers <= rec) return 'workers-green';
      if (this.extractWorkers <= rec + 2) return 'workers-yellow';
      return 'workers-red';
    },

    workersLabel() {
      if (!this.systemResources) return '';
      const rec = this.systemResources.cpu_recommended_workers;
      if (this.extractWorkers <= rec) return '✓ safe';
      if (this.extractWorkers <= rec + 2) return '⚠ heavy';
      return '⚠ risky';
    },

    diskWarningText() {
      if (!this.systemResources) return '';
      const w = this.systemResources.disk_warning;
      const free = this.systemResources.disk_free_gb;
      const est = this.systemResources.estimated_output_mb;
      if (w === 'danger') return `⛔ Low disk! Only ${free} GB free, need ~${(est/1024).toFixed(2)} GB`;
      if (w === 'warning') return `⚠ Disk may be tight: ${free} GB free, ~${(est/1024).toFixed(2)} GB estimated`;
      return '';
    },

    async runStep(step) {
      if (!this.selectedAc) { this.toast('Select an AC first', 'warning'); return; }

      let url, body;
      if (step === 'split') {
        url = '/api/jobs/split';
        body = { ac: this.selectedAc, force: this.splitForce };
      } else if (step === 'extract') {
        if (this.extractReset && !confirm('This will reset the checkpoint for the specified part. Continue?')) return;
        url = '/api/jobs/extract';
        body = { ac: this.selectedAc, workers: this.extractWorkers,
                 part: this.extractPart, cross_check: this.extractCrossCheck,
                 limit: this.extractLimit || 0,
                 page: this.extractPage || '',
                 reset: this.extractReset };
      } else if (step === 'merge') {
        url = '/api/jobs/merge';
        body = { ac: this.selectedAc, force: this.mergeForce };
      } else if (step === 'analyze') {
        url = '/api/jobs/analyze';
        body = { ac: this.selectedAc };
      }

      try {
        const r = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!r.ok) {
          const err = await r.json();
          this.toast(err.detail || 'Error starting job', 'error');
          return;
        }
        const data = await r.json();
        this.toast(`${step} started for ${this.selectedAc}`, 'info');
        this.openJobInLogs(data.job_id);
      } catch (e) {
        this.toast('Network error', 'error');
      }
    },

    async runPipeline() {
      if (!this.selectedAc) { this.toast('Select an AC first', 'warning'); return; }
      const r = await fetch('/api/jobs/pipeline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ac: this.selectedAc,
          workers: this.extractWorkers,
          cross_check: this.extractCrossCheck,
          force: this.splitForce || this.mergeForce,
        }),
      });
      if (r.ok) {
        this.toast(`Full pipeline queued for ${this.selectedAc}`, 'success');
        await this.pollQueue();
      }
    },

    async runValidate() {
      if (!this.selectedAc) return;
      this.previewLoading = true;
      this.previewRows = null;
      try {
        const r = await fetch('/api/jobs/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ac: this.selectedAc, run_validate: true, workers: 1 }),
        });
        const data = await r.json();
        this.openJobInLogs(data.job_id);
        this.toast('Validation started — results will appear after completion', 'info');

        // Poll until job done, then fetch preview
        const poll = setInterval(async () => {
          const jr = await fetch(`/api/jobs/${data.job_id}`);
          const jd = await jr.json();
          if (jd.status !== 'running' && jd.status !== 'pending') {
            clearInterval(poll);
            this.previewLoading = false;
            if (jd.status === 'done') {
              const pr = await fetch(`/api/acs/${this.selectedAc}/preview`);
              const pd = await pr.json();
              this.previewRows = pd.rows;
              this.previewFile = pd.source_file || '';
            }
          }
        }, 2000);
      } catch (e) {
        this.previewLoading = false;
        this.toast('Validate failed', 'error');
      }
    },

    async runDryRun() {
      if (!this.selectedAc) { this.toast('Select an AC first', 'warning'); return; }
      try {
        const r = await fetch('/api/jobs/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ac: this.selectedAc, workers: 1, dry_run: true,
            part: this.extractPart,
          }),
        });
        if (!r.ok) {
          const err = await r.json();
          this.toast(err.detail || 'Error', 'error');
          return;
        }
        const data = await r.json();
        this.toast('Dry-run started — check Live Logs', 'info');
        this.openJobInLogs(data.job_id);
      } catch (e) {
        this.toast('Network error', 'error');
      }
    },

    async runValidatePage() {
      if (!this.selectedAc) { this.toast('Select an AC first', 'warning'); return; }
      try {
        const r = await fetch('/api/jobs/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ac: this.selectedAc, run_validate: true, workers: 1,
            part: this.extractPart,
            page: this.extractPage || '',
          }),
        });
        if (!r.ok) {
          const err = await r.json();
          this.toast(err.detail || 'Error', 'error');
          return;
        }
        const data = await r.json();
        this.toast('Validation started — check Live Logs', 'info');
        this.openJobInLogs(data.job_id);
      } catch (e) {
        this.toast('Network error', 'error');
      }
    },

    previewColumns() {
      if (!this.previewRows || !this.previewRows.length) return [];
      return Object.keys(this.previewRows[0]);
    },

    // Queue
    async pollQueue() {
      try {
        const r = await fetch('/api/jobs/queue');
        const data = await r.json();
        this.queueItems = data.items || [];
        this.queueRunning = data.running || false;
      } catch (e) {}
    },

    async addToQueue() {
      if (!this.selectedAc) { this.toast('Select an AC first', 'warning'); return; }
      await fetch('/api/jobs/queue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ac: this.selectedAc,
          workers: this.extractWorkers,
          cross_check: this.extractCrossCheck,
          force: this.splitForce || this.mergeForce,
        }),
      });
      this.toast(`${this.selectedAc} added to queue`, 'info');
      await this.pollQueue();
    },

    async removeFromQueue(ac) {
      await fetch(`/api/jobs/queue/${ac}`, { method: 'DELETE' });
      await this.pollQueue();
    },

    async startQueue() {
      await fetch('/api/jobs/queue/start', { method: 'POST' });
      this.toast('Queue started', 'success');
      await this.pollQueue();
      if (this.queuePollTimer) clearInterval(this.queuePollTimer);
      this.queuePollTimer = setInterval(() => this.pollQueue(), 5000);
    },

    async stopQueue() {
      await fetch('/api/jobs/queue/stop', { method: 'POST' });
      this.toast('Queue will stop after current AC', 'info');
    },

    queueItemColor(status) {
      const map = { waiting: 'badge-pending', running: 'badge-running', done: 'badge-done', error: 'badge-error' };
      return map[status] || 'badge-pending';
    },

    // =================================================================
    // Live Logs tab
    // =================================================================
    openJobInLogs(jobId) {
      this.activeTab = 'logs';
      this.activeJobId = jobId;
      this.logLines = [];
      this.activeJobStatus = 'pending';
      this.etaText = '';
      this._startSSE(jobId);
      this.loadRecentJobs();
      this._startEtaPoll();
    },

    _startSSE(jobId) {
      if (this.eventSource) {
        this.eventSource.close();
      }
      const es = new EventSource(`/api/jobs/${jobId}/stream`);
      this.eventSource = es;

      es.onmessage = (e) => {
        if (e.data === ':keepalive' || e.data.trim() === '') return;
        const cls = this._lineClass(e.data);
        this.logLines.push({ text: e.data, cls });
        if (this.autoScroll) {
          this.$nextTick(() => {
            const el = document.getElementById('log-terminal');
            if (el) el.scrollTop = el.scrollHeight;
          });
        }
      };

      es.addEventListener('done', async () => {
        es.close();
        this.eventSource = null;
        const jr = await fetch(`/api/jobs/${jobId}`);
        const jd = await jr.json();
        this.activeJobStatus = jd.status;
        this.loadRecentJobs();
        clearInterval(this.etaPollTimer);
        this._appendPathLines(jd.step, jd.ac);
        if (jd.status === 'done') {
          this.toast(`Job ${jobId} completed`, 'success');
          this._sendBrowserNotification(`Job done: ${jd.step} ${jd.ac || ''}`);
          this.loadAcs();
          this.loadDataAcs();
        } else if (jd.status === 'error') {
          this.toast(`Job ${jobId} failed (exit ${jd.exit_code})`, 'error');
        }
      });

      es.onerror = () => {
        // EventSource reconnects automatically
      };
    },

    _pathsForJob(step, ac) {
      if (!ac) return null;
      const map = {
        split:   { input: `Input/ER_Downloads/${ac}/`, output: `Input/split_files/${ac}/` },
        extract: { input: `Input/split_files/${ac}/`, output: `output/split_files/${ac}/` },
        merge:   { input: `output/split_files/${ac}/`, output: `output/merged_files/parts/${ac}/  &  output/merged_files/ac/${ac}.csv` },
        analyze: { input: `output/merged_files/ac/${ac}.csv`, output: null },
      };
      return map[step] || null;
    },

    _appendPathLines(step, ac) {
      const paths = this._pathsForJob(step, ac);
      if (!paths) return;
      const sep = '\u2500'.repeat(50);
      this.logLines.push({ text: sep, cls: 'log-line-info' });
      this.logLines.push({ text: `Input:  ${paths.input}`, cls: 'log-line-info' });
      if (paths.output) {
        this.logLines.push({ text: `Output: ${paths.output}`, cls: 'log-line-info' });
      }
      this.logLines.push({ text: sep, cls: 'log-line-info' });
      if (this.autoScroll) {
        this.$nextTick(() => {
          const el = document.getElementById('log-terminal');
          if (el) el.scrollTop = el.scrollHeight;
        });
      }
    },

    _lineClass(text) {
      const t = text.toLowerCase();
      if (t.includes('error') || t.includes('failed') || t.includes('exception')) return 'log-line-error';
      if (t.includes('warn') || t.includes('warning')) return 'log-line-warn';
      if (t.includes('[ok]') || t.includes('success') || t.includes('done')) return 'log-line-ok';
      if (t.startsWith('[') || t.includes('info')) return 'log-line-info';
      return '';
    },

    async loadRecentJobs() {
      try {
        const r = await fetch('/api/jobs');
        this.recentJobs = await r.json();
        if (!this.activeJobId && this.recentJobs.length > 0) {
          this.activeJobId = this.recentJobs[0].job_id;
          this.activeJobStatus = this.recentJobs[0].status;
        }
      } catch (e) {}
    },

    async switchJob(jobId) {
      if (this.eventSource) { this.eventSource.close(); this.eventSource = null; }
      this.activeJobId = jobId;
      this.logLines = [];
      this.etaText = '';
      const jr = await fetch(`/api/jobs/${jobId}`);
      const jd = await jr.json();
      this.activeJobStatus = jd.status;
      // Load buffered lines
      for (const line of (jd.log_lines || [])) {
        this.logLines.push({ text: line, cls: this._lineClass(line) });
      }
      if (jd.status !== 'running' && jd.status !== 'pending') {
        this._appendPathLines(jd.step, jd.ac);
      }
      if (jd.status === 'running') {
        this._startSSE(jobId);
        this._startEtaPoll();
      }
    },

    async killActiveJob() {
      if (!this.activeJobId) return;
      await fetch(`/api/jobs/${this.activeJobId}`, { method: 'DELETE' });
      this.toast('Kill signal sent', 'warning');
    },

    statusBadgeClass(status) {
      const map = {
        running: 'badge-running', done: 'badge-done',
        error: 'badge-error', killed: 'badge-killed', pending: 'badge-pending'
      };
      return map[status] || 'badge-pending';
    },

    // ETA
    _startEtaPoll() {
      if (this.etaPollTimer) clearInterval(this.etaPollTimer);
      this.etaPollTimer = setInterval(() => this._updateEta(), 10000);
    },

    async _updateEta() {
      const job = this.recentJobs.find(j => j.job_id === this.activeJobId);
      if (!job || job.status !== 'running' || !job.ac) return;
      try {
        const r = await fetch(`/api/acs/${job.ac}/progress`);
        const d = await r.json();
        if (d.total > 0 && d.processed > 0) {
          const pct = d.pct;
          this.etaText = `${pct}% done (${d.processed}/${d.total} pages)`;
        }
      } catch (e) {}
    },

    // =================================================================
    // Data tab
    // =================================================================
    async loadDataAcs() {
      try {
        const r = await fetch('/api/acs');
        this.dataAcs = await r.json();
      } catch (e) {}
    },

    totalRecords() {
      return this.dataAcs.reduce((sum, a) => sum + (a.record_count || 0), 0);
    },

    async downloadCsv(ac) {
      window.location.href = `/api/acs/${ac}/csv`;
    },

    toggleExpandAc(ac) {
      this.expandedAc = this.expandedAc === ac ? '' : ac;
    },

    // =================================================================
    // History tab
    // =================================================================
    async loadLogFiles() {
      try {
        const r = await fetch('/api/logs');
        this.logFiles = await r.json();
      } catch (e) {}
    },

    async loadLogFile(name) {
      this.selectedLogFile = name;
      this.logFileContent = [];
      try {
        const r = await fetch(`/api/logs/${encodeURIComponent(name)}`);
        const d = await r.json();
        this.logFileContent = d.lines || [];
        this.logFileTotalLines = d.total_lines || 0;
      } catch (e) {}
    },

    downloadLog(name) {
      window.location.href = `/api/logs/${encodeURIComponent(name)}`;
    },

    // =================================================================
    // Browser notifications
    // =================================================================
    _sendBrowserNotification(message) {
      if (!('Notification' in window)) return;
      if (Notification.permission === 'granted') {
        new Notification('Electoral Roll OCR', { body: message, icon: '' });
      } else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then(p => {
          if (p === 'granted') new Notification('Electoral Roll OCR', { body: message });
        });
      }
    },

    requestNotificationPermission() {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
      }
    },

    // =================================================================
    // Toast notifications
    // =================================================================
    toast(message, type = 'info') {
      const id = Date.now();
      const colors = {
        info:    'bg-blue-900 border-blue-600 text-blue-200',
        success: 'bg-green-900 border-green-600 text-green-200',
        warning: 'bg-yellow-900 border-yellow-600 text-yellow-200',
        error:   'bg-red-900 border-red-600 text-red-200',
      };
      this.toasts.push({ id, message, type, color: colors[type] || colors.info });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 4000);
    },

    dismissToast(id) {
      this.toasts = this.toasts.filter(t => t.id !== id);
    },

    // =================================================================
    // Utilities
    // =================================================================
    formatPct(pct) {
      return pct ? `${pct}%` : '0%';
    },

    formatDate(iso) {
      if (!iso) return '';
      return new Date(iso).toLocaleString();
    },

    acLabel(ac) {
      const found = this.acs.find(a => a.ac === ac);
      if (!found) return ac;
      return `${ac} (${found.checkpoint_pct}%)`;
    },
  };
}
