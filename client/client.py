import socket
import struct
import sys
import time
import common.protocol as protocol 
from . import player
from .ui import BlackjackUI 

# =========================
# Configuration
# =========================
UDP_PORT = 13122
CLIENT_TEAM_NAME = "Team Israel" 
UDP_OFFER_TIMEOUT = 0.5  # קיצרנו את ה-Timeout כדי שהאנימציה תרוץ חלק
TCP_RESPONSE_TIMEOUT = 20.0

def main():
    ui = BlackjackUI()
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
    udp_sock.bind(('', UDP_PORT))
    
    while True:
        try:
            # שלב 1: הגדרת כמות סיבובים (בטקסט רגיל)
            print("\n--- New Game Setup ---")
            try:
                rounds_str = input("Enter number of rounds to play: ")
                num_rounds = int(rounds_str)
            except ValueError:
                num_rounds = 3

            # שלב 2: הפעלת ה-UI וחיפוש שרת עם אנימציית ערבוב
            ui.start()
            frame = 0
            server_ip = None
            server_port = None
            server_name = None

            # לולאת המתנה לשרת עם אנימציה
            while True:
                # הצגת אנימציית ערבוב באזור הדילר
                ui.layout["dealer"].update(ui.render_shuffling(frame))
                # עדכון סטטוס בשאר הלוח
                from rich.panel import Panel
                from rich.align import Align
                from rich.text import Text
                ui.layout["opponents"].update(Panel(Align.center(Text("Searching for a table...", style="bold yellow")), border_style="dim"))
                ui.layout["player"].update(Panel(Align.center(Text(f"Listening for offers on port {UDP_PORT}...", style="dim")), title="Lobby"))
                
                ui.live.refresh()
                frame += 1
                
                try:
                    udp_sock.settimeout(UDP_OFFER_TIMEOUT)
                    data, addr = udp_sock.recvfrom(1024)
                    server_ip = addr[0]
                    server_port, server_name = protocol.unpack_offer(data)
                    break # נמצא שרת!
                except socket.timeout:
                    continue # ממשיך לאנימציה הבאה
                except Exception:
                    continue

            # שלב 3: התחברות וניהול המשחק
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tcp_sock.connect((server_ip, server_port))
                tcp_sock.settimeout(TCP_RESPONSE_TIMEOUT)
                
                req_packet = protocol.pack_request(num_rounds, CLIENT_TEAM_NAME) + b"\n"                
                tcp_sock.sendall(req_packet)
                
                # הרצת המשחק (ה-UI כבר רץ, פשוט מעבירים אותו)
                player.play_game(tcp_sock, num_rounds, ui)

            except Exception as e:
                ui.stop() # עוצרים רגע כדי להדפיס שגיאה
                print(f"Game session error: {e}")
                time.sleep(2)
            finally:
                tcp_sock.close()
                ui.stop() # סגירה סופית של ה-UI בסוף המשחק

        except KeyboardInterrupt:
            ui.stop()
            print("\nExiting client.")
            break

if __name__ == "__main__":
    main()