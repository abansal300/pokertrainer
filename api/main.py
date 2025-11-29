import os
import json
import uuid
import re

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from redis import Redis

import psycopg2

import hashlib

DB_HOST = os.getenv('DB_ADDR', 'localhost:5432').split(':')[0]
DB_NAME = 'poker_stats'
DB_USER = 'user'
DB_PASSWORD = 'password'

# 1. Configuration
REDIS_ADDR = os.getenv("REDIS_ADDR", "localhost:6379")
QUEUE_NAME = "analysis_jobs"

app = Flask(__name__)
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", message_queue=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

rdb = None

def initialize_redis():
    # Connects to redis
    global rdb
    try:
        # Check for the secure URL first (Render provides this)
        redis_url = os.getenv('REDIS_URL')
        
        if redis_url:
            rdb = Redis.from_url(redis_url, decode_responses=True)
        else:
            # Fallback to local Docker logic
            redis_host = os.getenv('REDIS_ADDR', 'localhost:6379').split(':')[0]
            rdb = Redis(host=redis_host, port=6379, decode_responses=True)
            
        rdb.ping()
        print("SUCCESS: Connected to Redis Queue.")
    except Exception as e:
        print(f"FATAL: Could not connect to Redis: {e}")

with app.app_context():
    initialize_redis()

def create_cache_key(hero_hand_strs: list, board_strs: list) -> str:
    """Creates a unique, deterministic key for the hand combination."""
    # 1. Combine all cards
    all_cards = hero_hand_strs + board_strs
    # 2. Sort them alphabetically (Canonical form)
    all_cards.sort()
    # 3. Create a clean, unique string
    key_string = ":".join(all_cards)
    # 4. Hash the string to create a compact key
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()
        
        # Select all hands, ordered by when they were processed
        cursor.execute("""
            SELECT hand_id, hero_hand, board, equity, 
                   TO_CHAR(processed_at, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS processed_at 
            FROM hands_analysis ORDER BY processed_at DESC
        """)
        
        # Get column names for building the JSON response
        columns = [desc[0] for desc in cursor.description]
        
        # Convert all results to a list of dictionaries
        history = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()

        for item in history:
            item['equity'] = float(item['equity'])

        return jsonify({"status": "success", "history": history}), 200

    except Exception as e:
        print(f"API ERROR: Database query failed: {e}")
        return jsonify({"error": f"Database query failed: {e}"}), 500

# 2. Status Check Endpoint
@app.route("/", methods = ["GET"])
def status_check():
    return jsonify({"status": "ok", "service": "API Gateaway", "queue": QUEUE_NAME})

# 3. Main Ingestion Endpoint
@app.route('/api/upload', methods=['POST'])
def upload_handler():
    # ... (Keep existing validation logic) ...
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    uploaded_file = request.files['file']
    if uploaded_file.filename == '': return jsonify({"error": "Empty filename"}), 400
    raw_content = uploaded_file.read().decode('utf-8')
    job_payloads = parse_hand_history(raw_content)
    if not job_payloads: return jsonify({"error": "No hands found"}), 400
    
    pushed_count = 0
    job_ids = [] # <--- NEW: Track generated IDs
    
    try:
        pipe = rdb.pipeline()
        for payload in job_payloads:
            job_id = str(uuid.uuid4())
            payload["job_id"] = job_id
            
            job_ids.append(job_id) # <--- NEW: Add to list
            
            pipe.lpush(QUEUE_NAME, json.dumps(payload))
            pushed_count += 1
        
        pipe.execute()
        
        return jsonify({
            "status": "Accepted",
            "total_jobs": pushed_count,
            "job_ids": job_ids, # <--- NEW: Return this list to Frontend
            "message": "Jobs queued."
        }), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/results/<job_id>', methods=['GET'])
def result_handler(job_id):
    # Check Redis for the result stored by the Worker
    result_key = f"result:{job_id}"
    data = rdb.get(result_key)
    
    if not data:
        # If no data exists yet, the worker is still thinking
        return jsonify({"status": "pending"}), 202
    
    # If data exists, return it
    return jsonify({"status": "completed", "data": json.loads(data)}), 200

if __name__ == "__main__":
    import eventlet
    eventlet.monkey_patch()

    print("Starting SocketIO server...")
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)

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
    

