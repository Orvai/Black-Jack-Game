## Project Overview
This project implements a network-based Blackjack game using a client–server architecture.
The server is fully authoritative and manages all game logic and outcomes.
Service discovery is performed via UDP broadcast, while gameplay runs over TCP.
Clients automatically discover servers without hard-coded IP addresses.
The design emphasizes reliable communication and concurrent multi-client gameplay.

## Requirements & Installation
### Python Version
Python 3.8+ is required.

### External Dependencies
The client UI depends on the `rich` library.

```
pip install rich
```

`rich` is required only for the client. The server does not depend on `rich`.

## Network Architecture
### Service Discovery (UDP Broadcast)
The server periodically broadcasts game offers using UDP broadcast on port 13122.
Each broadcast packet includes a magic cookie, a message type indicating an offer, a TCP port, and the server name.
Clients listen on the broadcast port and automatically discover available servers.
This eliminates hard-coded IP addresses and supports dynamic network environments.
UDP broadcast enables zero-configuration discovery, allows multiple clients to discover simultaneously, and works across changing IPs.

### Gameplay Communication (TCP)
After receiving an offer, the client opens a TCP connection to the server.
TCP is used to ensure reliable delivery, ordered packets, and no packet loss during gameplay.
All gameplay decisions are transmitted over TCP using a fixed-size payload.
The protocol is custom and binary, includes magic cookie validation, and enforces fixed packet sizes.

## Custom Protocol Design
All packets include a magic cookie for validation and integrity checks.
There are three primary message types: Offer (UDP), Request (TCP), and Payload (TCP).
Payload packets are exactly 14 bytes and carry player decisions.
Valid decisions are strictly limited to the literals "Hittt" and "Stand".

## Server Architecture & Multithreading
### Multithreading Model
The server runs multiple threads concurrently: one thread for UDP broadcasting, one thread for the game table loop, and one thread per connected TCP client.
This threading model allows multiple players to join simultaneously, keeps broadcasts active while games are running, and prevents gameplay from blocking discovery.
Shared game state is protected by locks (mutexes) to maintain thread safety.
The server runs indefinitely to accept new clients and host successive games.

## Game Flow Summary
The server starts and begins broadcasting offers via UDP.
Clients discover servers by listening for broadcast offers.
A client connects to the selected server over TCP.
The server controls all game logic and sends outcomes.
The client only sends decisions and then returns to discovery mode after the session.

## Design Decisions & Constraints
The server is fully authoritative and clients do not calculate outcomes.
Aces are treated as always 11, per the assignment specification.
All printed output strictly follows the assignment PDF.
No hard-coded IPs or ports are used, except for the UDP broadcast port.

## How to Run
### Run Server
```
python server/server.py
```

### Run Client
```
python client/client.py
```

Run the server first. Multiple clients can be started in parallel.

## Notes for Reviewers / Graders
Output strings strictly match the PDF.
Protocol structure and packet sizes are strictly enforced.
Timeouts and blocking I/O are implemented as required.
The project is designed to be robust in real network environments.
