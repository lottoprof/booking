"""
bot/app/events/channel_publisher.py

Periodic consumer that checks for scheduled channel posts
(status=scheduled, scheduled_at <= now) and publishes them.

Runs every 60 seconds as an asyncio task in gateway lifespan.
"""

import asyncio
import json
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds


async def channel_publisher_loop(redis_url: str, backend_url: str) -> None:
    """
    Poll backend for pending scheduled posts and publish them.

    Args:
        redis_url: unused, kept for consistency with other consumer signatures
        backend_url: backend base URL (e.g. http://127.0.0.1:8000)
    """
    logger.info("channel_publisher_loop started")

    async with httpx.AsyncClient(base_url=backend_url, timeout=15.0) as client:
        while True:
            try:
                await _check_and_publish(client)
            except asyncio.CancelledError:
                logger.info("channel_publisher_loop cancelled")
                raise
            except Exception:
                logger.exception("channel_publisher_loop error")

            await asyncio.sleep(CHECK_INTERVAL)


async def _check_and_publish(client: httpx.AsyncClient) -> None:
    """Fetch pending posts and publish each one."""
    resp = await client.get("/channel-posts/pending")
    if resp.status_code != 200:
        return

    posts = resp.json()
    if not posts:
        return

    logger.info("Found %d scheduled posts to publish", len(posts))

    for post in posts:
        try:
            await _publish_post(client, post)
        except Exception:
            logger.exception("Failed to publish scheduled post id=%d", post["id"])
            await client.patch(
                f"/channel-posts/{post['id']}",
                json={"status": "failed"},
            )


async def _publish_post(client: httpx.AsyncClient, post: dict) -> None:
    """Publish a single scheduled post to the public channel."""
    from bot.app.config import TG_CHANNEL_DRAFT_ID, TG_CHANNEL_PUBLIC_ID
    from bot.app.main import bot

    if not TG_CHANNEL_PUBLIC_ID or not TG_CHANNEL_DRAFT_ID:
        logger.error("Channel IDs not configured")
        return

    draft_chat_id = int(TG_CHANNEL_DRAFT_ID)
    try:
        public_chat_id: int | str = int(TG_CHANNEL_PUBLIC_ID)
    except ValueError:
        public_chat_id = TG_CHANNEL_PUBLIC_ID

    # Build CTA keyboard
    reply_markup = None
    if post.get("cta_buttons"):
        try:
            cta_list = json.loads(post["cta_buttons"])
            from bot.app.flows.admin.channel_publish import _build_cta_keyboard
            reply_markup = _build_cta_keyboard(cta_list)
        except (json.JSONDecodeError, TypeError):
            pass

    hashtag_text = post.get("hashtags") or ""

    is_media_group = bool(post.get("media_group_id") and post.get("media_files"))

    if is_media_group:
        files = json.loads(post["media_files"])
        from aiogram.types import (
            InputMediaAnimation,
            InputMediaDocument,
            InputMediaPhoto,
            InputMediaVideo,
        )

        media_map = {
            "photo": InputMediaPhoto,
            "video": InputMediaVideo,
            "animation": InputMediaAnimation,
            "document": InputMediaDocument,
        }

        media_group = []
        caption_text = post.get("draft_text") or ""
        if hashtag_text:
            caption_text = f"{caption_text}\n\n{hashtag_text}" if caption_text else hashtag_text

        for i, f_info in enumerate(files):
            cls = media_map.get(f_info["type"], InputMediaPhoto)
            kwargs = {"media": f_info["file_id"]}
            if i == 0 and caption_text:
                kwargs["caption"] = caption_text
            media_group.append(cls(**kwargs))

        sent = await bot.send_media_group(chat_id=public_chat_id, media=media_group)
        public_msg_id = sent[0].message_id if sent else None

        if reply_markup and sent:
            await bot.send_message(
                chat_id=public_chat_id,
                text="\u200b",
                reply_markup=reply_markup,
                reply_to_message_id=sent[0].message_id,
            )
    else:
        caption_text = post.get("draft_text") or ""
        if hashtag_text:
            caption_text = f"{caption_text}\n\n{hashtag_text}" if caption_text else hashtag_text

        has_media = False
        files = []
        if post.get("media_files"):
            try:
                files = json.loads(post["media_files"])
                has_media = bool(files)
            except (json.JSONDecodeError, TypeError):
                pass

        if has_media:
            from bot.app.flows.admin.channel_publish import _send_single_media
            sent_msg = await _send_single_media(
                bot, public_chat_id, files[0], caption_text, reply_markup,
            )
            public_msg_id = sent_msg.message_id if sent_msg else None
        elif caption_text:
            sent_msg = await bot.send_message(
                chat_id=public_chat_id, text=caption_text,
                reply_markup=reply_markup,
            )
            public_msg_id = sent_msg.message_id
        else:
            result = await bot.copy_message(
                chat_id=public_chat_id,
                from_chat_id=draft_chat_id,
                message_id=post["draft_message_id"],
                reply_markup=reply_markup,
            )
            public_msg_id = result.message_id

    # Mark as published
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    update: dict = {"status": "published", "published_at": now}
    if public_msg_id:
        update["public_message_id"] = public_msg_id
    await client.patch(f"/channel-posts/{post['id']}", json=update)

    logger.info("Published scheduled post id=%d", post["id"])
