"""
Rayton Telethon Microservice
============================
Runs as a persistent process alongside Odoo.
Acts as a real Telegram USER (not a bot), so it can change group settings
that the Bot API does not expose (e.g. "Chat history for new members").

Start:
    uvicorn main:app --host 0.0.0.0 --port 8001

Endpoints:
    POST /create_group          — create supergroup, add bot as admin, set history visible
    POST /set_history_visible   — make existing chat history visible
    GET  /health                — liveness check
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    ChannelPrivateError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    InviteToChannelRequest,
    TogglePreHistoryHiddenRequest,
)
from telethon.tl.types import ChatAdminRights

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rayton_tg_service")

# ── Config from environment ───────────────────────────────────────────────────
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_PATH = os.environ.get("TG_SESSION", "rayton_service")
SERVICE_SECRET = os.environ["SERVICE_SECRET"]
BOT_USERNAME = os.environ.get("TG_BOT_USERNAME", "")   # e.g. @rayton_projekt_bot

# ── Global Telethon client ────────────────────────────────────────────────────
_client: TelegramClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    logger.info("Starting Telethon client...")
    _client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await _client.start()
    me = await _client.get_me()
    logger.info("Authorized as: %s (id=%s)", me.first_name, me.id)
    yield
    logger.info("Stopping Telethon client...")
    await _client.disconnect()


app = FastAPI(title="Rayton TG Service", lifespan=lifespan)


# ── Auth guard ────────────────────────────────────────────────────────────────

def _check_secret(x_secret: str):
    if x_secret != SERVICE_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Bot admin rights (full admin except promote_others) ───────────────────────
BOT_ADMIN_RIGHTS = ChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=False,
    delete_messages=True,
    ban_users=False,
    invite_users=True,
    pin_messages=True,
    add_admins=False,
    anonymous=False,
    manage_call=True,
    other=True,
)


# ── Request / Response models ─────────────────────────────────────────────────

class CreateGroupRequest(BaseModel):
    title: str
    bot_username: str = ""        # overrides TG_BOT_USERNAME env if provided
    usernames: list[str] = []     # extra Telegram @usernames to invite
    admin_usernames: list[str] = []  # subset of usernames to promote to admin


class SetHistoryRequest(BaseModel):
    chat_id: str             # Telegram supergroup ID, e.g. "-1001234567890"
    visible: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "authorized": _client is not None and _client.is_connected(),
    }


@app.post("/create_group")
async def create_group(
    req: CreateGroupRequest,
    x_secret: str = Header(...),
):
    """
    Full group creation pipeline:
      1. Create a Telegram supergroup with the given title
      2. Set 'Chat history for new members' = Visible
      3. Add the bot to the group
      4. Promote the bot to admin (change_info, delete, invite, pin, manage_call)

    Returns: { "status": "ok", "chat_id": "-100xxxxxxxxx", "title": "..." }
    The chat_id is in Bot API format (-100 prefix) — save it to rayton.telegram.chat.
    """
    _check_secret(x_secret)

    bot_username = req.bot_username or BOT_USERNAME
    if not bot_username:
        raise HTTPException(
            status_code=400,
            detail="bot_username not provided and TG_BOT_USERNAME is not configured in .env",
        )

    logger.info("Creating supergroup: %r, bot: %s", req.title, bot_username)

    # ── 1. Create supergroup ──────────────────────────────────────────────────
    result = await _client(CreateChannelRequest(
        title=req.title,
        about="",
        megagroup=True,   # True = supergroup, False = broadcast channel
    ))
    channel = result.chats[0]
    logger.info("Supergroup created: id=%s title=%r", channel.id, channel.title)

    # ── 2. Set chat history visible for new members ───────────────────────────
    try:
        await _client(TogglePreHistoryHiddenRequest(
            channel=channel,
            enabled=False,   # False = VISIBLE
        ))
        logger.info("History set to VISIBLE for %s", channel.id)
    except Exception as e:
        logger.warning("Could not set history visible: %s", e)

    # ── 3. Add bot to the group ───────────────────────────────────────────────
    try:
        bot_entity = await _client.get_entity(bot_username)
        await _client(InviteToChannelRequest(channel=channel, users=[bot_entity]))
        logger.info("Bot %s added to group %s", bot_username, channel.id)
    except UserAlreadyParticipantError:
        logger.info("Bot already in group %s", channel.id)
        bot_entity = await _client.get_entity(bot_username)
    except Exception as e:
        logger.warning("Could not add bot to group: %s", e)
        bot_entity = None

    # ── 4. Promote bot to admin ───────────────────────────────────────────────
    if bot_entity:
        try:
            await _client(EditAdminRequest(
                channel=channel,
                user_id=bot_entity,
                admin_rights=BOT_ADMIN_RIGHTS,
                rank="",
            ))
            logger.info("Bot promoted to admin in group %s", channel.id)
        except Exception as e:
            logger.warning("Could not promote bot to admin: %s", e)

    # ── 5. Invite extra users ─────────────────────────────────────────────────
    admin_set = set(req.admin_usernames)
    for uname in req.usernames:
        user_entity = None
        try:
            user_entity = await _client.get_entity(uname)
            await _client(InviteToChannelRequest(channel=channel, users=[user_entity]))
            logger.info("User %s added to group %s", uname, channel.id)
        except UserAlreadyParticipantError:
            logger.info("User %s already in group %s", uname, channel.id)
            user_entity = await _client.get_entity(uname)
        except Exception as e:
            logger.warning("Could not add user %s: %s", uname, e)

        # Promote to admin if requested
        if user_entity and uname in admin_set:
            try:
                await _client(EditAdminRequest(
                    channel=channel,
                    user_id=user_entity,
                    admin_rights=BOT_ADMIN_RIGHTS,
                    rank="",
                ))
                logger.info("User %s promoted to admin in group %s", uname, channel.id)
            except Exception as e:
                logger.warning("Could not promote user %s to admin: %s", uname, e)

    # ── 6. Build Bot API chat_id ──────────────────────────────────────────────
    # Telethon returns bare channel.id (positive int).
    # Bot API uses -100{channel_id} format for supergroups.
    chat_id_bot_api = f"-100{channel.id}"

    logger.info("Done. chat_id=%s title=%r", chat_id_bot_api, channel.title)
    return {
        "status": "ok",
        "chat_id": chat_id_bot_api,
        "title": channel.title,
    }


@app.post("/set_history_visible")
async def set_history_visible(
    req: SetHistoryRequest,
    x_secret: str = Header(...),
):
    """
    Set 'Chat history for new members' to Visible (or Hidden) on an existing group.
    Uses Telegram MTProto via Telethon — not available through Bot API.
    """
    _check_secret(x_secret)

    chat_id = int(req.chat_id)
    logger.info("set_history_visible chat_id=%s visible=%s", chat_id, req.visible)

    try:
        entity = await _client.get_entity(chat_id)
        await _client(TogglePreHistoryHiddenRequest(
            channel=entity,
            enabled=not req.visible,   # enabled=True means HIDDEN
        ))
        logger.info(
            "Chat %s history now: %s", chat_id, "visible" if req.visible else "hidden"
        )
        return {"status": "ok"}

    except ChatAdminRequiredError:
        raise HTTPException(
            status_code=403,
            detail="Service account is not an admin in this group.",
        )
    except ChannelPrivateError:
        raise HTTPException(
            status_code=404,
            detail="Group not found or service account is not a member.",
        )
    except Exception as e:
        logger.exception("Unexpected error for chat %s: %s", chat_id, e)
        raise HTTPException(status_code=500, detail=str(e))
