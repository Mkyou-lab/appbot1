import os
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from models import db, AdminUser, BotUser, Signal, VideoContent, Strategy, BroadcastMessage, ActivityLog, now_local

dash = Blueprint('dash', __name__)

SUBSCRIPTION_PLANS = {
    "week": {"name": "1 Week", "price": "$20", "days": 7},
    "month": {"name": "1 Month", "price": "$100", "days": 30},
    "lifetime": {"name": "Lifetime", "price": "$150", "days": 36500},
}

@dash.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dash.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        admin = AdminUser.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            admin.last_login = now_local()
            db.session.commit()
            login_user(admin, remember=True)
            return redirect(url_for('dash.dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@dash.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('dash.login'))

@dash.route('/')
@dash.route('/dashboard')
@login_required
def dashboard():
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    return render_template('dashboard.html',
                           total_users=BotUser.query.count(),
                           active_subs=BotUser.query.filter(BotUser.plan != 'trial').count(),
                           locked_users=BotUser.query.filter_by(is_locked=True).count(),
                           total_signals=Signal.query.count(),
                           wins=Signal.query.filter_by(result='win').count(),
                           losses=Signal.query.filter_by(result='loss').count(),
                           win_rate=0,
                           new_today=BotUser.query.filter(BotUser.joined_at >= today).count(),
                           signals_today=Signal.query.filter(Signal.created_at >= today).count(),
                           recent_users=BotUser.query.order_by(BotUser.joined_at.desc()).limit(5).all(),
                           recent_signals=Signal.query.order_by(Signal.created_at.desc()).limit(10).all(),
                           recent_activity=ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all(),
                           revenue=0, chart_labels=[], chart_wins=[], chart_losses=[], growth_labels=[], growth_data=[])

@dash.route('/users')
@login_required
def users():
    users_page = BotUser.query.order_by(BotUser.joined_at.desc()).paginate(page=1, per_page=50, error_out=False)
    return render_template('users.html', users=users_page, search="", filter_plan="", filter_status="")

@dash.route('/content')
@login_required
def content():
    return render_template('content.html', 
                           videos=VideoContent.query.order_by(VideoContent.created_at.desc()).all(), 
                           strategies=Strategy.query.order_by(Strategy.created_at.desc()).all())

@dash.route('/subscriptions')
@login_required
def subscriptions():
    return render_template('subscriptions.html', 
                           subs=BotUser.query.filter(BotUser.plan != 'trial').all(),
                           trial_users=BotUser.query.filter_by(plan='trial').count(),
                           week_users=BotUser.query.filter_by(plan='week').count(),
                           month_users=BotUser.query.filter_by(plan='month').count(),
                           lifetime_users=BotUser.query.filter_by(plan='lifetime').count())

@dash.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html', signals=Signal.query.order_by(Signal.created_at.desc()).limit(100).all(), pair_stats={})

@dash.route('/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast():
    if request.method == 'POST':
        msg = request.form.get('message', '')
        if msg:
            db.session.add(BroadcastMessage(message=msg))
            db.session.commit()
            flash('Broadcast queued!', 'info')
        return redirect(url_for('dash.broadcast'))
    return render_template('broadcast.html', broadcasts=BroadcastMessage.query.order_by(BroadcastMessage.sent_at.desc()).limit(20).all())

@dash.route('/api/online-users')
@login_required
def api_online_users():
    threshold = now_local() - timedelta(minutes=5)
    return jsonify({'online': BotUser.query.filter(BotUser.last_active >= threshold).count()})
