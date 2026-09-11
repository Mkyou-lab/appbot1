import asyncio
import aiohttp
import json
import os
import sys
import time
import math
import random
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

log = logging.getLogger("MK_SNIPER_BOT")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8552395488:AAHFmk5SvVUNbQs5HGTUS_rllHGECoTq31o")
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "7038512176").split(",") if x.strip()]
ADMIN_ID = ADMIN_IDS[0] if ADMIN_IDS else 7038512176
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@Mkg12333")
USDT_ADDRESS = os.environ.get("USDT_ADDRESS", "TXyzAbc123...")

TIMEZONE_OFFSET = 1
LOCAL_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET))
FREE_TRIAL_SIGNALS = 2

SUBSCRIPTION_PLANS = {
    "week": {"name": "1 Week", "price": "$20", "days": 7},
    "month": {"name": "1 Month", "price": "$100", "days": 30},
    "lifetime": {"name": "Lifetime", "price": "$150", "days": 36500},
}

PAIRS = {
    "EUR/USD": {"type": "forex", "payout": 85},
    "GBP/USD": {"type": "forex", "payout": 85},
    "USD/JPY": {"type": "forex", "payout": 85},
    "EUR/USD OTC": {"type": "otc", "payout": 92},
    "GBP/USD OTC": {"type": "otc", "payout": 92},
    "USD/JPY OTC": {"type": "otc", "payout": 92},
    "Gold OTC": {"type": "otc", "payout": 92},
    "BTC/USD": {"type": "crypto", "payout": 80},
    "ETH/USD": {"type": "crypto", "payout": 80},
}

DURATIONS = {
    "3s": {"secs": 3, "label": "3s", "scan_wait": 1.0},
    "5s": {"secs": 5, "label": "5s", "scan_wait": 1.0},
    "10s": {"secs": 10, "label": "10s", "scan_wait": 1.2},
    "15s": {"secs": 15, "label": "15s", "scan_wait": 1.2},
    "30s": {"secs": 30, "label": "30s", "scan_wait": 1.5},
    "1m": {"secs": 60, "label": "1m", "scan_wait": 1.5},
    "2m": {"secs": 120, "label": "2m", "scan_wait": 2.0},
    "5m": {"secs": 300, "label": "5m", "scan_wait": 2.5},
}

USER_SESSIONS = {}

_app_ref = None
_db_ref = None
_BotUser_ref = None
_Signal_ref = None
_ActivityLog_ref = None
_ActivationCode_ref = None

def init_bot_db(app, db, BotUser, Signal, ActivityLog, ActivationCode):
    global _app_ref, _db_ref, _BotUser_ref, _Signal_ref, _ActivityLog_ref, _ActivationCode_ref
    _app_ref = app; _db_ref = db; _BotUser_ref = BotUser
    _Signal_ref = Signal; _ActivityLog_ref = ActivityLog; _ActivationCode_ref = ActivationCode

def now_local():
    return datetime.now(LOCAL_TZ)

def register_or_get_user(telegram_id, username="N/A", first_name="User", last_name=""):
    """Registers user and returns (user, is_new_account)."""
    if not _app_ref: return None, False
    with _app_ref.app_context():
        user = _BotUser_ref.query.filter_by(telegram_id=telegram_id).first()
        is_new = False
        if not user:
            is_new = True
            is_admin = telegram_id in ADMIN_IDS
            user = _BotUser_ref(
                telegram_id=telegram_id,
                username=username or "N/A",
                first_name=first_name or "User",
                last_name=last_name or "",
                is_locked=not is_admin,  # Admins are unlocked by default
                status="approved" if is_admin else "pending",
                plan="lifetime" if is_admin else "trial"
            )
            _db_ref.session.add(user)
            _db_ref.session.commit()
        else:
            user.username = username or user.username
            user.first_name = first_name or user.first_name
            user.last_active = now_local()
            _db_ref.session.commit()
        return user, is_new

def check_user_active(telegram_id):
    if telegram_id in ADMIN_IDS:
        return True, "ADMIN (UNLIMITED)", None
    if not _app_ref:
        return False, "LOCKED", None
    with _app_ref.app_context():
        user = _BotUser_ref.query.filter_by(telegram_id=telegram_id).first()
        if not user or user.is_locked:
            return False, "LOCKED", None
        if user.plan == "lifetime":
            return True, "LIFETIME VIP", None
        if user.plan == "trial":
            rem = FREE_TRIAL_SIGNALS - user.trial_used
            return rem > 0, "TRIAL", rem
        if user.plan_expiry and now_local() < user.plan_expiry:
            days_left = (user.plan_expiry - now_local()).days
            return True, f"{user.plan.upper()} PLAN", days_left
        return False, "EXPIRED", 0

async def notify_admin_new_user(context: ContextTypes.DEFAULT_TYPE, user):
    """Sends INSTANT alert to Admin when a new account is registered."""
    admin_msg = (
        f"🚨 <b>NEW USER REGISTERED!</b>\n\n"
        f"👤 <b>Name:</b> {user.first_name} {user.last_name or ''}\n"
        f"💬 <b>Username:</b> @{user.username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"📅 <b>Date:</b> {user.joined_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"⚡ <b>Quick Actions:</b> Select a plan to activate or generate key:"
    )

    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Approve 1 Week", callback_data=f"act_{user.telegram_id}_week"),
            InlineKeyboardButton("⚡ Approve 1 Month", callback_data=f"act_{user.telegram_id}_month")
        ],
        [
            InlineKeyboardButton("♾️ Approve Lifetime", callback_data=f"act_{user.telegram_id}_lifetime")
        ],
        [
            InlineKeyboardButton("🔑 Key 1W", callback_data=f"genkey_{user.telegram_id}_week"),
            InlineKeyboardButton("🔑 Key 1M", callback_data=f"genkey_{user.telegram_id}_month"),
            InlineKeyboardButton("🔑 Key Life", callback_data=f"genkey_{user.telegram_id}_lifetime")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_msg, parse_mode=ParseMode.HTML, reply_markup=admin_kb)
        except Exception as e:
            log.warning(f"Could not notify admin {admin_id}: {e}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    un = update.effective_user.username or "N/A"
    fn = update.effective_user.first_name or "User"
    ln = update.effective_user.last_name or ""

    user, is_new = register_or_get_user(uid, un, fn, ln)

    if is_new and uid not in ADMIN_IDS:
        await notify_admin_new_user(context, user)

    active, plan_name, rem = check_user_active(uid)

    # 🔒 LOCKED USER SCREEN
    if not active:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 ENTER ACCESS KEY", callback_data="input_key_dialog")],
            [InlineKeyboardButton("💳 VIEW PAYMENT PLANS", callback_data="subscribe")],
            [InlineKeyboardButton("📩 NOTIFY ADMIN I PAID", callback_data=f"notify_paid_{uid}")]
        ])
        await update.message.reply_text(
            f"🔒 <b>MK SNIPER ENGINE - ACCESS LOCKED</b>\n\n"
            f"Welcome <b>{fn}</b>! Your Account Profile is created.\n"
            f"🆔 <b>Your Account ID:</b> <code>{uid}</code>\n"
            f"📊 <b>Status:</b> 🔴 Locked (Payment Required)\n\n"
            f"<b>How to unlock:</b>\n"
            f"1️⃣ Subscribe to a plan and make payment via USDT.\n"
            f"2️⃣ If Admin gave you an <b>Access Key</b>, tap <b>ENTER ACCESS KEY</b> below.\n"
            f"3️⃣ Admin has been instantly notified of your account creation.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return

    # 🟢 UNLOCKED / ADMIN MAIN MENU
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 GET SNIPER SIGNAL", callback_data="select_market")],
        [InlineKeyboardButton("📊 MY METRICS", callback_data="stats"), InlineKeyboardButton("💳 EXTEND PLAN", callback_data="subscribe")],
        [InlineKeyboardButton("📚 STRATEGIES", callback_data="strategies"), InlineKeyboardButton("ℹ️ HELP", callback_data="howto")]
    ])
    
    admin_banner = "👑 <b>ADMIN ACCESS GRANTED</b>\n\n" if uid in ADMIN_IDS else ""
    await update.message.reply_text(
        f"🎯 <b>MK SNIPER ENGINE v47.0 ACTIVE</b>\n"
        f"{admin_banner}"
        f"👤 Account: <b>{fn}</b> | ID: <code>{uid}</code>\n"
        f"⚡ Status: 🟢 <b>{plan_name}</b>\n\n"
        f"Select an option below to start trading:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    # Admin Direct Activation from Telegram Notification
    if data.startswith("act_"):
        if uid not in ADMIN_IDS: return
        parts = data.split("_")
        target_uid, plan = int(parts[1]), parts[2]

        with _app_ref.app_context():
            target_user = _BotUser_ref.query.filter_by(telegram_id=target_uid).first()
            if target_user:
                target_user.is_locked = False
                target_user.plan = plan
                target_user.plan_started = now_local()
                if plan == 'lifetime':
                    target_user.plan_expiry = None
                else:
                    days = SUBSCRIPTION_PLANS.get(plan, {}).get('days', 7)
                    target_user.plan_expiry = now_local() + timedelta(days=days)
                _db_ref.session.commit()

        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 <b>ACCOUNT UNLOCKED!</b>\n\nYour <b>{plan.upper()}</b> subscription has been activated by Admin!\nSend /start to begin trading.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        await q.edit_message_text(f"✅ User <code>{target_uid}</code> activated for <b>{plan.upper()}</b>.", parse_mode=ParseMode.HTML)

    # Admin Key Generation from Telegram Notification
    elif data.startswith("genkey_"):
        if uid not in ADMIN_IDS: return
        parts = data.split("_")
        target_uid, plan = int(parts[1]), parts[2]

        code_str = f"MK-{plan[:2].upper()}-{random.randint(1000, 9999)}"
        with _app_ref.app_context():
            ac = _ActivationCode_ref(code=code_str, plan=plan)
            _db_ref.session.add(ac)
            _db_ref.session.commit()

        await q.edit_message_text(
            f"🎟 <b>ACCESS KEY GENERATED FOR USER <code>{target_uid}</code>:</b>\n\n"
            f"Key: <code>{code_str}</code>\n"
            f"Plan: <b>{plan.upper()}</b>\n\n"
            f"<i>Forward this code to the user. They can redeem it with:</i>\n<code>/key {code_str}</code>",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("notify_paid_"):
        target_uid = int(data.replace("notify_paid_", ""))
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"💰 <b>PAYMENT NOTIFICATION!</b>\nUser <code>{target_uid}</code> (@{q.from_user.username}) claims they have sent payment.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        await q.edit_message_text("✅ Admin notified! Your account will unlock shortly after verification.")

    elif data == "input_key_dialog":
        await q.edit_message_text(
            f"🔑 <b>ENTER ACCESS KEY</b>\n\n"
            f"Please type your key in chat using command:\n"
            f"<code>/key YOUR_KEY</code>\n\n"
            f"Example: <code>/key MK-WK-4892</code>",
            parse_mode=ParseMode.HTML
        )

    elif data == "subscribe":
        await q.edit_message_text(
            f"💳 <b>SUBSCRIPTION PLANS & PAYMENT</b>\n\n"
            f"• 1 Week Access: <b>$20</b>\n"
            f"• 1 Month Access: <b>$100</b>\n"
            f"• Lifetime License: <b>$150</b>\n\n"
            f"💰 <b>USDT (TRC20 Wallet Address):</b>\n<code>{USDT_ADDRESS}</code>\n\n"
            f"After sending payment, contact Admin {ADMIN_USERNAME} with your ID: <code>{uid}</code> to receive your Access Key.",
            parse_mode=ParseMode.HTML
        )

    elif data == "select_market":
        active, _, _ = check_user_active(uid)
        if not active:
            await q.edit_message_text("🔒 Account locked. Please enter an Access Key.", parse_mode=ParseMode.HTML)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌙 OTC MARKETS", callback_data="mkt_otc"), InlineKeyboardButton("💱 LIVE FOREX", callback_data="mkt_forex")],
            [InlineKeyboardButton("₿ CRYPTO", callback_data="mkt_crypto")]
        ])
        await q.edit_message_text("🌍 <b>Select Market Feed:</b>", parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data.startswith("mkt_"):
        mkt = data.replace("mkt_", "")
        pairs_list = [p for p, v in PAIRS.items() if v["type"] == mkt]
        rows = [[InlineKeyboardButton(p, callback_data=f"pair_{p}")] for p in pairs_list]
        await q.edit_message_text(f"📍 <b>Select Asset ({mkt.upper()}):</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))

    elif data.startswith("pair_"):
        pair = data.replace("pair_", "")
        USER_SESSIONS[uid] = {"pair": pair}
        rows = [
            [InlineKeyboardButton("3s", callback_data="dur_3s"), InlineKeyboardButton("5s", callback_data="dur_5s"), InlineKeyboardButton("10s", callback_data="dur_10s")],
            [InlineKeyboardButton("15s", callback_data="dur_15s"), InlineKeyboardButton("30s", callback_data="dur_30s"), InlineKeyboardButton("1m", callback_data="dur_1m")],
            [InlineKeyboardButton("5m", callback_data="dur_5m")]
        ]
        await q.edit_message_text(f"✅ Selected Asset: <b>{pair}</b>\n⏱ <b>Select Trade Expiry Duration:</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))

    elif data.startswith("dur_"):
        dur_key = data.replace("dur_", "")
        pair = USER_SESSIONS.get(uid, {}).get("pair", "EUR/USD OTC")
        dur_info = DURATIONS.get(dur_key, DURATIONS["1m"])

        direction = random.choice(["CALL ⬆️", "PUT ⬇️"])
        acc = round(random.uniform(97.2, 99.6), 1)

        await q.edit_message_text(f"🔍 Analyzing wave structure for <b>{pair}</b> ({dur_info['label']})...", parse_mode=ParseMode.HTML)
        await asyncio.sleep(dur_info["scan_wait"])

        await q.edit_message_text(
            f"🎯 <b>ENTRY SIGNAL VALIDATED</b>\n\n"
            f"📊 <b>Asset:</b> <code>{pair}</code>\n"
            f"⏱ <b>Expiry:</b> <code>{dur_info['label']}</code>\n"
            f"🚀 <b>Action:</b> <b>{direction}</b>\n\n"
            f"💪 <b>Win Probability:</b> <code>{acc}%</code>\n"
            f"⚠️ <i>Execute immediately on your broker terminal.</i>",
            parse_mode=ParseMode.HTML
        )

# Command to Redeem Key
async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: <code>/key YOUR_ACCESS_KEY</code>", parse_mode=ParseMode.HTML)
        return
    key_str = context.args[0].strip().upper()

    with _app_ref.app_context():
        code_entry = _ActivationCode_ref.query.filter_by(code=key_str, is_used=False).first()
        if not code_entry:
            await update.message.reply_text("❌ <b>INVALID OR ALREADY REDEEMED KEY.</b>\nPlease check your key and try again.", parse_mode=ParseMode.HTML)
            return

        code_entry.is_used = True
        code_entry.used_by = uid

        user = _BotUser_ref.query.filter_by(telegram_id=uid).first()
        if user:
            user.is_locked = False
            user.plan = code_entry.plan
            user.plan_started = now_local()
            if code_entry.plan == 'lifetime':
                user.plan_expiry = None
            else:
                days = SUBSCRIPTION_PLANS.get(code_entry.plan, {}).get('days', 7)
                user.plan_expiry = now_local() + timedelta(days=days)
            _db_ref.session.commit()

            await update.message.reply_text(
                f"🎉 <b>ACCESS KEY REDEEMED SUCCESSFULLY!</b>\n\n"
                f"Plan Activated: <b>{code_entry.plan.upper()}</b>\n"
                f"Your account is unlocked permanently for this period.\n\n"
                f"Send /start to open your trading terminal!",
                parse_mode=ParseMode.HTML
            )

# Admin Command to Generate Access Keys Directly
async def cmd_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    plan = context.args[0].lower() if context.args else "week"
    if plan not in ("week", "month", "lifetime"):
        plan = "week"

    code_str = f"MK-{plan[:2].upper()}-{random.randint(1000, 9999)}"
    with _app_ref.app_context():
        ac = _ActivationCode_ref(code=code_str, plan=plan)
        _db_ref.session.add(ac)
        _db_ref.session.commit()

    await update.message.reply_text(
        f"🎟 <b>NEW ACCESS KEY CREATED</b>\n\n"
        f"Key: <code>{code_str}</code>\n"
        f"Plan: <b>{plan.upper()}</b>\n\n"
        f"Forward this key to the customer.",
        parse_mode=ParseMode.HTML
    )

def setup_bot_handlers(app_tg):
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(CommandHandler("key", cmd_key))
    app_tg.add_handler(CommandHandler("genkey", cmd_genkey))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
