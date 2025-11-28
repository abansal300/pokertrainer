import random
import collections
import json
import os
from redis import Redis

# --- 1. CARD MAP & HELPERS ---
CARD_RANKS_MAP = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                  '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

def get_counts(seven_cards):
    ranks = [CARD_RANKS_MAP[rank] for rank, suit in seven_cards]
    ranks_copy = list(ranks) # Copy to prevent mutation
    suits = [suit for rank, suit in seven_cards]
    rank_counts = collections.Counter(ranks_copy)
    suit_counts = collections.Counter(suits)
    return ranks_copy, rank_counts, suit_counts

def evaluate_seven_card_hand(seven_cards):
    ranks, rank_counts, suit_counts = get_counts(seven_cards)
    unique_ranks = sorted(list(set(ranks)), reverse=True)
    
    # 1. FLUSH CHECK
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

    # 2. STRAIGHT CHECK
    straight_rank = 0
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] == unique_ranks[i+4] + 4:
            straight_rank = unique_ranks[i]
            break
    if not straight_rank and all(r in unique_ranks for r in [14, 5, 4, 3, 2]):
        straight_rank = 5

    # Check Straight Flush
    if is_a_flush and straight_rank:
        if straight_rank == 14: return (9, 14)
        return (8, straight_rank)

    # Prepare for Kind checks
    kinds = sorted([r for r, c in rank_counts.items() if c >= 2], 
                   key=lambda r: (rank_counts[r], r), reverse=True)
    kind_counts = {c: [r for r, count in rank_counts.items() if count == c] for c in [4, 3, 2]}

    # 3. Quads
    if kind_counts[4]:
        quad_rank = kind_counts[4][0]
        kicker = max(r for r in unique_ranks if r != quad_rank)
        return (7, quad_rank, kicker)

    # 4. Full House
    if kind_counts[3] and (len(kind_counts[3]) > 1 or kind_counts[2]):
        trip_rank = kind_counts[3][0]
        pair_ranks = []
        if len(kind_counts[3]) > 1: pair_ranks = [kind_counts[3][1]]
        if kind_counts[2]: pair_ranks.extend(kind_counts[2])
        pair_rank = max(pair_ranks)
        return (6, trip_rank, pair_rank)

    # 5. Flush
    if is_a_flush: return (5, *flush_ranks)

    # 6. Straight
    if straight_rank: return (4, straight_rank)

    # 7. Trips
    if kind_counts[3]:
        trip_rank = kind_counts[3][0]
        kickers = sorted([r for r in unique_ranks if r != trip_rank], reverse=True)[:2]
        return (3, trip_rank, *kickers)

    # 8. Two Pair
    if kind_counts[2] and len(kind_counts[2]) >= 2:
        pair_ranks = sorted(kind_counts[2], reverse=True)[:2]
        kicker = max(r for r in unique_ranks if r not in pair_ranks)
        return (2, *pair_ranks, kicker)

    # 9. One Pair
    if kind_counts[2]:
        pair_rank = kind_counts[2][0]
        kickers = sorted([r for r in unique_ranks if r != pair_rank], reverse=True)[:3]
        return (1, pair_rank, *kickers)

    # 10. High Card
    high_cards = sorted(unique_ranks, reverse=True)[:5]
    return (0, *high_cards)


# --- 2. SIMULATION ENGINE ---
def simulate_equity(hero_hand, board, num_opponents, runs=10000):
    suits = ['s', 'h', 'd', 'c']
    ranks = list(CARD_RANKS_MAP.keys())
    full_deck = [(r, s) for r in ranks for s in suits]
    known_cards = hero_hand + board
    deck = [card for card in full_deck if card not in known_cards]
    hero_wins = 0

    remaining_board_count = 5 - len(board)
    total_unknowns = (num_opponents * 2) + remaining_board_count

    # Pre-calculate Hero Score (Optimization for current state)
    hero_current_score = evaluate_seven_card_hand(list(hero_hand) + list(board))

    for _ in range(runs):
        unknown_cards = random.sample(deck, total_unknowns)
        
        # Slice opponent hands
        opponent_hands = []
        for i in range(num_opponents):
            start = i * 2
            opponent_hands.append(unknown_cards[start : start + 2])
            
        # Slice board remainder
        board_remainder = unknown_cards[num_opponents * 2:]
        final_board = list(board) + list(board_remainder)

        # Evaluate Hero (Clean copy)
        hero_score = evaluate_seven_card_hand(list(hero_hand) + final_board)
        
        # Evaluate Opponents
        max_opponent_score = evaluate_seven_card_hand(list(opponent_hands[0]) + final_board)
        for opp_hand in opponent_hands[1:]:
            score = evaluate_seven_card_hand(list(opp_hand) + final_board)
            if score > max_opponent_score:
                max_opponent_score = score
        
        if hero_score > max_opponent_score:
            hero_wins += 1

    return (hero_wins / runs) * 100


# --- 3. WORKER LISTENER ---
def parse_card_string(card_str):
    if len(card_str) != 2: return None
    return (card_str[0], card_str[1])

QUEUE_NAME = 'analysis_jobs'

try:
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        rdb = Redis.from_url(redis_url, decode_responses=True)
    else:
        redis_host = os.getenv('REDIS_ADDR', 'localhost:6379').split(':')[0]
        rdb = Redis(host=redis_host, port=6379, decode_responses=True)
        
    rdb.ping()
    print("WORKER: Connected to Redis Queue.")
except Exception as e:
    print(f"WORKER FATAL: Could not connect to Redis: {e}")

def start_worker():
    print("WORKER: Listening for jobs...")
    while True:
        job = rdb.brpop(QUEUE_NAME, timeout=60)
        if job:
            _, payload_json = job
            try:
                data = json.loads(payload_json)
                job_id = data.get('job_id')
                hand_id = data.get('hand_id', 'Unknown')
                
                print(f"WORKER: Processing Hand {hand_id}")

                # --- THIS WAS THE MISSING PART IN YOUR CODE ---
                hero_hand_strs = data.get('hero_hand', [])
                board_strs = data.get('board', [])
                hero_hand = [parse_card_string(c) for c in hero_hand_strs]
                board = [parse_card_string(c) for c in board_strs]
                num_opponents = data.get('num_opponents', 3)
                runs = data.get('runs', 10000)
                # ---------------------------------------------

                equity = simulate_equity(hero_hand, board, num_opponents, runs)

                # Save Result
                result_payload = {
                    "hand_id": hand_id,
                    "equity": equity,
                    "hero_hand": hero_hand_strs, 
                    "board": board_strs
                }
                rdb.setex(f"result:{job_id}", 3600, json.dumps(result_payload))
                
                print(f"✅ SAVED: Job {job_id} Equity: {equity:.2f}%")

            except Exception as e:
                print(f"WORKER ERROR: {e}")

if __name__ == "__main__":
    start_worker()