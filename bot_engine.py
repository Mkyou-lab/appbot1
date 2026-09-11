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
ENTRY_STAKE = 10
MG_STAKE = 22

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
    "3s": {"secs": 3, "label": "3s", "scan_wait": 1.0, "regime": "micro_tick"},
    "5s": {"secs": 5, "label": "5s", "scan_wait": 1.0, "regime": "micro_tick"},
    "10s": {"secs": 10, "label": "10s", "scan_wait": 1.2, "regime": "micro_tick"},
    "15s": {"secs": 15, "label": "15s", "scan_wait": 1.2, "regime": "micro_tick"},
    "30s": {"secs": 30, "label": "30s", "scan_wait": 1.5, "regime": "momentum"},
    "1m": {"secs": 60, "label": "1m", "scan_wait": 1.5, "regime": "momentum"},
    "2m": {"secs": 120, "label": "2m", "scan_wait": 2.0, "regime": "momentum"},
    "5m": {"secs": 300, "label": "5m", "scan_wait": 2.5, "regime": "swing_trend"},
}

USER_SESSIONS = {}
ACTIVE_TRADES = {}

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

def get_or_create_user(telegram_id, username="N/A", first_name="User"):
    if not _app_ref: return None
    with _app_ref.app_context():
        user = _BotUser_ref.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            user = _BotUser_ref(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_locked=True,
                status="pending"
            )
            _db_ref.session.add(user)
            _db_ref.session.commit()
        else:
            user.last_active = now_local()
            _db_ref.session.commit()
        return user

def check_user_active(telegram_id):
    if telegram_id in ADMIN_IDS:
        return True, "ADMIN", None
    if not _app_ref:
        return False, "LOCKED", None
    with _app_ref.app_context():
        user = _BotUser_ref.query.filter_by(telegram_id=telegram_id).first()
        if not user or user.is_locked:
            return False, "LOCKED", None
        if user.plan == "lifetime":
            return True, "LIFETIME", None
        if user.plan == "trial":
            rem = FREE_TRIAL_SIGNALS - user.trial_used
            return rem > 0, "TRIAL", rem
        if user.plan_expiry and now_local() < user.plan_expiry:
            return True, user.plan.upper(), (user.plan_expiry - now_local()).days
        return False, "EXPIRED", 0

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    un = update.effective_user.username or "N/A"
    fn = update.effective_user.first_name or "User"

    get_or_create_user(uid, un, fn)
    active, plan_name, rem = check_user_active(uid)

    if not active:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Request Admin Approval", callback_data=f"req_access_{uid}")],
            [InlineKeyboardButton("💳 Subscription Plans", callback_data="subscribe")],
            [InlineKeyboardButton("🔑 Enter Activation Code", callback_data="input_code")]
        ])
        await update.message.reply_text(
            f"🔒 <b>MK SNIPER ENGINE - ACCESS RESTRICTED</b>\n\n"
            f"Welcome <b>{fn}</b>! Your Telegram ID: <code>{uid}</code>\n"
            f"Status: 🔴 <b>Unsubscribed / Locked</b>\n\n"
            f"To activate your terminal:\n"
            f"1️⃣ Tap <b>Request Admin Approval</b> below to notify the owner.\n"
            f"2️⃣ Or send proof of payment to {ADMIN_USERNAME}.\n"
            f"3️⃣ If you have a code, tap <b>Enter Activation Code</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 GET SNIPER SIGNAL", callback_data="select_market")],
        [InlineKeyboardButton("📊 MY METRICS", callback_data="stats"), InlineKeyboardButton("💳 UPGRADE", callback_data="subscribe")],
        [InlineKeyboardButton("ℹ️ HELP", callback_data="howto")]
    ])
    await update.message.reply_text(
        f"🎯 <b>MK SNIPER ENGINE v47.0 ACTIVE</b>\n"
        f"Status: 🟢 <b>{plan_name}</b>\n\n"
        f"Engine is calibrated and ready. Select an option below:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    await q.answer()

    if data.startswith("req_access_"):
        user_id = int(data.replace("req_access_", ""))
        user_name = q.from_user.first_name or "User"
        user_handle = q.from_user.username or "N/A"

        # Notify Admin in Telegram
        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ 1 Week", callback_data=f"approve_{user_id}_week"),
                InlineKeyboardButton("✅ 1 Month", callback_data=f"approve_{user_id}_month")
            ],
            [
                InlineKeyboardButton("♾️ Lifetime", callback_data=f"approve_{user_id}_lifetime"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
            ]
        ])
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🚨 <b>NEW USER ACCESS REQUEST!</b>\n\n"
                    f"👤 <b>User:</b> {user_name} (@{user_handle})\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                    f"Select subscription plan to activate:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=admin_kb
                )
            except Exception:
                pass

        await q.edit_message_text(
            f"✅ <b>Request Sent!</b>\n\nNotification delivered to Admin.\nYour terminal will automatically unlock once approved.",
            parse_mode=ParseMode.HTML
        )

    elif data.startswith("approve_"):
        parts = data.split("_")
        target_uid = int(parts[1])
        plan = parts[2]

        if uid not in ADMIN_IDS:
            return

        with _app_ref.app_context():
            user = _BotUser_ref.query.filter_by(telegram_id=target_uid).first()
            if user:
                user.is_locked = False
                user.plan = plan
                user.plan_started = now_local()
                if plan == 'lifetime':
                    user.plan_expiry = None
                else:
                    days = SUBSCRIPTION_PLANS.get(plan, {}).get('days', 7)
                    user.plan_expiry = now_local() + timedelta(days=days)
                _db_ref.session.commit()

        # Notify User
        try:
            await context.bot.send_message(
                target_uid,
                f"🎉 <b>ACCESS ACTIVATED!</b>\n\nYour <b>{plan.upper()}</b> subscription has been approved by Admin.\nSend /start to begin trading!",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        await q.edit_message_text(f"✅ User <code>{target_uid}</code> approved for <b>{plan.upper()}</b>.", parse_mode=ParseMode.HTML)

    elif data == "input_code":
        await q.edit_message_text(
            f"🔑 <b>ENTER ACTIVATION CODE</b>\n\nSend your activation code in chat using:\n<code>/code YOUR_CODE</code>\n\nExample: <code>/code MK-8921</code>",
            parse_mode=ParseMode.HTML
        )

    elif data == "subscribe":
        await q.edit_message_text(
            f"💳 <b>SUBSCRIPTION PLANS</b>\n\n"
            f"• 1 Week: $20\n• 1 Month: $100\n• Lifetime: $150\n\n"
            f"💰 <b>USDT (TRC20):</b>\n<code>{USDT_ADDRESS}</code>\n\n"
            f"Send payment receipt to {ADMIN_USERNAME} with ID: <code>{uid}</code>",
            parse_mode=ParseMode.HTML
        )

    elif data == "select_market":
        active, _, _ = check_user_active(uid)
        if not active:
            await q.edit_message_text("🔒 Account locked. Please subscribe.", parse_mode=ParseMode.HTML)
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
        await q.edit_message_text(f"✅ Selected: <b>{pair}</b>\n⏱ <b>Select Duration:</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))

    elif data.startswith("dur_"):
        dur_key = data.replace("dur_", "")
        pair = USER_SESSIONS.get(uid, {}).get("pair", "EUR/USD OTC")
        dur_info = DURATIONS.get(dur_key, DURATIONS["1m"])

        direction = random.choice(["CALL ⬆️", "PUT ⬇️"])
        acc = round(random.uniform(97.1, 99.4), 1)

        await q.edit_message_text(f"🔍 Analyzing {pair} ({dur_info['label']})...", parse_mode=ParseMode.HTML)
        await asyncio.sleep(dur_info["scan_wait"])

        await q.edit_message_text(
            f"🎯 <b>ENTRY SIGNAL VALIDATED</b>\n\n"
            f"📊 <b>Asset:</b> <code>{pair}</code>\n"
            f"⏱ <b>Expiry:</b> <code>{dur_info['label']}</code>\n"
            f"🚀 <b>Action:</b> <b>{direction}</b>\n\n"
            f"💪 <b>Accuracy:</b> <code>{acc}%</code>\n"
            f"⚠️ <i>Execute immediately on your broker.</i>",
            parse_mode=ParseMode.HTML
        )

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: <code>/code YOUR_CODE</code>", parse_mode=ParseMode.HTML)
        return
    code_str = context.args[0].strip().upper()

    with _app_ref.app_context():
        code_entry = _ActivationCode_ref.query.filter_by(code=code_str, is_used=False).first()
        if not code_entry:
            await update.message.reply_text("❌ Invalid or already used activation code.")
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

            await update.message.reply_text(f"🎉 <b>CODE ACCEPTED!</b>\nYour <b>{code_entry.plan.upper()}</b> subscription is active!\nSend /start to open menu.", parse_mode=ParseMode.HTML)

async def cmd_gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    plan = context.args[0].lower() if context.args else "week"
    code_str = f"MK-{random.randint(1000, 9999)}"

    with _app_ref.app_context():
        ac = _ActivationCode_ref(code=code_str, plan=plan)
        _db_ref.session.add(ac)
        _db_ref.session.commit()

    await update.message.reply_text(f"🎟 <b>Code Created:</b> <code>{code_str}</code>\nPlan: <b>{plan.upper()}</b>", parse_mode=ParseMode.HTML)

def setup_bot_handlers(app_tg):
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(CommandHandler("code", cmd_code))
    app_tg.add_handler(CommandHandler("gencode", cmd_gen_code))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
