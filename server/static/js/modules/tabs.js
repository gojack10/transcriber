// tab switching functionality
import { APP_STATE } from '../core/config.js';

export class TabsModule {
    static init() {
        // bind click events to tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.target.textContent.includes('queue') ? 'queue' : 'transcriptions';
                this.switchTab(tabName);
            });
        });
    }

    static switchTab(tabName) {
        APP_STATE.currentTab = tabName;
        
        // update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        const activeBtn = tabName === 'queue' 
            ? document.querySelector('.tab-btn:first-child')
            : document.querySelector('.tab-btn:last-child');
        activeBtn.classList.add('active');
        
        // update tab content
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        document.getElementById(`${tabName}-tab`).classList.add('active');
        
        // load data for active tab
        this.loadTabData(tabName);
    }

    static async loadTabData(tabName) {
        if (tabName === 'transcriptions') {
            const { TranscriptionsModule } = await import('./transcriptions.js');
            TranscriptionsModule.loadTranscriptions();
        } else if (tabName === 'queue') {
            const { QueueModule } = await import('./queue.js');
            QueueModule.refreshStatus();
        }
    }
}
