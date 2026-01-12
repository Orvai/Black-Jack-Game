import socket
import sys

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
            for i in range(3):
                data = recv_all(conn, PAYLOAD_SIZE)
                if not data: 
                    print("Server disconnected during initial deal.")
                    return

                _, _, rank, suit = protocol.unpack_payload(data)
                
                card_str = get_card_str(rank, suit)
                if i < 2:
                    player_cards.append(card_str)
                    print(f"Player dealt: {card_str}")
                else:
                    print(f"Dealer dealt: {card_str}")
            
            print(f"Your hand: {' '.join(player_cards)}")

        except Exception as e:
            print(f"Error in initial deal: {e}")
            return

        my_turn = True
        while my_turn:
            choice = input("Your move: [H]it or [S]tand? ").strip().lower()
            
            if choice == 'h':
                print("[DEBUG] 1. Preparing packet...")
                packet = protocol.pack_payload("Hit", 0, 0, 0)
                print(f"[DEBUG] 2. Packet ready ({len(packet)} bytes). Sending...")
                try:
                    print("[DEBUG] 1. s")
                    conn.sendall(packet)
                    print(f"[DEBUG] 2. P ({len(packet)} bytes). Sending...")
                    
                    data = recv_all(conn, PAYLOAD_SIZE)
                    if not data: return
                    _, result, rank, suit = protocol.unpack_payload(data)
                    
                    print(f"You drew: {get_card_str(rank, suit)}")
                    
                    if result != protocol.RESULT_NOT_OVER:
                         my_turn = False 

                except Exception as e:
                    print(f"Error during Hit: {e}")
                    return
                
            elif choice == 's':
                try:
                    print("[DEBUG] Processing STAND")
                    conn.sendall(protocol.pack_payload("Stand", 0, 0, 0))
                    my_turn = False
                except Exception as e:
                    print(f"Error during Stand: {e}")
                    return
            else:
                print(f"[WARNING] Unknown command ignored: '{decision}'")
                print("Invalid input. Please type 'H' or 'S'.")

        round_over = False
        while not round_over:
            try:
                data = recv_all(conn, PAYLOAD_SIZE)
                if not data: return
                _, result, rank, suit = protocol.unpack_payload(data)
                
                if result == protocol.RESULT_NOT_OVER:
                    print(f"Dealer drew: {get_card_str(rank, suit)}")
                else:
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
        print(f"\nGame Over. Played: {played}, Wins: {wins}, Win Rate: {win_rate:.1f}%")