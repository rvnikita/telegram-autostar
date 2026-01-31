#!/usr/bin/env python3
"""
Autostar - Automatically add star reactions to Telegram channel messages you read.

Runs as a secondary Telegram client session, listens for read updates,
and adds a ⭐ reaction to the last message you scrolled to.
"""

import asyncio
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import (
    UpdateReadChannelInbox,
    ReactionEmoji,
    Channel,
    ChatReactionsAll,
    ChatReactionsSome,
)
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.functions.channels import GetFullChannelRequest
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
REACTION = os.getenv('REACTION', '⭐')

if not API_ID or not API_HASH:
    logger.error("API_ID and API_HASH must be set in .env file")
    logger.error("Get them from https://my.telegram.org")
    exit(1)

# Session file path
SESSION_PATH = Path(__file__).parent / 'autostar'

client = TelegramClient(str(SESSION_PATH), int(API_ID), API_HASH)

# Cache for allowed reactions per channel
allowed_reactions_cache: dict[int, list[str] | None] = {}


async def get_allowed_reactions(peer, peer_id: int) -> list[str] | None:
    """Get allowed reaction emojis for a channel. Returns None if all allowed."""
    if peer_id in allowed_reactions_cache:
        return allowed_reactions_cache[peer_id]

    try:
        full = await client(GetFullChannelRequest(peer))
        reactions = full.full_chat.available_reactions

        if reactions is None or isinstance(reactions, ChatReactionsAll):
            allowed_reactions_cache[peer_id] = None
            return None
        elif isinstance(reactions, ChatReactionsSome):
            allowed = [r.emoticon for r in reactions.reactions if hasattr(r, 'emoticon')]
            allowed_reactions_cache[peer_id] = allowed
            return allowed
    except Exception as e:
        logger.debug(f"Could not get allowed reactions for {peer_id}: {e}")

    allowed_reactions_cache[peer_id] = None
    return None


async def has_my_reaction(peer, message_id: int) -> bool:
    """Check if we already have a reaction on this message."""
    try:
        async for msg in client.iter_messages(peer, ids=[message_id]):
            if msg and msg.reactions:
                for result in msg.reactions.results:
                    if hasattr(result, 'chosen_order') and result.chosen_order is not None:
                        return True
        return False
    except Exception:
        return False


async def add_star(peer, peer_id: int, message_id: int) -> bool:
    """Add a star reaction to a message if we haven't already."""
    # Skip if already reacted
    if await has_my_reaction(peer, message_id):
        logger.debug(f"Message {message_id}: already reacted")
        return True

    # Skip if star not allowed
    allowed = await get_allowed_reactions(peer, peer_id)
    if allowed is not None and REACTION not in allowed:
        logger.debug(f"Message {message_id}: ⭐ not allowed in channel {peer_id}")
        return False

    try:
        await client(SendReactionRequest(
            peer=peer,
            msg_id=message_id,
            reaction=[ReactionEmoji(emoticon=REACTION)]
        ))
        logger.info(f"⭐ channel {peer_id} message {message_id}")
        return True
    except ReactionInvalidError:
        if peer_id in allowed_reactions_cache:
            del allowed_reactions_cache[peer_id]
        return False
    except (MsgIdInvalidError, ChatAdminRequiredError, ChannelPrivateError):
        return False
    except FloodWaitError as e:
        logger.warning(f"Rate limited, waiting {e.seconds}s")
        await asyncio.sleep(e.seconds)
        return await add_star(peer, peer_id, message_id)
    except Exception as e:
        logger.debug(f"Failed to star message {message_id}: {e}")
        return False


@client.on(events.Raw)
async def handle_read_update(event):
    """Star the last read message in channels."""
    if not isinstance(event, UpdateReadChannelInbox):
        return

    peer_id = event.channel_id
    message_id = event.max_id

    try:
        entity = await client.get_entity(peer_id)

        # Only broadcast channels (not supergroups)
        if isinstance(entity, Channel) and entity.broadcast:
            await add_star(entity, peer_id, message_id)

    except Exception as e:
        logger.debug(f"Failed to process update for channel {peer_id}: {e}")


async def main():
    logger.info("Starting Autostar...")

    await client.start()

    me = await client.get_me()
    logger.info(f"Logged in as {me.first_name} (@{me.username})")
    logger.info("Listening for channel reads... Press Ctrl+C to stop.")

    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
