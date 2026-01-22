# server.py
import socket
import threading
import time
from dataclasses import dataclass, field

from . import blackjack

from common.protocol import (
    pack_offer,
    pack_payload,
    unpack_request,
    DECISION_STAND,
    RESULT_NOT_OVER,
    RESULT_LOSS,
    RESULT_TIE,
    RESULT_WIN,
    RESULT_YOUR_TURN,
    RESULT_OPPONENT_CARD,
    DECISION_HIT,
)

# =========================
# Config
# =========================
BROADCAST_PORT = 13122
OFFER_INTERVAL = 1.0
SERVER_NAME = "BlackjackServer"

# Separate timeouts:
REQUEST_TIMEOUT = 5.0      # only for reading the initial request packet
GAMEPLAY_TIMEOUT = 120.0    # allow user time to think/type during rounds
TURN_TIMEOUT = 15.0  # seconds per player turn
GAME_STATUS_WAITING = "WAITING"
GAME_STATUS_IN_PROGRESS = "IN_PROGRESS"

ROUND_JOIN_WINDOW = 10

@dataclass
class Player:
    id: int
    conn: socket.socket
    addr: tuple
    name: str
    remaining_rounds: int
    hand: list = field(default_factory=list)
    is_busted: bool = False
    is_standing: bool = False



class CasinoTable:
    def __init__(self):
        self.active_players = []
        self.waiting_room = []
        self.game_status = GAME_STATUS_WAITING
        self.lock = threading.Lock()
        self.dealer_hand = []
        self.next_player_id = 1

# =========================
# UDP Offer Thread
# =========================
def udp_offer_loop(tcp_port: int):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    offer_packet = pack_offer(tcp_port, SERVER_NAME)

    while True:
        udp_socket.sendto(offer_packet, ("<broadcast>", BROADCAST_PORT))
        time.sleep(OFFER_INTERVAL)


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


def get_local_ip():
    ip = "127.0.0.1"
    try:
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)
        for entry in addr_info:
            candidate = entry[4][0]
            if not candidate.startswith("127."):
                ip = candidate
                break
    except OSError:
        pass
    return ip

# =========================
# TCP Client Handler
# =========================
def handle_client(conn: socket.socket, addr, table: CasinoTable):
    registered = False
    try:
        # 1) Timeout only for receiving the initial request
        conn.settimeout(REQUEST_TIMEOUT)
        data = recv_exact(conn, 38)
        if not data:
            print(f"[TCP] No request received from {addr} (timeout/disconnect).")
            return
        try:
            conn.settimeout(0.1)
            peek_byte = conn.recv(1, socket.MSG_PEEK)
            if peek_byte in (b"\n", b"\r"):
                conn.recv(1)
        except socket.timeout:
            pass
        rounds, client_name = unpack_request(data)
        print(f"[TCP] Client {addr} -> name='{client_name}', rounds={rounds}")

        # 2) Gameplay timeout should be long enough for human input
        conn.settimeout(GAMEPLAY_TIMEOUT)

        with table.lock:
            pid = table.next_player_id
            table.next_player_id += 1

        player = Player(
            id=pid,
            conn=conn,
            addr=addr,
            name=client_name,
            remaining_rounds=rounds
        )
        should_wait = False
        with table.lock:
            if table.game_status == GAME_STATUS_WAITING:
                table.active_players.append(player)
                registered = True
            else:
                table.waiting_room.append(player)
                should_wait = True
                registered = True
        if should_wait:
            send_waiting_payload(conn)
        display_dashboard(table)

    except socket.timeout:
        print(f"[TCP] Timeout from {addr} (request or gameplay).")
    except Exception as e:
        print(f"[TCP] Error from {addr}: {e}")
    finally:
        if not registered:
            try:
                conn.close()
            except OSError:
                pass


def send_waiting_payload(conn: socket.socket):
    pkt = pack_payload(
        decision=DECISION_STAND,
        result=RESULT_NOT_OVER,
        rank=0,
        suit=0
    )
    try:
        conn.sendall(pkt)
    except OSError:
        pass


def broadcast(message: bytes, player_list, table: CasinoTable):
    with table.lock:
        players_snapshot = list(player_list)
    dead_players = []
    for player in players_snapshot:
        try:
            player.conn.sendall(message)
        except OSError:
            dead_players.append(player)
    if dead_players:
        with table.lock:
            for player in dead_players:
                if player in player_list:
                    player_list.remove(player)
                try:
                    player.conn.close()
                except OSError:
                    pass

def _encode_opponent_suit(player_id: int, suit: int) -> int:
    return ((player_id & 0x3F) << 2) | (suit & 0x03)


def broadcast_opponent_card(table: CasinoTable, source_player: Player, card):
    rank, suit = card
    pkt = pack_payload(
        decision=DECISION_STAND,
        result=RESULT_OPPONENT_CARD,
        rank=rank,
        suit=_encode_opponent_suit(source_player.id, suit)
    )
    with table.lock:
        targets = [p for p in table.active_players if p is not source_player]
    for p in targets:
        try:
            p.conn.sendall(pkt)
        except OSError:
            pass


def broadcast_opponent_action(table: CasinoTable, source_player: Player, action_code: int):
    pkt = pack_payload(
        decision=DECISION_STAND,
        result=RESULT_OPPONENT_CARD,
        rank=0,
        suit=_encode_opponent_suit(source_player.id, action_code)
    )
    with table.lock:
        targets = [p for p in table.active_players if p is not source_player]
    for p in targets:
        try:
            p.conn.sendall(pkt)
        except OSError:
            pass



def send_update(conn: socket.socket, card):
    rank, suit = card
    pkt = pack_payload(
        decision=DECISION_STAND,
        result=RESULT_NOT_OVER,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)


def send_result(conn: socket.socket, result: int, card):
    rank, suit = card
    pkt = pack_payload(
        decision=DECISION_STAND,
        result=result,
        rank=rank,
        suit=suit
    )
    conn.sendall(pkt)


def display_dashboard(table: CasinoTable):
    with table.lock:
        active_count = len(table.active_players)
        waiting_count = len(table.waiting_room)
        status = table.game_status
        dealer_hand = list(table.dealer_hand)
    print("[DASHBOARD] Live Table")
    print(f"[DASHBOARD] Status: {status}")
    print(f"[DASHBOARD] Active players: {active_count}")
    print(f"[DASHBOARD] Waiting players: {waiting_count}")
    print(f"[DASHBOARD] Dealer hand: {dealer_hand}")


def remove_player(table: CasinoTable, player: Player):
    with table.lock:
        if player in table.active_players:
            table.active_players.remove(player)
        if player in table.waiting_room:
            table.waiting_room.remove(player)
    try:
        player.conn.close()
    except OSError:
        pass


def run_table_loop(table: CasinoTable):
    while True:
        with table.lock:
            has_players = bool(table.active_players or table.waiting_room)
        if not has_players:
            time.sleep(1)
            continue

        # ===== Waiting room join window =====
        countdown_start = time.time()
        while time.time() - countdown_start < ROUND_JOIN_WINDOW:
            display_dashboard(table)
            time.sleep(1)

        with table.lock:
            if table.waiting_room:
                table.active_players.extend(table.waiting_room)
                table.waiting_room.clear()
            table.game_status = GAME_STATUS_IN_PROGRESS
            players_snapshot = list(table.active_players)

        if not players_snapshot:
            with table.lock:
                table.game_status = GAME_STATUS_WAITING
            continue

        # ===== Deal cards =====
        deck = blackjack.create_deck()
        dealer_hand = [deck.pop(), deck.pop()]
        with table.lock:
            table.dealer_hand = list(dealer_hand)

        for player in players_snapshot:
            player.hand = [deck.pop(), deck.pop()]
            player.is_busted = False
            player.is_standing = False
            try:
                send_update(player.conn, player.hand[0])
                broadcast_opponent_card(table, player, player.hand[0])
                send_update(player.conn, player.hand[1])
                broadcast_opponent_card(table, player, player.hand[1])
            except OSError:
                remove_player(table, player)

        # Dealer face-up card
        dealer_face_up = dealer_hand[0]
        broadcast(
            pack_payload(
                decision=DECISION_STAND,
                result=RESULT_NOT_OVER,
                rank=dealer_face_up[0],
                suit=dealer_face_up[1]
            ),
            table.active_players,
            table
        )

        # ===== Player turns =====
        for player in list(table.active_players):
            if player not in table.active_players:
                continue

            try:
                while not player.is_busted and not player.is_standing:
                    blackjack.drain_socket_buffer(player.conn)

                    # Signal turn start
                    try:
                        player.conn.sendall(
                            pack_payload(
                                decision=DECISION_STAND,
                                result=RESULT_YOUR_TURN,
                                rank=0,
                                suit=0
                            )
                        )
                    except OSError:
                        remove_player(table, player)
                        break

                    player.conn.settimeout(TURN_TIMEOUT)
                    data = blackjack.recv_exact(player.conn, 14)

                    # ===== AUTO-STAND on timeout =====
                    if not data:
                        player.is_standing = True
                        broadcast_opponent_action(table, player, 1)

                        # Notify the player himself to exit CURRENT TURN
                        try:
                            player.conn.sendall(
                                pack_payload(
                                    decision=DECISION_STAND,
                                    result=RESULT_NOT_OVER,
                                    rank=0,
                                    suit=0
                                )
                            )
                        except OSError:
                            remove_player(table, player)

                        player.conn.settimeout(GAMEPLAY_TIMEOUT)
                        break

                    decision = blackjack.read_client_decision(data)
                    if decision is None:
                        continue

                    # Restore normal timeout after valid input
                    player.conn.settimeout(GAMEPLAY_TIMEOUT)

                    if decision == DECISION_HIT:
                        card = deck.pop()
                        player.hand.append(card)
                        try:
                            send_update(player.conn, card)
                            broadcast_opponent_action(table, player, 0)
                            broadcast_opponent_card(table, player, card)
                        except OSError:
                            remove_player(table, player)
                            break

                        if blackjack.hand_value(player.hand) > 21:
                            player.is_busted = True
                            break

                    elif decision == DECISION_STAND:
                        player.is_standing = True
                        broadcast_opponent_action(table, player, 1)

            except (OSError, ValueError):
                remove_player(table, player)

        # ===== Dealer turn =====
        with table.lock:
            active_players = list(table.active_players)
        if not active_players:
            with table.lock:
                table.game_status = GAME_STATUS_WAITING
                table.dealer_hand = []
            continue

        # Reveal hidden dealer card
        dealer_hidden = dealer_hand[1]
        broadcast(
            pack_payload(
                decision=DECISION_STAND,
                result=RESULT_NOT_OVER,
                rank=dealer_hidden[0],
                suit=dealer_hidden[1]
            ),
            table.active_players,
            table
        )

        while blackjack.hand_value(dealer_hand) < 17:
            card = deck.pop()
            dealer_hand.append(card)
            with table.lock:
                table.dealer_hand = list(dealer_hand)
            broadcast(
                pack_payload(
                    decision=DECISION_STAND,
                    result=RESULT_NOT_OVER,
                    rank=card[0],
                    suit=card[1]
                ),
                table.active_players,
                table
            )

        # ===== Results =====
        dealer_score = blackjack.hand_value(dealer_hand)
        last_dealer_card = dealer_hand[-1]

        for player in list(table.active_players):
            if player.is_busted:
                result = RESULT_LOSS
            else:
                player_score = blackjack.hand_value(player.hand)
                if dealer_score > 21 or player_score > dealer_score:
                    result = RESULT_WIN
                elif player_score < dealer_score:
                    result = RESULT_LOSS
                else:
                    result = RESULT_TIE
            try:
                send_result(player.conn, result, last_dealer_card)
            except OSError:
                remove_player(table, player)

        # ===== Round cleanup =====
        with table.lock:
            for player in list(table.active_players):
                player.remaining_rounds -= 1
                player.hand = []
                player.is_busted = False
                player.is_standing = False
                if player.remaining_rounds <= 0:
                    table.active_players.remove(player)
                    try:
                        player.conn.close()
                    except OSError:
                        pass

            table.dealer_hand = []
            table.game_status = GAME_STATUS_WAITING

        display_dashboard(table)


# =========================
# Main
# =========================
def main():
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(("", 0))
    tcp_socket.listen()

    table = CasinoTable()
    tcp_port = tcp_socket.getsockname()[1]
    local_ip = get_local_ip()
    print(f"Server started, listening on IP address {local_ip}")

    threading.Thread(
        target=udp_offer_loop,
        args=(tcp_port,),
        daemon=True
    ).start()
    threading.Thread(
        target=run_table_loop,
        args=(table,),
        daemon=True
    ).start()

    while True:
        conn, addr = tcp_socket.accept()
        print(f"[SERVER] New connection from {addr}")
        threading.Thread(
            target=handle_client,
            args=(conn, addr, table),
            daemon=True
        ).start()


if __name__ == "__main__":
    main()
