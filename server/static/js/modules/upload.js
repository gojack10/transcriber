// file upload functionality
import { CONFIG, APP_STATE } from '../core/config.js';
import { updateStatus, generateId } from '../core/utils.js';
import { ApiService } from '../services/api.js';

export class UploadModule {
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
        
        // url input
        document.getElementById('url-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.addUrl();
        });
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
        
        for (const file of files) {
            await this.uploadFile(file);
        }
        
        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressContainer.innerHTML = '';
        }, CONFIG.PROGRESS_HIDE_DELAY);
    }

    static async uploadFile(file) {
        const progressContainer = document.getElementById('upload-progress');
        const progressId = `upload-${generateId()}`;
        
        const progressItem = this.createProgressItem(progressId, file.name);
        progressContainer.appendChild(progressItem);
        
        try {
            updateStatus(`uploading ${file.name}...`);
            
            const result = await ApiService.uploadFile(file, (percent) => {
                this.updateProgress(progressItem, percent);
            });
            
            if (result.success) {
                updateStatus(`${file.name} uploaded successfully`);
                this.setProgressStatus(progressItem, 'success', 'success');
                // refresh queue after successful upload
                const { QueueModule } = await import('./queue.js');
                QueueModule.refreshStatus();
            } else {
                this.setProgressStatus(progressItem, 'error', `failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`upload error: ${error.message}`);
            this.setProgressStatus(progressItem, 'error', `error: ${error.message}`);
        }
    }

    static createProgressItem(id, filename) {
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        progressItem.id = id;
        progressItem.innerHTML = `
            <div class="progress-filename">${filename}</div>
            <div class="progress-status uploading">uploading...</div>
            <div class="upload-progress-bar">
                <div class="upload-progress-fill"></div>
            </div>
            <div class="upload-progress-text">0%</div>
        `;
        return progressItem;
    }

    static updateProgress(progressItem, percent) {
        const progressFill = progressItem.querySelector('.upload-progress-fill');
        const progressText = progressItem.querySelector('.upload-progress-text');
        
        progressFill.style.width = `${percent}%`;
        progressText.textContent = `${Math.round(percent)}%`;
    }

    static setProgressStatus(progressItem, statusClass, statusText) {
        const statusElement = progressItem.querySelector('.progress-status');
        statusElement.textContent = statusText;
        statusElement.className = `progress-status ${statusClass}`;
    }

    static async addUrl() {
        const urlInput = document.getElementById('url-input');
        const url = urlInput.value.trim();
        
        if (!url) {
            updateStatus('please enter a url');
            return;
        }
        
        const progressContainer = document.getElementById('url-progress');
        const progressId = `url-${generateId()}`;
        
        progressContainer.style.display = 'block';
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        progressItem.id = progressId;
        progressItem.innerHTML = `
            <div class="progress-filename">${url}</div>
            <div class="progress-status processing">processing...</div>
        `;
        progressContainer.appendChild(progressItem);
        
        try {
            updateStatus(`adding url to queue...`);
            
            const result = await ApiService.post(CONFIG.API_ENDPOINTS.QUEUE_LINK, { url });
            const statusElement = progressItem.querySelector('.progress-status');
            
            if (result.success) {
                updateStatus(`url added to queue successfully`);
                statusElement.textContent = 'added to queue';
                statusElement.className = 'progress-status success';
                urlInput.value = '';
                // refresh queue after successful url add
                const { QueueModule } = await import('./queue.js');
                QueueModule.refreshStatus();
            } else {
                updateStatus(`failed to add url: ${result.error}`);
                statusElement.textContent = `failed: ${result.error}`;
                statusElement.className = 'progress-status error';
            }
        } catch (error) {
            updateStatus(`error adding url: ${error.message}`);
            const statusElement = progressItem.querySelector('.progress-status');
            statusElement.textContent = `error: ${error.message}`;
            statusElement.className = 'progress-status error';
        }
        
        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressContainer.innerHTML = '';
        }, CONFIG.PROGRESS_HIDE_DELAY);
    }
}
