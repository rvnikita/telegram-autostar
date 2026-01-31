#!/usr/bin/env python3
"""
Autostar - Automatically add star reactions to Telegram messages you've read.

This script runs as a secondary Telegram client session and monitors when you
read messages on your main client, then adds a star reaction to those messages.
"""

import asyncio
import os
import logging
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import (
    UpdateReadHistoryInbox,
    UpdateReadChannelInbox,
    ReactionEmoji,
    PeerUser,
    PeerChat,
    PeerChannel,
)
from telethon.tl.functions.messages import SendReactionRequest
from telethon.errors import (
    ReactionInvalidError,
    MsgIdInvalidError,
    ChatAdminRequiredError,
    ChannelPrivateError,
    FloodWaitError,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
WATCH_CHATS = os.getenv('WATCH_CHATS', '').strip()
REACTION = os.getenv('REACTION', '⭐')
REACTION_DELAY = float(os.getenv('REACTION_DELAY', '1.0'))

if not API_ID or not API_HASH:
    logger.error("API_ID and API_HASH must be set in .env file")
    logger.error("Get them from https://my.telegram.org")
    exit(1)

# Track last read message ID per chat to know which messages are newly read
last_read_ids: dict[int, int] = defaultdict(int)

# Track messages we've already starred to prevent duplicates
starred_messages: set[tuple[int, int]] = set()  # (peer_id, msg_id)

# Lock to prevent race conditions from duplicate updates
update_lock = asyncio.Lock()

# Parse watch list
watch_list: set[int] = set()
if WATCH_CHATS:
    for chat in WATCH_CHATS.split(','):
        chat = chat.strip()
        if chat.lstrip('-').isdigit():
            watch_list.add(int(chat))

# Session file path
SESSION_PATH = Path(__file__).parent / 'autostar'

client = TelegramClient(str(SESSION_PATH), int(API_ID), API_HASH)


def get_peer_id(peer) -> int:
    """Extract numeric ID from a peer object."""
    if isinstance(peer, PeerUser):
        return peer.user_id
    elif isinstance(peer, PeerChat):
        return peer.chat_id
    elif isinstance(peer, PeerChannel):
        return peer.channel_id
    elif isinstance(peer, int):
        return peer
    return 0


def should_watch(peer_id: int) -> bool:
    """Check if we should watch this chat."""
    if not watch_list:
        return True  # Watch all if no filter specified
    return peer_id in watch_list


async def add_reaction(peer, message_id: int) -> bool:
    """Add a star reaction to a message."""
    try:
        await client(SendReactionRequest(
            peer=peer,
            msg_id=message_id,
            reaction=[ReactionEmoji(emoticon=REACTION)]
        ))
        logger.info(f"  ✓ Starred message {message_id}")
        return True
    except ReactionInvalidError:
        logger.warning(f"  ✗ Message {message_id}: reactions not allowed")
        return False
    except MsgIdInvalidError:
        logger.warning(f"  ✗ Message {message_id}: not found")
        return False
    except ChatAdminRequiredError:
        logger.warning(f"  ✗ Message {message_id}: no permission")
        return False
    except ChannelPrivateError:
        logger.warning(f"  ✗ Message {message_id}: private channel")
        return False
    except FloodWaitError as e:
        logger.warning(f"  ⏳ Rate limited, waiting {e.seconds}s")
        await asyncio.sleep(e.seconds)
        return await add_reaction(peer, message_id)
    except Exception as e:
        logger.warning(f"  ✗ Message {message_id}: {e}")
        return False


async def get_messages_in_range(peer, from_id: int, to_id: int) -> list[int]:
    """Get message IDs between from_id (exclusive) and to_id (inclusive)."""
    message_ids = []
    range_size = to_id - from_id

    try:
        # Use iter_messages for reliable fetching
        # No limit - fetch all messages in range
        async for msg in client.iter_messages(
            peer,
            min_id=from_id,
            max_id=to_id + 1,
        ):
            if from_id < msg.id <= to_id:
                message_ids.append(msg.id)

        logger.info(f"  Found {len(message_ids)} messages in range ({from_id}, {to_id}] (range size: {range_size})")

    except Exception as e:
        logger.error(f"Failed to fetch message history: {e}")
        # Fallback: just return the to_id
        if to_id > from_id:
            message_ids = [to_id]

    return sorted(message_ids)


async def process_read_update(peer, peer_id: int, max_id: int):
    """Process a read update and add reactions to newly read messages."""
    if not should_watch(peer_id):
        return

    messages_to_star = []

    async with update_lock:
        last_read = last_read_ids[peer_id]

        if max_id <= last_read:
            return  # No new messages read

        # Update tracking immediately to prevent duplicate processing
        last_read_ids[peer_id] = max_id

        if last_read == 0:
            # First time seeing this chat, just mark current position
            logger.info(f"Now tracking chat {peer_id}, starting from message {max_id}")
            return

        # Get messages that were just read
        message_ids = await get_messages_in_range(peer, last_read, max_id)

        if not message_ids:
            logger.warning(f"No messages found in range ({last_read}, {max_id}]")
            return

        # Filter out already starred messages
        messages_to_star = [
            msg_id for msg_id in message_ids
            if (peer_id, msg_id) not in starred_messages
        ]

        if not messages_to_star:
            return

        logger.info(f"Starring {len(messages_to_star)} message(s) in chat {peer_id}: {messages_to_star}")

        # Mark as starred before sending to prevent duplicates
        for msg_id in messages_to_star:
            starred_messages.add((peer_id, msg_id))

    # Add reactions outside the lock so new updates aren't blocked
    for msg_id in messages_to_star:
        await add_reaction(peer, msg_id)
        await asyncio.sleep(REACTION_DELAY)


@client.on(events.Raw)
async def handle_raw_update(event):
    """Handle raw Telegram updates to catch read events."""

    if isinstance(event, UpdateReadHistoryInbox):
        # Regular chat read update
        peer_id = get_peer_id(event.peer)
        await process_read_update(event.peer, peer_id, event.max_id)

    elif isinstance(event, UpdateReadChannelInbox):
        # Channel/supergroup read update
        peer_id = event.channel_id
        try:
            # Get the full peer for the channel
            entity = await client.get_entity(peer_id)
            await process_read_update(entity, peer_id, event.max_id)
        except Exception as e:
            logger.error(f"Failed to process channel update: {e}")


async def initialize_read_positions():
    """Initialize read positions for watched chats on startup."""
    logger.info("Initializing read positions...")

    async for dialog in client.iter_dialogs():
        peer_id = dialog.entity.id

        if not should_watch(peer_id):
            continue

        # Store current read position
        if hasattr(dialog, 'dialog') and hasattr(dialog.dialog, 'read_inbox_max_id'):
            last_read_ids[peer_id] = dialog.dialog.read_inbox_max_id
        elif dialog.message:
            last_read_ids[peer_id] = dialog.message.id

    logger.info(f"Tracking {len(last_read_ids)} chat(s)")


async def main():
    """Main entry point."""
    logger.info("Starting Autostar...")
    logger.info(f"Reaction: {REACTION}")
    logger.info(f"Delay between reactions: {REACTION_DELAY}s")

    if watch_list:
        logger.info(f"Watching specific chats: {watch_list}")
    else:
        logger.info("Watching all chats")

    await client.start()

    me = await client.get_me()
    logger.info(f"Logged in as {me.first_name} (@{me.username})")

    await initialize_read_positions()

    logger.info("Listening for read updates... Press Ctrl+C to stop.")

    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
