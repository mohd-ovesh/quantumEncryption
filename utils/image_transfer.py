# # utils/image_transfer.py

# import os
# import math
# import hashlib
# import datetime
# from typing import Callable

# from utils.protocol import (
#     send_message, receive_message,
#     MSG_IMAGE_HEADER, MSG_IMAGE_CHUNK,
#     MSG_IMAGE_DONE,   MSG_IMAGE_ACK
# )

# # ── Constants ──────────────────────────────────────────────────────────────
# CHUNK_SIZE       = 8192              # 8 KB per chunk
# SUPPORTED_TYPES  = {
#     '.png'  : 'image/png',
#     '.jpg'  : 'image/jpeg',
#     '.jpeg' : 'image/jpeg',
#     '.gif'  : 'image/gif',
#     '.bmp'  : 'image/bmp',
#     '.webp' : 'image/webp',
# }
# RECEIVED_DIR = os.path.join(
#     os.path.dirname(__file__), '..', 'received_images'
# )

# # ── Sender Side ─────────────────────────────────────────────────────────────

# def send_image(
#         sock,
#         encryptor,
#         file_path   : str,
#         sender_name : str,
#         logger      = None,
#         progress_cb : Callable = None
# ) -> bool:
#     """
#     Read an image file, encrypt it in chunks, and send to peer.

#     Protocol:
#     ─────────────────────────────────────────────────────────
#     1. Send MSG_IMAGE_HEADER  (filename, size, hash, chunks)
#     2. For each chunk:
#            encrypt chunk bytes
#            send MSG_IMAGE_CHUNK (chunk_index, encrypted data)
#     3. Send MSG_IMAGE_DONE
#     4. Wait for MSG_IMAGE_ACK from receiver

#     Args:
#         sock        : connected socket
#         encryptor   : QuantumEncryptor instance
#         file_path   : full path to image file
#         sender_name : your name (for display)
#         logger      : QuantumLogger instance (optional)
#         progress_cb : optional callback(percent_done)

#     Returns:
#         True if receiver confirmed receipt, False otherwise
#     """
#     # ── Validate file ──────────────────────────────────────────────
#     if not os.path.exists(file_path):
#         print(f"  ❌ File not found: {file_path}")
#         return False

#     ext = os.path.splitext(file_path)[1].lower()
#     if ext not in SUPPORTED_TYPES:
#         print(f"  ❌ Unsupported type '{ext}'. Supported: {list(SUPPORTED_TYPES.keys())}")
#         return False

#     # ── Read file ──────────────────────────────────────────────────
#     with open(file_path, 'rb') as f:
#         image_bytes = f.read()

#     file_name   = os.path.basename(file_path)
#     file_size   = len(image_bytes)
#     file_hash   = hashlib.sha256(image_bytes).hexdigest()
#     mime_type   = SUPPORTED_TYPES[ext]
#     num_chunks  = math.ceil(file_size / CHUNK_SIZE)

#     print(f"\n  📸 Sending image: {file_name}")
#     print(f"     Size     : {file_size:,} bytes ({file_size/1024:.1f} KB)")
#     print(f"     Chunks   : {num_chunks}  ({CHUNK_SIZE//1024} KB each)")
#     print(f"     SHA-256  : {file_hash[:32]}...")

#     # ── Send header ────────────────────────────────────────────────
#     send_message(sock, MSG_IMAGE_HEADER, {
#         'file_name'  : file_name,
#         'file_size'  : file_size,
#         'file_hash'  : file_hash,
#         'mime_type'  : mime_type,
#         'num_chunks' : num_chunks,
#         'sender'     : sender_name,
#         'timestamp'  : datetime.datetime.now().isoformat()
#     })

#     # ── Send chunks ────────────────────────────────────────────────
#     print(f"\n  Encrypting and sending chunks:")
#     bytes_sent = 0

#     for i in range(num_chunks):
#         # Slice chunk from raw bytes
#         start = i * CHUNK_SIZE
#         end   = min(start + CHUNK_SIZE, file_size)
#         chunk = image_bytes[start:end]

#         # Encrypt this chunk
#         encrypted_chunk = encryptor.encrypt_bytes(chunk)

#         # Send as list of ints (JSON serializable)
#         send_message(sock, MSG_IMAGE_CHUNK, {
#             'chunk_index'     : i,
#             'total_chunks'    : num_chunks,
#             'encrypted_data'  : list(encrypted_chunk),
#             'original_size'   : len(chunk)
#         })

#         bytes_sent += len(chunk)
#         percent     = (i + 1) / num_chunks * 100

#         # Progress bar
#         bar_len  = 30
#         filled   = int(bar_len * (i + 1) / num_chunks)
#         bar      = '█' * filled + '░' * (bar_len - filled)
#         print(f"  [{bar}] {percent:>5.1f}%  chunk {i+1}/{num_chunks}", end='\r')

#         if progress_cb:
#             progress_cb(percent)

#     print(f"\n  ✅ All {num_chunks} chunks sent ({bytes_sent:,} bytes)")

#     # ── Send done signal ───────────────────────────────────────────
#     send_message(sock, MSG_IMAGE_DONE, {
#         'file_name' : file_name,
#         'file_hash' : file_hash,
#         'total_sent': bytes_sent
#     })

#     # ── Wait for ACK from receiver ─────────────────────────────────
#     print(f"  ⏳ Waiting for receiver to confirm...")
#     try:
#         ack = receive_message(sock)
#         if ack['type'] == MSG_IMAGE_ACK:
#             status    = ack['payload'].get('status', 'unknown')
#             peer_hash = ack['payload'].get('received_hash', '')

#             if status == 'ok' and peer_hash == file_hash:
#                 print(f"  ✅ Image received and verified by peer!")
#                 if logger:
#                     logger.log_image_transfer(
#                         direction  = 'SENT',
#                         file_name  = file_name,
#                         file_size  = file_size,
#                         file_hash  = file_hash,
#                         num_chunks = num_chunks,
#                         success    = True
#                     )
#                 return True
#             else:
#                 print(f"  ❌ Peer reported error: {status}")
#                 return False
#     except Exception as e:
#         print(f"  ❌ No ACK received: {e}")
#         return False

# # ── Receiver Side ───────────────────────────────────────────────────────────

# def receive_image(
#         sock,
#         encryptor,
#         header      : dict,
#         my_name     : str,
#         logger      = None
# ) -> str | None:
#     """
#     Receive an image after getting its header.

#     Called automatically by the receive_loop when MSG_IMAGE_HEADER arrives.

#     Args:
#         sock      : connected socket
#         encryptor : QuantumEncryptor instance
#         header    : the payload from MSG_IMAGE_HEADER
#         my_name   : your name (for display)
#         logger    : QuantumLogger instance (optional)

#     Returns:
#         saved file path if successful, None if failed
#     """
#     file_name    = header['file_name']
#     file_size    = header['file_size']
#     expected_hash= header['file_hash']
#     num_chunks   = header['num_chunks']
#     sender       = header.get('sender', 'Peer')

#     print(f"\n  📥 Incoming image from {sender}:")
#     print(f"     File     : {file_name}")
#     print(f"     Size     : {file_size:,} bytes ({file_size/1024:.1f} KB)")
#     print(f"     Chunks   : {num_chunks}")

#     # ── Prepare output directory ───────────────────────────────────
#     os.makedirs(RECEIVED_DIR, exist_ok=True)

#     # Add timestamp to avoid overwriting existing files
#     ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
#     base, ext = os.path.splitext(file_name)
#     save_name = f"{base}_{ts}{ext}"
#     save_path = os.path.join(RECEIVED_DIR, save_name)

#     # ── Receive and decrypt chunks ─────────────────────────────────
#     print(f"\n  Receiving and decrypting chunks:")
#     received_chunks = {}

#     try:
#         while len(received_chunks) < num_chunks:
#             msg = receive_message(sock)

#             if msg['type'] == MSG_IMAGE_CHUNK:
#                 payload     = msg['payload']
#                 chunk_idx   = payload['chunk_index']
#                 enc_data    = bytes(payload['encrypted_data'])

#                 # Decrypt this chunk
#                 chunk_bytes = encryptor.decrypt_bytes(enc_data)
#                 received_chunks[chunk_idx] = chunk_bytes

#                 # Progress bar
#                 progress  = len(received_chunks) / num_chunks * 100
#                 bar_len   = 30
#                 filled    = int(bar_len * len(received_chunks) / num_chunks)
#                 bar       = '█' * filled + '░' * (bar_len - filled)
#                 print(f"  [{bar}] {progress:>5.1f}%  chunk {chunk_idx+1}/{num_chunks}", end='\r')

#             elif msg['type'] == MSG_IMAGE_DONE:
#                 print(f"\n  ✅ All chunks received")
#                 break

#             elif msg['type'] == MSG_ABORT:
#                 print(f"\n  ❌ Transfer aborted by sender")
#                 send_message(sock, MSG_IMAGE_ACK, {
#                     'status'       : 'aborted',
#                     'received_hash': ''
#                 })
#                 return None

#     except Exception as e:
#         print(f"\n  ❌ Error receiving chunks: {e}")
#         send_message(sock, MSG_IMAGE_ACK, {
#             'status'       : f'error: {e}',
#             'received_hash': ''
#         })
#         return None

#     # ── Reassemble image ───────────────────────────────────────────
#     print(f"  🔧 Reassembling {len(received_chunks)} chunks...")

#     if len(received_chunks) != num_chunks:
#         print(f"  ❌ Missing chunks! Got {len(received_chunks)}/{num_chunks}")
#         send_message(sock, MSG_IMAGE_ACK, {
#             'status'       : 'incomplete',
#             'received_hash': ''
#         })
#         return None

#     # Reassemble in order
#     image_bytes = b''.join(
#         received_chunks[i] for i in range(num_chunks)
#     )

#     # ── Verify integrity ───────────────────────────────────────────
#     received_hash = hashlib.sha256(image_bytes).hexdigest()

#     if received_hash == expected_hash:
#         print(f"  ✅ Integrity check PASSED")
#         print(f"     SHA-256: {received_hash[:32]}...")
#     else:
#         print(f"  ❌ Integrity check FAILED!")
#         print(f"     Expected: {expected_hash[:32]}...")
#         print(f"     Got     : {received_hash[:32]}...")
#         send_message(sock, MSG_IMAGE_ACK, {
#             'status'       : 'hash_mismatch',
#             'received_hash': received_hash
#         })
#         return None

#     # ── Save to disk ───────────────────────────────────────────────
#     with open(save_path, 'wb') as f:
#         f.write(image_bytes)

#     print(f"  💾 Saved to: {save_path}")

#     # ── Send ACK ───────────────────────────────────────────────────
#     send_message(sock, MSG_IMAGE_ACK, {
#         'status'       : 'ok',
#         'received_hash': received_hash,
#         'saved_as'     : save_name
#     })

#     if logger:
#         logger.log_image_transfer(
#             direction  = 'RECEIVED',
#             file_name  = save_name,
#             file_size  = file_size,
#             file_hash  = received_hash,
#             num_chunks = num_chunks,
#             success    = True
#         )

#     return save_path

# utils/image_transfer.py

import os
import math
import hashlib
import datetime
from typing import Callable

from utils.protocol import (
    send_message, receive_message,
    MSG_IMAGE_HEADER, MSG_IMAGE_CHUNK,
    MSG_IMAGE_DONE,   MSG_IMAGE_ACK
)

# ── Constants ──────────────────────────────────────────────────────────────
CHUNK_SIZE       = 8192              # 8 KB per chunk
SUPPORTED_TYPES  = {
    '.png'  : 'image/png',
    '.jpg'  : 'image/jpeg',
    '.jpeg' : 'image/jpeg',
    '.gif'  : 'image/gif',
    '.bmp'  : 'image/bmp',
    '.webp' : 'image/webp',
}
RECEIVED_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'received_images'
)

# ── Sender Side ─────────────────────────────────────────────────────────────

def send_image(
        sock,
        encryptor,
        file_path   : str,
        sender_name : str,
        logger      = None,
        progress_cb : Callable = None
) -> bool:
    """
    Read an image file, encrypt it in chunks, and send to peer.

    Protocol:
    ─────────────────────────────────────────────────────────
    1. Send MSG_IMAGE_HEADER  (filename, size, hash, chunks)
    2. For each chunk:
           encrypt chunk bytes
           send MSG_IMAGE_CHUNK (chunk_index, encrypted data)
    3. Send MSG_IMAGE_DONE

    Args:
        sock        : connected socket
        encryptor   : QuantumEncryptor instance
        file_path   : full path to image file
        sender_name : your name (for display)
        logger      : QuantumLogger instance (optional)
        progress_cb : optional callback(percent_done)

    Returns:
        True if transfer completed successfully.
    """
    # ── Validate file ──────────────────────────────────────────────
    if not os.path.exists(file_path):
        print(f"  ❌ File not found: {file_path}")
        return False

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_TYPES:
        print(f"  ❌ Unsupported type '{ext}'. Supported: {list(SUPPORTED_TYPES.keys())}")
        return False

    # ── Read file ──────────────────────────────────────────────────
    with open(file_path, 'rb') as f:
        image_bytes = f.read()

    file_name   = os.path.basename(file_path)
    file_size   = len(image_bytes)
    file_hash   = hashlib.sha256(image_bytes).hexdigest()
    mime_type   = SUPPORTED_TYPES[ext]
    num_chunks  = math.ceil(file_size / CHUNK_SIZE)

    print(f"\n  📸 Sending image: {file_name}")
    print(f"     Size     : {file_size:,} bytes ({file_size/1024:.1f} KB)")
    print(f"     Chunks   : {num_chunks}  ({CHUNK_SIZE//1024} KB each)")
    print(f"     SHA-256  : {file_hash[:32]}...")

    # ── Send header ────────────────────────────────────────────────
    send_message(sock, MSG_IMAGE_HEADER, {
        'file_name'  : file_name,
        'file_size'  : file_size,
        'file_hash'  : file_hash,
        'mime_type'  : mime_type,
        'num_chunks' : num_chunks,
        'sender'     : sender_name,
        'timestamp'  : datetime.datetime.now().isoformat()
    })

    # ── Send chunks ────────────────────────────────────────────────
    print(f"\n  Encrypting and sending chunks:")
    bytes_sent = 0

    for i in range(num_chunks):
        # Slice chunk from raw bytes
        start = i * CHUNK_SIZE
        end   = min(start + CHUNK_SIZE, file_size)
        chunk = image_bytes[start:end]

        # Encrypt this chunk
        encrypted_chunk = encryptor.encrypt_bytes(chunk)

        # Send as list of ints (JSON serializable)
        send_message(sock, MSG_IMAGE_CHUNK, {
            'chunk_index'     : i,
            'total_chunks'    : num_chunks,
            'encrypted_data'  : list(encrypted_chunk),
            'original_size'   : len(chunk)
        })

        bytes_sent += len(chunk)
        percent     = (i + 1) / num_chunks * 100

        # Progress bar
        bar_len  = 30
        filled   = int(bar_len * (i + 1) / num_chunks)
        bar      = '█' * filled + '░' * (bar_len - filled)
        print(f"  [{bar}] {percent:>5.1f}%  chunk {i+1}/{num_chunks}", end='\r')

        if progress_cb:
            progress_cb(percent)

    print(f"\n  ✅ All {num_chunks} chunks sent ({bytes_sent:,} bytes)")

    # ── Send done signal ───────────────────────────────────────────
    send_message(sock, MSG_IMAGE_DONE, {
        'file_name' : file_name,
        'file_hash' : file_hash,
        'total_sent': bytes_sent
    })

    # ── Finish without waiting for ACK ─────────────────────────────
    if logger:
        logger.log_image_transfer(
            direction  = 'SENT',
            file_name  = file_name,
            file_size  = file_size,
            file_hash  = file_hash,
            num_chunks = num_chunks,
            success    = True
        )
    return True

# ── Receiver Side ───────────────────────────────────────────────────────────

def receive_image(
        sock,
        encryptor,
        header      : dict,
        my_name     : str,
        logger      = None
) -> str | None:
    """
    Receive an image after getting its header.

    Called automatically by the receive_loop when MSG_IMAGE_HEADER arrives.

    Args:
        sock      : connected socket
        encryptor : QuantumEncryptor instance
        header    : the payload from MSG_IMAGE_HEADER
        my_name   : your name (for display)
        logger    : QuantumLogger instance (optional)

    Returns:
        saved file path if successful, None if failed
    """
    file_name    = header['file_name']
    file_size    = header['file_size']
    expected_hash= header['file_hash']
    num_chunks   = header['num_chunks']
    sender       = header.get('sender', 'Peer')

    print(f"\n  📥 Incoming image from {sender}:")
    print(f"     File     : {file_name}")
    print(f"     Size     : {file_size:,} bytes ({file_size/1024:.1f} KB)")
    print(f"     Chunks   : {num_chunks}")

    # ── Prepare output directory ───────────────────────────────────
    os.makedirs(RECEIVED_DIR, exist_ok=True)

    # Add timestamp to avoid overwriting existing files
    ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(file_name)
    save_name = f"{base}_{ts}{ext}"
    save_path = os.path.join(RECEIVED_DIR, save_name)

    # ── Receive and decrypt chunks ─────────────────────────────────
    print(f"\n  Receiving and decrypting chunks:")
    received_chunks = {}

    try:
        while len(received_chunks) < num_chunks:
            msg = receive_message(sock)

            if msg['type'] == MSG_IMAGE_CHUNK:
                payload     = msg['payload']
                chunk_idx   = payload['chunk_index']
                enc_data    = bytes(payload['encrypted_data'])

                # Decrypt this chunk
                chunk_bytes = encryptor.decrypt_bytes(enc_data)
                received_chunks[chunk_idx] = chunk_bytes

                # Progress bar
                progress  = len(received_chunks) / num_chunks * 100
                bar_len   = 30
                filled    = int(bar_len * len(received_chunks) / num_chunks)
                bar       = '█' * filled + '░' * (bar_len - filled)
                print(f"  [{bar}] {progress:>5.1f}%  chunk {chunk_idx+1}/{num_chunks}", end='\r')

            elif msg['type'] == MSG_IMAGE_DONE:
                print(f"\n  ✅ All chunks received")
                break

            elif msg['type'] == MSG_ABORT:
                print(f"\n  ❌ Transfer aborted by sender")
                return None

    except Exception as e:
        print(f"\n  ❌ Error receiving chunks: {e}")
        return None

    # ── Reassemble image ───────────────────────────────────────────
    print(f"  🔧 Reassembling {len(received_chunks)} chunks...")

    if len(received_chunks) != num_chunks:
        print(f"  ❌ Missing chunks! Got {len(received_chunks)}/{num_chunks}")
        return None

    # Reassemble in order
    image_bytes = b''.join(
        received_chunks[i] for i in range(num_chunks)
    )

    # ── Verify integrity ───────────────────────────────────────────
    received_hash = hashlib.sha256(image_bytes).hexdigest()

    if received_hash == expected_hash:
        print(f"  ✅ Integrity check PASSED")
        print(f"     SHA-256: {received_hash[:32]}...")
    else:
        print(f"  ❌ Integrity check FAILED!")
        print(f"     Expected: {expected_hash[:32]}...")
        print(f"     Got     : {received_hash[:32]}...")
        return None

    # ── Save to disk ───────────────────────────────────────────────
    with open(save_path, 'wb') as f:
        f.write(image_bytes)

    print(f"  💾 Saved to: {save_path}")

    if logger:
        logger.log_image_transfer(
            direction  = 'RECEIVED',
            file_name  = save_name,
            file_size  = file_size,
            file_hash  = received_hash,
            num_chunks = num_chunks,
            success    = True
        )

    return save_path