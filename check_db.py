from database import admin_table, db
print(f"DB Path: {db._storage._handle.name}")
print(f"Admin Table: {admin_table}")
print(f"User count: {len(admin_table.all())}")
