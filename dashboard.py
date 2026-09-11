import os
import random
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from models import (db, AdminUser, BotUser, Signal, VideoContent, Strategy, 
                    BroadcastMessage, ActivityLog, ActivationCode, now_local)

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
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
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
    total_users = BotUser.query.count()
    active_subs = BotUser.query.filter(BotUser.plan != 'trial').count()
    locked_users = BotUser.query.filter_by(is_locked=True).count()
    total_signals = Signal.query.count()
    wins = Signal.query.filter_by(result='win').count()
    losses = Signal.query.filter_by(result='loss').count()
    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0

    new_today = BotUser.query.filter(BotUser.joined_at >= today).count()
    signals_today = Signal.query.filter(Signal.created_at >= today).count()

    recent_users = BotUser.query.order_by(BotUser.joined_at.desc()).limit(5).all()
    recent_signals = Signal.query.order_by(Signal.created_at.desc()).limit(10).all()
    recent_activity = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()

    paid_users = BotUser.query.filter(BotUser.plan.in_(['week', 'month', 'lifetime'])).all()
    revenue = sum(20 if u.plan == 'week' else 100 if u.plan == 'month' else 150 for u in paid_users)

    chart_labels, chart_wins, chart_losses = [], [], []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        chart_labels.append(day.strftime('%b %d'))
        chart_wins.append(Signal.query.filter(Signal.created_at >= day, Signal.created_at < next_day, Signal.result == 'win').count())
        chart_losses.append(Signal.query.filter(Signal.created_at >= day, Signal.created_at < next_day, Signal.result == 'loss').count())

    growth_labels, growth_data = [], []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        growth_labels.append(day.strftime('%b %d'))
        growth_data.append(BotUser.query.filter(BotUser.joined_at < next_day).count())

    return render_template('dashboard.html',
                           total_users=total_users,
                           active_subs=active_subs,
                           locked_users=locked_users,
                           total_signals=total_signals,
                           wins=wins, losses=losses,
                           win_rate=win_rate,
                           new_today=new_today,
                           signals_today=signals_today,
                           recent_users=recent_users,
                           recent_signals=recent_signals,
                           recent_activity=recent_activity,
                           revenue=revenue,
                           chart_labels=chart_labels,
                           chart_wins=chart_wins,
                           chart_losses=chart_losses,
                           growth_labels=growth_labels,
                           growth_data=growth_data)

@dash.route('/users')
@login_required
def users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    filter_plan = request.args.get('plan', '').strip()
    filter_status = request.args.get('status', '').strip()

    query = BotUser.query
    if search:
        query = query.filter((BotUser.username.ilike(f'%{search}%')) | (BotUser.first_name.ilike(f'%{search}%')))
    if filter_plan:
        query = query.filter_by(plan=filter_plan)
    if filter_status == 'locked':
        query = query.filter_by(is_locked=True)
    elif filter_status == 'active':
        query = query.filter_by(is_locked=False)

    users_page = query.order_by(BotUser.joined_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('users.html', users=users_page, search=search, filter_plan=filter_plan, filter_status=filter_status)

@dash.route('/users/<int:user_id>/toggle-lock', methods=['POST'])
@login_required
def toggle_lock(user_id):
    user = BotUser.query.get_or_404(user_id)
    user.is_locked = not user.is_locked
    db.session.commit()
    flash(f'User {user.first_name} {"locked" if user.is_locked else "unlocked"}', 'success')
    return redirect(url_for('dash.users'))

@dash.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
def activate_user(user_id):
    user = BotUser.query.get_or_404(user_id)
    plan = request.form.get('plan', 'week')
    user.plan = plan
    user.is_locked = False
    user.plan_started = now_local()
    if plan == 'lifetime':
        user.plan_expiry = None
    else:
        days = SUBSCRIPTION_PLANS.get(plan, {}).get('days', 7)
        user.plan_expiry = now_local() + timedelta(days=days)
    db.session.commit()
    flash(f'User {user.first_name} activated with {plan} plan', 'success')
    return redirect(url_for('dash.users'))

@dash.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    user = BotUser.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted', 'success')
    return redirect(url_for('dash.users'))

@dash.route('/content')
@login_required
def content():
    videos = VideoContent.query.order_by(VideoContent.created_at.desc()).all()
    strategies = Strategy.query.order_by(Strategy.created_at.desc()).all()
    return render_template('content.html', videos=videos, strategies=strategies)

@dash.route('/content/video/add', methods=['POST'])
@login_required
def add_video():
    v = VideoContent(
        title=request.form.get('title', ''),
        description=request.form.get('description', ''),
        video_url=request.form.get('video_url', ''),
        thumbnail_url=request.form.get('thumbnail_url', ''),
        category=request.form.get('category', 'strategy'),
        is_premium=request.form.get('is_premium') == 'on',
    )
    db.session.add(v)
    db.session.commit()
    flash('Video added', 'success')
    return redirect(url_for('dash.content'))

@dash.route('/content/video/<int:vid>/delete', methods=['POST'])
@login_required
def delete_video(vid):
    v = VideoContent.query.get_or_404(vid)
    db.session.delete(v)
    db.session.commit()
    flash('Video deleted', 'success')
    return redirect(url_for('dash.content'))

@dash.route('/content/video/<int:vid>/toggle', methods=['POST'])
@login_required
def toggle_video(vid):
    v = VideoContent.query.get_or_404(vid)
    v.is_active = not v.is_active
    db.session.commit()
    return redirect(url_for('dash.content'))

@dash.route('/content/strategy/add', methods=['POST'])
@login_required
def add_strategy():
    s = Strategy(
        title=request.form.get('title', ''),
        content=request.form.get('content', ''),
        category=request.form.get('category', 'beginner'),
        difficulty=request.form.get('difficulty', 'easy'),
        is_premium=request.form.get('is_premium') == 'on',
    )
    db.session.add(s)
    db.session.commit()
    flash('Strategy added', 'success')
    return redirect(url_for('dash.content'))

@dash.route('/content/strategy/<int:sid>/delete', methods=['POST'])
@login_required
def delete_strategy(sid):
    s = Strategy.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash('Strategy deleted', 'success')
    return redirect(url_for('dash.content'))

@dash.route('/subscriptions')
@login_required
def subscriptions():
    subs = BotUser.query.filter(BotUser.plan != 'trial').order_by(BotUser.plan_started.desc()).all()
    codes = ActivationCode.query.order_by(ActivationCode.created_at.desc()).limit(20).all()
    return render_template('subscriptions.html',
                           subs=subs,
                           codes=codes,
                           trial_users=BotUser.query.filter_by(plan='trial').count(),
                           week_users=BotUser.query.filter_by(plan='week').count(),
                           month_users=BotUser.query.filter_by(plan='month').count(),
                           lifetime_users=BotUser.query.filter_by(plan='lifetime').count())

@dash.route('/generate-key', methods=['POST'])
@login_required
def generate_key():
    plan = request.form.get('plan', 'week')
    code_str = f"MK-{plan[:2].upper()}-{random.randint(1000, 9999)}"
    ac = ActivationCode(code=code_str, plan=plan)
    db.session.add(ac)
    db.session.commit()
    flash(f'Generated Key: {code_str} ({plan.upper()})', 'success')
    return redirect(url_for('dash.subscriptions'))

@dash.route('/analytics')
@login_required
def analytics():
    signals = Signal.query.order_by(Signal.created_at.desc()).limit(100).all()
    pair_stats = {}
    for s in Signal.query.all():
        if s.pair not in pair_stats:
            pair_stats[s.pair] = {'wins': 0, 'losses': 0, 'total': 0}
        pair_stats[s.pair]['total'] += 1
        if s.result == 'win': pair_stats[s.pair]['wins'] += 1
        elif s.result == 'loss': pair_stats[s.pair]['losses'] += 1

    return render_template('analytics.html', signals=signals, pair_stats=pair_stats)

@dash.route('/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast():
    if request.method == 'POST':
        msg = request.form.get('message', '')
        if msg:
            db.session.add(BroadcastMessage(message=msg))
            db.session.commit()
            flash('Broadcast saved. Send via Telegram using /broadcast', 'info')
        return redirect(url_for('dash.broadcast'))
    return render_template('broadcast.html', broadcasts=BroadcastMessage.query.order_by(BroadcastMessage.sent_at.desc()).limit(20).all())

@dash.route('/api/stats')
@login_required
def api_stats():
    total_users = BotUser.query.count()
    active_subs = BotUser.query.filter(BotUser.plan != 'trial').count()
    locked = BotUser.query.filter_by(is_locked=True).count()
    total_signals = Signal.query.count()
    wins = Signal.query.filter_by(result='win').count()
    losses = Signal.query.filter_by(result='loss').count()
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = BotUser.query.filter(BotUser.joined_at >= today).count()

    return jsonify({
        'total_users': total_users,
        'active_subs': active_subs,
        'locked': locked,
        'total_signals': total_signals,
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
        'new_today': new_today,
        'timestamp': now_local().isoformat()
    })

@dash.route('/api/online-users')
@login_required
def api_online_users():
    threshold = now_local() - timedelta(minutes=5)
    return jsonify({'online': BotUser.query.filter(BotUser.last_active >= threshold).count()})
