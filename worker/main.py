import random
import collections
import json
import os
import time
import psycopg2 
from redis import Redis
import socketio

# --- 1. CONFIGURATION AND SETUP ---

# Standard card ranks (2 through 14 for Ace)
CARD_RANKS_MAP = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

# Global Database Credentials (Used by get_db_connection)
DB_HOST = os.getenv('DB_ADDR', 'localhost:5432').split(':')[0]
DB_NAME = 'poker_stats'
DB_USER = 'user'
DB_PASSWORD = 'password'
QUEUE_NAME = 'analysis_jobs'

rdb = None

API_SOCKET_URL = os.environ.get('API_SOCKET_URL', 'http://poker_api:8080')

# Initialize SocketIO Client
sio_client = socketio.Client(reconnection=True)
API_SOCKET_URL = os.environ.get('API_SOCKET_URL', 'http://poker_api:8080')
MAX_SOCKIO_RETRIES = 10

for i in range(MAX_SOCKIO_RETRIES):
    try:
        # Use transports for reliability in mixed environments
        sio_client.connect(API_SOCKET_URL, transports=['websocket', 'polling']) 
        print("WORKER: SocketIO client successfully connected to API.")
        break  # Exit loop on success
    except Exception as e:
        print(f"WORKER WARNING: SocketIO connection failed (Attempt {i+1}/{MAX_SOCKIO_RETRIES}). Retrying in 2s...")
        time.sleep(2)
else:
    # If the loop completes without connecting, the service is unusable
    print("WORKER FATAL: Could not establish stable SocketIO connection after all attempts.")

# CRITICAL: Global function for resilient database connections
def get_db_connection():
    """Returns a new PostgreSQL connection."""
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)


def setup_database():
    """Connects to Redis and implements retry logic to wait for Postgres startup."""
    global rdb
    MAX_RETRIES = 5
    RETRY_DELAY = 5 
    
    try:
        redis_host = os.getenv('REDIS_ADDR', 'localhost:6379').split(':')[0]
        rdb = Redis(host=redis_host, port=6379, decode_responses=True)
        rdb.ping()
        print("WORKER: Connected to Redis Queue.")
    except Exception as e:
        print(f"WORKER FATAL: Could not connect to Redis: {e}")
        return

    # Retry loop for PostgreSQL connection (Fixes the race condition)
    for attempt in range(MAX_RETRIES):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hands_analysis (
                    job_id VARCHAR(36) PRIMARY KEY,
                    hand_id VARCHAR(50),
                    hero_hand TEXT,
                    board TEXT,
                    num_opponents INTEGER,
                    equity DECIMAL(5, 2),
                    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            cursor.close()
            conn.close()
            print("WORKER: Database table 'hands_analysis' is ready.")
            return
            
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"WORKER WARNING: Postgres connection failed (Attempt {attempt+1}/{MAX_RETRIES}). Waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"WORKER FATAL: Could not connect to or set up PostgreSQL after {MAX_RETRIES} attempts.")
                raise e


# --- 2. EVALUATION LOGIC (Hand Ranking) ---
# [Evaluation functions omitted for brevity, assumed correct]
def get_counts(seven_cards):
    ranks = [CARD_RANKS_MAP[rank] for rank, suit in seven_cards]
    ranks_copy = list(ranks)
    suits = [suit for rank, suit in seven_cards]
    rank_counts = collections.Counter(ranks_copy)
    suit_counts = collections.Counter(suits)
    return ranks_copy, rank_counts, suit_counts

def evaluate_seven_card_hand(seven_cards):
    ranks, rank_counts, suit_counts = get_counts(seven_cards)
    unique_ranks = sorted(list(set(ranks)), reverse=True)
    
    is_a_flush = False
    flush_suit = None
    for suit, count in suit_counts.items():
        if count >= 5:
            is_a_flush = True
            flush_suit = suit
            break
            
    flush_ranks = []
    if is_a_flush:
        flush_cards = sorted([CARD_RANKS_MAP[r] for r, s in seven_cards if s == flush_suit], reverse=True)
        flush_ranks = flush_cards[:5]

    straight_rank = 0
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] == unique_ranks[i+4] + 4:
            straight_rank = unique_ranks[i]
            break
    if not straight_rank and all(r in unique_ranks for r in [14, 5, 4, 3, 2]):
        straight_rank = 5

    if is_a_flush and straight_rank:
        if straight_rank == 14: return (9, 14)
        return (8, straight_rank)

    kind_counts = {c: [r for r, count in rank_counts.items() if count == c] for c in [4, 3, 2]}

    if kind_counts[4]:
        quad_rank = kind_counts[4][0]
        kicker = max(r for r in unique_ranks if r != quad_rank)
        return (7, quad_rank, kicker)

    if kind_counts[3] and (len(kind_counts[3]) > 1 or kind_counts[2]):
        trip_rank = kind_counts[3][0]
        pair_ranks = []
        if len(kind_counts[3]) > 1: pair_ranks = [kind_counts[3][1]]
        if kind_counts[2]: pair_ranks.extend(kind_counts[2])
        pair_rank = max(pair_ranks)
        return (6, trip_rank, pair_rank)

    if is_a_flush: return (5, *flush_ranks)

    if straight_rank: return (4, straight_rank)

    if kind_counts[3]:
        trip_rank = kind_counts[3][0]
        kickers = sorted([r for r in unique_ranks if r != trip_rank], reverse=True)[:2]
        return (3, trip_rank, *kickers)

    if kind_counts[2] and len(kind_counts[2]) >= 2:
        pair_ranks = sorted(kind_counts[2], reverse=True)[:2]
        kicker = max(r for r in unique_ranks if r not in pair_ranks)
        return (2, *pair_ranks, kicker)

    if kind_counts[2]:
        pair_rank = kind_counts[2][0]
        kickers = sorted([r for r in unique_ranks if r != pair_rank], reverse=True)[:3]
        return (1, pair_rank, *kickers)

    high_cards = sorted(unique_ranks, reverse=True)[:5]
    return (0, *high_cards)


# --- 3. MONTE CARLO SIMULATION ---
def simulate_equity(hero_hand, board, num_opponents, runs=10000):
    suits = ['s', 'h', 'd', 'c']
    ranks = list(CARD_RANKS_MAP.keys())
    full_deck = [(r, s) for r in ranks for s in suits]
    known_cards = hero_hand + board
    deck = [card for card in full_deck if card not in known_cards]
    hero_wins = 0

    remaining_board_count = 5 - len(board)
    total_unknowns = (num_opponents * 2) + remaining_board_count

    if total_unknowns > len(deck): return 0.0

    for _ in range(runs):
        unknown_cards = random.sample(deck, total_unknowns)
        
        opponent_hands = []
        for i in range(num_opponents):
            opponent_hands.append(unknown_cards[i * 2 : i * 2 + 2])
            
        board_remainder = unknown_cards[num_opponents * 2:]
        final_board = list(board) + list(board_remainder)

        hero_score = evaluate_seven_card_hand(list(hero_hand) + final_board)
        
        max_opponent_score = evaluate_seven_card_hand(list(opponent_hands[0]) + final_board)
        for opp_hand in opponent_hands[1:]:
            score = evaluate_seven_card_hand(list(opp_hand) + final_board)
            if score > max_opponent_score:
                max_opponent_score = score
        
        if hero_score > max_opponent_score:
            hero_wins += 1

    return (hero_wins / runs) * 100


# --- 4. WORKER LISTENER ---
def parse_card_string(card_str):
    if len(card_str) != 2: return None
    return (card_str[0], card_str[1])


def start_worker():
    print("WORKER: Listening for jobs...")

    time.sleep(5)

    while True:
        job = rdb.brpop(QUEUE_NAME, timeout=60)
        
        if job:
            _, payload_json = job
            conn = None
            try:
                # 1. Parse Data
                data = json.loads(payload_json)
                job_id = data.get('job_id')
                hand_id = data.get('hand_id', 'Unknown')
                
                print(f"WORKER: Processing Hand {hand_id}")

                hero_hand_strs = data.get('hero_hand', [])
                board_strs = data.get('board', [])
                hero_hand = [parse_card_string(c) for c in hero_hand_strs]
                board = [parse_card_string(c) for c in board_strs]
                num_opponents = data.get('num_opponents', 3)
                runs = data.get('runs', 10000)

                # 2. Run Simulation
                equity = simulate_equity(hero_hand, board, num_opponents, runs)
                
                # 3. Save to PostgreSQL
                conn = get_db_connection()
                cursor = conn.cursor()
                
                hero_hand_str = ','.join(hero_hand_strs) 
                board_str = ','.join(board_strs)

                cursor.execute("""
                    INSERT INTO hands_analysis (job_id, hand_id, hero_hand, board, num_opponents, equity)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_id) DO NOTHING;
                """, (job_id, hand_id, hero_hand_str, board_str, num_opponents, round(equity, 2)))
                
                conn.commit()
                cursor.close()
                conn.close()
                print(f"✅ SAVED TO POSTGRES: Hand {hand_id} Equity: {equity:.2f}%")

                # 4. Save to Redis
                result_payload = {
                    "hand_id": hand_id,
                    "equity": equity,
                    "hero_hand": hero_hand_strs, 
                    "board": board_strs
                }
                rdb.setex(f"result:{job_id}", 3600, json.dumps(result_payload))

                # 5. Conditional SocketIO Emit (Prevents Worker from crashing)
                if sio_client.connected:
                    sio_client.emit(
                        'job_complete', 
                        {'job_id': job_id, 'status': 'completed', 'data': result_payload}
                    )
                    print(f"📡 EMITTED: Job {job_id} result via SocketIO.")
                else:
                    print(f"⚠️ SKIPPED EMIT: SocketIO client is disconnected. Frontend will poll.")

            except Exception as e:
                print(f"WORKER ERROR: Failed to process job {job_id}: {e}")
                if conn: conn.close()

if __name__ == "__main__":
    setup_database() 
    start_worker()