// modal functionality
import { updateStatus } from '../core/utils.js';
import { APP_STATE } from '../core/config.js';

export class ModalModule {
    static init() {
        this.initializeEventListeners();
    }

    static initializeEventListeners() {
        // transcription modal events
        document.querySelector('.modal-close').addEventListener('click', () => this.closeTranscriptionModal());
        document.querySelector('.copy-btn').addEventListener('click', () => this.copyToClipboard());
        
        // duplicate modal events  
        document.getElementById('duplicate-cancel').addEventListener('click', () => this.closeDuplicateModal());
        
        // close modal when clicking outside
        window.addEventListener('click', (event) => {
            const transcriptionModal = document.getElementById('transcription-modal');
            const duplicateModal = document.getElementById('duplicate-modal');
            
            if (event.target === transcriptionModal) {
                this.closeTranscriptionModal();
            }
            if (event.target === duplicateModal) {
                this.closeDuplicateModal();
            }
        });
        
        // keyboard shortcuts
        document.addEventListener('keydown', (event) => {
            const modal = document.getElementById('transcription-modal');
            if (modal.style.display === 'block') {
                if (event.key === 'Escape') {
                    this.closeTranscriptionModal();
                }
                if (event.ctrlKey && event.key === 'c' && event.target.id !== 'modal-content') {
                    event.preventDefault();
                    this.copyToClipboard();
                }
            }
        });
    }

    static showTranscription(filename, content) {
        document.getElementById('modal-title').textContent = filename;
        document.getElementById('modal-content').value = content;
        document.getElementById('transcription-modal').style.display = 'block';
    }

    static closeTranscriptionModal() {
        document.getElementById('transcription-modal').style.display = 'none';
        
        // reset copy button if timeout is active
        if (this.copyTimeout) {
            clearTimeout(this.copyTimeout);
            this.copyTimeout = null;
            const copyBtn = document.querySelector('.copy-btn');
            copyBtn.textContent = 'copy to clipboard';
            copyBtn.style.background = '';
        }
    }

    static async copyToClipboard() {
        try {
            const textarea = document.getElementById('modal-content');
            const text = textarea.value;
            
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
            } else {
                // fallback for older browsers or non-https
                textarea.select();
                textarea.setSelectionRange(0, 99999);
                document.execCommand('copy');
            }
            
            // visual feedback
            const copyBtn = document.querySelector('.copy-btn');
            
            // prevent multiple clicks from interfering
            if (copyBtn.textContent === 'copied!') {
                return;
            }
            
            const originalText = 'copy to clipboard';
            copyBtn.textContent = 'copied!';
            copyBtn.style.background = '#27ae60';
            
            // clear any existing timeout
            if (this.copyTimeout) {
                clearTimeout(this.copyTimeout);
            }
            
            this.copyTimeout = setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.style.background = '';
                this.copyTimeout = null;
            }, 1500);
            
            updateStatus('transcription copied to clipboard');
            
        } catch (error) {
            console.error('failed to copy text:', error);
            updateStatus('failed to copy to clipboard');
        }
    }

    static showDuplicateModal(filename, uploadData) {
        APP_STATE.pendingDuplicateData = uploadData;
        
        document.getElementById('duplicate-filename').textContent = filename;
        document.getElementById('duplicate-modal').style.display = 'block';
        
        // set up overwrite button event
        document.getElementById('duplicate-overwrite').onclick = () => {
            this.closeDuplicateModal();
            // proceed with upload/processing with overwrite flag
            if (APP_STATE.pendingDuplicateData.type === 'file') {
                this.proceedWithFileUpload(APP_STATE.pendingDuplicateData.file, true);
            } else if (APP_STATE.pendingDuplicateData.type === 'url') {
                this.proceedWithUrlUpload(APP_STATE.pendingDuplicateData.url, true);
            }
        };
    }

    static closeDuplicateModal() {
        document.getElementById('duplicate-modal').style.display = 'none';
        APP_STATE.pendingDuplicateData = null;
    }

    static async proceedWithFileUpload(file, overwrite = false) {
        // implementation for file upload with overwrite support
        // this would need backend support for overwrite flag
        const { UploadModule } = await import('./upload.js');
        UploadModule.uploadFile(file);
    }

    static async proceedWithUrlUpload(url, overwrite = false) {
        // implementation for url upload with overwrite support  
        // this would need backend support for overwrite flag
        const { UploadModule } = await import('./upload.js');
        UploadModule.addUrl();
    }
}
