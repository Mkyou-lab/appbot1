// static/js/dashboard.js

// Live Clock
function updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    const el = document.getElementById('liveClock');
    if (el) el.textContent = `${h}:${m}:${s}`;
}
setInterval(updateClock, 1000);
updateClock();

// Counter Animation
function animateCounters() {
    const counters = document.querySelectorAll('.counter');
    counters.forEach(counter => {
        const target = parseInt(counter.getAttribute('data-target'));
        const duration = 1500;
        const start = 0;
        const startTime = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            counter.textContent = Math.floor(eased * target);
            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                counter.textContent = target;
            }
        }
        requestAnimationFrame(update);
    });
}

// Run counters on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(animateCounters, 300);
});

// Sidebar Toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Close sidebar on click outside (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.sidebar-toggle');
    if (sidebar && sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove('open');
    }
});

// Live Stats Refresh
function refreshStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            // Update values if elements exist
            const mapping = {
                'total_users': data.total_users,
                'active_subs': data.active_subs,
                'total_signals': data.total_signals,
            };
            // Update stat cards
            document.querySelectorAll('.counter').forEach(el => {
                const target = el.getAttribute('data-target');
                // Re-animate if value changed
            });
        })
        .catch(() => {});
}

// Refresh online users
function refreshOnline() {
    fetch('/api/online-users')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('onlineCount');
            if (el) el.textContent = data.online || 0;
        })
        .catch(() => {});
}

// Refresh activity feed
function refreshActivity() {
    fetch('/api/recent-activity')
        .then(r => r.json())
        .then(data => {
            const feed = document.getElementById('activityFeed');
            if (!feed || data.length === 0) return;
            // Could dynamically update the feed here
        })
        .catch(() => {});
}

// Auto-refresh intervals
setInterval(refreshStats, 15000);
setInterval(refreshOnline, 10000);
setInterval(refreshActivity, 20000);

// Initial load
refreshOnline();

// Flash message auto-dismiss
document.querySelectorAll('.flash-alert').forEach(alert => {
    setTimeout(() => {
        alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-10px)';
        setTimeout(() => alert.remove(), 500);
    }, 5000);
});

// Add smooth page transitions
document.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', function(e) {
        // Add click ripple effect
        const ripple = document.createElement('span');
        ripple.style.cssText = `
            position: absolute;
            background: rgba(59,130,246,0.2);
            border-radius: 50%;
            width: 100px;
            height: 100px;
            transform: translate(-50%, -50%) scale(0);
            animation: ripple 0.6s ease-out;
            pointer-events: none;
        `;
        this.style.position = 'relative';
        this.style.overflow = 'hidden';
        const rect = this.getBoundingClientRect();
        ripple.style.left = (e.clientX - rect.left) + 'px';
        ripple.style.top = (e.clientY - rect.top) + 'px';
        this.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    });
});

// Add ripple keyframe
const style = document.createElement('style');
style.textContent = `
    @keyframes ripple {
        to { transform: translate(-50%, -50%) scale(4); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Table row hover glow effect
document.querySelectorAll('.data-table tr').forEach(row => {
    row.addEventListener('mouseenter', function() {
        this.style.transition = 'background 0.3s ease';
    });
});

console.log('%c🎯 MK SNIPER ENGINE v47.0', 'color: #3b82f6; font-size: 20px; font-weight: bold;');
console.log('%cDashboard Control Panel Active', 'color: #00ff88; font-size: 14px;');