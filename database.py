from tinydb import TinyDB, Query
import os

# Base directory for absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize TinyDB tables
try:
    db_path = os.path.join(BASE_DIR, 'admin.json')
    db = TinyDB(db_path)
    admin_table = db.table('admin')
    maintenance_table = db.table('maintenance')
    files_table = db.table('files')
    secrets_table = db.table('secrets')
    logs_table = db.table('logs')
    backups_table = db.table('backups')
    config_table = db.table('config')
    ai_training_table = db.table('ai_training_data')
    complaints_table = db.table('complaints')
    complaint_history_table = db.table('complaint_history')
    password_resets_table = db.table('password_resets')
    notifications_table = db.table('notifications')
    chat_messages_table = db.table('chat_messages')
    whatsapp_contacts_table = db.table('whatsapp_contacts')
    refunds_table = db.table('refunds')
    
    # Salary DB
    salary_db_path = os.path.join(BASE_DIR, 'salary_db.json')
    salary_db = TinyDB(salary_db_path)
    bank_details_table = salary_db.table('bank_details')
    salary_payments_table = salary_db.table('salary_payments')

except Exception as e:
    print(f"Error initializing TinyDB: {e}")

# Re-exporting Query as TinyQuery if needed for consistency during transition
TinyQuery = Query
