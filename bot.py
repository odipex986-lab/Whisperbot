#!/usr/bin/env python3
"""
PsstBot — Telegram inline whisper bot (Pyrogram / MTProto)

Two modes:
  • Open whisper     → @bot your message           (anyone can tap & read)
  • Targeted whisper → @bot your message @username  (only that user, matched by ID)

Why Pyrogram?
  Pyrogram uses MTProto, so it can resolve @username → numeric user ID
  directly. This means targeted whispers stay locked to the correct person
  even if they later change their username.
"""

import os
import re
import uuid
import logging
from collections import OrderedDict

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    InlineQuery,
    CallbackQuery,
)
from pyrogram.errors import (
    UsernameNotOccupied,
    UsernameInvalid,
    PeerIdInvalid,
    UserDeactivated,
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

API_ID   = int(os.environ["API_ID"])    # from my.telegram.org
API_HASH = os.environ["API_HASH"]       # from my.telegram.org
BOT_TOKEN = os.environ["BOT_TOKEN"]     # from @BotFather

# ── In-memory whisper store ───────────────────────────────────────────────────
# Each entry: {text, sender, sender_id, target_id, target_username}
# target_id       → numeric Telegram user ID (None = open whisper)
# target_username → @username string, kept only as fallback display

MAX_WHISPERS = 10_000
whispers: OrderedDict = OrderedDict()


def store_whisper(wid: str, data: dict) -> None:
    if len(whispers) >= MAX_WHISPERS:
        whispers.popitem(last=False)
    whispers[wid] = data


# ── Recent recipients store ───────────────────────────────────────────────────
# Tracks the last MAX_RECENT people each sender has whispered to.
# recent_recipients[sender_id] = [
#     {"target_id": int, "display_name": str, "username": str | None},
#     ...   (index 0 = most recent)
# ]

MAX_RECENT = 3
recent_recipients: dict = {}


def update_recent(sender_id: int, target_id: int,
                  display_name: str, username) -> None:
    """Add or bump a recipient to the top of the sender's recent list."""
    history = recent_recipients.setdefault(sender_id, [])
    # Remove existing entry for this target to avoid duplicates
    history = [r for r in history if r["target_id"] != target_id]
    # Prepend as most recent
    history.insert(0, {
        "target_id":    target_id,
        "display_name": display_name,
        "username":     username,
    })
    recent_recipients[sender_id] = history[:MAX_RECENT]


# ── Query parser ──────────────────────────────────────────────────────────────

USERNAME_RE = re.compile(r'^@([a-zA-Z][a-zA-Z0-9_]{3,31})$')
USERID_RE   = re.compile(r'^\d{5,12}$')   # Telegram IDs: ~5–12 digits


def parse_query(text: str) -> tuple:
    """
    Detects the target at the end of the query.

    Returns:
        (message, target_username, target_id)

        target_username — str without @  (e.g. "alice")   when @username used
        target_id       — int            (e.g. 123456789) when numeric ID used
        Both are None for open whispers (exactly one will be set when targeted).

    Examples:
        "hello world"            → ("hello world", None,    None)
        "hello world @alice"     → ("hello world", "alice", None)
        "hello world 123456789"  → ("hello world", None,    123456789)
    """
    parts = text.rsplit(None, 1)
    if len(parts) == 2:
        last = parts[1]
        msg  = parts[0].strip()
        if msg:
            if USERNAME_RE.match(last):
                return msg, last[1:], None          # @username → strip @
            if USERID_RE.match(last):
                return msg, None, int(last)         # raw numeric ID
    return text, None, None


# ── Pyrogram client ───────────────────────────────────────────────────────────

app = Client(
    name="psstbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,          # no session file needed — safe for Railway
)


# ── /start ────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message) -> None:
    me = await client.get_me()
    name = message.from_user.first_name

    await message.reply(
        f"Hey **{name}**! 👋 I'm **PsstBot** — a secret whisper bot! 🤫\n\n"
        "📖 **Three ways to whisper:**\n\n"
        "1️⃣ **Open** — anyone can read:\n"
        f"`@{me.username} your message`\n\n"
        "2️⃣ **By @username** — only that person:\n"
        f"`@{me.username} your message @username`\n\n"
        "3️⃣ **By user ID** — for people with no username:\n"
        f"`@{me.username} your message 123456789`\n\n"
        "💡 Both targeted modes lock by **numeric user ID** — "
        "secure even if they change their @handle.\n\n"
        "Try me in any group or DM! 🚀",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, message: Message) -> None:
    me = await client.get_me()

    await message.reply(
        "🤫 **PsstBot Help**\n\n"
        "🌐 **Open** (anyone can read):\n"
        f"`@{me.username} your message`\n\n"
        "🔒 **By @username** (only that person):\n"
        f"`@{me.username} your message @username`\n\n"
        "🔒 **By user ID** (no username needed):\n"
        f"`@{me.username} your message 123456789`\n\n"
        "📝 **Notes:**\n"
        "• Typing @username or ID shows multiple options to pick from\n"
        "• Both targeted modes lock by **numeric user ID**\n"
        "• Sender can always reveal their own whisper\n"
        "• Messages over ~150 chars are sent to the reader's DM\n"
        "• Whispers stored in memory; cleared on bot restart",
    )


# ── Inline query handler ──────────────────────────────────────────────────────

@app.on_inline_query()
async def handle_inline(client: Client, query: InlineQuery) -> None:
    raw = query.query.strip()
    user = query.from_user
    sender_name = user.first_name

    # ── Empty query: show usage hints ─────────────────────────────────────────
    if not raw:
        me = await client.get_me()
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    title="🤫 Open whisper — anyone can read",
                    description=f"@{me.username} your secret message",
                    input_message_content=InputTextMessageContent("..."),
                ),
                InlineQueryResultArticle(
                    title="🔒 By @username — one person only",
                    description=f"@{me.username} your message @username",
                    input_message_content=InputTextMessageContent("..."),
                ),
                InlineQueryResultArticle(
                    title="🔒 By user ID — no username needed",
                    description=f"@{me.username} your message 123456789",
                    input_message_content=InputTextMessageContent("..."),
                ),
            ],
            cache_time=0,
            is_personal=True,
        )
        return

    # ── Parse — now returns (message, target_username, target_id) ────────────
    message_text, target_username, target_id_direct = parse_query(raw)
    preview = message_text[:40] + ("..." if len(message_text) > 40 else "")
    results = []

    def _open_result(msg: str, sname: str) -> tuple:
        """Create and store an open whisper; return (whisper_id, result)."""
        wid = str(uuid.uuid4())
        store_whisper(wid, {"text": msg, "sender": sname,
                             "sender_id": user.id,
                             "target_id": None, "target_username": None})
        res = InlineQueryResultArticle(
            title="🤫 Send as open whisper instead",
            description="Anyone in the chat can tap to read",
            input_message_content=InputTextMessageContent(
                f"🤫 **{sname}** sent a whisper...",
                parse_mode=enums.ParseMode.MARKDOWN,
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👆 Tap to reveal", callback_data=f"w:{wid}")
            ]]),
        )
        return wid, res

    # ── Mode A: targeted by @username ─────────────────────────────────────────
    if target_username:
        target_id   = None
        resolve_err = None

        try:
            tu = await client.get_users(target_username)
            target_id = tu.id
            logger.info("Resolved @%s → ID %d", target_username, target_id)
        except (UsernameNotOccupied, UsernameInvalid):
            resolve_err = f"@{target_username} doesn't exist on Telegram."
        except UserDeactivated:
            resolve_err = f"@{target_username}'s account is deactivated."
        except PeerIdInvalid:
            resolve_err = f"Could not find @{target_username}."
        except Exception as e:
            logger.error("Error resolving @%s: %s", target_username, e)
            resolve_err = "Could not resolve that username right now."

        if resolve_err:
            await query.answer(
                results=[InlineQueryResultArticle(
                    title=f"⚠️ {resolve_err}",
                    description="Check the username and try again.",
                    input_message_content=InputTextMessageContent(resolve_err),
                )],
                cache_time=0, is_personal=True,
            )
            return

        t_id = str(uuid.uuid4())
        store_whisper(t_id, {
            "text": message_text, "sender": sender_name,
            "sender_id": user.id,
            "target_id": target_id,
            "target_username": target_username,     # display only
        })
        # Track this recipient for future suggestions
        update_recent(user.id, target_id,
                      tu.first_name or target_username, target_username)
        results.append(InlineQueryResultArticle(
            title=f"🔒 Whisper to @{target_username} only",
            description=f'"{preview}"',
            input_message_content=InputTextMessageContent(
                f"🤫 **{sender_name}** sent a whisper to **@{target_username}**...",
                parse_mode=enums.ParseMode.MARKDOWN,
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"👆 Tap to reveal (only @{target_username})",
                    callback_data=f"w:{t_id}",
                )
            ]]),
        ))
        # Also offer open version
        _, open_res = _open_result(message_text, sender_name)
        open_res.title = "🤫 Send as open whisper instead"
        results.append(open_res)

    # ── Mode B: targeted by numeric user ID ───────────────────────────────────
    elif target_id_direct is not None:
        # Try to fetch display name — not critical if it fails
        target_display = str(target_id_direct)
        try:
            tu = await client.get_users(target_id_direct)
            target_display = tu.first_name or target_display
            logger.info("Resolved ID %d → %s", target_id_direct, target_display)
        except Exception as e:
            logger.warning("Could not fetch name for ID %d: %s", target_id_direct, e)

        t_id = str(uuid.uuid4())
        store_whisper(t_id, {
            "text": message_text, "sender": sender_name,
            "sender_id": user.id,
            "target_id": target_id_direct,
            "target_username": None,                # no username, ID only
        })
        # Track this recipient for future suggestions
        update_recent(user.id, target_id_direct, target_display, None)
        results.append(InlineQueryResultArticle(
            title=f"🔒 Whisper to {target_display} (ID: {target_id_direct}) only",
            description=f'"{preview}"',
            input_message_content=InputTextMessageContent(
                f"🤫 **{sender_name}** sent a whisper to **{target_display}**...",
                parse_mode=enums.ParseMode.MARKDOWN,
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"👆 Tap to reveal (only {target_display})",
                    callback_data=f"w:{t_id}",
                )
            ]]),
        ))
        # Also offer open version
        _, open_res = _open_result(message_text, sender_name)
        open_res.title = "🤫 Send as open whisper instead"
        results.append(open_res)

    # ── Mode C: open whisper + recent recipient suggestions ──────────────────
    else:
        w_id = str(uuid.uuid4())
        store_whisper(w_id, {
            "text": message_text, "sender": sender_name,
            "sender_id": user.id,
            "target_id": None, "target_username": None,
        })
        # Open whisper is always the first option
        results.append(InlineQueryResultArticle(
            title="🤫 Send as open whisper",
            description=f'"{preview}" — anyone can tap to read',
            input_message_content=InputTextMessageContent(
                f"🤫 **{sender_name}** sent a whisper...",
                parse_mode=enums.ParseMode.MARKDOWN,
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👆 Tap to reveal", callback_data=f"w:{w_id}")
            ]]),
        ))

        # ── Append recent recipients as quick-send options ────────────────────
        history = recent_recipients.get(user.id, [])
        for recent in history:
            r_target_id   = recent["target_id"]
            r_name        = recent["display_name"]
            r_username    = recent["username"]
            label         = f"@{r_username}" if r_username else f"ID: {r_target_id}"

            r_wid = str(uuid.uuid4())
            store_whisper(r_wid, {
                "text":            message_text,
                "sender":          sender_name,
                "sender_id":       user.id,
                "target_id":       r_target_id,
                "target_username": r_username,
            })

            bubble = (
                f"🤫 **{sender_name}** sent a whisper to **{r_name}**..."
                if not r_username else
                f"🤫 **{sender_name}** sent a whisper to **@{r_username}**..."
            )

            results.append(InlineQueryResultArticle(
                title=f"🔒 Send to {r_name}",
                description=f"{label} — tap to whisper to them",
                input_message_content=InputTextMessageContent(
                    bubble,
                    parse_mode=enums.ParseMode.MARKDOWN,
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"👆 Tap to reveal (only {r_name})",
                        callback_data=f"w:{r_wid}",
                    )
                ]]),
            ))

    await query.answer(results=results, cache_time=0, is_personal=True)


# ── Callback / button handler ─────────────────────────────────────────────────

@app.on_callback_query()
async def handle_callback(client: Client, query: CallbackQuery) -> None:
    user = query.from_user
    data = query.data

    if not data.startswith("w:"):
        await query.answer("Unknown action.", show_alert=True)
        return

    whisper_id = data[2:]
    whisper = whispers.get(whisper_id)

    if not whisper:
        await query.answer(
            "⚠️ This whisper has expired or no longer exists.",
            show_alert=True,
        )
        return

    sender      = whisper["sender"]
    sender_id   = whisper["sender_id"]
    text        = whisper["text"]
    target_id   = whisper.get("target_id")        # numeric ID — primary check
    target_uname = whisper.get("target_username") # string — fallback only

    # ── Access control ────────────────────────────────────────────────────────
    if target_id is not None or target_uname is not None:
        is_sender       = user.id == sender_id
        is_target_by_id = target_id is not None and user.id == target_id
        # Fallback: if ID lookup failed at send time, try username match
        is_target_by_uname = (
            target_uname is not None and
            target_id is None and
            (user.username or "").lower() == target_uname.lower()
        )

        if not (is_sender or is_target_by_id or is_target_by_uname):
            await query.answer(
                "🔒 This whisper wasn't meant for you!",
                show_alert=True,
            )
            return

    # ── Reveal ────────────────────────────────────────────────────────────────
    header = f"🤫 Whisper from {sender}:\n\n"
    max_body = 200 - len(header)

    if len(text) <= max_body:
        await query.answer(header + text, show_alert=True)
    else:
        # Text too long for popup — show preview, DM the full thing
        preview = text[:max_body - 30] + "..."
        await query.answer(
            header + preview + "\n\n(Full message sent to your DM 📬)",
            show_alert=True,
        )
        try:
            await client.send_message(
                chat_id=user.id,
                text=f"🤫 **Full whisper from {sender}:**\n\n{text}",
            )
        except Exception:
            logger.warning("Could not DM user %d — they may not have started the bot.", user.id)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("PsstBot starting...")
    app.run()
