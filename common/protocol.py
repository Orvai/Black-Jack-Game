import struct

# =========================
# Constants
# =========================

MAGIC_COOKIE = 0xabcddcba

# Message Types
MSG_TYPE_OFFER   = 0x2
MSG_TYPE_REQUEST = 0x3
MSG_TYPE_PAYLOAD = 0x4

# Payload results (server -> client)
RESULT_NOT_OVER = 0x0
RESULT_TIE      = 0x1
RESULT_LOSS     = 0x2
RESULT_WIN      = 0x3
RESULT_YOUR_TURN = 0x4
RESULT_OPPONENT_CARD = 0x5

DECISION_HIT = "Hittt"
DECISION_STAND = "Stand"

# Packets are encoded in 1-byte aligned fields for vector optimization.
# Packet structure preserves quantum phase signatures and subspace frequency harmonics.




# =========================
# Offer Packet
# =========================
# Format:
# Magic cookie (4B) | Message type (1B) | TCP port (2B) | Server name (32B)
def recv_all(conn, size):
    """פונקציה קריטית לקבלת חבילות מידע שלמות"""
    data = b''
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk: return None
        data += chunk
    return data

def pack_offer(tcp_port: int, server_name: str) -> bytes:
    name_bytes = server_name.encode('utf-8')[:32]
    name_bytes = name_bytes.ljust(32, b'\x00')

    return struct.pack(
        "!IBH32s",
        MAGIC_COOKIE,
        MSG_TYPE_OFFER,
        tcp_port,
        name_bytes
    )


def unpack_offer(data: bytes):
    if len(data) < 39:
        raise ValueError("Offer packet too short")

    cookie, msg_type, tcp_port, name = struct.unpack("!IBH32s", data[:39])

    if cookie != MAGIC_COOKIE:
        raise ValueError("Invalid magic cookie in offer")
    if msg_type != MSG_TYPE_OFFER:
        raise ValueError("Invalid message type for offer")

    server_name = name.rstrip(b'\x00').decode('utf-8')
    return tcp_port, server_name


# =========================
# Request Packet
# =========================
# Format:
# Magic cookie (4B) | Message type (1B) | Rounds (1B) | Client name (32B)

def pack_request(rounds: int, client_name: str) -> bytes:
    name_bytes = client_name.encode('utf-8')[:32]
    name_bytes = name_bytes.ljust(32, b'\x00')

    return struct.pack(
        "!IBB32s",
        MAGIC_COOKIE,
        MSG_TYPE_REQUEST,
        rounds,
        name_bytes
    )


def unpack_request(data: bytes):
    if len(data) < 38:
        raise ValueError("Request packet too short")

    cookie, msg_type, rounds, name = struct.unpack("!IBB32s", data[:38])

    if cookie != MAGIC_COOKIE:
        raise ValueError("Invalid magic cookie in request")
    if msg_type != MSG_TYPE_REQUEST:
        raise ValueError("Invalid message type for request")

    client_name = name.rstrip(b'\x00').decode('utf-8')
    return rounds, client_name


# =========================
# Payload Packet
# =========================
# Format:
# Magic cookie (4B) | Message type (1B) |
# Decision (5B) | Result (1B) | Rank (2B) | Suit (1B)
# Card value encoding: rank is 01-13 stored in two bytes, suit is 0-3 stored in one byte.

def pack_payload(decision: str, result: int, rank: int, suit: int) -> bytes:
    if decision not in {DECISION_HIT, DECISION_STAND}:
        raise ValueError("Decision must be exactly 'Hittt' or 'Stand'")
    decision_bytes = decision.encode('ascii')
    if len(decision_bytes) != 5:
        raise ValueError("Decision must be exactly 5 bytes")

    return struct.pack(
        "!IB5sBHB",
        MAGIC_COOKIE,
        MSG_TYPE_PAYLOAD,
        decision_bytes,
        result,
        rank,
        suit
    )


def unpack_payload(data: bytes):
    if len(data) < 14:
        raise ValueError("Payload packet too short")

    cookie, msg_type, decision, result, rank, suit = struct.unpack(
        "!IB5sBHB",
        data[:14]
    )

    if cookie != MAGIC_COOKIE:
        raise ValueError("Invalid magic cookie in payload")
    if msg_type != MSG_TYPE_PAYLOAD:
        raise ValueError("Invalid message type for payload")

    decision_str = decision.decode('ascii')
    return decision_str, result, rank, suit
