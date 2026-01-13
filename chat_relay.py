#!/usr/bin/env python3
"""
Chat Relay - Project 02
Optional relay server that prepends '*' to nicknames
"""

import socket
import select
import sys
import signal
import pickle
import struct
import argparse
import threading
import datetime

DEFAULT_RELAY_PORT = 8900
DEFAULT_SERVER_PORT = 8800
SERVER_HOST = 'localhost'
LOG_FILE = 'relay_log.txt'


def log_message(message):
    """Write message to relay log file with timestamp."""
    try:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Error logging: {e}")


def send_message(channel, *args):
    try:
        buffer = pickle.dumps(args)
        value = socket.htonl(len(buffer))
        size = struct.pack("L", value)
        channel.send(size)
        channel.send(buffer)
        return True
    except Exception as e:
        return False


def receive_message(channel):
    try:
        size_data = channel.recv(struct.calcsize("L"))
        if not size_data:
            return ''
        size = socket.ntohl(struct.unpack("L", size_data)[0])
        buf = b""
        while len(buf) < size:
            buf += channel.recv(size - len(buf))
        return pickle.loads(buf)[0]
    except:
        return ''


class ChatRelay:
    """
    Sits between the client and the main server, acting as a pass-through or “proxy” 
    that appends '*' to the user's nickname. 
    """
    
    def __init__(self, relay_port, server_host, server_port, backlog=5):
        """Initialize relay server."""
        self.relay_port = relay_port
        self.server_host = server_host
        self.server_port = server_port
        self.relay_socket = None
        self.running = False
        self.connections = {}  # client_socket -> server_socket
        self.total_relayed = 0
        
        try:
            self.relay_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.relay_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.relay_socket.bind(('0.0.0.0', relay_port))
            self.relay_socket.listen(backlog)
            
            print(f"Chat Relay listening on port {relay_port}")
            print(f"Forwarding to {server_host}:{server_port}")
            log_message(f"Relay started: port {relay_port} -> {server_host}:{server_port}")
            
            signal.signal(signal.SIGINT, self.shutdown)
        except Exception as e:
            print(f"Error starting relay: {e}")
            sys.exit(1)
    
    def shutdown(self, signum=None, frame=None):
        """Clean shutdown."""
        print("\nshutting down relay...")
        self.running = False
        
        # Close all connections
        for client_sock, server_sock in list(self.connections.items()):
            try:
                client_sock.close()
            except:
                pass
            try:
                server_sock.close()
            except:
                pass
        
        if self.relay_socket:
            try:
                self.relay_socket.close()
            except:
                pass
        
        log_message("Relay shut down")
        sys.exit(0)
    
    def connect_to_server(self):
        """Create connection to main chat server."""
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self.server_host, self.server_port))
            return server_sock
        except Exception as e:
            print(f"Error connecting to server: {e}")
            return None
    
    def rewrite_nickname(self, data):
        """Prepend '*' to nickname in NAME message."""
        if data.startswith('NAME: '):
            nickname = data.split('NAME: ')[1]
            if not nickname.startswith('*'):
                return f'NAME: *{nickname}'
        return data
    
    def handle_client_connection(self, client_sock, client_addr):
        print(f"New client connection from {client_addr}")
        log_message(f"Client connected: {client_addr}")
        
        # Connect to main server
        server_sock = self.connect_to_server()
        if not server_sock:
            print(f"Failed to connect to server for client {client_addr}")
            client_sock.close()
            return
        
        # Store connection pair
        self.connections[client_sock] = server_sock
        self.connections[server_sock] = client_sock
        
        print(f"Relay established for {client_addr}")
        log_message(f"Relay established: {client_addr} <-> {self.server_host}:{self.server_port}")
        
        # Start bidirectional forwarding
        client_thread = threading.Thread(
            target=self.forward_data,
            args=(client_sock, server_sock, True, client_addr),
            daemon=True
        )
        server_thread = threading.Thread(
            target=self.forward_data,
            args=(server_sock, client_sock, False, client_addr),
            daemon=True
        )
        
        client_thread.start()
        server_thread.start()
    
    def forward_data(self, source_sock, dest_sock, is_client_to_server, client_addr):
        """Forward data between client and server."""
        direction = "Client->Server" if is_client_to_server else "Server->Client"
        first_message = True
        
        try:
            while self.running:
                data = receive_message(source_sock)
                
                if not data:
                    # Connection closed
                    print(f"Connection closed: {client_addr} ({direction})")
                    log_message(f"Connection closed: {client_addr} ({direction})")
                    break
                
                # Rewrite nickname on first client message
                if is_client_to_server and first_message:
                    if data.startswith('NAME: '):
                        original_data = data
                        data = self.rewrite_nickname(data)
                        print(f"Rewrote nickname: {original_data} -> {data}")
                        log_message(f"Nickname rewrite: {original_data} -> {data}")
                    first_message = False
                
                # Forward the message
                if not send_message(dest_sock, data):
                    break
                
                self.total_relayed += 1
                
                # Log relayed traffic 
                if len(data) < 100:  # Only log short messages
                    log_message(f"{direction}: {data}")
        
        except Exception as e:
            print(f"Forward error ({direction}): {e}")
        finally:
            # Clean up both sockets
            self.cleanup_connection(source_sock, dest_sock, client_addr)
    
    def cleanup_connection(self, sock1, sock2, client_addr):
        """Clean up connection pair."""
        try:
            if sock1 in self.connections:
                del self.connections[sock1]
            if sock2 in self.connections:
                del self.connections[sock2]
            
            sock1.close()
            sock2.close()
            
            print(f"Cleaned up relay for {client_addr}")
            log_message(f"Relay cleaned up: {client_addr}")
        except:
            pass
    
    def print_stats(self):
        """Print periodic statistics."""
        while self.running:
            import time
            time.sleep(30)
            active_connections = len(self.connections) // 2  # Divide by 2 as we store both directions
            print(f"\n=== Relay Stats ===")
            print(f"Active Connections: {active_connections}")
            print(f"Total Messages Relayed: {self.total_relayed}")
            print(f"===================\n")
    
    def run(self):
        """Main relay loop."""
        self.running = True
        
        print("Relay running. Press Ctrl+C to stop.\n")
        
        # Start stats thread
        stats_thread = threading.Thread(target=self.print_stats, daemon=True)
        stats_thread.start()
        
        while self.running:
            try:
                # Accept client connections
                readable, _, _ = select.select([self.relay_socket], [], [], 1)
                
                for sock in readable:
                    client_sock, client_addr = sock.accept()
                    
                    # Handle in new thread
                    handler = threading.Thread(
                        target=self.handle_client_connection,
                        args=(client_sock, client_addr),
                        daemon=True
                    )
                    handler.start()
            
            except select.error as e:
                print(f"Select error: {e}")
                break
            except Exception as e:
                print(f"Error: {e}")
                break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Chat Relay - Chat Project')
    parser.add_argument('--relay-port', type=int, default=DEFAULT_RELAY_PORT,
                        help=f'Relay listening port (default: {DEFAULT_RELAY_PORT})')
    parser.add_argument('--server-host', type=str, default=SERVER_HOST,
                        help=f'Main server host (default: {SERVER_HOST})')
    parser.add_argument('--server-port', type=int, default=DEFAULT_SERVER_PORT,
                        help=f'Main server port (default: {DEFAULT_SERVER_PORT})')
    args = parser.parse_args()
    
    relay = ChatRelay(args.relay_port, args.server_host, args.server_port)
    relay.run()


if __name__ == '__main__':
    main()
