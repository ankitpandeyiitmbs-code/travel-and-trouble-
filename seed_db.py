import sqlite3
import os
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'wanderbuddy.db')


def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # ── Initialize schema first so tables exist ──────────────────────────────
    schema_path = os.path.join(BASE_DIR, 'schema.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r') as f:
            conn.executescript(f.read())

    # ── New feature tables (from app.py migration) ───────────────────────────
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
        sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS event_chat_message (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        order_num INTEGER DEFAULT 0
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
        admin_note TEXT
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
        reason TEXT
    );
    """)

    # ── Add new columns to existing tables (ignore if already exist) ─────────
    for sql in [
        "ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0",
        "ALTER TABLE bookings ADD COLUMN wb_batch_id INTEGER",
        "ALTER TABLE events ADD COLUMN event_time TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass

    # ── Ensure site_settings row exists ──────────────────────────────────────
    conn.execute("""INSERT OR IGNORE INTO site_settings
        (id, site_title, hero_tagline, hero_subtext, email, phone, address,
         working_hours, year_established, logo_url, primary_color, font_family,
         instagram, twitter, facebook, youtube)
        VALUES (1,'Travel & Trouble','Where Adventure Meets Comfort',
        'Discover breathtaking destinations crafted for the modern explorer',
        'admin@travelandtrouble.com','+91 98765 43210','New Delhi, India',
        'Mon-Sat 9am-6pm',2022,'','#C4622D','DM Sans','','','','')"""
    )

    conn.commit()
    print("✅ Schema and new tables initialized.")

    # ── Users ─────────────────────────────────────────────────────────────────
    users = [
        ('Admin', 'admin@travelandtrouble.com', generate_password_hash('Admin@123'), None, 'admin'),
        ('Rahul Sharma', 'user@test.com', generate_password_hash('User@123'), '+91 99999 00000', 'traveler'),
        ('Priya Kapoor', 'vendor@test.com', generate_password_hash('Vendor@123'), '+91 88888 00000', 'vendor'),
    ]
    for u in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (name, email, password, phone, role) VALUES (?,?,?,?,?)", u)

    conn.commit()
    vendor_user = conn.execute("SELECT id FROM users WHERE email='vendor@test.com'").fetchone()
    if vendor_user:
        conn.execute(
            "INSERT OR IGNORE INTO vendor_profiles (user_id, business_name, business_type, verified) VALUES (?,?,?,?)",
            (vendor_user['id'], 'Mountain Gear Co', 'Equipment', 1))

    # ── Trips ─────────────────────────────────────────────────────────────────
    trips = [
        ('kedarkantha-trek', 'Kedarkantha Winter Trek', 8500, '6 Days',
         'https://images.unsplash.com/photo-1605493652047-19286d4b7e7e?w=800',
         'Trek', 'Experience the magic of a winter trek through dense oak and rhododendron forests to the summit of Kedarkantha at 12,500 ft. Witness breathtaking views of Swargarohini, Bandarpunch, and Ranglana peaks.',
         'Uttarakhand', 'Challenging',
         '[{"day":1,"title":"Sankri Base Camp","description":"Arrive at Sankri, acclimatize and explore the village."},{"day":2,"title":"Sankri to Juda Ka Talab","description":"Trek through pine and oak forests to the frozen lake camp."},{"day":3,"title":"Juda Ka Talab to Kedarkantha Base","description":"Gradual climb through snow-clad forests to base camp."},{"day":4,"title":"Summit Day","description":"Early morning summit attempt, panoramic views of the Himalayan peaks."},{"day":5,"title":"Base to Sankri","description":"Descend back to Sankri village."},{"day":6,"title":"Departure","description":"Drive back to Dehradun, end of trek."}]',
         'Snow-capped summit,Rhododendron forests,Himalayan panorama,Camping under stars'),
        ('triund', 'McLeodganj–Triund Trek', 7999, '4N/5D',
         'https://images.unsplash.com/photo-1598994606657-b2c0da9bdd8f?w=800',
         'Trek', 'Trek from the spiritual town of McLeodganj to the stunning Triund meadow with views of the Dhauladhar range. Perfect for beginners and photography enthusiasts.',
         'Himachal Pradesh', 'Moderate',
         '[{"day":1,"title":"Arrive McLeodganj","description":"Explore the Tibetan colony, Namgyal Monastery, and Bhagsu waterfall."},{"day":2,"title":"McLeodganj to Triund","description":"Trek through oak and rhododendron forests to the open meadow at 9350 ft."},{"day":3,"title":"Triund Sunrise & Descent","description":"Witness sunrise over Dhauladhar and trek back to McLeodganj."},{"day":4,"title":"Dharamshala Exploration","description":"Visit cricket stadium, War Memorial, and local markets."},{"day":5,"title":"Departure","description":"Head back home with memories."}]',
         'Dhauladhar views,Tibetan culture,Bhagsu waterfall,Meadow camping'),
        ('kheerganga', 'Kasol–Kheerganga Trek', 7999, '4N/5D',
         'https://images.unsplash.com/photo-1510797215324-95aa89f43c33?w=800',
         'Trek', 'Follow the Parvati Valley to the hot springs of Kheerganga. Trek through lush forests alongside the Parvati river with a vibrant backpacker culture.',
         'Himachal Pradesh', 'Moderate',
         '[{"day":1,"title":"Arrive Kasol","description":"Explore the Israeli Bakeries, Chalal village and Parvati river banks."},{"day":2,"title":"Trek to Kheerganga","description":"14 km trek through forests and waterfalls to the hot spring camp."},{"day":3,"title":"Hot Springs & Rest","description":"Soak in the natural hot springs and enjoy Himalayan views."},{"day":4,"title":"Descent to Kasol","description":"Trek back down through the forest trail."},{"day":5,"title":"Departure","description":"Drive to Bhuntar and onward journey."}]',
         'Natural hot springs,Parvati Valley,Waterfall trails,Backpacker culture'),
        ('jibhi', 'Jibhi–Tirthan Valley–Jalori Pass', 6999, '4N/5D',
         'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
         'Chill', 'Explore the hidden gem of Tirthan Valley, a UNESCO Biosphere Reserve. Perfect blend of relaxation, trout fishing, and light forest walks.',
         'Himachal Pradesh', 'Easy',
         '[{"day":1,"title":"Arrive Jibhi","description":"Check in to river-side cottage, explore Jibhi waterfall."},{"day":2,"title":"Tirthan Valley Walk","description":"Light walk along the Great Himalayan National Park boundaries, trout fishing."},{"day":3,"title":"Jalori Pass","description":"Drive and short trek to Jalori Pass (10,800 ft) and Serolsar Lake."},{"day":4,"title":"Chehni Kothi & Village Walk","description":"Visit the 1500-year-old Chehni tower and surrounding villages."},{"day":5,"title":"Departure","description":"Drive to Chandigarh or Kullu airport."}]',
         'UNESCO Biosphere,Trout fishing,Serolsar Lake,Heritage towers'),
        ('manali-solang', 'Manali–Solang Valley Adventure', 7999, '4N/5D',
         'https://images.unsplash.com/photo-1582719508461-905c673771fd?w=800',
         'Adventure', 'Adventure packed trip to Manali with snow activities in Solang Valley, Rohtang Pass visits, and river crossing. Perfect for thrill-seekers.',
         'Himachal Pradesh', 'Moderate',
         '[{"day":1,"title":"Arrive Manali","description":"Check in, evening stroll at Mall Road and Manu Temple."},{"day":2,"title":"Solang Valley","description":"Snow activities - skiing, zorbing, cable car rides and snowfall."},{"day":3,"title":"Rohtang Pass","description":"Day trip to Rohtang (subject to permit availability) or Beas Kund trek."},{"day":4,"title":"Old Manali & River Crossing","description":"Explore Old Manali, Hadimba Temple, river crossing activity."},{"day":5,"title":"Departure","description":"Drive back to Chandigarh."}]',
         'Snow activities,Rohtang Pass,River crossing,Hadimba Temple'),
        ('kareri-lake', 'Kareri Lake Trek', 7499, '4N/5D',
         'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=800',
         'Trek', 'Trek to the pristine glacial Kareri Lake at 9,800 ft through dense deodar forests. An off-the-beaten-path gem near Dharamshala.',
         'Himachal Pradesh', 'Challenging',
         '[{"day":1,"title":"Arrive Dharamshala","description":"Check in, evening explore McLeodganj markets."},{"day":2,"title":"Trek to Reru","description":"Drive to trailhead, trek 10 km to Reru village campsite."},{"day":3,"title":"Reru to Kareri Lake","description":"Steep climb through meadows to the beautiful glacial lake camp."},{"day":4,"title":"Exploration & Descent","description":"Morning exploration, afternoon descent to Reru."},{"day":5,"title":"Return to Dharamshala","description":"Trek out, drive back, departure."}]',
         'Glacial lake,Dense deodar forests,Off-beat trail,Dhauladhar base'),
        ('bir-billing', 'Bir Billing Paragliding Adventure', 7499, '4N/5D',
         'https://images.unsplash.com/photo-1530789253388-582c481c54b0?w=800',
         'Adventure', 'Soar over the tea gardens and valleys of Bir Billing, the paragliding capital of Asia. Includes a tandem paragliding flight and monastery visits.',
         'Himachal Pradesh', 'Moderate',
         '[{"day":1,"title":"Arrive Bir","description":"Check in to Tibetan colony guesthouse, explore tea gardens."},{"day":2,"title":"Paragliding Day","description":"Tandem paragliding from Billing (7000 ft) to Bir landing site."},{"day":3,"title":"Monastery Trail","description":"Cycling tour through Bir Tibetan colony, Chokling Monastery, and Palpung."},{"day":4,"title":"Leisure & Local Cuisine","description":"Morning yoga, explore local cafes and craft shops."},{"day":5,"title":"Departure","description":"Drive to Pathankot or Gaggal airport."}]',
         'Tandem paragliding,Tea gardens,Tibetan monasteries,Asia paragliding capital'),
        ('chopta-tungnath', 'Chopta–Tungnath–Chandrashila Trek', 8499, '4N/5D',
         'https://images.unsplash.com/photo-1544551763-46a013bb70d5?w=800',
         'Trek', 'Trek to the highest Shiva temple in the world at Tungnath (12,073 ft) and the spectacular Chandrashila summit with 360-degree Himalayan views.',
         'Uttarakhand', 'Challenging',
         '[{"day":1,"title":"Arrive Chopta","description":"Drive from Rishikesh through Ukhimath, arrive at Chopta meadows."},{"day":2,"title":"Tungnath Temple","description":"Trek 3.5 km to Tungnath, the highest Shiva shrine in the world."},{"day":3,"title":"Chandrashila Summit","description":"Early morning summit push to Chandrashila (13,123 ft) for sunrise views."},{"day":4,"title":"Deoria Tal","description":"Drive to Sari village, trek to the reflective Deoria Lake."},{"day":5,"title":"Rishikesh Return","description":"Drive back to Rishikesh, evening aarti at Triveni Ghat."}]',
         'Highest Shiva temple,360° Himalayan views,Deoria Lake,Ancient temples'),
    ]
    for t in trips:
        conn.execute(
            "INSERT OR IGNORE INTO trips (id,title,price,duration,image_url,category,description,location,difficulty,itinerary,highlights) VALUES (?,?,?,?,?,?,?,?,?,?,?)", t)

    # ── Old-style batches (batch_date system) ─────────────────────────────────
    batch_dates = ['2026-06-01', '2026-07-01', '2026-08-01']
    for trip_id, *_ in trips:
        for bd in batch_dates:
            conn.execute(
                "INSERT OR IGNORE INTO trip_batches (trip_id, batch_date, current_bookings, min_required, max_allowed, status) VALUES (?,?,0,6,16,'pending')",
                (trip_id, bd))

    # ── New-style WanderBuddy batches ─────────────────────────────────────────
    wb_batches = [
        ('kedarkantha-trek', 'Batch A – Jun 2026', '2026-06-01', '2026-06-06', 16, None),
        ('kedarkantha-trek', 'Batch B – Jul 2026', '2026-07-01', '2026-07-06', 16, 9200.0),
        ('triund',           'Batch A – Jun 2026', '2026-06-10', '2026-06-14', 20, None),
        ('manali-solang',    'Batch A – Aug 2026', '2026-08-05', '2026-08-09', 18, 8499.0),
    ]
    for trip_id, batch_name, start, end, seats, price_override in wb_batches:
        conn.execute(
            "INSERT OR IGNORE INTO trip_batch (trip_id, batch_name, start_date, end_date, max_seats, price_override, is_active) VALUES (?,?,?,?,?,?,1)",
            (trip_id, batch_name, start, end, seats, price_override))

    # ── Events ────────────────────────────────────────────────────────────────
    events = [
        ('stargazing-kasol', 'Stargazing Night Kasol', 2500, '1 Night',
         'https://images.unsplash.com/photo-1464802686167-b939a6910659?w=800',
         'Campside', 'Spend a magical night under the stars in Kasol. Guided stargazing session with telescope, bonfire, and astronomy talks by expert astronomers.',
         'Kasol', '2026-06-15',
         '[{"day":1,"title":"Evening Arrival","description":"Arrive by evening, set up camp and introductions."},{"day":2,"title":"Stargazing Night","description":"Full night session with telescope viewing, astronomy talks, and constellation mapping."}]'),
        ('river-rafting-rishikesh', 'River Rafting Weekend', 3500, '2 Days',
         'https://images.unsplash.com/photo-1530866495561-507c9faab2ed?w=800',
         'Adventure', 'Tackle the rapids of the Ganges in Rishikesh! Includes Grade 3-4 rapids, cliff jumping, camping on the riverbank, and beach volleyball.',
         'Rishikesh', '2026-07-10',
         '[{"day":1,"title":"Rafting Day 1","description":"Safety briefing, 16 km stretch rafting, beach camp."},{"day":2,"title":"Rafting Day 2","description":"Morning yoga, cliff jumping, 12 km rafting back to base."}]'),
        ('bonfire-camp', 'Bonfire Camping Night', 1999, '1 Night',
         'https://images.unsplash.com/photo-1487730116645-74489c55551f?w=800',
         'Camping', 'A cozy bonfire camping night in the forests near Bir. Includes dinner, bonfire storytelling, acoustic music session, and breakfast.',
         'Bir', '2026-06-20',
         '[{"day":1,"title":"Camp Night","description":"Arrive by evening, bonfire, dinner, storytelling, music, stargazing."}]'),
        ('yoga-retreat', 'Himalayan Yoga Retreat', 4500, '2 Days',
         'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
         'Wellness', 'A rejuvenating yoga and meditation retreat in the lap of the Himalayas near Dharamshala. Guided by certified yoga instructors with Ayurvedic meals.',
         'Dharamshala', '2026-07-05',
         '[{"day":1,"title":"Arrival & Morning Yoga","description":"Check-in, Hatha yoga session, Ayurvedic lunch, evening meditation."},{"day":2,"title":"Deep Practice","description":"Pranayama, Vinyasa flow, sound healing, departure post lunch."}]'),
        ('paragliding-trial', 'Paragliding Trial Day', 3000, '1 Day',
         'https://images.unsplash.com/photo-1530789253388-582c481c54b0?w=800',
         'Adventure', 'Your first paragliding experience! A full day at Billing with ground training, tandem flight over the Beas valley, and certificate of completion.',
         'Billing', '2026-08-01',
         '[{"day":1,"title":"Trial Day","description":"Ground school, equipment check, tandem flight from 7000 ft, landing practice."}]'),
    ]
    for e in events:
        conn.execute(
            "INSERT OR IGNORE INTO events (id,title,price,duration,image_url,category,description,location,event_date,itinerary) VALUES (?,?,?,?,?,?,?,?,?,?)", e)

    # ── Sample Adventure Activities ───────────────────────────────────────────
    activities = [
        ('kedarkantha-trek', 'Summit Selfie', 'Take a photo at the Kedarkantha summit marker', 'photo', 'At the summit cairn (12,500 ft)', 20, 10, 1, 1),
        ('kedarkantha-trek', 'Frozen Lake Reel', 'Record a 30-sec reel at Juda Ka Talab frozen lake', 'reel', 'Juda Ka Talab campsite', 25, 15, 1, 2),
        ('kedarkantha-trek', 'Local Cuisine Challenge', 'Try and photograph a traditional Garhwali meal', 'food', 'Any local dhaba in Sankri village', 15, 5, 1, 3),
        ('kedarkantha-trek', 'Snow Angel Creative', 'Make a snow angel and photograph it from above', 'creative', 'Any snow patch on Day 2-4', 10, 5, 1, 4),
        ('triund',           'Dhauladhar Panorama', 'Capture a wide-angle shot of the Dhauladhar range', 'photo', 'Triund meadow top', 20, 10, 1, 1),
        ('triund',           'Campfire Night Reel', 'Short reel of the campfire with starry sky', 'reel', 'Triund campsite', 20, 10, 1, 2),
    ]
    for trip_id, title, desc, atype, loc, pts, bonus, active, order in activities:
        conn.execute(
            "INSERT OR IGNORE INTO trip_activity (trip_id, title, description, activity_type, location_hint, points, bonus_points, is_active, order_num) VALUES (?,?,?,?,?,?,?,?,?)",
            (trip_id, title, desc, atype, loc, pts, bonus, active, order))

    # ── Sample Rewards ────────────────────────────────────────────────────────
    import random, string
    sample_rewards = [
        ('Early Bird Discount', '10% off on your next booking', 'discount', '10%', 50, None),
        ('Free WanderBuddy Hoodie', 'Win a WanderBuddy branded hoodie', 'gift', 'Hoodie worth ₹1599', 100, None),
        ('Free Trip Upgrade', 'Free room upgrade on any Kedarkantha batch', 'free_trip', 'Double sharing upgrade', 200, 'kedarkantha-trek'),
    ]
    for title, desc, rtype, value, min_pts, trip_id in sample_rewards:
        coupon = 'WB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        conn.execute(
            "INSERT OR IGNORE INTO reward (title, description, reward_type, value, coupon_code, min_points, trip_id, is_active) VALUES (?,?,?,?,?,?,?,1)",
            (title, desc, rtype, value, coupon, min_pts, trip_id))

    # ── Quests ────────────────────────────────────────────────────────────────
    quest_templates = [
        ('Sunrise Hiker', 50, 'fa-solid fa-sun'),
        ('Trail Photographer', 75, 'fa-solid fa-camera'),
        ('Summit Achiever', 100, 'fa-solid fa-mountain'),
    ]
    for trip_id, *_ in trips:
        for qt in quest_templates:
            existing = conn.execute("SELECT id FROM quests WHERE trip_id=? AND title=?", (trip_id, qt[0])).fetchone()
            if not existing:
                conn.execute("INSERT INTO quests (trip_id, title, points, icon) VALUES (?,?,?,?)", (trip_id, *qt))

    # ── Merchandise ───────────────────────────────────────────────────────────
    merch = [
        ('WanderBuddy Hoodie', 'Premium cotton blend hoodie with WanderBuddy logo. Perfect for chilly mountain evenings.', 1599, 50, 'Apparel',
         'https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400'),
        ('Adventure Flask', 'BPA-free 750ml insulated flask keeps drinks cold for 24hrs, hot for 12hrs.', 899, 100, 'Gear',
         'https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=400'),
        ('50L Trekking Backpack', 'Waterproof 50L backpack with hip belt, hydration sleeve and rain cover. Trail-tested.', 2999, 30, 'Gear',
         'https://images.unsplash.com/photo-1622560480654-d96214fdc887?w=400'),
        ('Trekking Poles (pair)', 'Lightweight aluminum collapsible trekking poles with cork grip and tungsten tips.', 1299, 40, 'Gear',
         'https://images.unsplash.com/photo-1551632811-561732d1e306?w=400'),
        ('Merino Wool Socks', '3-pack merino wool trekking socks. Anti-blister, moisture-wicking, odor-resistant.', 499, 200, 'Apparel',
         'https://images.unsplash.com/photo-1586350977771-b3b0abd50c82?w=400'),
        ('Beanie Cap', 'Warm fleece-lined beanie with WanderBuddy embroidery. One size fits all.', 399, 150, 'Apparel',
         'https://images.unsplash.com/photo-1520302519878-3acd5abfc5a7?w=400'),
        ('Headlamp 500 Lumen', 'Rechargeable LED headlamp with 500 lumen output, red night-vision mode, IPX6 waterproof.', 799, 60, 'Gear',
         'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400'),
        ('Quick-dry Towel', 'Super-absorbent microfiber travel towel. Dries 5x faster than cotton. Comes with carry pouch.', 599, 80, 'Accessories',
         'https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=400'),
    ]
    for m in merch:
        conn.execute(
            "INSERT OR IGNORE INTO merchandise (name, description, price, stock, category, image_url) VALUES (?,?,?,?,?,?)", m)

    # ── Addons ────────────────────────────────────────────────────────────────
    trip_ids_for_addons = ['kedarkantha-trek', 'triund']
    for tid in trip_ids_for_addons:
        v = conn.execute("SELECT id FROM users WHERE email='vendor@test.com'").fetchone()
        if v:
            existing = conn.execute("SELECT id FROM addons WHERE trip_id=? AND vendor_id=? AND title='Hotel Upgrade'", (tid, v['id'])).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO addons (trip_id, vendor_id, addon_type, title, price, description) VALUES (?,?,?,?,?,?)",
                    (tid, v['id'], 'hotel', 'Hotel Upgrade', 1500, 'Upgrade from tent/dormitory to a comfortable hotel room with attached bathroom.'))
                conn.execute(
                    "INSERT INTO addons (trip_id, vendor_id, addon_type, title, price, description) VALUES (?,?,?,?,?,?)",
                    (tid, v['id'], 'transport', 'Mountain Transport', 800, 'Private cab pickup and drop from nearest railway/bus station to trek base camp.'))

    # ── Site settings ─────────────────────────────────────────────────────────
    conn.execute("""
        INSERT OR IGNORE INTO site_settings
        (id, site_title, hero_tagline, hero_subtext, email, phone, address, working_hours, year_established,
         instagram, twitter, facebook, youtube, logo_url)
        VALUES (1, 'Travel & Trouble', 'Where Adventure Meets Comfort',
        'Discover breathtaking destinations crafted for the modern explorer',
        'admin@travelandtrouble.com', '+91 98765 43210', 'New Delhi, India',
        'Mon-Sat 9am-6pm', 2022,
        'https://instagram.com/travelandtrouble',
        'https://twitter.com/travelandtrouble',
        'https://facebook.com/travelandtrouble',
        'https://youtube.com/travelandtrouble',
        '')
    """)

    # ── Page content ──────────────────────────────────────────────────────────
    pages = {
        'about': (
            'About Travel & Trouble',
            '''<section class="py-5">
<div class="container">
<div class="row align-items-center mb-5">
<div class="col-lg-6">
<h1 class="display-4 fw-bold mb-3" style="color:var(--navy)">We Are Travel & Trouble</h1>
<p class="lead" style="color:var(--text-secondary)">Born from a love of mountains and the chaos of unforgettable journeys, Travel & Trouble curates experiences that push boundaries and create lifelong memories.</p>
<p>Founded in 2022, we started as a small group of trekking enthusiasts who believed travel should be more than checking tourist boxes. Today we have guided over 5,000 travelers across the Himalayas, organizing treks, events, and adventures that transform ordinary people into extraordinary explorers.</p>
</div>
<div class="col-lg-6"><img src="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=600" class="img-fluid rounded-3 shadow" alt="About us"></div>
</div>
<div class="row g-4 mb-5">
<div class="col-md-4 text-center"><div class="p-4 rounded-3" style="background:var(--terra-dim)"><h2 class="display-5 fw-bold" style="color:var(--terra)">5000+</h2><p class="mb-0">Happy Travelers</p></div></div>
<div class="col-md-4 text-center"><div class="p-4 rounded-3" style="background:var(--terra-dim)"><h2 class="display-5 fw-bold" style="color:var(--terra)">50+</h2><p class="mb-0">Unique Trips</p></div></div>
<div class="col-md-4 text-center"><div class="p-4 rounded-3" style="background:var(--terra-dim)"><h2 class="display-5 fw-bold" style="color:var(--terra)">4.9★</h2><p class="mb-0">Average Rating</p></div></div>
</div>
<h2 class="fw-bold mb-4" style="color:var(--navy)">Our Values</h2>
<div class="row g-4">
<div class="col-md-4"><h5><i class="fa-solid fa-leaf me-2" style="color:var(--terra)"></i>Responsible Travel</h5><p style="color:var(--text-secondary)">We follow Leave No Trace principles and contribute to local communities on every trip.</p></div>
<div class="col-md-4"><h5><i class="fa-solid fa-shield-halved me-2" style="color:var(--terra)"></i>Safety First</h5><p style="color:var(--text-secondary)">All our trek leaders are certified in wilderness first aid. Safety is never compromised.</p></div>
<div class="col-md-4"><h5><i class="fa-solid fa-people-group me-2" style="color:var(--terra)"></i>Community</h5><p style="color:var(--text-secondary)">We believe travel is better together. Our Explorer community stays connected long after the trip ends.</p></div>
</div>
</div>
</section>'''
        ),
        'privacy': (
            'Privacy Policy',
            '''<div class="container py-5"><div class="row"><div class="col-lg-8 mx-auto">
<h1 class="fw-bold mb-4" style="color:var(--navy)">Privacy Policy</h1>
<p class="text-muted">Last updated: January 2025</p>
<h4 class="mt-4 mb-3">1. Information We Collect</h4>
<p>We collect information you provide directly to us, such as name, email address, phone number, and payment information when you create an account or make a booking.</p>
<h4 class="mt-4 mb-3">2. How We Use Your Information</h4>
<p>We use the information we collect to provide, maintain and improve our services, process transactions, send trip confirmations and updates, and communicate with you about our products and services.</p>
<h4 class="mt-4 mb-3">3. Information Sharing</h4>
<p>We do not sell, trade, or otherwise transfer your personally identifiable information to outside parties except to trusted third parties who assist us in operating our website and servicing you, so long as those parties agree to keep this information confidential.</p>
<h4 class="mt-4 mb-3">4. Data Security</h4>
<p>We implement a variety of security measures to maintain the safety of your personal information. Your personal information is contained behind secured networks and is only accessible by a limited number of persons who have special access rights.</p>
<h4 class="mt-4 mb-3">5. Contact Us</h4>
<p>If you have any questions about this Privacy Policy, please contact us at admin@travelandtrouble.com.</p>
</div></div></div>'''
        ),
        'terms': (
            'Terms & Conditions',
            '''<div class="container py-5"><div class="row"><div class="col-lg-8 mx-auto">
<h1 class="fw-bold mb-4" style="color:var(--navy)">Terms & Conditions</h1>
<p class="text-muted">Last updated: January 2025</p>
<h4 class="mt-4 mb-3">1. Booking Policy</h4>
<p>All bookings are subject to availability. A trip batch is confirmed once a minimum of 6 participants have booked. If the minimum is not reached 7 days before departure, affected travelers will receive a full refund or may transfer to another batch.</p>
<h4 class="mt-4 mb-3">2. Cancellation Policy</h4>
<p>Cancellations made 15+ days before departure: 90% refund. Cancellations 8-14 days before: 50% refund. Cancellations within 7 days: no refund. No-shows: no refund.</p>
<h4 class="mt-4 mb-3">3. Health & Fitness</h4>
<p>Participants must be in good physical health. Medical conditions that may be affected by strenuous activity or high altitude must be disclosed at the time of booking. Travel & Trouble reserves the right to refuse participation on safety grounds.</p>
<h4 class="mt-4 mb-3">4. Liability</h4>
<p>Travel & Trouble acts as a booking agent and is not liable for injury, loss, damage, accident, illness, or any other unforeseen circumstances. All travelers participate at their own risk.</p>
<h4 class="mt-4 mb-3">5. Code of Conduct</h4>
<p>All participants are expected to respect fellow travelers, local communities, and the natural environment. Disruptive behavior may result in removal from the trip without refund.</p>
</div></div></div>'''
        ),
        'home': (
            'Home',
            '<p>Welcome to Travel & Trouble — Where Adventure Meets Comfort.</p>'
        ),
    }
    for pname, (ptitle, pcontent) in pages.items():
        conn.execute(
            "INSERT OR IGNORE INTO page_content (page_name, title, content) VALUES (?,?,?)",
            (pname, ptitle, pcontent))

    conn.commit()
    conn.close()
    print("✅ Database seeded successfully!")
    print()
    print("─── Demo Login Credentials ───────────────────")
    print("  Admin  : admin@travelandtrouble.com / Admin@123")
    print("  User   : user@test.com              / User@123")
    print("  Vendor : vendor@test.com            / Vendor@123")
    print("──────────────────────────────────────────────")


if __name__ == '__main__':
    seed()