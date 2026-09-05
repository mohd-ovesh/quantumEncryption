# pc_a_server.py  ← Run on PC-A

import socket
import threading
import os
import sys
import numpy as np
import datetime

from e91.quantum_engine import QuantumEngine
from e91.key_generator  import KeyGenerator
from e91.encryptor      import QuantumEncryptor
from utils.protocol     import (
    send_message, receive_message, hash_key,
    MSG_BASIS_COMPARE, MSG_CHSH_RESULT, MSG_KEY_HASH,
    MSG_READY, MSG_CHAT, MSG_ABORT, MSG_ERROR_RATE
)
from utils.logger import QuantumLogger

# ── Globals ──────────────────────────────────────────────────────────────────
encryptor : QuantumEncryptor = None
logger    : QuantumLogger    = None
conn_sock : socket.socket    = None
chat_active = False

# ── UI Helpers ────────────────────────────────────────────────────────────────

def clear_input_line():
    """Move cursor up and clear line so received messages don't break input."""
    sys.stdout.write('\r' + ' ' * 60 + '\r')
    sys.stdout.flush()

def print_received(sender: str, message: str):
    """Print an incoming message cleanly above the input prompt."""
    clear_input_line()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{now}] 📨 {sender}: {message}")
    # Re-print the input prompt
    if chat_active:
        print("  Alice ▶ ", end='', flush=True)

# ── Key Exchange ──────────────────────────────────────────────────────────────

def perform_e91_key_exchange(conn):
    global logger

    print("\n" + "═"*60)
    print("      E91 QUANTUM KEY EXCHANGE  —  ALICE")
    print("═"*60)

    engine = QuantumEngine()

    # ── 1. Generate measurements ─────────────────────────────────
    print("\n  📡 [1/7] Generating 300 entangled Bell pairs...")
    results = engine.generate_raw_measurements(num_pairs=300)

    # ── 2. Send Alice's data to Bob ──────────────────────────────
    print("\n  📤 [2/7] Sending bases to Bob...")
    alice_bases = [r['alice_angle_idx'] for r in results]
    alice_bits  = [r['alice_bit']       for r in results]

    send_message(conn, MSG_BASIS_COMPARE, {
        'alice_bases': alice_bases,
        'alice_bits' : alice_bits
    })

    logger.log_key_exchange('raw_measurements', {
        'num_pairs'  : len(results),
        'alice_bases': alice_bases,
        'alice_bits' : alice_bits
    })

    # ── 3. Receive Bob's data ─────────────────────────────────────
    print("\n  📥 [3/7] Receiving Bob's bases...")
    msg       = receive_message(conn)
    bob_bases = msg['payload']['bob_bases']
    bob_bits  = msg['payload']['bob_bits']
    print(f"  ✅ Received {len(bob_bases)} basis choices from Bob")

    # ── 4. Build combined results ─────────────────────────────────
    combined = []
    for i, r in enumerate(results):
        combined.append({
            'alice_bit'       : r['alice_bit'],
            'bob_bit'         : bob_bits[i],
            'alice_angle_idx' : r['alice_angle_idx'],
            'bob_angle_idx'   : bob_bases[i],
            'alice_angle_deg' : r['alice_angle_deg'],
            'bob_angle_deg'   : r.get('bob_angle_deg', bob_bases[i] * 45)
        })

    # ── 5. CHSH Security Test ─────────────────────────────────────
    print("\n  🔒 [4/7] Running CHSH inequality test...")
    chsh = engine.compute_chsh_value(combined)

    print(f"\n  ┌─── CHSH Results ──────────────────────────┐")
    print(f"  │  E(0°,   45°) = {chsh['E_00']:+.4f}                    │")
    print(f"  │  E(0°,  135°) = {chsh['E_02']:+.4f}                    │")
    print(f"  │  E(90°,  45°) = {chsh['E_20']:+.4f}                    │")
    print(f"  │  E(90°, 135°) = {chsh['E_22']:+.4f}                    │")
    print(f"  │  S  value     = {chsh['S_value']:.4f}                    │")
    print(f"  │  Quantum max  = {chsh['quantum_bound']:.4f}                    │")
    print(f"  │  Secure?      = {'YES ✅' if chsh['is_secure'] else 'NO  ❌'}                     │")
    print(f"  └────────────────────────────────────────────┘")

    logger.log_chsh_result(chsh)

    send_message(conn, MSG_CHSH_RESULT, {
        'S_value'  : chsh['S_value'],
        'is_secure': chsh['is_secure']
    })

    if not chsh['is_secure']:
        logger.log_security_event('CHSH_FAIL', f"S={chsh['S_value']:.4f} ≤ 2.0", 'CRITICAL')
        send_message(conn, MSG_ABORT, {'reason': 'CHSH failed'})
        return None

    logger.log_security_event('CHSH_PASS', f"S={chsh['S_value']:.4f} > 2.0", 'INFO')

    # ── 6. Extract key bits ───────────────────────────────────────
    print("\n  🔑 [5/7] Extracting key bits from matching bases...")
    key_data = engine.extract_key_bits(combined)
    print(f"  ✅ Found {key_data['key_length']} matching-basis measurements")

    # Log all measurements with classification
    logger.log_measurements(combined, key_data['used_indices'], key_data['chsh_indices'])
    logger.log_key_exchange('basis_sifting', {
        'total_pairs'     : len(combined),
        'key_bits_found'  : key_data['key_length'],
        'chsh_bits_used'  : len(key_data['chsh_indices']),
        'discarded'       : len(combined) - key_data['key_length'] - len(key_data['chsh_indices'])
    })

    # ── 7. Generate key ───────────────────────────────────────────
    print("\n  🧮 [6/7] Generating final quantum key...")
    kg = KeyGenerator()
    kg.sift_key(key_data['alice_bits'], key_data['bob_bits'])

    error_rate = kg.check_error_rate(sample_size=20)
    send_message(conn, MSG_ERROR_RATE, {'error_rate': error_rate})

    logger.log_key_exchange('error_rate', kg.log_data.get('error_check', {}))
    logger.log_security_event(
        'QBER_CHECK',
        f"QBER={error_rate:.2%}",
        'INFO' if error_rate < 0.11 else 'CRITICAL'
    )

    if error_rate >= 0.11:
        logger.log_security_event('QBER_TOO_HIGH', f"QBER={error_rate:.2%} — aborting", 'CRITICAL')
        return None

    final_key = kg.generate_final_key(target_bytes=16)
    if not final_key:
        return None

    logger.log_key_exchange('final_key', {
        'key_hex'     : final_key.hex(),
        'key_bits'    : 128,
        'algorithm'   : 'SHA-256 privacy amplification'
    })

    # ── 8. Verify key match ───────────────────────────────────────
    print("\n  🤝 [7/7] Verifying key match with Bob...")
    our_hash = hash_key(final_key)
    send_message(conn, MSG_KEY_HASH, {'key_hash': our_hash})

    msg          = receive_message(conn)
    bob_key_hash = msg['payload']['key_hash']

    if our_hash == bob_key_hash:
        print(f"\n  🎉 Keys MATCH! Channel is secure.")
        print(f"     Key: {final_key.hex()}")
        logger.log_security_event('KEY_MATCH', 'Alice and Bob share identical key', 'INFO')
    else:
        print(f"\n  ❌ Keys DO NOT match!")
        logger.log_security_event('KEY_MISMATCH', 'Keys differ — aborting', 'CRITICAL')
        return None

    send_message(conn, MSG_READY, {'status': 'ready'})
    receive_message(conn)  # Bob's ready signal

    return QuantumEncryptor(final_key)

# ── Receive Thread ────────────────────────────────────────────────────────────

def receive_loop(conn):
    """
    Runs in background. Handles ALL incoming messages:
    - MSG_CHAT     → decrypt and display
    - MSG_ABORT    → clean shutdown
    """
    global encryptor, logger, chat_active

    while True:
        try:
            msg = receive_message(conn)

            if msg['type'] == MSG_CHAT:
                encrypted_data = bytes(msg['payload']['data'])
                plaintext      = encryptor.decrypt(encrypted_data)
                encrypted_hex  = encrypted_data.hex()

                print_received("Bob", plaintext)

                # Log the received message
                logger.log_chat_message(
                    direction    = 'RECEIVED',
                    plaintext    = plaintext,
                    encrypted_hex= encrypted_hex,
                    msg_len      = len(encrypted_data)
                )

            elif msg['type'] == MSG_ABORT:
                clear_input_line()
                print("\n\n  [Bob has disconnected]")
                logger.log_security_event('PEER_DISCONNECT', 'Bob disconnected', 'INFO')
                logger.save_session_summary()
                os._exit(0)

        except Exception as e:
            clear_input_line()
            print(f"\n\n  [Connection lost: {e}]")
            if logger:
                logger.save_session_summary()
            os._exit(0)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global encryptor, logger, conn_sock, chat_active

    logger = QuantumLogger(role='alice')

    print("\n╔══════════════════════════════════════════╗")
    print("║    Quantum Encrypted Chat  —  ALICE      ║")
    print("║    Protocol: E91 (Bell Entanglement)     ║")
    print("╚══════════════════════════════════════════╝")

    # Setup server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 12345))
    server.listen(1)
    print(f"\n  Listening on port 12345... waiting for Bob.")

    conn, addr = server.accept()
    conn_sock  = conn
    print(f"  ✅ Bob connected from {addr[0]}:{addr[1]}")

    logger.log_security_event('CONNECTION', f"Bob connected from {addr[0]}:{addr[1]}", 'INFO')

    # Quantum key exchange
    encryptor = perform_e91_key_exchange(conn)

    if encryptor is None:
        print("\n  ❌ Key exchange failed. Closing.")
        logger.save_session_summary()
        conn.close()
        server.close()
        return

    # ── Start Chat ────────────────────────────────────────────────
    chat_active = True

    recv_thread        = threading.Thread(target=receive_loop, args=(conn,))
    recv_thread.daemon = True
    recv_thread.start()

    print("\n" + "═"*60)
    print("  🔐 SECURE QUANTUM CHANNEL ESTABLISHED!")
    print("  Type your message and press Enter to send.")
    print("  Type 'exit' to quit.")
    print("  Type 'status' to see session stats.")
    print("═"*60 + "\n")

    # ── Send Loop ─────────────────────────────────────────────────
    while True:
        try:
            print("  Alice ▶ ", end='', flush=True)
            message = input()

            if message.lower() == 'exit':
                send_message(conn, MSG_ABORT, {'reason': 'User quit'})
                break

            if message.lower() == 'status':
                s = logger.session_data
                print(f"\n  ┌─── Session Status ──────────────────────┐")
                print(f"  │  Messages sent    : {s['chat_stats']['messages_sent']:<20}│")
                print(f"  │  Messages received: {s['chat_stats']['messages_received']:<20}│")
                print(f"  │  Bytes sent       : {s['chat_stats']['total_bytes_sent']:<20}│")
                if s.get('chsh'):
                    print(f"  │  CHSH S-value     : {s['chsh'].get('S_value', 0):<20.4f}│")
                print(f"  └─────────────────────────────────────────┘\n")
                continue

            if message.strip() == '':
                continue

            # Encrypt and send
            encrypted = encryptor.encrypt(message)
            send_message(conn, MSG_CHAT, {'data': list(encrypted)})

            # Log sent message
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"  [{now}] 📤 Sent (encrypted)")
            logger.log_chat_message(
                direction    = 'SENT',
                plaintext    = message,
                encrypted_hex= encrypted.hex(),
                msg_len      = len(encrypted)
            )

        except KeyboardInterrupt:
            send_message(conn, MSG_ABORT, {'reason': 'Keyboard interrupt'})
            break
        except Exception as e:
            print(f"\n  [Error: {e}]")
            break

    # Cleanup
    chat_active = False
    logger.save_session_summary()
    conn.close()
    server.close()
    print("\n  Connection closed. Goodbye!")

if __name__ == '__main__':
    main()