2021556018
Mustafa Kaan Çelik
Evening class

# Chat Project - README


A feature-rich Python chat system with a main server, GUI/console clients, and an optional relay server. Includes real-time messaging, private messaging, rate limiting, and a web-based monitoring interface.

## Features

- **Multi-client chat server** with public and private messaging
- **Unique nickname enforcement** with automatic suffix generation
- **Public message broadcasting** with timestamps
- **GUI client** (Tkinter) with private chat windows and user list
- **Console client** for terminal-based chatting
- **Optional relay server** that prepends '*' to nicknames
- **Web monitoring interface** with real-time WebSocket updates
- **Rate limiting** to prevent spam
- **Offline message storage** for unavailable users
- **Message logging** to file

## Dependencies

### Required Python Packages
```bash
pip install websockets
```

### Standard Library Modules
- `socket`, `select`, `pickle`, `struct`
- `threading`, `signal`, `argparse`
- `tkinter` 
- `asyncio`, `datetime`, `json`

### Python Version
- Python 3.7+ (required for asyncio and websockets)

## Installation

1. Ensure Python 3.7+ is installed
2. Install dependencies:
   ```bash
   pip install websockets
   ```
3. Download all three files to the same directory:
   - `chat_server.py`
   - `chat_client.py`
   - `chat_relay.py`

## Execution Guide

### 1. Starting the Chat Server

**Basic usage:**
```bash
python3 chat_server.py
```

**With custom ports:**
```bash
python3 chat_server.py --chat-port 8800 --http-port 8080 --ws-port 8081
```

**Command-line arguments:**
- `--chat-port`: Port for chat connections (default: 8800)
- `--http-port`: Port for web interface (default: 8080)
- `--ws-port`: Port for WebSocket connections (default: 8081)

**Server outputs:**
- Console: Connection logs and statistics
- `chat_log.txt`: Timestamped message history
- Web interface: `http://localhost:8080`

### 2. Launching Clients

#### GUI Client (Recommended)

**Basic usage:**
```bash
python3 chat_client.py
```

**Connect to remote server:**
```bash
python3 chat_client.py --host 192.168.1.100 --port 8800
```

**Features:**
- Enter nickname on startup
- Public chat in main window
- Double-click users to open private chat windows
- User list updates automatically

#### Console Client

**Basic usage:**
```bash
python3 chat_client.py --console --name YourNickname
```

**With custom server:**
```bash
python3 chat_client.py --console --name Alice --host localhost --port 8800
```

**Command-line arguments:**
- `--console`: Enable console mode (no GUI)
- `--name`: Your nickname (required for console mode)
- `--host`: Server hostname/IP (default: localhost)
- `--port`: Server port (default: 8800)

**Console commands:**
- `/pm <nickname> <message>`: Send private message
- `/quit` or `/exit`: Leave chat

### 3. Using the Relay Server (Optional)

The relay server acts as a proxy that prepends '*' to all nicknames passing through it.

**Basic usage:**
```bash
python3 chat_relay.py
```

**Custom configuration:**
```bash
python3 chat_relay.py --relay-port 8900 --server-host localhost --server-port 8800
```

**Command-line arguments:**
- `--relay-port`: Port for relay to listen on (default: 8900)
- `--server-host`: Main server hostname (default: localhost)
- `--server-port`: Main server port (default: 8800)

**To connect through relay:**
```bash
# Client connects to relay instead of server
python3 chat_client.py --port 8900
```

The relay will:
- Forward all traffic between client and server
- Automatically prepend '*' to the client's nickname
- Log relay activity to `relay_log.txt`

## Complete Setup Example

**Terminal 1 - Start server:**
```bash
python3 chat_server.py
```

**Terminal 2 - Start relay (optional):**
```bash
python3 chat_relay.py
```

**Terminal 3 - GUI client (direct connection):**
```bash
python3 chat_client.py
```

**Terminal 4 - Console client (through relay):**
```bash
python3 chat_client.py --console --name Bob --port 8900
```

**Terminal 5 - Another GUI client:**
```bash
python3 chat_client.py --host localhost --port 8800
```

## Usage Tips

### Private Messaging
- **GUI**: Double-click username in user list
- **Console/GUI**: Type `/pm username message`

### Web Monitoring
- Open browser to `http://localhost:8080`
- View real-time messages and server statistics
- WebSocket auto-reconnects if disconnected

### Rate Limiting
- Maximum 10 messages per 60 seconds per user
- Excess messages trigger warning
- Helps prevent spam

### Offline Messages
- Messages sent to offline users are stored
- Delivered automatically when user reconnects

## Troubleshooting

**"Address already in use" error:**
```bash
# Find and kill process using port
lsof -ti:8800 | xargs kill -9
```

**GUI won't start:**
```bash
# Use console mode instead
python3 chat_client.py --console --name YourName
```

**WebSocket connection fails:**
- Check firewall settings
- Ensure ws-port is accessible
- Browser console may show errors

**Can't connect to relay:**
- Verify relay is running first
- Check relay-port matches client's --port

## File Outputs

- `chat_log.txt`: Server message history
- `relay_log.txt`: Relay activity log (if using relay)

## Network Configuration

**Local network access:**
- Find server IP: `hostname -I` or `ipconfig`
- Clients use: `--host <server-ip>`

**Firewall rules:**
- Allow TCP ports: 8800 (chat), 8080 (HTTP), 8081 (WebSocket), 8900 (relay)

## Stopping Services

- Press `Ctrl+C` in any terminal to stop server/relay/console client
- GUI clients: Close window normally

---

