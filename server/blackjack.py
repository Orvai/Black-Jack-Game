import random
import socket
import struct

from common.protocol import (
    pack_payload,
    RESULT_WIN,
    RESULT_LOSS,
    RESULT_TIE,
    RESULT_NOT_OVER,
    DECISION_HIT,
    DECISION_STAND,
    MAGIC_COOKIE,
    MSG_TYPE_PAYLOAD,
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
    # Ace is ALWAYS 11 (per assignment spec)
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def hand_value(hand):
    return sum(card_value(rank) for rank, _ in hand)


# =========================
# Core game
# =========================

def play_game(conn: socket.socket, rounds: int):
    for _ in range(rounds):
        ok = play_round(conn)
        if not ok:
            return


def recv_exact(conn: socket.socket, size: int):
    data = b""
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
        except socket.timeout:
            return None
        if not chunk:
            return None
        data += chunk
    return data


def read_client_decision(data: bytes):
    """
    Client -> Server payload parsing:
    We ONLY care about the Decision field (5 bytes).
    The rest of the payload is ignored by design.
    """
    if len(data) < 14:
        return None

    cookie, msg_type = struct.unpack("!IB", data[:5])
    if cookie != MAGIC_COOKIE or msg_type != MSG_TYPE_PAYLOAD:
        return None

    decision = data[5:10].decode("ascii")
    return decision


def play_round(conn: socket.socket):
    deck = create_deck()

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    # Initial deal
    send_update(conn, player_hand[0])
    send_update(conn, player_hand[1])
    send_update(conn, dealer_hand[0])

    # =========================
    # Player turn
    # =========================
    player_busted = False

    while True:
        data = recv_exact(conn, 14)
        if not data:
            return False

        decision = read_client_decision(data)
        if decision is None:
            continue

        if decision == DECISION_HIT:
            card = deck.pop()
            player_hand.append(card)

            if hand_value(player_hand) > 21:
                # Bust → FINAL payload
                send_result(conn, RESULT_LOSS, card)
                player_busted = True
                break
            else:
                send_update(conn, card)

        elif decision == DECISION_STAND:
            break

        else:
            continue

    if player_busted:
        return True

    # =========================
    # Dealer turn
    # =========================

    # Reveal hidden card
    send_update(conn, dealer_hand[1])

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
    return True


# =========================
# Payload helpers
# =========================

def send_update(conn, card):
    rank, suit = card
    pkt = pack_payload(
        decision=DECISION_STAND,   # irrelevant for server->client
        result=RESULT_NOT_OVER,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)


def send_result(conn, result, card):
    rank, suit = card
    pkt = pack_payload(
        decision=DECISION_STAND,   # irrelevant for server->client
        result=result,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)
