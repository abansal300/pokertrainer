import random
import collections
import itertools
from collections import Counter

# --- Configuration ---
# Example: Hero has Ace-King of Spades vs a generic opponent range
HERO_HAND = [('A', 's'), ('K', 's')]
BOARD = [('T', 'c'), ('J', 'd'), ('2', 'h')] # Ten, Jack, Two on the flop
SIMULATION_RUNS = 10000

# Standard card values for comparison
CARD_RANKS = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
# --- End Config ---

def get_counts(seven_cards):
    ranks = [CARD_RANKS[rank] for rank, suit in seven_cards]

    ranks_copy = list(ranks)

    suits = [suit for rank, suit in seven_cards]

    rank_counts = collections.Counter(ranks_copy)
    suit_counts = collections.Counter(suits)

    return ranks_copy, rank_counts, suit_counts

def evaluate_hand(seven_cards):
    
    ranks, rank_counts, suit_counts = get_counts(seven_cards)
    unique_ranks = sorted(list(set(ranks)), reverse=True)

    # Flush Check
    is_a_flush = False
    flush_suit = None
    for suit, count in suit_counts.items():
        if count >= 5:
            is_a_flush = True
            flush_suit = suit
            break
    
    if is_a_flush:
        flush_cards = sorted([CARD_RANKS[rank] for rank, suit in seven_cards if suit == flush_suit], reverse=True)
        flush_ranks = flush_cards[:5]

    # Straight Check
    straight_rank = 0
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] == unique_ranks[i + 4] + 4:
            straight_rank = unique_ranks[i]
            break
    
    if not straight_rank and all(r in unique_ranks for r in [14, 5, 4, 3, 2]):
        straight_rank = 5 #Ace-Five straight
    
    #Straight Flush Check
    if is_a_flush and straight_rank:

        #Royal Flush
        if straight_rank == 14:
            return (9, 14)
        
        return (8, straight_rank)

    #Quads, Full House, Pairs
    kinds = sorted([r for r, c in rank_counts.items() if c >= 2], 
                   key=lambda r: (rank_counts[r], r), reverse=True)

    kind_counts = {c: [r for r, count in rank_counts.items() if count == c] for c in [4, 3, 2]}

    if kind_counts[4]:
        quad_rank = kind_counts[4][0]
        kicker = max(r for r in ranks if r != quad_rank)
        return (7, quad_rank, kicker)

    #Full House
    if kind_counts[3] and (len(kind_counts[3]) > 1 or kind_counts[2]):
        triple_rank = kind_counts[3][0]

        pair_ranks = []
        if len(kind_counts[3]) > 1:
            pair_ranks = [kind_counts[3][1]]

        if kind_counts[2]:
            pair_ranks.extend(kind_counts[2])
        pair_ranks = max(pair_ranks)

        return (6, triple_rank, pair_ranks)

    #Just Flush
    if is_a_flush:
        return (5, *flush_ranks)

    #Just Straight
    if straight_rank:
        return (4, straight_rank)
    
    #Three of a kind
    if kind_counts[3]:
        trip_rank = kind_counts[3][0]
        kickers = sorted([r for r in ranks if r != trip_rank], reverse=True)[:2]

        return (3, trip_rank, *kickers)

    #Two Pair
    if kind_counts[2] and len(kind_counts[2]) >= 2:
        pair_ranks = sorted(kind_counts[2], reverse=True)[:2]
        kicker = max(r for r in unique_ranks if r not in pair_ranks)
        return (2, *pair_ranks, kicker)
    
    #One Pair
    if kind_counts[2]:
        pair_rank = kind_counts[2][0]
        kickers = sorted([r for r in unique_ranks if r != pair_rank], reverse=True)[:3]
        return (1, pair_rank, *kickers)

    #High Card
    high_cards = sorted(unique_ranks, reverse=True)[:5]
    return (0, *high_cards)

def simulate_equity(hero_hand, board, num_opponents, runs=10000):
    print("--- Starting Equity Simulation ---")

    # 1. SETUP
    suits = ['s', 'h', 'd', 'c']
    ranks = list(CARD_RANKS.keys())
    full_deck = [(r, s) for r in ranks for s in suits]

    #Remove hero's hand and board cards from deck
    known_cards = hero_hand + board
    deck = [card for card in full_deck if card not in known_cards]

    hero_wins = 0

    # 2. CALCULATE UNKOWNS
    remaining_board_count = 5 - len(board)
    total_unknowns_to_deal = (num_opponents * 2) + remaining_board_count

    if total_unknowns_to_deal > len(deck):
        print(f"Error: Not enough cards in deck to deal to all opponents and board.")
        return 0.0
    
    for _ in range(runs):
        # 3. DEAL ALL UNKOWN CARDS
        unknown_cards = random.sample(deck, total_unknowns_to_deal)

        # 4. SLICING UNKNOWNS
        opponents_hands = []

        for i in range(num_opponents):
            start_index = i * 2
            opponents_hands.append(unknown_cards[start_index:start_index+2])

        #Community Cards Remain
        board_start_index = num_opponents * 2
        remaining_community_cards = unknown_cards[board_start_index:]
        final_board = board + remaining_community_cards

        # 5. EVALUATION/WINNING CONDITION

        hero_score = evaluate_hand(hero_hand + final_board)

        max_opponent_score = evaluate_hand(opponents_hands[0] + list(final_board))

        for opponent_hand in opponents_hands[1:]:
            opponent_score = evaluate_hand(opponent_hand + list(final_board))
            if opponent_score > max_opponent_score:
                max_opponent_score = opponent_score
        
        # Winning Condition
        if hero_score > max_opponent_score:
            hero_wins += 1
        
    equity = (hero_wins / runs) * 100
    print(f"Equity vs {num_opponents} opponents: {equity:.2f}%")
    print("--- Simulation Complete ---")
    return equity

if __name__ == "__main__":
    #Test Scnario: Hero has Ace-King suited vs 3 opponents on a Ten-high flop
    # TEST_HERO_HAND = [('A', 's'), ('K', 's')]
    # TEST_BOARD = [('T', 'c'), ('J', 'd'), ('2', 'h')]
    # TEST_OPPONENTS = 3

    # simulate_equity(TEST_HERO_HAND, TEST_BOARD, TEST_OPPONENTS)

    TEST_HERO_HAND = [('2', 'c'), ('3', 'h')]
    TEST_BOARD = [('A', 'd'), ('A', 's'), ('K', 's')] # Two Aces and a King
    TEST_OPPONENTS = 1 # Keep opponents low to reduce simulation noise
    
    simulate_equity(TEST_HERO_HAND, TEST_BOARD, TEST_OPPONENTS)









