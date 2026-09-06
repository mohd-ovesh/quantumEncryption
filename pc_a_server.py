# pc_a_server.py

import socket
import threading
import os
import sys
import numpy as np
import datetime

from e91.quantum_engine import QuantumEngine
from e91.key_generator  import KeyGenerator
from e91.encryptor      import QuantumEncryptor
from utils.logger import QuantumLogger

from utils.image_transfer import send_image, receive_image, SUPPORTED_TYPES
from utils.protocol import (
    send_message, receive_message, hash_key,
    MSG_BASIS_COMPARE, MSG_CHSH_RESULT, MSG_KEY_HASH,
    MSG_READY, MSG_CHAT, MSG_ABORT, MSG_ERROR_RATE,
    MSG_IMAGE_HEADER, MSG_IMAGE_CHUNK, MSG_IMAGE_DONE, MSG_IMAGE_ACK
)

# ── Globals ────────────────────────────────────────────────────────────────
encryptor   : QuantumEncryptor = None
logger      : QuantumLogger    = None
conn_sock   : socket.socket    = None
chat_active                    = False
my_name     : str              = "Alice"   # default, overwritten at runtime
peer_name   : str              = "Bob"     # received from peer

# ── UI ─────────────────────────────────────────────────────────────────────

def clear_line():
    sys.stdout.write('\r' + ' ' * 80 + '\r')
    sys.stdout.flush()

def print_received(sender: str, message: str):
    """Print an incoming message cleanly."""
    clear_line()
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{ts}] 📨 {sender}: {message}")
    if chat_active:
        # Re-print input prompt
        print(f"  {my_name} ▶ ", end='', flush=True)

# ── E91 Key Exchange ────────────────────────────────────────────────────────

def perform_e91_key_exchange(conn):
    global logger, peer_name

    print("\n" + "═"*62)
    print(f"       E91 QUANTUM KEY EXCHANGE  —  {my_name.upper()}")
    print("═"*62)

    engine    = QuantumEngine()
    num_pairs = 300

    # ── Step 1: Exchange names with Bob ────────────────────────────
    # Alice sends her name, receives Bob's name
    print(f"\n  💬 Exchanging names with peer...")
    send_message(conn, 'NAME_EXCHANGE', {'name': my_name})
    msg       = receive_message(conn)
    peer_name = msg['payload']['name']
    print(f"  ✅ Connected to: {peer_name}")

    # ── Step 2: Alice picks random bases ───────────────────────────
    print(f"\n  📡 [1/7] Choosing {num_pairs} random measurement bases...")
    alice_bases = [int(np.random.randint(0, 3)) for _ in range(num_pairs)]
    print(f"  ✅ Sample: {alice_bases[:12]}...")

    # ── Step 3: Exchange bases with Bob ────────────────────────────
    print(f"\n  📤 [2/7] Sending bases to {peer_name}...")
    send_message(conn, MSG_BASIS_COMPARE, {
        'alice_bases': alice_bases,
        'num_pairs'  : num_pairs
    })

    print(f"\n  📥 [3/7] Receiving {peer_name}'s bases...")
    msg       = receive_message(conn)
    bob_bases = msg['payload']['bob_bases']
    print(f"  ✅ Sample: {bob_bases[:12]}...")

    # ── Step 4: Simulate Bell pairs ─────────────────────────────────
    print(f"\n  ⚛️  [4/7] Simulating {num_pairs} entangled Bell pairs...")
    results = engine.generate_all_measurements(num_pairs, alice_bases, bob_bases)

    alice_bits_all = [r['alice_bit'] for r in results]
    bob_bits_all   = [r['bob_bit']   for r in results]

    print(f"\n  📤 [5/7] Sending {peer_name} his measurement results...")
    send_message(conn, 'MEASUREMENT_RESULTS', {
        'bob_bits_all': bob_bits_all
    })

    logger.log_key_exchange('raw_measurements', {
        'num_pairs'  : num_pairs,
        'alice_bases': alice_bases,
        'bob_bases'  : bob_bases,
        'alice_bits' : alice_bits_all,
        'bob_bits'   : bob_bits_all
    })

    # ── Step 5: CHSH Security Test ──────────────────────────────────
    print(f"\n  🔒 [6/7] Running CHSH inequality test...")
    chsh = engine.compute_chsh_value(results)

    _print_chsh(chsh)
    logger.log_chsh_result(chsh)

    send_message(conn, MSG_CHSH_RESULT, {
        'S_value'   : chsh['S_value'],
        'is_secure' : chsh['is_secure'],
        'E_a0b0'    : chsh['E_a0b0'],
        'E_a0b1'    : chsh['E_a0b1'],
        'E_a1b0'    : chsh['E_a1b0'],
        'E_a1b1'    : chsh['E_a1b1'],
    })

    if not chsh['is_secure']:
        logger.log_security_event('CHSH_FAIL', f"S={chsh['S_value']:.4f}", 'CRITICAL')
        send_message(conn, MSG_ABORT, {'reason': 'CHSH failed — S ≤ 2.0'})
        return None

    logger.log_security_event('CHSH_PASS', f"S={chsh['S_value']:.4f}", 'INFO')

    # ── Step 6: Extract key bits ────────────────────────────────────
    print(f"\n  🔑 [7/7] Extracting key bits & generating shared key...")
    key_data = engine.extract_key_bits(results)

    alice_key_bits = key_data['alice_bits']
    n_key          = key_data['key_length']

    print(f"\n  📊 Key statistics:")
    print(f"     Matching-basis pairs : {n_key}")
    print(f"     CHSH test pairs      : {len(key_data['chsh_indices'])}")

    if n_key < 8:
        print(f"\n  ❌ Not enough key bits ({n_key}). Aborting.")
        send_message(conn, MSG_ABORT, {'reason': f'Only {n_key} key bits'})
        return None

    logger.log_measurements(results, key_data['used_indices'], key_data['chsh_indices'])
    logger.log_key_exchange('key_sifting', {
        'total_pairs'   : num_pairs,
        'key_bits'      : n_key,
        'chsh_bits'     : len(key_data['chsh_indices']),
        'alice_key_bits': alice_key_bits
    })

    # Privacy amplification
    kg        = KeyGenerator()
    final_key = kg.privacy_amplification(alice_key_bits, target_bytes=16)

    logger.log_key_exchange('final_key', {
        'key_hex'    : final_key.hex(),
        'key_bits'   : 128,
        'source_bits': n_key
    })

    # Send Bob alice_key_bits so he derives same key
    send_message(conn, MSG_ERROR_RATE, {
        'alice_key_bits': alice_key_bits,
        'n_key_bits'    : n_key,
        'chsh_s_value'  : chsh['S_value'],
        'status'        : 'secure'
    })

    # ── Key verification ────────────────────────────────────────────
    print(f"\n  🤝 Verifying key match with {peer_name}...")
    our_hash = hash_key(final_key)
    send_message(conn, MSG_KEY_HASH, {'key_hash': our_hash})

    msg          = receive_message(conn)
    bob_key_hash = msg['payload']['key_hash']

    if our_hash == bob_key_hash:
        print(f"\n  🎉 Keys MATCH! Channel secured.")
        print(f"     Key: {final_key.hex()}")
        logger.log_security_event('KEY_MATCH', 'Identical keys confirmed', 'INFO')
    else:
        print(f"\n  ❌ Keys DO NOT match!")
        logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
        send_message(conn, MSG_ABORT, {'reason': 'Key mismatch'})
        return None

    send_message(conn, MSG_READY, {'status': 'ready'})
    receive_message(conn)

    return QuantumEncryptor(final_key)

# ── CHSH Display ────────────────────────────────────────────────────────────

def _print_chsh(chsh: dict):
    s  = chsh['S_value']
    q  = chsh['quantum_bound']
    ok = chsh['is_secure']
    print(f"\n  ┌─── CHSH Results ─────────────────────────────────────────┐")
    print(f"  │  E( 0°, 22.5°)  = {chsh['E_a0b0']:+.4f}   theory = -0.7071       │")
    print(f"  │  E( 0°, 67.5°)  = {chsh['E_a0b1']:+.4f}   theory = +0.7071       │")
    print(f"  │  E(45°, 22.5°)  = {chsh['E_a1b0']:+.4f}   theory = -0.7071       │")
    print(f"  │  E(45°, 67.5°)  = {chsh['E_a1b1']:+.4f}   theory = -0.7071       │")
    print(f"  ├──────────────────────────────────────────────────────────┤")
    print(f"  │  S = {s:.4f}   classical ≤ 2.0   quantum ≤ {q:.4f}       │")
    print(f"  │  {'✅ SECURE — entanglement confirmed' if ok else '❌ INSECURE — eavesdropping suspected'}                      │")
    print(f"  └──────────────────────────────────────────────────────────┘")

# ── Receive Thread ──────────────────────────────────────────────────────────

def receive_loop(conn):
    global encryptor, logger, chat_active, peer_name

    while True:
        try:
            msg = receive_message(conn)

            # ── Text message ───────────────────────────────────────
            if msg['type'] == MSG_CHAT:
                enc_data  = bytes(msg['payload']['data'])
                plaintext = encryptor.decrypt(enc_data)
                print_received(peer_name, plaintext)
                logger.log_chat_message(
                    direction     = 'RECEIVED',
                    plaintext     = plaintext,
                    encrypted_hex = enc_data.hex(),
                    msg_len       = len(enc_data)
                )

            # ── Image incoming ─────────────────────────────────────
            elif msg['type'] == MSG_IMAGE_HEADER:
                header    = msg['payload']
                sender    = header.get('sender', peer_name)

                print(f"\n  📸 {sender} is sending you an image...")

                saved_path = receive_image(
                    sock      = conn,
                    encryptor = encryptor,
                    header    = header,
                    my_name   = my_name,
                    logger    = logger
                )

                if saved_path:
                    print(f"\n  ✅ Image saved: {saved_path}")
                else:
                    print(f"\n  ❌ Image transfer failed")

                # Re-print input prompt
                if chat_active:
                    print(f"  {my_name} ▶ ", end='', flush=True)

            # ── Disconnect ─────────────────────────────────────────
            elif msg['type'] == MSG_ABORT:
                clear_line()
                print(f"\n\n  [{peer_name} has disconnected]")
                logger.log_security_event('PEER_DISCONNECT', f'{peer_name} left', 'INFO')
                logger.save_session_summary()
                os._exit(0)

        except Exception as e:
            clear_line()
            print(f"\n\n  [Connection lost: {e}]")
            if logger:
                logger.save_session_summary()
            os._exit(0)

def _print_help():
    print(f"\n  ┌─── Commands ────────────────────────────────────┐")
    print(f"  │  /img <path>  → send an image file             │")
    print(f"  │  status       → show session statistics        │")
    print(f"  │  help         → show this help                 │")
    print(f"  │  exit         → disconnect and quit            │")
    print(f"  │                                                 │")
    print(f"  │  Supported image types:                        │")
    print(f"  │  PNG, JPG, JPEG, GIF, BMP, WEBP               │")
    print(f"  │                                                 │")
    print(f"  │  Example:                                       │")
    print(f"  │  /img ~/Desktop/photo.jpg                      │")
    print(f"  │  /img /Users/me/images/test.png                │")
    print(f"  └─────────────────────────────────────────────────┘\n")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    global encryptor, logger, conn_sock, chat_active, my_name

    # ── Ask for user's name ─────────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║    Quantum Encrypted Chat  (SERVER)      ║")
    print("║    Protocol: E91 (Bell Entanglement)     ║")
    print("╚══════════════════════════════════════════╝")

    while True:
        name = input("\n  Enter your name: ").strip()
        if name:
            my_name = name
            break
        print("  ⚠️  Name cannot be empty.")

    logger = QuantumLogger(role=my_name.lower())

    print(f"\n  Hello, {my_name}! Starting server...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 12346))
    server.listen(1)
    print(f"  Listening on port 12346... waiting for peer.")

    conn, addr = server.accept()
    conn_sock  = conn
    print(f"  ✅ Peer connected from {addr[0]}:{addr[1]}")
    logger.log_security_event('CONNECTION', f"Peer from {addr[0]}:{addr[1]}", 'INFO')

    encryptor = perform_e91_key_exchange(conn)

    if encryptor is None:
        print("\n  ❌ Key exchange failed.")
        logger.save_session_summary()
        conn.close()
        server.close()
        return

    chat_active = True
    recv_thread = threading.Thread(target=receive_loop, args=(conn,))
    recv_thread.daemon = True
    recv_thread.start()

    print("\n" + "═"*62)
    print(f"  🔐 SECURE QUANTUM CHANNEL ESTABLISHED!")
    print(f"  Chatting as : {my_name}")
    print(f"  Peer        : {peer_name}")
    print(f"  Commands    : 'exit' to quit | 'status' for stats")
    print("═"*62 + "\n")

    # ── Send Loop ───────────────────────────────────────────────────
    while True:
        try:
            print(f"  {my_name} ▶ ", end='', flush=True)
            message = input()

            # Exit
            if message.lower() == 'exit':
                send_message(conn, MSG_ABORT, {'reason': 'User quit'})
                break

            # Status
            if message.lower() == 'status':
                _print_status()
                continue

            # Help
            if message.lower() == 'help':
                _print_help()
                continue

            # ── Send image command ──────────────────────────────────
            # Usage: /img /path/to/photo.jpg
            if message.lower().startswith('/img '):
                file_path = message[5:].strip()

                # Handle quoted paths and ~ expansion
                file_path = file_path.strip('"').strip("'")
                file_path = os.path.expanduser(file_path)

                success = send_image(
                    sock        = conn,
                    encryptor   = encryptor,
                    file_path   = file_path,
                    sender_name = my_name,
                    logger      = logger
                )

                if success:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"  [{ts}] 📸 Image sent successfully")
                continue

            # Skip empty
            if not message.strip():
                continue

            # ── Regular text message ────────────────────────────────
            enc = encryptor.encrypt(message)
            send_message(conn, MSG_CHAT, {'data': list(enc)})
            ts  = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"  [{ts}] 📤 Sent ({len(enc)} bytes encrypted)")
            logger.log_chat_message('SENT', message, enc.hex(), len(enc))

        except KeyboardInterrupt:
            send_message(conn, MSG_ABORT, {'reason': 'Interrupted'})
            break
        except Exception as e:
            print(f"\n  [Error: {e}]")
            break

    chat_active = False
    logger.save_session_summary()
    conn.close()
    server.close()
    print(f"\n  Goodbye, {my_name}!")

def _print_status():
    s = logger.session_data
    print(f"\n  ┌─── Session Status ──────────────────────────┐")
    print(f"  │  Your name : {my_name:<30}│")
    print(f"  │  Peer name : {peer_name:<30}│")
    print(f"  │  Sent      : {s['chat_stats']['messages_sent']:<30}│")
    print(f"  │  Received  : {s['chat_stats']['messages_received']:<30}│")
    if s.get('chsh'):
        ok = '✅ YES' if s['chsh'].get('is_secure') else '❌ NO'
        print(f"  │  S-value   : {s['chsh'].get('S_value', 0):<30.4f}│")
        print(f"  │  Secure    : {ok:<30}│")
    print(f"  └─────────────────────────────────────────────┘\n")

if __name__ == '__main__':
    main()