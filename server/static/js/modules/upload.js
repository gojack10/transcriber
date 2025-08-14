// file upload functionality
import { CONFIG, APP_STATE } from '../core/config.js';
import { updateStatus, generateId } from '../core/utils.js';
import { ApiService } from '../services/api.js';

export class UploadModule {
    static activeUploads = new Set();
    static completedUploads = new Set();
    static currentUploadType = 'files';
    
    static init() {
        this.initializeEventListeners();
    }

    static initializeEventListeners() {
        const uploadArea = document.getElementById('upload-area');
        const fileInput = document.getElementById('file-input');
        
        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', this.handleDragOver);
        uploadArea.addEventListener('dragleave', this.handleDragLeave);
        uploadArea.addEventListener('drop', this.handleDrop);
        fileInput.addEventListener('change', this.handleFileSelect);
        
        document.getElementById('url-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addUrl();
        });
    }

    static switchUploadType(type) {
        this.currentUploadType = type;
        
        document.querySelectorAll('.upload-type-btn').forEach(btn => btn.classList.remove('active'));
        document.getElementById(`${type}-tab`).classList.add('active');
        
        document.getElementById('files-upload').style.display = type === 'files' ? 'block' : 'none';
        document.getElementById('url-upload').style.display = type === 'url' ? 'block' : 'none';
    }

    static handleDragOver = (e) => {
        e.preventDefault();
        document.getElementById('upload-area').classList.add('dragover');
    }

    static handleDragLeave = () => {
        document.getElementById('upload-area').classList.remove('dragover');
    }

    static handleDrop = (e) => {
        e.preventDefault();
        document.getElementById('upload-area').classList.remove('dragover');
        this.handleFiles(e.dataTransfer.files);
    }

    static handleFileSelect = (e) => {
        this.handleFiles(e.target.files);
    }

    static async handleFiles(files) {
        const progressContainer = document.getElementById('upload-progress');
        progressContainer.style.display = 'block';
        
        const uploadPromises = Array.from(files).map(file => this.uploadFile(file));
        await Promise.all(uploadPromises);
        
        setTimeout(() => {
            if (this.activeUploads.size === 0) {
                progressContainer.style.display = 'none';
                progressContainer.innerHTML = '';
                this.completedUploads.clear();
            }
        }, CONFIG.PROGRESS_HIDE_DELAY);
    }

    static async uploadFile(file) {
        const progressContainer = document.getElementById('upload-progress');
        const progressId = `upload-${generateId()}`;
        
        this.activeUploads.add(progressId);
        const progressItem = this.createProgressItem(progressId, file.name);
        progressContainer.appendChild(progressItem);
        
        try {
            updateStatus(`uploading ${file.name}...`);
            
            const result = await ApiService.uploadFile(file, (percent) => {
                this.updateProgress(progressItem, percent);
            });
            
            if (result.success) {
                updateStatus(`${file.name} uploaded successfully`);
                this.setProgressStatus(progressItem, 'success', 'added to queue');
                this.completedUploads.add(progressId);
                
                setTimeout(() => {
                    if (this.completedUploads.has(progressId)) {
                        progressItem.remove();
                        this.completedUploads.delete(progressId);
                    }
                }, CONFIG.UPLOAD_SUCCESS_DISPLAY_TIME);
                
                const { QueueModule } = await import('./queue.js');
                QueueModule.refreshStatus();
            } else {
                this.setProgressStatus(progressItem, 'error', `failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`upload error: ${error.message}`);
            this.setProgressStatus(progressItem, 'error', `error: ${error.message}`);
        } finally {
            this.activeUploads.delete(progressId);
        }
    }

    static createProgressItem(id, filename) {
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        progressItem.id = id;
        progressItem.innerHTML = `
            <div class="progress-header">
                <div class="progress-filename">${filename}</div>
                <div class="progress-status uploading">uploading</div>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar">
                    <div class="progress-bar-fill"></div>
                </div>
            </div>
        `;
        return progressItem;
    }

    static updateProgress(progressItem, percent) {
        const progressFill = progressItem.querySelector('.progress-bar-fill');
        progressFill.style.width = `${percent}%`;
    }

    static setProgressStatus(progressItem, statusClass, statusText) {
        const statusElement = progressItem.querySelector('.progress-status');
        statusElement.textContent = statusText;
        statusElement.className = `progress-status ${statusClass}`;
        
        if (statusClass === 'success') {
            progressItem.style.borderLeftColor = 'var(--success)';
        } else if (statusClass === 'error') {
            progressItem.style.borderLeftColor = 'var(--urgent)';
        }
    }

    static async addUrl() {
        const urlInput = document.getElementById('url-input');
        const url = urlInput.value.trim();
        
        if (!url) {
            updateStatus('please enter a url');
            return;
        }
        
        const progressContainer = document.getElementById('upload-progress');
        const progressId = `url-${generateId()}`;
        
        progressContainer.style.display = 'block';
        const progressItem = this.createUrlProgressItem(progressId, url);
        progressContainer.appendChild(progressItem);
        
        try {
            updateStatus(`adding url to queue...`);
            
            const result = await ApiService.post(CONFIG.API_ENDPOINTS.QUEUE_LINK, { url });
            
            if (result.success) {
                updateStatus(`url added to queue successfully`);
                this.setProgressStatus(progressItem, 'success', 'added to queue');
                urlInput.value = '';
                
                setTimeout(() => {
                    progressItem.remove();
                }, CONFIG.UPLOAD_SUCCESS_DISPLAY_TIME);
                
                const { QueueModule } = await import('./queue.js');
                QueueModule.refreshStatus();
            } else {
                updateStatus(`failed to add url: ${result.error}`);
                this.setProgressStatus(progressItem, 'error', `failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error adding url: ${error.message}`);
            this.setProgressStatus(progressItem, 'error', `error: ${error.message}`);
        }
    }

    static createUrlProgressItem(id, url) {
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        progressItem.id = id;
        progressItem.innerHTML = `
            <div class="progress-header">
                <div class="progress-filename">${url}</div>
                <div class="progress-status processing">processing</div>
            </div>
        `;
        return progressItem;
    }
}
