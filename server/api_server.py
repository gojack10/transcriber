from flask import Flask, request, jsonify, send_from_directory
from flask.helpers import make_response
import os
import threading
from pathlib import Path
import tempfile
from werkzeug.utils import secure_filename
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wrappers.media_manager import conversion_queue, download_audio, convert_to_audio
from wrappers.queue_manager import QueueStatus

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
app.config['UPLOAD_FOLDER'] = '/home/jack/llm/transcription/.temp'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'ogg', 'm4a'}

def allowed_file(filename):
    """check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.after_request
def after_request(response):
    """add cors headers to all responses"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    """serve the main web interface"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/style.css')
def styles():
    """serve css file"""
    return send_from_directory(app.static_folder, 'style.css')

@app.route('/app.js')
def scripts():
    """serve javascript file"""
    return send_from_directory(app.static_folder, 'app.js')

@app.route('/api/queue/link', methods=['POST'])
def add_link_to_queue():
    """add youtube/yt-dlp supported url to download queue"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'url field required'}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({'error': 'url cannot be empty'}), 400
        
        def download_task():
            try:
                download_audio(url)
            except Exception as e:
                print(f"download error for {url}: {e}")
        
        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'download started for {url}',
            'url': url
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/file', methods=['POST'])
def upload_file_to_queue():
    """upload file and add to conversion queue"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'no file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'no file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': f'file type not allowed. allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        def convert_task():
            try:
                convert_to_audio(file_path)
            except Exception as e:
                print(f"conversion error for {file_path}: {e}")
        
        thread = threading.Thread(target=convert_task, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'file uploaded and conversion started',
            'filename': filename,
            'file_path': file_path
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    """get current queue status with counts by status"""
    try:
        counts = conversion_queue.get_queue_counts()
        total_items = sum(counts.values())
        
        return jsonify({
            'total_items': total_items,
            'status_counts': counts,
            'queue_active': total_items > 0
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/items', methods=['GET'])
def get_queue_items():
    """get all queue items with details"""
    try:
        items = conversion_queue.get_all_items()
        
        items_data = []
        for item in items:
            items_data.append({
                'id': item.id,
                'file_path': item.file_path,
                'url': getattr(item, 'url', None),
                'status': item.status.value,
                'created_at': item.created_at.isoformat(),
                'updated_at': item.updated_at.isoformat(),
                'error_message': item.error_message
            })
        
        return jsonify({
            'items': items_data,
            'total_count': len(items_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/item/<item_id>', methods=['DELETE'])
def remove_queue_item(item_id):
    """remove item from queue (note: this is basic - doesn't stop active processing)"""
    try:
        item = conversion_queue.get_item(item_id)
        if not item:
            return jsonify({'error': 'item not found'}), 404
        
        # basic removal - just mark as cancelled
        # note: for production would need more sophisticated cancellation
        item.update_status(QueueStatus.FAILED, "cancelled by user")
        
        return jsonify({
            'success': True,
            'message': f'item {item_id} marked as cancelled'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_server(host='localhost', port=8080, debug=False):
    """start the flask server"""
    print(f"starting transcription api server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == '__main__':
    run_server(debug=True)
