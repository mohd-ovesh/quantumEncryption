# # pc_a_server.py

# import socket
# import threading
# import os
# import sys
# import numpy as np
# import datetime

# from e91.quantum_engine import QuantumEngine
# from e91.key_generator  import KeyGenerator
# from e91.encryptor      import QuantumEncryptor
# from utils.protocol     import (
#     send_message, receive_message, hash_key,
#     MSG_BASIS_COMPARE, MSG_CHSH_RESULT, MSG_KEY_HASH,
#     MSG_READY, MSG_CHAT, MSG_ABORT, MSG_ERROR_RATE
# )
# from utils.logger import QuantumLogger

# # ── Globals ────────────────────────────────────────────────────────────────
# encryptor   : QuantumEncryptor = None
# logger      : QuantumLogger    = None
# conn_sock   : socket.socket    = None
# chat_active                    = False

# # ── UI ─────────────────────────────────────────────────────────────────────

# def clear_line():
#     sys.stdout.write('\r' + ' ' * 80 + '\r')
#     sys.stdout.flush()

# def print_received(sender: str, message: str):
#     clear_line()
#     ts = datetime.datetime.now().strftime("%H:%M:%S")
#     print(f"\n  [{ts}] 📨 {sender}: {message}")
#     if chat_active:
#         print("  Alice ▶ ", end='', flush=True)

# # ── E91 Key Exchange ────────────────────────────────────────────────────────

# def perform_e91_key_exchange(conn):
#     """
#     Alice's E91 Protocol — Clean version.

#     Security model:
#     ────────────────────────────────────────────────────────────
#     ✅ CHSH test (S > 2.0) is the ONLY security check needed.
#        If S > 2.0 → quantum entanglement confirmed → no Eve.
#        If S ≤ 2.0 → classical correlations → Eve present → abort.

#     ❌ QBER between alice_bits and bob_bits is NOT used.
#        Reason: 22.5° angle naturally causes ~15% mismatch.
#        This is physics, not eavesdropping.

#     Key generation:
#     ────────────────────────────────────────────────────────────
#     Alice simulates both qubits → gets alice_key_bits & bob_key_bits.
#     Alice sends alice_key_bits to Bob.
#     Both run SHA-256(alice_key_bits) → identical 128-bit key.

#     Message sequence Alice → Bob:
#     ────────────────────────────────────────────────────────────
#     1. MSG_BASIS_COMPARE    (alice_bases)
#     3. MEASUREMENT_RESULTS  (bob_bits_all)
#     4. MSG_CHSH_RESULT      (S_value, correlators, is_secure)
#        [if not secure] MSG_ABORT
#     5. MSG_ERROR_RATE       (alice_key_bits, stats)
#        [if not enough bits] MSG_ABORT
#     6. MSG_KEY_HASH         (sha256 of final key)
#     7. MSG_READY
#     """
#     global logger

#     print("\n" + "═"*62)
#     print("        E91 QUANTUM KEY EXCHANGE  —  ALICE")
#     print("═"*62)

#     engine    = QuantumEngine()
#     num_pairs = 300

#     # ── Step 1: Alice picks random bases ───────────────────────────
#     print(f"\n  📡 [1/7] Choosing {num_pairs} random measurement bases...")
#     alice_bases = [int(np.random.randint(0, 3)) for _ in range(num_pairs)]
#     print(f"  ✅ Sample: {alice_bases[:12]}...")

#     # ── Step 2: Exchange bases with Bob ────────────────────────────
#     print(f"\n  📤 [2/7] Sending bases to Bob...")
#     send_message(conn, MSG_BASIS_COMPARE, {
#         'alice_bases': alice_bases,
#         'num_pairs'  : num_pairs
#     })

#     print(f"\n  📥 [3/7] Receiving Bob's bases...")
#     msg       = receive_message(conn)
#     bob_bases = msg['payload']['bob_bases']
#     print(f"  ✅ Sample: {bob_bases[:12]}...")

#     # ── Step 3: Simulate Bell pairs ─────────────────────────────────
#     # Alice knows BOTH bases now → simulates full entangled pairs
#     # Gets correlated alice_bit and bob_bit from SAME quantum circuit
#     print(f"\n  ⚛️  [4/7] Simulating {num_pairs} entangled Bell pairs...")
#     results = engine.generate_all_measurements(num_pairs, alice_bases, bob_bases)

#     alice_bits_all = [r['alice_bit'] for r in results]
#     bob_bits_all   = [r['bob_bit']   for r in results]

#     # Send Bob his qubit measurement results
#     print(f"\n  📤 [5/7] Sending Bob his measurement results...")
#     send_message(conn, 'MEASUREMENT_RESULTS', {
#         'bob_bits_all': bob_bits_all
#     })

#     logger.log_key_exchange('raw_measurements', {
#         'num_pairs'  : num_pairs,
#         'alice_bases': alice_bases,
#         'bob_bases'  : bob_bases,
#         'alice_bits' : alice_bits_all,
#         'bob_bits'   : bob_bits_all
#     })

#     # ── Step 4: CHSH Security Test ──────────────────────────────────
#     # This is the SOLE security verification in E91
#     print(f"\n  🔒 [6/7] Running CHSH inequality test...")
#     chsh = engine.compute_chsh_value(results)

#     _print_chsh(chsh)
#     logger.log_chsh_result(chsh)

#     # Send CHSH result to Bob (always send before any abort)
#     send_message(conn, MSG_CHSH_RESULT, {
#         'S_value'   : chsh['S_value'],
#         'is_secure' : chsh['is_secure'],
#         'E_a0b0'    : chsh['E_a0b0'],
#         'E_a0b1'    : chsh['E_a0b1'],
#         'E_a1b0'    : chsh['E_a1b0'],
#         'E_a1b1'    : chsh['E_a1b1'],
#     })

#     if not chsh['is_secure']:
#         logger.log_security_event('CHSH_FAIL', f"S={chsh['S_value']:.4f} ≤ 2.0", 'CRITICAL')
#         send_message(conn, MSG_ABORT, {'reason': 'CHSH test failed — S ≤ 2.0'})
#         return None

#     logger.log_security_event('CHSH_PASS', f"S={chsh['S_value']:.4f} > 2.0", 'INFO')

#     # ── Step 5: Extract key bits & send to Bob ──────────────────────
#     print(f"\n  🔑 [7/7] Extracting key bits & generating shared key...")
#     key_data = engine.extract_key_bits(results)

#     alice_key_bits = key_data['alice_bits']
#     bob_key_bits   = key_data['bob_bits']
#     n_key          = key_data['key_length']

#     print(f"\n  📊 Key bit statistics:")
#     print(f"     Total pairs measured   : {num_pairs}")
#     print(f"     Matching-basis pairs   : {n_key}")
#     print(f"     CHSH test pairs        : {len(key_data['chsh_indices'])}")
#     print(f"     Discarded (other)      : {num_pairs - n_key - len(key_data['chsh_indices'])}")

#     if n_key < 8:
#         print(f"\n  ❌ Not enough key bits ({n_key}). Need at least 8.")
#         send_message(conn, MSG_ABORT, {'reason': f'Only {n_key} key bits — need ≥ 8'})
#         return None

#     # Show natural quantum correlation (informational only)
#     if alice_key_bits and bob_key_bits:
#         agree     = sum(a == b for a, b in zip(alice_key_bits, bob_key_bits))
#         agree_pct = agree / n_key * 100
#         print(f"\n  📊 Alice-Bob natural correlation:")
#         print(f"     Agreement rate : {agree}/{n_key} = {agree_pct:.1f}%")
#         print(f"     Expected       : ~85% (cos²(22.5°) at key-pair angle)")
#         print(f"     Note           : NOT used for security — CHSH handles that")

#     logger.log_measurements(results, key_data['used_indices'], key_data['chsh_indices'])
#     logger.log_key_exchange('key_sifting', {
#         'total_pairs'  : num_pairs,
#         'key_bits'     : n_key,
#         'chsh_bits'    : len(key_data['chsh_indices']),
#         'alice_key_bits': alice_key_bits,
#         'bob_key_bits'  : bob_key_bits,
#         'agreement_pct' : round(agree_pct, 2) if n_key > 0 else 0
#     })

#     # Privacy amplification — Alice uses her key bits
#     kg        = KeyGenerator()
#     final_key = kg.privacy_amplification(alice_key_bits, target_bytes=16)

#     logger.log_key_exchange('final_key', {
#         'key_hex'        : final_key.hex(),
#         'key_bits'       : 128,
#         'source_bits'    : n_key,
#         'algorithm'      : 'SHA-256 privacy amplification'
#     })

#     # Send Bob everything he needs to derive the SAME key
#     # alice_key_bits → Bob runs same SHA-256 → same final_key
#     send_message(conn, MSG_ERROR_RATE, {
#         'alice_key_bits': alice_key_bits,    # Bob uses these to make key
#         'n_key_bits'    : n_key,
#         'chsh_s_value'  : chsh['S_value'],
#         'status'        : 'secure'
#     })

#     # ── Key verification ────────────────────────────────────────────
#     print(f"\n  🤝 Verifying key match with Bob...")
#     our_hash = hash_key(final_key)
#     send_message(conn, MSG_KEY_HASH, {'key_hash': our_hash})

#     msg          = receive_message(conn)
#     bob_key_hash = msg['payload']['key_hash']

#     if our_hash == bob_key_hash:
#         print(f"\n  🎉 Keys MATCH! Quantum-secured channel established.")
#         print(f"     Key: {final_key.hex()}")
#         logger.log_security_event('KEY_MATCH', 'Identical keys — channel ready', 'INFO')
#     else:
#         print(f"\n  ❌ Keys DO NOT match!")
#         print(f"     Alice: {our_hash[:32]}...")
#         print(f"     Bob  : {bob_key_hash[:32]}...")
#         logger.log_security_event('KEY_MISMATCH', 'Keys differ', 'CRITICAL')
#         send_message(conn, MSG_ABORT, {'reason': 'Key mismatch'})
#         return None

#     send_message(conn, MSG_READY, {'status': 'ready'})
#     receive_message(conn)   # Bob's READY signal

#     return QuantumEncryptor(final_key)

# # ── CHSH Display ────────────────────────────────────────────────────────────

# def _print_chsh(chsh: dict):
#     s  = chsh['S_value']
#     q  = chsh['quantum_bound']
#     ok = chsh['is_secure']
#     print(f"\n  ┌─── CHSH Results ─────────────────────────────────────────┐")
#     print(f"  │  E( 0°, 22.5°)  = {chsh['E_a0b0']:+.4f}   theory = -0.7071       │")
#     print(f"  │  E( 0°, 67.5°)  = {chsh['E_a0b1']:+.4f}   theory = +0.7071       │")
#     print(f"  │  E(45°, 22.5°)  = {chsh['E_a1b0']:+.4f}   theory = -0.7071       │")
#     print(f"  │  E(45°, 67.5°)  = {chsh['E_a1b1']:+.4f}   theory = -0.7071       │")
#     print(f"  ├──────────────────────────────────────────────────────────┤")
#     print(f"  │  S = {s:.4f}                                              │")
#     print(f"  │  Classical limit ≤ 2.0000   Quantum limit ≤ {q:.4f}     │")
#     print(f"  │  Verdict : {'✅ SECURE — entanglement confirmed, no Eve' if ok else '❌ INSECURE — classical correlations, Eve present'}  │")
#     print(f"  └──────────────────────────────────────────────────────────┘")

# # ── Receive Thread ──────────────────────────────────────────────────────────

# def receive_loop(conn):
#     global encryptor, logger, chat_active

#     while True:
#         try:
#             msg = receive_message(conn)

#             if msg['type'] == MSG_CHAT:
#                 enc_data  = bytes(msg['payload']['data'])
#                 plaintext = encryptor.decrypt(enc_data)
#                 print_received("Bob", plaintext)
#                 logger.log_chat_message(
#                     direction     = 'RECEIVED',
#                     plaintext     = plaintext,
#                     encrypted_hex = enc_data.hex(),
#                     msg_len       = len(enc_data)
#                 )

#             elif msg['type'] == MSG_ABORT:
#                 clear_line()
#                 print("\n\n  [Bob disconnected]")
#                 logger.log_security_event('PEER_DISCONNECT', 'Bob left', 'INFO')
#                 logger.save_session_summary()
#                 os._exit(0)

#         except Exception as e:
#             clear_line()
#             print(f"\n\n  [Connection lost: {e}]")
#             if logger:
#                 logger.save_session_summary()
#             os._exit(0)

# # ── Main ────────────────────────────────────────────────────────────────────

# def main():
#     global encryptor, logger, conn_sock, chat_active

#     logger = QuantumLogger(role='alice')

#     print("\n╔══════════════════════════════════════════╗")
#     print("║    Quantum Encrypted Chat  —  ALICE      ║")
#     print("║    Protocol: E91 (Bell Entanglement)     ║")
#     print("╚══════════════════════════════════════════╝")

#     server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     server.bind(('0.0.0.0', 12345))
#     server.listen(1)
#     print(f"\n  Listening on port 12345...")

#     conn, addr = server.accept()
#     conn_sock  = conn
#     print(f"  ✅ Bob connected from {addr[0]}:{addr[1]}")
#     logger.log_security_event('CONNECTION', f"Bob from {addr[0]}:{addr[1]}", 'INFO')

#     encryptor = perform_e91_key_exchange(conn)

#     if encryptor is None:
#         print("\n  ❌ Key exchange failed.")
#         logger.save_session_summary()
#         conn.close()
#         server.close()
#         return

#     chat_active = True
#     recv_thread = threading.Thread(target=receive_loop, args=(conn,))
#     recv_thread.daemon = True
#     recv_thread.start()

#     print("\n" + "═"*62)
#     print("  🔐 SECURE QUANTUM CHANNEL ESTABLISHED!")
#     print("  Commands: 'exit' to quit | 'status' for stats")
#     print("═"*62 + "\n")

#     while True:
#         try:
#             print("  Alice ▶ ", end='', flush=True)
#             message = input()

#             if message.lower() == 'exit':
#                 send_message(conn, MSG_ABORT, {'reason': 'User quit'})
#                 break

#             if message.lower() == 'status':
#                 _print_status()
#                 continue

#             if not message.strip():
#                 continue

#             enc = encryptor.encrypt(message)
#             send_message(conn, MSG_CHAT, {'data': list(enc)})
#             ts  = datetime.datetime.now().strftime("%H:%M:%S")
#             print(f"  [{ts}] 📤 Sent ({len(enc)} bytes encrypted)")
#             logger.log_chat_message('SENT', message, enc.hex(), len(enc))

#         except KeyboardInterrupt:
#             send_message(conn, MSG_ABORT, {'reason': 'Interrupted'})
#             break
#         except Exception as e:
#             print(f"\n  [Error: {e}]")
#             break

#     chat_active = False
#     logger.save_session_summary()
#     conn.close()
#     server.close()
#     print("\n  Goodbye!")

# def _print_status():
#     s = logger.session_data
#     print(f"\n  ┌─── Status ─────────────────────────────────┐")
#     print(f"  │  Sent     : {s['chat_stats']['messages_sent']:<32}│")
#     print(f"  │  Received : {s['chat_stats']['messages_received']:<32}│")
#     if s.get('chsh'):
#         ok = '✅' if s['chsh'].get('is_secure') else '❌'
#         print(f"  │  S-value  : {s['chsh'].get('S_value', 0):<32.4f}│")
#         print(f"  │  Secure   : {ok:<32}│")
#     print(f"  └────────────────────────────────────────────┘\n")

# if __name__ == '__main__':
#     main()


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
from utils.protocol     import (
    send_message, receive_message, hash_key,
    MSG_BASIS_COMPARE, MSG_CHSH_RESULT, MSG_KEY_HASH,
    MSG_READY, MSG_CHAT, MSG_ABORT, MSG_ERROR_RATE
)
from utils.logger import QuantumLogger

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
    server.bind(('0.0.0.0', 12345))
    server.listen(1)
    print(f"  Listening on port 12345... waiting for peer.")

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

            if message.lower() == 'exit':
                send_message(conn, MSG_ABORT, {'reason': 'User quit'})
                break

            if message.lower() == 'status':
                _print_status()
                continue

            if not message.strip():
                continue

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