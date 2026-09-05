# e91/encryptor.py

import os
import hashlib
import hmac

class QuantumEncryptor:

    def __init__(self, key: bytes):
        self.key = key
        print(f"\n[Encryptor] Ready with {len(key)*8}-bit quantum key")

    def _stretch_key(self, length: int, nonce: bytes) -> bytes:
        keystream = b''
        counter   = 0
        while len(keystream) < length:
            h          = hmac.new(self.key, nonce + counter.to_bytes(4,'big'), hashlib.sha256)
            keystream += h.digest()
            counter   += 1
        return keystream[:length]

    def encrypt(self, plaintext: str) -> bytes:
        msg_bytes = plaintext.encode('utf-8')
        nonce     = os.urandom(16)
        keystream = self._stretch_key(len(msg_bytes), nonce)
        return nonce + bytes(m ^ k for m, k in zip(msg_bytes, keystream))

    def decrypt(self, data: bytes) -> str:
        nonce      = data[:16]
        ciphertext = data[16:]
        keystream  = self._stretch_key(len(ciphertext), nonce)
        return bytes(c ^ k for c, k in zip(ciphertext, keystream)).decode('utf-8')