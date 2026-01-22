import socket
import struct
import sys
import time
import select
import common.protocol as protocol

from . import player
from .ui import BlackjackUI

# =========================
# Configuration
# =========================
UDP_PORT = 13122
CLIENT_TEAM_NAME = "Team Israel"
UDP_OFFER_TIMEOUT = 1.0
TCP_RESPONSE_TIMEOUT = 20.0


def ask_for_rounds() -> int:
    """
    Ask the user for number of rounds.
    Keeps asking until a valid positive integer is provided.
    """
    while True:
        try:
            value = int(input("Enter number of rounds to play: ").strip())
            if value <= 0:
                print("❌ Number of rounds must be a positive integer.")
                continue
            return value
        except ValueError:
            print("❌ Invalid input. Please enter a number (e.g. 3).")


def main():
    ui = BlackjackUI()

    # =========================
    # UDP socket setup
    # =========================
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.bind(("0.0.0.0", UDP_PORT))

    print("\n--- Blackjack Client Started ---")

    while True:
        try:
            # =========================
            # Ask user for new session
            # =========================
            num_rounds = ask_for_rounds()

            print("\nClient started, listening for offer requests...")

            server_ip = None
            server_port = None
            server_name = None

            start_search_time = time.time()
            found_server = False

            # =========================
            # Discovery Phase
            # =========================
            while not found_server:
                udp_sock.settimeout(UDP_OFFER_TIMEOUT)
                try:
                    data, addr = udp_sock.recvfrom(1024)
                    server_port, server_name = protocol.unpack_offer(data)
                    server_ip = addr[0]
                    print(f"Received offer from {server_ip} ({server_name}), connecting...")
                    found_server = True

                except socket.timeout:
                    elapsed = time.time() - start_search_time
                    if elapsed > 7.0:
                        print("Still searching... (type 'm' + Enter for manual IP)")
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if rlist:
                            if sys.stdin.readline().strip().lower() == 'm':
                                server_ip = input("Enter server IP: ").strip()
                                server_port = int(input("Enter server port: ").strip())
                                found_server = True
                    continue

                except Exception:
                    continue

            # =========================
            # TCP connection & gameplay
            # =========================
            ui.start()
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            try:
                tcp_sock.connect((server_ip, server_port))
                tcp_sock.settimeout(TCP_RESPONSE_TIMEOUT)

                request = protocol.pack_request(num_rounds, CLIENT_TEAM_NAME)
                tcp_sock.sendall(request)

                player.play_game(tcp_sock, num_rounds, ui)

            except Exception as e:
                print(f"Game session error: {e}")
                time.sleep(2)

            finally:
                try:
                    tcp_sock.close()
                except Exception:
                    pass
                ui.stop()
                print("\nGame over. Returning to discovery mode...\n")

        except KeyboardInterrupt:
            print("\nExiting client.")
            break


if __name__ == "__main__":
    main()
