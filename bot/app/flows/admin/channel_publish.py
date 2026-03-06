"""
bot/app/flows/admin/channel_publish.py

Admin flow: browse ready posts from draft channel, configure CTA buttons
and hashtags, publish immediately or schedule for later.

FSM states:
  view_list → view_post → ask_button → choose_btn_type →
  choose_booking_target / choose_article → ask_more_buttons →
  ask_hashtags → ask_when → enter_datetime → publish
"""

import json
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.app.i18n.loader import DEFAULT_LANG, t
from bot.app.keyboards.admin import admin_main
from bot.app.utils.api import api
from bot.app.utils.pagination import build_nav_row
from bot.app.utils.state import user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
MAX_CTA_BUTTONS = 3


class ChannelPublish(StatesGroup):
    view_post = State()
    ask_button = State()
    choose_btn_type = State()
    choose_booking_target = State()
    choose_article = State()
    ask_hashtags = State()
    ask_when = State()
    enter_datetime = State()


# ==============================================================
# Keyboards
# ==============================================================

def kb_posts_list(
    posts: list[dict], page: int, total: int, lang: str,
) -> InlineKeyboardMarkup:
    rows = []
    for p in posts:
        text_preview = (p.get("draft_text") or t("admin:channel:no_text", lang))[:40]
        created = (p.get("created_at") or "")[:10]
        label = t("admin:channel:item", lang, created, text_preview)
        rows.append([InlineKeyboardButton(
            text=label, callback_data=f"chp:view:{p['id']}"
        )])

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    nav = build_nav_row(page, total_pages, "chp:page:{p}", "chp:noop", lang)
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        text=t("admin:channel:back", lang), callback_data="chp:close"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_post_actions(post_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("admin:channel:confirm_publish", lang),
            callback_data=f"chp:start_publish:{post_id}",
        )],
        [InlineKeyboardButton(
            text=t("admin:channel:back", lang),
            callback_data="chp:back_list",
        )],
    ])


def kb_yes_no(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("common:yes", lang), callback_data="chp:btn_yes"),
            InlineKeyboardButton(text=t("common:no", lang), callback_data="chp:btn_no"),
        ],
    ])


def kb_btn_type(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("admin:channel:btn_booking", lang), callback_data="chp:btype:booking",
        )],
        [InlineKeyboardButton(
            text=t("admin:channel:btn_blog", lang), callback_data="chp:btype:blog",
        )],
        [InlineKeyboardButton(
            text=t("admin:channel:btn_pricing", lang), callback_data="chp:btype:pricing",
        )],
        [InlineKeyboardButton(
            text=t("admin:channel:btn_home", lang), callback_data="chp:btype:home",
        )],
        [InlineKeyboardButton(
            text=t("common:cancel", lang), callback_data="chp:btn_no",
        )],
    ])


def kb_booking_target(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t("admin:channel:btn_booking_general", lang),
            callback_data="chp:book:general",
        )],
        [InlineKeyboardButton(
            text=t("admin:channel:btn_booking_service", lang),
            callback_data="chp:book:service",
        )],
        [InlineKeyboardButton(
            text=t("common:cancel", lang), callback_data="chp:btn_no",
        )],
    ])


def kb_items_select(
    items: list[dict], key_id: str, key_label: str, cb_prefix: str, lang: str,
) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(
            text=item[key_label],
            callback_data=f"{cb_prefix}:{item[key_id]}",
        )])
    rows.append([InlineKeyboardButton(
        text=t("common:cancel", lang), callback_data="chp:btn_no",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_hashtags(
    categories: list[dict], selected: set[str], lang: str,
) -> InlineKeyboardMarkup:
    rows = []
    for cat in categories:
        slug = cat["slug"]
        prefix = "✅ " if slug in selected else ""
        rows.append([InlineKeyboardButton(
            text=f"{prefix}{cat['name']}",
            callback_data=f"chp:htag:{slug}",
        )])
    rows.append([
        InlineKeyboardButton(
            text=t("admin:channel:done", lang), callback_data="chp:htag_done",
        ),
        InlineKeyboardButton(
            text=t("admin:channel:skip", lang), callback_data="chp:htag_skip",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_when(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t("admin:channel:now", lang), callback_data="chp:when:now",
            ),
            InlineKeyboardButton(
                text=t("admin:channel:schedule", lang), callback_data="chp:when:schedule",
            ),
        ],
    ])


# ==============================================================
# Hashtag mapping: category slug → hashtag text
# ==============================================================

SLUG_TO_HASHTAG = {
    "services": "#услуги",
    "body-care": "#уходзателом",
    "results": "#результаты",
    "faq": "#ответынавопросы",
    "lpg": "#lpgмассаж",
    "pressotherapy": "#прессотерапия",
}


def slugs_to_hashtag_text(slugs: list[str]) -> str:
    tags = [SLUG_TO_HASHTAG.get(s, f"#{s.replace('-', '')}") for s in slugs]
    return " ".join(tags)


# ==============================================================
# Setup
# ==============================================================

def setup(menu_controller, get_user_role):
    router = Router(name="channel_publish")
    mc = menu_controller

    # ----------------------------------------------------------
    # Entry point (called from admin_reply)
    # ----------------------------------------------------------

    async def show_list(message: Message):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)

        posts = await api._request("GET", "/channel-posts", params={"status": "ready"})
        if not posts:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("admin:channel:back", lang), callback_data="chp:close",
                )]
            ])
            await mc.show_inline_readonly(message, t("admin:channel:empty", lang), kb)
            return

        router._posts_cache = {message.chat.id: {"posts": posts, "page": 0}}
        text = t("admin:channel:list_title", lang)
        kb = kb_posts_list(posts[:PAGE_SIZE], 0, len(posts), lang)
        await mc.show_inline_readonly(message, text, kb)

    router.show_list = show_list

    # ----------------------------------------------------------
    # Close / Back to menu
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:close")
    async def close_list(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()

    @router.callback_query(F.data == "chp:noop")
    async def noop(callback: CallbackQuery):
        await callback.answer()

    # ----------------------------------------------------------
    # Pagination
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("chp:page:"))
    async def paginate(callback: CallbackQuery):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        page = int(callback.data.split(":")[2])

        cache = getattr(router, "_posts_cache", {}).get(callback.message.chat.id, {})
        posts = cache.get("posts", [])
        if not posts:
            await callback.answer()
            return

        start = page * PAGE_SIZE
        page_posts = posts[start:start + PAGE_SIZE]
        text = t("admin:channel:list_title", lang)
        kb = kb_posts_list(page_posts, page, len(posts), lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # View single post
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("chp:view:"))
    async def view_post(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        post_id = int(callback.data.split(":")[2])

        post = await api._request("GET", f"/channel-posts/{post_id}")
        if not post:
            await callback.answer(t("admin:channel:error", lang), show_alert=True)
            return

        if post["status"] == "published":
            await callback.answer(t("admin:channel:already_published", lang), show_alert=True)
            return

        # Build preview text
        preview = post.get("draft_text") or t("admin:channel:no_text", lang)
        media_info = ""
        if post.get("media_files"):
            try:
                files = json.loads(post["media_files"])
                media_info = f"\n📎 {len(files)} media"
            except (json.JSONDecodeError, TypeError):
                pass

        text = f"{t('admin:channel:preview', lang)}\n\n{preview}{media_info}"
        kb = kb_post_actions(post_id, lang)

        await state.set_state(ChannelPublish.view_post)
        await state.update_data(post_id=post_id)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Start publish flow
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("chp:start_publish:"))
    async def start_publish(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        post_id = int(callback.data.split(":")[2])

        await state.set_state(ChannelPublish.ask_button)
        await state.update_data(post_id=post_id, cta_buttons=[])

        text = t("admin:channel:ask_button", lang)
        kb = kb_yes_no(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Back to list
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:back_list")
    async def back_to_list(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.clear()

        posts = await api._request("GET", "/channel-posts", params={"status": "ready"})
        if not posts:
            text = t("admin:channel:empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("admin:channel:back", lang), callback_data="chp:close",
                )]
            ])
        else:
            router._posts_cache = {callback.message.chat.id: {"posts": posts, "page": 0}}
            text = t("admin:channel:list_title", lang)
            kb = kb_posts_list(posts[:PAGE_SIZE], 0, len(posts), lang)

        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # CTA Button flow: Yes → choose type
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:btn_yes", ChannelPublish.ask_button)
    async def btn_yes(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.set_state(ChannelPublish.choose_btn_type)
        text = t("admin:channel:btn_type_prompt", lang)
        kb = kb_btn_type(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "chp:btn_no", ChannelPublish.ask_button)
    async def btn_no_skip(callback: CallbackQuery, state: FSMContext):
        """Skip CTA buttons → go to hashtags."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _show_hashtags(callback, state, lang)

    # ----------------------------------------------------------
    # Choose button type
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:btype:booking", ChannelPublish.choose_btn_type)
    async def btn_type_booking(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.set_state(ChannelPublish.choose_booking_target)
        text = t("admin:channel:btn_type_prompt", lang)
        kb = kb_booking_target(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "chp:btype:blog", ChannelPublish.choose_btn_type)
    async def btn_type_blog(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)

        # Fetch articles from backend
        articles = await api._request("GET", "/channel-posts/articles")
        if not articles:
            # No articles — treat as skip
            await _add_cta_button(state, {"type": "blog", "ref": None})
            await _after_button_added(callback, state, lang)
            return

        await state.set_state(ChannelPublish.choose_article)
        text = t("admin:channel:btn_choose_article", lang)
        kb = kb_items_select(articles, "slug", "title", "chp:article", lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "chp:btype:pricing", ChannelPublish.choose_btn_type)
    async def btn_type_pricing(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _add_cta_button(state, {"type": "pricing", "ref": None})
        await _after_button_added(callback, state, lang)

    @router.callback_query(F.data == "chp:btype:home", ChannelPublish.choose_btn_type)
    async def btn_type_home(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _add_cta_button(state, {"type": "home", "ref": None})
        await _after_button_added(callback, state, lang)

    # Cancel from btn_type → skip to hashtags
    @router.callback_query(F.data == "chp:btn_no", ChannelPublish.choose_btn_type)
    async def btn_type_cancel(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _show_hashtags(callback, state, lang)

    # ----------------------------------------------------------
    # Booking target
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:book:general", ChannelPublish.choose_booking_target)
    async def book_general(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _add_cta_button(state, {"type": "booking", "ref": None})
        await _after_button_added(callback, state, lang)

    @router.callback_query(F.data == "chp:book:service", ChannelPublish.choose_booking_target)
    async def book_service_pick(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        packages = await api.get_packages()
        if not packages:
            await _add_cta_button(state, {"type": "booking", "ref": None})
            await _after_button_added(callback, state, lang)
            return

        active = [p for p in packages if p.get("is_active") and p.get("show_on_booking")]
        if not active:
            await _add_cta_button(state, {"type": "booking", "ref": None})
            await _after_button_added(callback, state, lang)
            return

        text = t("admin:channel:btn_choose_service", lang)
        kb = kb_items_select(active, "slug", "name", "chp:booksvc", lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("chp:booksvc:"), ChannelPublish.choose_booking_target)
    async def book_service_selected(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        slug = callback.data.split(":", 2)[2]
        await _add_cta_button(state, {"type": "booking", "ref": slug})
        await _after_button_added(callback, state, lang)

    # Cancel from booking target
    @router.callback_query(F.data == "chp:btn_no", ChannelPublish.choose_booking_target)
    async def book_cancel(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _show_hashtags(callback, state, lang)

    # ----------------------------------------------------------
    # Article selection
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("chp:article:"), ChannelPublish.choose_article)
    async def article_selected(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        slug = callback.data.split(":", 2)[2]
        await _add_cta_button(state, {"type": "blog", "ref": slug})
        await _after_button_added(callback, state, lang)

    @router.callback_query(F.data == "chp:btn_no", ChannelPublish.choose_article)
    async def article_cancel(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _show_hashtags(callback, state, lang)

    # ----------------------------------------------------------
    # After button added → ask for more or move to hashtags
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:btn_yes", ChannelPublish.choose_btn_type)
    async def add_more_yes(callback: CallbackQuery, state: FSMContext):
        """Re-ask button type (from 'add more' prompt)."""
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.set_state(ChannelPublish.choose_btn_type)
        text = t("admin:channel:btn_type_prompt", lang)
        kb = kb_btn_type(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Hashtags (multi-select)
    # ----------------------------------------------------------

    @router.callback_query(F.data.startswith("chp:htag:"), ChannelPublish.ask_hashtags)
    async def toggle_hashtag(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        slug = callback.data.split(":", 2)[2]

        data = await state.get_data()
        selected = set(data.get("hashtag_slugs", []))

        if slug in selected:
            selected.discard(slug)
        else:
            selected.add(slug)

        await state.update_data(hashtag_slugs=list(selected))

        categories = data.get("categories", [])
        text = t("admin:channel:ask_hashtags", lang)
        kb = kb_hashtags(categories, selected, lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    @router.callback_query(F.data == "chp:htag_done", ChannelPublish.ask_hashtags)
    async def hashtags_done(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await _show_when(callback, state, lang)

    @router.callback_query(F.data == "chp:htag_skip", ChannelPublish.ask_hashtags)
    async def hashtags_skip(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.update_data(hashtag_slugs=[])
        await _show_when(callback, state, lang)

    # ----------------------------------------------------------
    # When to publish
    # ----------------------------------------------------------

    @router.callback_query(F.data == "chp:when:now", ChannelPublish.ask_when)
    async def publish_now(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        data = await state.get_data()
        post_id = data["post_id"]

        success = await _do_publish(post_id, data, callback.message.bot)
        if success:
            await callback.answer(t("admin:channel:published", lang), show_alert=True)
        else:
            await callback.answer(t("admin:channel:error", lang), show_alert=True)

        await state.clear()
        await mc.back_to_reply(
            callback.message, admin_main(lang),
            title=t("admin:main:title", lang),
        )

    @router.callback_query(F.data == "chp:when:schedule", ChannelPublish.ask_when)
    async def schedule_prompt(callback: CallbackQuery, state: FSMContext):
        lang = user_lang.get(callback.from_user.id, DEFAULT_LANG)
        await state.set_state(ChannelPublish.enter_datetime)
        text = t("admin:channel:enter_datetime", lang)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=t("common:cancel", lang), callback_data="chp:back_list",
            )]
        ])
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    # ----------------------------------------------------------
    # Enter datetime (text input)
    # ----------------------------------------------------------

    @router.message(ChannelPublish.enter_datetime)
    async def enter_datetime(message: Message, state: FSMContext):
        lang = user_lang.get(message.from_user.id, DEFAULT_LANG)
        text = (message.text or "").strip()

        # Parse DD.MM.YYYY HH:MM
        try:
            dt = datetime.strptime(text, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer(t("admin:channel:invalid_datetime", lang))
            return

        if dt <= datetime.utcnow():
            await message.answer(t("admin:channel:past_datetime", lang))
            return

        data = await state.get_data()
        post_id = data["post_id"]
        scheduled_at = dt.strftime("%Y-%m-%d %H:%M:%S")

        # Save CTA buttons and hashtags to the post
        update_payload: dict = {
            "status": "scheduled",
            "scheduled_at": scheduled_at,
        }

        cta_buttons = data.get("cta_buttons", [])
        if cta_buttons:
            update_payload["cta_buttons"] = json.dumps(cta_buttons)

        hashtag_slugs = data.get("hashtag_slugs", [])
        if hashtag_slugs:
            update_payload["hashtags"] = slugs_to_hashtag_text(hashtag_slugs)

        await api._request("PATCH", f"/channel-posts/{post_id}", json=update_payload)

        display_dt = dt.strftime("%d.%m.%Y %H:%M")
        await message.answer(t("admin:channel:scheduled", lang, display_dt))

        await state.clear()
        await mc.show(
            message, admin_main(lang),
            title=t("admin:main:title", lang),
            menu_context=None,
        )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    async def _add_cta_button(state: FSMContext, button: dict):
        data = await state.get_data()
        buttons = data.get("cta_buttons", [])
        buttons.append(button)
        await state.update_data(cta_buttons=buttons)

    async def _after_button_added(callback: CallbackQuery, state: FSMContext, lang: str):
        """After a CTA button was added, ask for more or proceed to hashtags."""
        data = await state.get_data()
        buttons = data.get("cta_buttons", [])

        await callback.answer(t("admin:channel:btn_added", lang))

        if len(buttons) >= MAX_CTA_BUTTONS:
            # Max reached → hashtags
            await _show_hashtags(callback, state, lang)
            return

        # Ask for more
        await state.set_state(ChannelPublish.choose_btn_type)
        text = t("admin:channel:btn_add_more", lang)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t("common:yes", lang), callback_data="chp:btn_yes"),
                InlineKeyboardButton(text=t("common:no", lang), callback_data="chp:btn_no"),
            ],
        ])
        await mc.edit_inline(callback.message, text, kb)

    async def _show_hashtags(callback: CallbackQuery, state: FSMContext, lang: str):
        """Show hashtag multi-select from blog categories."""
        categories = await api._request("GET", "/channel-posts/categories")
        if not categories:
            # No categories — skip to when
            await state.update_data(hashtag_slugs=[], categories=[])
            await _show_when(callback, state, lang)
            return

        await state.set_state(ChannelPublish.ask_hashtags)
        await state.update_data(categories=categories, hashtag_slugs=[])

        text = t("admin:channel:ask_hashtags", lang)
        kb = kb_hashtags(categories, set(), lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _show_when(callback: CallbackQuery, state: FSMContext, lang: str):
        """Show publish timing choice."""
        await state.set_state(ChannelPublish.ask_when)
        text = t("admin:channel:ask_when", lang)
        kb = kb_when(lang)
        await mc.edit_inline(callback.message, text, kb)
        await callback.answer()

    async def _do_publish(post_id: int, data: dict, bot) -> bool:
        """Actually publish the post to the public channel."""
        from bot.app.config import TG_CHANNEL_DRAFT_ID, TG_CHANNEL_PUBLIC_ID

        if not TG_CHANNEL_PUBLIC_ID or not TG_CHANNEL_DRAFT_ID:
            logger.error("Channel IDs not configured")
            return False

        post = await api._request("GET", f"/channel-posts/{post_id}")
        if not post:
            return False

        draft_chat_id = int(TG_CHANNEL_DRAFT_ID)
        public_chat_id = TG_CHANNEL_PUBLIC_ID
        # If numeric, convert
        try:
            public_chat_id = int(public_chat_id)
        except ValueError:
            pass  # keep as string (@channel_name)

        cta_buttons = data.get("cta_buttons", [])
        hashtag_slugs = data.get("hashtag_slugs", [])
        hashtag_text = slugs_to_hashtag_text(hashtag_slugs) if hashtag_slugs else ""

        # Build inline keyboard from CTA buttons
        reply_markup = _build_cta_keyboard(cta_buttons) if cta_buttons else None

        try:
            is_media_group = bool(post.get("media_group_id") and post.get("media_files"))

            if is_media_group:
                # Send media group
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

                sent_messages = await bot.send_media_group(
                    chat_id=public_chat_id,
                    media=media_group,
                )

                public_msg_id = sent_messages[0].message_id if sent_messages else None

                # Media groups don't support reply_markup → send as reply
                if reply_markup and sent_messages:
                    await bot.send_message(
                        chat_id=public_chat_id,
                        text="\u200b",  # zero-width space
                        reply_markup=reply_markup,
                        reply_to_message_id=sent_messages[0].message_id,
                    )
            else:
                # Single message — use copy_message
                caption_text = post.get("draft_text") or ""
                if hashtag_text:
                    caption_text = f"{caption_text}\n\n{hashtag_text}" if caption_text else hashtag_text

                # Check if there's media
                has_media = False
                files: list = []
                if post.get("media_files"):
                    try:
                        files = json.loads(post["media_files"])
                        has_media = bool(files)
                    except (json.JSONDecodeError, TypeError):
                        pass

                if has_media:
                    # Re-send media with new caption + keyboard
                    f_info = files[0]
                    sent = await _send_single_media(
                        bot, public_chat_id, f_info,
                        caption_text, reply_markup,
                    )
                    public_msg_id = sent.message_id if sent else None
                elif caption_text:
                    # Text-only message
                    sent = await bot.send_message(
                        chat_id=public_chat_id,
                        text=caption_text,
                        reply_markup=reply_markup,
                    )
                    public_msg_id = sent.message_id
                else:
                    # Copy as-is (fallback)
                    result = await bot.copy_message(
                        chat_id=public_chat_id,
                        from_chat_id=draft_chat_id,
                        message_id=post["draft_message_id"],
                        reply_markup=reply_markup,
                    )
                    public_msg_id = result.message_id

            # Update post status
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            update_data: dict = {
                "status": "published",
                "published_at": now,
            }
            if public_msg_id:
                update_data["public_message_id"] = public_msg_id
                update_data["public_chat_id"] = int(public_chat_id) if isinstance(public_chat_id, int) else None

            if cta_buttons:
                update_data["cta_buttons"] = json.dumps(cta_buttons)
            if hashtag_text:
                update_data["hashtags"] = hashtag_text

            await api._request("PATCH", f"/channel-posts/{post_id}", json=update_data)
            return True

        except Exception:
            logger.exception("Failed to publish post %d", post_id)
            await api._request(
                "PATCH", f"/channel-posts/{post_id}",
                json={"status": "failed"},
            )
            return False

    return router


# ==============================================================
# Standalone helpers (no closure needed)
# ==============================================================

def _build_cta_keyboard(
    cta_buttons: list[dict],
) -> InlineKeyboardMarkup | None:
    """Build InlineKeyboardMarkup from CTA button specs."""
    from bot.app.config import CHANNEL_URL

    base_url = (CHANNEL_URL or "https://upgradelpg.site").rstrip("/")
    rows = []

    for btn in cta_buttons:
        btn_type = btn["type"]
        ref = btn.get("ref")

        if btn_type == "booking":
            if ref:
                url = f"{base_url}/book?service={ref}"
            else:
                url = f"{base_url}/book"
            text = "📋 Записаться"
        elif btn_type == "blog":
            if ref:
                url = f"{base_url}/blog/{ref}.html"
            else:
                url = f"{base_url}/blog"
            text = "📖 Читать"
        elif btn_type == "pricing":
            url = f"{base_url}/pricing"
            text = "💰 Цены"
        elif btn_type == "home":
            url = base_url
            text = "🌐 На сайт"
        else:
            continue

        rows.append([InlineKeyboardButton(text=text, url=url)])

    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send_single_media(bot, chat_id, f_info: dict, caption: str, reply_markup):
    """Send a single media file with caption and optional keyboard."""
    media_type = f_info["type"]
    file_id = f_info["file_id"]

    if media_type == "photo":
        return await bot.send_photo(
            chat_id=chat_id, photo=file_id,
            caption=caption or None, reply_markup=reply_markup,
        )
    elif media_type == "video":
        return await bot.send_video(
            chat_id=chat_id, video=file_id,
            caption=caption or None, reply_markup=reply_markup,
        )
    elif media_type == "animation":
        return await bot.send_animation(
            chat_id=chat_id, animation=file_id,
            caption=caption or None, reply_markup=reply_markup,
        )
    elif media_type == "document":
        return await bot.send_document(
            chat_id=chat_id, document=file_id,
            caption=caption or None, reply_markup=reply_markup,
        )
    return None
