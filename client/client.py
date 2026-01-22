import socket
import struct
import sys
import time
import select # הוספתי בשביל זיהוי קלט מהמקלדת בלי לעצור את התוכנית
import common.protocol as protocol

from . import player
from .ui import BlackjackUI

# =========================
# Configuration
# =========================
UDP_PORT = 13122
CLIENT_TEAM_NAME = "Team Israel"
UDP_OFFER_TIMEOUT = 1.0  # נבדוק כל שנייה
TCP_RESPONSE_TIMEOUT = 20.0

def main():
    ui = BlackjackUI()

    # =========================
    # UDP socket setup (תיקונים למק)
    # =========================
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # מאפשר קבלת חבילות ברודקאסט
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # שימוש ב-0.0.0.0 עוזר בדרך כלל ב-Mac לקלוט ברודקאסט מכל הממשקים
    udp_sock.bind(("0.0.0.0", UDP_PORT))

    print(f"\n--- Blackjack Client Started ---")
    try:
        num_rounds = int(input("Enter number of rounds to play: "))
    except ValueError:
        num_rounds = 3

    while True:
        try:
            print("\nClient started, listening for offer requests...")
            
            server_ip = None
            server_port = None
            server_name = None
            
            start_search_time = time.time()
            found_server = False

            # =========================
            # Discovery Phase (Automatic with Manual Fallback)
            # =========================
            while not found_server:
                # בדיקה אם הגיע UDP
                udp_sock.settimeout(UDP_OFFER_TIMEOUT)
                try:
                    data, addr = udp_sock.recvfrom(1024)
                    # כאן המקום לוודא Magic Cookie בתוך unpack_offer
                    server_port, server_name = protocol.unpack_offer(data)
                    server_ip = addr[0]
                    print(f"Received offer from {server_ip} ({server_name}), connecting...")
                    found_server = True
                except socket.timeout:
                    # אם עבר זמן ועדיין מחפשים
                    elapsed = time.time() - start_search_time
                    if elapsed > 7.0: # אחרי 7 שניות נציע מעבר לידני
                        print(f"Still searching... (To enter IP manually, type 'm' and press Enter, or just wait)")
                        
                        # בדיקה אם המשתמש הקיש משהו במקלדת בלי לעצור את הלופ
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if rlist:
                            choice = sys.stdin.readline().strip().lower()
                            if choice == 'm':
                                server_ip = input("Enter server IP: ").strip()
                                server_port = int(input("Enter server port: ").strip())
                                found_server = True
                    continue
                except Exception as e:
                    continue

            # =========================
            # TCP connection & gameplay
            # =========================
            ui.start()
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tcp_sock.connect((server_ip, server_port))
                tcp_sock.settimeout(TCP_RESPONSE_TIMEOUT)

                # שליחת הבקשה לפי הפרוטוקול
                request = protocol.pack_request(num_rounds, CLIENT_TEAM_NAME)
                tcp_sock.sendall(request)

                # הרצת המשחק - וודא ש-play_game מדפיס סטטיסטיקה בסוף
                player.play_game(tcp_sock, num_rounds, ui)

            except Exception as e:
                ui.stop()
                print(f"Game session error: {e}")
                time.sleep(2)
            finally:
                tcp_sock.close()
                ui.stop()
                # הדרישה: חזרה מיידית להאזנה
                print("\nGame over. Returning to discovery mode...")

        except KeyboardInterrupt:
            print("\nExiting client.")
            break

if __name__ == "__main__":
    main()