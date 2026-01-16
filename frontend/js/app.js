/**
 * ElectriFix Diagnostics - Frontend Application
 * Alpine.js based reactive frontend
 */

const API_BASE = window.location.origin;

function app() {
    return {
        // UI State
        currentView: 'dashboard',
        toast: { show: false, message: '', type: 'success' },
        
        // Data
        stats: {},
        models: [],
        ports: [],
        recentDiagnoses: [],
        diagnosisHistory: [],
        aiConfigured: false,
        apiKey: '',
        
        // Diagnosis workflow
        currentDiagStep: 0,
        diagnosisSteps: ['Select Model', 'Symptoms', 'Capture', 'Results'],
        diagForm: {
            modelId: '',
            symptoms: '',
            port: '',
            baudRate: '9600'
        },
        isCapturing: false,
        captureStats: {
            totalBytes: 0,
            packetCount: 0,
            duration: '0s',
            hexPreview: ''
        },
        analysisResults: null,
        captureStartTime: null,
        captureInterval: null,
        wsConnection: null,
        
        // Computed
        get selectedModel() {
            if (!this.diagForm.modelId) return null;
            return this.models.find(m => m.id == this.diagForm.modelId);
        },
        
        // Lifecycle
        async init() {
            await this.loadInitialData();
            this.setupWebSocket();
        },
        
        async loadInitialData() {
            try {
                // Load all data in parallel
                const [statusRes, statsRes, modelsRes, portsRes, historyRes] = await Promise.all([
                    fetch(API_BASE + '/api/status'),
                    fetch(API_BASE + '/api/stats'),
                    fetch(API_BASE + '/api/models'),
                    fetch(API_BASE + '/api/serial/ports'),
                    fetch(API_BASE + '/api/diagnose/history?limit=10')
                ]);
                
                const status = await statusRes.json();
                this.aiConfigured = status.ai_configured;
                
                this.stats = await statsRes.json();
                
                const modelsData = await modelsRes.json();
                this.models = modelsData.models || [];
                
                const portsData = await portsRes.json();
                this.ports = portsData.ports || [];
                
                const historyData = await historyRes.json();
                this.recentDiagnoses = historyData.history || [];
                this.diagnosisHistory = historyData.history || [];
                
            } catch (error) {
                console.error('Failed to load initial data:', error);
                this.showToast('Failed to connect to server', 'error');
            }
        },
        
        setupWebSocket() {
            const wsUrl = API_BASE.replace('http', 'ws') + '/ws/capture';
            
            try {
                this.wsConnection = new WebSocket(wsUrl);
                
                this.wsConnection.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'capture_update' && data.capturing) {
                        this.captureStats.totalBytes = data.total_bytes;
                        this.captureStats.packetCount = data.packet_count;
                        if (data.recent_hex && data.recent_hex.length > 0) {
                            this.captureStats.hexPreview = data.recent_hex.join(' ');
                        }
                    }
                };
                
                this.wsConnection.onerror = (error) => {
                    console.log('WebSocket error - falling back to polling');
                };
                
            } catch (error) {
                console.log('WebSocket not available');
            }
        },
        
        // Actions
        async refreshPorts() {
            try {
                const res = await fetch(API_BASE + '/api/serial/ports');
                const data = await res.json();
                this.ports = data.ports || [];
                this.showToast('Ports refreshed', 'success');
            } catch (error) {
                this.showToast('Failed to refresh ports', 'error');
            }
        },
        
        async autoDetectBaud() {
            if (!this.diagForm.port) {
                this.showToast('Please select a port first', 'error');
                return;
            }
            
            this.showToast('Detecting baud rate...', 'success');
            
            try {
                const res = await fetch(API_BASE + '/api/serial/detect-baud?port=' + encodeURIComponent(this.diagForm.port), {
                    method: 'POST'
                });
                const data = await res.json();
                
                if (data.success) {
                    this.diagForm.baudRate = String(data.baud_rate);
                    this.showToast('Detected: ' + data.baud_rate + ' baud (' + data.protocol + ')', 'success');
                } else {
                    this.showToast(data.message || 'Detection failed', 'error');
                }
            } catch (error) {
                this.showToast('Detection failed', 'error');
            }
        },
        
        async startCapture() {
            if (!this.diagForm.port) {
                this.showToast('Please select a serial port', 'error');
                return;
            }
            
            try {
                const res = await fetch(API_BASE + '/api/serial/start?port=' + encodeURIComponent(this.diagForm.port) + 
                    '&baud_rate=' + this.diagForm.baudRate, { method: 'POST' });
                const data = await res.json();
                
                if (data.status === 'capturing') {
                    this.isCapturing = true;
                    this.captureStartTime = Date.now();
                    this.captureStats = { totalBytes: 0, packetCount: 0, duration: '0s', hexPreview: '' };
                    
                    // Start polling for updates
                    this.captureInterval = setInterval(() => this.updateCaptureStatus(), 500);
                    
                    this.showToast('Capture started', 'success');
                } else {
                    this.showToast('Failed to start capture', 'error');
                }
            } catch (error) {
                this.showToast('Failed to start capture', 'error');
            }
        },
        
        async stopCapture() {
            try {
                const res = await fetch(API_BASE + '/api/serial/stop', { method: 'POST' });
                const data = await res.json();
                
                this.isCapturing = false;
                if (this.captureInterval) {
                    clearInterval(this.captureInterval);
                    this.captureInterval = null;
                }
                
                if (data.total_bytes > 0) {
                    this.captureStats.totalBytes = data.total_bytes;
                    this.captureStats.packetCount = data.packet_count;
                    this.captureStats.duration = Math.round(data.duration_ms / 1000) + 's';
                    this.captureStats.hexPreview = data.hex_preview;
                    this.showToast('Capture stopped: ' + data.total_bytes + ' bytes', 'success');
                } else {
                    this.showToast('No data captured', 'error');
                }
            } catch (error) {
                this.isCapturing = false;
                this.showToast('Error stopping capture', 'error');
            }
        },
        
        async updateCaptureStatus() {
            if (!this.isCapturing) return;
            
            try {
                const res = await fetch(API_BASE + '/api/serial/status');
                const data = await res.json();
                
                if (data.capturing) {
                    this.captureStats.totalBytes = data.total_bytes;
                    this.captureStats.packetCount = data.packet_count;
                    
                    const elapsed = Math.round((Date.now() - this.captureStartTime) / 1000);
                    this.captureStats.duration = elapsed + 's';
                }
            } catch (error) {
                // Ignore polling errors
            }
        },
        
        async runAnalysis() {
            if (this.isCapturing) {
                await this.stopCapture();
            }
            
            this.currentDiagStep = 3;
            this.analysisResults = null;
            
            try {
                const params = new URLSearchParams({
                    model_id: this.diagForm.modelId,
                    customer_symptoms: this.diagForm.symptoms || ''
                });
                
                const res = await fetch(API_BASE + '/api/diagnose/analyze?' + params.toString(), {
                    method: 'POST'
                });
                
                const data = await res.json();
                
                if (data.diagnosis_id) {
                    this.analysisResults = data;
                    this.showToast('Analysis complete', 'success');
                } else {
                    this.showToast('Analysis failed', 'error');
                }
            } catch (error) {
                console.error('Analysis error:', error);
                this.showToast('Analysis failed', 'error');
            }
        },
        
        nextDiagStep() {
            if (this.currentDiagStep === 0 && !this.diagForm.modelId) {
                this.showToast('Please select a scooter model', 'error');
                return;
            }
            
            // Auto-select baud rate from model
            if (this.currentDiagStep === 0 && this.selectedModel) {
                this.diagForm.baudRate = String(this.selectedModel.baud_rate);
            }
            
            this.currentDiagStep++;
        },
        
        resetDiagnosis() {
            this.currentDiagStep = 0;
            this.diagForm = { modelId: '', symptoms: '', port: '', baudRate: '9600' };
            this.captureStats = { totalBytes: 0, packetCount: 0, duration: '0s', hexPreview: '' };
            this.analysisResults = null;
            this.isCapturing = false;
            
            // Refresh history
            this.loadHistory();
        },
        
        async loadHistory() {
            try {
                const res = await fetch(API_BASE + '/api/diagnose/history?limit=50');
                const data = await res.json();
                this.diagnosisHistory = data.history || [];
                this.recentDiagnoses = (data.history || []).slice(0, 10);
            } catch (error) {
                console.error('Failed to load history');
            }
        },
        
        async saveApiKey() {
            if (!this.apiKey) {
                this.showToast('Please enter an API key', 'error');
                return;
            }
            
            try {
                const res = await fetch(API_BASE + '/api/settings/api-key', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: this.apiKey })
                });
                
                const data = await res.json();
                
                if (data.message && data.success !== false) {
                    this.aiConfigured = true;
                    this.apiKey = '';
                    this.showToast('API key saved successfully', 'success');
                } else {
                    this.showToast('Failed to save API key', 'error');
                }
            } catch (error) {
                this.showToast('Failed to save API key', 'error');
            }
        },
        
        // Helpers
        formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        },
        
        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
