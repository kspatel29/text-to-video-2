import os
import uuid
import subprocess
import threading
import time
import json
from flask import Flask, request, jsonify, send_file, abort
from datetime import datetime

app = Flask(__name__)

# Storage for tracking video generation requests
REQUESTS_FILE = 'video_requests.json'

# Initialize or load the requests storage
def load_requests():
    if os.path.exists(REQUESTS_FILE):
        try:
            with open(REQUESTS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_requests(requests_data):
    with open(REQUESTS_FILE, 'w') as f:
        json.dump(requests_data, f, indent=2)

# Initialize storage
requests_storage = load_requests()

def generate_video(request_id, input_text):
    """
    Background function to handle video generation process
    """
    try:
        # Update request status to processing
        requests_data = load_requests()
        requests_data[request_id]['status'] = 'processing'
        requests_data[request_id]['start_time'] = datetime.now().isoformat()
        save_requests(requests_data)
        
        # Build the command to run in the virtual environment
        cmd = f"source venv/bin/activate && python main.py '{input_text}'"
        
        # Execute the command
        process = subprocess.Popen(
            cmd, 
            shell=True, 
            executable='/bin/bash',
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = process.communicate()
        
        # Check if process completed successfully
        if process.returncode == 0:
            # Update the request status
            requests_data = load_requests()
            requests_data[request_id]['status'] = 'completed'
            requests_data[request_id]['output_path'] = 'final_lesson.mp4'
            requests_data[request_id]['end_time'] = datetime.now().isoformat()
            requests_data[request_id]['logs'] = stdout.decode('utf-8')
            save_requests(requests_data)
        else:
            # Update with error information
            error_output = stderr.decode('utf-8')
            requests_data = load_requests()
            requests_data[request_id]['status'] = 'failed'
            requests_data[request_id]['error'] = error_output
            requests_data[request_id]['end_time'] = datetime.now().isoformat()
            requests_data[request_id]['logs'] = stdout.decode('utf-8')
            save_requests(requests_data)
            
    except Exception as e:
        # Handle any unexpected exceptions
        requests_data = load_requests()
        requests_data[request_id]['status'] = 'failed'
        requests_data[request_id]['error'] = str(e)
        requests_data[request_id]['end_time'] = datetime.now().isoformat()
        save_requests(requests_data)


@app.route('/generate-video', methods=['POST'])
def start_video_generation():
    """
    Endpoint to start the video generation process asynchronously
    """
    # Get the input text from the request
    data = request.json
    if not data or 'text' not in data:
        return jsonify({'error': 'Missing required parameter: text'}), 400
    
    input_text = data['text']
    
    # Generate a unique request ID
    request_id = str(uuid.uuid4())
    
    # Initialize request data
    requests_data = load_requests()
    requests_data[request_id] = {
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'input_text': input_text
    }
    save_requests(requests_data)
    
    # Start video generation in a background thread
    thread = threading.Thread(
        target=generate_video,
        args=(request_id, input_text)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'request_id': request_id,
        'status': 'queued',
        'message': 'Video generation started'
    })


@app.route('/video-status/<request_id>', methods=['GET'])
def check_video_status(request_id):
    """
    Endpoint to check the status of a video generation request
    """
    requests_data = load_requests()
    if request_id not in requests_data:
        return jsonify({'error': 'Request ID not found'}), 404
    
    request_data = requests_data[request_id]
    response = {
        'request_id': request_id,
        'status': request_data['status'],
        'created_at': request_data['created_at']
    }
    
    # Add additional information based on status
    if request_data['status'] == 'completed':
        response['end_time'] = request_data.get('end_time')
    elif request_data['status'] == 'failed':
        response['error'] = request_data.get('error')
        response['end_time'] = request_data.get('end_time')
    elif request_data['status'] == 'processing':
        response['start_time'] = request_data.get('start_time')
    
    return jsonify(response)


@app.route('/download-video/<request_id>', methods=['GET'])
def download_video(request_id):
    """
    Endpoint to download a completed video
    """
    requests_data = load_requests()
    if request_id not in requests_data:
        return jsonify({'error': 'Request ID not found'}), 404
    
    request_data = requests_data[request_id]
    
    if request_data['status'] != 'completed':
        return jsonify({
            'error': 'Video is not ready for download',
            'status': request_data['status']
        }), 400
    
    video_path = request_data.get('output_path')
    if not video_path or not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found'}), 404
    
    return send_file(
        video_path,
        mimetype='video/mp4',
        as_attachment=True,
        download_name=f'video_{request_id}.mp4'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
