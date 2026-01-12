import random
import socket

from common.protocol import (
    pack_payload,
    unpack_payload,
    RESULT_WIN,
    RESULT_LOSS,
    RESULT_TIE,
    RESULT_NOT_OVER,
)

# =========================
# Card utilities
# =========================

SUITS = [0, 1, 2, 3]
RANKS = list(range(1, 14))


def create_deck():
    deck = [(rank, suit) for rank in RANKS for suit in SUITS]
    random.shuffle(deck)
    return deck


def card_value(rank: int) -> int:
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def hand_value(hand):
    value = sum(card_value(r) for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == 1)
    while value > 21 and aces:
        value -= 10
        aces -= 1

    return value


# =========================
# Core game
# =========================

def play_game(conn: socket.socket, rounds: int):
    for _ in range(rounds):
        play_round(conn)
    return


def play_round(conn: socket.socket):
    deck = create_deck()

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    
    send_update(conn, player_hand[0])
    send_update(conn, player_hand[1])
    send_update(conn, dealer_hand[0])

    # =========================
    # Player turn
    # =========================
    while True:
        player_score = hand_value(player_hand)
        # if player_score > 21:
        #     last_card = player_hand[-1] 
        #     send_result(conn, RESULT_LOSS, last_card)
        #     return

        data = conn.recv(1024)
        if not data:
            return 

        decision, _, _, _ = unpack_payload(data)

        if decision == "Hit":
            card = deck.pop()
            player_hand.append(card)
            print(hand_value(player_hand))
            if hand_value(player_hand) > 21:
                send_result(conn, RESULT_LOSS, card)
                return
            else:
                send_update(conn, card)


        elif decision == "Stand":
            break

        else:
            continue

    # =========================
    # Dealer turn
    # =========================

    hidden_card = dealer_hand[1]
    send_update(conn, hidden_card)

    while hand_value(dealer_hand) < 17:
        card = deck.pop()
        dealer_hand.append(card)
        send_update(conn, card)

    # =========================
    # Determine result
    # =========================
    player_score = hand_value(player_hand)
    dealer_score = hand_value(dealer_hand)

    if dealer_score > 21 or player_score > dealer_score:
        result = RESULT_WIN
    elif player_score < dealer_score:
        result = RESULT_LOSS
    else:
        result = RESULT_TIE

    last_card = dealer_hand[-1]
    send_result(conn, result, last_card)


# =========================
# Payload helpers 
# =========================

def send_update(conn, card):
    rank, suit = card
    pkt = pack_payload(
        decision="", 
        result=RESULT_NOT_OVER,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)


def send_result(conn, result, card):
    rank, suit = card
    pkt = pack_payload(
        decision="",  
        result=result,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)