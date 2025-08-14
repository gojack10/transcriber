// app configuration and constants
export const CONFIG = {
    REFRESH_INTERVAL: 2000,
    PROGRESS_HIDE_DELAY: 8000,
    UPLOAD_SUCCESS_DISPLAY_TIME: 5000,
    API_ENDPOINTS: {
        QUEUE_STATUS: '/api/queue/status',
        QUEUE_ITEMS: '/api/queue/items',
        QUEUE_FILE: '/api/queue/file',
        QUEUE_LINK: '/api/queue/link',
        TRANSCRIPTIONS: '/api/transcriptions',
        RESOLVE_DUPLICATE: '/api/queue/resolve-duplicate'
    },
    SUPPORTED_FILE_TYPES: ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.mp3', '.wav', '.ogg', '.m4a']
};

export const APP_STATE = {
    statusInterval: null,
    currentTab: 'queue',
    queueManagementMode: false,
    transcriptionsManagementMode: false,
    selectedQueueItems: new Set(),
    selectedTranscriptions: new Set(),
    pendingDuplicateData: null
};
