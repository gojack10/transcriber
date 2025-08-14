// transcription automation frontend javascript

let statusInterval;
let currentTab = 'queue';
let queueManagementMode = false;
let transcriptionsManagementMode = false;
let selectedQueueItems = new Set();
let selectedTranscriptions = new Set();
let pendingDuplicateData = null;

// initialize app when dom loads
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    refreshStatus();
    loadTranscriptions();
    // auto-refresh every 2 seconds
    statusInterval = setInterval(() => {
        if (currentTab === 'queue') {
            refreshStatus();
        }
    }, 2000);
});

function initializeEventListeners() {
    // file upload drag and drop
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });
    
    // url input enter key
    document.getElementById('url-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addUrl();
        }
    });
}

async function handleFiles(files) {
    const progressContainer = document.getElementById('upload-progress');
    progressContainer.style.display = 'block';
    
    for (const file of files) {
        await uploadFile(file);
    }
    
    // hide progress after a delay
    setTimeout(() => {
        progressContainer.style.display = 'none';
        progressContainer.innerHTML = '';
    }, 3000);
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const progressContainer = document.getElementById('upload-progress');
    const progressId = `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // add progress item with progress bar
    const progressItem = document.createElement('div');
    progressItem.className = 'progress-item';
    progressItem.id = progressId;
    progressItem.innerHTML = `
        <div class="progress-filename">${file.name}</div>
        <div class="progress-status uploading">uploading...</div>
        <div class="upload-progress-bar">
            <div class="upload-progress-fill"></div>
        </div>
        <div class="upload-progress-text">0%</div>
    `;
    progressContainer.appendChild(progressItem);
    
    try {
        updateStatus(`uploading ${file.name}...`);
        
        // use xhr for progress tracking
        const xhr = new XMLHttpRequest();
        
        // track upload progress
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                const progressFill = progressItem.querySelector('.upload-progress-fill');
                const progressText = progressItem.querySelector('.upload-progress-text');
                
                progressFill.style.width = `${percentComplete}%`;
                progressText.textContent = `${Math.round(percentComplete)}%`;
            }
        });
        
        // handle completion
        xhr.addEventListener('load', () => {
            const statusElement = progressItem.querySelector('.progress-status');
            
            if (xhr.status === 200) {
                const result = JSON.parse(xhr.responseText);
                
                if (result.success) {
                    updateStatus(`${file.name} uploaded successfully`);
                    statusElement.textContent = 'success';
                    statusElement.className = 'progress-status success';
                    refreshStatus();
                } else {
                    updateStatus(`upload failed: ${result.error}`);
                    statusElement.textContent = `failed: ${result.error}`;
                    statusElement.className = 'progress-status error';
                }
            } else {
                updateStatus(`upload error: ${xhr.status}`);
                statusElement.textContent = `error: ${xhr.status}`;
                statusElement.className = 'progress-status error';
            }
        });
        
        xhr.addEventListener('error', () => {
            updateStatus(`upload error: network error`);
            const statusElement = progressItem.querySelector('.progress-status');
            statusElement.textContent = 'network error';
            statusElement.className = 'progress-status error';
        });
        
        xhr.open('POST', '/api/queue/file');
        xhr.send(formData);
        
    } catch (error) {
        updateStatus(`upload error: ${error.message}`);
        const statusElement = progressItem.querySelector('.progress-status');
        statusElement.textContent = `error: ${error.message}`;
        statusElement.className = 'progress-status error';
    }
}

async function addUrl() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    
    if (!url) {
        updateStatus('please enter a url');
        return;
    }
    
    const progressContainer = document.getElementById('url-progress');
    const progressId = `url-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // show progress and add item
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
        
        const response = await fetch('/api/queue/link', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url })
        });
        
        const result = await response.json();
        
        const statusElement = progressItem.querySelector('.progress-status');
        
        if (result.success) {
            updateStatus(`url added to queue successfully`);
            statusElement.textContent = 'added to queue';
            statusElement.className = 'progress-status success';
            urlInput.value = '';
            refreshStatus();
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
    
    // hide progress after delay
    setTimeout(() => {
        progressContainer.style.display = 'none';
        progressContainer.innerHTML = '';
    }, 3000);
}

async function refreshStatus() {
    try {
        const [statusResponse, itemsResponse] = await Promise.all([
            fetch('/api/queue/status'),
            fetch('/api/queue/items')
        ]);
        
        const statusData = await statusResponse.json();
        const itemsData = await itemsResponse.json();
        
        // sort items based on selected criteria
        const sortBy = document.getElementById('queue-sort-by')?.value || 'updated_at';
        const sortOrder = document.getElementById('queue-sort-order')?.value || 'desc';
        const sortedItems = sortQueueItems(itemsData.items, sortBy, sortOrder);
        
        updateQueueStats(statusData);
        updateQueueItems(sortedItems);
        
        updateStatus(`queue: ${statusData.total_items} items`);
        
    } catch (error) {
        updateStatus(`error refreshing: ${error.message}`);
    }
}

function sortQueueItems(items, sortBy, sortOrder) {
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
                // get filename from path or use url
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

function updateQueueStats(statusData) {
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

function updateQueueItems(items) {
    const itemsContainer = document.getElementById('queue-items');
    
    if (!items || items.length === 0) {
        itemsContainer.innerHTML = '<p style="text-align: center; color: #666;">no items in queue</p>';
        return;
    }
    
    itemsContainer.innerHTML = items.map(item => {
        const fileName = item.file_path ? item.file_path.split('/').pop() : item.url;
        const timeAgo = getTimeAgo(new Date(item.updated_at));
        
        // determine button text and style based on status
        const activeStates = ['queued', 'downloading', 'converting', 'transcribing'];
        const finishedStates = ['completed', 'failed', 'cancelled', 'skipped'];
        const duplicateStates = ['pending_duplicate'];
        
        let buttonText = 'remove';
        let buttonClass = 'delete-btn';
        let actionButtons = '';
        
        if (duplicateStates.includes(item.status)) {
            actionButtons = `
                <button class="warning-btn" onclick="resolveDuplicate('${item.id}', 'overwrite')">overwrite</button>
                <button class="delete-btn" onclick="resolveDuplicate('${item.id}', 'cancel')">cancel</button>
            `;
        } else if (activeStates.includes(item.status)) {
            buttonText = 'cancel';
            buttonClass = 'cancel-btn';
            actionButtons = `<button class="${buttonClass}" onclick="removeItem('${item.id}')">${buttonText}</button>`;
        } else if (finishedStates.includes(item.status)) {
            buttonText = 'remove';
            buttonClass = 'delete-btn';
            actionButtons = `<button class="${buttonClass}" onclick="removeItem('${item.id}')">${buttonText}</button>`;
        }
        
        const checkboxHtml = queueManagementMode ? 
            `<input type="checkbox" class="item-checkbox" onchange="toggleQueueItemSelection('${item.id}')" ${selectedQueueItems.has(item.id) ? 'checked' : ''}>` : '';
        
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
                    ${queueManagementMode ? '' : actionButtons}
                </div>
            </div>
        `;
    }).join('');
}

async function removeItem(itemId) {
    try {
        const response = await fetch(`/api/queue/item/${itemId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            const action = result.action || 'updated';
            updateStatus(`item ${action} successfully`);
            refreshStatus();
        } else {
            updateStatus(`failed: ${result.error}`);
        }
    } catch (error) {
        updateStatus(`error: ${error.message}`);
    }
}

function updateStatus(message) {
    document.getElementById('status-text').textContent = message;
}

function getTimeAgo(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// tab switching
function switchTab(tabName) {
    currentTab = tabName;
    
    // update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
    
    // update tab content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // load data for active tab
    if (tabName === 'transcriptions') {
        loadTranscriptions();
    } else if (tabName === 'queue') {
        refreshStatus();
    }
}

// transcriptions functionality
async function loadTranscriptions() {
    try {
        const sortBy = document.getElementById('sort-by')?.value || 'id';
        const sortOrder = document.getElementById('sort-order')?.value || 'desc';
        
        const response = await fetch(`/api/transcriptions?sort_by=${sortBy}&sort_order=${sortOrder}`);
        const data = await response.json();
        
        if (data.transcriptions) {
            updateTranscriptionsTable(data.transcriptions);
        }
        
    } catch (error) {
        console.error('error loading transcriptions:', error);
        updateStatus(`error loading transcriptions: ${error.message}`);
    }
}

function updateTranscriptionsTable(transcriptions) {
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
        const checkboxHtml = transcriptionsManagementMode ? 
            `<input type="checkbox" class="item-checkbox" onchange="toggleTranscriptionSelection(${item.id})" ${selectedTranscriptions.has(item.id) ? 'checked' : ''}>` : '';
        
        return `
            <div class="transcription-item">
                ${checkboxHtml}
                <div class="transcription-info">
                    <div class="transcription-id">${item.id}</div>
                    <div class="transcription-filename">${item.filename}</div>
                    <div class="transcription-time">${item.transcribed_time}</div>
                </div>
                <div class="transcription-actions">
                    ${transcriptionsManagementMode ? '' : `<button class="view-btn" onclick="viewTranscription(${item.id}, '${item.filename}')">view</button>`}
                </div>
            </div>
        `;
    }).join('');
}

async function viewTranscription(id, filename) {
    try {
        const response = await fetch(`/api/transcriptions/${id}`);
        const data = await response.json();
        
        if (data.content) {
            document.getElementById('modal-title').textContent = filename;
            document.getElementById('modal-content').value = data.content;
            document.getElementById('transcription-modal').style.display = 'block';
        }
        
    } catch (error) {
        console.error('error loading transcription content:', error);
        updateStatus(`error loading transcription: ${error.message}`);
    }
}

function closeModal() {
    document.getElementById('transcription-modal').style.display = 'none';
}

async function copyToClipboard() {
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
        const originalText = copyBtn.textContent;
        copyBtn.textContent = 'copied!';
        copyBtn.style.background = '#27ae60';
        
        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.style.background = '';
        }, 1500);
        
        updateStatus('transcription copied to clipboard');
        
    } catch (error) {
        console.error('failed to copy text:', error);
        updateStatus('failed to copy to clipboard');
    }
}

// close modal when clicking outside
window.addEventListener('click', function(event) {
    const modal = document.getElementById('transcription-modal');
    if (event.target === modal) {
        closeModal();
    }
});

// keyboard shortcuts for modal
document.addEventListener('keydown', function(event) {
    const modal = document.getElementById('transcription-modal');
    if (modal.style.display === 'block') {
        // escape to close
        if (event.key === 'Escape') {
            closeModal();
        }
        // ctrl+c to copy (additional shortcut)
        if (event.ctrlKey && event.key === 'c' && event.target.id !== 'modal-content') {
            event.preventDefault();
            copyToClipboard();
        }
    }
});

// queue management functions
function toggleQueueManagement() {
    queueManagementMode = !queueManagementMode;
    selectedQueueItems.clear();
    
    const manageBtn = document.getElementById('queue-manage-btn');
    const actionsDiv = document.getElementById('queue-actions');
    
    if (queueManagementMode) {
        manageBtn.textContent = 'done';
        actionsDiv.style.display = 'flex';
    } else {
        manageBtn.textContent = 'manage';
        actionsDiv.style.display = 'none';
    }
    
    refreshStatus(); // refresh to show/hide checkboxes
}

function toggleQueueItemSelection(itemId) {
    if (selectedQueueItems.has(itemId)) {
        selectedQueueItems.delete(itemId);
    } else {
        selectedQueueItems.add(itemId);
    }
    updateSelectedQueueCount();
}

function toggleSelectAllQueue() {
    const checkboxes = document.querySelectorAll('#queue-items .item-checkbox');
    const selectAllBtn = document.getElementById('queue-select-all');
    
    if (selectedQueueItems.size === checkboxes.length) {
        // deselect all
        selectedQueueItems.clear();
        selectAllBtn.textContent = 'select all';
    } else {
        // select all
        checkboxes.forEach(checkbox => {
            const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
            selectedQueueItems.add(itemId);
        });
        selectAllBtn.textContent = 'deselect all';
    }
    
    // update checkbox states
    checkboxes.forEach(checkbox => {
        const itemId = checkbox.onchange.toString().match(/'([^']+)'/)[1];
        checkbox.checked = selectedQueueItems.has(itemId);
    });
    
    updateSelectedQueueCount();
}

function updateSelectedQueueCount() {
    const deleteBtn = document.getElementById('queue-delete-selected');
    const count = selectedQueueItems.size;
    
    if (count > 0) {
        deleteBtn.textContent = `remove selected (${count})`;
        deleteBtn.disabled = false;
    } else {
        deleteBtn.textContent = 'remove selected';
        deleteBtn.disabled = true;
    }
}

async function deleteSelectedQueueItems() {
    if (selectedQueueItems.size === 0) return;
    
    try {
        const response = await fetch('/api/queue/items', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ids: Array.from(selectedQueueItems) })
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateStatus(result.message);
            selectedQueueItems.clear();
            refreshStatus();
            updateSelectedQueueCount();
        } else {
            updateStatus(`failed: ${result.error}`);
        }
    } catch (error) {
        updateStatus(`error: ${error.message}`);
    }
}

function cancelQueueSelection() {
    toggleQueueManagement();
}

// transcriptions management functions
function toggleTranscriptionsManagement() {
    transcriptionsManagementMode = !transcriptionsManagementMode;
    selectedTranscriptions.clear();
    
    const manageBtn = document.getElementById('transcriptions-manage-btn');
    const actionsDiv = document.getElementById('transcriptions-actions');
    
    if (transcriptionsManagementMode) {
        manageBtn.textContent = 'done';
        actionsDiv.style.display = 'flex';
    } else {
        manageBtn.textContent = 'manage';
        actionsDiv.style.display = 'none';
    }
    
    loadTranscriptions(); // refresh to show/hide checkboxes
}

function toggleTranscriptionSelection(itemId) {
    if (selectedTranscriptions.has(itemId)) {
        selectedTranscriptions.delete(itemId);
    } else {
        selectedTranscriptions.add(itemId);
    }
    updateSelectedTranscriptionsCount();
}

function toggleSelectAllTranscriptions() {
    const checkboxes = document.querySelectorAll('#transcriptions-list .item-checkbox');
    const selectAllBtn = document.getElementById('transcriptions-select-all');
    
    if (selectedTranscriptions.size === checkboxes.length) {
        // deselect all
        selectedTranscriptions.clear();
        selectAllBtn.textContent = 'select all';
    } else {
        // select all
        checkboxes.forEach(checkbox => {
            const itemId = parseInt(checkbox.onchange.toString().match(/\((\d+)\)/)[1]);
            selectedTranscriptions.add(itemId);
        });
        selectAllBtn.textContent = 'deselect all';
    }
    
    // update checkbox states
    checkboxes.forEach(checkbox => {
        const itemId = parseInt(checkbox.onchange.toString().match(/\((\d+)\)/)[1]);
        checkbox.checked = selectedTranscriptions.has(itemId);
    });
    
    updateSelectedTranscriptionsCount();
}

function updateSelectedTranscriptionsCount() {
    const deleteBtn = document.getElementById('transcriptions-delete-selected');
    const count = selectedTranscriptions.size;
    
    if (count > 0) {
        deleteBtn.textContent = `delete selected (${count})`;
        deleteBtn.disabled = false;
    } else {
        deleteBtn.textContent = 'delete selected';
        deleteBtn.disabled = true;
    }
}

async function deleteSelectedTranscriptions() {
    if (selectedTranscriptions.size === 0) return;
    
    try {
        const response = await fetch('/api/transcriptions', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ids: Array.from(selectedTranscriptions) })
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateStatus(`deleted ${result.deleted_count} transcriptions`);
            selectedTranscriptions.clear();
            loadTranscriptions();
            updateSelectedTranscriptionsCount();
        } else {
            updateStatus(`failed: ${result.error}`);
        }
    } catch (error) {
        updateStatus(`error: ${error.message}`);
    }
}

function cancelTranscriptionsSelection() {
    toggleTranscriptionsManagement();
}

// duplicate handling functions
function showDuplicateModal(filename, uploadData) {
    pendingDuplicateData = uploadData;
    
    document.getElementById('duplicate-filename').textContent = filename;
    document.getElementById('duplicate-modal').style.display = 'block';
    
    // set up overwrite button event
    document.getElementById('duplicate-overwrite').onclick = () => {
        closeDuplicateModal();
        // proceed with upload/processing with overwrite flag
        if (pendingDuplicateData.type === 'file') {
            proceedWithFileUpload(pendingDuplicateData.file, true);
        } else if (pendingDuplicateData.type === 'url') {
            proceedWithUrlUpload(pendingDuplicateData.url, true);
        }
    };
}

function closeDuplicateModal() {
    document.getElementById('duplicate-modal').style.display = 'none';
    pendingDuplicateData = null;
}

async function proceedWithFileUpload(file, overwrite = false) {
    // implementation for file upload with overwrite support
    // this would need backend support for overwrite flag
    uploadFile(file);
}

async function proceedWithUrlUpload(url, overwrite = false) {
    // implementation for url upload with overwrite support  
    // this would need backend support for overwrite flag
    addUrl();
}

// resolve duplicate function
async function resolveDuplicate(itemId, action) {
    try {
        console.log(`resolveDuplicate called: itemId=${itemId}, action=${action}`);
        updateStatus(`resolving duplicate: ${action}...`);
        
        const response = await fetch(`/api/queue/resolve-duplicate/${itemId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: action })
        });
        
        console.log(`API response status: ${response.status}`);
        const result = await response.json();
        console.log('API response data:', result);
        
        if (result.success) {
            updateStatus(result.message);
            refreshStatus(); // refresh to update the queue display
        } else {
            updateStatus(`failed: ${result.error}`);
        }
    } catch (error) {
        console.error('resolveDuplicate error:', error);
        updateStatus(`error: ${error.message}`);
    }
}

// close duplicate modal when clicking outside
window.addEventListener('click', function(event) {
    const duplicateModal = document.getElementById('duplicate-modal');
    if (event.target === duplicateModal) {
        closeDuplicateModal();
    }
});

// cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
});
