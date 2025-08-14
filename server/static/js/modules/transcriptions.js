// transcriptions management functionality
import { CONFIG, APP_STATE } from '../core/config.js';
import { updateStatus } from '../core/utils.js';
import { ApiService } from '../services/api.js';

export class TranscriptionsModule {
    static init() {
        // only bind sort controls - management buttons use onclick handlers
        document.getElementById('sort-by').addEventListener('change', () => this.loadTranscriptions());
        document.getElementById('sort-order').addEventListener('change', () => this.loadTranscriptions());
    }

    static async loadTranscriptions() {
        try {
            const sortBy = document.getElementById('sort-by')?.value || 'id';
            const sortOrder = document.getElementById('sort-order')?.value || 'desc';
            
            const data = await ApiService.get(`${CONFIG.API_ENDPOINTS.TRANSCRIPTIONS}?sort_by=${sortBy}&sort_order=${sortOrder}`);
            
            if (data.transcriptions) {
                this.updateTranscriptionsTable(data.transcriptions);
            }
            
        } catch (error) {
            console.error('error loading transcriptions:', error);
            updateStatus(`error loading transcriptions: ${error.message}`);
        }
    }

    static updateTranscriptionsTable(transcriptions) {
        const container = document.getElementById('transcriptions-list');
        const countElement = document.getElementById('transcriptions-count');
        
        // update count
        const count = transcriptions ? transcriptions.length : 0;
        countElement.textContent = `${count} total`;
        
        if (!transcriptions || transcriptions.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--fg2); padding: 20px;">no transcriptions available</div>';
            return;
        }
        
        container.innerHTML = transcriptions.map(item => {
            const checkboxHtml = APP_STATE.transcriptionsManagementMode ? 
                `<input type="checkbox" class="item-checkbox" onchange="TranscriptionsModule.toggleItemSelection(${item.id})" onclick="event.stopPropagation()" ${APP_STATE.selectedTranscriptions.has(item.id) ? 'checked' : ''}>` : '';
            
            return `
                <div class="transcription-item" ${!APP_STATE.transcriptionsManagementMode ? `onclick="TranscriptionsModule.viewTranscription(${item.id}, '${item.filename}')" style="cursor: pointer;"` : ''}>
                    <div class="transcription-info">
                        <div class="transcription-id">${item.id}</div>
                        <div class="transcription-filename">${item.filename}</div>
                        <div class="transcription-time">${item.transcribed_time}</div>
                    </div>
                    ${checkboxHtml}
                </div>
            `;
        }).join('');
    }

    static async viewTranscription(id, filename) {
        try {
            const data = await ApiService.get(`${CONFIG.API_ENDPOINTS.TRANSCRIPTIONS}/${id}`);
            
            if (data.content) {
                // use modal module to show transcription
                const { ModalModule } = await import('./modal.js');
                ModalModule.showTranscription(filename, data.content);
            }
            
        } catch (error) {
            console.error('error loading transcription content:', error);
            updateStatus(`error loading transcription: ${error.message}`);
        }
    }

    static toggleManagement() {
        APP_STATE.transcriptionsManagementMode = !APP_STATE.transcriptionsManagementMode;
        APP_STATE.selectedTranscriptions.clear();
        
        const manageBtn = document.getElementById('transcriptions-manage-btn');
        const actionsDiv = document.getElementById('transcriptions-actions');
        
        if (APP_STATE.transcriptionsManagementMode) {
            manageBtn.textContent = 'done';
            actionsDiv.style.display = 'flex';
        } else {
            manageBtn.textContent = 'manage';
            actionsDiv.style.display = 'none';
        }
        
        this.loadTranscriptions();
    }

    static toggleItemSelection(itemId) {
        if (APP_STATE.selectedTranscriptions.has(itemId)) {
            APP_STATE.selectedTranscriptions.delete(itemId);
        } else {
            APP_STATE.selectedTranscriptions.add(itemId);
        }
        this.updateSelectedCount();
    }

    static toggleSelectAll() {
        const checkboxes = document.querySelectorAll('#transcriptions-list .item-checkbox');
        const selectAllBtn = document.getElementById('transcriptions-select-all');
        
        if (APP_STATE.selectedTranscriptions.size === checkboxes.length) {
            APP_STATE.selectedTranscriptions.clear();
            selectAllBtn.textContent = 'select all';
        } else {
            checkboxes.forEach(checkbox => {
                const itemId = parseInt(checkbox.onchange.toString().match(/\((\d+)\)/)[1]);
                APP_STATE.selectedTranscriptions.add(itemId);
            });
            selectAllBtn.textContent = 'deselect all';
        }
        
        checkboxes.forEach(checkbox => {
            const itemId = parseInt(checkbox.onchange.toString().match(/\((\d+)\)/)[1]);
            checkbox.checked = APP_STATE.selectedTranscriptions.has(itemId);
        });
        
        this.updateSelectedCount();
    }

    static updateSelectedCount() {
        const deleteBtn = document.getElementById('transcriptions-delete-selected');
        const count = APP_STATE.selectedTranscriptions.size;
        
        if (count > 0) {
            deleteBtn.textContent = `delete selected (${count})`;
            deleteBtn.disabled = false;
        } else {
            deleteBtn.textContent = 'delete selected';
            deleteBtn.disabled = true;
        }
    }

    static async deleteSelected() {
        if (APP_STATE.selectedTranscriptions.size === 0) return;
        
        try {
            const result = await ApiService.delete(CONFIG.API_ENDPOINTS.TRANSCRIPTIONS, { 
                ids: Array.from(APP_STATE.selectedTranscriptions) 
            });
            
            if (result.success) {
                updateStatus(`deleted ${result.deleted_count} transcriptions`);
                APP_STATE.selectedTranscriptions.clear();
                this.loadTranscriptions();
                this.updateSelectedCount();
                
                // notify other tabs that transcriptions changed
                this.notifyTranscriptionsChanged();
            } else {
                updateStatus(`failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }
    
    static notifyTranscriptionsChanged() {
        // trigger an immediate refresh if we're on transcriptions tab
        if (APP_STATE.currentTab === 'transcriptions') {
            this.loadTranscriptions();
        }
        
        // update the count for queue tab monitoring
        // reset last completed count to ensure we detect future changes
        if (APP_STATE.lastCompletedCount) {
            APP_STATE.lastCompletedCount = Math.max(0, APP_STATE.lastCompletedCount - 1);
        }
    }
}
