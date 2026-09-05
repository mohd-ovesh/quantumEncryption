# # e91/quantum_engine.py

import numpy as np
from qiskit     import QuantumCircuit
from qiskit_aer import AerSimulator

class QuantumEngine:
    """
    E91 Quantum Key Distribution engine.

    Uses optimal measurement angles for maximum CHSH violation.

    Angle Layout:
    ┌─────────────────────────────────────────────────────┐
    │  Alice: a0=0°    a1=45°   a2=90°                   │
    │  Bob:   b0=22.5° b1=67.5° b2=112.5°                │
    │                                                     │
    │  CHSH test uses: (a0,b0),(a0,b1),(a1,b0),(a1,b1)   │
    │  Key bits from:  (a1,b0) and (a2,b1)               │
    │                  [22.5° diff → highly correlated]   │
    └─────────────────────────────────────────────────────┘

    Quantum correlation formula for Bell state |Φ+⟩:
        E(a, b) = -cos( 2 × (a - b) )

    Expected correlations:
        E(0°,   22.5°)  = -cos(45°)  = -0.7071
        E(0°,   67.5°)  = -cos(135°) = +0.7071
        E(45°,  22.5°)  = -cos(45°)  = -0.7071
        E(45°,  67.5°)  = -cos(45°)  = -0.7071

    Expected S = |-0.7071 - 0.7071 - 0.7071 - 0.7071| = 2.828 ✅
    """

    def __init__(self):
        self.simulator = AerSimulator()

        # ── Measurement angles (radians) ──────────────────────────
        # Alice's 3 angles
        self.alice_angles = [
            np.radians(0),     # a0 = 0°
            np.radians(45),    # a1 = 45°
            np.radians(90),    # a2 = 90°
        ]

        # Bob's 3 angles — shifted by 22.5° from Alice's
        self.bob_angles = [
            np.radians(22.5),  # b0 = 22.5°
            np.radians(67.5),  # b1 = 67.5°
            np.radians(112.5), # b2 = 112.5°
        ]

        # ── CHSH test uses these 4 angle-pair combinations ────────
        # (alice_idx, bob_idx)
        # All have 22.5° or 67.5° differences → violate classical bound
        self.chsh_pairs = [
            (0, 0),   # a0=0°   vs b0=22.5°  → diff=22.5°
            (0, 1),   # a0=0°   vs b1=67.5°  → diff=67.5°
            (1, 0),   # a1=45°  vs b0=22.5°  → diff=22.5°
            (1, 1),   # a1=45°  vs b1=67.5°  → diff=22.5° (45-67.5=-22.5)
        ]

        # ── Key bits from matching/close bases ─────────────────────
        # (alice_idx, bob_idx) pairs used for key extraction
        # These have small angle differences → high correlation
        self.key_pairs = [
            (1, 0),   # a1=45°  vs b0=22.5°  → diff=22.5° → correlated
            (2, 1),   # a2=90°  vs b1=67.5°  → diff=22.5° → correlated
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Single Bell Pair Measurement
    # ─────────────────────────────────────────────────────────────────────────

    def measure_bell_pair(
            self,
            alice_angle_idx : int,
            bob_angle_idx   : int
    ) -> dict:
        """
        Simulate measuring ONE entangled Bell pair.

        Full quantum circuit:
        ┌───┐           ┌──────────────────┐ ┌─┐
        │ H │──●────────│ Ry(-2×alice_ang) │─┤M├─→ alice_bit
        └───┘  │        └──────────────────┘ └─┘
               │        ┌──────────────────┐ ┌─┐
              [X]───────│ Ry(-2×bob_ang)   │─┤M├─→ bob_bit
                        └──────────────────┘ └─┘

        The Ry rotations change the measurement basis.
        The entanglement ensures correlations follow quantum mechanics.

        Args:
            alice_angle_idx : Alice's basis index (0, 1, or 2)
            bob_angle_idx   : Bob's basis index   (0, 1, or 2)

        Returns:
            dict with bits, angles, and metadata
        """
        alice_angle = self.alice_angles[alice_angle_idx]
        bob_angle   = self.bob_angles[bob_angle_idx]

        # Build quantum circuit
        qc = QuantumCircuit(2, 2)

        # Create Bell state |Φ+⟩ = (|00⟩ + |11⟩) / √2
        qc.h(0)           # Hadamard → superposition on qubit 0
        qc.cx(0, 1)       # CNOT     → entangle qubit 0 and 1

        # Rotate each qubit into its measurement basis
        # Ry(-2θ) rotates the measurement axis by angle θ
        if alice_angle != 0:
            qc.ry(-2 * alice_angle, 0)

        if bob_angle != 0:
            qc.ry(-2 * bob_angle, 1)

        # Measure both qubits
        qc.measure(0, 0)   # qubit 0 (Alice) → classical bit 0
        qc.measure(1, 1)   # qubit 1 (Bob)   → classical bit 1

        # Run on simulator (shots=1 → single quantum event)
        job    = self.simulator.run(qc, shots=1)
        counts = job.result().get_counts(qc)

        # Parse result
        # Qiskit bit string format: "b1b0" (reversed)
        # "01" means qubit1=0, qubit0=1
        state     = list(counts.keys())[0]
        bob_bit   = int(state[0])   # leftmost  = qubit 1 = Bob
        alice_bit = int(state[1])   # rightmost = qubit 0 = Alice

        # Compute theoretical correlation for this pair
        angle_diff         = alice_angle - bob_angle
        theory_correlation = -np.cos(2 * angle_diff)

        return {
            'alice_bit'          : alice_bit,
            'bob_bit'            : bob_bit,
            'alice_angle_idx'    : alice_angle_idx,
            'bob_angle_idx'      : bob_angle_idx,
            'alice_angle_deg'    : round(np.degrees(alice_angle), 2),
            'bob_angle_deg'      : round(np.degrees(bob_angle),   2),
            'angle_diff_deg'     : round(np.degrees(angle_diff),  2),
            'theory_correlation' : round(theory_correlation,       4),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Batch Measurement
    # ─────────────────────────────────────────────────────────────────────────

    def generate_all_measurements(
            self,
            num_pairs    : int,
            alice_bases  : list,
            bob_bases    : list
    ) -> list:
        """
        Measure all Bell pairs using Alice's and Bob's chosen bases.

        Called on Alice's PC after Bob's bases are received.
        Alice simulates the full entangled pair → gets both bits.
        Bob's bit is sent to him over the classical channel.

        Args:
            num_pairs   : total pairs to simulate
            alice_bases : Alice's basis index for each pair
            bob_bases   : Bob's basis index for each pair

        Returns:
            List of measurement result dicts
        """
        results = []
        print(f"\n  [Quantum] Measuring {num_pairs} entangled Bell pairs...")
        print(f"  [Quantum] Alice angles: 0°, 45°, 90°")
        print(f"  [Quantum] Bob   angles: 22.5°, 67.5°, 112.5°")

        for i in range(num_pairs):
            result = self.measure_bell_pair(
                alice_bases[i],
                bob_bases[i]
            )
            results.append(result)

            if (i + 1) % 100 == 0:
                print(f"  [Quantum] ▶ {i+1}/{num_pairs} pairs measured...")

        print(f"  [Quantum] ✅ All {num_pairs} measurements complete")

        # Print quick sanity check
        self._print_correlation_check(results)

        return results

    def _print_correlation_check(self, results: list):
        """
        Print measured vs theoretical correlations for all angle pairs.
        Useful for debugging and verifying quantum behaviour.
        """
        print(f"\n  [Quantum] Correlation sanity check:")
        print(f"  {'Angles':25s}  {'Measured':>10s}  {'Theory':>10s}  {'Samples':>8s}")
        print(f"  {'-'*60}")

        # All unique angle combinations
        seen = {}
        for r in results:
            key = (r['alice_angle_idx'], r['bob_angle_idx'])
            if key not in seen:
                seen[key] = []
            a_val = 1 - 2 * r['alice_bit']
            b_val = 1 - 2 * r['bob_bit']
            seen[key].append(a_val * b_val)

        for (a_idx, b_idx), values in sorted(seen.items()):
            a_deg    = np.degrees(self.alice_angles[a_idx])
            b_deg    = np.degrees(self.bob_angles[b_idx])
            measured = np.mean(values)
            theory   = -np.cos(2 * (self.alice_angles[a_idx] - self.bob_angles[b_idx]))
            tag      = " ← CHSH" if (a_idx, b_idx) in self.chsh_pairs else \
                       " ← KEY"  if (a_idx, b_idx) in self.key_pairs   else ""
            print(f"  Alice {a_deg:>6.1f}° + Bob {b_deg:>6.1f}°"
                  f"  {measured:>10.4f}  {theory:>10.4f}  {len(values):>8d}{tag}")

    # ─────────────────────────────────────────────────────────────────────────
    # CHSH Inequality Test
    # ─────────────────────────────────────────────────────────────────────────

    def compute_chsh_value(self, results: list) -> dict:
        """
        Compute CHSH S-value using the 4 designated angle pairs.

        CHSH Formula:
            S = | E(a0,b0) - E(a0,b1) + E(a1,b0) + E(a1,b1) |

        Where:
            a0=0°,   a1=45°
            b0=22.5°, b1=67.5°

        Theoretical values:
            E(0°,  22.5°) = -cos(2×22.5°) = -cos(45°)  = -0.7071
            E(0°,  67.5°) = -cos(2×67.5°) = -cos(135°) = +0.7071
            E(45°, 22.5°) = -cos(2×22.5°) = -cos(45°)  = -0.7071
            E(45°, 67.5°) = -cos(2×22.5°) = -cos(45°)  = -0.7071

            S = |-0.7071 - 0.7071 - 0.7071 - 0.7071|
              = |-2.8284|
              = 2.8284 = 2√2  ✅

        Args:
            results : list of measurement dicts

        Returns:
            dict with S_value, correlators, security verdict
        """
        correlations = {}
        sample_sizes = {}

        for a_idx, b_idx in self.chsh_pairs:
            matching = [
                r for r in results
                if r['alice_angle_idx'] == a_idx
                and r['bob_angle_idx']  == b_idx
            ]

            sample_sizes[(a_idx, b_idx)] = len(matching)

            if not matching:
                correlations[(a_idx, b_idx)] = 0.0
                continue

            # E(a,b) = ⟨Alice × Bob⟩ with 0→+1, 1→-1
            total = sum(
                (1 - 2 * m['alice_bit']) * (1 - 2 * m['bob_bit'])
                for m in matching
            )
            correlations[(a_idx, b_idx)] = total / len(matching)

        # Extract the 4 correlators
        # CHSH pairs: (0,0), (0,1), (1,0), (1,1)
        E_a0b0 = correlations.get((0, 0), 0.0)
        E_a0b1 = correlations.get((0, 1), 0.0)
        E_a1b0 = correlations.get((1, 0), 0.0)
        E_a1b1 = correlations.get((1, 1), 0.0)

        # CHSH formula
        S = abs(E_a0b0 - E_a0b1 + E_a1b0 + E_a1b1)

        # Print sample sizes
        print(f"\n  [CHSH] Sample counts per angle pair:")
        for (a_idx, b_idx), size in sample_sizes.items():
            a_deg = np.degrees(self.alice_angles[a_idx])
            b_deg = np.degrees(self.bob_angles[b_idx])
            print(f"         Alice {a_deg:>6.1f}° + Bob {b_deg:>6.1f}° → {size} samples")

        return {
            'S_value'      : S,
            'E_a0b0'       : E_a0b0,   # E(0°,   22.5°)
            'E_a0b1'       : E_a0b1,   # E(0°,   67.5°)
            'E_a1b0'       : E_a1b0,   # E(45°,  22.5°)
            'E_a1b1'       : E_a1b1,   # E(45°,  67.5°)
            # Keep old keys for logger compatibility
            'E_00'         : E_a0b0,
            'E_02'         : E_a0b1,
            'E_20'         : E_a1b0,
            'E_22'         : E_a1b1,
            'correlations' : {str(k): v for k, v in correlations.items()},
            'sample_sizes' : {str(k): v for k, v in sample_sizes.items()},
            'is_secure'    : S > 2.0,
            'quantum_bound': 2 * np.sqrt(2),
            'total_pairs'  : len(results),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Key Bit Extraction
    # ─────────────────────────────────────────────────────────────────────────

    def extract_key_bits(self, results: list) -> dict:
        """
        Pull out bits from KEY pairs (matching/close bases).

        Key pairs:
            (a1=45°, b0=22.5°) → 22.5° diff → high correlation
            (a2=90°, b1=67.5°) → 22.5° diff → high correlation

        These bits form the raw shared secret.

        Args:
            results : list of measurement dicts

        Returns:
            dict with alice_bits, bob_bits, and index lists
        """
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
            'key_length'   : len(alice_key_bits),
        }