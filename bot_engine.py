import asyncio, os, time, math, random, logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

log = logging.getLogger("MK_BOT")

_db_ref = None
_BotUser_ref = None
_Signal_ref = None
_ActivityLog_ref = None
_app_ref = None

def init_bot_db(app, db, BotUser, Signal, ActivityLog):
    global _db_ref, _BotUser_ref, _Signal_ref, _ActivityLog_ref, _app_ref
    _app_ref = app; _db_ref = db; _BotUser_ref = BotUser; _Signal_ref = Signal; _ActivityLog_ref = ActivityLog

def get_or_create_user(telegram_id, username=None, first_name=None):
    if not _app_ref: return None
    with _app_ref.app_context():
        user = _BotUser_ref.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            user = _BotUser_ref(telegram_id=telegram_id, username=username, first_name=first_name, is_locked=True)
            _db_ref.session.add(user)
            _db_ref.session.commit()
        return user

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    un = update.effective_user.username or "N/A"
    fn = update.effective_user.first_name or "User"
    user = get_or_create_user(uid, un, fn)
    
    if user and user.is_locked:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 SUBSCRIBE", callback_data="subscribe")]])
        await update.message.reply_text("🔒 *ACCOUNT LOCKED*\n\nSubscribe to unlock.", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return
        
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎯 GET SIGNAL", callback_data="signal")]])
    await update.message.reply_text("🎯 *MK SNIPER ENGINE ONLINE*\nTap below to start.", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "subscribe":
        await q.edit_message_text("💳 *PLANS:*\n• 1 Week: $20\n• 1 Month: $100\n• Lifetime: $150\n\nContact Admin to pay.", parse_mode=ParseMode.MARKDOWN)
    elif q.data == "signal":
        await q.edit_message_text("⚡ *SIGNAL VALIDATED*\n\nPair: EUR/USD OTC\nAction: CALL ⬆️", parse_mode=ParseMode.MARKDOWN)

def setup_bot_handlers(app_tg):
    app_tg.add_handler(CommandHandler("start", start_cmd))
    app_tg.add_handler(CallbackQueryHandler(btn_handler))
