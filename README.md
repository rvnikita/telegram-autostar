# Autostar

Automatically add star reactions to Telegram messages you've read.

This script runs as a secondary Telegram client session and monitors when you read messages on your main client (phone/desktop), then adds a customizable reaction to those messages.

## Features

- Automatically reacts to messages as you read them
- Works across all your Telegram clients (monitors read state sync)
- Configurable reaction emoji (default: star)
- Optional chat filtering (watch specific chats or all)
- Rate limit handling with configurable delays
- Graceful error handling for restricted chats

## Requirements

- Python 3.9+
- Telegram account
- Telegram API credentials

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/rvnikita/telegram-autostar.git
cd telegram-autostar
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get Telegram API credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Navigate to "API development tools"
4. Create an application (any name/description works)
5. Note down your `API_ID` and `API_HASH`

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
API_ID=your_api_id_here
API_HASH=your_api_hash_here
```

### 6. Run

```bash
python autostar.py
```

On first run, you'll be prompted to authenticate with your phone number and verification code. This creates a session file that persists the login.

## Configuration

All configuration is done via environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `API_ID` | Your Telegram API ID | *required* |
| `API_HASH` | Your Telegram API hash | *required* |
| `WATCH_CHATS` | Comma-separated chat IDs to watch | *empty* (all chats) |
| `REACTION` | Emoji reaction to add | `⭐` |
| `REACTION_DELAY` | Seconds between reactions (rate limit protection) | `1.0` |

### Examples

**Watch all chats with default star reaction:**
```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
```

**Watch specific chats only:**
```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
WATCH_CHATS=-1001234567890,-1009876543210
```

**Use a different reaction:**
```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
REACTION=👍
```

### Finding Chat IDs

Several methods to find a chat's ID:

1. **Using [@userinfobot](https://t.me/userinfobot):** Forward any message from the chat to this bot
2. **Using [@getidsbot](https://t.me/getidsbot):** Forward a message or add to a group
3. **Web Telegram:** Open web.telegram.org, select a chat, and check the URL for the chat ID

Note: Channel and supergroup IDs are typically negative numbers starting with `-100`.

## How It Works

1. **Session Creation:** Autostar creates a secondary Telegram client session linked to your account
2. **Read State Monitoring:** It listens for read state synchronization updates that Telegram sends when you read messages on any device
3. **Reaction Dispatch:** When new messages are marked as read, it sends reaction requests for each message
4. **Deduplication:** Tracks already-reacted messages to prevent duplicate reactions

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Your Phone/    │────▶│    Telegram     │────▶│    Autostar     │
│  Desktop App    │     │    Servers      │     │    (this tool)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │ Read messages         │ Sync read state       │ Add reactions
        ▼                       ▼                       ▼
```

## Running as a Background Service

### Using screen

```bash
screen -S autostar
python autostar.py
# Press Ctrl+A, then D to detach
# Reattach with: screen -r autostar
```

### Using nohup

```bash
nohup python autostar.py > autostar.log 2>&1 &
```

### Using systemd (Linux)

Create `/etc/systemd/system/autostar.service`:

```ini
[Unit]
Description=Autostar - Telegram auto-reaction service
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/autostar
ExecStart=/path/to/autostar/venv/bin/python autostar.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable autostar
sudo systemctl start autostar
```

### Using launchd (macOS)

Create `~/Library/LaunchAgents/com.autostar.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.autostar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/autostar/venv/bin/python</string>
        <string>/path/to/autostar/autostar.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/autostar</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/autostar/autostar.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/autostar/autostar.log</string>
</dict>
</plist>
```

Then load:

```bash
launchctl load ~/Library/LaunchAgents/com.autostar.plist
```

## Limitations

- **Reactions must be enabled:** Some channels/groups have reactions disabled by admins
- **Rate limits apply:** Telegram limits reaction frequency; the configurable delay helps avoid bans
- **Forward-only tracking:** Only tracks messages read after the script starts
- **Session persistence required:** The script must remain running to process reactions
- **One reaction per message:** Adding a reaction replaces any previous reaction you may have set

## Troubleshooting

### "API_ID and API_HASH must be set"
Ensure your `.env` file exists and contains valid credentials from my.telegram.org.

### "reactions not allowed"
The chat has reactions disabled. You can exclude it using `WATCH_CHATS`.

### "Rate limited, waiting Xs"
Telegram is throttling requests. The script automatically waits and retries. Consider increasing `REACTION_DELAY`.

### Session issues
Delete `autostar.session` and `autostar.session-journal` to force re-authentication:
```bash
rm autostar.session autostar.session-journal
python autostar.py
```

## Security Notes

- **Never commit `.env`** - It contains your API credentials
- **Never share session files** - They provide full account access
- **API credentials are personal** - Don't share your API_ID/API_HASH
- The `.gitignore` file excludes all sensitive files by default

## License

MIT License - feel free to use and modify as needed.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
