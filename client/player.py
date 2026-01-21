import sys
import socket
import time
import common.protocol as protocol

# ==========================================
# פונקציות עזר - תקשורת ולוגיקה
# ==========================================

def recv_all(conn, size):
    """קבלת נתונים מלאה מהסוקט כדי להבטיח חבילות שלמות"""
    data = b''
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
            if not chunk: 
                return None 
            data += chunk
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
    wins = 0
    played = 0
    PAYLOAD_SIZE = 14

    # UI state (compatible with BlackjackUI)
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

    def sync_ui():
        """Always recompute score right before rendering."""
        p = game_state["players"][my_id]
        p["score"] = calculate_score(p["cards"])
        ui.update_table(game_state)

    def reset_round_state():
        """Hard reset: never carry state between rounds."""
        game_state["dealer"]["cards"] = []
        game_state["dealer"]["hidden_cards"] = 1

        p = game_state["players"][my_id]
        p["cards"] = []
        p["score"] = 0
        p["status"] = ""
        p["is_current"] = False

        # Remove any non-local players so UI shows VACANT seats
        game_state["players"] = {my_id: p}

    while played < total_rounds:
        reset_round_state()

        # ===== Internal Sequence Tracker =====
        # Count only real cards (rank != 0) received this round
        cards_received = 0
        awaiting_hit_card = False

        game_state["event_log"].append(f"--- Round {played + 1} Starting ---")
        sync_ui()

        round_over = False
        while not round_over:
            data = recv_all(conn, PAYLOAD_SIZE)
            if not data:
                return  # server disconnected

            _, result, rank, suit = protocol.unpack_payload(data)

            # ---------- YOUR TURN ----------
            if result == protocol.RESULT_YOUR_TURN:
                p = game_state["players"][my_id]
                try:
                    p["is_current"] = True
                    sync_ui()

                    choice = ui.get_action_prompt()
                finally:
                    # Never allow UI to get stuck in turn mode
                    p["is_current"] = False
                    sync_ui()

                if choice == 'h':
                    conn.sendall(protocol.pack_payload(protocol.DECISION_HIT, 0, 0, 0))
                    awaiting_hit_card = True
                    game_state["event_log"].append("You chose HIT")
                elif choice == 'q':
                    ui.stop()
                    print("Quitting game...")
                    return
                else:
                    conn.sendall(protocol.pack_payload(protocol.DECISION_STAND, 0, 0, 0))
                    awaiting_hit_card = False
                    game_state["event_log"].append("You chose STAND")

                sync_ui()
                continue

            # ---------- NOT OVER (a card update) ----------
            if result == protocol.RESULT_NOT_OVER:
                if rank == 0:
                    # "waiting" / heartbeat payload
                    sync_ui()
                    continue

                card = get_card_data(rank, suit)

                # Strict ownership rules:
                # First 2 cards -> player
                # Next 1 card -> dealer (face up) + hidden_cards stays 1
                # After HIT -> player
                # Otherwise -> dealer
                if cards_received < 2:
                    p = game_state["players"][my_id]
                    p["cards"].append(card)
                    game_state["event_log"].append(f"You were dealt {card['rank']}")
                elif cards_received == 2:
                    game_state["dealer"]["cards"].append(card)
                    game_state["dealer"]["hidden_cards"] = 1
                    game_state["event_log"].append("Dealer dealt a face-up card")
                else:
                    if awaiting_hit_card:
                        p = game_state["players"][my_id]
                        p["cards"].append(card)
                        game_state["event_log"].append(f"You drew {card['rank']}")
                        awaiting_hit_card = False
                    else:
                        game_state["dealer"]["cards"].append(card)
                        game_state["event_log"].append("Dealer drew a card")

                cards_received += 1
                sync_ui()
                continue

            # ---------- ROUND OVER ----------
            if result in (protocol.RESULT_WIN, protocol.RESULT_LOSS, protocol.RESULT_TIE):
                # Dealer hole card is revealed at round end
                game_state["dealer"]["hidden_cards"] = 0

                if rank != 0:
                    final_card = get_card_data(rank, suit)

                    # Avoid duplicate: server often sends last dealer card both as update and as result payload
                    dealer_cards = game_state["dealer"]["cards"]
                    if not dealer_cards or dealer_cards[-1] != final_card:
                        dealer_cards.append(final_card)

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
                game_state["event_log"].append(f"Round Over: {p['status']}")
                sync_ui()
                time.sleep(3)
                continue

            # ---------- Anything else ----------
            sync_ui()

    ui.stop()
    if played > 0:
        win_rate = (wins / played) * 100
        print(f"\n[!] Game Finished! Played: {played}, Wins: {wins}, Win Rate: {win_rate:.1f}%")
    else:
        print("\n[!] No rounds were played.")
