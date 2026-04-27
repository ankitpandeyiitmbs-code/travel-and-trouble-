import sqlite3

def create_test_booking():
    conn = sqlite3.connect('wanderbuddy.db')
    try:
        # User ID 2 is user@test.com
        # Trip 'triund' on '2026-06-01' is Batch ID 4
        conn.execute("""
            INSERT INTO bookings (
                user_id, trip_id, booking_type, batch_date, 
                num_travelers, sharing_type, price_per_person, 
                total_price, status, wb_batch_id, payment_id
            ) VALUES (2, 'triund', 'trip', '2026-06-01', 1, 'double', 8000, 8000, 'confirmed', 4, 'TEST_PAY_123')
        """)
        conn.commit()
        print("Success: Test booking created for user ID 2 (user@test.com) on Triund trek.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    create_test_booking()
