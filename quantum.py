import socket
import threading
import os

def receive_messages(connection):
    """This function runs in the background and constantly listens for messages."""
    while True:
        try:
            message = connection.recv(1024).decode('utf-8')
            if not message or message.lower() == 'exit':
                print("\n[Partner disconnected]")
                os._exit(0)
            print(f"\nPartner: {message}")
        except Exception:
            print("\n[Connection closed]")
            os._exit(0)

# 1. Setup the Client
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_ip = '192.168.29.42' # IMPORTANT: Change to PC A's IP address

# 2. Connect to Server
print(f"Connecting to {server_ip}...")
client_socket.connect((server_ip, 12345))
print("Connected! You can now type freely.")

# 3. Start the Listening Thread
receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
receive_thread.daemon = True
receive_thread.start()

# 4. Main Thread (Sending Loop)
while True:
    message = input()
    client_socket.send(message.encode('utf-16'))
    if message.lower() == 'exit':
        break

# Clean up
client_socket.close()
