"""
add_test_bookings.py - Add test users and bookings for chat feature testing
Run: python add_test_bookings.py
"""
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

DB_PATH = os.environ.get("DATABASE_URL", "wanderbuddy.db")

def add_test_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Create test users
    users = [
        ('Test User 1', 'testuser1@test.com', generate_password_hash('Test@123'), '+91 99999 11111', 'traveler'),
        ('Test User 2', 'testuser2@test.com', generate_password_hash('Test@123'), '+91 99999 22222', 'traveler'),
    ]
    
    for user in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (name, email, password, phone, role) VALUES (?,?,?,?,?)", user)
    
    conn.commit()
    
    # Get user IDs
    user1 = conn.execute("SELECT id FROM users WHERE email='testuser1@test.com'").fetchone()
    user2 = conn.execute("SELECT id FROM users WHERE email='testuser2@test.com'").fetchone()
    
    if not user1 or not user2:
        print("Error: Could not create or find test users")
        conn.close()
        return
    
    # Get a trip ID and batch
    trip = conn.execute("SELECT id FROM trips LIMIT 1").fetchone()
    if not trip:
        print("Error: No trips found in database")
        conn.close()
        return
    
    trip_id = trip['id']
    
    # Get or create a WanderBuddy batch for this trip (for chat feature)
    wb_batch = conn.execute("SELECT * FROM trip_batch WHERE trip_id=? LIMIT 1", (trip_id,)).fetchone()
    if not wb_batch:
        # Create a WanderBuddy batch if none exists
        start_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d')
        conn.execute(
            "INSERT INTO trip_batch (trip_id, batch_name, start_date, end_date, max_seats, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (trip_id, 'Test Batch for Chat', start_date, end_date, 20))
        conn.commit()
        wb_batch = conn.execute("SELECT * FROM trip_batch WHERE trip_id=? LIMIT 1", (trip_id,)).fetchone()
    
    wb_batch_id = wb_batch['id']
    
    # Get a batch date for old system compatibility
    batch = conn.execute("SELECT * FROM trip_batches WHERE trip_id=? LIMIT 1", (trip_id,)).fetchone()
    if not batch:
        # Create a test batch if none exists
        batch_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        conn.execute(
            "INSERT INTO trip_batches (trip_id, batch_date, current_bookings, min_required, max_allowed, status) VALUES (?, ?, 0, 6, 16, 'pending')",
            (trip_id, batch_date))
        conn.commit()
        batch = conn.execute("SELECT * FROM trip_batches WHERE trip_id=? LIMIT 1", (trip_id,)).fetchone()
    
    batch_date = batch['batch_date']
    
    # Create bookings for both users on the same batch with wb_batch_id for chat
    bookings = [
        (user1['id'], trip_id, 'trip', batch_date, 'confirmed', None, 2, wb_batch_id),
        (user2['id'], trip_id, 'trip', batch_date, 'confirmed', None, 2, wb_batch_id),
    ]
    
    for booking in bookings:
        conn.execute(
            "INSERT OR IGNORE INTO bookings (user_id, trip_id, booking_type, batch_date, status, payment_id, num_travelers, wb_batch_id) VALUES (?,?,?,?,?,?,?,?)",
            booking)
    
    # Update batch current_bookings
    conn.execute("UPDATE trip_batches SET current_bookings = current_bookings + 2 WHERE trip_id=? AND batch_date=?", (trip_id, batch_date))
    
    conn.commit()
    conn.close()
    
    print("✅ Test data added successfully!")
    print()
    print("─── Test Login Credentials ───────────────────")
    print("  User 1 : testuser1@test.com / Test@123")
    print("  User 2 : testuser2@test.com / Test@123")
    print("──────────────────────────────────────────────")
    print(f"  Both users booked trip: {trip_id}")
    print(f"  Batch date: {batch_date}")
    print("──────────────────────────────────────────────")

if __name__ == "__main__":
    add_test_data()
