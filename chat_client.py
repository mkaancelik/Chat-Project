#!/usr/bin/env python3
"""Chat Client -  Chat Project"""

import socket
import sys
import pickle
import struct
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import argparse

DEFAULT_PORT = 8800
SERVER_HOST = 'localhost'


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


class PrivateMessageWindow:
    """Window for private messaging."""
    
    def __init__(self, parent, nickname, client):
        self.nickname = nickname
        self.client = client
        self.window = tk.Toplevel(parent)
        self.window.title(f"Private Chat with {nickname}")
        self.window.geometry("500x400")
        
        # Messages display
        self.messages = scrolledtext.ScrolledText(self.window, state='disabled', 
                                                   wrap=tk.WORD, height=20)
        self.messages.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Input frame
        input_frame = tk.Frame(self.window)
        input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)
        
        self.input_field = tk.Entry(input_frame)
        self.input_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_field.bind('<Return>', self.send_message)
        
        send_btn = tk.Button(input_frame, text="Send", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.input_field.focus()
    
    def send_message(self, event=None):
        """Send private message."""
        message = self.input_field.get().strip()
        if message:
            self.client.send_private_message(self.nickname, message)
            self.input_field.delete(0, tk.END)
    
    def display_message(self, message):
        self.messages.config(state='normal')
        self.messages.insert(tk.END, message + '\n')
        self.messages.config(state='disabled')
        self.messages.see(tk.END)


class ChatClientGUI:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False
        self.nickname = ""
        self.private_windows = {}
        self.users = []
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("Chat Client")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Get nickname before showing main window
        self.get_nickname()
        
        if not self.nickname:
            sys.exit(0)
        
        self.setup_ui()
        self.connect_to_server()
        
        # Start receive thread
        self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.receive_thread.start()
    
    def get_nickname(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Enter Nickname")
        dialog.geometry("300x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="Enter your nickname:").pack(pady=10)
        
        entry = tk.Entry(dialog, width=30)
        entry.pack(pady=5)
        entry.focus()
        
        result = {'nickname': None}
        
        def on_ok():
            nick = entry.get().strip()
            if nick:
                result['nickname'] = nick
                dialog.destroy()
            else:
                messagebox.showwarning("Invalid", "Nickname cannot be empty!")
        
        def on_enter(event):
            on_ok()
        
        entry.bind('<Return>', on_enter)
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
        
        self.root.wait_window(dialog)
        self.nickname = result['nickname']
    
    def setup_ui(self):
        """Setup main UI."""
        self.root.title(f"Chat Client - {self.nickname}")
        
        # Create paned window for split view
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - chat messages
        left_frame = tk.Frame(paned)
        paned.add(left_frame, minsize=400)
        
        tk.Label(left_frame, text="Public Chat", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.messages = scrolledtext.ScrolledText(left_frame, state='disabled', 
                                                   wrap=tk.WORD)
        self.messages.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # Input frame
        input_frame = tk.Frame(left_frame)
        input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)
        
        self.input_field = tk.Entry(input_frame)
        self.input_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_field.bind('<Return>', self.send_message)
        
        send_btn = tk.Button(input_frame, text="Send", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Right panel - user list
        right_frame = tk.Frame(paned)
        paned.add(right_frame, minsize=200)
        
        tk.Label(right_frame, text="Connected Users", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.user_listbox = tk.Listbox(right_frame)
        self.user_listbox.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.user_listbox.bind('<Double-Button-1>', self.open_private_chat)
        
        tk.Label(right_frame, text="Double-click to private chat", 
                 font=('Arial', 8, 'italic')).pack(pady=5)
        
        # Status bar
        self.status_bar = tk.Label(self.root, text="Connecting...", 
                                   bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def connect_to_server(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.connected = True
            
            # Send nickname
            send_message(self.sock, f'NAME: {self.nickname}')
            
            # Receive confirmation
            data = receive_message(self.sock)
            if data and data.startswith('CLIENT: '):
                assigned_nick = data.split('CLIENT: ')[1]
                self.nickname = assigned_nick
                self.root.title(f"Chat Client - {self.nickname}")
                self.status_bar.config(text=f"Connected as {self.nickname}")
                self.display_message(f"Connected to server as {self.nickname}\n", 'system')
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.root.destroy()
            sys.exit(1)
    
    def display_message(self, message, tag=''):
        """Display message in main chat."""
        self.messages.config(state='normal')
        self.messages.insert(tk.END, message + '\n', tag)
        
        # Configure tags
        self.messages.tag_config('system', foreground='blue')
        self.messages.tag_config('private', foreground='green')
        self.messages.tag_config('error', foreground='red')
        
        self.messages.config(state='disabled')
        self.messages.see(tk.END)
    
    def send_message(self, event=None):
        """Send public message."""
        message = self.input_field.get().strip()
        if message:
            if message.startswith('/pm '):
                # Private message command
                parts = message.split(' ', 2)
                if len(parts) >= 3:
                    target = parts[1]
                    msg = parts[2]
                    self.send_private_message(target, msg)
                else:
                    self.display_message("Usage: /pm <nickname> <message>", 'error')
            else:
                # Public message - display it immediately for the sender
                if send_message(self.sock, message):
                    import datetime
                    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                    self.display_message(f"[{timestamp}] YOU: {message}")
                    self.input_field.delete(0, tk.END)
    
    def send_private_message(self, target, message):
        """send private message to target user."""
        pm_command = f"/pm {target} {message}"
        send_message(self.sock, pm_command)
    
    def open_private_chat(self, event=None):
        """open private hcat window to selected user."""
        selection = self.user_listbox.curselection()
        if selection:
            nickname = self.user_listbox.get(selection[0])
            
            if nickname == self.nickname:
                messagebox.showinfo("Info", "You cannot chat with yourself!")
                return
            
            if nickname not in self.private_windows:
                self.private_windows[nickname] = PrivateMessageWindow(
                    self.root, nickname, self
                )
            else:
                self.private_windows[nickname].window.lift()
    
    def update_user_list(self, users):
        """Update the user list."""
        self.users = users
        self.user_listbox.delete(0, tk.END)
        for user in sorted(users):
            self.user_listbox.insert(tk.END, user)
    
    def receive_messages(self):
        """Receive messages from server."""
        while self.connected:
            try:
                data = receive_message(self.sock)
                
                if not data:
                    self.connected = False
                    self.root.after(0, lambda: self.display_message(
                        "Disconnected from server", 'error'))
                    self.root.after(0, lambda: self.status_bar.config(
                        text="Disconnected"))
                    break
                
                # Handle user list update
                if data.startswith('USERLIST:'):
                    users = data.split('USERLIST:')[1].split(',')
                    users = [u.strip() for u in users if u.strip()]
                    self.root.after(0, lambda u=users: self.update_user_list(u))
                    continue
                
                # Handle private messages display in private window
                if 'PRIVATE' in data:
                    if 'PRIVATE from' in data:
                        parts = data.split('PRIVATE from ')
                        if len(parts) > 1:
                            sender_part = parts[1].split(':', 1)
                            if len(sender_part) > 1:
                                sender = sender_part[0].strip()
                                
                                # Create window and display message together
                                self.root.after(0, lambda s=sender, d=data: 
                                    self.handle_incoming_private_message(s, d))
                        continue  
                    
                    # Outgoing private message confirmation (sent by this user)
                    elif 'PRIVATE to' in data:
                        parts = data.split('PRIVATE to ')
                        if len(parts) > 1:
                            target_part = parts[1].split(':', 1)
                            if len(target_part) > 1:
                                target = target_part[0].strip()
                                
                                # Create window and display message together
                                self.root.after(0, lambda t=target, d=data: 
                                    self.handle_outgoing_private_message(t, d))
                        continue  
                    
                    # Offline message or other private message notification
                    # Display in main window for system notifications
                    if 'OFFLINE MESSAGE' in data or 'is offline' in data:
                        self.root.after(0, lambda d=data: 
                            self.display_message(d, 'private'))
                        continue
                
                # Handle rate limit warningg
                elif data.startswith('RATE_LIMIT:'):
                    self.root.after(0, lambda d=data: 
                        self.display_message(d, 'error'))
                
                # Regular public message display in main window
                else:
                    self.root.after(0, lambda d=data: self.display_message(d))
                
            except Exception as e:
                if self.connected:
                    print(f"Receive error: {e}")
                    self.connected = False
                break
    
    def create_private_window(self, sender):
        if sender not in self.private_windows:
            self.private_windows[sender] = PrivateMessageWindow(
                self.root, sender, self
            )
    
    def handle_incoming_private_message(self, sender, message):
        if sender not in self.private_windows:
            self.private_windows[sender] = PrivateMessageWindow(
                self.root, sender, self
            )
        self.private_windows[sender].display_message(message)
    
    def handle_outgoing_private_message(self, target, message):
        if target not in self.private_windows:
            self.private_windows[target] = PrivateMessageWindow(
                self.root, target, self
            )
        self.private_windows[target].display_message(message)
    
    def on_closing(self):
        """Handle window closing."""
        if self.connected:
            try:
                self.sock.close()
            except:
                pass
        self.root.destroy()
    
    def run(self):
        """Run the GUI."""
        self.root.mainloop()


class ChatClientConsole:    
    def __init__(self, name, host, port):
        self.name = name
        self.host = host
        self.port = port
        self.connected = False
        self.sock = None
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            print(f"Connected to {host}:{port}")
            self.connected = True
            
            send_message(self.sock, f'NAME: {name}')
            data = receive_message(self.sock)
            
            if data and data.startswith('CLIENT: '):
                self.name = data.split('CLIENT: ')[1]
                print(f"Connected as: {self.name}")
            
            print("\nCommands:")
            print("  /pm <nickname> <message> - Send private message")
            print("  /quit or /exit - Leave chat")
            print()
        except Exception as e:
            print(f"Failed to connect: {e}")
            sys.exit(1)
    
    def run(self):
        """Main client loop."""
        input_thread = threading.Thread(target=self.handle_input, daemon=True)
        input_thread.start()
        
        try:
            while self.connected:
                data = receive_message(self.sock)
                
                if not data:
                    print("\nDisconnected from server")
                    self.connected = False
                    break
                
                if data.startswith('USERLIST:'):
                    # Dont print user list in console mode
                    continue
                
                print(f"\n{data}")
                sys.stdout.write(f"[{self.name}]> ")
                sys.stdout.flush()
        except KeyboardInterrupt:
            print("\nExiting...")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self.cleanup()
    
    def handle_input(self):
        """Handle user input."""
        while self.connected:
            try:
                sys.stdout.write(f"[{self.name}]> ")
                sys.stdout.flush()
                line = sys.stdin.readline().strip()
                
                if not line:
                    continue
                
                if line.lower() in ['/quit', '/exit']:
                    print("\nLeaving chat...")
                    self.connected = False
                    break
                
                if not send_message(self.sock, line):
                    self.connected = False
                    break
            except Exception as e:
                print(f"\nInput error: {e}")
                self.connected = False
                break
    
    def cleanup(self):
        """Close connection."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Chat Client - Chat Project')
    parser.add_argument('--host', type=str, default=SERVER_HOST,
                        help=f'Server host (default: {SERVER_HOST})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'Server port (default: {DEFAULT_PORT})')
    parser.add_argument('--name', type=str, help='Your nickname (console mode only)')
    parser.add_argument('--console', action='store_true',
                        help='Use console mode instead of GUI')
    args = parser.parse_args()
    
    if args.console:
        if not args.name:
            parser.error("--name is required for console mode")
        client = ChatClientConsole(args.name, args.host, args.port)
        client.run()
    else:
        # GUI mode
        try:
            client = ChatClientGUI(args.host, args.port)
            client.run()
        except Exception as e:
            print(f"GUI Error: {e}")
            print("Try running with --console flag for console mode")
            sys.exit(1)


if __name__ == '__main__':
    main()
