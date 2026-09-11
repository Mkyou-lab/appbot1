import os
import sys
import asyncio
import threading
import logging

from flask import Flask
from flask_login import LoginManager

from models import db, AdminUser, BotUser, Signal, VideoContent, Strategy, BroadcastMessage, ActivityLog
from dashboard import dash

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("MK_APP")

# ==================== FLASK APP ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mk-sniper-ultra-secret-key-2024')

# Safely parse and sanitize DATABASE_URL
raw_db_url = os.environ.get('DATABASE_URL', '').strip()

if not raw_db_url:
    # Default to local SQLite if no valid database URL is provided
    db_url = 'sqlite:///mk_sniper.db'
elif raw_db_url.startswith('postgres://'):
    db_url = raw_db_url.replace('postgres://', 'postgresql://', 1)
else:
    db_url = raw_db_url

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'dash.login'

@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

# Register Dashboard Blueprint
app.register_blueprint(dash)

@app.route('/health')
def health():
    return {'status': 'ok', 'engine': 'MK SNIPER v47.0'}, 200

# Create tables and default admin
with app.app_context():
    db.create_all()
    admin = AdminUser.query.filter_by(username='admin').first()
    if not admin:
        admin = AdminUser(username=os.environ.get('DASHBOARD_USER', 'admin'))
        admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
        db.session.add(admin)
        db.session.commit()
        log.info("Default admin user created")

os.makedirs('static/uploads', exist_ok=True)

# ==================== TELEGRAM BOT THREAD ====================
def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        from telegram.ext import Application as TGApp
        from bot_engine import (setup_bot_handlers, init_bot_db, BOT_TOKEN)

        if ":" not in BOT_TOKEN:
            log.error("Invalid BOT_TOKEN!")
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
                log.info("🤖 Telegram bot started successfully!")
                try:
                    await asyncio.Event().wait()
                finally:
                    await tg_app.updater.stop()
                    await tg_app.stop()

        loop.run_until_complete(run())

    except Exception as e:
        log.error(f"Telegram bot error: {e}")
    finally:
        loop.close()

bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()
log.info("🚀 Bot thread started")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
