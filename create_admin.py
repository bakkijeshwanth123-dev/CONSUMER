"""
Quick script to create an admin user in the TinyDB database
"""
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash
from tinydb import TinyDB

# Connect to database
db = TinyDB('admin.json')
admin_table = db.table('admin')

# Create admin user
admin_id = str(uuid.uuid4())
admin_user = {
    'id': admin_id,
    'username': 'admin',
    'email': 'admin@system.local',
    'password_hash': generate_password_hash('Admin@123'),
    'role': 'admin',
    'full_name': 'System Administrator',
    'phone': '',
    'legal_consent_at': datetime.now().isoformat(),
    'created_at': datetime.now().isoformat(),
    'is_active': True
}

# Insert admin user
admin_table.insert(admin_user)

print("✅ Admin user created successfully!")
print(f"📧 Email: admin@system.local")
print(f"🔑 Password: Admin@123")
print(f"👤 Username: admin")
print(f"\n⚠️  Please change the password after first login!")
