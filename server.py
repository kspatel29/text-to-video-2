import os
import uuid
import subprocess
import threading
import time
import json
import sys
import argparse
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from datetime import datetime
import shlex

app = Flask(__name__)
CORS(app)

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

# Helper function to watch and print stream output
def stream_watcher(identifier, stream, output_list):
    """Reads a stream line by line, prints it, and stores it."""
    try:
        for line_bytes in iter(stream.readline, b''):
            line = line_bytes.decode('utf-8', errors='replace')
            print(f"[{identifier}] {line}", end='', flush=True)
            output_list.append(line)
    except Exception as e:
        print(f"Error in stream_watcher for {identifier}: {e}")
    finally:
        if hasattr(stream, 'close'):
            stream.close()

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

        escaped_input = shlex.quote(input_text)
        
        # Build the command to run in the virtual environment
        cmd = f"source venv/bin/activate && python main.py {escaped_input}"

        # Execute the command
        process = subprocess.Popen(
            cmd,
            shell=True,
            executable='/bin/bash',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout_lines = []
        stderr_lines = []

        stdout_thread = None
        stderr_thread = None

        if process.stdout:
            stdout_thread = threading.Thread(
                target=stream_watcher,
                args=(f"main.py stdout - {request_id}", process.stdout, stdout_lines)
            )
            stdout_thread.daemon = True # Daemon threads will exit when the main program exits
            stdout_thread.start()

        if process.stderr:
            stderr_thread = threading.Thread(
                target=stream_watcher,
                args=(f"main.py stderr - {request_id}", process.stderr, stderr_lines)
            )
            stderr_thread.daemon = True
            stderr_thread.start()

        # Wait for stream watchers to finish
        if stdout_thread:
            stdout_thread.join()
        if stderr_thread:
            stderr_thread.join()
        
        # Wait for the process to terminate and get the return code
        return_code = process.wait()

        final_stdout = "".join(stdout_lines)
        final_stderr = "".join(stderr_lines)

        # Check if process completed successfully
        if return_code == 0:
            # Update the request status
            requests_data = load_requests()
            requests_data[request_id]['status'] = 'completed'
            requests_data[request_id]['output_path'] = 'final_lesson.mp4'
            requests_data[request_id]['end_time'] = datetime.now().isoformat()
            requests_data[request_id]['logs'] = final_stdout
            save_requests(requests_data)
        else:
            # Update with error information
            error_output = final_stderr
            requests_data = load_requests()
            requests_data[request_id]['status'] = 'failed'
            requests_data[request_id]['error'] = error_output
            requests_data[request_id]['end_time'] = datetime.now().isoformat()
            requests_data[request_id]['logs'] = final_stdout # Store stdout even on failure
            save_requests(requests_data)

    except Exception as e:
        # Handle any unexpected exceptions
        print(f"Error in generate_video for {request_id}: {e}") # Also print server-side error
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


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Azure App Service
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'text-to-video-flask'
    }), 200


if __name__ == '__main__':
    # Parse command line arguments for Azure compatibility
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    args = parser.parse_args()
    
    # Get port from command line, environment variable, or default
    port = args.port or int(os.environ.get('WEBSITES_PORT', 5000))
    
    print(f"Starting Flask server on port {port}")
    print("Flask Video Generation API is ready!")
    
    # Run the Flask app without SSL (Azure handles SSL termination)
    app.run(host='0.0.0.0', port=port, debug=False)
