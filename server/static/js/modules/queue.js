// queue management functionality  
import { CONFIG, APP_STATE } from '../core/config.js';
import { updateStatus, getTimeAgo } from '../core/utils.js';
import { ApiService } from '../services/api.js';

export class QueueModule {
    static init() {
        // only bind sort controls - management buttons use onclick handlers
        document.getElementById('queue-sort-by').addEventListener('change', () => this.refreshStatus());
        document.getElementById('queue-sort-order').addEventListener('change', () => this.refreshStatus());
    }

    static async refreshStatus(force = false) {
        // debounce queue refreshes to avoid rapid API calls (unless forced)
        if (APP_STATE.queueRefreshTimeout && !force) {
            clearTimeout(APP_STATE.queueRefreshTimeout);
        }
        
        const delay = force ? 0 : 100; // immediate refresh when forced
        APP_STATE.queueRefreshTimeout = setTimeout(async () => {
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
                
                // update activity state for adaptive polling
                this.updateActivityState(statusData);
                
                updateStatus(`queue: ${statusData.total_items} items`);
                
            } catch (error) {
                updateStatus(`error refreshing: ${error.message}`);
            } finally {
                APP_STATE.queueRefreshTimeout = null;
            }
        }, delay); // debounce delay (0 if forced)
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
                    // use video title for youtube urls, filename for files
                    valueA = a.url && a.video_title ? a.video_title.toLowerCase() : 
                            (a.file_path ? a.file_path.split('/').pop().toLowerCase() : (a.url || '').toLowerCase());
                    valueB = b.url && b.video_title ? b.video_title.toLowerCase() : 
                            (b.file_path ? b.file_path.split('/').pop().toLowerCase() : (b.url || '').toLowerCase());
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

    static updateActivityState(statusData) {
        // detect if queue has active processing items
        const activeCount = (statusData.status_counts.downloading || 0) + 
                           (statusData.status_counts.converting || 0) + 
                           (statusData.status_counts.transcribing || 0) +
                           (statusData.status_counts.queued || 0);
        
        APP_STATE.hasActiveItems = activeCount > 0;
        
        // adjust polling interval based on activity
        if (activeCount > 0) {
            APP_STATE.currentInterval = CONFIG.REFRESH_INTERVAL; // 2s when active
        } else if (statusData.total_items > 0) {
            APP_STATE.currentInterval = CONFIG.REFRESH_INTERVAL_IDLE; // 10s when idle but has items
        } else {
            APP_STATE.currentInterval = CONFIG.REFRESH_INTERVAL_INACTIVE; // 30s when empty
        }
        
        // force faster refresh if we just detected a major status change
        const completedCount = statusData.status_counts.completed || 0;
        if (completedCount !== APP_STATE.lastCompletedCount) {
            APP_STATE.currentInterval = Math.min(APP_STATE.currentInterval, CONFIG.REFRESH_INTERVAL);
        }
    }

    static async refreshStats() {
        try {
            const data = await ApiService.get(CONFIG.API_ENDPOINTS.QUEUE_STATUS);
            this.updateQueueStats(data);
        } catch (error) {
            console.error('error refreshing queue stats:', error);
            updateStatus(`error refreshing stats: ${error.message}`);
        }
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
            const displayName = item.url && item.video_title ? item.video_title : 
                               (item.file_path ? item.file_path.split('/').pop() : item.url);
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
                <div class="queue-item" data-item-id="${item.id}">
                    <div class="item-info">
                        <div class="item-name">${displayName}</div>
                        <div class="item-details">
                            ${item.url ? `type: youtube video` : `path: ${item.file_path}`}<br>
                            updated: ${timeAgo}
                            ${item.error_message ? `<br>error: ${item.error_message}` : ''}
                        </div>
                    </div>
                    <div class="item-status status-${item.status}">${item.status === 'pending_duplicate' ? 'duplicate detected' : item.status}</div>
                    <div class="item-actions">
                        ${APP_STATE.queueManagementMode ? '' : actionButtons}
                    </div>
                    ${checkboxHtml}
                </div>
            `;
        }).join('');
    }

    static async removeItem(itemId) {
        try {
            // optimistically remove item from DOM first for instant feedback
            const queueItem = document.querySelector(`.queue-item[data-item-id="${itemId}"]`);
            if (queueItem) {
                queueItem.style.opacity = '0.5';
                queueItem.style.pointerEvents = 'none';
            }
            
            const result = await ApiService.delete(`/api/queue/item/${itemId}`);
            
            if (result.success) {
                const action = result.action || 'updated';
                updateStatus(`item ${action} successfully`);
                
                // remove item from DOM instead of full refresh
                if (queueItem) {
                    queueItem.remove();
                }
                
                // only update stats, not the whole queue
                this.refreshStats();
            } else {
                updateStatus(`failed: ${result.error}`);
                // restore item appearance on failure
                if (queueItem) {
                    queueItem.style.opacity = '1';
                    queueItem.style.pointerEvents = 'auto';
                }
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
            // restore item appearance on error
            const queueItem = document.querySelector(`.queue-item[data-item-id="${itemId}"]`);
            if (queueItem) {
                queueItem.style.opacity = '1';
                queueItem.style.pointerEvents = 'auto';
            }
        }
    }

    static async resolveDuplicate(itemId, action) {
        try {
            updateStatus(`resolving duplicate: ${action}...`);
            
            const result = await ApiService.post(`${CONFIG.API_ENDPOINTS.RESOLVE_DUPLICATE}/${itemId}`, { action });
            
            if (result.success) {
                updateStatus(result.message);
                this.refreshStatus();
                
                // clear any duplicate upload progress items
                this.clearDuplicateUploadItems();
                
                // refresh transcriptions since resolving duplicates can add/remove them
                if (action === 'overwrite') {
                    const { TranscriptionsModule } = await import('./transcriptions.js');
                    TranscriptionsModule.loadTranscriptions();
                }
            } else {
                updateStatus(`failed: ${result.error}`);
            }
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }

    static clearDuplicateUploadItems() {
        // remove any upload progress items showing duplicate errors
        const progressItems = document.querySelectorAll('.progress-item');
        progressItems.forEach(item => {
            const statusText = item.querySelector('.progress-status')?.textContent;
            if (statusText && statusText.includes('duplicate')) {
                item.remove();
            }
        });
    }

    static toggleManagement() {
        APP_STATE.queueManagementMode = !APP_STATE.queueManagementMode;
        APP_STATE.selectedQueueItems.clear();
        
        const manageBtn = document.getElementById('queue-manage-btn');
        const actionsDiv = document.getElementById('queue-actions');
        const selectAllBtn = document.getElementById('queue-select-all');
        
        if (APP_STATE.queueManagementMode) {
            manageBtn.textContent = 'done';
            actionsDiv.style.display = 'flex';
        } else {
            manageBtn.textContent = 'manage';
            actionsDiv.style.display = 'none';
            // reset select all button when exiting management mode
            selectAllBtn.textContent = 'select all';
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
            // separate duplicate items from regular items
            const queueItems = document.querySelectorAll('.queue-item');
            const duplicateIds = new Set();
            const regularIds = new Set();
            
            queueItems.forEach(item => {
                const checkbox = item.querySelector('.item-checkbox');
                if (checkbox && checkbox.checked) {
                    const statusElement = item.querySelector('[class*="status-"]');
                    if (statusElement && statusElement.className.includes('status-pending_duplicate')) {
                        const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
                        duplicateIds.add(itemId);
                    } else {
                        const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
                        regularIds.add(itemId);
                    }
                }
            });
            
            let successCount = 0;
            let totalCount = APP_STATE.selectedQueueItems.size;
            
            // handle duplicate items by canceling them
            for (const itemId of duplicateIds) {
                try {
                    const result = await ApiService.post(`${CONFIG.API_ENDPOINTS.RESOLVE_DUPLICATE}/${itemId}`, { action: 'cancel' });
                    if (result.success) {
                        successCount++;
                    }
                } catch (error) {
                    console.error(`failed to cancel duplicate ${itemId}:`, error);
                }
            }
            
            // handle regular items through bulk delete
            if (regularIds.size > 0) {
                const result = await ApiService.delete(CONFIG.API_ENDPOINTS.QUEUE_ITEMS, { 
                    ids: Array.from(regularIds) 
                });
                if (result.success) {
                    successCount += result.removed_count || result.cancelled_count || regularIds.size;
                }
            }
            
            if (successCount > 0) {
                updateStatus(`processed ${successCount} of ${totalCount} selected items`);
                APP_STATE.selectedQueueItems.clear();
                this.refreshStatus();
                this.updateSelectedCount();
            } else {
                updateStatus(`failed to process selected items`);
            }
            
        } catch (error) {
            updateStatus(`error: ${error.message}`);
        }
    }
}
