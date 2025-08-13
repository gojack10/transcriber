// transcription automation frontend javascript

let statusInterval;
let currentTab = 'queue';

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
    for (const file of files) {
        await uploadFile(file);
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        updateStatus(`uploading ${file.name}...`);
        
        const response = await fetch('/api/queue/file', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateStatus(`${file.name} uploaded successfully`);
            refreshStatus();
        } else {
            updateStatus(`upload failed: ${result.error}`);
        }
    } catch (error) {
        updateStatus(`upload error: ${error.message}`);
    }
}

async function addUrl() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    
    if (!url) {
        updateStatus('please enter a url');
        return;
    }
    
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
        
        if (result.success) {
            updateStatus(`url added to queue successfully`);
            urlInput.value = '';
            refreshStatus();
        } else {
            updateStatus(`failed to add url: ${result.error}`);
        }
    } catch (error) {
        updateStatus(`error adding url: ${error.message}`);
    }
}

async function refreshStatus() {
    try {
        const [statusResponse, itemsResponse] = await Promise.all([
            fetch('/api/queue/status'),
            fetch('/api/queue/items')
        ]);
        
        const statusData = await statusResponse.json();
        const itemsData = await itemsResponse.json();
        
        updateQueueStats(statusData);
        updateQueueItems(itemsData.items);
        
        updateStatus(`queue: ${statusData.total_items} items`);
        
    } catch (error) {
        updateStatus(`error refreshing: ${error.message}`);
    }
}

function updateQueueStats(statusData) {
    const statsContainer = document.getElementById('queue-stats');
    
    const stats = [
        { label: 'total', value: statusData.total_items },
        { label: 'queued', value: statusData.status_counts.queued || 0 },
        { label: 'downloading', value: statusData.status_counts.downloading || 0 },
        { label: 'converting', value: statusData.status_counts.converting || 0 },
        { label: 'transcribing', value: statusData.status_counts.transcribing || 0 },
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
        
        let buttonText = 'remove';
        let buttonClass = 'delete-btn';
        
        if (activeStates.includes(item.status)) {
            buttonText = 'cancel';
            buttonClass = 'cancel-btn';
        } else if (finishedStates.includes(item.status)) {
            buttonText = 'remove';
            buttonClass = 'delete-btn';
        }
        
        return `
            <div class="queue-item">
                <div class="item-info">
                    <div class="item-name">${fileName}</div>
                    <div class="item-details">
                        ${item.url ? `url: ${item.url}` : `path: ${item.file_path}`}<br>
                        updated: ${timeAgo}
                        ${item.error_message ? `<br>error: ${item.error_message}` : ''}
                    </div>
                </div>
                <div class="item-status status-${item.status}">${item.status}</div>
                <div class="item-actions">
                    <button class="${buttonClass}" onclick="removeItem('${item.id}')">${buttonText}</button>
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
    
    if (!transcriptions || transcriptions.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: var(--fg2); padding: 20px;">no transcriptions available</div>';
        return;
    }
    
    container.innerHTML = transcriptions.map(item => `
        <div class="transcription-item">
            <div class="transcription-info">
                <div class="transcription-id">${item.id}</div>
                <div class="transcription-filename">${item.filename}</div>
                <div class="transcription-time">${item.transcribed_time}</div>
            </div>
            <div class="transcription-actions">
                <button class="view-btn" onclick="viewTranscription(${item.id}, '${item.filename}')">view</button>
            </div>
        </div>
    `).join('');
}

async function viewTranscription(id, filename) {
    try {
        const response = await fetch(`/api/transcriptions/${id}`);
        const data = await response.json();
        
        if (data.content) {
            document.getElementById('modal-title').textContent = filename;
            document.getElementById('modal-content').textContent = data.content;
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

// close modal when clicking outside
window.addEventListener('click', function(event) {
    const modal = document.getElementById('transcription-modal');
    if (event.target === modal) {
        closeModal();
    }
});

// cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
});
