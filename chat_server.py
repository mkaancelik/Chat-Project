#!/usr/bin/env python3
"""Chat Server -  Chat Project"""

import socket
import select
import sys
import signal
import pickle
import struct
import argparse
import threading
import datetime
import time
import json
import random
import string
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
import asyncio
import websockets

# Configuration
DEFAULT_CHAT_PORT = 8800
DEFAULT_HTTP_PORT = 8080
DEFAULT_WS_PORT = 8081
SERVER_HOST = '0.0.0.0'
LOG_FILE = 'chat_log.txt'
MESSAGE_RATE_LIMIT = 10  # messages per minute
RATE_LIMIT_WINDOW = 60  # seconds

# Global message buffer for web interface
message_buffer = []
MAX_BUFFER_SIZE = 1000

# WebSocket clients
ws_clients = set()

# Event loop for websocket
ws_loop = None


def log_message(message, log_file=LOG_FILE):
    """Message logging."""
    try:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
        
        # Add to message buffer
        message_buffer.append(log_entry)
        if len(message_buffer) > MAX_BUFFER_SIZE:
            message_buffer.pop(0)
        
        # Broadcast to websocket clients
        if ws_loop and ws_clients:
            asyncio.run_coroutine_threadsafe(
                broadcast_to_websockets(log_entry), 
                ws_loop
            )
    except Exception as e:
        print(f"Error logging: {e}")


async def broadcast_to_websockets(message):
    """Send message to websocket clients."""
    if ws_clients:
        disconnected = set()
        for client in ws_clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                print(f"WebSocket send error: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        for client in disconnected:
            ws_clients.discard(client)


def send_message(channel, *args):
    try:
        buffer = pickle.dumps(args)
        value = socket.htonl(len(buffer))
        size = struct.pack("L", value)
        channel.send(size)
        channel.send(buffer)
        return True
    except Exception as e:
        print(f"Error sending: {e}")
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


class RateLimiter:
    """Rate limiter for spam."""
    
    def __init__(self, max_messages, time_window):
        self.max_messages = max_messages
        self.time_window = time_window
        self.message_times = {}
    
    def check_rate(self, client_id):
        """Check if client is in rate limit."""
        current_time = time.time()
        
        if client_id not in self.message_times:
            self.message_times[client_id] = []
        
        # Remove old messages outside the time window
        self.message_times[client_id] = [
            t for t in self.message_times[client_id] 
            if current_time - t < self.time_window
        ]
        
        # Check if limit exceeded
        if len(self.message_times[client_id]) >= self.max_messages:
            return False
        
        # Add current message time
        self.message_times[client_id].append(current_time)
        return True
    
    def remove_client(self, client_id):
        """Remove client from rate limiter."""
        if client_id in self.message_times:
            del self.message_times[client_id]


class ChatServer:
    
    def __init__(self, chat_port, http_port, ws_port, backlog=5):
        """Initialize server."""
        self.chat_port = chat_port
        self.http_port = http_port
        self.ws_port = ws_port
        self.clients = 0
        self.clientmap = {}  # socket -> (address, nickname)
        self.nickname_map = {}  # nickname -> socket
        self.outputs = []
        self.server = None
        self.running = False
        self.rate_limiter = RateLimiter(MESSAGE_RATE_LIMIT, RATE_LIMIT_WINDOW)
        self.total_messages = 0
        self.private_messages = 0
        self.offline_messages = {}  # nickname -> [(sender, message, timestamp)]
        
        try:
            # Setup chat server
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((SERVER_HOST, chat_port))
            self.server.listen(backlog)
            print(f"Chat Server listening on {SERVER_HOST}:{chat_port}")
            log_message(f"Chat Server started on {SERVER_HOST}:{chat_port}")
            
            # Start HTTP server in separate thread
            self.http_thread = threading.Thread(target=self.run_http_server, daemon=True)
            self.http_thread.start()
            
            # Start WebSocket server in separate thread
            self.ws_thread = threading.Thread(target=self.run_websocket_server, daemon=True)
            self.ws_thread.start()
            
            signal.signal(signal.SIGINT, self.shutdown)
        except Exception as e:
            print(f"Error starting server: {e}")
            sys.exit(1)
    
    def run_http_server(self):
        try:
            handler = self.http_handler()
            httpd = HTTPServer((SERVER_HOST, self.http_port), handler)
            print(f"HTTP Server listening on {SERVER_HOST}:{self.http_port}")
            log_message(f"HTTP Server started on {SERVER_HOST}:{self.http_port}")
            httpd.serve_forever()
        except Exception as e:
            print(f"HTTP Server error: {e}")
    
    def run_websocket_server(self):
        """Run WebSocket server for real-time updates."""
        global ws_loop
        
        async def handler(websocket):
            # Add client to set
            ws_clients.add(websocket)
            print(f"WebSocket client connected. Total: {len(ws_clients)}")
            
            try:
                # Send existing messages
                for msg in message_buffer:
                    await websocket.send(msg)
                
                # Keep connection alive
                await websocket.wait_closed()
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"WebSocket handler error: {e}")
            finally:
                ws_clients.discard(websocket)
                print(f"WebSocket client disconnected. Total: {len(ws_clients)}")
        
        async def start_server():
            async with websockets.serve(handler, SERVER_HOST, self.ws_port):
                print(f"WebSocket Server listening on {SERVER_HOST}:{self.ws_port}")
                log_message(f"WebSocket Server started on {SERVER_HOST}:{self.ws_port}")
                await asyncio.Future()  # run forever
        
        try:
            # Create and set the event loop for this thread
            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            ws_loop.run_until_complete(start_server())
        except Exception as e:
            print(f"WebSocket Server error: {e}")
    
    def http_handler(self):
        """Create HTTP request handler."""
        server_ref = self
        
        class ChatHTTPHandler(SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    html = server_ref.generate_html()
                    self.wfile.write(html.encode())
                elif self.path == '/api/messages':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    data = json.dumps({'messages': message_buffer})
                    self.wfile.write(data.encode())
                elif self.path == '/api/stats':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    stats = {
                        'clients': server_ref.clients,
                        'total_messages': server_ref.total_messages,
                        'private_messages': server_ref.private_messages
                    }
                    self.wfile.write(json.dumps(stats).encode())
                else:
                    self.send_error(404)
            
            def log_message(self, format, *args):
                pass  # Suppress HTTP logs
        
        return ChatHTTPHandler
    
    def generate_html(self):
        """Generate HTML for web page."""
        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            html_file_path = os.path.join(script_dir, 'chat_monitor.html')
            
            # Read the HTML template file
            with open(html_file_path, 'r', encoding='utf-8') as f:
                html_template = f.read()
            
            # Replace placeholders with actual values
            html_content = html_template.replace('{{CLIENT_COUNT}}', str(self.clients))
            html_content = html_content.replace('{{MESSAGE_COUNT}}', str(self.total_messages))
            html_content = html_content.replace('{{PRIVATE_COUNT}}', str(self.private_messages))
            html_content = html_content.replace('{{WS_PORT}}', str(self.ws_port))
            
            return html_content
        except FileNotFoundError:
            return "<html><body><h1>Error: chat_monitor.html not found</h1></body></html>"
        except Exception as e:
            return f"<html><body><h1>Error loading HTML: {e}</h1></body></html>"
    
    def shutdown(self, signum=None, frame=None):
        """Clean shutdown."""
        print("\nShutting down server...")
        self.running = False
        for output in self.outputs:
            try:
                output.close()
            except:
                pass
        if self.server:
            try:
                self.server.close()
            except:
                pass
        log_message("Server shut down")
        sys.exit(0)
    
    def generate_unique_nickname(self, base_nickname):
        """Generate unique nickname."""
        if base_nickname not in self.nickname_map:
            return base_nickname
        
        # Add random suffix
        while True:
            suffix = ''.join(random.choices(string.digits, k=3))
            new_nickname = f"{base_nickname}{suffix}"
            if new_nickname not in self.nickname_map:
                return new_nickname
    
    def get_client_name(self, client):
        """Get the name of the client."""
        info = self.clientmap.get(client)
        if info:
            return info[1]
        return "Unknown"
    
    def broadcast(self, message, exclude=None):
        """Send message to all clients."""
        for output in self.outputs:
            if output != exclude:
                send_message(output, message)
    
    def send_private_message(self, sender_sock, target_nickname, message):
        """Send private message to target user."""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        sender_name = self.get_client_name(sender_sock)
        
        if target_nickname in self.nickname_map:
            target_sock = self.nickname_map[target_nickname]
            pm_msg = f"[{timestamp}] PRIVATE from {sender_name}: {message}"
            send_message(target_sock, pm_msg)
            send_message(sender_sock, f"[{timestamp}] PRIVATE to {target_nickname}: {message}")
            
            log_message(f"PRIVATE [{sender_name} -> {target_nickname}]: {message}")
            self.private_messages += 1
            return True
        else:
            # User offline - save message
            if target_nickname not in self.offline_messages:
                self.offline_messages[target_nickname] = []
            self.offline_messages[target_nickname].append((sender_name, message, timestamp))
            
            send_message(sender_sock, f"User {target_nickname} is offline. Message saved for delivery.")
            log_message(f"OFFLINE MESSAGE [{sender_name} -> {target_nickname}]: {message}")
            return False
    
    def deliver_offline_messages(self, nickname, client_sock):
        """Deliver offline messages to newly connected user."""
        if nickname in self.offline_messages:
            messages = self.offline_messages[nickname]
            for sender, msg, timestamp in messages:
                pm_msg = f"[{timestamp}] OFFLINE MESSAGE from {sender}: {msg}"
                send_message(client_sock, pm_msg)
            del self.offline_messages[nickname]
            log_message(f"Delivered {len(messages)} offline messages to {nickname}")
    
    def send_user_list(self, client_sock):
        """Send list of connected users to client."""
        user_list = list(self.nickname_map.keys())
        send_message(client_sock, f"USERLIST:{','.join(user_list)}")
    
    def run(self):
        """Main server loop."""
        inputs = [self.server]
        self.outputs = []
        self.running = True
        
        print("Server running. Press Ctrl+C to stop.\n")
        print(f"Web interface: http://localhost:{self.http_port}")
        
        # Start stats monitoring thread
        stats_thread = threading.Thread(target=self.print_stats, daemon=True)
        stats_thread.start()
        
        while self.running:
            try:
                readable, writeable, exceptional = select.select(inputs, self.outputs, inputs, 1)
            except select.error as e:
                print(f"Select error: {e}")
                break
            
            for sock in readable:
                if sock == self.server:
                    self.handle_new_connection(inputs)
                else:
                    self.handle_client_message(sock, inputs)
            
            for sock in exceptional:
                self.handle_client_error(sock, inputs)
    
    def print_stats(self):
        """Print periodic stats."""
        while self.running:
            time.sleep(30)
            print(f"\n=== Server Stats ===")
            print(f"Connected Clients: {self.clients}")
            print(f"Total Messages: {self.total_messages}")
            print(f"Private Messages: {self.private_messages}")
            print(f"WebSocket Clients: {len(ws_clients)}")
            print(f"==================\n")
    
    def handle_new_connection(self, inputs):
        """Accept new client."""
        try:
            client, address = self.server.accept()
            print(f"New connection from {address}")
            
            cname = receive_message(client)
            if not cname or not cname.startswith('NAME: '):
                client.close()
                return
            
            cname = cname.split('NAME: ')[1]
            
            # Block nicknames starting with '*' (reserved for relay)
            if cname.startswith('*'):
                error_msg = "Nickname cannot start with '*' (reserved for relay)"
                send_message(client, f"ERROR: {error_msg}")
                log_message(f"Connection rejected from {address}: {error_msg}")
                client.close()
                return
            
            # Generate unique nickname
            original_name = cname
            cname = self.generate_unique_nickname(cname)
            
            self.clients += 1
            self.clientmap[client] = (address, cname)
            self.nickname_map[cname] = client
            inputs.append(client)
            self.outputs.append(client)
            
            send_message(client, f'CLIENT: {cname}')
            
            # Send user list
            self.send_user_list(client)
            
            # Deliver offline messages
            self.deliver_offline_messages(cname, client)
            
            join_msg = f"{cname} joined (Total Clients: {self.clients})"
            print(join_msg)
            log_message(join_msg)
            self.broadcast(join_msg, exclude=client)
            
            # update user list
            for sock in self.outputs:
                self.send_user_list(sock)
            
        except Exception as e:
            print(f"Error accepting connection: {e}")
    
    def handle_client_message(self, sock, inputs):
        try:
            data = receive_message(sock)
            
            if data:
                client_name = self.get_client_name(sock)
                
                # Check rate limit
                if not self.rate_limiter.check_rate(client_name):
                    send_message(sock, "RATE_LIMIT: You are sending messages too quickly. Slow down!")
                    log_message(f"Rate limit triggered for {client_name}")
                    return
                
                # Handle private message
                if data.startswith('/pm '):
                    parts = data.split(' ', 2)
                    if len(parts) >= 3:
                        target = parts[1]
                        message = parts[2]
                        self.send_private_message(sock, target, message)
                    else:
                        send_message(sock, "Usage: /pm <nickname> <message>")
                    return
                
                # Broadcast public message
                timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                msg = f"[{timestamp}] {client_name}: {data}"
                print(msg)
                log_message(msg)
                self.broadcast(msg, exclude=sock)
                self.total_messages += 1
            else:
                self.handle_client_disconnect(sock, inputs)
        except Exception as e:
            print(f"Error handling message: {e}")
            self.handle_client_disconnect(sock, inputs)
    
    def handle_client_disconnect(self, sock, inputs):
        client_name = self.get_client_name(sock)
        print(f"{client_name} disconnected")
        
        self.clients -= 1
        if sock in inputs:
            inputs.remove(sock)
        if sock in self.outputs:
            self.outputs.remove(sock)
        if sock in self.clientmap:
            del self.clientmap[sock]
        if client_name in self.nickname_map:
            del self.nickname_map[client_name]
        
        self.rate_limiter.remove_client(client_name)
        
        try:
            sock.close()
        except:
            pass
        
        leave_msg = f"{client_name} left (Total Clients: {self.clients})"
        print(leave_msg)
        log_message(leave_msg)
        self.broadcast(leave_msg)
        
        # Update all clients with new user list
        for sock in self.outputs:
            self.send_user_list(sock)
    
    def handle_client_error(self, sock, inputs):
        if sock == self.server:
            print("Server socket error")
            self.shutdown()
        else:
            self.handle_client_disconnect(sock, inputs)


def main():
    parser = argparse.ArgumentParser(description='Chat Server - Chat Project')
    parser.add_argument('--chat-port', type=int, default=DEFAULT_CHAT_PORT, 
                        help=f'Chat server port (default: {DEFAULT_CHAT_PORT})')
    parser.add_argument('--http-port', type=int, default=DEFAULT_HTTP_PORT,
                        help=f'HTTP server port (default: {DEFAULT_HTTP_PORT})')
    parser.add_argument('--ws-port', type=int, default=DEFAULT_WS_PORT,
                        help=f'WebSocket server port (default: {DEFAULT_WS_PORT})')
    args = parser.parse_args()
    
    server = ChatServer(args.chat_port, args.http_port, args.ws_port)
    server.run()


if __name__ == '__main__':
    main()
