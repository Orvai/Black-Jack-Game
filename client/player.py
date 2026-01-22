import sys
import socket
import time
import threading

import common.protocol as protocol

# ==========================================
# פונקציות עזר - תקשורת ולוגיקה
# ==========================================

def recv_all(conn, size):
    data = b''
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
            if not chunk:
                return None  # disconnect
            data += chunk
        except socket.timeout:
            return b''      # just "no data yet"
        except:
            return None
    return data

def get_card_data(rank, suit):
    """המרת נתוני הפרוטוקול לפורמט שה-UI יודע להציג"""
    RANKS = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
    r = RANKS.get(rank, str(rank))
    
    SUITS = {0: 'hearts', 1: 'diamonds', 2: 'clubs', 3: 'spades'}
    s = SUITS.get(suit, 'hearts')
    return {"rank": r, "suit": s}

def calculate_score(cards):
    """חישוב ניקוד בלאק-ג'ק (כולל טיפול ב-Ace כ-1 או 11)"""
    score = 0
    aces = 0
    for c in cards:
        r = c['rank']
        if r == 'A':
            aces += 1
            score += 11
        elif r in ['J', 'Q', 'K']:
            score += 10
        else:
            score += int(r)
    
    # תיקון ניקוד אם עברנו 21 ויש לנו אסים
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

# ==========================================
# לוגיקת המשחק הראשית
# ==========================================

def play_game(conn, total_rounds, ui):
    import threading

    wins = 0
    played = 0
    PAYLOAD_SIZE = 14

    game_state = {
        "dealer": {"cards": [], "hidden_cards": 1},
        "players": {},
        "event_log": ["Connected to the Casino!"]
    }

    my_id = 999
    game_state["players"][my_id] = {
        "id": my_id,
        "name": "Team Israel",
        "cards": [],
        "score": 0,
        "bankroll": 1000,
        "status": "",
        "is_local": True,
        "seat": 1,
        "is_current": False,
    }

    opponent_seat_map = {}

    def alloc_seat(pid):
        if pid in opponent_seat_map:
            return opponent_seat_map[pid]
        used = {p.get("seat") for p in game_state["players"].values()}
        for s in range(2, 6):
            if s not in used:
                opponent_seat_map[pid] = s
                return s
        opponent_seat_map[pid] = 5
        return 5

    def get_or_create_opponent(pid):
        if pid in game_state["players"]:
            return game_state["players"][pid]
        seat = alloc_seat(pid)
        game_state["players"][pid] = {
            "id": pid,
            "name": f"Opponent {pid}",
            "cards": [],
            "score": 0,
            "bankroll": 1000,
            "status": "",
            "is_local": False,
            "seat": seat,
            "is_current": False,
        }
        return game_state["players"][pid]

    def sync_ui():
        for pl in game_state["players"].values():
            pl["score"] = calculate_score(pl["cards"])
        ui.update_table(game_state)

    def reset_round_state():
        game_state["dealer"]["cards"] = []
        game_state["dealer"]["hidden_cards"] = 1
        for pl in game_state["players"].values():
            pl["cards"] = []
            pl["score"] = 0
            pl["status"] = ""
            pl["is_current"] = False

    while played < total_rounds:
        reset_round_state()
        cards_received = 0
        awaiting_hit_card = False

        game_state["event_log"].append(f"--- Round {played + 1} Starting ---")
        sync_ui()

        round_over = False
        while not round_over:
            data = recv_all(conn, PAYLOAD_SIZE)
            if not data:
                return

            _, result, rank, suit = protocol.unpack_payload(data)

            # ---------- OPPONENT ----------
            if result == protocol.RESULT_OPPONENT_CARD:
                pid = (suit >> 2) & 0x3F
                low = suit & 0x03
                opp = get_or_create_opponent(pid)

                if rank == 0:
                    game_state["event_log"].append(
                        f"{opp['name']} {'HIT' if low == 0 else 'STAND'}"
                    )
                else:
                    card = get_card_data(rank, low)
                    opp["cards"].append(card)
                    game_state["event_log"].append(f"{opp['name']} drew {card['rank']}")
                sync_ui()
                continue

            # ---------- YOUR TURN ----------
            if result == protocol.RESULT_YOUR_TURN:
                p = game_state["players"][my_id]
                p["is_current"] = True
                ui._turn_player_key = str(my_id)
                ui._turn_started_at = time.monotonic()
                game_state["event_log"].append("Your turn!")
                sync_ui()

                choice_holder = {"choice": None}

                def read_choice():
                    try:
                        choice_holder["choice"] = ui.get_action_prompt()
                    except:
                        choice_holder["choice"] = "s"

                t = threading.Thread(target=read_choice, daemon=True)
                t.start()

                prev_timeout = conn.gettimeout()
                conn.settimeout(0.2)

                try:
                    while True:
                        if choice_holder["choice"] is not None:
                            break
                        try:
                            data2 = conn.recv(PAYLOAD_SIZE)
                        except socket.timeout:
                            sync_ui()
                            continue

                        if not data2:
                            return

                        _, r2, rk2, st2 = protocol.unpack_payload(data2)

                        # Server auto-stand / progress
                        if r2 != protocol.RESULT_YOUR_TURN:
                            result, rank, suit = r2, rk2, st2
                            break
                finally:
                    conn.settimeout(prev_timeout)
                    p["is_current"] = False
                    sync_ui()

                if result != protocol.RESULT_YOUR_TURN:
                    continue

                choice = choice_holder["choice"]

                if choice == 'h':
                    conn.sendall(protocol.pack_payload(protocol.DECISION_HIT, 0, 0, 0))
                    awaiting_hit_card = True
                    game_state["event_log"].append("You chose HIT")
                elif choice == 'q':
                    ui.stop()
                    return
                else:
                    conn.sendall(protocol.pack_payload(protocol.DECISION_STAND, 0, 0, 0))
                    awaiting_hit_card = False
                    game_state["event_log"].append("You chose STAND")

                sync_ui()
                continue

            # ---------- CARD UPDATE ----------
            if result == protocol.RESULT_NOT_OVER:
                if rank == 0:
                    sync_ui()
                    continue

                card = get_card_data(rank, suit)
                if cards_received < 2:
                    game_state["players"][my_id]["cards"].append(card)
                elif cards_received == 2:
                    game_state["dealer"]["cards"].append(card)
                else:
                    if awaiting_hit_card:
                        game_state["players"][my_id]["cards"].append(card)
                        awaiting_hit_card = False
                    else:
                        game_state["dealer"]["cards"].append(card)

                cards_received += 1
                sync_ui()
                continue

            # ---------- ROUND OVER ----------
            if result in (protocol.RESULT_WIN, protocol.RESULT_LOSS, protocol.RESULT_TIE):
                game_state["dealer"]["hidden_cards"] = 0

                if rank != 0:
                    card = get_card_data(rank, suit)
                    game_state["dealer"]["cards"].append(card)

                p = game_state["players"][my_id]
                if result == protocol.RESULT_WIN:
                    p["status"] = "WINNER"
                    p["bankroll"] += 100
                    wins += 1
                elif result == protocol.RESULT_LOSS:
                    p["status"] = "BUSTED"
                    p["bankroll"] -= 100
                else:
                    p["status"] = "STAY"

                played += 1
                round_over = True
                sync_ui()
                time.sleep(2)
                break

    ui.stop()

    if played > 0:
        win_rate = (wins / played) * 100
        print(f"\n[!] Game Finished! Played: {played}, Wins: {wins}, Win Rate: {win_rate:.1f}%")
    else:
        print("\n[!] No rounds were played.")
