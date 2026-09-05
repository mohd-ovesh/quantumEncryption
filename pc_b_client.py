# pc_b_client.py  ← Run on PC-B

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
encryptor   : QuantumEncryptor = None
logger      : QuantumLogger    = None
chat_active                    = False

# ── UI Helpers ────────────────────────────────────────────────────────────────

def clear_input_line():
    sys.stdout.write('\r' + ' ' * 60 + '\r')
    sys.stdout.flush()

def print_received(sender: str, message: str):
    clear_input_line()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{now}] 📨 {sender}: {message}")
    if chat_active:
        print("  Bob   ▶ ", end='', flush=True)

# ── Key Exchange ──────────────────────────────────────────────────────────────

def perform_e91_key_exchange(sock):
    global logger

    print("\n" + "═"*60)
    print("      E91 QUANTUM KEY EXCHANGE  —  BOB")
    print("═"*60)

    engine    = QuantumEngine()
    num_pairs = 300

    # ── 1. Bob prepares his random basis choices ──────────────────
    print("\n  📡 [1/7] Preparing Bob's random measurement bases...")
    bob_bases = [np.random.randint(0, 3) for _ in range(num_pairs)]

    # ── 2. Receive Alice's bases and bits ─────────────────────────
    print("\n  📥 [2/7] Receiving Alice's measurement data...")
    msg         = receive_message(sock)
    alice_bases = msg['payload']['alice_bases']
    alice_bits  = msg['payload']['alice_bits']
    print(f"  ✅ Received {len(alice_bases)} measurements from Alice")

    logger.log_key_exchange('raw_measurements', {
        'num_pairs' : num_pairs,
        'bob_bases' : bob_bases
    })

    # ── 3. Simulate Bob's quantum measurements ────────────────────
    print("\n  🔬 [3/7] Simulating Bob's qubit measurements...")
    bob_bits = []

    for i in range(len(alice_bits)):
        a_angle      = engine.alice_angles[alice_bases[i]]
        b_angle      = engine.bob_angles[bob_bases[i]]
        prob_same    = np.cos(a_angle - b_angle) ** 2

        if np.random.random() < prob_same:
            bob_bits.append(alice_bits[i])
        else:
            bob_bits.append(1 - alice_bits[i])

    print(f"  ✅ Bob measured {len(bob_bits)} qubits")

    # ── 4. Send Bob's data to Alice ───────────────────────────────
    print("\n  📤 [4/7] Sending Bob's bases to Alice...")
    send_message(sock, MSG_BASIS_COMPARE, {
        'bob_bases': bob_bases,
        'bob_bits' : bob_bits
    })

    # ── 5. Receive CHSH result ────────────────────────────────────
    print("\n  🔒 [5/7] Receiving CHSH security test result...")
    msg = receive_message(sock)

    if msg['type'] == MSG_ABORT:
        print("\n  ❌ Alice aborted — channel not secure!")
        return None

    chsh_result = msg['payload']
    print(f"\n  ┌─── CHSH Verification ─────────────────────┐")
    print(f"  │  S-value : {chsh_result['S_value']:.4f}                        │")
    print(f"  │  Secure? : {'YES ✅' if chsh_result['is_secure'] else 'NO  ❌'}                       │")
    print(f"  └────────────────────────────────────────────┘")

    logger.log_chsh_result({
        'S_value'      : chsh_result['S_value'],
        'E_00'         : 0,
        'E_02'         : 0,
        'E_20'         : 0,
        'E_22'         : 0,
        'is_secure'    : chsh_result['is_secure'],
        'quantum_bound': 2 * np.sqrt(2)
    })

    if not chsh_result['is_secure']:
        logger.log_security_event('CHSH_FAIL', f"S={chsh_result['S_value']:.4f}", 'CRITICAL')
        return None

    logger.log_security_event('CHSH_PASS', f"S={chsh_result['S_value']:.4f}", 'INFO')

    # ── 6. Extract key bits ───────────────────────────────────────
    print("\n  🔑 [6/7] Extracting key bits from matching bases...")
    combined = []
    for i in range(len(alice_bits)):
        combined.append({
            'alice_bit'       : alice_bits[i],
            'bob_bit'         : bob_bits[i],
            'alice_angle_idx' : alice_bases[i],
            'bob_angle_idx'   : bob_bases[i],
            'alice_angle_deg' : round(np.degrees(engine.alice_angles[alice_bases[i]]), 2),
            'bob_angle_deg'   : round(np.degrees(engine.bob_angles[bob_bases[i]]), 2)
        })

    key_data = engine.extract_key_bits(combined)
    print(f"  ✅ Found {key_data['key_length']} matching-basis bits")

    logger.log_measurements(combined, key_data['used_indices'], key_data['chsh_indices'])
    logger.log_key_exchange('basis_sifting', {
        'total_pairs'   : len(combined),
        'key_bits_found': key_data['key_length'],
        'chsh_bits_used': len(key_data['chsh_indices'])
    })

    # ── 7. Generate final key ─────────────────────────────────────
    print("\n  🧮 [7/7] Generating final quantum key...")
    msg        = receive_message(sock)
    error_rate = msg['payload']['error_rate']
    print(f"  Error rate shared by Alice: {error_rate:.2%}")

    if error_rate >= 0.11:
        logger.log_security_event('QBER_TOO_HIGH', f"{error_rate:.2%}", 'CRITICAL')
        return None

    kg = KeyGenerator()
    kg.sift_key(key_data['alice_bits'], key_data['bob_bits'])
    kg.raw_alice_bits = kg.raw_alice_bits[20:]
    kg.raw_bob_bits   = kg.raw_bob_bits[20:]

    final_key = kg.privacy_amplification(kg.raw_alice_bits, target_bytes=16)
    if not final_key:
        return None

    logger.log_key_exchange('final_key', {
        'key_hex'  : final_key.hex(),
        'key_bits' : 128
    })

    # ── 8. Key verification ───────────────────────────────────────
    print("\n  🤝 Verifying key match with Alice...")
    msg            = receive_message(sock)
    alice_key_hash = msg['payload']['key_hash']

    our_hash = hash_key(final_key)
    send_message(sock, MSG_KEY_HASH, {'key_hash': our_hash})

    if our_hash == alice_key_hash:
        print(f"\n  🎉 Keys MATCH! Channel is secure.")
        print(f"     Key: {final_key.hex()}")
        logger.log_security_event('KEY_MATCH', 'Keys are identical', 'INFO')
    else:
        print(f"\n  ❌ Keys do NOT match!")
        logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
        return None

    receive_message(sock)                          # Alice's READY
    send_message(sock, MSG_READY, {'status': 'ready'})

    return QuantumEncryptor(final_key)

# ── Receive Thread ────────────────────────────────────────────────────────────

def receive_loop(sock):
    global encryptor, logger, chat_active

    while True:
        try:
            msg = receive_message(sock)

            if msg['type'] == MSG_CHAT:
                encrypted_data = bytes(msg['payload']['data'])
                plaintext      = encryptor.decrypt(encrypted_data)
                encrypted_hex  = encrypted_data.hex()

                print_received("Alice", plaintext)

                logger.log_chat_message(
                    direction    = 'RECEIVED',
                    plaintext    = plaintext,
                    encrypted_hex= encrypted_hex,
                    msg_len      = len(encrypted_data)
                )

            elif msg['type'] == MSG_ABORT:
                clear_input_line()
                print("\n\n  [Alice has disconnected]")
                logger.log_security_event('PEER_DISCONNECT', 'Alice disconnected', 'INFO')
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
    global encryptor, logger, chat_active

    logger = QuantumLogger(role='bob')

    SERVER_IP = '192.168.29.42'    # ← Change to Alice's PC IP

    print("\n╔══════════════════════════════════════════╗")
    print("║    Quantum Encrypted Chat  —  BOB        ║")
    print("║    Protocol: E91 (Bell Entanglement)     ║")
    print("╚══════════════════════════════════════════╝")
    print(f"\n  Connecting to Alice at {SERVER_IP}:12345 ...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, 12345))
    print(f"  ✅ Connected!")

    logger.log_security_event('CONNECTION', f"Connected to Alice at {SERVER_IP}", 'INFO')

    # Quantum key exchange
    encryptor = perform_e91_key_exchange(sock)

    if encryptor is None:
        print("\n  ❌ Key exchange failed. Closing.")
        logger.save_session_summary()
        sock.close()
        return

    # ── Start Chat ────────────────────────────────────────────────
    chat_active = True

    recv_thread        = threading.Thread(target=receive_loop, args=(sock,))
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
            print("  Bob   ▶ ", end='', flush=True)
            message = input()

            if message.lower() == 'exit':
                send_message(sock, MSG_ABORT, {'reason': 'User quit'})
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
            send_message(sock, MSG_CHAT, {'data': list(encrypted)})

            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"  [{now}] 📤 Sent (encrypted)")
            logger.log_chat_message(
                direction    = 'SENT',
                plaintext    = message,
                encrypted_hex= encrypted.hex(),
                msg_len      = len(encrypted)
            )

        except KeyboardInterrupt:
            send_message(sock, MSG_ABORT, {'reason': 'Keyboard interrupt'})
            break
        except Exception as e:
            print(f"\n  [Error: {e}]")
            break

    # Cleanup
    chat_active = False
    logger.save_session_summary()
    sock.close()
    print("\n  Connection closed. Goodbye!")

if __name__ == '__main__':
    main()