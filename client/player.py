import sys
import socket
import time
import common.protocol as protocol 

# ==========================================
# עזרי עזר לניהול הקלפים והתקשורת
# ==========================================

def get_card_data(rank, suit):
    """ממיר את נתוני הפרוטוקול לפורמט שה-UI מבין"""
    RANKS = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
    r = RANKS.get(rank, str(rank))
    
    SUITS = {0: 'hearts', 1: 'diamonds', 2: 'clubs', 3: 'spades'}
    s = SUITS.get(suit, 'hearts')
    return {"rank": r, "suit": s}

def recv_all(conn, size):
    """פונקציית העזר המקורית שלך לקבלת נתונים מלאה מהסוקט"""
    data = b''
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
            if not chunk: return None 
            data += chunk
        except: return None
    return data

# ==========================================
# לוגיקת המשחק הראשית
# ==========================================

def play_game(conn, total_rounds, ui):
    wins = 0
    played = 0
    PAYLOAD_SIZE = 14 

    # אתחול מצב המשחק עבור ה-UI
    game_state = {
        "dealer": {"cards": [], "hidden_cards": 1},
        "players": [None] * 5,
        "event_log": ["Connected! Waiting for deal..."]
    }

    # השחקן המקומי תמיד בכסא 0
    game_state["players"][0] = {
        "name": "Team Israel", "cards": [], "score": 0, "is_local": True, "status": ""
    }

    while played < total_rounds:
        # איפוס נתונים לסיבוב חדש
        game_state["dealer"] = {"cards": [], "hidden_cards": 1}
        game_state["players"][0]["cards"] = []
        game_state["players"][0]["status"] = ""
        game_state["event_log"].append(f"--- Round {played + 1} Starting ---")
        ui.update_table(game_state)

        round_over = False
        awaiting_player_card = False

        while not round_over:
            data = recv_all(conn, PAYLOAD_SIZE)
            if not data:
                return # השרת התנתק

            _, result, rank, suit = protocol.unpack_payload(data)

            # 1. תור השחקן
            if result == protocol.RESULT_YOUR_TURN:
                game_state["players"][0]["is_current"] = True
                ui.update_table(game_state)
                
                # קבלת קלט דרך ה-UI
                choice = ui.console.input("[bold yellow]Hit [H] or Stand [S]? [/]").strip().lower()
                
                game_state["players"][0]["is_current"] = False
                if choice == 'h':
                    conn.sendall(protocol.pack_payload(protocol.DECISION_HIT, 0, 0, 0))
                    awaiting_player_card = True
                else:
                    conn.sendall(protocol.pack_payload(protocol.DECISION_STAND, 0, 0, 0))
                ui.update_table(game_state)
                continue

            # 2. עדכון על קלף של יריב
            if result == protocol.RESULT_OPPONENT_CARD:
                card = get_card_data(rank, suit)
                game_state["event_log"].append(f"Opponent drew {card['rank']}")
                # עדכון כסא יריב (נשתמש בכסא 2 כברירת מחדל)
                if not game_state["players"][1]:
                    game_state["players"][1] = {"name": "Opponent", "cards": [], "score": 0}
                game_state["players"][1]["cards"].append(card)
                ui.update_table(game_state)
                continue

            # 3. קלף לדילר או לשחקן המקומי
            if result == protocol.RESULT_NOT_OVER:
                if rank != 0:
                    card = get_card_data(rank, suit)
                    if awaiting_player_card:
                        game_state["players"][0]["cards"].append(card)
                        game_state["event_log"].append(f"You drew {card['rank']}")
                        awaiting_player_card = False
                    else:
                        game_state["dealer"]["cards"].append(card)
                        game_state["event_log"].append("Dealer drew a card")
                ui.update_table(game_state)
                continue

            # 4. סיום סיבוב (נצחון/הפסד/תיקו)
            if result in [protocol.RESULT_WIN, protocol.RESULT_LOSS, protocol.RESULT_TIE]:
                game_state["dealer"]["hidden_cards"] = 0 # חשוף קלפים
                if rank != 0:
                    game_state["dealer"]["cards"].append(get_card_data(rank, suit))
                
                if result == protocol.RESULT_WIN:
                    game_state["players"][0]["status"] = "WINNER"
                    wins += 1
                elif result == protocol.RESULT_LOSS:
                    game_state["players"][0]["status"] = "BUSTED"
                else:
                    game_state["players"][0]["status"] = "STAY"

                played += 1
                round_over = True
                game_state["event_log"].append(f"Round Over: {game_state['players'][0]['status']}")
                ui.update_table(game_state)
                time.sleep(2.5) # זמן לראות את התוצאה

    ui.console.print(f"\n[bold green]Game Finished![/] Win rate: {(wins/played)*100:.1f}%")
    time.sleep(2)