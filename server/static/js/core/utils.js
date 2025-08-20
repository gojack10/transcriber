// shared utility functions
export function updateStatus(message) {
    document.getElementById('status-text').textContent = message;
}

export function getTimeAgo(date) {
    // get current time in browser's timezone
    const now = new Date();
    let targetDate;
    
    if (date instanceof Date) {
        targetDate = date;
    } else if (typeof date === 'string') {
        // server sends UTC timestamps - parse and convert to browser's local timezone
        targetDate = new Date(date);
    } else {
        return 'invalid date';
    }
    
    // check if date is valid
    if (isNaN(targetDate.getTime())) {
        return 'invalid date';
    }
    
    // both dates are now in browser's local timezone for comparison
    const diff = Math.floor((now - targetDate) / 1000);
    
    // handle future dates (allow small clock differences)
    if (diff < -30) {
        const absDiff = Math.abs(diff);
        if (absDiff < 60) return `in ${absDiff}s`;
        if (absDiff < 3600) return `in ${Math.floor(absDiff / 60)}m`;
        if (absDiff < 86400) return `in ${Math.floor(absDiff / 3600)}h`;
        return `in ${Math.floor(absDiff / 86400)}d`;
    }
    
    // handle small negative differences as "just now"
    if (diff < 0) return 'just now';
    
    if (diff < 60) return diff === 0 ? 'just now' : `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

export function generateId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
