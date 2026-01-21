import socket
import struct
import sys
import common.protocol as protocol 
from . import player
from .ui import BlackjackUI  # וודא שהקוד של ה-UI שמרת בקובץ בשם gui.py בתיקייה הזו

# =========================
# Configuration
# =========================
UDP_PORT = 13122
CLIENT_TEAM_NAME = "Team Israel" 
UDP_OFFER_TIMEOUT = 5.0
TCP_RESPONSE_TIMEOUT = 20.0

def main():
    # יצירת מופע של ה-UI
    ui = BlackjackUI()
    
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
    udp_sock.bind(('', UDP_PORT))
    udp_sock.settimeout(UDP_OFFER_TIMEOUT)
    

    while True:
        try:
            print("\n--- New Game Setup ---")
            try:
                # ה-input כאן עובד כרגיל כי ה-UI עוד לא בסטטוס "start"
                rounds_str = input("Enter number of rounds to play: ")
                num_rounds = int(rounds_str)
            except ValueError:
                print("Invalid input. Using default: 3 rounds.")
                num_rounds = 3

            print(f"Client started, listening for offer requests (will play {num_rounds} rounds)...")

            try:
                data, addr = udp_sock.recvfrom(1024)
            except socket.timeout:
                print("No offers received, continuing to listen...")
                continue
            
            server_ip = addr[0]

            try:
                server_port, server_name = protocol.unpack_offer(data)
                print(f"Received offer from {server_name} at {server_ip}")
            except Exception as e:
                print(f"Invalid offer received: {e}")
                continue 

            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tcp_sock.connect((server_ip, server_port))
            except Exception as e:
                print(f"Failed to connect to server: {e}")
                tcp_sock.close()
                continue
            
            tcp_sock.settimeout(TCP_RESPONSE_TIMEOUT)

            try:
                req_packet = protocol.pack_request(num_rounds, CLIENT_TEAM_NAME) + b"\n"                
                tcp_sock.sendall(req_packet)
                
                # --- הפעלת ה-UI המעוצב לפני תחילת הלוגיקה של המשחק ---
                ui.start()
                try:
                    # אנחנו מעבירים את ה-ui כפרמטר ל-player.py
                    player.play_game(tcp_sock, num_rounds, ui)
                finally:
                    # חשוב מאוד: לסגור את ה-UI כדי להחזיר את הטרמינל למצב טקסט רגיל
                    ui.stop()

            except Exception as e:
                print(f"Game session error: {e}")
            finally:
                print("Disconnecting from server...")
                tcp_sock.close()

        except KeyboardInterrupt:
            print("\nExiting client.")
            break

if __name__ == "__main__":
    main()