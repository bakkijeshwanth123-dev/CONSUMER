"""
Test script to verify secrets routes are properly loaded
"""
from app import app

print("=" * 60)
print("CHECKING SECRETS ROUTES")
print("=" * 60)

# List all routes containing 'secret'
secret_routes = [rule for rule in app.url_map.iter_rules() if 'secret' in rule.rule.lower()]

if secret_routes:
    print(f"\nFound {len(secret_routes)} secret-related routes:")
    for rule in secret_routes:
        print(f"  - {rule.rule} -> {rule.endpoint} (methods: {rule.methods})")
else:
    print("\n❌ No secret routes found!")

# Check if manage_secrets function exists
try:
    from routes_secrets import manage_secrets, view_secret
    print("\n✅ routes_secrets module imported successfully")
    print(f"   - manage_secrets function: {manage_secrets}")
    print(f"   - view_secret function: {view_secret}")
except Exception as e:
    print(f"\n❌ Error importing routes_secrets: {e}")

print("\n" + "=" * 60)
print("RECOMMENDATION:")
print("=" * 60)
print("1. Stop the Flask server (Ctrl+C)")
print("2. Run: python main.py")
print("3. Navigate to: http://localhost:5000/secrets")
print("=" * 60)
