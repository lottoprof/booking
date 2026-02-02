# bot/app/flows/client/my_packages.py
"""
Flow for displaying client's purchased packages with remaining services.
"""

from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.app.i18n.loader import t, DEFAULT_LANG
from bot.app.utils.api import api


def setup(menu_controller):
    """Setup router for my_packages flow."""
    router = Router(name="client_my_packages")
    mc = menu_controller

    async def show_my_packages(message: Message, user_id: int, lang: str):
        """Show client's purchased packages with remaining services."""
        # 1. Get user's packages
        packages = await api.get_user_packages(user_id)

        # 2. Filter active packages (not closed, total_remaining > 0)
        active = [
            p for p in packages
            if not p.get("is_closed") and p.get("total_remaining", 0) > 0
        ]

        # 3. If no active packages
        if not active:
            text = t("client:packages:empty", lang)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("common:hide", lang), callback_data="mypkg:hide")]
            ])
            await mc.show_inline_readonly(message, text, kb)
            return

        # 4. Get services for name lookup
        services = await api.get_services()
        service_names = {str(s["id"]): s["name"] for s in services}

        # 5. Each package as a separate message
        for pkg in active:
            remaining_data = await _get_package_remaining(pkg["id"])
            breakdown = remaining_data.get("breakdown", []) if remaining_data else []

            lines = [f"📦 {pkg['package_name']}"]

            if len(breakdown) == 1:
                # Simple package (1 service)
                item = breakdown[0]
                used = item["quantity"] - item["remaining"]
                lines.append(f"Сделано: {used}")
                lines.append(f"Осталось: {item['remaining']}")
            elif len(breakdown) > 1:
                # Complex package (multiple services)
                used_parts = []
                remaining_parts = []
                for item in breakdown:
                    name = service_names.get(str(item["service_id"]), "?")
                    used = item["quantity"] - item["remaining"]
                    used_parts.append(f"{name} {used}")
                    remaining_parts.append(f"{name} {item['remaining']}")
                lines.append(f"Сделано: {', '.join(used_parts)}")
                lines.append(f"Осталось: {', '.join(remaining_parts)}")

            # Valid to
            valid_to = pkg.get("valid_to")
            if valid_to:
                date_str = str(valid_to)[:10]
                try:
                    formatted = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
                    lines.append(f"⏳ до {formatted}")
                except ValueError:
                    lines.append(f"⏳ до {date_str}")

            text = "\n".join(lines)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("common:hide", lang), callback_data="mypkg:hide")]
            ])
            await mc.show_inline_readonly(message, text, kb)

    async def _get_package_remaining(package_id: int) -> dict | None:
        """Get remaining breakdown for a client package."""
        return await api._request("GET", f"/client_packages/{package_id}/remaining")

    @router.callback_query(F.data == "mypkg:hide")
    async def handle_hide(callback: CallbackQuery):
        """Hide the packages message."""
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()

    @router.callback_query(F.data == "mypkg:noop")
    async def handle_noop(callback: CallbackQuery):
        await callback.answer()

    router.show_my_packages = show_my_packages
    return router
