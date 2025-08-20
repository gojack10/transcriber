// shared utility functions
export function updateStatus(message) {
    document.getElementById('status-text').textContent = message;
}

export function getTimeAgo(date) {
    const now = new Date();
    // ensure date is a valid Date object
    let targetDate;
    
    if (date instanceof Date) {
        targetDate = date;
    } else if (typeof date === 'string') {
        // handle ISO date strings with timezone info
        targetDate = new Date(date);
        
        // if the date string doesn't include timezone info and looks like UTC, ensure it's treated as UTC
        if (!date.includes('+') && !date.includes('Z') && date.includes('T')) {
            // assume UTC if no timezone specified
            targetDate = new Date(date + 'Z');
        }
    } else {
        return 'invalid date';
    }
    
    // check if date is valid
    if (isNaN(targetDate.getTime())) {
        console.error('Invalid date:', date);
        return 'invalid date';
    }
    
    const diff = Math.floor((now - targetDate) / 1000);
    
    // handle negative differences (future dates)
    if (diff < 0) {
        console.warn('Future date detected:', date, 'diff:', diff);
        const absDiff = Math.abs(diff);
        if (absDiff < 60) return `in ${absDiff}s`;
        if (absDiff < 3600) return `in ${Math.floor(absDiff / 60)}m`;
        if (absDiff < 86400) return `in ${Math.floor(absDiff / 3600)}h`;
        return `in ${Math.floor(absDiff / 86400)}d`;
    }
    
    if (diff < 60) return `${diff}s ago`;
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
