// queue management functionality  
import { CONFIG, APP_STATE } from '../core/config.js';
import { updateStatus, getTimeAgo } from '../core/utils.js';
import { ApiService } from '../services/api.js';

export class QueueModule {
    static init() {
        // bind event listeners for queue controls
        document.getElementById('queue-manage-btn').addEventListener('click', () => this.toggleManagement());
        document.getElementById('queue-select-all').addEventListener('click', () => this.toggleSelectAll());
        document.getElementById('queue-delete-selected').addEventListener('click', () => this.deleteSelected());
        document.getElementById('queue-cancel-selection').addEventListener('click', () => this.toggleManagement());
        
        // sort controls
        document.getElementById('queue-sort-by').addEventListener('change', () => this.refreshStatus());
        document.getElementById('queue-sort-order').addEventListener('change', () => this.refreshStatus());
    }

    static async refreshStatus() {
        try {
            const [statusData, itemsData] = await Promise.all([
                ApiService.get(CONFIG.API_ENDPOINTS.QUEUE_STATUS),
                ApiService.get(CONFIG.API_ENDPOINTS.QUEUE_ITEMS)
            ]);
            
            const sortBy = document.getElementById('queue-sort-by')?.value || 'updated_at';
            const sortOrder = document.getElementById('queue-sort-order')?.value || 'desc';
            const sortedItems = this.sortQueueItems(itemsData.items, sortBy, sortOrder);
            
            this.updateQueueStats(statusData);
            this.updateQueueItems(sortedItems);
            
            updateStatus(`queue: ${statusData.total_items} items`);
            
        } catch (error) {
            updateStatus(`error refreshing: ${error.message}`);
        }
    }

    static sortQueueItems(items, sortBy, sortOrder) {
        if (!items || items.length === 0) return items;
        
        return items.sort((a, b) => {
            let valueA, valueB;
            
            switch(sortBy) {
                case 'status':
                    valueA = a.status;
                    valueB = b.status;
                    break;
                case 'created_at':
                    valueA = new Date(a.created_at);
                    valueB = new Date(b.created_at);
                    break;
                case 'updated_at':
                    valueA = new Date(a.updated_at);
                    valueB = new Date(b.updated_at);
                    break;
                case 'file_path':
                    valueA = a.file_path ? a.file_path.split('/').pop().toLowerCase() : (a.url || '').toLowerCase();
                    valueB = b.file_path ? b.file_path.split('/').pop().toLowerCase() : (b.url || '').toLowerCase();
                    break;
                default:
                    valueA = new Date(a.updated_at);
                    valueB = new Date(b.updated_at);
            }
            
            let comparison = 0;
            if (valueA < valueB) comparison = -1;
            if (valueA > valueB) comparison = 1;
            
            return sortOrder === 'desc' ? -comparison : comparison;
        });
    }

    static updateQueueStats(statusData) {
        const statsContainer = document.getElementById('queue-stats');
        
        const stats = [
            { label: 'total', value: statusData.total_items },
            { label: 'queued', value: statusData.status_counts.queued || 0 },
            { label: 'downloading', value: statusData.status_counts.downloading || 0 },
            { label: 'converting', value: statusData.status_counts.converting || 0 },
            { label: 'transcribing', value: statusData.status_counts.transcribing || 0 },
            { label: 'duplicates', value: statusData.status_counts.pending_duplicate || 0 },
            { label: 'completed', value: statusData.status_counts.completed || 0 },
            { label: 'failed', value: statusData.status_counts.failed || 0 },
            { label: 'cancelled', value: statusData.status_counts.cancelled || 0 }
        ];
        
        statsContainer.innerHTML = stats.map(stat => `
            <div class="stat-item">
                <div class="stat-number">${stat.value}</div>
                <div class="stat-label">${stat.label}</div>
            </div>
        `).join('');
    }

    static updateQueueItems(items) {
        const itemsContainer = document.getElementById('queue-items');
        
        if (!items || items.length === 0) {
            itemsContainer.innerHTML = '<p style="text-align: center; color: #666;">no items in queue</p>';
            return;
        }
        
        itemsContainer.innerHTML = items.map(item => {
            const fileName = item.file_path ? item.file_path.split('/').pop() : item.url;
            const timeAgo = getTimeAgo(new Date(item.updated_at));
            
            const activeStates = ['queued', 'downloading', 'converting', 'transcribing'];
            const finishedStates = ['completed', 'failed', 'cancelled', 'skipped'];
            const duplicateStates = ['pending_duplicate'];
            
            let actionButtons = '';
            
            if (duplicateStates.includes(item.status)) {
                actionButtons = `
                    <button class="warning-btn" onclick="QueueModule.resolveDuplicate('${item.id}', 'overwrite')">overwrite</button>
                    <button class="delete-btn" onclick="QueueModule.resolveDuplicate('${item.id}', 'cancel')">cancel</button>
                `;
            } else if (activeStates.includes(item.status)) {
                actionButtons = `<button class="cancel-btn" onclick="QueueModule.removeItem('${item.id}')">cancel</button>`;
            } else if (finishedStates.includes(item.status)) {
                actionButtons = `<button class="delete-btn" onclick="QueueModule.removeItem('${item.id}')">remove</button>`;
            }
            
            const checkboxHtml = APP_STATE.queueManagementMode ? 
                `<input type="checkbox" class="item-checkbox" onchange="QueueModule.toggleItemSelection('${item.id}')" ${APP_STATE.selectedQueueItems.has(item.id) ? 'checked' : ''}>` : '';
            
            return `
                <div class="queue-item">
                    ${checkboxHtml}
                    <div class="item-info">
                        <div class="item-name">${fileName}</div>
                        <div class="item-details">
                            ${item.url ? `url: ${item.url}` : `path: ${item.file_path}`}<br>
                            updated: ${timeAgo}
                            ${item.error_message ? `<br>error: ${item.error_message}` : ''}
                        </div>
                    </div>
                    <div class="item-status status-${item.status}">${item.status === 'pending_duplicate' ? 'duplicate detected' : item.status}</div>
                    <div class="item-actions">
                        ${APP_STATE.queueManagementMode ? '' : actionButtons}
                    </div>
                </div>
            `;
        }).join('');
    }

    static async removeItem(itemId) {
        try {
            const result = await ApiService.delete(`/api/queue/item/${itemId}`);
            
            if (result.success) {
                const action = result.action || 'updated';
                updateStatus(`item ${action} successfully`);
                this.refreshStatus();
            } else {
                updateStatus(`failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }

    static async resolveDuplicate(itemId, action) {
        try {
            updateStatus(`resolving duplicate: ${action}...`);
            
            const result = await ApiService.post(`${CONFIG.API_ENDPOINTS.RESOLVE_DUPLICATE}/${itemId}`, { action });
            
            if (result.success) {
                updateStatus(result.message);
                this.refreshStatus();
            } else {
                updateStatus(`failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }

    static toggleManagement() {
        APP_STATE.queueManagementMode = !APP_STATE.queueManagementMode;
        APP_STATE.selectedQueueItems.clear();
        
        const manageBtn = document.getElementById('queue-manage-btn');
        const actionsDiv = document.getElementById('queue-actions');
        
        if (APP_STATE.queueManagementMode) {
            manageBtn.textContent = 'done';
            actionsDiv.style.display = 'flex';
        } else {
            manageBtn.textContent = 'manage';
            actionsDiv.style.display = 'none';
        }
        
        this.refreshStatus();
    }

    static toggleItemSelection(itemId) {
        if (APP_STATE.selectedQueueItems.has(itemId)) {
            APP_STATE.selectedQueueItems.delete(itemId);
        } else {
            APP_STATE.selectedQueueItems.add(itemId);
        }
        this.updateSelectedCount();
    }

    static toggleSelectAll() {
        const checkboxes = document.querySelectorAll('#queue-items .item-checkbox');
        const selectAllBtn = document.getElementById('queue-select-all');
        
        if (APP_STATE.selectedQueueItems.size === checkboxes.length) {
            APP_STATE.selectedQueueItems.clear();
            selectAllBtn.textContent = 'select all';
        } else {
            checkboxes.forEach(checkbox => {
                const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
                APP_STATE.selectedQueueItems.add(itemId);
            });
            selectAllBtn.textContent = 'deselect all';
        }
        
        checkboxes.forEach(checkbox => {
            const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
            checkbox.checked = APP_STATE.selectedQueueItems.has(itemId);
        });
        
        this.updateSelectedCount();
    }

    static updateSelectedCount() {
        const deleteBtn = document.getElementById('queue-delete-selected');
        const count = APP_STATE.selectedQueueItems.size;
        
        if (count > 0) {
            deleteBtn.textContent = `remove selected (${count})`;
            deleteBtn.disabled = false;
        } else {
            deleteBtn.textContent = 'remove selected';
            deleteBtn.disabled = true;
        }
    }

    static async deleteSelected() {
        if (APP_STATE.selectedQueueItems.size === 0) return;
        
        try {
            const result = await ApiService.delete(CONFIG.API_ENDPOINTS.QUEUE_ITEMS, { 
                ids: Array.from(APP_STATE.selectedQueueItems) 
            });
            
            if (result.success) {
                updateStatus(result.message);
                APP_STATE.selectedQueueItems.clear();
                this.refreshStatus();
                this.updateSelectedCount();
            } else {
                updateStatus(`failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }
}
