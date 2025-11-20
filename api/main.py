import os
import json
import uuid
import re

from flask import Flask, request, jsonify
from flask_cors import CORS
from redis import Redis

# 1. Configuration
REDIS_ADDR = os.getenv("REDIS_ADDR", "localhost:6379")
QUEUE_NAME = "analysis_jobs"

app = Flask(__name__)
CORS(app)

rdb = None

def initialize_redis():
    # Connects to redis
    global rdb
    try:
        rdb = Redis(host='redis', port=6379, decode_responses=True)
        rdb.ping()
        print("SUCCESS: Connected to Redis")
    except Exception as e:
        print(f"FATAL: Could not connect to redis: {e}")

with app.app_context():
    initialize_redis()

# 2. Status Check Endpoint
@app.route("/", methods = ["GET"])
def status_check():
    return jsonify({"status": "ok", "service": "API Gateaway", "queue": QUEUE_NAME})

# 3. Main Ingestion Endpoint
@app.route('/api/upload', methods = ["POST"])
def upload_handler():
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    uploaded_file = request.files['file']

    if uploaded_file.filename == '':
        return jsonify({"error": "No file selected."}), 400

    raw_content = uploaded_file.read().decode('utf-8')

    # 1. parse the hands
    job_payloads = parse_hand_history(raw_content)

    if not job_payloads:
        return jsonify({"error": "No valid hands found in the file."}), 400
    
    # 2. enqueue the jobs
    pushed_count = 0

    try:
        pipe = rdb.pipeline()

        for payload in job_payloads:
            job_id = str(uuid.uuid4())
            payload['job_id'] = job_id

            pipe.lpush(QUEUE_NAME, json.dumps(payload))
            pushed_count += 1

        pipe.execute()

        return jsonify({
            "status": "Accepted for Processing",
            "total_hands_found": len(job_payloads),
            "total_jobs_queued": pushed_count,
            "message": "Jobs queued successfully. Processing in the background."
        }), 202
    except Exception as e:
        return jsonify({"error": f"Failed to queue jobs to Redis: {e}"}), 500
        


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

# 4. Parser Logic
def parse_hand_history(raw_content: str) -> list:
    """
    parses a single hand history log file containing multiple hands.
    """
    # Regex pattern to split the file into individual hands
    HAND_DELIMITER = r'(?=PokerStars Hand #\d+)'
    hand_blocks = re.split(HAND_DELIMITER, raw_content, flags=re.MULTILINE)[1:]
    
    jobs = []
    
    for block in hand_blocks:
        # Extract data using Regex
        hand_id_match = re.search(r"Hand #(\d+):", block)
        hole_cards_match = re.search(r"Dealt to Hero \[(.*?)\]", block)
        board_match = re.search(r"Board \[(.*?)\]", block)
        
        hand_id = hand_id_match.group(1) if hand_id_match else None
        hole_cards = hole_cards_match.group(1).split() if hole_cards_match else []
        board_cards = board_match.group(1).split() if board_match else []
        
        if hole_cards:
            job_payload = {
                "hand_id": hand_id,
                "hero_hand": hole_cards,
                "board": board_cards,
                "num_opponents": 3, 
                "runs": 10000 
            }
            jobs.append(job_payload)

    return jobs
    

