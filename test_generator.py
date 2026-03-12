import sys
from legal_notice_generator import generate_legal_notice
from database import complaints_table, admin_table, Query

def test_gen():
    try:
        # Create a mock complaint if none exist
        existing = complaints_table.all()
        if existing:
            c = existing[-1] # Take the last one
            c_id = c.get('id', 'mock_id')
            customer_name = "Test Customer"
            seller_name = "Test Seller"
            seller_address = "Test Address"
            
            print(f"Testing with complaint ID: {c_id}")
            t_id = generate_legal_notice(c_id, c, customer_name, seller_name, seller_address)
            print(f"Success! Tracking ID: {t_id}")
        else:
            print("No complaints found in DB.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_gen()
