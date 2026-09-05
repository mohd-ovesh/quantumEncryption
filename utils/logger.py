# utils/logger.py

import os
import json
import csv
import time
import datetime
import threading
from typing import Any, List, Dict

class QuantumLogger:
    """
    Saves ALL quantum protocol data to files for later analysis.
    
    Files created per session:
    ┌─────────────────────────────────────────────────────────┐
    │  File                        │  Contains               │
    ├─────────────────────────────────────────────────────────┤
    │  session_TIMESTAMP.json      │  Full session summary   │
    │  quantum_measurements.csv    │  Every qubit measured   │
    │  chsh_analysis.json          │  CHSH test breakdown    │
    │  key_exchange.json           │  Key generation steps   │
    │  chat_log.txt                │  All messages sent/recv │
    └─────────────────────────────────────────────────────────┘
    """

    def __init__(self, role: str):
        """
        Args:
            role: 'alice' or 'bob'
        """
        self.role      = role
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.lock      = threading.Lock()  # Thread-safe file writes

        # Create logs directory
        self.log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        os.makedirs(self.log_dir, exist_ok=True)

        # File paths
        self.session_file      = self._path(f"session_{role}_{self.timestamp}.json")
        self.measurements_file = self._path(f"quantum_measurements_{role}_{self.timestamp}.csv")
        self.chsh_file         = self._path(f"chsh_analysis_{role}_{self.timestamp}.json")
        self.key_file          = self._path(f"key_exchange_{role}_{self.timestamp}.json")
        self.chat_file         = self._path(f"chat_log_{role}_{self.timestamp}.txt")

        # In-memory store (gets written to session file at end)
        self.session_data = {
            'role'            : role,
            'session_start'   : datetime.datetime.now().isoformat(),
            'session_end'     : None,
            'protocol'        : 'E91',
            'quantum_backend' : 'Qiskit AerSimulator',
            'key_exchange'    : {},
            'chsh'            : {},
            'chat_stats'      : {
                'messages_sent'    : 0,
                'messages_received': 0,
                'total_bytes_sent' : 0
            },
            'security_events' : []
        }

        # Initialize CSV file with headers
        self._init_csv()

        # Initialize chat log
        self._init_chat_log()

        print(f"\n[Logger] Logging to: {self.log_dir}")
        print(f"[Logger] Session files prefix: {role}_{self.timestamp}")

    # ── Internal Helpers ────────────────────────────────────────────────────

    def _path(self, filename: str) -> str:
        """Get full path for a log file."""
        return os.path.join(self.log_dir, filename)

    def _init_csv(self):
        """Create CSV file with headers for quantum measurements."""
        with open(self.measurements_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'pair_index',        # Which entangled pair (0, 1, 2, ...)
                'alice_angle_idx',   # Alice's basis choice (0=0°, 1=45°, 2=90°)
                'alice_angle_deg',   # Alice's basis in degrees
                'bob_angle_idx',     # Bob's basis choice (0=45°, 1=90°, 2=135°)
                'bob_angle_deg',     # Bob's basis in degrees
                'alice_bit',         # Alice's measurement result (0 or 1)
                'bob_bit',           # Bob's measurement result (0 or 1)
                'bases_match',       # Whether they used matching bases
                'used_for',          # 'key' or 'chsh_test' or 'discarded'
                'bits_agree',        # Whether alice_bit == bob_bit
                'timestamp'          # When this pair was measured
            ])

    def _init_chat_log(self):
        """Create chat log file with header."""
        with open(self.chat_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write(f"  QUANTUM ENCRYPTED CHAT LOG\n")
            f.write(f"  Role     : {self.role.upper()}\n")
            f.write(f"  Protocol : E91 (Quantum Entanglement)\n")
            f.write(f"  Started  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n\n")

    # ── Quantum Measurement Logging ─────────────────────────────────────────

    def log_measurements(self, results: List[Dict], key_indices: List[int], chsh_indices: List[int]):
        """
        Save every single qubit measurement to CSV.
        
        Args:
            results      : list of measurement dicts from QuantumEngine
            key_indices  : which indices were used for key bits
            chsh_indices : which indices were used for CHSH test
        """
        key_set  = set(key_indices)
        chsh_set = set(chsh_indices)

        rows = []
        for i, r in enumerate(results):
            if i in key_set:
                used_for = 'key'
            elif i in chsh_set:
                used_for = 'chsh_test'
            else:
                used_for = 'discarded'

            rows.append([
                i,
                r['alice_angle_idx'],
                round(r.get('alice_angle_deg', r['alice_angle_idx'] * 45), 2),
                r['bob_angle_idx'],
                round(r.get('bob_angle_deg',   r['bob_angle_idx']   * 45), 2),
                r['alice_bit'],
                r['bob_bit'],
                (r['alice_angle_idx'], r['bob_angle_idx']) in [(1,0),(2,1)],
                used_for,
                r['alice_bit'] == r['bob_bit'],
                datetime.datetime.now().isoformat()
            ])

        with self.lock:
            with open(self.measurements_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        print(f"[Logger] Saved {len(rows)} quantum measurements to CSV")

    # ── CHSH Logging ─────────────────────────────────────────────────────────

    def log_chsh_result(self, chsh_data: Dict):
        """
        Save CHSH test results and detailed breakdown.
        
        Args:
            chsh_data: dict from QuantumEngine.compute_chsh_value()
        """
        record = {
            'timestamp'          : datetime.datetime.now().isoformat(),
            'S_value'            : chsh_data['S_value'],
            'quantum_bound'      : chsh_data['quantum_bound'],
            'classical_bound'    : 2.0,
            'is_secure'          : chsh_data['is_secure'],
            'security_margin'    : chsh_data['S_value'] - 2.0,
            'correlations'       : {
                'E_alice0_bob0'  : chsh_data['E_00'],    # E(0°, 45°)
                'E_alice0_bob2'  : chsh_data['E_02'],    # E(0°, 135°)
                'E_alice2_bob0'  : chsh_data['E_20'],    # E(90°, 45°)
                'E_alice2_bob2'  : chsh_data['E_22'],    # E(90°, 135°)
            },
            'interpretation'     : {
                'above_classical' : chsh_data['S_value'] > 2.0,
                'near_quantum_max': chsh_data['S_value'] > 2.5,
                'verdict'         : (
                    'SECURE - Strong quantum correlations detected'
                    if chsh_data['is_secure']
                    else 'INSECURE - Possible eavesdropping!'
                )
            }
        }

        with self.lock:
            with open(self.chsh_file, 'w') as f:
                json.dump(record, f, indent=2)

        # Also update session data
        self.session_data['chsh'] = record
        print(f"[Logger] CHSH analysis saved → {os.path.basename(self.chsh_file)}")

    # ── Key Exchange Logging ─────────────────────────────────────────────────

    def log_key_exchange(self, stage: str, data: Dict):
        """
        Append a key exchange event to the key exchange log.
        
        Stages: 'basis_sifting', 'error_rate', 'privacy_amplification', 'final'
        
        Args:
            stage: name of the key exchange stage
            data : relevant data for this stage
        """
        record = {
            'timestamp' : datetime.datetime.now().isoformat(),
            'stage'     : stage,
            'data'      : data
        }

        # Load existing data if file exists
        existing = []
        if os.path.exists(self.key_file):
            with open(self.key_file, 'r') as f:
                try:
                    existing = json.load(f)
                except Exception:
                    existing = []

        existing.append(record)

        with self.lock:
            with open(self.key_file, 'w') as f:
                json.dump(existing, f, indent=2)

        # Update session data
        self.session_data['key_exchange'][stage] = data
        print(f"[Logger] Key exchange stage '{stage}' saved")

    # ── Chat Logging ─────────────────────────────────────────────────────────

    def log_chat_message(
            self,
            direction    : str,        # 'SENT' or 'RECEIVED'
            plaintext    : str,        # The actual message
            encrypted_hex: str,        # Hex of the encrypted bytes
            msg_len      : int         # Length in bytes
    ):
        """
        Save each chat message with metadata.
        
        Args:
            direction    : 'SENT' or 'RECEIVED'
            plaintext    : decrypted message text
            encrypted_hex: encrypted bytes as hex string
            msg_len      : length of encrypted message
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        line = (
            f"[{timestamp}] {direction:8s} | "
            f"Plaintext : '{plaintext}'\n"
            f"{'':>12}          | "
            f"Encrypted : {encrypted_hex[:48]}{'...' if len(encrypted_hex)>48 else ''}\n"
            f"{'':>12}          | "
            f"Length    : {msg_len} bytes\n"
            f"{'-'*70}\n"
        )

        with self.lock:
            with open(self.chat_file, 'a') as f:
                f.write(line)

        # Update stats
        if direction == 'SENT':
            self.session_data['chat_stats']['messages_sent']     += 1
            self.session_data['chat_stats']['total_bytes_sent']  += msg_len
        else:
            self.session_data['chat_stats']['messages_received'] += 1

    # ── Security Event Logging ───────────────────────────────────────────────

    def log_security_event(self, event_type: str, details: str, severity: str = 'INFO'):
        """
        Log any security-relevant event.
        
        Args:
            event_type : e.g. 'CHSH_PASS', 'HIGH_ERROR_RATE', 'KEY_MISMATCH'
            details    : human-readable description
            severity   : 'INFO', 'WARNING', 'CRITICAL'
        """
        event = {
            'timestamp' : datetime.datetime.now().isoformat(),
            'type'      : event_type,
            'severity'  : severity,
            'details'   : details
        }
        self.session_data['security_events'].append(event)
        print(f"[Security Event] [{severity}] {event_type}: {details}")

    # ── Session Summary ──────────────────────────────────────────────────────

    def save_session_summary(self):
        """
        Write the complete session summary JSON file.
        Call this when the chat session ends.
        """
        self.session_data['session_end'] = datetime.datetime.now().isoformat()

        # Calculate session duration
        start = datetime.datetime.fromisoformat(self.session_data['session_start'])
        end   = datetime.datetime.fromisoformat(self.session_data['session_end'])
        duration = (end - start).total_seconds()
        self.session_data['session_duration_seconds'] = duration

        with self.lock:
            with open(self.session_file, 'w') as f:
                json.dump(self.session_data, f, indent=2)

        print(f"\n[Logger] Session summary saved → {os.path.basename(self.session_file)}")
        self._print_summary()

    def _print_summary(self):
        """Print a human-readable summary to terminal."""
        s = self.session_data
        print("\n" + "="*60)
        print("              SESSION SUMMARY")
        print("="*60)
        print(f"  Role           : {s['role'].upper()}")
        print(f"  Duration       : {s.get('session_duration_seconds', 0):.1f} seconds")
        print(f"  Messages Sent  : {s['chat_stats']['messages_sent']}")
        print(f"  Messages Recv  : {s['chat_stats']['messages_received']}")
        print(f"  Bytes Sent     : {s['chat_stats']['total_bytes_sent']}")

        if s.get('chsh'):
            print(f"  CHSH S-value   : {s['chsh'].get('S_value', 'N/A'):.4f}")
            print(f"  Channel Secure : {'YES ✅' if s['chsh'].get('is_secure') else 'NO ❌'}")

        print(f"\n  Log files in   : logs/")
        print("="*60)