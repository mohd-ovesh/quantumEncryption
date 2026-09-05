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
                os._exit(0) # Forcefully close the whole program
            print(f"\nPartner: {message}")
        except Exception:
            print("\n[Connection closed]")
            os._exit(0)

# 1. Setup the Server
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('0.0.0.0', 12345))
server_socket.listen(1)
print("Waiting for a connection...")

# 2. Accept Client
client_socket, address = server_socket.accept()
print(f"Connected to {address}! You can now type freely.")

# 3. Start the Listening Thread
receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
receive_thread.daemon = True # Closes automatically when the main program closes
receive_thread.start()

# 4. Main Thread (Sending Loop)
while True:
    message = input()
    client_socket.send(message.encode('utf-8'))
    if message.lower() == 'exit':
        break

# Clean up
client_socket.close()
server_socket.close()