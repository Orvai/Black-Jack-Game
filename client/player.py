import sys
import socket
import common.protocol as protocol 


SUITS = {0: '♥', 1: '♦', 2: '♣', 3: '♠'}
RANKS = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
for r in range(2, 11):
    RANKS[r] = str(r)

def get_card_str(rank, suit):
    r_str = RANKS.get(rank, '?')
    s_str = SUITS.get(suit, '?')
    return f"[{r_str}{s_str}]"


def recv_all(conn, size):

    data = b''
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
            if not chunk:
                return None 
            data += chunk
        except socket.timeout:
            return None
        except OSError:
            return None
    return data


def play_game(conn, total_rounds):
    wins = 0
    played = 0
    
    PAYLOAD_SIZE = 14 

    print(f"\n--- Starting Game ({total_rounds} rounds) ---")

    while played < total_rounds:

        try:
            player_cards = []
            dealer_cards = []
            while len(player_cards) < 2 or len(dealer_cards) < 1:
                data = recv_all(conn, PAYLOAD_SIZE)
                if not data:
                    print("Server disconnected during initial deal.")
                    return

                _, result, rank, suit = protocol.unpack_payload(data)
                if result == protocol.RESULT_NOT_OVER and rank == 0 and suit == 0:
                    print("Waiting for other players...")
                    continue

                card_str = get_card_str(rank, suit)
                if len(player_cards) < 2:
                    player_cards.append(card_str)
                    print(f"Player dealt: {card_str}")
                else:
                    dealer_cards.append(card_str)
                    print(f"Dealer dealt: {card_str}")
            
            print(f"Your hand: {' '.join(player_cards)}")

        except Exception as e:
            print(f"Error in initial deal: {e}")
            return

        round_over = False
        awaiting_player_card = False
        while not round_over:
            try:
                data = recv_all(conn, PAYLOAD_SIZE)
                if not data:
                    print("Server disconnected during the round.")
                    return
                _, result, rank, suit = protocol.unpack_payload(data)

                if result == protocol.RESULT_YOUR_TURN:
                    while True:
                        choice = input("Your move: [H]it or [S]tand? ").strip().lower()
                        if choice == 'h':
                            conn.sendall(protocol.pack_payload(protocol.DECISION_HIT, 0, 0, 0))
                            awaiting_player_card = True
                            break
                        if choice == 's':
                            conn.sendall(protocol.pack_payload(protocol.DECISION_STAND, 0, 0, 0))
                            break
                        print(f"[WARNING] Unknown command ignored: '{choice}'")
                        print("Invalid input. Please type 'H' or 'S'.")
                    continue
                if result == protocol.RESULT_OPPONENT_CARD:
                    print(f"👀 An opponent just drew: {get_card_str(rank, suit)}")
                    continue

                if result == protocol.RESULT_NOT_OVER:
                    if rank != 0:
                        if awaiting_player_card:
                            print(f"You drew: {get_card_str(rank, suit)}")
                            awaiting_player_card = False
                        else:
                            print(f"Dealer drew: {get_card_str(rank, suit)}")
                    print("Waiting for other players...")
                    continue

                if rank != 0:
                    print(f"Final card involved: {get_card_str(rank, suit)}")

                if result == protocol.RESULT_WIN:
                    print("Result: YOU WON! 🎉")
                    wins += 1
                elif result == protocol.RESULT_LOSS:
                    print("Result: YOU LOST 😞")
                elif result == protocol.RESULT_TIE:
                    print("Result: IT'S A TIE 🤝")

                round_over = True
                played += 1
                print("--------------------------------")
            except Exception as e:
                print(f"Error getting result: {e}")
                return

    if played > 0:
        win_rate = (wins / played) * 100
        print(f"Finished playing {played} rounds, win rate: {win_rate:.1f}")