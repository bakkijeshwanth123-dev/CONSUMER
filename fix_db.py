import json

def fix_admin_json():
    with open('admin.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if 'admin' in data:
        for user_id, user_data in data['admin'].items():
            if 'password' in user_data and 'password_hash' not in user_data:
                user_data['password_hash'] = user_data.pop('password')
                print(f"Renamed password to password_hash for user {user_data.get('username')} ({user_id})")
            elif 'password' in user_data and 'password_hash' in user_data:
                # Both exist, delete the redundant 'password'
                user_data.pop('password')
                print(f"Removed redundant password for user {user_data.get('username')} ({user_id})")
    
    with open('admin.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print("Fixed admin.json")

if __name__ == "__main__":
    fix_admin_json()
