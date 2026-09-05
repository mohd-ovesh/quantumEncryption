# e91/quantum_engine.py

import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

class QuantumEngine:
    """
    Core quantum operations for E91 protocol.
    Now returns richer data structures for logging.
    """

    def __init__(self):
        self.simulator    = AerSimulator()
        self.alice_angles = [0, np.pi/4, np.pi/2]        # 0°, 45°, 90°
        self.bob_angles   = [np.pi/4, np.pi/2, 3*np.pi/4]# 45°, 90°, 135°
        self.chsh_pairs   = [(0,0), (0,2), (2,0), (2,2)]
        self.key_pairs    = [(1,0), (2,1)]

    def create_bell_pair(self):
        """Bell state |Φ+⟩ = (|00⟩ + |11⟩)/√2"""
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        return qc

    def apply_measurement_basis(self, qc, qubit_idx, angle):
        """Rotate qubit to measure in given basis angle."""
        if angle != 0:
            qc.ry(-2 * angle, qubit_idx)
        return qc

    def measure_entangled_pair(self, alice_angle_idx, bob_angle_idx):
        """Measure one entangled pair with given basis choices."""
        alice_angle = self.alice_angles[alice_angle_idx]
        bob_angle   = self.bob_angles[bob_angle_idx]

        qc = self.create_bell_pair()
        qc = self.apply_measurement_basis(qc, 0, alice_angle)
        qc = self.apply_measurement_basis(qc, 1, bob_angle)
        qc.measure(0, 0)
        qc.measure(1, 1)

        job    = self.simulator.run(qc, shots=1)
        counts = job.result().get_counts()
        state  = list(counts.keys())[0]

        bob_bit   = int(state[0])
        alice_bit = int(state[1])

        return {
            'alice_bit'       : alice_bit,
            'bob_bit'         : bob_bit,
            'alice_angle_idx' : alice_angle_idx,
            'bob_angle_idx'   : bob_angle_idx,
            'alice_angle_deg' : round(np.degrees(alice_angle), 2),
            'bob_angle_deg'   : round(np.degrees(bob_angle),   2)
        }

    def generate_raw_measurements(self, num_pairs=300):
        """Generate all measurements. Returns results + index tracking."""
        results = []
        print(f"\n[Quantum] Generating {num_pairs} entangled pairs...")

        for i in range(num_pairs):
            alice_choice = np.random.randint(0, 3)
            bob_choice   = np.random.randint(0, 3)
            results.append(self.measure_entangled_pair(alice_choice, bob_choice))

            if (i + 1) % 100 == 0:
                print(f"  ▶ {i+1}/{num_pairs} pairs measured...")

        print(f"[Quantum] ✅ {len(results)} measurements complete")
        return results

    def compute_chsh_value(self, results):
        """Compute CHSH S-value and all correlators."""
        correlations = {}

        for a_idx, b_idx in self.chsh_pairs:
            matching = [
                r for r in results
                if r['alice_angle_idx'] == a_idx and r['bob_angle_idx'] == b_idx
            ]
            if not matching:
                correlations[(a_idx, b_idx)] = 0.0
                continue

            total = sum(
                (1 - 2*m['alice_bit']) * (1 - 2*m['bob_bit'])
                for m in matching
            )
            correlations[(a_idx, b_idx)] = total / len(matching)

        E_00 = correlations.get((0,0), 0)
        E_02 = correlations.get((0,2), 0)
        E_20 = correlations.get((2,0), 0)
        E_22 = correlations.get((2,2), 0)
        S    = abs(E_00 - E_02 + E_20 + E_22)

        return {
            'S_value'      : S,
            'E_00'         : E_00,
            'E_02'         : E_02,
            'E_20'         : E_20,
            'E_22'         : E_22,
            'correlations' : {str(k): v for k, v in correlations.items()},
            'is_secure'    : S > 2.0,
            'quantum_bound': 2 * np.sqrt(2)
        }

    def extract_key_bits(self, results):
        """Extract bits from matching-basis measurements."""
        alice_key_bits = []
        bob_key_bits   = []
        used_indices   = []
        chsh_indices   = []

        for i, r in enumerate(results):
            a_idx = r['alice_angle_idx']
            b_idx = r['bob_angle_idx']

            if (a_idx, b_idx) in self.key_pairs:
                alice_key_bits.append(r['alice_bit'])
                bob_key_bits.append(r['bob_bit'])
                used_indices.append(i)
            elif (a_idx, b_idx) in self.chsh_pairs:
                chsh_indices.append(i)

        return {
            'alice_bits'   : alice_key_bits,
            'bob_bits'     : bob_key_bits,
            'used_indices' : used_indices,
            'chsh_indices' : chsh_indices,
            'key_length'   : len(alice_key_bits)
        }