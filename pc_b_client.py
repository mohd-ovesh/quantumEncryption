# pc_b_client.py

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
chat_active                    = False
my_name     : str              = "Bob"     # default, overwritten at runtime
peer_name   : str              = "Alice"   # received from peer

# ── UI ─────────────────────────────────────────────────────────────────────

def clear_line():
    sys.stdout.write('\r' + ' ' * 80 + '\r')
    sys.stdout.flush()

def print_received(sender: str, message: str):
    clear_line()
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{ts}] 📨 {sender}: {message}")
    if chat_active:
        print(f"  {my_name} ▶ ", end='', flush=True)

# ── Safe receive helper ─────────────────────────────────────────────────────

def recv_or_abort(sock, step_name: str):
    msg = receive_message(sock)
    if msg['type'] == MSG_ABORT:
        reason = msg['payload'].get('reason', 'Unknown')
        print(f"\n  ❌ [{step_name}] Peer aborted: {reason}")
        logger.log_security_event('PEER_ABORT', f"{step_name}: {reason}", 'CRITICAL')
        return None
    return msg

# ── E91 Key Exchange ────────────────────────────────────────────────────────

def perform_e91_key_exchange(sock):
    global logger, peer_name

    print("\n" + "═"*62)
    print(f"        E91 QUANTUM KEY EXCHANGE  —  {my_name.upper()}")
    print("═"*62)

    engine = QuantumEngine()

    # ── Step 1: Exchange names ──────────────────────────────────────
    # Bob receives Alice's name first, then sends his own
    print(f"\n  💬 Exchanging names with peer...")
    msg       = receive_message(sock)
    peer_name = msg['payload']['name']
    send_message(sock, 'NAME_EXCHANGE', {'name': my_name})
    print(f"  ✅ Connected to: {peer_name}")

    # ── Step 2: Receive peer's bases ────────────────────────────────
    print(f"\n  📥 [1/7] Receiving {peer_name}'s basis choices...")
    msg = recv_or_abort(sock, 'Step 1 bases')
    if msg is None:
        return None

    alice_bases = msg['payload']['alice_bases']
    num_pairs   = msg['payload']['num_pairs']
    print(f"  ✅ Received {len(alice_bases)} bases: {alice_bases[:12]}...")

    # ── Step 3: Bob picks random bases ──────────────────────────────
    print(f"\n  📡 [2/7] Choosing {num_pairs} random bases...")
    bob_bases = [int(np.random.randint(0, 3)) for _ in range(num_pairs)]
    print(f"  ✅ My bases: {bob_bases[:12]}...")

    # ── Step 4: Send bases to peer ──────────────────────────────────
    print(f"\n  📤 [3/7] Sending bases to {peer_name}...")
    send_message(sock, MSG_BASIS_COMPARE, {'bob_bases': bob_bases})
    logger.log_key_exchange('basis_choices', {
        'alice_bases': alice_bases,
        'bob_bases'  : bob_bases,
        'num_pairs'  : num_pairs
    })

    # ── Step 5: Receive qubit results ───────────────────────────────
    print(f"\n  📥 [4/7] Receiving qubit measurement results...")
    msg = recv_or_abort(sock, 'Step 4 measurements')
    if msg is None:
        return None

    bob_bits_all = msg['payload']['bob_bits_all']
    print(f"  ✅ Received {len(bob_bits_all)} measurement results")

    # ── Step 6: CHSH result ─────────────────────────────────────────
    print(f"\n  🔒 [5/7] Receiving CHSH security result...")
    msg = recv_or_abort(sock, 'Step 5 CHSH')
    if msg is None:
        return None

    chsh = msg['payload']
    _print_chsh_peer(chsh)

    logger.log_chsh_result({
        'S_value'      : chsh['S_value'],
        'E_00'         : chsh.get('E_a0b0', 0),
        'E_02'         : chsh.get('E_a0b1', 0),
        'E_20'         : chsh.get('E_a1b0', 0),
        'E_22'         : chsh.get('E_a1b1', 0),
        'is_secure'    : chsh['is_secure'],
        'quantum_bound': 2 * np.sqrt(2)
    })

    if not chsh['is_secure']:
        try:
            receive_message(sock)   # consume MSG_ABORT
        except Exception:
            pass
        logger.log_security_event('CHSH_FAIL', f"S={chsh['S_value']:.4f}", 'CRITICAL')
        print(f"\n  ❌ Channel not secure!")
        return None

    logger.log_security_event('CHSH_PASS', f"S={chsh['S_value']:.4f}", 'INFO')

    # ── Step 7: Log matching pairs ──────────────────────────────────
    print(f"\n  🔑 [6/7] Identifying matching-basis pairs...")
    combined = []
    for i in range(num_pairs):
        combined.append({
            'alice_angle_idx' : alice_bases[i],
            'bob_angle_idx'   : bob_bases[i],
            'alice_bit'       : 0,
            'bob_bit'         : bob_bits_all[i],
            'alice_angle_deg' : round(np.degrees(engine.alice_angles[alice_bases[i]]), 2),
            'bob_angle_deg'   : round(np.degrees(engine.bob_angles[bob_bases[i]]),   2)
        })

    key_data = engine.extract_key_bits(combined)
    print(f"  ✅ {key_data['key_length']} matching-basis pairs found")
    logger.log_measurements(combined, key_data['used_indices'], key_data['chsh_indices'])

    # ── Step 8: Receive key material ────────────────────────────────
    print(f"\n  🧮 [7/7] Receiving key bits from {peer_name}...")
    msg = recv_or_abort(sock, 'Step 7 key material')
    if msg is None:
        return None

    payload        = msg['payload']
    alice_key_bits = payload['alice_key_bits']
    n_key_bits     = payload['n_key_bits']
    chsh_s         = payload['chsh_s_value']

    print(f"\n  📊 Key generation summary:")
    print(f"     Matching-basis pairs : {n_key_bits}")
    print(f"     Key bits received    : {len(alice_key_bits)}")
    print(f"     CHSH S-value         : {chsh_s:.4f}")

    if len(alice_key_bits) < 8:
        print(f"\n  ❌ Not enough key bits ({len(alice_key_bits)})")
        return None

    # Generate key — SHA-256(alice_key_bits) → same as peer's key
    kg        = KeyGenerator()
    final_key = kg.privacy_amplification(alice_key_bits, target_bytes=16)

    logger.log_key_exchange('final_key', {
        'key_hex'    : final_key.hex(),
        'key_bits'   : 128,
        'source_bits': len(alice_key_bits)
    })

    # ── Key verification ─────────────────────────────────────────────
    print(f"\n  🤝 Verifying key match with {peer_name}...")
    msg = recv_or_abort(sock, 'Key hash verification')
    if msg is None:
        return None

    peer_key_hash = msg['payload']['key_hash']
    our_hash      = hash_key(final_key)
    send_message(sock, MSG_KEY_HASH, {'key_hash': our_hash})

    if our_hash == peer_key_hash:
        print(f"\n  🎉 Keys MATCH! Quantum-secured channel established.")
        print(f"     Key: {final_key.hex()}")
        logger.log_security_event('KEY_MATCH', 'Identical keys confirmed', 'INFO')
    else:
        print(f"\n  ❌ Keys DO NOT match!")
        logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
        return None

    receive_message(sock)                               # peer's MSG_READY
    send_message(sock, MSG_READY, {'status': 'ready'})

    return QuantumEncryptor(final_key)

# ── CHSH Display ────────────────────────────────────────────────────────────

def _print_chsh_peer(chsh: dict):
    E00 = chsh.get('E_a0b0', 0)
    E01 = chsh.get('E_a0b1', 0)
    E10 = chsh.get('E_a1b0', 0)
    E11 = chsh.get('E_a1b1', 0)
    s   = chsh['S_value']
    ok  = chsh['is_secure']
    q   = 2 * np.sqrt(2)

    print(f"\n  ┌─── CHSH Verification ─────────────────────────────────────┐")
    print(f"  │  E( 0°, 22.5°)  = {E00:+.4f}   theory = -0.7071           │")
    print(f"  │  E( 0°, 67.5°)  = {E01:+.4f}   theory = +0.7071           │")
    print(f"  │  E(45°, 22.5°)  = {E10:+.4f}   theory = -0.7071           │")
    print(f"  │  E(45°, 67.5°)  = {E11:+.4f}   theory = -0.7071           │")
    print(f"  ├───────────────────────────────────────────────────────────┤")
    print(f"  │  S = {s:.4f}   classical ≤ 2.0   quantum ≤ {q:.4f}       │")
    print(f"  │  {'✅ SECURE — quantum correlations confirmed' if ok else '❌ INSECURE — classical correlations'}               │")
    print(f"  └───────────────────────────────────────────────────────────┘")

# ── Receive Thread ──────────────────────────────────────────────────────────

def receive_loop(sock):
    global encryptor, logger, chat_active, peer_name

    while True:
        try:
            msg = receive_message(sock)

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

            elif msg['type'] == MSG_IMAGE_HEADER:
                header = msg['payload']
                sender = header.get('sender', peer_name)

                print(f"\n  📸 {sender} is sending you an image...")

                saved_path = receive_image(
                    sock      = sock,
                    encryptor = encryptor,
                    header    = header,
                    my_name   = my_name,
                    logger    = logger
                )

                if saved_path:
                    print(f"\n  ✅ Image saved: {saved_path}")
                else:
                    print(f"\n  ❌ Image transfer failed")

                if chat_active:
                    print(f"  {my_name} ▶ ", end='', flush=True)

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
    print(f"  └─────────────────────────────────────────────────┘\n")

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    global encryptor, logger, chat_active, my_name

    SERVER_IP = '192.168.29.162'   # ← Change to server PC's IP

    # ── Ask for user's name ─────────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║    Quantum Encrypted Chat  (CLIENT)      ║")
    print("║    Protocol: E91 (Bell Entanglement)     ║")
    print("╚══════════════════════════════════════════╝")

    while True:
        name = input("\n  Enter your name: ").strip()
        if name:
            my_name = name
            break
        print("  ⚠️  Name cannot be empty.")

    logger = QuantumLogger(role=my_name.lower())

    print(f"\n  Hello, {my_name}! Connecting to {SERVER_IP}:12346 ...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, 12346))
    print(f"  ✅ Connected!")
    logger.log_security_event('CONNECTION', f"Connected to {SERVER_IP}", 'INFO')

    encryptor = perform_e91_key_exchange(sock)

    if encryptor is None:
        print("\n  ❌ Key exchange failed.")
        logger.save_session_summary()
        sock.close()
        return

    chat_active = True
    recv_thread = threading.Thread(target=receive_loop, args=(sock,))
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

            if message.lower() == 'exit':
                send_message(sock, MSG_ABORT, {'reason': 'User quit'})
                break

            if message.lower() == 'status':
                _print_status()
                continue

            # Image send command
            if message.lower().startswith('/img '):
                file_path = message[5:].strip()
                file_path = file_path.strip('"').strip("'")
                file_path = os.path.expanduser(file_path)

                success = send_image(
                    sock        = sock,
                    encryptor   = encryptor,
                    file_path   = file_path,
                    sender_name = my_name,
                    logger      = logger
                )

                if success:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"  [{ts}] 📸 Image sent successfully")
                continue

            # Help command
            if message.lower() == 'help':
                _print_help()
                continue

            if not message.strip():
                continue

            enc = encryptor.encrypt(message)
            send_message(sock, MSG_CHAT, {'data': list(enc)})
            ts  = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"  [{ts}] 📤 Sent ({len(enc)} bytes encrypted)")
            logger.log_chat_message('SENT', message, enc.hex(), len(enc))

        except KeyboardInterrupt:
            send_message(sock, MSG_ABORT, {'reason': 'Interrupted'})
            break
        except Exception as e:
            print(f"\n  [Error: {e}]")
            break

    chat_active = False
    logger.save_session_summary()
    sock.close()
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