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

        # 5. Format packages
        lines = [t("client:packages:title", lang), ""]

        for pkg in active:
            pkg_id = pkg["id"]
            lines.append(f"📦 {pkg['package_name']}")

            # Get breakdown for this package
            remaining_data = await _get_package_remaining(pkg_id)

            if remaining_data and remaining_data.get("breakdown"):
                breakdown = remaining_data["breakdown"]
                for i, item in enumerate(breakdown):
                    service_id = str(item["service_id"])
                    service_name = service_names.get(service_id, f"#{service_id}")
                    remaining = item["remaining"]
                    total = item["quantity"]

                    remaining_text = t("client:packages:remaining", lang) % (remaining, total)
                    prefix = "├" if i < len(breakdown) - 1 or pkg.get("valid_to") else "└"
                    lines.append(f"{prefix} {service_name}: {remaining_text}")

            # Valid to
            valid_to = pkg.get("valid_to")
            if valid_to:
                date_str = str(valid_to)[:10]
                try:
                    formatted = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
                    lines.append("└ " + t("client:packages:valid_until", lang) % formatted)
                except ValueError:
                    lines.append("└ " + t("client:packages:valid_until", lang) % date_str)
            else:
                lines.append("└ " + t("client:packages:unlimited", lang))

            lines.append("")

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
