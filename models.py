import os
import re
from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

TIMEZONE_OFFSET = 1
LOCAL_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET))

def now_local():
    return datetime.now(LOCAL_TZ)

class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_local)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BotUser(db.Model):
    __tablename__ = 'bot_users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(120))
    first_name = db.Column(db.String(120))
    last_name = db.Column(db.String(120))
    status = db.Column(db.String(20), default='pending')
    plan = db.Column(db.String(20), default='trial')
    trial_used = db.Column(db.Integer, default=0)
    plan_expiry = db.Column(db.DateTime, nullable=True)
    plan_started = db.Column(db.DateTime, nullable=True)
    is_locked = db.Column(db.Boolean, default=True)
    total_wins = db.Column(db.Integer, default=0)
    total_losses = db.Column(db.Integer, default=0)
    total_pnl = db.Column(db.Float, default=0.0)
    joined_at = db.Column(db.DateTime, default=now_local)
    last_active = db.Column(db.DateTime, default=now_local)
    last_signal_at = db.Column(db.DateTime, nullable=True)

    def has_active_subscription(self):
        if not self.is_locked and self.plan == 'lifetime':
            return True
        if not self.is_locked and self.plan == 'trial':
            return self.trial_used < 2
        if not self.is_locked and self.plan_expiry:
            return now_local() < self.plan_expiry
        return False

    @property
    def win_rate(self):
        total = self.total_wins + self.total_losses
        return round(self.total_wins / total * 100, 1) if total > 0 else 0.0

    @property
    def days_remaining(self):
        if self.plan == 'lifetime': return 99999
        if self.plan == 'trial': return max(0, 2 - self.trial_used)
        if self.plan_expiry: return max(0, (self.plan_expiry - now_local()).days)
        return 0

class ActivationCode(db.Model):
    __tablename__ = 'activation_codes'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    plan = db.Column(db.String(20), nullable=False) # week, month, lifetime
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, default=now_local)

class Signal(db.Model):
    __tablename__ = 'signals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False)
    pair = db.Column(db.String(50), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    duration = db.Column(db.String(10), nullable=False)
    accuracy = db.Column(db.Float, default=0.0)
    result = db.Column(db.String(10), nullable=True)
    pnl = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=now_local)

class VideoContent(db.Model):
    __tablename__ = 'video_content'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    video_url = db.Column(db.String(500))
    thumbnail_url = db.Column(db.String(500))
    category = db.Column(db.String(50), default='strategy')
    is_premium = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now_local)
    is_active = db.Column(db.Boolean, default=True)

    @property
    def embed_url(self):
        """Converts standard YouTube / Vimeo URLs to playable Embed URLs."""
        url = self.video_url or ""
        if "youtube.com/watch?v=" in url:
            vid_id = url.split("watch?v=")[1].split("&")[0]
            return f"https://www.youtube.com/embed/{vid_id}?autoplay=1"
        elif "youtu.be/" in url:
            vid_id = url.split("youtu.be/")[1].split("?")[0]
            return f"https://www.youtube.com/embed/{vid_id}?autoplay=1"
        elif "vimeo.com/" in url:
            vid_id = url.split("vimeo.com/")[1]
            return f"https://player.vimeo.com/video/{vid_id}?autoplay=1"
        return url

class Strategy(db.Model):
    __tablename__ = 'strategies'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='beginner')
    difficulty = db.Column(db.String(20), default='easy')
    is_premium = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now_local)
    is_active = db.Column(db.Boolean, default=True)

class BroadcastMessage(db.Model):
    __tablename__ = 'broadcasts'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    sent_to = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    sent_at = db.Column(db.DateTime, default=now_local)

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger)
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=now_local)
