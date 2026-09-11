import os
import sys
import asyncio
import threading
import logging

from flask import Flask
from flask_login import LoginManager
from sqlalchemy.engine import make_url

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger("MK_APP")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mk-sniper-ultra-secret-key-2024')

# ==================== FAILSAFE DATABASE URI PARSER ====================
def get_safe_db_uri():
    raw_url = os.environ.get('DATABASE_URL', '').strip()
    if raw_url.startswith('postgres://'):
        raw_url = raw_url.replace('postgres://', 'postgresql://', 1)
    
    if raw_url:
        try:
            make_url(raw_url)
            return raw_url
        except Exception as e:
            log.warning(f"⚠️ DATABASE_URL invalid ({e}). Using SQLite.")

    base_dir = os.path.abspath(os.path.dirname(__file__))
    return f"sqlite:///{os.path.join(base_dir, 'mk_sniper.db')}"

app.config['SQLALCHEMY_DATABASE_URI'] = get_safe_db_uri()
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

app.register_blueprint(dash)

@app.route('/health')
def health():
    return {'status': 'ok', 'engine': 'MK SNIPER v47.0'}, 200

# ==================== GUARANTEED ADMIN LOGIN SYNC ====================
with app.app_context():
    try:
        db.create_all()
        target_user = os.environ.get('DASHBOARD_USER', 'admin').strip()
        target_pass = os.environ.get('ADMIN_PASSWORD', 'admin123').strip()

        admin = AdminUser.query.filter_by(username=target_user).first()
        if not admin:
            admin = AdminUser(username=target_user)
            db.session.add(admin)

        admin.set_password(target_pass)
        db.session.commit()
        log.info(f"✅ Admin credentials synced! Username: '{target_user}'")
    except Exception as e:
        log.error(f"Error syncing admin account: {e}")

os.makedirs('static/uploads', exist_ok=True)

# ==================== TELEGRAM BOT THREAD ====================
def run_telegram_bot():
    log.info("Starting Telegram Bot Thread...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        from telegram.ext import Application as TGApp
        from bot_engine import setup_bot_handlers, init_bot_db, BOT_TOKEN

        if not BOT_TOKEN or ":" not in BOT_TOKEN:
            log.warning("❌ Missing or invalid BOT_TOKEN! Dashboard active, bot thread idle.")
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
                log.info("🤖 Telegram Bot active!")
                await asyncio.Event().wait()

        loop.run_until_complete(run())
    except Exception as e:
        log.error(f"⚠️ Telegram Bot thread warning: {e}")

try:
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    log.info("🚀 Bot thread launched.")
except Exception as e:
    log.error(f"Could not launch bot thread: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
