# server.py
import socket
import threading
import time
from . import blackjack

from common.protocol import (
    pack_offer,
    unpack_request,
)

# =========================
# Config
# =========================
BROADCAST_PORT = 13122
OFFER_INTERVAL = 1.0
SERVER_NAME = "BlackjackServer"

# =========================
# UDP Offer Thread
# =========================
def udp_offer_loop(tcp_port: int):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    offer_packet = pack_offer(tcp_port, SERVER_NAME)

    while True:
        udp_socket.sendto(offer_packet, ("<broadcast>", BROADCAST_PORT))
        time.sleep(OFFER_INTERVAL)

# =========================
# TCP Client Handler
# =========================
def handle_client(conn: socket.socket, addr):
    try:
        data = conn.recv(1024)
        if not data:
            return
        rounds, client_name = unpack_request(data)
        print(f"[TCP] Client {addr} -> name='{client_name}', rounds={rounds}")
        blackjack.play_game(conn, rounds)
        conn.close()
        print(f"[TCP] Finished game with {client_name}")
    except Exception as e:
        print(f"[TCP] Error from {addr}: {e}")

    finally:
        conn.close()

# =========================
# Main
# =========================
def main():
    # TCP socket
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(("", 0))     
    tcp_socket.listen()

    tcp_port = tcp_socket.getsockname()[1]
    print(f"[SERVER] TCP listening on port {tcp_port}")

    # UDP offer thread
    threading.Thread(
        target=udp_offer_loop,
        args=(tcp_port,),
        daemon=True
    ).start()

    #  Accept loop
    while True:
        conn, addr = tcp_socket.accept()
        print(f"[SERVER] New connection from {addr}")

        threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        ).start()


if __name__ == "__main__":
    main()
