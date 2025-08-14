// api communication layer
import { CONFIG } from '../core/config.js';

export class ApiService {
    static async get(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`http error! status: ${response.status}`);
        return response.json();
    }

    static async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            // try to get json error response for better error handling
            let errorData;
            try {
                errorData = await response.json();
            } catch {
                errorData = { error: `http error! status: ${response.status}` };
            }
            
            const error = new Error(errorData.error || `http error! status: ${response.status}`);
            error.status = response.status;
            error.response = errorData;
            throw error;
        }
        
        return response.json();
    }

    static async delete(url, data = null) {
        const options = { method: 'DELETE' };
        if (data) {
            options.headers = { 'Content-Type': 'application/json' };
            options.body = JSON.stringify(data);
        }
        const response = await fetch(url, options);
        if (!response.ok) throw new Error(`http error! status: ${response.status}`);
        return response.json();
    }

    static async uploadFile(file, onProgress) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);
            
            const xhr = new XMLHttpRequest();
            
            if (onProgress) {
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = (e.loaded / e.total) * 100;
                        onProgress(percentComplete);
                    }
                });
            }
            
            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    reject(new Error(`upload failed: ${xhr.status}`));
                }
            });
            
            xhr.addEventListener('error', () => {
                reject(new Error('network error'));
            });
            
            xhr.open('POST', CONFIG.API_ENDPOINTS.QUEUE_FILE);
            xhr.send(formData);
        });
    }
}
