# e91/encryptor.py

import os
import hashlib
import hmac

class QuantumEncryptor:
    """
    Encrypts/Decrypts messages and binary data using quantum-derived key.
    """

    def __init__(self, key: bytes):
        self.key = key
        print(f"\n  [Encryptor] Ready with {len(key)*8}-bit quantum key")

    def _stretch_key(self, length: int, nonce: bytes) -> bytes:
        """Generate keystream of given length using HMAC-SHA256."""
        keystream = b''
        counter   = 0
        while len(keystream) < length:
            h          = hmac.new(
                self.key,
                nonce + counter.to_bytes(4, 'big'),
                hashlib.sha256
            )
            keystream += h.digest()
            counter   += 1
        return keystream[:length]

    # ── Text encryption (for chat messages) ───────────────────────

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a text string. Returns nonce + ciphertext."""
        return self.encrypt_bytes(plaintext.encode('utf-8'))

    def decrypt(self, data: bytes) -> str:
        """Decrypt bytes back to text string."""
        return self.decrypt_bytes(data).decode('utf-8')

    # ── Binary encryption (for images and files) ──────────────────

    def encrypt_bytes(self, data: bytes) -> bytes:
        """
        Encrypt raw bytes (works for any binary data).

        Format: [16-byte nonce] + [encrypted data]

        Args:
            data : raw bytes to encrypt

        Returns:
            nonce + ciphertext as bytes
        """
        nonce     = os.urandom(16)
        keystream = self._stretch_key(len(data), nonce)
        cipher    = bytes(d ^ k for d, k in zip(data, keystream))
        return nonce + cipher

    def decrypt_bytes(self, data: bytes) -> bytes:
        """
        Decrypt raw bytes.

        Args:
            data : nonce + ciphertext

        Returns:
            original plaintext bytes
        """
        nonce      = data[:16]
        ciphertext = data[16:]
        keystream  = self._stretch_key(len(ciphertext), nonce)
        return bytes(c ^ k for c, k in zip(ciphertext, keystream))