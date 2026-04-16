"""
WanderBuddy - Travel and Trouble
Production-Ready Flask Application
"""
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import sqlite3
import os
import re
import uuid
import logging
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import secrets
from config import config  # config.py now handles load_dotenv()

# ── App Initialization ────────────────────────────────────────────────────────
env = os.environ.get('FLASK_ENV', 'development')
app = Flask(__name__)
app.config.from_object(config[env])

# Razorpay keys are already in config — make shortcuts
RAZORPAY_KEY_ID     = app.config.get('RAZORPAY_KEY_ID', 'rzp_test_replace_me')
RAZORPAY_KEY_SECRET = app.config.get('RAZORPAY_KEY_SECRET', 'replace_this_secret')

mail = Mail(app)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── Config shortcuts ──────────────────────────────────────────────────────────
UPLOAD_FOLDER          = app.config['UPLOAD_FOLDER']
ALLOWED_EXTENSIONS     = app.config['ALLOWED_EXTENSIONS']
ADMIN_EMAIL            = app.config['ADMIN_EMAIL']
HARDCODED_ADMIN_EMAIL  = 'ankit.pandeyiitmbs@gmail.com'
ADMIN_EMAILS           = list({ADMIN_EMAIL, HARDCODED_ADMIN_EMAIL})
HARDCODED_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
ITEMS_PER_PAGE         = app.config.get('ITEMS_PER_PAGE', 12)

DEFAULT_SITE_SETTINGS = {
    'id': 1,
    'phone': '+91 8347416221',
    'email': 'ankit.pandeyiitmbs@gmail.com',
    'address': 'New Delhi, India',
    'instagram': '#',
    'twitter': '#',
    'facebook': '#',
    'youtube': '#',
    'working_hours': '9:00 AM - 5:00 PM IST',
    'year_established': 2026,
    'logo_url': '',
    'primary_color': '#1a1a2e',
    'secondary_color': '#16213e',
    'accent_color': '#e8c547',
    'font_family': 'DM Sans',
    'hero_tagline': 'Where Adventure Meets Comfort',
    'hero_subtext': 'Discover breathtaking destinations crafted for the modern explorer',
    'site_title': 'Travel & Trouble'
}

DEFAULT_PAGE_CONTENT = {
    'about': {
        'title': 'About Travel & Trouble',
        'content': (
            '<h2>Our Story</h2>'
            '<p>Travel & Trouble was built for travelers who want more than a checklist. '
            'We design mountain journeys that balance comfort, local culture, and real community.</p>'
            '<h2>What We Believe</h2>'
            '<p>Every trip should feel safe, clear, and memorable. That means transparent pricing, '
            'verified ground partners, small groups, and thoughtful itineraries that leave room for connection.</p>'
            '<h2>How We Travel</h2>'
            '<ul>'
            '<li>Small batches that make group coordination easier.</li>'
            '<li>Trusted operators, guides, and add-on partners.</li>'
            '<li>Experiences that mix adventure with downtime.</li>'
            '<li>Responsible travel that respects local communities and trails.</li>'
            '</ul>'
        )
    },
    'privacy': {
        'title': 'Privacy Policy',
        'content': (
            '<h2>What We Collect</h2>'
            '<p>We collect the details needed to run bookings safely and smoothly, including account, payment, '
            'support, and travel-preference information.</p>'
            '<h2>How We Use It</h2>'
            '<ul>'
            '<li>To manage bookings, payments, and support requests.</li>'
            '<li>To share operational trip updates and important alerts.</li>'
            '<li>To improve the product, pages, and customer experience.</li>'
            '</ul>'
            '<h2>Data Sharing</h2>'
            '<p>We only share information with the partners required to deliver your trip or complete a payment. '
            'We do not sell personal data.</p>'
            '<h2>Your Rights</h2>'
            '<p>You can request updates, corrections, or deletion of your information by contacting our support team.</p>'
        )
    },
    'terms': {
        'title': 'Terms of Service',
        'content': (
            '<h2>Bookings and Payments</h2>'
            '<p>Bookings are confirmed only after payment is completed and inventory remains available.</p>'
            '<h2>Traveler Responsibilities</h2>'
            '<ul>'
            '<li>Provide accurate contact and identity details.</li>'
            '<li>Follow trip safety instructions and local guidelines.</li>'
            '<li>Respect fellow travelers, guides, and host communities.</li>'
            '</ul>'
            '<h2>Cancellations</h2>'
            '<p>Refund timing and eligibility depend on how close the cancellation is to departure and the operating costs already committed.</p>'
            '<h2>Liability</h2>'
            '<p>Adventure travel includes inherent risk. Travelers are responsible for choosing experiences suited to their fitness and comfort level.</p>'
        )
    },
    'home': {
        'title': 'Adventure Awaits',
        'content': (
            '<h2>Travel better with community-first trips.</h2>'
            '<p>Discover treks, mountain escapes, events, and gear curated for modern explorers.</p>'
        )
    }
}

LEGACY_PAGE_MARKERS = {
    'about':   ['We are a community of passionate travelers'],
    'privacy': ['Your data is safe with us.'],
    'terms':   ['Rules for using our platform.'],
    'home':    ['Explore the best treks in India.']
}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Security headers (applied in production via after_request) ────────────────
@app.after_request
def apply_security_headers(response):
    if not app.debug:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options']        = 'SAMEORIGIN'
        response.headers['X-XSS-Protection']       = '1; mode=block'
        response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    return response

# ── Database ──────────────────────────────────────────────────────────────────
def get_db_connection():
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise


def init_db():
    ensure_database_ready()


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or uuid.uuid4().hex[:8]


def ensure_site_settings_row(conn):
    columns      = ', '.join(DEFAULT_SITE_SETTINGS.keys())
    placeholders = ', '.join('?' for _ in DEFAULT_SITE_SETTINGS)
    conn.execute(
        f'INSERT OR IGNORE INTO site_settings ({columns}) VALUES ({placeholders})',
        tuple(DEFAULT_SITE_SETTINGS.values())
    )
    return dict(conn.execute('SELECT * FROM site_settings WHERE id = 1').fetchone())


def load_cms_page(conn, page_name):
    default_page = DEFAULT_PAGE_CONTENT.get(page_name, {
        'title':   page_name.replace('-', ' ').title(),
        'content': ''
    })
    page = conn.execute('SELECT * FROM page_content WHERE page_name = ?', (page_name,)).fetchone()

    needs_refresh = page is None
    if page is not None:
        page_dict = dict(page)
        content   = page_dict.get('content') or ''
        needs_refresh = (
            not page_dict.get('title') or
            any(marker in content for marker in LEGACY_PAGE_MARKERS.get(page_name, ()))
        )

    if needs_refresh:
        conn.execute(
            '''
            INSERT INTO page_content (page_name, title, content, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(page_name) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (page_name, default_page['title'], default_page['content'])
        )
        page = conn.execute('SELECT * FROM page_content WHERE page_name = ?', (page_name,)).fetchone()

    return dict(page)


def get_booking_target(conn, target_id):
    trip = conn.execute('SELECT * FROM trips WHERE id = ?', (target_id,)).fetchone()
    if trip:
        return dict(trip), 'trip'
    event = conn.execute('SELECT * FROM events WHERE id = ?', (target_id,)).fetchone()
    if event:
        return dict(event), 'event'
    return None, None


def build_batch_choices(conn, target, target_type):
    if target_type == 'event':
        event_date = target.get('event_date') or 'Date to be announced'
        return [{'value': event_date, 'label': event_date, 'status': 'scheduled'}]

    rows = conn.execute(
        '''
        SELECT batch_date, current_bookings, max_allowed, status
        FROM trip_batches
        WHERE trip_id = ? AND status != 'cancelled'
        ORDER BY batch_date ASC
        ''',
        (target['id'],)
    ).fetchall()

    if rows:
        return [{
            'value': row['batch_date'],
            'label': f"{row['batch_date']} ({row['current_bookings']}/{row['max_allowed']} booked)",
            'status': row['status']
        } for row in rows]

    return [{'value': 'Dates to be confirmed', 'label': 'Dates to be confirmed by the team', 'status': 'pending'}]


def migrate_bookings_table(conn):
    columns      = {row['name'] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()}
    foreign_keys = conn.execute("PRAGMA foreign_key_list(bookings)").fetchall()
    has_trip_fk  = any(fk['table'] == 'trips' and fk['from'] == 'trip_id' for fk in foreign_keys)

    if 'booking_type' in columns and not has_trip_fk:
        return

    logger.info('Migrating bookings table for mixed trip and event support.')
    conn.execute('PRAGMA foreign_keys = OFF')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bookings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            trip_id TEXT NOT NULL,
            booking_type TEXT DEFAULT 'trip',
            batch_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_id TEXT,
            document_path TEXT,
            num_travelers INTEGER DEFAULT 1,
            sharing_type TEXT DEFAULT 'quad',
            price_per_person INTEGER DEFAULT 0,
            total_price INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    booking_type_expr = 'booking_type' if 'booking_type' in columns else "'trip'"
    conn.execute(f'''
        INSERT INTO bookings_new (
            id, user_id, trip_id, booking_type, batch_date, status, payment_id,
            document_path, num_travelers, sharing_type, price_per_person, total_price
        )
        SELECT
            id, user_id, trip_id, {booking_type_expr}, batch_date, status, payment_id,
            document_path, num_travelers, sharing_type, price_per_person, total_price
        FROM bookings
    ''')
    conn.execute('DROP TABLE bookings')
    conn.execute('ALTER TABLE bookings_new RENAME TO bookings')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_bookings_trip_id ON bookings(trip_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_bookings_type_target ON bookings(booking_type, trip_id)')
    conn.execute('PRAGMA foreign_keys = ON')


def ensure_database_ready():
    conn = None
    try:
        conn = get_db_connection()
        with open('schema.sql', 'r', encoding='utf-8', errors='replace') as f:
            conn.executescript(f.read())
        migrate_bookings_table(conn)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_bookings_type_target ON bookings(booking_type, trip_id)')
        ensure_site_settings_row(conn)
        for page_name in DEFAULT_PAGE_CONTENT:
            load_cms_page(conn, page_name)
        conn.commit()
    except Exception as e:
        logger.error(f'Database initialization error: {e}')
        raise
    finally:
        if conn is not None:
            conn.close()


# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin' and session.get('user_email') not in ADMIN_EMAILS:
            flash('Unauthorized access.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ── Context Processor ─────────────────────────────────────────────────────────
@app.context_processor
def inject_site_settings():
    conn = get_db_connection()
    try:
        settings = ensure_site_settings_row(conn)
    except Exception as e:
        logger.error(f"Error loading site settings: {e}")
        settings = DEFAULT_SITE_SETTINGS.copy()
    finally:
        conn.close()
    return dict(settings=settings)


# Initialise DB at startup
ensure_database_ready()
logger.info(f"[DB] Using database at: {app.config['DATABASE']}")

import sqlite3 as _sqlite3
try:
    _c = _sqlite3.connect(app.config['DATABASE'])
    _trips = _c.execute('SELECT COUNT(*) FROM trips').fetchone()[0]
    _events = _c.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    _merch = _c.execute('SELECT COUNT(*) FROM merchandise').fetchone()[0]
    _c.close()
    logger.info(f"[DB] Startup check — trips:{_trips}  events:{_events}  merchandise:{_merch}")
except Exception as _e:
    logger.error(f"[DB] Startup check failed: {_e}")


# ── Error Handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}")
    return render_template('500.html'), 500


# ── Public Routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    conn = get_db_connection()
    trips = conn.execute('SELECT * FROM trips LIMIT 3').fetchall()
    conn.close()
    return render_template('index.html', trips=trips)


@app.route('/trips')
def trips_page():
    conn = get_db_connection()
    all_trips = conn.execute('SELECT * FROM trips ORDER BY title').fetchall()
    conn.close()
    return render_template('trips.html', all_trips=all_trips)


@app.route('/events')
def events_page():
    category = request.args.get('category', '').strip()
    conn = get_db_connection()
    if category:
        events = conn.execute(
            'SELECT * FROM events WHERE category = ? ORDER BY event_date', (category,)
        ).fetchall()
    else:
        events = conn.execute('SELECT * FROM events ORDER BY event_date').fetchall()
    conn.close()
    return render_template('events.html', events=events, active_category=category)


@app.route('/about')
def about_page():
    conn = get_db_connection()
    try:
        page = load_cms_page(conn, 'about')
    finally:
        conn.close()
    return render_template('cms_page.html', page=page, page_name='about', title=page['title'])


@app.route('/privacy')
def privacy_page():
    conn = get_db_connection()
    try:
        page = load_cms_page(conn, 'privacy')
    finally:
        conn.close()
    return render_template('cms_page.html', page=page, page_name='privacy', title=page['title'])


@app.route('/terms')
def terms_page():
    conn = get_db_connection()
    try:
        page = load_cms_page(conn, 'terms')
    finally:
        conn.close()
    return render_template('cms_page.html', page=page, page_name='terms', title=page['title'])


@app.route('/contact', methods=['GET', 'POST'])
def contact_page():
    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        email   = request.form.get('email', '').strip()
        subject = request.form.get('subject', 'other').strip()
        message = request.form.get('message', '').strip()
        if name and email and message:
            conn = get_db_connection()
            try:
                conn.execute(
                    'INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
                    (name, email, subject, message)
                )
                conn.commit()
                flash('Thanks for reaching out! We will get back to you within 24 hours.', 'success')
            except Exception:
                flash('Could not send message. Please try again or email us directly.', 'error')
            finally:
                conn.close()
        else:
            flash('Please fill in all required fields.', 'error')
        return redirect(url_for('contact_page'))
    return render_template('contact.html')


@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        tag     = request.form.get('tag', 'General').strip()
        if title and content:
            conn = get_db_connection()
            try:
                conn.execute(
                    'INSERT INTO posts (user_id, title, content, tag, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
                    (session['user_id'], title, content, tag)
                )
                conn.commit()
                flash('Post published to the community!', 'success')
            except Exception:
                flash('Could not publish post. Please try again.', 'error')
            finally:
                conn.close()
        else:
            flash('Title and content are required.', 'error')
        return redirect(url_for('community'))
    return render_template('create_post.html')


@app.route('/treks')
def treks():
    location   = request.args.get('location', '').strip()
    difficulty = request.args.get('difficulty', '').strip()
    category   = request.args.get('category', '').strip()
    search     = request.args.get('search', '').strip()
    page       = request.args.get('page', 1, type=int)

    query       = "SELECT * FROM trips WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM trips WHERE 1=1"
    params = []

    if location:
        query       += " AND location LIKE ?"
        count_query += " AND location LIKE ?"
        params.append(f"%{location}%")
    if difficulty:
        query       += " AND difficulty = ?"
        count_query += " AND difficulty = ?"
        params.append(difficulty)
    if category:
        query       += " AND category = ?"
        count_query += " AND category = ?"
        params.append(category)
    if search:
        query       += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        count_query += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    filter_params = list(params)
    offset = (page - 1) * ITEMS_PER_PAGE
    query += " LIMIT ? OFFSET ?"

    conn = get_db_connection()
    try:
        total_count = conn.execute(count_query, filter_params).fetchone()[0]
        trips       = conn.execute(query, filter_params + [ITEMS_PER_PAGE, offset]).fetchall()
        total_pages = (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        has_prev    = page > 1
        has_next    = page < total_pages
    except Exception as e:
        logger.error(f"Error fetching trips: {e}")
        trips = []
        total_pages = has_prev = has_next = 0
    finally:
        conn.close()

    return render_template('treks.html',
                           trips=trips, page=page, total_pages=total_pages,
                           has_prev=has_prev, has_next=has_next,
                           location=location, difficulty=difficulty,
                           category=category, search=search)


@app.route('/shop')
def shop():
    conn  = get_db_connection()
    items = conn.execute('SELECT * FROM merchandise').fetchall()
    conn.close()
    cart       = session.get('cart', {})
    cart_count = sum(cart.values())
    return render_template('shop.html', items=items, cart_count=cart_count)


@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    if 'cart' not in session:
        session['cart'] = {}
    item_id_str = str(item_id)
    session['cart'][item_id_str] = session['cart'].get(item_id_str, 0) + 1
    session.modified = True
    flash('Item added to your Drop stash!', 'success')
    return redirect(url_for('shop'))


@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cart_session = session.get('cart', {})
    cart_items   = []
    total_price  = 0
    if cart_session:
        conn = get_db_connection()
        for item_id_str, quantity in cart_session.items():
            item = conn.execute('SELECT * FROM merchandise WHERE id = ?', (int(item_id_str),)).fetchone()
            if item:
                subtotal     = item['price'] * quantity
                total_price += subtotal
                cart_items.append({
                    'id': item['id'], 'name': item['name'], 'price': item['price'],
                    'image_url': item['image_url'], 'quantity': quantity, 'subtotal': subtotal
                })
        conn.close()
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)


@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    item_id_str = str(item_id)
    if 'cart' in session and item_id_str in session['cart']:
        del session['cart'][item_id_str]
        session.modified = True
        flash('Item removed.', 'info')
    return redirect(url_for('cart'))


@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    action      = request.form.get('action', 'increase')
    item_id_str = str(item_id)
    if 'cart' not in session:
        session['cart'] = {}
    if item_id_str in session['cart']:
        if action == 'increase':
            session['cart'][item_id_str] += 1
        elif action == 'decrease':
            session['cart'][item_id_str] -= 1
            if session['cart'][item_id_str] <= 0:
                del session['cart'][item_id_str]
                flash('Item removed from cart.', 'info')
        session.modified = True
    return redirect(url_for('cart'))


@app.route('/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM shop_orders WHERE id = ? AND user_id = ?',
        (order_id, session['user_id'])
    ).fetchone()
    if not order:
        flash('Order not found.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    if order['status'] == 'shipped':
        flash('This order has already shipped and cannot be cancelled.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    if order['status'] == 'cancelled':
        flash('This order is already cancelled.', 'info')
        conn.close()
        return redirect(url_for('dashboard'))
    items = conn.execute(
        'SELECT item_id, quantity FROM shop_order_items WHERE order_id = ?', (order_id,)
    ).fetchall()
    for item in items:
        conn.execute('UPDATE merchandise SET stock = stock + ? WHERE id = ?',
                     (item['quantity'], item['item_id']))
    conn.execute("UPDATE shop_orders SET status = 'cancelled' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash('Order cancelled successfully. Stock has been restored.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/checkout_shop', methods=['POST'])
def checkout_shop():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cart_session = session.get('cart', {})
    if not cart_session:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('shop'))

    conn         = get_db_connection()
    total_amount = 0
    items_to_insert = []

    for item_id_str, quantity in cart_session.items():
        item = conn.execute(
            'SELECT id, price, name, stock FROM merchandise WHERE id = ?', (int(item_id_str),)
        ).fetchone()
        if item:
            if item['stock'] < quantity:
                flash(f'Sorry, only {item["stock"]} units of "{item["name"]}" available.', 'error')
                conn.close()
                return redirect(url_for('cart'))
            total_amount += item['price'] * quantity
            items_to_insert.append((item['id'], quantity, item['price']))

    if total_amount > 0:
        cursor   = conn.execute(
            'INSERT INTO shop_orders (user_id, total_amount, status) VALUES (?, ?, ?)',
            (session['user_id'], total_amount, 'pending')
        )
        order_id = cursor.lastrowid
        for item in items_to_insert:
            conn.execute(
                'INSERT INTO shop_order_items (order_id, item_id, quantity, price_at_purchase) VALUES (?, ?, ?, ?)',
                (order_id, item[0], item[1], item[2])
            )
            conn.execute('UPDATE merchandise SET stock = stock - ? WHERE id = ?', (item[1], item[0]))
        conn.commit()
        conn.close()
        session['pending_shop_order_id'] = order_id
        session['pending_shop_total']    = total_amount
        session.pop('cart', None)
        return redirect(url_for('shop_payment', order_id=order_id))
    else:
        flash('Some items in your cart are no longer available.', 'error')
        conn.close()
        return redirect(url_for('cart'))


@app.route('/shop/payment/<int:order_id>')
def shop_payment(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM shop_orders WHERE id = ? AND user_id = ?',
        (order_id, session['user_id'])
    ).fetchone()
    if not order or order['status'] != 'pending':
        flash('Order not found or already processed.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    items = conn.execute(
        '''SELECT soi.quantity, soi.price_at_purchase, m.name, m.image_url
           FROM shop_order_items soi JOIN merchandise m ON soi.item_id = m.id
           WHERE soi.order_id = ?''', (order_id,)
    ).fetchall()
    conn.close()
    return render_template('shop_payment.html', order=order, items=items,
                           razorpay_key=RAZORPAY_KEY_ID)


@app.route('/shop/payment/confirm', methods=['POST'])
def confirm_shop_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    order_id           = request.form.get('order_id', type=int)
    razorpay_payment_id = request.form.get('razorpay_payment_id', '')
    conn  = get_db_connection()
    order = conn.execute(
        'SELECT * FROM shop_orders WHERE id = ? AND user_id = ?',
        (order_id, session['user_id'])
    ).fetchone()
    if not order or order['status'] != 'pending':
        flash('Invalid order.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    conn.execute("UPDATE shop_orders SET status = 'confirmed' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash('Payment successful! Your gear order is confirmed. 🎉', 'success')
    return redirect(url_for('dashboard'))


@app.route('/community')
def community():
    conn  = get_db_connection()
    posts = conn.execute(
        'SELECT p.*, u.name as author_name FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.timestamp DESC'
    ).fetchall()
    conn.close()
    return render_template('community.html', posts=posts)


@app.route('/explorer-pass')
def explorer_pass():
    membership_tier = None
    if 'user_id' in session:
        conn = get_db_connection()
        sub  = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active'", (session['user_id'],)
        ).fetchone()
        if sub:
            membership_tier = sub['plan_name'].lower() if 'plan_name' in sub.keys() else 'basic'
        conn.close()
    return render_template('subscription.html', membership_tier=membership_tier)


@app.route('/subscribe_pass', methods=['POST'])
def subscribe_pass():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    tier        = request.form.get('tier', 'basic')
    tier_prices = {'basic': 999, 'pro': 1999, 'elite': 4999}
    conn = get_db_connection()
    try:
        existing = conn.execute("SELECT * FROM subscriptions WHERE user_id = ?", (session['user_id'],)).fetchone()
        if existing:
            conn.execute(
                "UPDATE subscriptions SET plan_name = ?, valid_until = date('now', '+1 year'), status = 'active' WHERE user_id = ?",
                (tier, session['user_id'])
            )
            flash(f'Upgraded to Explorer {tier.title()}! Welcome to enhanced benefits.', 'success')
        else:
            conn.execute(
                "INSERT INTO subscriptions (user_id, plan_name, valid_until, status) VALUES (?, ?, date('now', '+1 year'), 'active')",
                (session['user_id'], tier)
            )
            flash(f'Welcome to Explorer {tier.title()} Pass! Your benefits are now active.', 'success')
        conn.commit()
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        flash('Error processing subscription. Please try again.', 'error')
    finally:
        conn.close()
    return redirect(url_for('explorer_pass'))


def get_membership_discount(user_id):
    if not user_id:
        return 0
    conn = get_db_connection()
    try:
        sub = conn.execute(
            "SELECT plan_name FROM subscriptions WHERE user_id = ? AND status = 'active' AND valid_until > date('now')",
            (user_id,)
        ).fetchone()
        if sub:
            discounts = {'basic': 5, 'pro': 10, 'elite': 15}
            return discounts.get(sub['plan_name'].lower(), 0)
        return 0
    except Exception as e:
        logger.error(f"Error getting membership discount: {e}")
        return 0
    finally:
        conn.close()


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name     = request.form['name']
        email    = request.form['email']
        password = generate_password_hash(request.form['password'])
        phone    = request.form['phone']
        role     = request.form.get('role', 'traveler')
        conn = get_db_connection()
        try:
            cursor  = conn.execute(
                'INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)',
                (name, email, password, phone, role)
            )
            user_id = cursor.lastrowid
            if role == 'vendor':
                business_name = request.form.get('business_name', 'Unnamed Business')
                business_type = request.form.get('business_type', 'hotel')
                conn.execute(
                    'INSERT INTO vendor_profiles (user_id, business_name, business_type, verified) VALUES (?, ?, ?, 1)',
                    (user_id, business_name, business_type)
                )
            conn.commit()
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'error')
        finally:
            conn.close()
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']

        # Admin login via env password
        if HARDCODED_ADMIN_PASSWORD and email in ADMIN_EMAILS and password == HARDCODED_ADMIN_PASSWORD:
            session['user_id']    = 1
            session['user_name']  = 'Admin'
            session['user_email'] = email
            session['user_role']  = 'admin'
            return redirect(url_for('admin_dashboard'))

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id']    = user['id']
            session['user_name']  = user['name']
            session['user_email'] = user['email']
            session['user_role']  = user['role']
            if user['email'] in ADMIN_EMAILS or user['role'] == 'admin':
                session['user_role'] = 'admin'
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'vendor':
                return redirect(url_for('vendor_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        conn  = get_db_connection()
        user  = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            conn.execute(
                "UPDATE users SET reset_token = ?, reset_expiry = datetime('now', '+1 hour') WHERE id = ?",
                (token, user['id'])
            )
            conn.commit()
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message("Password Reset - Travel & Trouble",
                          recipients=[email],
                          body=f"Hi {user['name']},\n\nReset your password here:\n{reset_url}\n\nThis link expires in 1 hour.")
            try:
                mail.send(msg)
                flash('Password reset link sent to your email.', 'success')
            except Exception as e:
                logger.error(f"Email error: {e}")
                if app.debug:
                    flash(f'Reset Link (DEBUG): {reset_url}', 'info')
                else:
                    flash('Could not send email. Please contact support.', 'error')
        else:
            flash('If that email is registered, you will receive a reset link.', 'info')
        conn.close()
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE reset_token = ? AND reset_expiry > datetime('now')", (token,)
    ).fetchone()
    if not user:
        flash('Invalid or expired reset token.', 'error')
        conn.close()
        return redirect(url_for('login'))
    if request.method == 'POST':
        password         = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
        else:
            conn.execute(
                "UPDATE users SET password = ?, reset_token = NULL, reset_expiry = NULL WHERE id = ?",
                (generate_password_hash(password), user['id'])
            )
            conn.commit()
            conn.close()
            flash('Password reset successful! Please login.', 'success')
            return redirect(url_for('login'))
    conn.close()
    return render_template('reset_password.html', token=token)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        if name and email:
            try:
                conn.execute(
                    'UPDATE users SET name = ?, phone = ?, email = ? WHERE id = ?',
                    (name, phone, email, session['user_id'])
                )
                conn.commit()
                session['user_name']  = name
                session['user_email'] = email
                flash('Profile updated successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Email already in use by another account.', 'error')
            finally:
                conn.close()
            return redirect(url_for('profile'))
        else:
            flash('Name and email are required.', 'error')
    conn.close()
    return render_template('profile.html', user=user)


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    old_password     = request.form.get('old_password')
    new_password     = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    if new_password != confirm_password:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('profile'))
    conn = get_db_connection()
    user = conn.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user and check_password_hash(user['password'], old_password):
        conn.execute('UPDATE users SET password = ? WHERE id = ?',
                     (generate_password_hash(new_password), session['user_id']))
        conn.commit()
        flash('Password changed successfully!', 'success')
    else:
        flash('Incorrect old password.', 'error')
    conn.close()
    return redirect(url_for('profile'))


@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    try:
        booking = conn.execute(
            'SELECT * FROM bookings WHERE id = ? AND user_id = ?',
            (booking_id, session['user_id'])
        ).fetchone()
        if not booking:
            flash('Booking not found.', 'error')
            return redirect(url_for('dashboard'))
        if booking['status'] == 'cancelled':
            flash('Booking is already cancelled.', 'info')
            return redirect(url_for('dashboard'))
        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        if (booking['booking_type'] or 'trip') == 'trip':
            conn.execute(
                '''UPDATE trip_batches SET current_bookings = MAX(current_bookings - ?, 0)
                   WHERE trip_id = ? AND batch_date = ?''',
                (booking['num_travelers'], booking['trip_id'], booking['batch_date'])
            )
        conn.commit()
        flash('Booking cancelled successfully. Your spot has been released.', 'success')
    except Exception as e:
        logger.error(f"Cancellation error: {e}")
        flash('Error cancelling booking. Please contact support.', 'error')
    finally:
        conn.close()
    return redirect(url_for('dashboard'))


@app.route('/search')
def search():
    query_str = request.args.get('q', '').strip()
    if not query_str:
        return redirect(url_for('index'))
    conn            = get_db_connection()
    search_pattern  = f"%{query_str}%"
    trips  = conn.execute(
        'SELECT * FROM trips WHERE title LIKE ? OR description LIKE ? OR location LIKE ? OR category LIKE ?',
        (search_pattern, search_pattern, search_pattern, search_pattern)
    ).fetchall()
    events = conn.execute(
        'SELECT * FROM events WHERE title LIKE ? OR description LIKE ? OR location LIKE ? OR category LIKE ?',
        (search_pattern, search_pattern, search_pattern, search_pattern)
    ).fetchall()
    conn.close()
    return render_template('search_results.html', query=query_str, trips=trips, events=events)


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


# ── Vendor Routes ─────────────────────────────────────────────────────────────
@app.route('/vendor/dashboard')
def vendor_dashboard():
    if session.get('user_role') != 'vendor':
        return redirect(url_for('login'))
    conn = get_db_connection()
    vendor_profile  = conn.execute(
        "SELECT * FROM vendor_profiles WHERE user_id = ?", (session['user_id'],)
    ).fetchone()
    total_addons    = conn.execute(
        "SELECT COUNT(*) FROM addons WHERE vendor_id = ?", (session['user_id'],)
    ).fetchone()[0]
    total_bookings  = conn.execute(
        "SELECT COUNT(*) FROM booking_addons ba JOIN addons a ON ba.addon_id = a.id WHERE a.vendor_id = ?",
        (session['user_id'],)
    ).fetchone()[0]
    total_revenue   = conn.execute(
        "SELECT SUM(a.price) FROM booking_addons ba JOIN addons a ON ba.addon_id = a.id WHERE a.vendor_id = ?",
        (session['user_id'],)
    ).fetchone()[0] or 0

    # FIX: LEFT JOIN trips so event bookings don't crash this query
    recent_bookings = conn.execute("""
        SELECT ba.booking_id, u.name as traveler_name, a.title as addon_title,
               COALESCE(t.title, e.title, b.trip_id) as trip_title,
               b.batch_date, a.price
        FROM booking_addons ba
        JOIN addons a ON ba.addon_id = a.id
        JOIN bookings b ON ba.booking_id = b.id
        JOIN users u ON b.user_id = u.id
        LEFT JOIN trips t ON b.trip_id = t.id AND COALESCE(b.booking_type,'trip') = 'trip'
        LEFT JOIN events e ON b.trip_id = e.id AND COALESCE(b.booking_type,'trip') = 'event'
        WHERE a.vendor_id = ?
        ORDER BY b.id DESC LIMIT 5
    """, (session['user_id'],)).fetchall()

    conn.close()
    return render_template('vendor_dashboard.html',
                           vendor_profile=vendor_profile,
                           stats={'total_addons': total_addons,
                                  'total_bookings': total_bookings,
                                  'total_revenue': total_revenue},
                           recent_bookings=recent_bookings)


@app.route('/vendor/addons', methods=['GET'])
def vendor_addons():
    if session.get('user_role') != 'vendor':
        return redirect(url_for('login'))
    conn = get_db_connection()
    # FIX: LEFT JOIN trips so addon list doesn't crash if trip was deleted
    addons = conn.execute(
        "SELECT a.*, COALESCE(t.title, a.trip_id) as trip_title FROM addons a LEFT JOIN trips t ON a.trip_id = t.id WHERE a.vendor_id = ?",
        (session['user_id'],)
    ).fetchall()
    trips          = conn.execute("SELECT id, title FROM trips").fetchall()
    vendor_profile = conn.execute("SELECT * FROM vendor_profiles WHERE user_id = ?", (session['user_id'],)).fetchone()
    conn.close()
    return render_template('vendor_addons.html', addons=addons, trips=trips, vendor_profile=vendor_profile)


@app.route('/vendor/addons/add', methods=['POST'])
def add_vendor_addon():
    if session.get('user_role') != 'vendor':
        return redirect(url_for('login'))
    conn           = get_db_connection()
    vendor_profile = conn.execute(
        "SELECT verified FROM vendor_profiles WHERE user_id = ?", (session['user_id'],)
    ).fetchone()
    if not vendor_profile or not vendor_profile['verified']:
        conn.close()
        flash("Your account is pending approval. You cannot add listings.", "error")
        return redirect(url_for('vendor_addons'))
    conn.execute(
        "INSERT INTO addons (trip_id, vendor_id, addon_type, title, price, description) VALUES (?, ?, ?, ?, ?, ?)",
        (request.form['trip_id'], session['user_id'], request.form['addon_type'],
         request.form['title'], request.form['price'], request.form['description'])
    )
    conn.commit()
    conn.close()
    flash("Add-on successfully listed!", "success")
    return redirect(url_for('vendor_addons'))


@app.route('/vendor/addons/delete/<int:id>', methods=['POST'])
def delete_vendor_addon(id):
    if session.get('user_role') != 'vendor':
        return redirect(url_for('login'))
    conn  = get_db_connection()
    addon = conn.execute(
        "SELECT id FROM addons WHERE id = ? AND vendor_id = ?", (id, session['user_id'])
    ).fetchone()
    if addon:
        has_bookings = conn.execute("SELECT id FROM booking_addons WHERE addon_id = ?", (id,)).fetchone()
        if has_bookings:
            flash("Cannot delete an add-on that has active bookings.", "error")
        else:
            conn.execute("DELETE FROM addons WHERE id = ?", (id,))
            conn.commit()
            flash("Add-on deleted.", "success")
    conn.close()
    return redirect(url_for('vendor_addons'))


# ── Trip & Booking Routes ─────────────────────────────────────────────────────
@app.route('/trip/<trip_id>')
def trip_details(trip_id):
    conn = get_db_connection()
    try:
        trip, target_type = get_booking_target(conn, trip_id)
        if not trip:
            return render_template('404.html'), 404
        addons = []
        if target_type == 'trip':
            addons = conn.execute('SELECT * FROM addons WHERE trip_id = ?', (trip_id,)).fetchall()
        batch_choices = build_batch_choices(conn, trip, target_type)
    finally:
        conn.close()
    return render_template('trip_details.html', trip=trip, addons=addons,
                           batch_choices=batch_choices, target_type=target_type)


@app.route('/book', methods=['POST'])
def book_trip():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    trip_id        = request.form['trip_id']
    batch_date     = request.form['batch_date']
    user_id        = session['user_id']
    selected_addons = request.form.getlist('addons')
    num_travelers  = int(request.form.get('num_travelers', 1))
    sharing_type   = request.form.get('sharing_type', 'quad')

    if num_travelers < 1 or num_travelers > 12:
        flash('Group size must be between 1 and 12 travelers.', 'error')
        return redirect(url_for('trip_details', trip_id=trip_id))

    conn = get_db_connection()
    try:
        target, booking_type = get_booking_target(conn, trip_id)
        if not target:
            flash('Trip/Event not found.', 'error')
            return redirect(url_for('treks'))
        if booking_type == 'event':
            sharing_type     = 'ticket'
            price_per_person = int(target['price'])
        else:
            base_price       = target['price']
            price_multipliers = {'quad': 1.0, 'triple': 1.125, 'double': 1.375}
            price_per_person = int(base_price * price_multipliers.get(sharing_type, 1.0))

        discount_pct          = get_membership_discount(user_id)
        final_price_per_person = int(price_per_person * (100 - discount_pct) / 100)
        total_price            = final_price_per_person * num_travelers

        cursor     = conn.execute(
            '''INSERT INTO bookings
               (user_id, trip_id, booking_type, batch_date, num_travelers,
                sharing_type, price_per_person, total_price, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, trip_id, booking_type, batch_date, num_travelers,
             sharing_type, final_price_per_person, total_price, 'pending')
        )
        booking_id = cursor.lastrowid

        if booking_type == 'trip':
            for addon_id in selected_addons:
                conn.execute(
                    'INSERT INTO booking_addons (booking_id, addon_id) VALUES (?, ?)',
                    (booking_id, addon_id)
                )
            conn.execute(
                '''INSERT INTO trip_batches (trip_id, batch_date, current_bookings, min_required, max_allowed)
                   VALUES (?, ?, ?, 6, 16)
                   ON CONFLICT(trip_id, batch_date) DO UPDATE SET
                   current_bookings = current_bookings + ?''',
                (trip_id, batch_date, num_travelers, num_travelers)
            )
        conn.commit()
        flash(f'Booking created for {num_travelers} traveler(s)! Proceed to payment.', 'success')
        return redirect(url_for('payment', booking_id=booking_id))
    except Exception as e:
        logger.error(f"Booking error: {e}")
        flash('Error creating booking. Please try again.', 'error')
        return redirect(url_for('trip_details', trip_id=trip_id))
    finally:
        conn.close()


@app.route('/payment/<int:booking_id>')
def payment(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        booking = conn.execute(
            '''SELECT b.*,
                      COALESCE(t.title, e.title, b.trip_id) AS title,
                      COALESCE(t.price, e.price, b.price_per_person) AS price,
                      COALESCE(t.duration, e.duration, '') AS duration
               FROM bookings b
               LEFT JOIN trips t ON b.trip_id = t.id AND COALESCE(b.booking_type,'trip') = 'trip'
               LEFT JOIN events e ON b.trip_id = e.id AND COALESCE(b.booking_type,'trip') = 'event'
               WHERE b.id = ? AND b.user_id = ?''',
            (booking_id, session['user_id'])
        ).fetchone()
        if not booking:
            flash('Booking not found.', 'error')
            return redirect(url_for('dashboard'))

        addons = conn.execute(
            'SELECT a.* FROM booking_addons ba JOIN addons a ON ba.addon_id = a.id WHERE ba.booking_id = ?',
            (booking_id,)
        ).fetchall()

        base_price  = booking['total_price']
        addon_total = sum(a['price'] for a in addons)
        final_total = base_price + addon_total

        batch_status = None
        if booking['booking_type'] == 'trip':
            batch = conn.execute(
                'SELECT * FROM trip_batches WHERE trip_id = ? AND batch_date = ?',
                (booking['trip_id'], booking['batch_date'])
            ).fetchone()
            batch_status = {
                'current':    batch['current_bookings'] if batch else booking['num_travelers'],
                'min_required': 6, 'max_allowed': 16,
                'confirmed':  bool(batch and batch['current_bookings'] >= 6)
            }

        sub = conn.execute(
            "SELECT plan_name FROM subscriptions WHERE user_id = ? AND status = 'active'",
            (session['user_id'],)
        ).fetchone()
        membership_tier = sub['plan_name'] if sub else None

        return render_template(
            'payment.html',
            booking=booking, addons=addons,
            base_price=base_price, addon_total=addon_total, final_total=final_total,
            batch_status=batch_status, membership_tier=membership_tier,
            razorpay_key=RAZORPAY_KEY_ID   # FIX: pass key explicitly to template
        )
    finally:
        conn.close()


@app.route('/process_payment/<int:booking_id>', methods=['POST'])
def process_payment(booking_id):
    razorpay_payment_id = request.form.get('razorpay_payment_id')
    if razorpay_payment_id:
        conn = get_db_connection()
        conn.execute(
            'UPDATE bookings SET status = "confirmed", payment_id = ? WHERE id = ?',
            (razorpay_payment_id, booking_id)
        )
        conn.commit()
        conn.close()
        flash('Payment Successful! Welcome to the adventure.', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Payment Failed. Please try again.', 'error')
        return redirect(url_for('payment', booking_id=booking_id))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn     = get_db_connection()
    bookings = conn.execute(
        '''SELECT b.*,
                  COALESCE(t.title, e.title, b.trip_id) AS title,
                  COALESCE(t.image_url, e.image_url, '') AS image_url,
                  b.trip_id AS trip_id
           FROM bookings b
           LEFT JOIN trips t ON b.trip_id = t.id AND COALESCE(b.booking_type,'trip') = 'trip'
           LEFT JOIN events e ON b.trip_id = e.id AND COALESCE(b.booking_type,'trip') = 'event'
           WHERE b.user_id = ?
           ORDER BY b.id DESC''',
        (session['user_id'],)
    ).fetchall()

    booking_data = []
    for booking in bookings:
        available_quests  = conn.execute('SELECT * FROM quests WHERE trip_id = ?', (booking['trip_id'],)).fetchall()
        completed_quests  = conn.execute('SELECT * FROM user_quests WHERE booking_id = ?', (booking['id'],)).fetchall()
        total_points      = 0
        quests_status     = []
        for q in available_quests:
            entry      = next((uq for uq in completed_quests if uq['quest_id'] == q['id']), None)
            is_done    = is_pending = False
            if entry:
                if entry['status'] == 'approved':
                    is_done      = True
                    total_points += q['points']
                elif entry['status'] == 'pending':
                    is_pending = True
            quests_status.append({
                'id': q['id'], 'title': q['title'], 'points': q['points'],
                'icon': q['icon'], 'done': is_done, 'pending': is_pending
            })
        max_points = sum(q['points'] for q in available_quests) if available_quests else 1
        progress   = (total_points / max_points) * 100
        booking_data.append({
            'details': booking, 'quests': quests_status,
            'score': total_points, 'progress': int(progress)
        })

    shop_orders = conn.execute(
        '''SELECT so.*, GROUP_CONCAT(m.name || ' (x' || soi.quantity || ')', ', ') as items
           FROM shop_orders so
           JOIN shop_order_items soi ON so.id = soi.order_id
           JOIN merchandise m ON soi.item_id = m.id
           WHERE so.user_id = ?
           GROUP BY so.id
           ORDER BY so.id DESC''',
        (session['user_id'],)
    ).fetchall()

    conn.close()
    return render_template('dashboard.html', user=session['user_name'],
                           booking_data=booking_data, shop_orders=shop_orders)


@app.route('/upload/<int:booking_id>', methods=['POST'])
def upload_file(booking_id):
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(f"doc_{booking_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db_connection()
        conn.execute('UPDATE bookings SET document_path = ? WHERE id = ?', (filename, booking_id))
        conn.commit()
        conn.close()
        flash('Document uploaded successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/complete_quest', methods=['POST'])
def complete_quest():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    booking_id = request.form['booking_id']
    quest_id   = request.form['quest_id']
    file       = request.files.get('proof')
    if file and allowed_file(file.filename):
        filename = secure_filename(f"quest_{booking_id}_{quest_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO user_quests (booking_id, quest_id, proof_image, status) VALUES (?, ?, ?, ?)',
            (booking_id, quest_id, filename, 'pending')
        )
        conn.commit()
        conn.close()
        flash('Proof submitted!', 'info')
    else:
        flash('Invalid file!', 'error')
    return redirect(url_for('dashboard'))


# ── Chat Routes ───────────────────────────────────────────────────────────────
@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    room     = request.args.get('room')
    is_admin = (session.get('user_email') == ADMIN_EMAIL)
    return render_template('chat.html', room=room, user=session['user_name'], is_admin=is_admin)


@app.route('/send_message', methods=['POST'])
def send_message():
    data     = request.json
    conn     = get_db_connection()
    msg_type = data.get('type', 'text')
    conn.execute(
        'INSERT INTO messages (room_id, user_id, sender, content, msg_type) VALUES (?, ?, ?, ?, ?)',
        (data['room'], session['user_id'], session['user_name'], data['message'], msg_type)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


@app.route('/upload_chat_image', methods=['POST'])
def upload_chat_image():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file and allowed_file(file.filename):
        ext      = file.filename.rsplit('.', 1)[1].lower()
        filename = f"chat_{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        room = request.form['room']
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO messages (room_id, user_id, sender, content, msg_type) VALUES (?, ?, ?, ?, ?)',
            (room, session['user_id'], session['user_name'], filename, 'image')
        )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Invalid file'}), 400


@app.route('/get_messages/<room_id>')
def get_messages(room_id):
    conn         = get_db_connection()
    msgs         = conn.execute(
        'SELECT * FROM messages WHERE room_id = ? ORDER BY timestamp ASC', (room_id,)
    ).fetchall()
    conn.close()
    is_admin       = (session.get('user_email') == ADMIN_EMAIL)
    current_user_id = session.get('user_id')
    results = []
    for m in msgs:
        msg_dict              = dict(m)
        msg_dict['can_edit']  = (m['user_id'] == current_user_id)
        msg_dict['can_delete'] = (m['user_id'] == current_user_id) or is_admin
        msg_dict['msg_type']  = m['msg_type'] if 'msg_type' in m.keys() else 'text'
        results.append(msg_dict)
    return jsonify(results)


@app.route('/delete_message/<int:msg_id>', methods=['POST'])
def delete_message(msg_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    msg  = conn.execute('SELECT * FROM messages WHERE id = ?', (msg_id,)).fetchone()
    if not msg:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    is_admin = (session.get('user_email') == ADMIN_EMAIL)
    if msg['user_id'] != session['user_id'] and not is_admin:
        conn.close()
        return jsonify({'error': 'Permission denied'}), 403
    conn.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})


@app.route('/edit_message/<int:msg_id>', methods=['POST'])
def edit_message(msg_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    data        = request.json
    new_content = data.get('content')
    conn        = get_db_connection()
    msg         = conn.execute('SELECT * FROM messages WHERE id = ?', (msg_id,)).fetchone()
    if not msg or msg['user_id'] != session['user_id']:
        conn.close()
        return jsonify({'error': 'Permission denied'}), 403
    conn.execute('UPDATE messages SET content = ? WHERE id = ?', (new_content, msg_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'updated'})


# ── Admin Routes ──────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    total_users    = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_bookings = conn.execute('SELECT COUNT(*) FROM bookings WHERE status="confirmed"').fetchone()[0]
    revenue        = conn.execute(
        "SELECT SUM(total_price) FROM bookings WHERE status = 'confirmed'"
    ).fetchone()[0] or 0
    total_vendors  = conn.execute("SELECT COUNT(*) FROM vendor_profiles").fetchone()[0]
    total_addons   = conn.execute("SELECT COUNT(*) FROM addons").fetchone()[0]
    total_posts    = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    total_events   = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    stats = {
        'users': total_users, 'bookings': total_bookings, 'revenue': revenue,
        'vendors': total_vendors, 'addons': total_addons,
        'posts': total_posts, 'events': total_events
    }

    bookings = conn.execute(
        '''SELECT b.*, u.name AS user_name, u.email,
                  COALESCE(t.title, e.title, b.trip_id) AS trip_title
           FROM bookings b
           JOIN users u ON b.user_id = u.id
           LEFT JOIN trips t ON b.trip_id = t.id AND COALESCE(b.booking_type,'trip') = 'trip'
           LEFT JOIN events e ON b.trip_id = e.id AND COALESCE(b.booking_type,'trip') = 'event'
           ORDER BY b.id DESC LIMIT 10'''
    ).fetchall()

    all_trips   = conn.execute("SELECT * FROM trips").fetchall()
    all_quests  = conn.execute(
        "SELECT q.*, t.title as trip_name FROM quests q JOIN trips t ON q.trip_id = t.id"
    ).fetchall()
    vendors     = conn.execute(
        "SELECT v.*, u.name, u.email, u.phone FROM vendor_profiles v JOIN users u ON v.user_id = u.id"
    ).fetchall()
    payouts     = conn.execute(
        '''SELECT v.business_name, v.payout_details, SUM(a.price) as total_earned
           FROM vendor_profiles v
           JOIN addons a ON v.user_id = a.vendor_id
           JOIN booking_addons ba ON a.id = ba.addon_id
           GROUP BY v.business_name'''
    ).fetchall()
    community_posts = conn.execute(
        "SELECT p.*, u.name as author FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.id DESC"
    ).fetchall()
    quest_feed  = conn.execute(
        '''SELECT uq.*, q.title as quest_title, u.name as user_name
           FROM user_quests uq
           JOIN quests q ON uq.quest_id = q.id
           JOIN bookings b ON uq.booking_id = b.id
           JOIN users u ON b.user_id = u.id'''
    ).fetchall()
    inbox       = conn.execute("SELECT * FROM contact_messages ORDER BY created_at DESC").fetchall()
    all_users   = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    all_bookings = conn.execute(
        '''SELECT b.*, u.name AS user_name, u.email,
                  COALESCE(t.title, e.title, b.trip_id) AS trip_title
           FROM bookings b
           JOIN users u ON b.user_id = u.id
           LEFT JOIN trips t ON b.trip_id = t.id AND COALESCE(b.booking_type,'trip') = 'trip'
           LEFT JOIN events e ON b.trip_id = e.id AND COALESCE(b.booking_type,'trip') = 'event'
           ORDER BY b.id DESC'''
    ).fetchall()
    all_events = conn.execute("SELECT * FROM events").fetchall()
    all_pages  = conn.execute("SELECT * FROM page_content ORDER BY page_name").fetchall()
    conn.close()

    return render_template('admin.html',
                           stats=stats, all_trips=all_trips, all_quests=all_quests,
                           vendors=vendors, payouts=payouts,
                           community_posts=community_posts, quest_feed=quest_feed,
                           inbox=inbox, all_users=all_users, all_bookings=all_bookings,
                           bookings=bookings, all_events=all_events, all_pages=all_pages)


@app.route('/admin/quest/action', methods=['POST'])
@admin_required
def quest_action():
    quest_entry_id = request.form['entry_id']
    action         = request.form['action']
    status         = 'approved' if action == 'approve' else 'rejected'
    conn = get_db_connection()
    conn.execute("UPDATE user_quests SET status = ? WHERE id = ?", (status, quest_entry_id))
    conn.commit()
    conn.close()
    flash(f'Quest {status}.', 'success')
    return redirect(url_for('admin_dashboard') + '#overview')


@app.route('/admin/events/add', methods=['POST'])
@admin_required
def admin_add_event():
    title      = request.form.get('title', '').strip()
    event_id   = request.form.get('id', '').strip() or slugify(title)
    price      = int(request.form.get('price', 0) or 0)
    duration   = request.form.get('duration', '').strip() or '1 Day'
    category   = request.form.get('category', '').strip() or 'Adventure Camps'
    description = request.form.get('description', '').strip()
    location   = request.form.get('location', '').strip() or 'Location to be announced'
    event_date = request.form.get('event_date', '').strip() or 'Date to be announced'
    itinerary  = request.form.get('itinerary', '').strip() or description or 'Detailed schedule will be shared before the event.'

    if not title or price <= 0:
        flash('Event title and a valid price are required.', 'error')
        return redirect(url_for('admin_dashboard') + '#events')

    image_url = request.form.get('image_url', '')
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            filename   = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url  = url_for('static', filename='uploads/' + filename)
    if not image_url:
        image_url = url_for('static', filename='assets/logo.svg')

    conn = get_db_connection()
    try:
        conn.execute(
            '''INSERT INTO events (id, title, price, duration, image_url, category, description, location, event_date, itinerary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (event_id, title, price, duration, image_url, category, description, location, event_date, itinerary)
        )
        conn.commit()
        flash('Event added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Event ID already exists. Please choose another slug.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard') + '#events')


@app.route('/admin/events/edit', methods=['POST'])
@admin_required
def admin_edit_event():
    event_id = request.form.get('id') or request.form.get('event_id')
    conn     = get_db_connection()
    current  = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    if not current:
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('admin_dashboard') + '#events')
    current   = dict(current)
    image_url = request.form.get('image_url', '').strip() or current['image_url']
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            filename  = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = url_for('static', filename='uploads/' + filename)

    conn.execute(
        '''UPDATE events SET title=?, price=?, duration=?, image_url=?, category=?,
           description=?, location=?, event_date=?, itinerary=? WHERE id=?''',
        (
            request.form.get('title', '').strip()      or current['title'],
            int(request.form.get('price', current['price']) or current['price']),
            request.form.get('duration', '').strip()   or current['duration'],
            image_url,
            request.form.get('category', '').strip()   or current['category'],
            request.form.get('description', '').strip() or current['description'],
            request.form.get('location', '').strip()   or current['location'],
            request.form.get('event_date', '').strip()  or current['event_date'],
            request.form.get('itinerary', '').strip()  or current['itinerary'],
            event_id
        )
    )
    conn.commit()
    conn.close()
    flash('Event updated successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#events')


@app.route('/admin/events/delete/<id>', methods=['POST'])
@admin_required
def admin_delete_event(id):
    conn = get_db_connection()
    linked = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE trip_id = ? AND COALESCE(booking_type,'trip') = 'event'", (id,)
    ).fetchone()[0]
    if linked:
        conn.close()
        flash('Event cannot be deleted while bookings still exist for it.', 'error')
        return redirect(url_for('admin_dashboard') + '#events')
    conn.execute('DELETE FROM events WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#events')


@app.route('/admin/pages/add', methods=['POST'])
@admin_required
def admin_add_page():
    page_name = slugify(request.form['page_name'])
    title     = request.form.get('title', '').strip() or page_name.replace('-', ' ').title()
    content   = request.form.get('content', '').strip()
    conn      = get_db_connection()
    try:
        conn.execute('INSERT INTO page_content (page_name, title, content) VALUES (?, ?, ?)',
                     (page_name, title, content))
        conn.commit()
        flash('Page created successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Page name must be unique.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard') + '#pages_tab')


@app.route('/admin/pages/edit', methods=['POST'])
@admin_required
def admin_edit_page():
    page_id = request.form['id']
    title   = request.form['title']
    content = request.form['content']
    conn    = get_db_connection()
    conn.execute(
        'UPDATE page_content SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (title, content, page_id)
    )
    conn.commit()
    conn.close()
    flash('Page updated successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#pages_tab')


@app.route('/admin/pages/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_page(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM page_content WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Page deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#pages_tab')


@app.route('/admin/trip/add', methods=['POST'])
@admin_required
def add_trip():
    title      = request.form.get('title', '').strip()
    trip_id    = request.form.get('trip_id', '').strip() or slugify(title)
    price      = int(request.form.get('price', 0) or 0)
    duration   = request.form.get('duration', '').strip()
    image_url  = request.form.get('image_url', '').strip()
    category   = request.form.get('category', '').strip() or 'Adventure Trip'
    description = request.form.get('description', '').strip()
    location   = request.form.get('location', 'Unknown')
    difficulty = request.form.get('difficulty', 'Moderate')
    highlights = request.form.get('highlights', '')

    if not title or price <= 0 or not duration:
        flash('Trip title, duration, and a valid price are required.', 'error')
        return redirect(url_for('admin_dashboard') + '#trips')

    if 'trip_image_file' in request.files:
        file = request.files['trip_image_file']
        if file and file.filename:
            filename  = secure_filename(f"trip_{trip_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = url_for('static', filename='uploads/' + filename)
    if not image_url:
        image_url = url_for('static', filename='assets/logo.svg')

    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO trips (id, title, price, duration, image_url, category, description, location, difficulty, highlights) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trip_id, title, price, duration, image_url, category, description, location, difficulty, highlights)
        )
        conn.commit()
        flash("Trip created successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Trip ID already exists. Update the title or supply a unique ID.", "error")
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard') + '#trips')


@app.route('/admin/trip/delete/<trip_id>', methods=['POST'])
@admin_required
def delete_trip(trip_id):
    conn = get_db_connection()
    ref_count = conn.execute(
        '''SELECT
               (SELECT COUNT(*) FROM bookings WHERE trip_id = ? AND COALESCE(booking_type,'trip') = 'trip') +
               (SELECT COUNT(*) FROM trip_batches WHERE trip_id = ?) +
               (SELECT COUNT(*) FROM quests WHERE trip_id = ?) +
               (SELECT COUNT(*) FROM addons WHERE trip_id = ?)''',
        (trip_id, trip_id, trip_id, trip_id)
    ).fetchone()[0]
    if ref_count:
        conn.close()
        flash('Trip cannot be deleted while batches, bookings, quests, or add-ons still reference it.', 'error')
        return redirect(url_for('admin_dashboard') + '#trips')
    conn.execute('DELETE FROM trips WHERE id = ?', (trip_id,))
    conn.commit()
    conn.close()
    flash('Trip deleted.', 'info')
    return redirect(url_for('admin_dashboard') + '#trips')


@app.route('/admin/quest/add', methods=['POST'])
@admin_required
def add_quest():
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO quests (trip_id, title, points, icon) VALUES (?,?,?,?)',
        (request.form['trip_id'], request.form['title'], request.form['points'], request.form['icon'])
    )
    conn.commit()
    conn.close()
    flash('Quest added successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#quests')


@app.route('/admin/trip/edit', methods=['POST'])
@admin_required
def edit_trip():
    trip_id = request.form['trip_id']
    conn    = get_db_connection()
    current = conn.execute('SELECT * FROM trips WHERE id = ?', (trip_id,)).fetchone()
    if not current:
        conn.close()
        flash('Trip not found.', 'error')
        return redirect(url_for('admin_dashboard') + '#trips')
    current   = dict(current)
    image_url = request.form.get('image_url', '').strip() or current['image_url']
    if 'trip_image_file' in request.files:
        file = request.files['trip_image_file']
        if file and file.filename:
            filename  = secure_filename(f"trip_{trip_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = url_for('static', filename='uploads/' + filename)
    conn.execute(
        "UPDATE trips SET title=?, price=?, duration=?, image_url=?, category=?, description=?, location=?, difficulty=?, highlights=? WHERE id=?",
        (
            request.form.get('title',       '').strip() or current['title'],
            int(request.form.get('price',   current['price']) or current['price']),
            request.form.get('duration',    '').strip() or current['duration'],
            image_url,
            request.form.get('category',    '').strip() or current['category'],
            request.form.get('description', '').strip() or current['description'],
            request.form.get('location',    '').strip() or current['location'],
            request.form.get('difficulty',  '').strip() or current['difficulty'],
            request.form.get('highlights',  '').strip() or current['highlights'],
            trip_id
        )
    )
    conn.commit()
    conn.close()
    flash("Trip updated!", "success")
    return redirect(url_for('admin_dashboard') + '#trips')


@app.route('/admin/settings/update', methods=['POST'])
@admin_required
def update_settings():
    logo_url = request.form.get('logo_url', '')
    if 'logo_file' in request.files:
        file = request.files['logo_file']
        if file and file.filename:
            filename = secure_filename(f"logo_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            logo_url = url_for('static', filename='uploads/' + filename)

    conn     = get_db_connection()
    current  = ensure_site_settings_row(conn)
    vals     = (
        request.form.get('phone',            current['phone']),
        request.form.get('email',            current['email']),
        request.form.get('address',          current['address']),
        request.form.get('instagram',        current['instagram']),
        request.form.get('twitter',          current['twitter']),
        request.form.get('facebook',         current['facebook']),
        request.form.get('youtube',          current['youtube']),
        logo_url or                          current['logo_url'],
        request.form.get('working_hours',    current['working_hours']),
        request.form.get('year_established', current['year_established']),
        request.form.get('primary_color',    current['primary_color']),
        request.form.get('secondary_color',  current['secondary_color']),
        request.form.get('accent_color',     current['accent_color']),
        request.form.get('font_family',      current['font_family']),
        request.form.get('hero_tagline',     current['hero_tagline']),
        request.form.get('hero_subtext',     current['hero_subtext']),
        request.form.get('site_title',       current['site_title']),
    )
    conn.execute(
        '''UPDATE site_settings SET
           phone=?, email=?, address=?, instagram=?, twitter=?, facebook=?, youtube=?,
           logo_url=?, working_hours=?, year_established=?,
           primary_color=?, secondary_color=?, accent_color=?, font_family=?,
           hero_tagline=?, hero_subtext=?, site_title=?
           WHERE id=1''',
        vals
    )
    conn.commit()
    conn.close()
    flash("Settings updated!", "success")
    return redirect(url_for('admin_dashboard') + '#settings')


# ── Batch Management ──────────────────────────────────────────────────────────
@app.route('/admin/trip/batches/<trip_id>')
@admin_required
def admin_batches(trip_id):
    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        flash('Trip not found.', 'error')
        return redirect(url_for('admin_dashboard') + '#trips')
    batches = conn.execute(
        "SELECT * FROM trip_batches WHERE trip_id = ? ORDER BY batch_date ASC", (trip_id,)
    ).fetchall()
    conn.close()
    return render_template('admin_batches.html', trip=trip, batches=batches)


@app.route('/admin/trip/batches/add', methods=['POST'])
@admin_required
def add_batch():
    trip_id    = request.form['trip_id']
    batch_date = request.form['batch_date']
    min_req    = int(request.form['min_required'])
    max_all    = int(request.form['max_allowed'])
    if min_req > max_all:
        flash("Minimum group size cannot exceed max capacity.", "error")
        return redirect(url_for('admin_batches', trip_id=trip_id))
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO trip_batches (trip_id, batch_date, min_required, max_allowed) VALUES (?, ?, ?, ?)",
            (trip_id, batch_date, min_req, max_all)
        )
        conn.commit()
        flash("Batch added successfully!", "success")
    except sqlite3.IntegrityError:
        flash("A batch already exists for this date.", "error")
    finally:
        conn.close()
    return redirect(url_for('admin_batches', trip_id=trip_id))


@app.route('/admin/trip/batches/delete/<int:batch_id>', methods=['POST'])
@admin_required
def delete_batch(batch_id):
    conn  = get_db_connection()
    batch = conn.execute(
        "SELECT trip_id, current_bookings FROM trip_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    trip_id = 'trek'
    if batch:
        trip_id = batch['trip_id']
        if batch['current_bookings'] > 0:
            flash("Cannot delete a batch with active bookings.", "error")
        else:
            conn.execute("DELETE FROM trip_batches WHERE id = ?", (batch_id,))
            conn.commit()
            flash("Batch deleted.", "success")
    conn.close()
    return redirect(url_for('admin_batches', trip_id=trip_id))


# ── User & Booking Management ─────────────────────────────────────────────────
@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user['email'] in ADMIN_EMAILS:
        flash("Cannot delete main admin account.", "error")
    else:
        try:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            flash("User deleted.", "success")
        except sqlite3.IntegrityError:
            flash("User cannot be deleted while related records still exist.", "error")
    conn.close()
    return redirect(url_for('admin_dashboard') + '#users')


@app.route('/admin/booking/status', methods=['POST'])
@admin_required
def update_booking_status():
    booking_id = request.form['booking_id']
    status     = request.form['status']
    conn       = get_db_connection()
    conn.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
    conn.commit()
    conn.close()
    flash(f"Booking status updated to {status}!", "success")
    return redirect(url_for('admin_dashboard') + '#bookings_tab')


@app.route('/admin/delete_post/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    flash('Post deleted.', 'info')
    return redirect(url_for('admin_dashboard') + '#community')


# ── Event Editor ──────────────────────────────────────────────────────────────
@app.route('/admin/event/edit/<event_id>')
@admin_required
def admin_event_editor(event_id):
    conn  = get_db_connection()
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()
    if not event:
        flash('Event not found', 'error')
        return redirect(url_for('admin_dashboard') + '#events')
    return render_template('admin_event_editor.html', event=event)


# ── CMS Page Editor ───────────────────────────────────────────────────────────
@app.route('/admin/page/edit/<page_name>')
@admin_required
def admin_page_editor(page_name):
    valid_pages = ['about', 'privacy', 'terms', 'home']
    if page_name not in valid_pages:
        flash('Invalid page', 'error')
        return redirect(url_for('admin_dashboard') + '#pages_tab')
    conn  = get_db_connection()
    page  = load_cms_page(conn, page_name)
    conn.close()
    return render_template('admin_page_editor.html', page=page, page_name=page_name)


@app.route('/admin/page/update', methods=['POST'])
@admin_required
def admin_page_update():
    page_name = request.form['page_name']
    title     = request.form.get('title', '').strip()
    content   = request.form.get('content', '').strip()
    conn      = get_db_connection()
    conn.execute(
        'UPDATE page_content SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE page_name = ?',
        (title, content, page_name)
    )
    conn.commit()
    conn.close()
    flash(f'{page_name.title()} page updated successfully!', 'success')
    return redirect(url_for('admin_page_editor', page_name=page_name))


# ── Admin Shop ────────────────────────────────────────────────────────────────
@app.route('/admin/shop')
@admin_required
def admin_shop():
    conn  = get_db_connection()
    items = conn.execute('SELECT * FROM merchandise ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('admin_shop.html', items=items)


@app.route('/admin/shop/item/add', methods=['POST'])
@admin_required
def admin_add_shop_item():
    image_url = request.form.get('image_url', '')
    if 'shop_item_file' in request.files:
        file = request.files['shop_item_file']
        if file and file.filename:
            filename  = secure_filename(f"shop_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = url_for('static', filename='uploads/' + filename)
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO merchandise (name, description, price, stock, category, image_url) VALUES (?, ?, ?, ?, ?, ?)',
        (request.form['name'], request.form['description'], request.form['price'],
         request.form['stock'], request.form['category'], image_url)
    )
    conn.commit()
    conn.close()
    flash('Shop item added successfully!', 'success')
    return redirect(url_for('admin_shop'))


@app.route('/admin/shop/item/edit', methods=['POST'])
@admin_required
def admin_edit_shop_item():
    item_id = request.form['item_id']
    conn    = get_db_connection()
    current = conn.execute('SELECT * FROM merchandise WHERE id = ?', (item_id,)).fetchone()
    if not current:
        conn.close()
        flash('Shop item not found.', 'error')
        return redirect(url_for('admin_shop'))
    current   = dict(current)
    image_url = request.form.get('image_url', '').strip() or current['image_url']
    if 'shop_item_file' in request.files:
        file = request.files['shop_item_file']
        if file and file.filename:
            filename  = secure_filename(f"shop_{item_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = url_for('static', filename='uploads/' + filename)
    conn.execute(
        'UPDATE merchandise SET name=?, description=?, price=?, stock=?, category=?, image_url=? WHERE id=?',
        (request.form['name'], request.form['description'], request.form['price'],
         request.form['stock'], request.form['category'], image_url, item_id)
    )
    conn.commit()
    conn.close()
    flash('Shop item updated successfully!', 'success')
    return redirect(url_for('admin_shop'))


@app.route('/admin/shop/item/delete/<int:item_id>', methods=['POST'])
@admin_required
def admin_delete_shop_item(item_id):
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM merchandise WHERE id = ?', (item_id,))
        conn.commit()
        flash('Shop item deleted!', 'info')
    except sqlite3.IntegrityError:
        flash('Shop item cannot be deleted while order history still references it.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_shop'))


# ── Itinerary Editor ──────────────────────────────────────────────────────────
@app.route('/admin/trip/itinerary/<trip_id>')
@admin_required
def admin_edit_itinerary(trip_id):
    conn = get_db_connection()
    trip = conn.execute('SELECT * FROM trips WHERE id = ?', (trip_id,)).fetchone()
    conn.close()
    if not trip:
        flash('Trip not found', 'error')
        return redirect(url_for('admin_dashboard') + '#trips')
    return render_template('admin_itinerary_editor.html', trip=trip)


@app.route('/admin/trip/itinerary/update', methods=['POST'])
@admin_required
def admin_update_itinerary():
    trip_id    = request.form['trip_id']
    itinerary  = request.form['itinerary']
    highlights = request.form.get('highlights', '')
    conn       = get_db_connection()
    conn.execute('UPDATE trips SET itinerary = ?, highlights = ? WHERE id = ?',
                 (itinerary, highlights, trip_id))
    conn.commit()
    conn.close()
    flash('Itinerary updated successfully!', 'success')
    return redirect(url_for('admin_edit_itinerary', trip_id=trip_id))


# ── Legacy redirect shims ─────────────────────────────────────────────────────
@app.route('/admin/batches')
@admin_required
def admin_batches_index():
    flash('Select a trip from the Trips tab to manage its batches.', 'info')
    return redirect(url_for('admin_dashboard') + '#trips')


@app.route('/admin/batches/<trip_id>')
@admin_required
def admin_batches_legacy(trip_id):
    return redirect(url_for('admin_batches', trip_id=trip_id))


@app.route('/admin/bookings')
@admin_required
def admin_bookings_legacy():
    return redirect(url_for('admin_dashboard') + '#bookings_tab')


@app.route('/admin/event/edit', methods=['POST'])
@admin_required
def admin_edit_event_legacy():
    return admin_edit_event()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    logger.info(f"Booting database at: {app.config['DATABASE']}")
    init_db()
    app.run(
        debug=app.config.get('DEBUG', False),
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
