// main app initialization
import { CONFIG, APP_STATE } from './config.js';
import { UploadModule } from '../modules/upload.js';
import { QueueModule } from '../modules/queue.js';
import { TranscriptionsModule } from '../modules/transcriptions.js';
import { ModalModule } from '../modules/modal.js';
import { TabsModule } from '../modules/tabs.js';

// make modal module globally available to eliminate dynamic imports
window.ModalModule = ModalModule;

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
        
        // initialize completed count tracking
        this.initializeCompletedCountTracking();
        
        // start auto-refresh
        this.startAutoRefresh();
        
        // cleanup on page unload
        window.addEventListener('beforeunload', this.cleanup);
    }
    
    static initializeCompletedCountTracking() {
        // set initial completed count from the queue stats
        const currentStats = document.getElementById('queue-stats');
        if (currentStats) {
            const completedElement = Array.from(currentStats.querySelectorAll('.stat-item'))
                .find(item => item.querySelector('.stat-label')?.textContent === 'completed');
            if (completedElement) {
                APP_STATE.lastCompletedCount = parseInt(completedElement.querySelector('.stat-number')?.textContent || '0');
            }
        }
    }
    
    static startAutoRefresh() {
        this.scheduleNextRefresh();
        
        // pause polling when tab becomes hidden
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (APP_STATE.statusInterval) {
                    clearTimeout(APP_STATE.statusInterval);
                    APP_STATE.statusInterval = null;
                }
            } else {
                // resume polling when tab becomes visible
                if (!APP_STATE.statusInterval) {
                    this.scheduleNextRefresh();
                }
            }
        });
    }
    
    static scheduleNextRefresh() {
        if (APP_STATE.statusInterval) {
            clearTimeout(APP_STATE.statusInterval);
        }
        
        APP_STATE.statusInterval = setTimeout(async () => {
            if (APP_STATE.currentTab === 'queue') {
                // check if queue status changed in a way that might affect transcriptions
                const previousCompletedCount = APP_STATE.lastCompletedCount || 0;
                
                await QueueModule.refreshStatus();
                
                // if we're monitoring queue and completed count increased, refresh transcriptions
                const currentStats = document.getElementById('queue-stats');
                if (currentStats) {
                    const completedElement = Array.from(currentStats.querySelectorAll('.stat-item'))
                        .find(item => item.querySelector('.stat-label')?.textContent === 'completed');
                    if (completedElement) {
                        const currentCompletedCount = parseInt(completedElement.querySelector('.stat-number')?.textContent || '0');
                        if (currentCompletedCount > previousCompletedCount) {
                            // completed count increased - likely new transcriptions available
                            TranscriptionsModule.loadTranscriptions();
                        }
                        APP_STATE.lastCompletedCount = currentCompletedCount;
                    }
                }
            } else if (APP_STATE.currentTab === 'transcriptions') {
                TranscriptionsModule.loadTranscriptions();
            }
            
            // schedule next refresh with current interval
            this.scheduleNextRefresh();
        }, APP_STATE.currentInterval);
    }
    
    static cleanup = () => {
        if (APP_STATE.statusInterval) {
            clearTimeout(APP_STATE.statusInterval);
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
