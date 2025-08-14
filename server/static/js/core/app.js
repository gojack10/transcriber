// main app initialization
import { CONFIG, APP_STATE } from './config.js';
import { UploadModule } from '../modules/upload.js';
import { QueueModule } from '../modules/queue.js';
import { TranscriptionsModule } from '../modules/transcriptions.js';
import { ModalModule } from '../modules/modal.js';
import { TabsModule } from '../modules/tabs.js';

class App {
    static async init() {
        // initialize all modules
        UploadModule.init();
        QueueModule.init();
        TranscriptionsModule.init();
        ModalModule.init();
        TabsModule.init();
        
        // load initial data
        await QueueModule.refreshStatus();
        await TranscriptionsModule.loadTranscriptions();
        
        // start auto-refresh
        this.startAutoRefresh();
        
        // cleanup on page unload
        window.addEventListener('beforeunload', this.cleanup);
    }
    
    static startAutoRefresh() {
        APP_STATE.statusInterval = setInterval(() => {
            if (APP_STATE.currentTab === 'queue') {
                QueueModule.refreshStatus();
            }
        }, CONFIG.REFRESH_INTERVAL);
    }
    
    static cleanup = () => {
        if (APP_STATE.statusInterval) {
            clearInterval(APP_STATE.statusInterval);
        }
    }
}

// initialize app when dom loads
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// expose modules globally for onclick handlers in html
window.UploadModule = UploadModule;
window.QueueModule = QueueModule;
window.TranscriptionsModule = TranscriptionsModule;
window.ModalModule = ModalModule;
window.TabsModule = TabsModule;
