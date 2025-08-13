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
from wrappers.db.db_manager import TranscriptionDB

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 
app.config['UPLOAD_FOLDER'] = '/home/jack/llm/transcription/.temp'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = TranscriptionDB()

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
    """cancel active items or remove finished items from queue"""
    try:
        item = conversion_queue.get_item(item_id)
        if not item:
            return jsonify({'error': 'item not found'}), 404
        
        # check if item can be cancelled (active processing)
        if conversion_queue.can_cancel_item(item_id):
            item.update_status(QueueStatus.CANCELLED, "cancelled by user")
            return jsonify({
                'success': True,
                'action': 'cancelled',
                'message': f'item {item_id} cancelled'
            })
        
        elif conversion_queue.can_remove_item(item_id):
            conversion_queue.remove_item(item_id)
            return jsonify({
                'success': True,
                'action': 'removed', 
                'message': f'item {item_id} removed from queue'
            })
        
        else:
            return jsonify({
                'error': f'item cannot be cancelled or removed (status: {item.status.value})'
            }), 400
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/items', methods=['DELETE'])
def remove_queue_items():
    """cancel or remove multiple queue items"""
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'error': 'ids field required'}), 400
        
        ids = data['ids']
        if not isinstance(ids, list) or not ids:
            return jsonify({'error': 'ids must be a non-empty list'}), 400
        
        result = conversion_queue.remove_items(ids)
        
        total_processed = result['removed'] + result['cancelled']
        message_parts = []
        
        if result['removed'] > 0:
            message_parts.append(f"{result['removed']} removed")
        if result['cancelled'] > 0:
            message_parts.append(f"{result['cancelled']} cancelled")
        if result['not_found'] > 0:
            message_parts.append(f"{result['not_found']} not found")
        if result['cannot_remove'] > 0:
            message_parts.append(f"{result['cannot_remove']} cannot be removed")
        
        message = f"processed {total_processed} items: " + ", ".join(message_parts)
        
        return jsonify({
            'success': True,
            'result': result,
            'message': message
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions', methods=['GET'])
def get_transcriptions():
    try:
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'desc')
        
        transcriptions = db.get_all_transcriptions(sort_by, sort_order)
        
        return jsonify({
            'transcriptions': transcriptions,
            'total_count': len(transcriptions)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions/<int:transcription_id>', methods=['GET'])
def get_transcription_content(transcription_id):
    try:
        with db.get_connection() as conn:
            cursor = conn.execute("""
            SELECT filename, content FROM transcriptions WHERE id = ?;""", (transcription_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'transcription not found'}), 404
                
            return jsonify({
                'filename': row[0],
                'content': row[1]
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions/<int:transcription_id>', methods=['DELETE'])
def delete_transcription(transcription_id):
    """delete a single transcription by id"""
    try:
        success = db.delete_transcription(transcription_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'transcription {transcription_id} deleted successfully'
            })
        else:
            return jsonify({'error': 'transcription not found or could not be deleted'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions', methods=['DELETE'])
def delete_transcriptions():
    """delete multiple transcriptions by ids"""
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'error': 'ids field required'}), 400
        
        ids = data['ids']
        if not isinstance(ids, list) or not ids:
            return jsonify({'error': 'ids must be a non-empty list'}), 400
        
        try:
            ids = [int(id) for id in ids]
        except (ValueError, TypeError):
            return jsonify({'error': 'all ids must be integers'}), 400
        
        deleted_count = db.delete_transcriptions(ids)
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'deleted {deleted_count} transcriptions'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions/check-duplicate', methods=['POST'])
def check_duplicate_transcription():
    """check if a transcription filename already exists"""
    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'error': 'filename field required'}), 400
        
        filename = data['filename']
        exists = db.transcription_exists(filename)
        
        return jsonify({
            'exists': exists,
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/duplicates', methods=['GET'])
def get_pending_duplicates():
    """get all queue items with pending duplicate status"""
    try:
        items = conversion_queue.get_all_items_by_status(QueueStatus.PENDING_DUPLICATE)
        
        items_data = []
        for item in items:
            items_data.append({
                'id': item.id,
                'file_path': item.file_path,
                'url': getattr(item, 'url', None),
                'status': item.status.value,
                'created_at': item.created_at.isoformat(),
                'updated_at': item.updated_at.isoformat(),
                'error_message': item.error_message,
                'pending_filename': item.pending_transcription['filename'] if item.pending_transcription else None
            })
        
        return jsonify({
            'items': items_data,
            'total_count': len(items_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/resolve-duplicate/<item_id>', methods=['POST'])
def resolve_duplicate(item_id):
    """resolve a duplicate by either overwriting or cancelling"""
    try:
        print(f"resolve_duplicate called: item_id={item_id}")
        data = request.get_json()
        print(f"request data: {data}")
        
        if not data or 'action' not in data:
            return jsonify({'error': 'action field required (overwrite/cancel)'}), 400
        
        action = data['action']
        print(f"action: {action}")
        
        if action not in ['overwrite', 'cancel']:
            return jsonify({'error': 'action must be overwrite or cancel'}), 400
        
        item = conversion_queue.get_item(item_id)
        print(f"item found: {item}")
        
        if not item:
            return jsonify({'error': 'item not found'}), 404
        
        print(f"item status: {item.status}")
        if item.status != QueueStatus.PENDING_DUPLICATE:
            return jsonify({'error': 'item is not pending duplicate resolution'}), 400
        
        print(f"pending transcription: {item.pending_transcription}")
        if not item.pending_transcription:
            return jsonify({'error': 'no pending transcription data found'}), 400
        
        if action == 'cancel':
            item.update_status(QueueStatus.CANCELLED, "duplicate cancelled by user")
            item.pending_transcription = None
            return jsonify({
                'success': True,
                'message': 'duplicate cancelled'
            })
        
        elif action == 'overwrite':
            filename = item.pending_transcription['filename']
            
            existing_transcriptions = db.get_all_transcriptions()
            existing_id = None
            for t in existing_transcriptions:
                if t['filename'] == filename:
                    existing_id = t['id']
                    break
            
            if existing_id:
                db.delete_transcription(existing_id)
            
            if not item.pending_transcription.get('content'):
                item.update_status(QueueStatus.CONVERTED)
                item.pending_transcription = None
                
                return jsonify({
                    'success': True,
                    'message': f'existing transcription deleted, item queued for transcription: {filename}'
                })
            else:
                content = item.pending_transcription['content']
                header = item.pending_transcription['header']
                
                from pathlib import Path
                temp_dir = Path('/home/jack/llm/transcription/.temp')
                output_path = temp_dir / filename
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(header)
                    f.write(content)
                
                db.add_transcription(filename, content, item.id)
                item.update_status(QueueStatus.COMPLETED)
                item.pending_transcription = None
                
                return jsonify({
                    'success': True,
                    'message': f'overwrite completed for {filename}'
                })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_server(host='localhost', port=8080, debug=False):
    """start the flask server"""
    print(f"starting transcription api server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == '__main__':
    run_server(debug=True)
