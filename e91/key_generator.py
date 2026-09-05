# e91/key_generator.py

import hashlib
import numpy as np
from typing import List

class KeyGenerator:

    def __init__(self):
        self.raw_alice_bits = []
        self.raw_bob_bits   = []
        self.final_key      = None
        self.log_data       = {}   # Collects data for logger

    def sift_key(self, alice_bits: List[int], bob_bits: List[int]):
        self.raw_alice_bits = alice_bits[:]
        self.raw_bob_bits   = bob_bits[:]
        self.log_data['sifted_length'] = len(alice_bits)
        print(f"\n[KeyGen] Sifted bits: {len(alice_bits)}")
        return len(alice_bits)

    def check_error_rate(self, sample_size: int = 20):
        if len(self.raw_alice_bits) < sample_size:
            sample_size = max(1, len(self.raw_alice_bits) // 4)

        alice_sample = self.raw_alice_bits[:sample_size]
        bob_sample   = self.raw_bob_bits[:sample_size]

        errors     = sum(a != b for a, b in zip(alice_sample, bob_sample))
        error_rate = errors / sample_size if sample_size > 0 else 0.0

        self.log_data['error_check'] = {
            'sample_size': sample_size,
            'errors'     : errors,
            'error_rate' : error_rate,
            'qber_safe'  : error_rate < 0.11
        }

        print(f"\n[KeyGen] Error Rate: {error_rate:.2%} ({errors}/{sample_size})")
        status = "✅ SECURE" if error_rate < 0.11 else "❌ SUSPICIOUS"
        print(f"[KeyGen] QBER Status: {status}")

        # Remove publicly revealed bits
        self.raw_alice_bits = self.raw_alice_bits[sample_size:]
        self.raw_bob_bits   = self.raw_bob_bits[sample_size:]

        return error_rate

    def bits_to_bytes(self, bits: List[int]) -> bytes:
        padded = bits + [0] * ((-len(bits)) % 8)
        result = bytearray()
        for i in range(0, len(padded), 8):
            result.append(int(''.join(str(b) for b in padded[i:i+8]), 2))
        return bytes(result)

    def privacy_amplification(self, bits: List[int], target_length_bytes: int = 16):
        raw_bytes = self.bits_to_bytes(bits)
        full_hash = hashlib.sha256(raw_bytes).digest()
        final_key = full_hash[:target_length_bytes]

        self.log_data['privacy_amplification'] = {
            'input_bits'          : len(bits),
            'output_bytes'        : target_length_bytes,
            'output_bits'         : target_length_bytes * 8,
            'key_hex'             : final_key.hex(),
            'hash_algorithm'      : 'SHA-256'
        }

        print(f"\n[KeyGen] Privacy amplification: {len(bits)} bits → {target_length_bytes*8} bit key")
        print(f"[KeyGen] Key: {final_key.hex()}")
        return final_key

    def generate_final_key(self, target_bytes: int = 16):
        error_rate = self.check_error_rate()

        if error_rate >= 0.11:
            print("\n[KeyGen] ❌ Aborting — channel not secure")
            return None

        if len(self.raw_alice_bits) < 8:
            print("\n[KeyGen] ❌ Not enough bits remaining")
            return None

        final_key = self.privacy_amplification(self.raw_alice_bits, target_bytes)
        self.final_key = final_key
        return final_key