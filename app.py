import os
import sys
import asyncio
import threading
import logging

from flask import Flask
from flask_login import LoginManager

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger("MK_APP")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mk-sniper-ultra-secret-key-2024')

# Safe DB URL handling (prevents crashes from empty variables)
raw_db = os.environ.get('DATABASE_URL', '').strip()
if not raw_db or raw_db in ('""', "''", "None"):
    db_url = 'sqlite:///mk_sniper.db'
elif raw_db.startswith('postgres://'):
    db_url = raw_db.replace('postgres://', 'postgresql://', 1)
else:
    db_url = raw_db

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

from models import db, AdminUser, BotUser, Signal, VideoContent, Strategy, BroadcastMessage, ActivityLog
from dashboard import dash

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'dash.login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return AdminUser.query.get(int(user_id))
    except Exception:
        return None

# Register Dashboard Blueprint
app.register_blueprint(dash)

@app.route('/health')
def health():
    return {'status': 'ok', 'engine': 'MK SNIPER v47.0'}, 200

# Create tables and default admin safely
with app.app_context():
    try:
        db.create_all()
        admin = AdminUser.query.filter_by(username='admin').first()
        if not admin:
            admin_user = os.environ.get('DASHBOARD_USER', 'admin')
            admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
            admin = AdminUser(username=admin_user)
            admin.set_password(admin_pass)
            db.session.add(admin)
            db.session.commit()
            log.info("Default admin user created successfully.")
    except Exception as e:
        log.error(f"Database initialization warning: {e}")

os.makedirs('static/uploads', exist_ok=True)

# ==================== ISOLATED TELEGRAM BOT THREAD ====================
def run_telegram_bot():
    """Runs Telegram Bot safely inside a daemon thread."""
    log.info("Starting Telegram Bot Thread...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        from telegram.ext import Application as TGApp
        from bot_engine import setup_bot_handlers, init_bot_db, BOT_TOKEN

        if not BOT_TOKEN or ":" not in BOT_TOKEN:
            log.error("❌ Invalid or missing BOT_TOKEN! Bot thread stopped, but Web Dashboard remains active.")
            return

        init_bot_db(app, db, BotUser, Signal, ActivityLog)

        tg_app = TGApp.builder().token(BOT_TOKEN).build()
        setup_bot_handlers(tg_app)

        async def run():
            async with tg_app:
                await tg_app.start()
                await tg_app.updater.start_polling(
                    allowed_updates=['message', 'callback_query'],
                    drop_pending_updates=True
                )
                log.info("🤖 Telegram Bot is active and listening for signals!")
                await asyncio.Event().wait()

        loop.run_until_complete(run())
    except Exception as e:
        log.error(f"⚠️ Telegram Bot thread warning: {e}")

# Launch Bot Thread safely
try:
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    log.info("🚀 Bot thread launched.")
except Exception as e:
    log.error(f"Could not launch bot thread: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
