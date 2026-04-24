import os
import time
import re
import json
import uuid
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, g)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
_base_dir = os.path.dirname(os.path.abspath(__file__))
app.config['DATABASE'] = os.environ.get('DATABASE') or os.path.join(_base_dir, 'wanderbuddy.db')
app.config['UPLOAD_FOLDER'] = os.path.join(_base_dir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID') or 'rzp_test_replace_me'
IS_SIMULATION_MODE = os.environ.get('IS_SIMULATION_MODE', 'false').lower() == 'true'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ITEMS_PER_PAGE = 12
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['ALLOWED_EXTENSIONS'] = ALLOWED_EXTENSIONS

ADMIN_EMAILS = ['admin@wanderbuddy.com', 'travelandtrouble@gmail.com']


# ── DECORATORS ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (session.get('user_role') == 'admin' or session.get('user_email') in ADMIN_EMAILS):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def vendor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') not in ['vendor', 'admin']:
            flash('Vendor access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ── SECURITY HEADERS ────────────────────────────────────────────────────────

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ── HELPER FUNCTIONS ───────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = text.strip('-')
    return text


def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


DEFAULT_SITE_SETTINGS = {
    'site_title': 'Travel & Trouble',
    'logo_url': '',
    'hero_tagline': 'Explore the Unexplored',
    'hero_subtext': 'Join us on unforgettable journeys through the mountains.',
    'email': 'hello@travelandtrouble.com',
    'phone': '+91 85956 89569',
    'shop_active': 1,
    'address': 'Mountain Base, Manali, Himachal Pradesh',
    'working_hours': 'Mon-Sat: 9AM-6PM',
    'instagram': 'https://instagram.com/travelandtrouble',
    'twitter': 'https://twitter.com/travelandtrouble',
    'facebook': 'https://facebook.com/travelandtrouble',
    'youtube': 'https://youtube.com/travelandtrouble',
    'year_established': '2020',
}


def ensure_site_settings_row(conn):
    conn.execute("""INSERT OR IGNORE INTO site_settings
        (id, site_title, hero_tagline, hero_subtext, email, phone, address,
         working_hours, year_established, logo_url, primary_color, font_family,
         instagram, twitter, facebook, youtube)
        VALUES (1,'Travel & Trouble','Where Adventure Meets Comfort',
        'Discover breathtaking destinations crafted for the modern explorer',
        'admin@travelandtrouble.com','+91 85956 89569','New Delhi, India',
        'Mon-Sat 9am-6pm',2022,'','#C4622D','DM Sans','','','','')""")
    row = conn.execute("SELECT * FROM site_settings WHERE id=1").fetchone()
    return dict(row) if row else DEFAULT_SITE_SETTINGS.copy()


def load_cms_page(conn, page_name):
    defaults = {
        'about': ('About Travel & Trouble', '<h2>About Us</h2><p>We are a travel company.</p>'),
        'privacy': ('Privacy Policy', '<h2>Privacy Policy</h2><p>Your privacy matters.</p>'),
        'terms': ('Terms & Conditions', '<h2>Terms</h2><p>Please read our terms.</p>'),
        'home': ('Home', '<p>Welcome!</p>'),
    }
    existing = conn.execute("SELECT id FROM page_content WHERE page_name=?", (page_name,)).fetchone()
    if not existing:
        title, content = defaults.get(page_name, (page_name.title(), f'<p>{page_name} page content.</p>'))
        conn.execute("INSERT OR IGNORE INTO page_content (page_name, title, content) VALUES (?,?,?)",
                     (page_name, title, content))


def get_booking_target(conn, target_id):
    try:
        trip = conn.execute("SELECT * FROM trips WHERE id=?", (target_id,)).fetchone()
        if trip:
            return dict(trip), 'trip'
        event = conn.execute("SELECT * FROM events WHERE id=?", (target_id,)).fetchone()
        if event:
            return dict(event), 'event'
        upcoming_event = conn.execute("SELECT * FROM upcoming_events WHERE id=?", (target_id,)).fetchone()
        if upcoming_event:
            return dict(upcoming_event), 'upcoming_event'
        return None, None
    except Exception as e:
        print(f"Error in get_booking_target for {target_id}: {e}")
        return None, None


def build_batch_choices(conn, target, target_type):
    try:
        if target_type == 'event' or target_type == 'upcoming_event':
            ed = target.get('event_date', 'TBC')
            return [{'value': ed, 'label': ed, 'status': 'pending'}]
        batches = conn.execute(
            "SELECT * FROM trip_batches WHERE trip_id=? ORDER BY batch_date", (target['id'],)).fetchall()
        if not batches:
            return [{'value': 'TBC', 'label': 'Dates to be confirmed', 'status': 'pending'}]
        choices = []
        for b in batches:
            label = f"{b['batch_date']} ({b['current_bookings']}/{b['max_allowed']} booked)"
            choices.append({'value': b['batch_date'], 'label': label, 'status': b['status']})
        return choices
    except Exception as e:
        print(f"Error in build_batch_choices: {e}")
        return [{'value': 'TBC', 'label': 'Dates to be confirmed', 'status': 'pending'}]


def get_membership_discount(user_id):
    if not user_id:
        return 0
    conn = get_db_connection()
    sub = conn.execute(
        "SELECT plan_name FROM subscriptions WHERE user_id=? AND status='active' AND valid_until > date('now')",
        (user_id,)).fetchone()
    conn.close()
    if not sub:
        return 0
    return {'basic': 5, 'pro': 10, 'elite': 15}.get(sub['plan_name'], 0)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def slugify(value):
    value = str(value).lower().strip()
    value = re.sub(r'[^\w\s-]', '', value)
    value = re.sub(r'[\s_]+', '-', value)
    value = re.sub(r'-+', '-', value)
    return value.strip('-')


def migrate_bookings_table(conn):
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if 'booking_type' not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN booking_type TEXT DEFAULT 'trip'")
        if 'num_travelers' not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN num_travelers INTEGER DEFAULT 1")
        if 'sharing_type' not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN sharing_type TEXT DEFAULT 'quad'")
        if 'price_per_person' not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN price_per_person INTEGER DEFAULT 0")
        if 'total_price' not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN total_price INTEGER DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_type_target ON bookings(booking_type, trip_id)")
    except Exception:
        pass


def ensure_database_ready():
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    conn = get_db_connection()
    with open(schema_path, 'r') as f:
        schema = f.read()
    conn.executescript(schema)
    migrate_bookings_table(conn)
    
    # ── Custom Migrations ───────────────────────────────────────────────────
    try:
        # Add is_active to quests
        cols_q = [r[1] for r in conn.execute("PRAGMA table_info(quests)").fetchall()]
        if 'is_active' not in cols_q:
            conn.execute("ALTER TABLE quests ADD COLUMN is_active BOOLEAN DEFAULT 1")
            
        # Add shop_active to site_settings
        cols_s = [r[1] for r in conn.execute("PRAGMA table_info(site_settings)").fetchall()]
        if 'shop_active' not in cols_s:
            conn.execute("ALTER TABLE site_settings ADD COLUMN shop_active BOOLEAN DEFAULT 1")
    except Exception as e:
        print(f"Migration error: {e}")
        
    ensure_site_settings_row(conn)
    for pname in ['about', 'privacy', 'terms', 'home', 'events-cms', 'featured-events-cms']:
        load_cms_page(conn, pname)
    conn.commit()
    conn.close()


ensure_database_ready()


# ── CONTEXT PROCESSOR ───────────────────────────────────────────────────────

@app.context_processor
def inject_site_settings():
    try:
        conn = get_db_connection()
        settings = ensure_site_settings_row(conn)
        conn.close()
        return dict(settings=settings)
    except Exception:
        return dict(settings=DEFAULT_SITE_SETTINGS.copy())


# ── PUBLIC ROUTES ────────────────────────────────────────────────────────────

@app.route('/test-route')
def test_route():
    return 'Route working!'

@app.route('/')
def index():
    conn = get_db_connection()
    featured_trips = conn.execute("SELECT * FROM trips ORDER BY ROWID DESC LIMIT 4").fetchall()
    events = conn.execute("SELECT * FROM events ORDER BY event_date LIMIT 3").fetchall()
    upcoming_events = conn.execute("SELECT * FROM upcoming_events ORDER BY event_date ASC").fetchall()
    shop_items = conn.execute("SELECT * FROM merchandise WHERE stock > 0 LIMIT 4").fetchall()
    home_content = conn.execute("SELECT content FROM page_content WHERE page_name='home'").fetchone()
    conn.close()
    return render_template('index.html',
                           featured_trips=featured_trips,
                           events=events,
                           upcoming_events=upcoming_events,
                           shop_items=shop_items,
                           home_content=home_content['content'] if home_content else '')


@app.route('/trips')
def trips():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    difficulty = request.args.get('difficulty', '')
    conn = get_db_connection()
    query = "SELECT * FROM trips WHERE 1=1"
    params = []
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if category:
        query += " AND category=?"
        params.append(category)
    if difficulty:
        query += " AND difficulty=?"
        params.append(difficulty)
    query += " ORDER BY title"
    all_trips = conn.execute(query, params).fetchall()
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM trips").fetchall()]
    conn.close()
    return render_template('trips.html', all_trips=all_trips, search=search,
                           category=category, difficulty=difficulty, categories=categories)


@app.route('/treks')
def treks():
    search = request.args.get('search', '')
    location = request.args.get('location', '')
    difficulty = request.args.get('difficulty', '')
    category = request.args.get('category', '')
    page = int(request.args.get('page', 1))
    per_page = ITEMS_PER_PAGE
    conn = get_db_connection()
    query = "SELECT * FROM trips WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM trips WHERE 1=1"
    params = []
    if search:
        cond = " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        query += cond
        count_query += cond
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if location:
        query += " AND location=?"
        count_query += " AND location=?"
        params.append(location)
    if difficulty:
        query += " AND difficulty=?"
        count_query += " AND difficulty=?"
        params.append(difficulty)
    if category:
        query += " AND category=?"
        count_query += " AND category=?"
        params.append(category)
    total = conn.execute(count_query, params).fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    query += f" ORDER BY title LIMIT {per_page} OFFSET {(page-1)*per_page}"
    trips_page = conn.execute(query, params).fetchall()
    all_locations = [r[0] for r in conn.execute("SELECT DISTINCT location FROM trips").fetchall()]
    all_categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM trips").fetchall()]
    conn.close()
    return render_template('treks.html', trips=trips_page, page=page, total_pages=total_pages,
                           has_prev=page > 1, has_next=page < total_pages,
                           all_locations=all_locations, all_categories=all_categories,
                           search=search, location=location, difficulty=difficulty, category=category)


@app.route('/events')
def events():
    category = request.args.get('category', '')
    conn = get_db_connection()
    if category:
        all_events = conn.execute("SELECT * FROM events WHERE category=?", (category,)).fetchall()
    else:
        all_events = conn.execute("SELECT * FROM events").fetchall()
    categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM events").fetchall()]
    conn.close()
    return render_template('events.html', all_events=all_events, category=category, categories=categories)


@app.route('/trip/<trip_id>')
def trip_details(trip_id):
    try:
        conn = get_db_connection()
        target, target_type = get_booking_target(conn, trip_id)
        if not target:
            conn.close()
            return render_template('404.html'), 404
        batch_choices = build_batch_choices(conn, target, target_type)
        addons = []
        if target_type == 'trip':
            try:
                addons = conn.execute("SELECT a.*, u.name as vendor_name FROM addons a JOIN users u ON a.vendor_id=u.id WHERE a.trip_id=?", (trip_id,)).fetchall()
            except Exception as e:
                addons = []
        existing_booking = None
        sub_tier = None
        discount_pct = 0
        if session.get('user_id'):
            existing_booking = conn.execute(
                "SELECT * FROM bookings WHERE user_id=? AND trip_id=? AND status NOT IN ('cancelled')",
                (session['user_id'], trip_id)).fetchone()
            discount_pct = get_membership_discount(session['user_id'])
            sub = conn.execute(
                "SELECT plan_name FROM subscriptions WHERE user_id=? AND status='active' AND valid_until > date('now')",
                (session['user_id'],)).fetchone()
            if sub:
                sub_tier = sub['plan_name']
        
        itinerary = []
        raw_itinerary = target.get('itinerary', '[]')
        if raw_itinerary and target_type == 'trip':
            try:
                itinerary = json.loads(raw_itinerary)
            except:
                itinerary = []
        conn.close()
        return render_template('trip_details.html', trip=target, target_type=target_type, 
                               batch_choices=batch_choices, addons=addons, 
                               existing_booking=existing_booking, sub_tier=sub_tier, 
                               discount_pct=discount_pct, itinerary=itinerary,
                               razorpay_key=RAZORPAY_KEY_ID)
    except Exception as e:
        logger.error(f"Error in trip_details for {trip_id}: {e}")
        return render_template('404.html'), 404


@app.route('/shop')
def shop():
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM merchandise WHERE stock > 0").fetchall()
    cart = session.get('cart', {})
    cart_count = sum(cart.values())
    conn.close()
    return render_template('shop.html', items=items, cart_count=cart_count)


@app.route('/about')
def about():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM page_content WHERE page_name='about'").fetchone()
    conn.close()
    return render_template('about.html', page=page)


@app.route('/privacy')
def privacy():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM page_content WHERE page_name='privacy'").fetchone()
    conn.close()
    return render_template('privacy.html', page=page)


@app.route('/terms')
def terms():
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM page_content WHERE page_name='terms'").fetchone()
    conn.close()
    return render_template('terms.html', page=page)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', 'general').strip()
        message = request.form.get('message', '').strip()
        if name and email and message:
            conn = get_db_connection()
            conn.execute("INSERT INTO contact_messages (name,email,subject,message) VALUES (?,?,?,?)",
                         (name, email, subject, message))
            conn.commit()
            conn.close()
            flash('Thank you! We will get back to you soon.', 'success')
        else:
            flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('contact'))
    return render_template('contact.html')


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results_trips, results_events, results_merch = [], [], []
    if q:
        conn = get_db_connection()
        like = f'%{q}%'
        results_trips = conn.execute(
            "SELECT * FROM trips WHERE title LIKE ? OR description LIKE ? OR location LIKE ?",
            (like, like, like)).fetchall()
        results_events = conn.execute(
            "SELECT * FROM events WHERE title LIKE ? OR description LIKE ? OR location LIKE ?",
            (like, like, like)).fetchall()
        results_merch = conn.execute(
            "SELECT * FROM merchandise WHERE name LIKE ? OR description LIKE ?",
            (like, like)).fetchall()
        conn.close()
    return render_template('search_results.html', q=q,
                           results_trips=results_trips,
                           results_events=results_events,
                           results_merch=results_merch)


# ── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            session['user_email'] = user['email']
            flash(f"Welcome back, {user['name']}!", 'success')
            if user['role'] == 'admin' or email in ADMIN_EMAILS:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        is_vendor = request.form.get('is_vendor')
        business_name = request.form.get('business_name', '').strip()
        if not name or not email or not password:
            flash('Please fill in all required fields.', 'danger')
            return render_template('signup.html')
        role = 'admin' if email in ADMIN_EMAILS else ('vendor' if is_vendor else 'traveler')
        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            conn.close()
            flash('An account with this email already exists.', 'danger')
            return render_template('signup.html')
        hashed = generate_password_hash(password)
        conn.execute("INSERT INTO users (name,email,password,phone,role) VALUES (?,?,?,?,?)",
                     (name, email, hashed, phone, role))
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if is_vendor and business_name and user:
            conn.execute(
                "INSERT INTO vendor_profiles (user_id, business_name, business_type, verified) VALUES (?,?,?,0)",
                (user['id'], business_name, request.form.get('business_type', '')))
            conn.commit()
        conn.close()
        session.permanent = True
        session['user_id'] = user['id']
        session['user_name'] = name
        session['user_role'] = role
        session['user_email'] = email
        flash(f"Account created! Welcome, {name}!", 'success')
        return redirect(url_for('admin_panel') if role == 'admin' else url_for('dashboard'))
    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        conn = get_db_connection()
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now() + timedelta(hours=1)).isoformat()
            conn.execute("UPDATE users SET reset_token=?, reset_expiry=? WHERE id=?",
                         (token, expiry, user['id']))
            conn.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            if MAIL_ENABLED:
                try:
                    msg = MailMessage('Password Reset', recipients=[email],
                                      body=f'Click here to reset your password: {reset_link}')
                    mail.send(msg)
                    flash('Password reset email sent!', 'success')
                except Exception:
                    flash(f'Reset link (simulation): {reset_link}', 'info')
            else:
                flash(f'Reset link (test mode): {reset_link}', 'info')
        else:
            flash('If that email exists, a reset link has been sent.', 'info')
        conn.close()
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE reset_token=? AND reset_expiry > ?",
        (token, datetime.now().isoformat())).fetchone()
    if not user:
        conn.close()
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        else:
            conn.execute("UPDATE users SET password=?, reset_token=NULL, reset_expiry=NULL WHERE id=?",
                         (generate_password_hash(password), user['id']))
            conn.commit()
            conn.close()
            flash('Password updated! Please log in.', 'success')
            return redirect(url_for('login'))
    conn.close()
    return render_template('reset_password.html', token=token)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        conn.execute("UPDATE users SET name=?, phone=? WHERE id=?",
                     (name, phone, session['user_id']))
        conn.commit()
        session['user_name'] = name
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not check_password_hash(user['password'], current):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm:
        flash('New passwords do not match.', 'danger')
    elif len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
    else:
        conn.execute("UPDATE users SET password=? WHERE id=?",
                     (generate_password_hash(new_pw), session['user_id']))
        conn.commit()
        flash('Password changed successfully!', 'success')
    conn.close()
    return redirect(url_for('profile'))


# ── BOOKING ROUTES ───────────────────────────────────────────────────────────

@app.route('/book', methods=['POST'])
@login_required
def book():
    trip_id = request.form.get('trip_id')
    batch_date = request.form.get('batch_date', 'TBC')
    num_travelers = max(1, min(12, int(request.form.get('num_travelers', 1))))
    sharing_type = request.form.get('sharing_type', 'quad')
    addon_ids = request.form.getlist('addons')
    conn = get_db_connection()
    target, target_type = get_booking_target(conn, trip_id)
    if not target:
        conn.close()
        flash('Invalid adventure selected.', 'danger')
        return redirect(url_for('index'))

    base_price = int(target.get('price', 0))
    num_travelers = int(request.form.get('num_travelers', 1))
    sharing_type = request.form.get('sharing_type', 'quad')
    
    # Calculate per-person price based on sharing
    if target_type == 'trip':
        # Applying sharing multipliers
        sharing_multipliers = {'quad': 1.0, 'triple': 1.125, 'double': 1.375}
        price_per_person = int(base_price * sharing_multipliers.get(sharing_type, 1.0))
    else:
        price_per_person = base_price

    addon_ids = request.form.getlist('addons')
    addons_info = []
    addons_total = 0
    if addon_ids:
        for aid in addon_ids:
            row = conn.execute("SELECT * FROM addons WHERE id=?", (aid,)).fetchone()
            if row:
                addons_info.append(row)
                addons_total += row['price']

    # Total Price Calculation
    sub_discount = get_membership_discount(session['user_id'])
    total_price = (price_per_person * num_travelers) + (addons_total * num_travelers)
    if sub_discount > 0:
        total_price = int(total_price * (1 - sub_discount / 100))

    try:
        cur = conn.execute(
            '''INSERT INTO bookings (user_id, trip_id, booking_type, batch_date, 
               num_travelers, sharing_type, price_per_person, total_price, status) 
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (session['user_id'], trip_id, target_type, batch_date, 
             num_travelers, sharing_type, price_per_person, total_price, 'pending')
        )
        booking_id = cur.lastrowid
        for aid in addon_ids:
            conn.execute("INSERT INTO booking_addons (booking_id, addon_id) VALUES (?,?)", (booking_id, aid))
        conn.commit()
    except Exception as e:
        conn.close()
        flash('Something went wrong. Please try again.', 'danger')
        return redirect(url_for('trips'))
    
    conn.close()
    return redirect(url_for('payment', booking_id=booking_id))


@app.route('/payment/<int:booking_id>')
@login_required
def payment(booking_id):
    conn = get_db_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",
                           (booking_id, session['user_id'])).fetchone()
    if not booking:
        conn.close()
        flash('Booking not found.', 'danger')
        return redirect(url_for('dashboard'))
    target, target_type = get_booking_target(conn, booking['trip_id'])
    addons = conn.execute(
        "SELECT a.* FROM addons a JOIN booking_addons ba ON a.id=ba.addon_id WHERE ba.booking_id=?",
        (booking_id,)).fetchall()
    addon_total = sum(a['price'] for a in addons)
    final_total = booking['total_price'] + addon_total
    batch_info = None
    if target_type == 'trip':
        batch = conn.execute(
            "SELECT * FROM trip_batches WHERE trip_id=? AND batch_date=?",
            (booking['trip_id'], booking['batch_date'])).fetchone()
        if batch:
            batch_info = {'current': batch['current_bookings'], 'min_required': 6,
                          'max_allowed': 16, 'confirmed': batch['current_bookings'] >= 6}
    sub = conn.execute(
        "SELECT plan_name FROM subscriptions WHERE user_id=? AND status='active' AND valid_until > date('now')",
        (session['user_id'],)).fetchone()
    membership_tier = sub['plan_name'] if sub else None
    conn.close()
    return render_template('payment.html', booking=booking, target=target, addons=addons,
                           addon_total=addon_total, final_total=final_total,
                           batch_info=batch_info, membership_tier=membership_tier,
                           razorpay_key=RAZORPAY_KEY_ID, is_simulation=IS_SIMULATION_MODE)


@app.route('/process_payment/<int:booking_id>', methods=['POST'])
@login_required
def process_payment(booking_id):
    conn = get_db_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",
                           (booking_id, session['user_id'])).fetchone()
    if not booking:
        conn.close()
        flash('Booking not found.', 'danger')
        return redirect(url_for('dashboard'))
    payment_id = request.form.get('razorpay_payment_id') or f"SIM_{uuid.uuid4().hex[:12].upper()}"
    conn.execute("UPDATE bookings SET status='confirmed', payment_id=? WHERE id=?",
                 (payment_id, booking_id))
    conn.commit()
    conn.close()
    flash('Payment successful! Your booking is confirmed.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",
                           (booking_id, session['user_id'])).fetchone()
    if not booking:
        conn.close()
        flash('Booking not found.', 'danger')
        return redirect(url_for('dashboard'))
    if booking['status'] == 'cancelled':
        conn.close()
        flash('Booking is already cancelled.', 'info')
        return redirect(url_for('dashboard'))
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    if booking['booking_type'] == 'trip':
        conn.execute(
            "UPDATE trip_batches SET current_bookings = MAX(current_bookings - ?, 0) WHERE trip_id=? AND batch_date=?",
            (booking['num_travelers'], booking['trip_id'], booking['batch_date']))
    conn.commit()
    conn.close()
    flash('Booking cancelled.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    bookings = conn.execute(
        """SELECT b.*, COALESCE(t.title, e.title) as trip_title, COALESCE(t.image_url, e.image_url) as trip_image
           FROM bookings b
           LEFT JOIN trips t ON b.trip_id=t.id AND b.booking_type='trip'
           LEFT JOIN events e ON b.trip_id=e.id AND b.booking_type='event'
           WHERE b.user_id=? ORDER BY b.id DESC""",
        (session['user_id'],)).fetchall()
    booking_ids = [b['id'] for b in bookings if b['status'] == 'confirmed']
    user_quests = []
    if booking_ids:
        placeholders = ','.join('?' * len(booking_ids))
        user_quests = conn.execute(
            f"""SELECT uq.*, q.title as quest_title, q.points, q.icon, q.is_active
                FROM user_quests uq JOIN quests q ON uq.quest_id=q.id
                WHERE uq.booking_id IN ({placeholders})""",
            booking_ids).fetchall()
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND valid_until > date('now')",
        (session['user_id'],)).fetchone()
    shop_orders = conn.execute(
        "SELECT * FROM shop_orders WHERE user_id=? ORDER BY id DESC",
        (session['user_id'],)).fetchall()
    conn.close()
    return render_template('dashboard.html', bookings=bookings, user_quests=user_quests,
                           subscription=sub, shop_orders=shop_orders)


@app.route('/upload/<int:booking_id>', methods=['POST'])
@login_required
def upload_document(booking_id):
    conn = get_db_connection()
    booking = conn.execute("SELECT * FROM bookings WHERE id=? AND user_id=?",
                           (booking_id, session['user_id'])).fetchone()
    if not booking:
        conn.close()
        flash('Booking not found.', 'danger')
        return redirect(url_for('dashboard'))
    if 'document' not in request.files:
        flash('No file selected.', 'danger')
        return redirect(url_for('dashboard'))
    f = request.files['document']
    if f and allowed_file(f.filename):
        filename = secure_filename(f.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        conn.execute("UPDATE bookings SET document_path=? WHERE id=?",
                     (unique_name, booking_id))
        conn.commit()
        flash('Document uploaded successfully!', 'success')
    else:
        flash('Invalid file type.', 'danger')
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/complete_quest', methods=['POST'])
@login_required
def complete_quest():
    booking_id = request.form.get('booking_id')
    quest_id = request.form.get('quest_id')
    proof_image = None
    if 'proof_image' in request.files:
        f = request.files['proof_image']
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            proof_image = unique_name
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM user_quests WHERE booking_id=? AND quest_id=?",
                            (booking_id, quest_id)).fetchone()
    if not existing:
        conn.execute("INSERT INTO user_quests (booking_id, quest_id, status, proof_image) VALUES (?,?,?,?)",
                     (booking_id, quest_id, 'pending', proof_image))
        conn.commit()
        flash('Quest submitted for review!', 'success')
    else:
        flash('You have already submitted this quest.', 'info')
    conn.close()
    return redirect(url_for('dashboard'))


# ── SHOP ROUTES ──────────────────────────────────────────────────────────────

@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    cart = session.get('cart', {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    session['cart'] = cart
    session.modified = True
    flash('Item added to cart!', 'success')
    return redirect(url_for('shop'))


@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    qty = int(request.form.get('quantity', 0))
    cart = session.get('cart', {})
    if qty <= 0:
        cart.pop(str(item_id), None)
    else:
        cart[str(item_id)] = qty
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('cart'))


@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    cart = session.get('cart', {})
    cart.pop(str(item_id), None)
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('cart'))


@app.route('/cart')
def cart():
    cart = session.get('cart', {})
    if not cart:
        return render_template('cart.html', items=[], total=0, cart_count=0)
    conn = get_db_connection()
    item_ids = list(cart.keys())
    placeholders = ','.join('?' * len(item_ids))
    db_items = conn.execute(
        f"SELECT * FROM merchandise WHERE id IN ({placeholders})", item_ids).fetchall()
    conn.close()
    items = []
    total = 0
    for item in db_items:
        qty = cart.get(str(item['id']), 0)
        subtotal = item['price'] * qty
        total += subtotal
        items.append({'item': item, 'qty': qty, 'subtotal': subtotal})
    cart_count = sum(cart.values())
    return render_template('cart.html', items=items, total=total, cart_count=cart_count)


@app.route('/checkout_shop', methods=['POST'])
@login_required
def checkout_shop():
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'danger')
        return redirect(url_for('shop'))
    conn = get_db_connection()
    item_ids = list(cart.keys())
    placeholders = ','.join('?' * len(item_ids))
    db_items = conn.execute(
        f"SELECT * FROM merchandise WHERE id IN ({placeholders})", item_ids).fetchall()
    item_map = {str(i['id']): i for i in db_items}
    # Check stock
    for iid, qty in cart.items():
        item = item_map.get(str(iid))
        if not item or item['stock'] < qty:
            conn.close()
            flash(f'Insufficient stock for {item["name"] if item else "item"}.', 'danger')
            return redirect(url_for('cart'))
    total = sum(item_map[str(iid)]['price'] * qty for iid, qty in cart.items() if str(iid) in item_map)
    conn.execute("INSERT INTO shop_orders (user_id, total_amount, status) VALUES (?,?,?)",
                 (session['user_id'], total, 'pending'))
    conn.commit()
    order = conn.execute("SELECT last_insert_rowid() as id").fetchone()
    order_id = order['id']
    for iid, qty in cart.items():
        item = item_map.get(str(iid))
        if item:
            conn.execute(
                "INSERT INTO shop_order_items (order_id, item_id, quantity, price_at_purchase) VALUES (?,?,?,?)",
                (order_id, int(iid), qty, item['price']))
            conn.execute("UPDATE merchandise SET stock = stock - ? WHERE id=?", (qty, int(iid)))
    conn.commit()
    conn.close()
    session.pop('cart', None)
    session.modified = True
    return redirect(url_for('shop_payment', order_id=order_id))


@app.route('/shop/payment/<int:order_id>')
@login_required
def shop_payment(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM shop_orders WHERE id=? AND user_id=?",
                         (order_id, session['user_id'])).fetchone()
    if not order:
        conn.close()
        flash('Order not found.', 'danger')
        return redirect(url_for('dashboard'))
    items = conn.execute(
        """SELECT soi.*, m.name, m.image_url FROM shop_order_items soi
           JOIN merchandise m ON soi.item_id=m.id WHERE soi.order_id=?""",
        (order_id,)).fetchall()
    conn.close()
    return render_template('shop_payment.html', order=order, items=items,
                           razorpay_key=RAZORPAY_KEY_ID, is_simulation=IS_SIMULATION_MODE)


@app.route('/shop/payment/confirm', methods=['POST'])
@login_required
def confirm_shop_payment():
    order_id = request.form.get('order_id')
    payment_id = request.form.get('razorpay_payment_id') or f"SIM_{uuid.uuid4().hex[:12].upper()}"
    conn = get_db_connection()
    conn.execute("UPDATE shop_orders SET status='confirmed' WHERE id=? AND user_id=?",
                 (order_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Order confirmed! Thank you for your purchase.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/cancel_order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM shop_orders WHERE id=? AND user_id=?",
                         (order_id, session['user_id'])).fetchone()
    if not order:
        conn.close()
        flash('Order not found.', 'danger')
        return redirect(url_for('dashboard'))
    if order['status'] == 'shipped':
        conn.close()
        flash('Cannot cancel a shipped order.', 'danger')
        return redirect(url_for('dashboard'))
    if order['status'] == 'cancelled':
        conn.close()
        flash('Order is already cancelled.', 'info')
        return redirect(url_for('dashboard'))
    items = conn.execute("SELECT * FROM shop_order_items WHERE order_id=?", (order_id,)).fetchall()
    for item in items:
        conn.execute("UPDATE merchandise SET stock = stock + ? WHERE id=?",
                     (item['quantity'], item['item_id']))
    conn.execute("UPDATE shop_orders SET status='cancelled' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    flash('Order cancelled and stock restored.', 'success')
    return redirect(url_for('dashboard'))


# ── EXPLORER PASS ROUTES ─────────────────────────────────────────────────────

@app.route('/explorer-pass')
def explorer_pass():
    plans = [
        {'name': 'basic', 'label': 'Basic', 'price': 999, 'discount': '5%',
         'features': ['5% off all trips', 'Early booking access', 'Explorer community access']},
        {'name': 'pro', 'label': 'Pro', 'price': 1999, 'discount': '10%',
         'features': ['10% off all trips', 'Priority booking', 'Free gear rental (1/yr)', 'Exclusive events access']},
        {'name': 'elite', 'label': 'Elite', 'price': 4999, 'discount': '15%',
         'features': ['15% off all trips', 'VIP booking', 'Free gear rental (unlimited)', 'Dedicated trip concierge', 'Annual surprise gift']},
    ]
    sub = None
    if session.get('user_id'):
        conn = get_db_connection()
        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND valid_until > date('now')",
            (session['user_id'],)).fetchone()
        conn.close()
    return render_template('subscription.html', plans=plans, current_sub=sub,
                           razorpay_key=RAZORPAY_KEY_ID)


@app.route('/subscribe_pass', methods=['POST'])
@login_required
def subscribe_pass():
    tier = request.form.get('tier', 'basic')
    prices = {'basic': 999, 'pro': 1999, 'elite': 4999}
    price = prices.get(tier, 999)
    session['pending_pass_tier'] = tier
    session['pending_pass_price'] = price
    session.modified = True
    return redirect(url_for('explorer_pass_payment'))


@app.route('/explorer-pass/payment')
@login_required
def explorer_pass_payment():
    tier = session.get('pending_pass_tier')
    price = session.get('pending_pass_price')
    if not tier or not price:
        return redirect(url_for('explorer_pass'))
    return render_template('explorer_pass_payment.html', tier=tier, price=price,
                           razorpay_key=RAZORPAY_KEY_ID, is_simulation=IS_SIMULATION_MODE)


@app.route('/explorer-pass/confirm', methods=['POST'])
@login_required
def confirm_explorer_pass():
    tier = session.pop('pending_pass_tier', None)
    price = session.pop('pending_pass_price', None)
    if not tier:
        return redirect(url_for('explorer_pass'))
    payment_id = request.form.get('razorpay_payment_id') or f"SIM_{uuid.uuid4().hex[:12].upper()}"
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM subscriptions WHERE user_id=?",
                            (session['user_id'],)).fetchone()
    if existing:
        conn.execute(
            "UPDATE subscriptions SET plan_name=?, status='active', valid_until=date('now','+1 year') WHERE user_id=?",
            (tier, session['user_id']))
    else:
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan_name, status, valid_until) VALUES (?,?,'active',date('now','+1 year'))",
            (session['user_id'], tier))
    conn.commit()
    conn.close()
    flash(f'Explorer Pass ({tier.title()}) activated! Enjoy your benefits.', 'success')
    return redirect(url_for('explorer_pass'))


# ── COMMUNITY ROUTES ─────────────────────────────────────────────────────────

@app.route('/community')
def community():
    conn = get_db_connection()
    posts = conn.execute(
        "SELECT p.*, u.name as author FROM posts p JOIN users u ON p.user_id=u.id ORDER BY p.timestamp DESC"
    ).fetchall()
    conn.close()
    return render_template('community.html', posts=posts)


@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        tag = request.form.get('tag', 'General').strip()
        
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                ext = filename.rsplit('.', 1)[1].lower()
                new_filename = f"post_{int(time.time())}_{session['user_id']}.{ext}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                file.save(file_path)
                image_url = f"/static/uploads/{new_filename}"

        if title and content:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO posts (user_id, title, content, tag, image_url) VALUES (?,?,?,?,?)",
                (session['user_id'], title, content, tag, image_url))
            conn.commit()
            conn.close()
            flash('Post published!', 'success')
            return redirect(url_for('community'))
        flash('Title and content are required.', 'danger')
    return render_template('create_post.html')


@app.route('/chat')
@login_required
def chat():
    conn = get_db_connection()
    messages = conn.execute(
        "SELECT * FROM messages WHERE room_id='general' ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    conn.close()
    messages = list(reversed(messages))
    return render_template('chat.html', messages=messages)


@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    content = request.json.get('content', '').strip() if request.is_json else request.form.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'error': 'Empty message'})
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO messages (room_id, user_id, sender, content, msg_type) VALUES (?,?,?,?,?)",
        ('general', session['user_id'], session['user_name'], content, 'text'))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/upload_chat_image', methods=['POST'])
@login_required
def upload_chat_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No file'})
    f = request.files['image']
    if f and allowed_file(f.filename):
        filename = secure_filename(f.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        image_url = url_for('static', filename=f'uploads/{unique_name}')
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO messages (room_id, user_id, sender, content, msg_type) VALUES (?,?,?,?,?)",
            ('general', session['user_id'], session['user_name'], image_url, 'image'))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'url': image_url})
    return jsonify({'success': False, 'error': 'Invalid file'})


@app.route('/get_messages/<room_id>')
@login_required
def get_messages(room_id):
    conn = get_db_connection()
    messages = conn.execute(
        "SELECT id, sender, content, msg_type, timestamp FROM messages WHERE room_id=? ORDER BY timestamp DESC LIMIT 50",
        (room_id,)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in reversed(messages)])


@app.route('/delete_message/<int:msg_id>', methods=['POST'])
@login_required
def delete_message(msg_id):
    conn = get_db_connection()
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    if msg and (msg['user_id'] == session['user_id'] or session.get('user_role') == 'admin'):
        conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    conn.close()
    return jsonify({'success': False, 'error': 'Not authorized'})


@app.route('/edit_message/<int:msg_id>', methods=['POST'])
@login_required
def edit_message(msg_id):
    new_content = request.json.get('content', '').strip() if request.is_json else ''
    if not new_content:
        return jsonify({'success': False})
    conn = get_db_connection()
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    if msg and msg['user_id'] == session['user_id']:
        conn.execute("UPDATE messages SET content=? WHERE id=?", (new_content, msg_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    conn.close()
    return jsonify({'success': False, 'error': 'Not authorized'})


@app.route('/post/like/<int:post_id>', methods=['POST'])
def like_post(post_id):
    # Simple like - no auth required for demo
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN likes INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    conn.execute("UPDATE posts SET likes = COALESCE(likes, 0) + 1 WHERE id=?", (post_id,))
    conn.commit()
    post = conn.execute("SELECT likes FROM posts WHERE id=?", (post_id,)).fetchone()
    conn.close()
    return jsonify({'likes': post['likes'] if post else 0})


# ── VENDOR ROUTES ─────────────────────────────────────────────────────────────

@app.route('/vendor/dashboard')
@login_required
@vendor_required
def vendor_dashboard():
    conn = get_db_connection()
    vp = conn.execute("SELECT * FROM vendor_profiles WHERE user_id=?", (session['user_id'],)).fetchone()
    addons = conn.execute(
        "SELECT a.*, t.title as trip_title FROM addons a LEFT JOIN trips t ON a.trip_id=t.id WHERE a.vendor_id=?",
        (session['user_id'],)).fetchall()
    addon_ids = [a['id'] for a in addons]
    earnings = 0
    if addon_ids:
        placeholders = ','.join('?' * len(addon_ids))
        result = conn.execute(
            f"""SELECT SUM(a.price) FROM addons a
                JOIN booking_addons ba ON a.id=ba.addon_id
                JOIN bookings b ON ba.booking_id=b.id
                WHERE a.id IN ({placeholders}) AND b.status='confirmed'""",
            addon_ids).fetchone()
        earnings = result[0] or 0
    conn.close()
    return render_template('vendor_dashboard.html', vendor_profile=vp, addons=addons, earnings=earnings)


@app.route('/vendor/addons')
@login_required
@vendor_required
def vendor_addons():
    conn = get_db_connection()
    addons = conn.execute(
        "SELECT a.*, t.title as trip_title FROM addons a LEFT JOIN trips t ON a.trip_id=t.id WHERE a.vendor_id=?",
        (session['user_id'],)).fetchall()
    trips = conn.execute("SELECT id, title FROM trips").fetchall()
    vp = conn.execute("SELECT * FROM vendor_profiles WHERE user_id=?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('vendor_addons.html', addons=addons, trips=trips, vendor_profile=vp)


@app.route('/vendor/addons/add', methods=['POST'])
@login_required
@vendor_required
def add_vendor_addon():
    conn = get_db_connection()
    vp = conn.execute("SELECT * FROM vendor_profiles WHERE user_id=?", (session['user_id'],)).fetchone()
    if not vp or not vp['verified']:
        conn.close()
        flash('Your account must be verified to add addons.', 'danger')
        return redirect(url_for('vendor_addons'))
    trip_id = request.form.get('trip_id')
    addon_type = request.form.get('addon_type', 'hotel')
    title = request.form.get('title', '').strip()
    price = int(request.form.get('price', 0))
    description = request.form.get('description', '').strip()
    conn.execute("INSERT INTO addons (trip_id, vendor_id, addon_type, title, price, description) VALUES (?,?,?,?,?,?)",
                 (trip_id, session['user_id'], addon_type, title, price, description))
    conn.commit()
    conn.close()
    flash('Addon added!', 'success')
    return redirect(url_for('vendor_addons'))


@app.route('/vendor/addons/delete/<int:addon_id>', methods=['POST'])
@login_required
@vendor_required
def delete_vendor_addon(addon_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM addons WHERE id=? AND vendor_id=?", (addon_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Addon deleted.', 'success')
    return redirect(url_for('vendor_addons'))


# ── ADMIN ROUTES ─────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    conn = get_db_connection()
    # Stats
    stats = {
        'total_users': conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'confirmed_bookings': conn.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'").fetchone()[0],
        'total_revenue': conn.execute("SELECT COALESCE(SUM(total_price),0) FROM bookings WHERE status='confirmed'").fetchone()[0],
        'total_vendors': conn.execute("SELECT COUNT(*) FROM vendor_profiles").fetchone()[0],
        'total_posts': conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        'total_events': conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }
    all_trips = [dict(row) for row in conn.execute("SELECT * FROM trips").fetchall()]
    all_events = [dict(row) for row in conn.execute("SELECT * FROM events").fetchall()]
    all_upcoming_events = [dict(row) for row in conn.execute("SELECT * FROM upcoming_events ORDER BY event_date ASC").fetchall()]
    all_users = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()]
    all_bookings = [dict(row) for row in conn.execute(
        """SELECT b.*, u.name as user_name, u.email as user_email,
           COALESCE(t.title, e.title,'Unknown') as trip_title
           FROM bookings b
           LEFT JOIN users u ON b.user_id=u.id
           LEFT JOIN trips t ON b.trip_id=t.id AND b.booking_type='trip'
           LEFT JOIN events e ON b.trip_id=e.id AND b.booking_type='event'
           ORDER BY b.id DESC""").fetchall()]
    bookings = all_bookings[:10]
    all_quests = [dict(row) for row in conn.execute(
        "SELECT q.*, t.title as trip_name FROM quests q LEFT JOIN trips t ON q.trip_id=t.id").fetchall()]
    quest_feed = [dict(row) for row in conn.execute(
        """SELECT uq.*, q.title as quest_title, u.name as user_name, b.trip_id
           FROM user_quests uq
           JOIN quests q ON uq.quest_id=q.id
           JOIN bookings b ON uq.booking_id=b.id
           JOIN users u ON b.user_id=u.id
           WHERE uq.status='pending'""").fetchall()]
    vendors = [dict(row) for row in conn.execute(
        "SELECT vp.*, u.name as owner_name, u.email as owner_email FROM vendor_profiles vp JOIN users u ON vp.user_id=u.id").fetchall()]
    community_posts = [dict(row) for row in conn.execute(
        "SELECT p.*, u.name as author FROM posts p JOIN users u ON p.user_id=u.id ORDER BY p.timestamp DESC").fetchall()]
    inbox = [dict(row) for row in conn.execute("SELECT * FROM contact_messages ORDER BY created_at DESC").fetchall()]
    all_pages = [dict(row) for row in conn.execute("SELECT * FROM page_content ORDER BY page_name").fetchall()]
    all_shop_orders = [dict(row) for row in conn.execute(
        """SELECT so.*, u.name as user_name, u.email as user_email,
           GROUP_CONCAT(m.name, ', ') as item_names
           FROM shop_orders so
           LEFT JOIN users u ON so.user_id=u.id
           LEFT JOIN shop_order_items soi ON so.id=soi.order_id
           LEFT JOIN merchandise m ON soi.item_id=m.id
           GROUP BY so.id ORDER BY so.id DESC""").fetchall()]
    all_subscriptions = [dict(row) for row in conn.execute(
        "SELECT s.*, u.name as user_name, u.email as user_email FROM subscriptions s JOIN users u ON s.user_id=u.id").fetchall()]
    all_shop_items = [dict(row) for row in conn.execute("SELECT * FROM merchandise ORDER BY id DESC").fetchall()]
    settings = dict(conn.execute("SELECT * FROM site_settings WHERE id=1").fetchone())
    all_users_list = [dict(row) for row in conn.execute("SELECT id, title FROM trips").fetchall()]
    # New feature stats
    admin_pending_reviews = conn.execute("SELECT COUNT(*) FROM activity_submission WHERE status='pending'").fetchone()[0]
    admin_total_points = conn.execute("SELECT COALESCE(SUM(points_awarded),0) FROM activity_submission WHERE status='approved'").fetchone()[0]
    conn.close()
    return render_template('admin.html', stats=stats, all_trips=all_trips, all_events=all_events,
                           all_upcoming_events=all_upcoming_events,
                           all_users=all_users, all_bookings=all_bookings, bookings=bookings,
                           all_quests=all_quests, quest_feed=quest_feed, vendors=vendors,
                           community_posts=community_posts, inbox=inbox, all_pages=all_pages,
                           all_shop_orders=all_shop_orders, all_subscriptions=all_subscriptions,
                           all_shop_items=all_shop_items, settings=settings,
                           trips_list=all_trips, admin_pending_reviews=admin_pending_reviews,
                           admin_total_points=admin_total_points)


# ADMIN - TRIPS
@app.route('/admin/trip/add', methods=['POST'])
@login_required
@admin_required
def admin_add_trip():
    title = request.form.get('title', '').strip()
    trip_id = slugify(title)
    # Check for duplicate
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM trips WHERE id=?", (trip_id,)).fetchone()
    if existing:
        trip_id = f"{trip_id}-{uuid.uuid4().hex[:4]}"
    conn.execute(
        "INSERT INTO trips (id,title,price,duration,image_url,category,description,location,difficulty,itinerary,highlights) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (trip_id, title, int(request.form.get('price', 0)), request.form.get('duration', ''),
         request.form.get('image_url', ''), request.form.get('category', ''),
         request.form.get('description', ''), request.form.get('location', 'India'),
         request.form.get('difficulty', 'Moderate'), '[]', request.form.get('highlights', '')))
    conn.commit()
    conn.close()
    flash('Trip added!', 'success')
    return redirect(url_for('admin_panel') + '#trips')


@app.route('/admin/trip/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_trip():
    trip_id = request.form.get('trip_id')
    conn = get_db_connection()
    conn.execute(
        "UPDATE trips SET title=?,price=?,duration=?,image_url=?,category=?,description=?,location=?,difficulty=?,highlights=? WHERE id=?",
        (request.form.get('title'), int(request.form.get('price', 0)), request.form.get('duration'),
         request.form.get('image_url'), request.form.get('category'), request.form.get('description'),
         request.form.get('location'), request.form.get('difficulty'), request.form.get('highlights'),
         trip_id))
    conn.commit()
    conn.close()
    flash('Trip updated!', 'success')
    return redirect(url_for('admin_panel') + '#trips')


@app.route('/admin/trip/delete/<trip_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_trip(trip_id):
    conn = get_db_connection()
    active = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE trip_id=? AND status NOT IN ('cancelled')", (trip_id,)).fetchone()[0]
    if active > 0:
        conn.close()
        flash('Cannot delete trip with active bookings.', 'danger')
        return redirect(url_for('admin_panel') + '#trips')
    try:
        conn.execute("DELETE FROM quests WHERE trip_id=?", (trip_id,))
        conn.execute("DELETE FROM addons WHERE trip_id=?", (trip_id,))
        conn.execute("DELETE FROM trip_batches WHERE trip_id=?", (trip_id,))
        conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))
        conn.commit()
        flash('Trip deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    conn.close()
    return redirect(url_for('admin_panel') + '#trips')


@app.route('/admin/trip/<trip_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_trip_page(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('admin_panel') + '#trips')
    if request.method == 'POST':
        conn.execute(
            "UPDATE trips SET title=?,price=?,duration=?,image_url=?,category=?,description=?,location=?,difficulty=?,highlights=? WHERE id=?",
            (request.form.get('title'), int(request.form.get('price', 0)),
             request.form.get('duration'), request.form.get('image_url'),
             request.form.get('category'), request.form.get('description'),
             request.form.get('location'), request.form.get('difficulty'),
             request.form.get('highlights'), trip_id))
        conn.commit()
        conn.close()
        flash('Trip updated!', 'success')
        return redirect(url_for('admin_panel') + '#trips')
    conn.close()
    return render_template('admin/edit/trip.html', trip=dict(trip))


@app.route('/admin/trip/itinerary/<trip_id>')
@login_required
@admin_required
def admin_trip_itinerary(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    conn.close()
    if not trip:
        return redirect(url_for('admin_panel'))
    try:
        itinerary = json.loads(trip['itinerary'] or '[]')
    except Exception:
        itinerary = []
    
    # Add day_number to items that don't have it
    needs_update = False
    for i, day in enumerate(itinerary):
        if 'day_number' not in day:
            day['day_number'] = i + 1
            needs_update = True
        if 'id' not in day:
            day['id'] = i + 1
            needs_update = True
    
    # Save back if we added missing fields
    if needs_update:
        conn = get_db_connection()
        conn.execute("UPDATE trips SET itinerary=? WHERE id=?", (json.dumps(itinerary), trip_id))
        conn.commit()
        conn.close()
    
    return render_template('admin_itinerary_editor.html', trip=trip, itinerary=itinerary)


@app.route('/admin/trip/itinerary/update', methods=['POST'])
@login_required
@admin_required
def admin_update_itinerary():
    trip_id = request.form.get('trip_id')
    days_raw = request.form.getlist('day[]')
    titles_raw = request.form.getlist('title[]')
    descs_raw = request.form.getlist('description[]')
    itinerary = []
    for i, (d, t, desc) in enumerate(zip(days_raw, titles_raw, descs_raw)):
        itinerary.append({'day': int(d) if d.isdigit() else i+1, 'title': t, 'description': desc})
    conn = get_db_connection()
    conn.execute("UPDATE trips SET itinerary=? WHERE id=?", (json.dumps(itinerary), trip_id))
    conn.commit()
    conn.close()
    flash('Itinerary updated!', 'success')
    return redirect(url_for('admin_trip_itinerary', trip_id=trip_id))


@app.route('/admin/trip/itinerary/add', methods=['POST'])
@login_required
@admin_required
def admin_add_itinerary_day():
    trip_id = request.form.get('trip_id')
    day_number = request.form.get('day_number')
    title = request.form.get('title')
    description = request.form.get('description')
    meals = request.form.get('meals', '')
    accommodation = request.form.get('accommodation', '')
    
    conn = get_db_connection()
    trip = conn.execute("SELECT itinerary FROM trips WHERE id=?", (trip_id,)).fetchone()
    try:
        itinerary = json.loads(trip['itinerary'] or '[]')
    except Exception:
        itinerary = []
    
    # Generate a unique ID for the day
    day_id = len(itinerary) + 1
    itinerary.append({
        'id': day_id,
        'day_number': int(day_number) if day_number else len(itinerary) + 1,
        'title': title,
        'description': description,
        'meals': meals,
        'accommodation': accommodation
    })
    
    conn.execute("UPDATE trips SET itinerary=? WHERE id=?", (json.dumps(itinerary), trip_id))
    conn.commit()
    conn.close()
    flash('Day added to itinerary!', 'success')
    return redirect(url_for('admin_trip_itinerary', trip_id=trip_id))


@app.route('/admin/trip/itinerary/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_itinerary_day():
    trip_id = request.form.get('trip_id')
    day_id = request.form.get('day_id')
    conn = get_db_connection()
    trip = conn.execute("SELECT itinerary FROM trips WHERE id=?", (trip_id,)).fetchone()
    try:
        itinerary = json.loads(trip['itinerary'] or '[]')
    except Exception:
        itinerary = []
    
    # Remove the day with the matching day_number (day_id contains day_number)
    if day_id:
        itinerary = [day for day in itinerary if str(day.get('day_number')) != str(day_id)]
    
    conn.execute("UPDATE trips SET itinerary=? WHERE id=?", (json.dumps(itinerary), trip_id))
    conn.commit()
    conn.close()
    flash('Day deleted from itinerary!', 'success')
    return redirect(url_for('admin_trip_itinerary', trip_id=trip_id))


@app.route('/admin/trip/itinerary/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_itinerary_day():
    trip_id = request.form.get('trip_id')
    original_day_number = request.form.get('original_day_number')
    day_number = request.form.get('day_number')
    title = request.form.get('title')
    description = request.form.get('description')
    meals = request.form.get('meals', '')
    accommodation = request.form.get('accommodation', '')
    
    conn = get_db_connection()
    trip = conn.execute("SELECT itinerary FROM trips WHERE id=?", (trip_id,)).fetchone()
    try:
        itinerary = json.loads(trip['itinerary'] or '[]')
    except Exception:
        itinerary = []
    
    # Find and update the day with the matching original day_number
    if original_day_number:
        for day in itinerary:
            if str(day.get('day_number')) == str(original_day_number):
                day['day_number'] = int(day_number) if day_number else day.get('day_number')
                day['title'] = title
                day['description'] = description
                day['meals'] = meals
                day['accommodation'] = accommodation
                break
    
    conn.execute("UPDATE trips SET itinerary=? WHERE id=?", (json.dumps(itinerary), trip_id))
    conn.commit()
    conn.close()
    flash('Day updated!', 'success')
    return redirect(url_for('admin_trip_itinerary', trip_id=trip_id))


@app.route('/admin/trip/batches/<trip_id>')
@login_required
@admin_required
def admin_trip_batches(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    batches = conn.execute("SELECT * FROM trip_batches WHERE trip_id=? ORDER BY batch_date", (trip_id,)).fetchall()
    conn.close()
    return render_template('admin_batches.html', trip=trip, batches=batches)


@app.route('/admin/trip/batches/add', methods=['POST'])
@login_required
@admin_required
def admin_add_batch():
    trip_id = request.form.get('trip_id')
    batch_date = request.form.get('batch_date')
    min_req = int(request.form.get('min_required', 6))
    max_allowed = int(request.form.get('max_allowed', 16))
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO trip_batches (trip_id, batch_date, min_required, max_allowed, status) VALUES (?,?,?,?,'pending')",
            (trip_id, batch_date, min_req, max_allowed))
        conn.commit()
        flash('Batch added!', 'success')
    except Exception:
        flash('Batch date already exists for this trip.', 'warning')
    conn.close()
    return redirect(url_for('admin_wb_trip_batches', trip_id=trip_id))


@app.route('/admin/trip/batches/delete/<int:batch_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_batch(batch_id):
    conn = get_db_connection()
    batch = conn.execute("SELECT * FROM trip_batches WHERE id=?", (batch_id,)).fetchone()
    if batch and batch['current_bookings'] > 0:
        conn.close()
        flash('Cannot delete batch with active bookings.', 'danger')
        return redirect(url_for('admin_wb_trip_batches', trip_id=batch['trip_id']))
    trip_id = batch['trip_id'] if batch else ''
    conn.execute("DELETE FROM trip_batches WHERE id=?", (batch_id,))
    conn.commit()
    conn.close()
    flash('Batch deleted.', 'success')
    return redirect(url_for('admin_wb_trip_batches', trip_id=trip_id))


# ADMIN - EVENTS
@app.route('/admin/events/add', methods=['POST'])
@login_required
@admin_required
def admin_add_event():
    title = request.form.get('title', '').strip()
    event_id = slugify(title)
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
    if existing:
        event_id = f"{event_id}-{uuid.uuid4().hex[:4]}"
    conn.execute(
        "INSERT INTO events (id,title,price,duration,image_url,category,description,location,event_date) VALUES (?,?,?,?,?,?,?,?,?)",
        (event_id, title, int(request.form.get('price', 0)), request.form.get('duration', '1 Day'),
         request.form.get('image_url', ''), request.form.get('category', ''),
         request.form.get('description', ''), request.form.get('location', ''),
         request.form.get('event_date', '')))
    conn.commit()
    conn.close()
    flash('Event added!', 'success')
    return redirect(url_for('admin_panel') + '#events')


@app.route('/admin/events/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_event():
    event_id = request.form.get('event_id')
    conn = get_db_connection()
    conn.execute(
        "UPDATE events SET title=?,price=?,duration=?,image_url=?,category=?,description=?,location=?,event_date=? WHERE id=?",
        (request.form.get('title'), int(request.form.get('price', 0)), request.form.get('duration'),
         request.form.get('image_url'), request.form.get('category'), request.form.get('description'),
         request.form.get('location'), request.form.get('event_date'), event_id))
    conn.commit()
    conn.close()
    flash('Event updated!', 'success')
    return redirect(url_for('admin_panel') + '#events')


@app.route('/admin/events/delete/<event_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_event(event_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    flash('Event deleted.', 'success')
    return redirect(url_for('admin_panel') + '#events')


# ── UPCOMING EVENTS CRUD ───────────────────────────────────────────
@app.route('/admin/upcoming_events/add', methods=['POST'])
@login_required
@admin_required
def admin_add_upcoming_event():
    title = request.form.get('title', '').strip()
    event_id = slugify(title)
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM upcoming_events WHERE id=?", (event_id,)).fetchone()
    if existing:
        event_id = f"{event_id}-{uuid.uuid4().hex[:4]}"
    
    # Handle image upload
    image_url = request.form.get('image_url', '')
    if 'image_file' in request.files and request.files['image_file'].filename:
        file = request.files['image_file']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{event_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f"/static/uploads/{filename}"
    
    conn.execute(
        "INSERT INTO upcoming_events (id,title,description,image_url,event_date,price,location,category) VALUES (?,?,?,?,?,?,?,?)",
        (event_id, title, request.form.get('description', ''), image_url,
         request.form.get('event_date', ''), int(request.form.get('price', 0)),
         request.form.get('location', ''), request.form.get('category', '')))
    conn.commit()
    conn.close()
    flash('Upcoming event added!', 'success')
    return redirect(url_for('admin_panel') + '#upcoming_events')


@app.route('/admin/upcoming_event/<event_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_upcoming_event_page(event_id):
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM upcoming_events WHERE id=?", (event_id,)).fetchone()
    conn.close()
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('admin_panel') + '#upcoming_events')
    
    if request.method == 'POST':
        # Handle image upload
        image_url = request.form.get('image_url', event['image_url'])
        if 'image_file' in request.files and request.files['image_file'].filename:
            file = request.files['image_file']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{event_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f"/static/uploads/{filename}"
        
        conn = get_db_connection()
        conn.execute(
            "UPDATE upcoming_events SET title=?,description=?,image_url=?,event_date=?,price=?,location=?,category=? WHERE id=?",
            (request.form.get('title'), request.form.get('description'), image_url,
             request.form.get('event_date'), int(request.form.get('price', 0)),
             request.form.get('location'), request.form.get('category'), event_id))
        conn.commit()
        conn.close()
        flash('Upcoming event updated!', 'success')
        return redirect(url_for('admin_panel') + '#upcoming_events')
    
    return render_template('admin/edit/upcoming_event.html', event=dict(event))


@app.route('/admin/upcoming_events/delete/<event_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_upcoming_event(event_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM upcoming_events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    flash('Upcoming event deleted.', 'success')
    return redirect(url_for('admin_panel') + '#upcoming_events')


@app.route('/admin/event/<event_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_event_page(event_id):
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        conn.close()
        flash('Event not found.', 'danger')
        return redirect(url_for('admin_panel') + '#events')
    if request.method == 'POST':
        conn.execute(
            "UPDATE events SET title=?,price=?,duration=?,image_url=?,category=?,description=?,location=?,event_date=? WHERE id=?",
            (request.form.get('title'), int(request.form.get('price', 0)),
             request.form.get('duration'), request.form.get('image_url'),
             request.form.get('category'), request.form.get('description'),
             request.form.get('location'), request.form.get('event_date'), event_id))
        conn.commit()
        conn.close()
        flash('Event updated!', 'success')
        return redirect(url_for('admin_panel') + '#events')
    conn.close()
    return render_template('admin/edit/event.html', event=dict(event))


# ADMIN - USERS
@app.route('/admin/user/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_user():
    user_id = request.form.get('user_id')
    email = request.form.get('email', '').strip()
    role = request.form.get('role', 'traveler')
    conn = get_db_connection()
    user = conn.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
    if user and user['email'] in ADMIN_EMAILS and role != 'admin':
        conn.close()
        flash('Cannot demote a primary admin email.', 'danger')
        return redirect(url_for('admin_panel') + '#users')
    conn.execute("UPDATE users SET name=?, email=?, role=? WHERE id=?",
                 (request.form.get('name'), email, role, user_id))
    conn.commit()
    conn.close()
    flash('User updated!', 'success')
    return redirect(url_for('admin_panel') + '#users')


@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
    if user and user['email'] in ADMIN_EMAILS:
        conn.close()
        flash('Cannot delete admin account.', 'danger')
        return redirect(url_for('admin_panel') + '#users')
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted.', 'success')
    return redirect(url_for('admin_panel') + '#users')


@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user_page(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin_panel') + '#users')
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'traveler')
        if user['email'] in ADMIN_EMAILS and role != 'admin':
            conn.close()
            flash('Cannot demote a primary admin email.', 'danger')
            return redirect(url_for('admin_edit_user_page', user_id=user_id))
        conn.execute("UPDATE users SET name=?, email=?, role=?, phone=? WHERE id=?",
                     (request.form.get('name'), email, role,
                      request.form.get('phone', ''), user_id))
        conn.commit()
        conn.close()
        flash('User updated!', 'success')
        return redirect(url_for('admin_panel') + '#users')
    conn.close()
    return render_template('admin/edit/user.html', user=dict(user))


# ADMIN - BOOKINGS
@app.route('/admin/booking/status', methods=['POST'])
@login_required
@admin_required
def admin_booking_status():
    booking_id = request.form.get('booking_id')
    status = request.form.get('status')
    conn = get_db_connection()
    conn.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
    conn.commit()
    conn.close()
    flash('Booking status updated!', 'success')
    return redirect(url_for('admin_panel') + '#bookings')


# ADMIN - QUESTS
@app.route('/admin/quest/add', methods=['POST'])
@login_required
@admin_required
def admin_add_quest():
    conn = get_db_connection()
    conn.execute("INSERT INTO quests (trip_id, title, points, icon) VALUES (?,?,?,?)",
                 (request.form.get('trip_id'), request.form.get('title'),
                  int(request.form.get('points', 50)), request.form.get('icon', 'fa-solid fa-star')))
    conn.commit()
    conn.close()
    flash('Quest added!', 'success')
    return redirect(url_for('admin_panel') + '#quests')


@app.route('/admin/quest/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_quest():
    conn = get_db_connection()
    conn.execute("UPDATE quests SET title=?, points=?, icon=? WHERE id=?",
                 (request.form.get('title'), int(request.form.get('points', 50)),
                  request.form.get('icon'), request.form.get('quest_id')))
    conn.commit()
    conn.close()
    flash('Quest updated!', 'success')
    return redirect(url_for('admin_panel') + '#quests')


@app.route('/admin/quest/delete/<int:quest_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_quest(quest_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM user_quests WHERE quest_id=?", (quest_id,))
    conn.execute("DELETE FROM quests WHERE id=?", (quest_id,))
    conn.commit()
    conn.close()
    flash('Quest deleted.', 'success')
    return redirect(url_for('admin_panel') + '#quests')


@app.route('/admin/quest/<int:quest_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_quest_page(quest_id):
    conn = get_db_connection()
    quest = conn.execute(
        "SELECT q.*, t.title as trip_name FROM quests q LEFT JOIN trips t ON q.trip_id=t.id WHERE q.id=?",
        (quest_id,)).fetchone()
    if not quest:
        conn.close()
        flash('Quest not found.', 'danger')
        return redirect(url_for('admin_panel') + '#quests')
    if request.method == 'POST':
        conn.execute("UPDATE quests SET title=?, points=?, icon=? WHERE id=?",
                     (request.form.get('title'), int(request.form.get('points', 50)),
                      request.form.get('icon', 'fa-solid fa-star'), quest_id))
        conn.commit()
        conn.close()
        flash('Quest updated!', 'success')
        return redirect(url_for('admin_panel') + '#quests')
    conn.close()
    return render_template('admin/edit/quest.html', quest=dict(quest))


@app.route('/admin/quest/toggle/<int:quest_id>', methods=['POST'])
@login_required
@admin_required
def toggle_quest(quest_id):
    conn = get_db_connection()
    q = conn.execute("SELECT * FROM quests WHERE id=?", (quest_id,)).fetchone()
    if q:
        new_status = 0 if q['is_active'] else 1
        conn.execute("UPDATE quests SET is_active=? WHERE id=?", (new_status, quest_id))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_panel') + '#quests')


@app.route('/admin/shop/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_shop():
    conn = get_db_connection()
    settings = dict(conn.execute("SELECT * FROM site_settings WHERE id=1").fetchone())
    new_status = 0 if settings.get('shop_active') else 1
    conn.execute("UPDATE site_settings SET shop_active=? WHERE id=1", (new_status,))
    conn.commit()
    conn.close()
    flash(f"Shop {'activated' if new_status else 'deactivated (Launching Soon mode)'}", "info")
    return redirect(url_for('admin_panel') + '#settings')


@app.route('/admin/quest/action', methods=['POST'])
@login_required
@admin_required
def admin_quest_action():
    uq_id = request.form.get('uq_id')
    action = request.form.get('action')
    status = 'approved' if action == 'approve' else 'rejected'
    conn = get_db_connection()
    conn.execute("UPDATE user_quests SET status=? WHERE id=?", (status, uq_id))
    conn.commit()
    conn.close()
    flash(f'Quest {status}!', 'success')
    return redirect(url_for('admin_panel') + '#quests')


# ADMIN - VENDORS
@app.route('/admin/vendor/verify/<int:vendor_id>', methods=['POST'])
@login_required
@admin_required
def admin_verify_vendor(vendor_id):
    conn = get_db_connection()
    conn.execute("UPDATE vendor_profiles SET verified=1 WHERE id=?", (vendor_id,))
    conn.commit()
    conn.close()
    flash('Vendor verified!', 'success')
    return redirect(url_for('admin_panel') + '#partners')


@app.route('/admin/vendor/unverify/<int:vendor_id>', methods=['POST'])
@login_required
@admin_required
def admin_unverify_vendor(vendor_id):
    conn = get_db_connection()
    conn.execute("UPDATE vendor_profiles SET verified=0 WHERE id=?", (vendor_id,))
    conn.commit()
    conn.close()
    flash('Vendor unverified.', 'success')
    return redirect(url_for('admin_panel') + '#partners')


# ADMIN - COMMUNITY
@app.route('/admin/delete_post/<int:post_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_post(post_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()
    flash('Post deleted.', 'success')
    return redirect(url_for('admin_panel') + '#community')


# ADMIN - SHOP
@app.route('/admin/shop/item/add', methods=['POST'])
@login_required
@admin_required
def admin_add_shop_item():
    image_url = request.form.get('image_url', '').strip()
    if 'image' in request.files:
        f = request.files['image']
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            image_url = url_for('static', filename=f'uploads/{unique_name}')
    conn = get_db_connection()
    conn.execute("INSERT INTO merchandise (name, description, price, stock, category, image_url) VALUES (?,?,?,?,?,?)",
                 (request.form.get('name'), request.form.get('description'),
                  int(request.form.get('price', 0)), int(request.form.get('stock', 0)),
                  request.form.get('category'), image_url))
    conn.commit()
    conn.close()
    flash('Shop item added!', 'success')
    return redirect(url_for('admin_panel') + '#shop_items')


@app.route('/admin/shop/item/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_shop_item():
    item_id = request.form.get('item_id')
    image_url = request.form.get('image_url', '').strip()
    if 'image' in request.files:
        f = request.files['image']
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            image_url = url_for('static', filename=f'uploads/{unique_name}')
    conn = get_db_connection()
    conn.execute("UPDATE merchandise SET name=?, description=?, price=?, stock=?, category=?, image_url=? WHERE id=?",
                 (request.form.get('name'), request.form.get('description'),
                  int(request.form.get('price', 0)), int(request.form.get('stock', 0)),
                  request.form.get('category'), image_url, item_id))
    conn.commit()
    conn.close()
    flash('Shop item updated!', 'success')
    return redirect(url_for('admin_panel') + '#shop_items')


@app.route('/admin/shop/item/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_shop_item(item_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM merchandise WHERE id=?", (item_id,))
        conn.commit()
        flash('Item deleted.', 'success')
    except Exception:
        flash('Cannot delete item linked to orders.', 'danger')
    conn.close()
    return redirect(url_for('admin_panel') + '#shop_items')


@app.route('/admin/shop/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_shop_item_page(item_id):
    conn = get_db_connection()
    item = conn.execute("SELECT * FROM merchandise WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash('Item not found.', 'danger')
        return redirect(url_for('admin_panel') + '#shop_items')
    if request.method == 'POST':
        image_url = request.form.get('image_url', '').strip()
        if 'image' in request.files:
            f = request.files['image']
            if f and f.filename and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                unique_name = f"{uuid.uuid4().hex}_{filename}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                image_url = url_for('static', filename=f'uploads/{unique_name}')
        conn.execute(
            "UPDATE merchandise SET name=?,description=?,price=?,stock=?,category=?,image_url=? WHERE id=?",
            (request.form.get('name'), request.form.get('description'),
             int(request.form.get('price', 0)), int(request.form.get('stock', 0)),
             request.form.get('category'), image_url, item_id))
        conn.commit()
        conn.close()
        flash('Shop item updated!', 'success')
        return redirect(url_for('admin_panel') + '#shop_items')
    conn.close()
    return render_template('admin/edit/shop_item.html', item=dict(item))


@app.route('/admin/shop/order/status', methods=['POST'])
@login_required
@admin_required
def admin_shop_order_status():
    order_id = request.form.get('order_id')
    status = request.form.get('status')
    conn = get_db_connection()
    conn.execute("UPDATE shop_orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()
    flash('Order status updated!', 'success')
    return redirect(url_for('admin_panel') + '#shop_orders')


# ADMIN - SUBSCRIPTIONS
@app.route('/admin/subscription/toggle/<int:sub_id>', methods=['POST'])
@login_required
@admin_required
def admin_toggle_subscription(sub_id):
    conn = get_db_connection()
    sub = conn.execute("SELECT status FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    new_status = 'inactive' if sub and sub['status'] == 'active' else 'active'
    conn.execute("UPDATE subscriptions SET status=? WHERE id=?", (new_status, sub_id))
    conn.commit()
    conn.close()
    flash(f'Subscription {new_status}.', 'success')
    return redirect(url_for('admin_panel') + '#explorer_pass')


# ADMIN - SETTINGS
@app.route('/admin/settings/update', methods=['POST'])
@login_required
@admin_required
def admin_settings_update():
    conn = get_db_connection()
    conn.execute("""UPDATE site_settings SET
        site_title=?, hero_tagline=?, hero_subtext=?, logo_url=?,
        email=?, phone=?, address=?, instagram=?, twitter=?,
        facebook=?, youtube=?, working_hours=?, year_established=?
        WHERE id=1""",
        (request.form.get('site_title'), request.form.get('hero_tagline'),
         request.form.get('hero_subtext'), request.form.get('logo_url'),
         request.form.get('email'), request.form.get('phone'), request.form.get('address'),
         request.form.get('instagram'), request.form.get('twitter'),
         request.form.get('facebook'), request.form.get('youtube'),
         request.form.get('working_hours'), int(request.form.get('year_established', 2022))))
    conn.commit()
    conn.close()
    flash('Settings saved!', 'success')
    return redirect(url_for('admin_panel') + '#settings')


# ADMIN - PAGES
@app.route('/admin/pages/add', methods=['POST'])
@login_required
@admin_required
def admin_add_page():
    page_name = slugify(request.form.get('page_name', ''))
    title = request.form.get('title', '')
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO page_content (page_name, title, content) VALUES (?,?,?)",
                     (page_name, title, '<p>New page content.</p>'))
        conn.commit()
        flash('Page added!', 'success')
    except Exception:
        flash('Page with that name already exists.', 'danger')
    conn.close()
    return redirect(url_for('admin_panel') + '#pages')


@app.route('/admin/pages/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_page():
    page_id = request.form.get('page_id')
    conn = get_db_connection()
    conn.execute("UPDATE page_content SET title=?, content=? WHERE id=?",
                 (request.form.get('title'), request.form.get('content'), page_id))
    conn.commit()
    conn.close()
    flash('Page updated!', 'success')
    return redirect(url_for('admin_panel') + '#pages')


@app.route('/admin/pages/delete/<int:page_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_page(page_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM page_content WHERE id=?", (page_id,))
    conn.commit()
    conn.close()
    flash('Page deleted.', 'success')
    return redirect(url_for('admin_panel') + '#pages')


@app.route('/admin/page/edit/<page_name>')
@login_required
@admin_required
def admin_page_editor(page_name):
    conn = get_db_connection()
    page = conn.execute("SELECT * FROM page_content WHERE page_name=?", (page_name,)).fetchone()
    conn.close()
    if not page:
        flash('Page not found.', 'danger')
        return redirect(url_for('admin_panel') + '#pages')
    return render_template('admin_page_editor.html', page=dict(page))


@app.route('/admin/page/update', methods=['POST'])
@login_required
@admin_required
def admin_page_update():
    page_name = request.form.get('page_name')
    title = request.form.get('title')
    content = request.form.get('content')
    conn = get_db_connection()
    conn.execute("UPDATE page_content SET title=?, content=?, updated_at=CURRENT_TIMESTAMP WHERE page_name=?",
                 (title, content, page_name))
    conn.commit()
    conn.close()
    flash('Page content updated!', 'success')
    return redirect(url_for('admin_panel') + '#pages')


@app.route('/admin/shop')
@login_required
@admin_required
def admin_shop():
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM merchandise ORDER BY id DESC").fetchall()
    orders = conn.execute(
        """SELECT so.*, u.name as user_name FROM shop_orders so
           LEFT JOIN users u ON so.user_id=u.id ORDER BY so.id DESC""").fetchall()
    conn.close()
    return render_template('admin_shop.html', items=items, orders=orders)


@app.route('/admin/bookings')
@login_required
@admin_required
def admin_bookings():
    conn = get_db_connection()
    bookings = conn.execute(
        """SELECT b.*, u.name as user_name, COALESCE(t.title, e.title,'?') as trip_title
           FROM bookings b
           LEFT JOIN users u ON b.user_id=u.id
           LEFT JOIN trips t ON b.trip_id=t.id AND b.booking_type='trip'
           LEFT JOIN events e ON b.trip_id=e.id AND b.booking_type='event'
           ORDER BY b.id DESC""").fetchall()
    conn.close()
    return jsonify([dict(b) for b in bookings])


@app.route('/admin/batches', methods=['POST'])
@login_required
@admin_required
def admin_batches():
    trip_id = request.form.get('trip_id')
    conn = get_db_connection()
    batches = conn.execute("SELECT * FROM trip_batches WHERE trip_id=? ORDER BY batch_date", (trip_id,)).fetchall()
    conn.close()
    return jsonify([dict(b) for b in batches])


# ═══════════════════════════════════════════════════════════════════════════════
# ── NEW FEATURE: DB MIGRATION FOR NEW TABLES ───────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def migrate_new_features():
    """Create new tables and add new columns to existing tables."""
    conn = get_db_connection()
    try:
        # Add points to users
        try:
            conn.execute("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0")
        except Exception:
            pass
        # Add batch_id to bookings
        try:
            conn.execute("ALTER TABLE bookings ADD COLUMN wb_batch_id INTEGER REFERENCES trip_batch(id)")
        except Exception:
            pass
        # Add event_time to events
        try:
            conn.execute("ALTER TABLE events ADD COLUMN event_time TEXT DEFAULT ''")
        except Exception:
            pass

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS trip_batch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            batch_name TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            max_seats INTEGER DEFAULT 20,
            price_override REAL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        );

        CREATE TABLE IF NOT EXISTS batch_chat_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES trip_batch(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS event_chat_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS trip_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            activity_type TEXT DEFAULT 'photo',
            location_hint TEXT,
            points INTEGER DEFAULT 10,
            bonus_points INTEGER DEFAULT 5,
            is_active INTEGER DEFAULT 1,
            order_num INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        );

        CREATE TABLE IF NOT EXISTS activity_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            batch_id INTEGER,
            image_path TEXT,
            caption TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            reviewed_at DATETIME,
            reviewed_by INTEGER,
            points_awarded INTEGER DEFAULT 0,
            admin_note TEXT,
            FOREIGN KEY(activity_id) REFERENCES trip_activity(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reward (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            reward_type TEXT DEFAULT 'coupon',
            value TEXT,
            coupon_code TEXT,
            min_points INTEGER DEFAULT 0,
            trip_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reward_assignment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            batch_id INTEGER,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            FOREIGN KEY(reward_id) REFERENCES reward(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        conn.commit()
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

migrate_new_features()

# Create activity uploads directory
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'activities'), exist_ok=True)

ACTIVITY_ALLOWED = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4'}


def allowed_activity_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ACTIVITY_ALLOWED


def _is_confirmed_trip_booker(conn, user_id, trip_id):
    row = conn.execute(
        "SELECT id FROM bookings WHERE user_id=? AND trip_id=? AND status='confirmed' AND booking_type='trip'",
        (user_id, trip_id)).fetchone()
    return row is not None


def _is_confirmed_batch_booker(conn, user_id, batch_id):
    batch = conn.execute("SELECT trip_id FROM trip_batch WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        return False
    return _is_confirmed_trip_booker(conn, user_id, batch['trip_id'])


def _is_confirmed_event_booker(conn, user_id, event_id):
    row = conn.execute(
        "SELECT id FROM bookings WHERE user_id=? AND trip_id=? AND status='confirmed' AND booking_type='event'",
        (user_id, event_id)).fetchone()
    return row is not None


def _is_admin():
    return session.get('user_role') == 'admin' or session.get('user_email') in ADMIN_EMAILS


# ─── MY BOOKINGS ──────────────────────────────────────────────────────────────

@app.route('/my-bookings')
@login_required
def my_bookings():
    conn = get_db_connection()
    bookings = conn.execute(
        """SELECT b.*, COALESCE(t.title, e.title, '?') as trip_title,
           COALESCE(t.image_url, e.image_url) as trip_image,
           tb.batch_name, tb.start_date, tb.end_date
           FROM bookings b
           LEFT JOIN trips t ON b.trip_id=t.id AND b.booking_type='trip'
           LEFT JOIN events e ON b.trip_id=e.id AND b.booking_type='event'
           LEFT JOIN trip_batch tb ON b.wb_batch_id=tb.id
           WHERE b.user_id=? ORDER BY b.id DESC""",
        (session['user_id'],)).fetchall()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)


# ─── ADMIN: TRIP BATCHES (new system) ─────────────────────────────────────────

@app.route('/admin/trips/<trip_id>/batches')
@login_required
@admin_required
def admin_wb_trip_batches(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('admin_panel'))
    batches = conn.execute(
        "SELECT * FROM trip_batch WHERE trip_id=? ORDER BY start_date", (trip_id,)).fetchall()
    conn.close()
    return render_template('admin/batches/list.html', trip=dict(trip), batches=batches)


@app.route('/admin/trips/<trip_id>/wb-batches/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_wb_batch_new(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        batch_name = request.form.get('batch_name', '').strip()
        start_date = request.form.get('start_date', '')
        end_date = request.form.get('end_date', '')
        max_seats = int(request.form.get('max_seats', 20))
        price_override_raw = request.form.get('price_override', '').strip()
        price_override = float(price_override_raw) if price_override_raw else None
        conn.execute(
            "INSERT INTO trip_batch (trip_id, batch_name, start_date, end_date, max_seats, price_override, is_active) VALUES (?,?,?,?,?,?,1)",
            (trip_id, batch_name, start_date, end_date, max_seats, price_override))
        conn.commit()
        conn.close()
        flash('Batch created!', 'success')
        return redirect(url_for('admin_wb_trip_batches', trip_id=trip_id))
    conn.close()
    return render_template('admin/batches/form.html', trip=dict(trip), batch=None, action='new')


@app.route('/admin/wb-batches/<int:batch_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_wb_batch_edit(batch_id):
    conn = get_db_connection()
    batch = conn.execute("SELECT * FROM trip_batch WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        flash('Batch not found.', 'danger')
        return redirect(url_for('admin_panel'))
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (batch['trip_id'],)).fetchone()
    if request.method == 'POST':
        batch_name = request.form.get('batch_name', '').strip()
        start_date = request.form.get('start_date', '')
        end_date = request.form.get('end_date', '')
        max_seats = int(request.form.get('max_seats', 20))
        price_override_raw = request.form.get('price_override', '').strip()
        price_override = float(price_override_raw) if price_override_raw else None
        is_active = 1 if request.form.get('is_active') else 0
        conn.execute(
            "UPDATE trip_batch SET batch_name=?, start_date=?, end_date=?, max_seats=?, price_override=?, is_active=? WHERE id=?",
            (batch_name, start_date, end_date, max_seats, price_override, is_active, batch_id))
        conn.commit()
        conn.close()
        flash('Batch updated!', 'success')
        return redirect(url_for('admin_wb_trip_batches', trip_id=batch['trip_id']))
    conn.close()
    return render_template('admin/batches/form.html', trip=dict(trip), batch=dict(batch), action='edit')


@app.route('/admin/wb-batches/<int:batch_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_wb_batch_delete(batch_id):
    conn = get_db_connection()
    batch = conn.execute("SELECT * FROM trip_batch WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        flash('Batch not found.', 'danger')
        return redirect(url_for('admin_panel'))
    trip_id = batch['trip_id']
    linked = conn.execute(
        "SELECT id FROM bookings WHERE wb_batch_id=? AND status='confirmed'", (batch_id,)).fetchone()
    if linked:
        conn.close()
        flash('Cannot delete — has active bookings.', 'danger')
        return redirect(url_for('admin_wb_trip_batches', trip_id=trip_id))
    conn.execute("DELETE FROM trip_batch WHERE id=?", (batch_id,))
    conn.commit()
    conn.close()
    flash('Batch deleted.', 'success')
    return redirect(url_for('admin_wb_trip_batches', trip_id=trip_id))


# ─── GROUP CHAT: TRIP BATCHES ─────────────────────────────────────────────────

@app.route('/batch-chat/<int:batch_id>')
@login_required
def batch_chat(batch_id):
    conn = get_db_connection()
    batch = conn.execute(
        "SELECT tb.*, t.title as trip_title FROM trip_batch tb JOIN trips t ON tb.trip_id=t.id WHERE tb.id=?",
        (batch_id,)).fetchone()
    if not batch:
        conn.close()
        flash('Batch not found.', 'danger')
        return redirect(url_for('dashboard'))
    if not _is_admin() and not _is_confirmed_batch_booker(conn, session['user_id'], batch_id):
        conn.close()
        flash('Access denied — you need a confirmed booking for this batch.', 'danger')
        return redirect(url_for('dashboard'))
    messages = conn.execute(
        """SELECT bcm.*, u.name as sender_name FROM batch_chat_message bcm
           JOIN users u ON bcm.user_id=u.id
           WHERE bcm.batch_id=? ORDER BY bcm.sent_at ASC""", (batch_id,)).fetchall()
    travelers_bookings = conn.execute(
        """SELECT b.*, u.name as user_name FROM bookings b
           JOIN users u ON b.user_id=u.id
           WHERE b.wb_batch_id=? AND b.status='confirmed'""", (batch_id,)).fetchall()
    conn.close()
    return render_template('chat/batch_chat.html', batch=dict(batch), messages=messages,
                           travelers=travelers_bookings, current_user_id=session['user_id'])


@app.route('/batch-chat/<int:batch_id>/send', methods=['POST'])
@login_required
def send_batch_message(batch_id):
    conn = get_db_connection()
    batch = conn.execute("SELECT trip_id FROM trip_batch WHERE id=?", (batch_id,)).fetchone()
    if not batch or (not _is_admin() and not _is_confirmed_batch_booker(conn, session['user_id'], batch_id)):
        conn.close()
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    message = request.form.get('message', '').strip()
    if message:
        conn.execute(
            "INSERT INTO batch_chat_message (batch_id, user_id, message) VALUES (?,?,?)",
            (batch_id, session['user_id'], message))
        conn.commit()
    conn.close()
    return redirect(url_for('batch_chat', batch_id=batch_id))


# ─── GROUP CHAT: EVENTS ───────────────────────────────────────────────────────

@app.route('/event-chat/<event_id>')
@login_required
def event_chat(event_id):
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        conn.close()
        flash('Event not found.', 'danger')
        return redirect(url_for('events'))
    if not _is_admin() and not _is_confirmed_event_booker(conn, session['user_id'], event_id):
        conn.close()
        flash('Access denied — you need a confirmed booking for this event.', 'danger')
        return redirect(url_for('events'))
    messages = conn.execute(
        """SELECT ecm.*, u.name as sender_name FROM event_chat_message ecm
           JOIN users u ON ecm.user_id=u.id
           WHERE ecm.event_id=? ORDER BY ecm.sent_at ASC""", (event_id,)).fetchall()
    attendees = conn.execute(
        """SELECT b.*, u.name as user_name FROM bookings b
           JOIN users u ON b.user_id=u.id
           WHERE b.trip_id=? AND b.booking_type='event' AND b.status='confirmed'""",
        (event_id,)).fetchall()
    conn.close()
    return render_template('chat/event_chat.html', event=dict(event), messages=messages,
                           attendees=attendees, current_user_id=session['user_id'])


@app.route('/event-chat/<event_id>/send', methods=['POST'])
@login_required
def send_event_message(event_id):
    conn = get_db_connection()
    event = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
    if not event or (not _is_admin() and not _is_confirmed_event_booker(conn, session['user_id'], event_id)):
        conn.close()
        flash('Access denied.', 'danger')
        return redirect(url_for('events'))
    message = request.form.get('message', '').strip()
    if message:
        conn.execute(
            "INSERT INTO event_chat_message (event_id, user_id, message) VALUES (?,?,?)",
            (event_id, session['user_id'], message))
        conn.commit()
    conn.close()
    return redirect(url_for('event_chat', event_id=event_id))


# ─── ADVENTURE GAME: USER SIDE ────────────────────────────────────────────────

@app.route('/adventure/<trip_id>')
@login_required
def adventure_dashboard(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('trips'))
    if not _is_admin() and not _is_confirmed_trip_booker(conn, session['user_id'], trip_id):
        conn.close()
        flash('You need a confirmed booking to access Adventure Mode.', 'danger')
        return redirect(url_for('trip_details', trip_id=trip_id))
    activities = conn.execute(
        "SELECT * FROM trip_activity WHERE trip_id=? AND is_active=1 ORDER BY order_num", (trip_id,)).fetchall()
    my_subs_rows = conn.execute(
        "SELECT * FROM activity_submission WHERE user_id=? AND activity_id IN (SELECT id FROM trip_activity WHERE trip_id=?)",
        (session['user_id'], trip_id)).fetchall()
    my_submissions = {s['activity_id']: dict(s) for s in my_subs_rows}

    # Get user's batch (if any)
    my_booking = conn.execute(
        "SELECT wb_batch_id FROM bookings WHERE user_id=? AND trip_id=? AND status='confirmed' AND booking_type='trip' ORDER BY id DESC LIMIT 1",
        (session['user_id'], trip_id)).fetchone()
    my_batch_id = my_booking['wb_batch_id'] if my_booking else None

    # Build leaderboard
    leaderboard = []
    if my_batch_id:
        batch_members = conn.execute(
            """SELECT DISTINCT b.user_id, u.name FROM bookings b JOIN users u ON b.user_id=u.id
               WHERE b.wb_batch_id=? AND b.status='confirmed'""", (my_batch_id,)).fetchall()
        for m in batch_members:
            result = conn.execute(
                """SELECT COALESCE(SUM(asub.points_awarded),0) as total_pts,
                   COUNT(asub.id) as completed,
                   MAX(asub.submitted_at) as last_sub
                   FROM activity_submission asub
                   WHERE asub.user_id=? AND asub.status='approved'
                   AND asub.activity_id IN (SELECT id FROM trip_activity WHERE trip_id=?)""",
                (m['user_id'], trip_id)).fetchone()
            leaderboard.append({
                'user_id': m['user_id'],
                'name': m['name'],
                'points': result['total_pts'] or 0,
                'completed': result['completed'] or 0,
                'last_sub': result['last_sub'] or '9999'
            })
        leaderboard.sort(key=lambda x: (-x['points'], -x['completed'], x['last_sub']))

    # Current user points
    user_pts = conn.execute(
        """SELECT COALESCE(SUM(points_awarded),0) as pts FROM activity_submission
           WHERE user_id=? AND status='approved'
           AND activity_id IN (SELECT id FROM trip_activity WHERE trip_id=?)""",
        (session['user_id'], trip_id)).fetchone()
    user_total_points = user_pts['pts'] if user_pts else 0
    conn.close()
    return render_template('adventure/dashboard.html', trip=dict(trip), activities=activities,
                           my_submissions=my_submissions, leaderboard=leaderboard,
                           user_total_points=user_total_points, my_batch_id=my_batch_id,
                           current_user_id=session['user_id'])


@app.route('/adventure/submit/<int:activity_id>', methods=['POST'])
@login_required
def submit_activity(activity_id):
    conn = get_db_connection()
    activity = conn.execute("SELECT * FROM trip_activity WHERE id=?", (activity_id,)).fetchone()
    if not activity or not _is_confirmed_trip_booker(conn, session['user_id'], activity['trip_id']):
        conn.close()
        flash('Access denied.', 'danger')
        return redirect(url_for('trips'))
    existing = conn.execute(
        "SELECT id FROM activity_submission WHERE user_id=? AND activity_id=?",
        (session['user_id'], activity_id)).fetchone()
    if existing:
        conn.close()
        flash('Already submitted!', 'info')
        return redirect(url_for('adventure_dashboard', trip_id=activity['trip_id']))
    image_path = ''
    if 'photo' in request.files:
        f = request.files['photo']
        if f and allowed_activity_file(f.filename):
            filename = secure_filename(f.filename)
            unique_name = f"{session['user_id']}_{activity_id}_{uuid.uuid4().hex[:8]}_{filename}"
            save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'activities', unique_name)
            f.save(save_path)
            image_path = f'uploads/activities/{unique_name}'
    caption = request.form.get('caption', '').strip()
    batch_id = request.form.get('batch_id') or None
    conn.execute(
        "INSERT INTO activity_submission (activity_id, user_id, batch_id, image_path, caption, status) VALUES (?,?,?,?,?,?)",
        (activity_id, session['user_id'], batch_id, image_path, caption, 'pending'))
    conn.commit()
    conn.close()
    flash('Submitted! Waiting for admin approval 🎯', 'success')
    return redirect(url_for('adventure_dashboard', trip_id=activity['trip_id']))


# ─── ADMIN: ACTIVITIES ────────────────────────────────────────────────────────

@app.route('/admin/trips/<trip_id>/activities')
@login_required
@admin_required
def admin_activities(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('admin_panel'))
    activities = conn.execute(
        "SELECT * FROM trip_activity WHERE trip_id=? ORDER BY order_num", (trip_id,)).fetchall()
    conn.close()
    return render_template('admin/activities/list.html', trip=dict(trip), activities=activities)


@app.route('/admin/trips/<trip_id>/activities/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_activity_new(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'danger')
        return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        conn.execute(
            """INSERT INTO trip_activity (trip_id, title, description, activity_type, location_hint, points, bonus_points, order_num, is_active)
               VALUES (?,?,?,?,?,?,?,?,1)""",
            (trip_id, request.form.get('title'), request.form.get('description'),
             request.form.get('activity_type', 'photo'), request.form.get('location_hint', ''),
             int(request.form.get('points', 10)), int(request.form.get('bonus_points', 5)),
             int(request.form.get('order_num', 0))))
        conn.commit()
        conn.close()
        flash('Activity created!', 'success')
        return redirect(url_for('admin_activities', trip_id=trip_id))
    conn.close()
    return render_template('admin/activities/form.html', trip=dict(trip), activity=None, action='new')


@app.route('/admin/activities/<int:activity_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_activity_edit(activity_id):
    conn = get_db_connection()
    activity = conn.execute("SELECT * FROM trip_activity WHERE id=?", (activity_id,)).fetchone()
    if not activity:
        conn.close()
        flash('Activity not found.', 'danger')
        return redirect(url_for('admin_panel'))
    trip = conn.execute("SELECT * FROM trips WHERE id=?", (activity['trip_id'],)).fetchone()
    if request.method == 'POST':
        is_active = 1 if request.form.get('is_active') else 0
        conn.execute(
            """UPDATE trip_activity SET title=?, description=?, activity_type=?, location_hint=?,
               points=?, bonus_points=?, order_num=?, is_active=? WHERE id=?""",
            (request.form.get('title'), request.form.get('description'),
             request.form.get('activity_type', 'photo'), request.form.get('location_hint', ''),
             int(request.form.get('points', 10)), int(request.form.get('bonus_points', 5)),
             int(request.form.get('order_num', 0)), is_active, activity_id))
        conn.commit()
        conn.close()
        flash('Activity updated!', 'success')
        return redirect(url_for('admin_activities', trip_id=activity['trip_id']))
    conn.close()
    return render_template('admin/activities/form.html', trip=dict(trip), activity=dict(activity), action='edit')


@app.route('/admin/activities/<int:activity_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_activity_delete(activity_id):
    conn = get_db_connection()
    activity = conn.execute("SELECT * FROM trip_activity WHERE id=?", (activity_id,)).fetchone()
    if not activity:
        conn.close()
        flash('Activity not found.', 'danger')
        return redirect(url_for('admin_panel'))
    trip_id = activity['trip_id']
    linked = conn.execute("SELECT id FROM activity_submission WHERE activity_id=?", (activity_id,)).fetchone()
    if linked:
        conn.close()
        flash('Cannot delete — has submissions. Deactivate it instead.', 'danger')
        return redirect(url_for('admin_activities', trip_id=trip_id))
    conn.execute("DELETE FROM trip_activity WHERE id=?", (activity_id,))
    conn.commit()
    conn.close()
    flash('Activity deleted.', 'success')
    return redirect(url_for('admin_activities', trip_id=trip_id))


# ─── ADMIN: SUBMISSIONS ───────────────────────────────────────────────────────

@app.route('/admin/submissions')
@login_required
@admin_required
def admin_submissions():
    status_filter = request.args.get('status', 'pending')
    conn = get_db_connection()
    submissions = conn.execute(
        """SELECT asub.*, u.name as user_name, ta.title as activity_title,
           t.title as trip_title, tb.batch_name
           FROM activity_submission asub
           JOIN users u ON asub.user_id=u.id
           JOIN trip_activity ta ON asub.activity_id=ta.id
           JOIN trips t ON ta.trip_id=t.id
           LEFT JOIN trip_batch tb ON asub.batch_id=tb.id
           WHERE asub.status=?
           ORDER BY asub.submitted_at DESC""", (status_filter,)).fetchall()
    conn.close()
    return render_template('admin/submissions/list.html', submissions=submissions, status_filter=status_filter)


@app.route('/admin/submissions/<int:sub_id>/review', methods=['POST'])
@login_required
@admin_required
def admin_submission_review(sub_id):
    conn = get_db_connection()
    sub = conn.execute(
        "SELECT asub.*, ta.points, ta.bonus_points, ta.id as act_id FROM activity_submission asub JOIN trip_activity ta ON asub.activity_id=ta.id WHERE asub.id=?",
        (sub_id,)).fetchone()
    if not sub:
        conn.close()
        flash('Submission not found.', 'danger')
        return redirect(url_for('admin_submissions'))
    action = request.form.get('action')
    admin_note = request.form.get('admin_note', '')
    now = datetime.utcnow().isoformat()
    if action == 'approve':
        prior_count = conn.execute(
            "SELECT COUNT(*) FROM activity_submission WHERE activity_id=? AND status='approved' AND id!=?",
            (sub['act_id'], sub_id)).fetchone()[0]
        pts = sub['points'] + (sub['bonus_points'] if prior_count == 0 else 0)
        conn.execute(
            "UPDATE activity_submission SET status='approved', points_awarded=?, reviewed_at=?, reviewed_by=?, admin_note=? WHERE id=?",
            (pts, now, session['user_id'], admin_note, sub_id))
        conn.execute("UPDATE users SET points = COALESCE(points,0) + ? WHERE id=?",
                     (pts, sub['user_id']))
        conn.commit()
        user = conn.execute("SELECT name FROM users WHERE id=?", (sub['user_id'],)).fetchone()
        flash(f"{user['name']} approved — {pts} pts awarded", 'success')
    elif action == 'reject':
        conn.execute(
            "UPDATE activity_submission SET status='rejected', points_awarded=0, reviewed_at=?, reviewed_by=?, admin_note=? WHERE id=?",
            (now, session['user_id'], admin_note, sub_id))
        conn.commit()
        flash('Submission rejected.', 'info')
    conn.close()
    return redirect(url_for('admin_submissions') + '?status=pending')


# ─── ADMIN: REWARDS ───────────────────────────────────────────────────────────

@app.route('/admin/rewards')
@login_required
@admin_required
def admin_rewards():
    conn = get_db_connection()
    rewards = conn.execute("SELECT * FROM reward ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('admin/rewards/list.html', rewards=rewards)


@app.route('/admin/rewards/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_reward_new():
    conn = get_db_connection()
    trips = conn.execute("SELECT id, title FROM trips ORDER BY title").fetchall()
    if request.method == 'POST':
        import random, string
        coupon = 'WB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        trip_id = request.form.get('trip_id') or None
        conn.execute(
            """INSERT INTO reward (title, description, reward_type, value, min_points, trip_id, coupon_code, is_active)
               VALUES (?,?,?,?,?,?,?,1)""",
            (request.form.get('title'), request.form.get('description'),
             request.form.get('reward_type', 'coupon'), request.form.get('value', ''),
             int(request.form.get('min_points', 0)), trip_id, coupon))
        conn.commit()
        conn.close()
        flash('Reward created!', 'success')
        return redirect(url_for('admin_rewards'))
    conn.close()
    return render_template('admin/rewards/form.html', reward=None, trips=trips, action='new')


@app.route('/admin/rewards/<int:reward_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_reward_edit(reward_id):
    conn = get_db_connection()
    reward = conn.execute("SELECT * FROM reward WHERE id=?", (reward_id,)).fetchone()
    if not reward:
        conn.close()
        flash('Reward not found.', 'danger')
        return redirect(url_for('admin_rewards'))
    trips = conn.execute("SELECT id, title FROM trips ORDER BY title").fetchall()
    if request.method == 'POST':
        trip_id = request.form.get('trip_id') or None
        conn.execute(
            "UPDATE reward SET title=?, description=?, reward_type=?, value=?, min_points=?, trip_id=? WHERE id=?",
            (request.form.get('title'), request.form.get('description'),
             request.form.get('reward_type', 'coupon'), request.form.get('value', ''),
             int(request.form.get('min_points', 0)), trip_id, reward_id))
        conn.commit()
        conn.close()
        flash('Reward updated!', 'success')
        return redirect(url_for('admin_rewards'))
    conn.close()
    return render_template('admin/rewards/form.html', reward=dict(reward), trips=trips, action='edit')


@app.route('/admin/rewards/<int:reward_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_reward_toggle(reward_id):
    conn = get_db_connection()
    r = conn.execute("SELECT is_active FROM reward WHERE id=?", (reward_id,)).fetchone()
    new_val = 0 if r and r['is_active'] else 1
    conn.execute("UPDATE reward SET is_active=? WHERE id=?", (new_val, reward_id))
    conn.commit()
    conn.close()
    flash('Reward toggled.', 'success')
    return redirect(url_for('admin_rewards'))


@app.route('/admin/rewards/assign', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_reward_assign():
    conn = get_db_connection()
    if request.method == 'POST':
        reward_id = request.form.get('reward_id')
        user_id = request.form.get('user_id')
        batch_id = request.form.get('batch_id') or None
        reason = request.form.get('reason', '')
        conn.execute(
            "INSERT INTO reward_assignment (reward_id, user_id, batch_id, reason) VALUES (?,?,?,?)",
            (reward_id, user_id, batch_id, reason))
        conn.commit()
        user = conn.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        flash(f"Reward assigned to {user['name'] if user else 'user'}!", 'success')
        return redirect(url_for('admin_reward_assign'))

    batch_id = request.args.get('batch_id', type=int)
    all_batches = conn.execute(
        "SELECT tb.*, t.title as trip_title FROM trip_batch tb JOIN trips t ON tb.trip_id=t.id ORDER BY t.title, tb.batch_name").fetchall()
    rewards = conn.execute("SELECT * FROM reward WHERE is_active=1 ORDER BY title").fetchall()

    leaderboard = []
    batch_members = []
    selected_batch = None
    if batch_id:
        selected_batch = conn.execute("SELECT tb.*, t.title as trip_title FROM trip_batch tb JOIN trips t ON tb.trip_id=t.id WHERE tb.id=?", (batch_id,)).fetchone()
        if selected_batch:
            batch_members_raw = conn.execute(
                """SELECT DISTINCT b.user_id, u.name FROM bookings b JOIN users u ON b.user_id=u.id
                   WHERE b.wb_batch_id=? AND b.status='confirmed'""", (batch_id,)).fetchall()
            batch_members = list(batch_members_raw)
            for m in batch_members:
                result = conn.execute(
                    """SELECT COALESCE(SUM(points_awarded),0) as pts FROM activity_submission
                       WHERE user_id=? AND status='approved'""", (m['user_id'],)).fetchone()
                leaderboard.append({'user_id': m['user_id'], 'name': m['name'], 'points': result['pts'] or 0})
            leaderboard.sort(key=lambda x: -x['points'])
    conn.close()
    return render_template('admin/rewards/assign.html', all_batches=all_batches, rewards=rewards,
                           leaderboard=leaderboard, batch_members=batch_members,
                           selected_batch=dict(selected_batch) if selected_batch else None,
                           batch_id=batch_id)


# ─── ADMIN: UPDATED STATS (for admin_panel to include new stats) ───────────────
# We patch admin_panel to include new stats by injecting via context:

@app.context_processor
def inject_admin_extra_stats():
    try:
        conn = get_db_connection()
        pending_reviews = conn.execute(
            "SELECT COUNT(*) FROM activity_submission WHERE status='pending'").fetchone()[0]
        total_pts = conn.execute(
            "SELECT COALESCE(SUM(points_awarded),0) FROM activity_submission WHERE status='approved'").fetchone()[0]
        conn.close()
        return dict(admin_pending_reviews=pending_reviews, admin_total_points=total_pts)
    except Exception:
        return dict(admin_pending_reviews=0, admin_total_points=0)


# ── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
