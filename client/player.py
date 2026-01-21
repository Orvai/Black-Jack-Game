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

    # אתחול ה-State עבור ה-UI המשופר
    # שים לב: המבנה תואם בדיוק למה שה-BlackjackUI מצפה לקבל
    game_state = {
        "dealer": {"cards": [], "hidden_cards": 1},
        "players": {}, # מילון שחקנים לפי ID
        "event_log": ["Connected to the Casino!"]
    }

    # הגדרת השחקן המקומי (Team Israel)
    # Seat 1 מיועד ל-Dashboard התחתון ב-UI
    my_id = 999 
    game_state["players"][my_id] = {
        "id": my_id,
        "name": "Team Israel",
        "cards": [],
        "score": 0,
        "bankroll": 1000,
        "is_local": True,
        "seat": 1 
    }

    while played < total_rounds:
        # איפוס נתונים לסיבוב חדש
        game_state["dealer"] = {"cards": [], "hidden_cards": 1}
        game_state["players"][my_id].update({"cards": [], "score": 0, "status": ""})
        
        # איפוס קלפי יריבים קיימים
        for pid in list(game_state["players"].keys()):
            if pid != my_id:
                game_state["players"][pid]["cards"] = []
                game_state["players"][pid]["score"] = 0

        game_state["event_log"].append(f"--- Round {played + 1} Starting ---")
        ui.update_table(game_state)

        round_over = False
        awaiting_player_card = False

        while not round_over:
            # קבלת חבילת מידע מהשרת
            data = recv_all(conn, PAYLOAD_SIZE)
            if not data: 
                return # השרת התנתק

            _, result, rank, suit = protocol.unpack_payload(data)

            # 1. תור השחקן - קבלת קלט מה-Dashboard המעוצב
            if result == protocol.RESULT_YOUR_TURN:
                game_state["players"][my_id]["is_current"] = True
                ui.update_table(game_state)
                
                # קבלת קלט (H/S/Q) דרך ה-UI (עוצר את ה-Live refresh זמנית)
                choice = ui.get_action_prompt()
                
                game_state["players"][my_id]["is_current"] = False
                
                if choice == 'h':
                    conn.sendall(protocol.pack_payload(protocol.DECISION_HIT, 0, 0, 0))
                    awaiting_player_card = True
                elif choice == 'q':
                    ui.stop()
                    print("Quitting game...")
                    return
                else:
                    conn.sendall(protocol.pack_payload(protocol.DECISION_STAND, 0, 0, 0))
                
                ui.update_table(game_state)
                continue

            # 2. יריב משך קלף - יופיע בשורת ה-Opponents המרכזית
            if result == protocol.RESULT_OPPONENT_CARD:
                card = get_card_data(rank, suit)
                
                # סימולציה של יריב (כסא 2-5 ב-UI)
                opp_id = 2 
                if opp_id not in game_state["players"]:
                    game_state["players"][opp_id] = {
                        "name": "Opponent", 
                        "cards": [], 
                        "score": 0, 
                        "seat": 2
                    }
                
                game_state["players"][opp_id]["cards"].append(card)
                game_state["players"][opp_id]["score"] = calculate_score(game_state["players"][opp_id]["cards"])
                game_state["event_log"].append(f"Opponent hit and drew {card['rank']}")
                
                ui.update_table(game_state)
                continue

            # 3. קלף "פסיבי" (חלוקה ראשונית או קלף לדילר)
            if result == protocol.RESULT_NOT_OVER:
                if rank != 0:
                    card = get_card_data(rank, suit)
                    if awaiting_player_card:
                        # קלף שביקשתי ב-Hit
                        p = game_state["players"][my_id]
                        p["cards"].append(card)
                        p["score"] = calculate_score(p["cards"])
                        game_state["event_log"].append(f"You drew {card['rank']}")
                        awaiting_player_card = False
                    else:
                        # קלף לדילר
                        game_state["dealer"]["cards"].append(card)
                        game_state["event_log"].append("Dealer drew a card")
                
                ui.update_table(game_state)
                continue

            # 4. סיום סיבוב (נצחון / הפסד / תיקו)
            if result in [protocol.RESULT_WIN, protocol.RESULT_LOSS, protocol.RESULT_TIE]:
                game_state["dealer"]["hidden_cards"] = 0 # חשיפת הקלף המוסתר של הדילר
                
                if rank != 0:
                    game_state["dealer"]["cards"].append(get_card_data(rank, suit))
                
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
                ui.update_table(game_state)
                
                # השהיה כדי שהשחקן יוכל לראות את התוצאה והקלפים הסופיים
                time.sleep(3) 

    # סיום כל הסבבים
    ui.stop()
    if played > 0:
        win_rate = (wins / played) * 100
        print(f"\n[!] Game Finished! Played: {played}, Wins: {wins}, Win Rate: {win_rate:.1f}%")
    else:
        print("\n[!] No rounds were played.")