import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = 'wanderbuddy.db'

def seed():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("🌱 Starting Data Seeding...")

    # 1. Admin User
    admin_email = 'ankit.pandeyiitmbs@gmail.com'
    admin_pass = generate_password_hash('200328')
    cursor.execute("INSERT OR IGNORE INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                   ('Admin', admin_email, admin_pass, 'admin'))
    print("✅ Admin user checked.")

    # 2. Sample Trips
    trips = [
        ('T001', 'Kedarkantha Winter Trek', 8500, '6 Days', 'https://images.unsplash.com/photo-1589182373726-e4f658ab50f0', 'Trek', 'Experience the magic of snow in Uttrakhand.', 'Uttrakhand', 'Moderate', 'Day 1: Arrival... Day 2: Base Camp...', 'Snow Peaks, Pine Forests, Summit View'),
        ('T002', 'Hampta Pass Adventure', 9500, '5 Days', 'https://images.unsplash.com/photo-1544123553-ad350cd5893d', 'Expedition', 'The dramatic shift from green Manali to desert Spiti.', 'Himachal', 'Moderate-Difficult', 'Day 1: Manali to Chika...', 'Crossover pass, Glacial valleys'),
        ('T003', 'Valley of Flowers', 12000, '7 Days', 'https://images.unsplash.com/photo-1596395817117-98782ee20fb1', 'Trek', 'A UNESCO world heritage site blooming with alpine flowers.', 'Uttrakhand', 'Easy-Moderate', 'Day 1: Haridwar to Joshimath...', 'Brahma Kamal, Alpine blooms, Hemkund Sahib')
    ]
    for t in trips:
        cursor.execute("INSERT OR IGNORE INTO trips (id, title, price, duration, image_url, category, description, location, difficulty, itinerary, highlights) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", t)
    print(f"✅ {len(trips)} Trips seeded.")

    # 3. Sample Events
    events = [
        ('E001', 'Stargazing in Kasol', 2500, '1 Night', 'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b', 'Campside', 'A night under the stars with live music and bonfire.', 'Kasol', '2026-05-15', 'Arrival at 4 PM, Music at 7 PM...'),
        ('E002', 'River Rafting Weekend', 3500, '2 Days', 'https://images.unsplash.com/photo-1530866495547-08b978dd8c70', 'Adventure', 'Professional grade rafting in the Ganges.', 'Rishikesh', '2026-06-10', 'Safety briefing, 16km run...')
    ]
    for e in events:
        cursor.execute("INSERT OR IGNORE INTO events (id, title, price, duration, image_url, category, description, location, event_date, itinerary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", e)
    print(f"✅ {len(events)} Events seeded.")

    # 4. Sample Merchandise
    items = [
        ('WanderBuddy Hoodie', 'Premium matte finish hoodie with embroidered logo.', 1599, 50, 'Apparel', 'https://images.unsplash.com/photo-1556821840-3a63f95609a7'),
        ('Adventure Flask', 'Vacuum insulated 750ml flask for high altitudes.', 899, 100, 'Gear', 'https://images.unsplash.com/photo-1517332264161-128f73121028')
    ]
    for i in items:
        cursor.execute("INSERT OR IGNORE INTO merchandise (name, description, price, stock, category, image_url) VALUES (?, ?, ?, ?, ?, ?)", i)
    print(f"✅ {len(items)} Shop items seeded.")

    # 5. Trip Batches (Required for bookings)
    batches = [
        ('T001', '2026-05-01', 0, 6, 16, 'pending'),
        ('T001', '2026-05-15', 0, 6, 16, 'pending'),
        ('T002', '2026-06-01', 0, 8, 20, 'pending')
    ]
    for b in batches:
        cursor.execute("INSERT OR IGNORE INTO trip_batches (trip_id, batch_date, current_bookings, min_required, max_allowed, status) VALUES (?, ?, ?, ?, ?, ?)", b)
    print(f"✅ {len(batches)} Trip Batches seeded.")

    conn.commit()
    conn.close()
    print("\n🚀 Seeding Complete! Enjoy your premium Matte Alpine experience.")

if __name__ == '__main__':
    seed()
