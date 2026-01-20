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

# Separate timeouts:
REQUEST_TIMEOUT = 5.0      # only for reading the initial request packet
GAMEPLAY_TIMEOUT = 60.0    # allow user time to think/type during rounds

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


def recv_exact(conn: socket.socket, size: int):
    data = b""
    while len(data) < size:
        try:
            chunk = conn.recv(size - len(data))
        except socket.timeout:
            return None
        if not chunk:
            return None
        data += chunk
    return data


def get_local_ip():
    ip = "127.0.0.1"
    try:
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)
        for entry in addr_info:
            candidate = entry[4][0]
            if not candidate.startswith("127."):
                ip = candidate
                break
    except OSError:
        pass
    return ip

# =========================
# TCP Client Handler
# =========================
def handle_client(conn: socket.socket, addr):
    try:
        # 1) Timeout only for receiving the initial request
        conn.settimeout(REQUEST_TIMEOUT)
        data = recv_exact(conn, 39)
        if not data:
            print(f"[TCP] No request received from {addr} (timeout/disconnect).")
            return
        data = data.rstrip(b"\n")
        if len(data) > 38:
            data = data[:38]
        rounds, client_name = unpack_request(data)
        print(f"[TCP] Client {addr} -> name='{client_name}', rounds={rounds}")

        # 2) Gameplay timeout should be long enough for human input
        conn.settimeout(GAMEPLAY_TIMEOUT)

        # Run the game
        blackjack.play_game(conn, rounds)

        print(f"[TCP] Finished game with {client_name}")

    except socket.timeout:
        print(f"[TCP] Timeout from {addr} (request or gameplay).")
    except Exception as e:
        print(f"[TCP] Error from {addr}: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass

# =========================
# Main
# =========================
def main():
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.bind(("", 0))
    tcp_socket.listen()

    tcp_port = tcp_socket.getsockname()[1]
    local_ip = get_local_ip()
    print(f"Server started, listening on IP address {local_ip} (port {tcp_port})")

    threading.Thread(
        target=udp_offer_loop,
        args=(tcp_port,),
        daemon=True
    ).start()

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
