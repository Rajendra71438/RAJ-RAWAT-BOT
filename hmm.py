"""
╔══════════════════════════════════════════════════╗
║         ADVANCED CHANNEL MANAGER BOT             ║
║         Single file — paste & run               ║
╚══════════════════════════════════════════════════╝

pip install python-telegram-bot==21.3 python-dotenv==1.0.1

Fill in .env:
    BOT_TOKEN=your_token
    MAIN_ADMIN_ID=your_telegram_id
    SOURCE_CHANNEL_ID=-100xxxxxxxxx
"""

import logging
import json
import os
from datetime import datetime, date
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ChatJoinRequestHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

load_dotenv()

# ═══════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════
BOT_TOKEN        = os.getenv("BOT_TOKEN")
MAIN_ADMIN_ID    = int(os.getenv("MAIN_ADMIN_ID", "0"))
SOURCE_CHANNEL   = os.getenv("SOURCE_CHANNEL_ID")   # e.g. -1001234567890
ADMIN_PASSWORD   = "9286"
DATA_FILE        = "bot_data.json"

# Minimal logging: only startup and broadcast results
logging.basicConfig(
    format="%(message)s",
    level=logging.WARNING
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ═══════════════════════════════════════════════════
#  DATA HELPERS
# ═══════════════════════════════════════════════════
def default_data():
    return {
        "sub_admins": {},
        "channels": [],
        "msg_sequence": [],
        "pending_requests": [],
        "approved_users": [],
        "broadcast_users": [],
        "broadcasts": [],
        "stats": {
            "total_users": 0,
            "daily": {}
        }
    }

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            if "broadcast_users" not in data:
                data["broadcast_users"] = []
            return data
    d = default_data()
    save_data(d)
    return d

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_main_admin(uid: int) -> bool:
    return uid == MAIN_ADMIN_ID

def is_sub_admin(uid: int) -> bool:
    bd = load_data()
    return str(uid) in bd.get("sub_admins", {})

def is_any_admin(uid: int) -> bool:
    return is_main_admin(uid) or is_sub_admin(uid)

def get_sub_admin_perms(uid: int) -> dict:
    bd = load_data()
    sa = bd.get("sub_admins", {}).get(str(uid), {})
    return sa.get("permissions", {})

def has_perm(uid: int, perm: str) -> bool:
    if is_main_admin(uid):
        return True
    return get_sub_admin_perms(uid).get(perm, False)

def today_str():
    return date.today().isoformat()

def record_new_user(uid: int):
    bd = load_data()
    if uid not in bd["approved_users"]:
        bd["approved_users"].append(uid)
        bd["stats"]["total_users"] += 1
        t = today_str()
        bd["stats"]["daily"][t] = bd["stats"]["daily"].get(t, 0) + 1
        save_data(bd)

def record_broadcast_user(uid: int):
    bd = load_data()
    if uid not in bd.get("broadcast_users", []):
        bd.setdefault("broadcast_users", []).append(uid)
        save_data(bd)

# ═══════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════
def main_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats",             callback_data="ma_stats"),
            InlineKeyboardButton("👥 Sub Admins",        callback_data="ma_subadmins"),
        ],
        [
            InlineKeyboardButton("📢 Channels",          callback_data="ma_channels"),
            InlineKeyboardButton("📨 Msg Sequence",      callback_data="ma_msgseq"),
        ],
        [
            InlineKeyboardButton("📋 Pending Requests",  callback_data="ma_pending"),
        ],
        [
            InlineKeyboardButton("📣 Broadcasts",        callback_data="ma_broadcasts"),
            InlineKeyboardButton("📡 Broadcast Msg",     callback_data="ma_broadcast"),
        ],
    ])

def sub_admin_menu(uid: int) -> InlineKeyboardMarkup:
    perms = get_sub_admin_perms(uid)
    buttons = []
    if perms.get("see_stats"):
        buttons.append([InlineKeyboardButton("📊 Stats", callback_data="sa_stats")])
    if perms.get("broadcast"):
        buttons.append([InlineKeyboardButton("📡 Broadcast Msg", callback_data="sa_broadcast")])
    if perms.get("accept_requests"):
        buttons.append([InlineKeyboardButton("📋 Pending Requests", callback_data="sa_pending")])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="sa_refresh")])
    if not buttons:
        buttons = [[InlineKeyboardButton("ℹ️ No permissions", callback_data="noop")]]
    return InlineKeyboardMarkup(buttons)

def back_btn(target="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])

# ═══════════════════════════════════════════════════
#  MENU TEXT
# ═══════════════════════════════════════════════════
def main_admin_text():
    bd = load_data()
    return (
        f"👑 *MAIN ADMIN PANEL*\n"
        f"{'━'*28}\n"
        f"👥 Total Users: *{bd['stats']['total_users']}*\n"
        f"📢 Channels: *{len(bd['channels'])}*\n"
        f"📨 Msg Sequence: *{len(bd['msg_sequence'])} msgs*\n"
        f"⏳ Pending: *{len(bd['pending_requests'])}*\n"
        f"📡 Broadcast Users: *{len(bd.get('broadcast_users', []))}*\n"
        f"{'━'*28}\n"
        f"_Select an option below_ 👇"
    )

def sub_admin_text(uid: int):
    bd = load_data()
    sa = bd["sub_admins"].get(str(uid), {})
    name = sa.get("name", "Sub Admin")
    perms = sa.get("permissions", {})
    active = [k.replace("_", " ").title() for k, v in perms.items() if v]
    return (
        f"🔰 *SUB ADMIN PANEL*\n"
        f"{'━'*28}\n"
        f"👤 Welcome, *{name}*!\n"
        f"🔑 Permissions: {', '.join(active) if active else 'None'}\n"
        f"{'━'*28}\n"
        f"_Select an option below_ 👇"
    )

# ═══════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("awaiting_password"):
        return
    if is_main_admin(uid):
        if not context.user_data.get("main_admin_auth"):
            context.user_data["awaiting_password"] = True
            await update.message.reply_text(
                "👑 *Main Admin Access*\n\n🔐 Enter password:",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        await show_main_menu(update, context)
    elif is_sub_admin(uid):
        await update.message.reply_text(
            sub_admin_text(uid),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=sub_admin_menu(uid)
        )
    else:
        await update.message.reply_text("❌ Not authorized.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    text = main_admin_text()
    kb   = main_admin_menu()
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# ═══════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    text = update.message.text or ""

    if text.strip().lower() == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("❌ Cancelled.")
        return

    if context.user_data.get("awaiting_password") and is_main_admin(uid):
        if text.strip() == ADMIN_PASSWORD:
            context.user_data["awaiting_password"] = False
            context.user_data["main_admin_auth"]   = True
            await update.message.reply_text("✅ *Access Granted!*", parse_mode=ParseMode.MARKDOWN)
            await show_main_menu(update, context)
        else:
            await update.message.reply_text("❌ Wrong password.")
        return

    state = context.user_data.get("state")
    if not is_any_admin(uid):
        return

    # Add sub admin id
    if state == "add_subadmin_id":
        try:
            new_id = int(text.strip())
            bd = load_data()
            if str(new_id) in bd["sub_admins"]:
                await update.message.reply_text("⚠️ Already a sub admin!")
                context.user_data.clear()
                context.user_data["main_admin_auth"] = True
                return
            context.user_data["new_subadmin_id"] = new_id
            context.user_data["state"] = "add_subadmin_name"
            await update.message.reply_text("✏️ Send name/label:")
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
        return

    if state == "add_subadmin_name":
        new_id   = context.user_data.get("new_subadmin_id")
        new_name = text.strip()
        bd = load_data()
        bd["sub_admins"][str(new_id)] = {
            "name": new_name,
            "permissions": {
                "see_stats": True,
                "broadcast": False,
                "accept_requests": False,
            }
        }
        save_data(bd)
        context.user_data.clear()
        context.user_data["main_admin_auth"] = True
        await update.message.reply_text(
            f"✅ Sub admin *{new_name}* added!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_btn("main_menu")
        )
        return

    # Add channel
    if state == "add_channel":
        ch = text.strip()
        if not (ch.startswith("-") or ch.startswith("@")):
            await update.message.reply_text("❌ Invalid channel format.")
            return
        bd = load_data()
        if ch not in bd["channels"]:
            bd["channels"].append(ch)
            save_data(bd)
            await update.message.reply_text(f"✅ Channel `{ch}` added!", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("⚠️ Already exists.")
        context.user_data.clear()
        context.user_data["main_admin_auth"] = True
        return

    # Add msg to sequence
    if state == "add_msg_seq":
        try:
            msg_id = int(text.strip())
            bd = load_data()
            bd["msg_sequence"].append(msg_id)
            save_data(bd)
            pos = len(bd["msg_sequence"])
            context.user_data.clear()
            context.user_data["main_admin_auth"] = True
            await update.message.reply_text(
                f"✅ Msg `{msg_id}` added at pos *{pos}*.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_btn("ma_msgseq")
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
        return

    # Insert msg at position
    if state == "insert_msg_pos":
        try:
            parts = text.strip().split()
            pos    = int(parts[0]) - 1
            msg_id = int(parts[1])
            bd = load_data()
            bd["msg_sequence"].insert(pos, msg_id)
            save_data(bd)
            context.user_data.clear()
            context.user_data["main_admin_auth"] = True
            await update.message.reply_text(
                f"✅ Msg `{msg_id}` inserted at pos *{pos+1}*.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_btn("ma_msgseq")
            )
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Format: `<pos> <msg_id>`")
        return

    # Remove msg by ID
    if state == "remove_msg_id":
        try:
            msg_id = int(text.strip())
            bd = load_data()
            if msg_id in bd["msg_sequence"]:
                bd["msg_sequence"].remove(msg_id)
                save_data(bd)
                await update.message.reply_text(f"✅ Msg `{msg_id}` removed.", parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("❌ Not found.")
            context.user_data.clear()
            context.user_data["main_admin_auth"] = True
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
        return

    # Change msg by ID
    if state == "change_msg_id":
        try:
            parts  = text.strip().split()
            old_id = int(parts[0])
            new_id = int(parts[1])
            bd = load_data()
            if old_id in bd["msg_sequence"]:
                idx = bd["msg_sequence"].index(old_id)
                bd["msg_sequence"][idx] = new_id
                save_data(bd)
                await update.message.reply_text(
                    f"✅ Replaced `{old_id}` → `{new_id}`.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text("❌ Old ID not found.")
            context.user_data.clear()
            context.user_data["main_admin_auth"] = True
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Format: `<old_id> <new_id>`")
        return

    # Broadcast text (send to all saved users)
    if state in ("ma_broadcast_text", "sa_broadcast_text"):
        bd = load_data()
        broadcast_users = bd.get("broadcast_users", [])
        if not broadcast_users:
            await update.message.reply_text("❌ No users to broadcast to.")
            context.user_data.clear()
            if is_main_admin(uid):
                context.user_data["main_admin_auth"] = True
            return

        # Save broadcast record
        bcast_id = len(bd["broadcasts"]) + 1
        bd["broadcasts"].append({
            "id":             bcast_id,
            "by":             update.effective_user.first_name,
            "by_id":          uid,
            "text":           text,
            "timestamp":      datetime.now().isoformat()
        })
        save_data(bd)

        sent, fail = 0, 0
        for user_id in broadcast_users:
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
                sent += 1
            except Exception:
                fail += 1

        # Only print broadcast result
        print(f"✅ Broadcast sent: {sent} success, {fail} failed")

        context.user_data.clear()
        if is_main_admin(uid):
            context.user_data["main_admin_auth"] = True

        await update.message.reply_text(
            f"✅ Broadcast sent!\n✅ Success: {sent}\n❌ Failed: {fail}",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Delete broadcast by ID (main admin only)
    if state == "delete_broadcast_id" and is_main_admin(uid):
        try:
            bcast_id = int(text.strip())
            bd = load_data()
            before = len(bd["broadcasts"])
            bd["broadcasts"] = [b for b in bd["broadcasts"] if b["id"] != bcast_id]
            save_data(bd)
            if len(bd["broadcasts"]) < before:
                await update.message.reply_text(f"✅ Broadcast #{bcast_id} deleted.")
            else:
                await update.message.reply_text("❌ Not found.")
            context.user_data.clear()
            context.user_data["main_admin_auth"] = True
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
        return

# ═══════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    data = query.data

    if data == "noop":
        return

    if is_main_admin(uid) and not context.user_data.get("main_admin_auth"):
        await query.answer("🔐 Authenticate first.", show_alert=True)
        return

    if not is_any_admin(uid):
        await query.answer("❌ Not authorized.", show_alert=True)
        return

    # Main menu
    if data == "main_menu" and is_main_admin(uid):
        await show_main_menu(update, context, edit=True)
        return

    if data == "sa_main_menu" and is_sub_admin(uid):
        await query.edit_message_text(
            sub_admin_text(uid),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=sub_admin_menu(uid)
        )
        return

    if data == "sa_refresh" and is_sub_admin(uid):
        await query.edit_message_text(
            sub_admin_text(uid),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=sub_admin_menu(uid)
        )
        return

    # Stats
    if data in ("ma_stats", "sa_stats"):
        if not has_perm(uid, "see_stats"):
            await query.answer("❌ No permission.", show_alert=True)
            return
        bd = load_data()
        daily = bd["stats"]["daily"]
        today = daily.get(today_str(), 0)
        days_text = ""
        for d in sorted(daily.keys(), reverse=True)[:7]:
            days_text += f"  📅 `{d}`: *{daily[d]}* joins\n"
        back = "main_menu" if is_main_admin(uid) else "sa_main_menu"
        await query.edit_message_text(
            f"📊 *STATISTICS*\n{'━'*26}\n"
            f"👥 Total: *{bd['stats']['total_users']}*\n"
            f"📅 Today: *{today}*\n"
            f"📢 Channels: *{len(bd['channels'])}*\n"
            f"📨 Sequence: *{len(bd['msg_sequence'])} msgs*\n"
            f"⏳ Pending: *{len(bd['pending_requests'])}*\n"
            f"📡 Broadcast Users: *{len(bd.get('broadcast_users', []))}*\n"
            f"{'━'*26}\n📆 *Last 7 Days:*\n{days_text}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_btn(back)
        )

    # Pending requests
    elif data in ("ma_pending", "sa_pending"):
        if not has_perm(uid, "accept_requests") and not is_main_admin(uid):
            await query.answer("❌ No permission.", show_alert=True)
            return
        bd = load_data()
        pending = bd.get("pending_requests", [])
        if not pending:
            back = "main_menu" if is_main_admin(uid) else "sa_main_menu"
            await query.edit_message_text("✅ No pending requests.", reply_markup=back_btn(back))
            return
        text = f"⏳ *Pending Requests* ({len(pending)})\n{'━'*26}\n"
        for i, r in enumerate(pending[:20], 1):
            text += f"{i}. 👤 `{r.get('user_name', 'Unknown')}` (ID: `{r['user_id']}`)\n"
        if len(pending) > 20:
            text += f"\n... and {len(pending)-20} more."
        back = "main_menu" if is_main_admin(uid) else "sa_main_menu"
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_btn(back))

    # Broadcasts history (main admin only)
    elif data == "ma_broadcasts" and is_main_admin(uid):
        bd = load_data()
        broadcasts = bd.get("broadcasts", [])
        broadcast_users_count = len(bd.get("broadcast_users", []))
        text = f"📣 *Broadcast History*\n{'━'*26}\n👥 Total Users: *{broadcast_users_count}*\n\n"
        if not broadcasts:
            text += "_No broadcasts sent yet._"
        else:
            text += f"*Recent Broadcasts* ({len(broadcasts)})\n{'━'*26}\n"
            for b in broadcasts[-10:]:
                text += (
                    f"🆔 #{b['id']} | 👤 {b['by']}\n"
                    f"🕐 {b['timestamp'][:16]}\n"
                    f"💬 _{b['text'][:60]}{'...' if len(b['text'])>60 else ''}_\n\n"
                )
        buttons = [
            [InlineKeyboardButton("📊 View Broadcast Users", callback_data="ma_view_broadcast_users")],
            [InlineKeyboardButton("🗑 Delete Broadcast", callback_data="ma_delete_broadcast")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "ma_view_broadcast_users" and is_main_admin(uid):
        bd = load_data()
        users = bd.get("broadcast_users", [])
        text = f"📡 *Broadcast Users* ({len(users)})\n{'━'*26}\n"
        for i, uid_ in enumerate(users[:30], 1):
            text += f"{i}. `{uid_}`\n"
        if len(users) > 30:
            text += f"\n... and {len(users)-30} more."
        if not users:
            text += "_No users yet._"
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_btn("ma_broadcasts"))

    elif data == "ma_delete_broadcast" and is_main_admin(uid):
        context.user_data["state"] = "delete_broadcast_id"
        await query.edit_message_text("🗑 Send broadcast ID to delete:", parse_mode=ParseMode.MARKDOWN)

    # Broadcast message (send to all saved users)
    elif data in ("ma_broadcast", "sa_broadcast"):
        if not has_perm(uid, "broadcast") and not is_main_admin(uid):
            await query.answer("❌ No permission.", show_alert=True)
            return
        bd = load_data()
        count = len(bd.get("broadcast_users", []))
        state_key = "ma_broadcast_text" if is_main_admin(uid) else "sa_broadcast_text"
        context.user_data["state"] = state_key
        await query.edit_message_text(
            f"📡 *Broadcast Message*\n\n👥 Recipients: *{count}* users\n\nSend the message to broadcast:",
            parse_mode=ParseMode.MARKDOWN
        )

    # Channels
    elif data == "ma_channels" and is_main_admin(uid):
        bd = load_data()
        channels = bd.get("channels", [])
        text = f"📢 *Channels* ({len(channels)})\n{'━'*26}\n"
        for i, ch in enumerate(channels, 1):
            text += f"{i}. `{ch}`\n"
        if not channels:
            text += "_None._"
        buttons = [
            [InlineKeyboardButton("➕ Add", callback_data="ma_add_channel"),
             InlineKeyboardButton("🗑 Remove", callback_data="ma_remove_channel")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "ma_add_channel" and is_main_admin(uid):
        context.user_data["state"] = "add_channel"
        await query.edit_message_text("➕ Send channel ID or @username:", parse_mode=ParseMode.MARKDOWN)

    elif data == "ma_remove_channel" and is_main_admin(uid):
        bd = load_data()
        channels = bd.get("channels", [])
        if not channels:
            await query.answer("No channels.", show_alert=True)
            return
        buttons = [[InlineKeyboardButton(f"🗑 {ch}", callback_data=f"del_ch_{ch}")] for ch in channels]
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="ma_channels")])
        await query.edit_message_text("🗑 Select channel to remove:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("del_ch_") and is_main_admin(uid):
        ch = data[7:]
        bd = load_data()
        if ch in bd["channels"]:
            bd["channels"].remove(ch)
            save_data(bd)
            await query.answer(f"Removed {ch}", show_alert=True)
        await show_main_menu(update, context, edit=True)

    # Message sequence
    elif data == "ma_msgseq" and is_main_admin(uid):
        bd = load_data()
        seq = bd.get("msg_sequence", [])
        text = f"📨 *Message Sequence*\n{'━'*26}\nSource: `{SOURCE_CHANNEL}`\n\n"
        if seq:
            for i, mid in enumerate(seq, 1):
                text += f"{i}. `{mid}`\n"
        else:
            text += "_Empty._\n"
        buttons = [
            [InlineKeyboardButton("➕ Add", callback_data="ma_add_msg"),
             InlineKeyboardButton("📍 Insert", callback_data="ma_insert_msg")],
            [InlineKeyboardButton("🔄 Change", callback_data="ma_change_msg"),
             InlineKeyboardButton("🗑 Remove", callback_data="ma_remove_msg")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "ma_add_msg" and is_main_admin(uid):
        context.user_data["state"] = "add_msg_seq"
        await query.edit_message_text("➕ Send message ID:", parse_mode=ParseMode.MARKDOWN)

    elif data == "ma_insert_msg" and is_main_admin(uid):
        context.user_data["state"] = "insert_msg_pos"
        await query.edit_message_text("📍 Send `<position> <msg_id>`:", parse_mode=ParseMode.MARKDOWN)

    elif data == "ma_change_msg" and is_main_admin(uid):
        context.user_data["state"] = "change_msg_id"
        await query.edit_message_text("🔄 Send `<old_id> <new_id>`:", parse_mode=ParseMode.MARKDOWN)

    elif data == "ma_remove_msg" and is_main_admin(uid):
        context.user_data["state"] = "remove_msg_id"
        await query.edit_message_text("🗑 Send message ID to remove:", parse_mode=ParseMode.MARKDOWN)

    # Sub admins
    elif data == "ma_subadmins" and is_main_admin(uid):
        bd = load_data()
        subs = bd.get("sub_admins", {})
        text = f"👥 *Sub Admins* ({len(subs)})\n{'━'*26}\n"
        for sid, info in subs.items():
            perms = info.get("permissions", {})
            active = [k.replace("_", " ").title() for k, v in perms.items() if v]
            text += f"👤 *{info['name']}* (`{sid}`)\n   Perms: {', '.join(active) if active else 'none'}\n\n"
        if not subs:
            text += "_None._"
        buttons = [
            [InlineKeyboardButton("➕ Add", callback_data="ma_add_subadmin"),
             InlineKeyboardButton("🗑 Remove", callback_data="ma_remove_subadmin")],
            [InlineKeyboardButton("⚙️ Edit Permissions", callback_data="ma_edit_perms")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "ma_add_subadmin" and is_main_admin(uid):
        context.user_data["state"] = "add_subadmin_id"
        await query.edit_message_text("➕ Send Telegram user ID:", parse_mode=ParseMode.MARKDOWN)

    elif data == "ma_remove_subadmin" and is_main_admin(uid):
        bd = load_data()
        subs = bd.get("sub_admins", {})
        if not subs:
            await query.answer("No sub admins.", show_alert=True)
            return
        buttons = [[InlineKeyboardButton(f"🗑 {info['name']}", callback_data=f"del_sa_{sid}")] for sid, info in subs.items()]
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="ma_subadmins")])
        await query.edit_message_text("🗑 Select to remove:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("del_sa_") and is_main_admin(uid):
        sid = data[7:]
        bd = load_data()
        if sid in bd["sub_admins"]:
            del bd["sub_admins"][sid]
            save_data(bd)
            await query.answer("Removed", show_alert=True)
        await show_main_menu(update, context, edit=True)

    elif data == "ma_edit_perms" and is_main_admin(uid):
        bd = load_data()
        subs = bd.get("sub_admins", {})
        if not subs:
            await query.answer("No sub admins.", show_alert=True)
            return
        buttons = [[InlineKeyboardButton(f"⚙️ {info['name']}", callback_data=f"perms_{sid}")] for sid, info in subs.items()]
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="ma_subadmins")])
        await query.edit_message_text("⚙️ Select sub admin:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("perms_") and is_main_admin(uid):
        sid = data[6:]
        await show_perm_editor(query, sid)

    elif data.startswith("toggleperm_") and is_main_admin(uid):
        parts = data.split("_", 2)
        sid, perm = parts[1], parts[2]
        bd = load_data()
        if sid not in bd["sub_admins"]:
            await query.answer("Not found.", show_alert=True)
            return
        current = bd["sub_admins"][sid]["permissions"].get(perm, False)
        bd["sub_admins"][sid]["permissions"][perm] = not current
        save_data(bd)
        await show_perm_editor(query, sid)

async def show_perm_editor(query, sid: str):
    bd = load_data()
    sa = bd["sub_admins"].get(sid, {})
    name = sa.get("name", sid)
    perms = sa.get("permissions", {})
    labels = {
        "see_stats": "📊 See Stats",
        "broadcast": "📡 Broadcast Msg",
        "accept_requests": "✅ Accept Requests",
    }
    buttons = []
    for key, label in labels.items():
        tick = "✅" if perms.get(key, False) else "❌"
        buttons.append([InlineKeyboardButton(f"{tick} {label}", callback_data=f"toggleperm_{sid}_{key}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="ma_subadmins")])
    await query.edit_message_text(
        f"⚙️ *Permissions — {name}*\n{'━'*26}\nTap to toggle:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ═══════════════════════════════════════════════════
#  JOIN REQUEST HANDLER
# ═══════════════════════════════════════════════════
async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request: ChatJoinRequest = update.chat_join_request
    uid = request.from_user.id
    uname = request.from_user.username or request.from_user.first_name
    ch_id = request.chat.id
    bd = load_data()
    record_broadcast_user(uid)
    await send_welcome_sequence(uid, context)
    already = any(r["user_id"] == uid for r in bd["pending_requests"])
    if not already:
        bd["pending_requests"].append({
            "user_id": uid,
            "user_name": uname,
            "channel_id": str(ch_id),
            "timestamp": datetime.now().isoformat()
        })
        save_data(bd)

# ═══════════════════════════════════════════════════
#  SEND WELCOME SEQUENCE
# ═══════════════════════════════════════════════════
async def send_welcome_sequence(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    bd = load_data()
    seq = bd.get("msg_sequence", [])
    if not seq or not SOURCE_CHANNEL:
        return
    for msg_id in seq:
        try:
            await context.bot.forward_message(
                chat_id=user_id,
                from_chat_id=SOURCE_CHANNEL,
                message_id=msg_id
            )
        except Exception:
            pass

# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
def main():
    print("✅ Bot is running!")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()