PRAGMA foreign_keys = ON;


-- 1. USERS (with role column)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    phone TEXT,
    role TEXT DEFAULT 'traveler',  -- 'traveler', 'vendor', 'admin'
    reset_token TEXT,
    reset_expiry DATETIME
);

-- 2. TRIPS (with extended columns)
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    duration TEXT NOT NULL,
    image_url TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    location TEXT DEFAULT 'Unknown',
    difficulty TEXT DEFAULT 'Moderate',
    itinerary TEXT DEFAULT 'Itinerary coming soon.',
    highlights TEXT
);

-- 3. BOOKINGS
CREATE TABLE IF NOT EXISTS bookings (
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
);

-- 4. MESSAGES (Chat with msg_type)
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    sender TEXT NOT NULL,
    content TEXT NOT NULL,
    msg_type TEXT DEFAULT 'text',  -- 'text' or 'image'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- 5. QUESTS
CREATE TABLE IF NOT EXISTS quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT NOT NULL,
    title TEXT NOT NULL,
    points INTEGER NOT NULL,
    icon TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips (id)
);

-- 6. USER QUESTS
CREATE TABLE IF NOT EXISTS user_quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    quest_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    proof_image TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings (id),
    FOREIGN KEY (quest_id) REFERENCES quests (id)
);

-- 7. VENDOR PROFILES
CREATE TABLE IF NOT EXISTS vendor_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    business_name TEXT NOT NULL,
    business_type TEXT,
    verified BOOLEAN DEFAULT 0,
    payout_details TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- 8. ADDONS (for vendor marketplace)
CREATE TABLE IF NOT EXISTS addons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT NOT NULL,
    vendor_id INTEGER NOT NULL,
    addon_type TEXT NOT NULL, -- 'hotel', 'transport', 'activity'
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    description TEXT,
    FOREIGN KEY(trip_id) REFERENCES trips(id),
    FOREIGN KEY(vendor_id) REFERENCES users(id)
);

-- 9. BOOKING ADDONS (links traveler purchases to bookings)
CREATE TABLE IF NOT EXISTS booking_addons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    addon_id INTEGER NOT NULL,
    FOREIGN KEY(booking_id) REFERENCES bookings(id),
    FOREIGN KEY(addon_id) REFERENCES addons(id)
);

-- 10. MERCHANDISE (Shop)
CREATE TABLE IF NOT EXISTS merchandise (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    price INTEGER NOT NULL,
    stock INTEGER DEFAULT 0,
    category TEXT,
    image_url TEXT
);

-- 11. SHOP ORDERS
CREATE TABLE IF NOT EXISTS shop_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT DEFAULT 'processing',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- 12. SHOP ORDER ITEMS
CREATE TABLE IF NOT EXISTS shop_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    price_at_purchase REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES shop_orders (id),
    FOREIGN KEY (item_id) REFERENCES merchandise (id)
);

-- 13. SUBSCRIPTIONS (Explorer Pass)
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_name TEXT DEFAULT 'Explorer Pass',
    status TEXT DEFAULT 'active',
    valid_until DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- 14. POSTS (Community)
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    image_url TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    video_url TEXT,
    tag TEXT DEFAULT 'General',
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- 15. SITE SETTINGS
CREATE TABLE IF NOT EXISTS site_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    phone TEXT,
    email TEXT,
    address TEXT,
    instagram TEXT,
    twitter TEXT,
    facebook TEXT,
    youtube TEXT,
    working_hours TEXT,
    year_established INTEGER,
    logo_url TEXT DEFAULT '',
    primary_color TEXT DEFAULT '#1a1a2e',
    secondary_color TEXT DEFAULT '#16213e',
    accent_color TEXT DEFAULT '#e8c547',
    font_family TEXT DEFAULT 'DM Sans',
    hero_tagline TEXT DEFAULT 'Where Adventure Meets Comfort',
    hero_subtext TEXT DEFAULT 'Discover breathtaking destinations crafted for the modern explorer',
    site_title TEXT DEFAULT 'Travel & Trouble'
);

-- 16. PAGE CONTENT (Editable CMS Pages)
CREATE TABLE IF NOT EXISTS page_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_name TEXT NOT NULL UNIQUE,
    title TEXT,
    content TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 17. CONTACT MESSAGES
CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    subject TEXT DEFAULT 'other',
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 18. EVENTS TABLE
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    price INTEGER NOT NULL,
    duration TEXT NOT NULL,
    image_url TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    location TEXT,
    event_date TEXT,
    itinerary TEXT
);



-- 17. TRIP BATCHES (Batch Management for Group Bookings)
CREATE TABLE IF NOT EXISTS trip_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT NOT NULL,
    batch_date TEXT NOT NULL,
    current_bookings INTEGER DEFAULT 0,
    min_required INTEGER DEFAULT 6,
    max_allowed INTEGER DEFAULT 16,
    status TEXT DEFAULT 'pending', -- pending, confirmed, completed, cancelled
    UNIQUE(trip_id, batch_date),
    FOREIGN KEY(trip_id) REFERENCES trips(id)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_bookings_trip_id ON bookings(trip_id);
CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_quests_trip_id ON quests(trip_id);
CREATE INDEX IF NOT EXISTS idx_user_quests_booking_id ON user_quests(booking_id);
CREATE INDEX IF NOT EXISTS idx_addons_vendor_id ON addons(vendor_id);
CREATE INDEX IF NOT EXISTS idx_addons_trip_id ON addons(trip_id);
CREATE INDEX IF NOT EXISTS idx_shop_orders_user_id ON shop_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp);
