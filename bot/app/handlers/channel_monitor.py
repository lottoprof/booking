"""
bot/app/handlers/channel_monitor.py

Monitors the private draft channel for new posts, edits, and reactions.
Bot must be admin in the draft channel.

- New channel_post → create channel_posts record (status=draft)
- Edited channel_post → update draft_text
- Reaction ✅ → status=ready, ❌ or remove ✅ → status=draft

Media groups are debounced: multiple messages with the same media_group_id
are merged into a single channel_posts row (first message becomes anchor,
subsequent messages append to media_files JSON).
"""

import asyncio
import json
import logging

from aiogram import F, Router
from aiogram.types import (
    MessageReactionUpdated,
    ReactionTypeEmoji,
)

from bot.app.config import TG_CHANNEL_DRAFT_ID
from bot.app.utils.api import api

logger = logging.getLogger(__name__)

router = Router(name="channel_monitor")

# Debounce buffer for media groups: {media_group_id: [messages]}
_media_group_buffer: dict[str, list[dict]] = {}
_media_group_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]

MEDIA_GROUP_WAIT = 1.0  # seconds to wait for all messages in a group


def _extract_media(message) -> dict | None:
    """Extract media file info from a channel post message."""
    if message.photo:
        best = message.photo[-1]  # largest resolution
        return {"type": "photo", "file_id": best.file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id}
    return None


def _extract_text(message) -> str | None:
    """Extract text or caption from a channel post."""
    return message.caption or message.text or None


async def _flush_media_group(media_group_id: str, chat_id: int):
    """Called after debounce delay — flush buffered media group to API."""
    await asyncio.sleep(MEDIA_GROUP_WAIT)

    messages = _media_group_buffer.pop(media_group_id, [])
    _media_group_tasks.pop(media_group_id, None)

    if not messages:
        return

    messages.sort(key=lambda m: m["message_id"])
    anchor = messages[0]

    media_files = [m["media"] for m in messages if m.get("media")]

    await api._request("POST", "/channel-posts", json={
        "draft_message_id": anchor["message_id"],
        "draft_chat_id": chat_id,
        "draft_text": anchor.get("text"),
        "media_group_id": media_group_id,
        "media_files": json.dumps(media_files) if media_files else None,
        "status": "draft",
    })
    logger.info(
        "Saved media group %s (%d items) from chat %d",
        media_group_id, len(messages), chat_id,
    )


def _is_draft_channel(chat_id: int) -> bool:
    """Check if chat_id matches the configured draft channel."""
    if not TG_CHANNEL_DRAFT_ID:
        return False
    try:
        return chat_id == int(TG_CHANNEL_DRAFT_ID)
    except (ValueError, TypeError):
        return False


@router.channel_post(F.chat.id == F.chat.id)
async def on_channel_post(message):
    """New message in any channel where bot is admin."""
    if not _is_draft_channel(message.chat.id):
        return

    chat_id = message.chat.id
    msg_id = message.message_id
    text = _extract_text(message)
    media = _extract_media(message)

    # Media group handling — debounce
    if message.media_group_id:
        gid = message.media_group_id
        entry = {"message_id": msg_id, "text": text, "media": media}

        if gid not in _media_group_buffer:
            _media_group_buffer[gid] = []
        _media_group_buffer[gid].append(entry)

        # Cancel existing flush task and restart timer
        old_task = _media_group_tasks.get(gid)
        if old_task and not old_task.done():
            old_task.cancel()
        _media_group_tasks[gid] = asyncio.create_task(
            _flush_media_group(gid, chat_id)
        )
        return

    # Single message — save immediately
    media_files = json.dumps([media]) if media else None

    await api._request("POST", "/channel-posts", json={
        "draft_message_id": msg_id,
        "draft_chat_id": chat_id,
        "draft_text": text,
        "media_files": media_files,
        "status": "draft",
    })
    logger.info("Saved single post msg_id=%d from chat %d", msg_id, chat_id)


@router.edited_channel_post(F.chat.id == F.chat.id)
async def on_edited_channel_post(message):
    """Edited message in draft channel → update text."""
    if not _is_draft_channel(message.chat.id):
        return

    text = _extract_text(message)
    media = _extract_media(message)

    # Find existing post by draft_message_id
    posts = await api._request(
        "GET", "/channel-posts",
        params={"status": "draft"},
    )
    if not posts:
        posts = await api._request(
            "GET", "/channel-posts",
            params={"status": "ready"},
        )

    if not posts:
        return

    target = None
    for p in posts:
        if p["draft_message_id"] == message.message_id:
            target = p
            break

    if not target:
        return

    update_data: dict = {}
    if text is not None:
        update_data["draft_text"] = text
    if media and not target.get("media_group_id"):
        update_data["media_files"] = json.dumps([media])

    if update_data:
        await api._request(
            "PATCH", f"/channel-posts/{target['id']}", json=update_data
        )
        logger.info("Updated post id=%d text/media", target["id"])


@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated):
    """Reaction on a message in draft channel."""
    if not _is_draft_channel(event.chat.id):
        return

    msg_id = event.message_id

    # Check new reactions for ✅ or ❌
    new_emojis = set()
    for r in event.new_reaction or []:
        if isinstance(r, ReactionTypeEmoji):
            new_emojis.add(r.emoji)

    # Find the post
    all_posts = await api._request("GET", "/channel-posts")
    if not all_posts:
        return

    target = None
    for p in all_posts:
        if p["draft_message_id"] == msg_id:
            target = p
            break
        # Also check media group — reaction on any message in group
        if p.get("media_group_id"):
            try:
                files = json.loads(p.get("media_files") or "[]")
                # We don't store all message_ids for group, just the anchor
                # So only match the anchor
            except (json.JSONDecodeError, TypeError):
                pass

    if not target:
        return

    if target["status"] in ("published", "scheduled"):
        return

    if "👍" in new_emojis:
        new_status = "ready"
    elif "👎" in new_emojis or not new_emojis:
        new_status = "draft"
    else:
        return

    if target["status"] != new_status:
        await api._request(
            "PATCH", f"/channel-posts/{target['id']}",
            json={"status": new_status},
        )
        logger.info("Post id=%d status → %s (reaction)", target["id"], new_status)
