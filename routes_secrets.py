"""
Secure Secrets Management Routes
Allows users to encrypt and share secrets using Serpent encryption
"""
from flask import render_template, request, redirect, url_for, flash, session
from tinydb import Query
from datetime import datetime
import uuid
import base64

from app import app
from database import secrets_table, admin_table
from auth_utils import login_required
from app_utils import log_action
from serpent import serpent_encrypt, serpent_decrypt

@app.route('/secrets', methods=['GET', 'POST'])
@login_required
def manage_secrets():
    """Manage encrypted secrets - share and view"""
    user_id = session['user_id']
    username = session['username']
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'share':
            recipient_username = request.form.get('recipient')
            secret_name = request.form.get('secret_name', '').strip()
            secret_data = request.form.get('secret_data', '').strip()
            
            if not all([recipient_username, secret_name, secret_data]):
                flash('All fields are required.', 'danger')
                return redirect(url_for('manage_secrets'))
            
            # Get recipient info
            recipient = admin_table.search(Query().username == recipient_username)
            if not recipient:
                flash('Recipient not found.', 'danger')
                return redirect(url_for('manage_secrets'))
            
            recipient = recipient[0]
            
            # Encrypt the secret using Serpent
            # Use a combination of sender and recipient IDs as key
            encryption_key = f"{user_id}:{recipient['id']}".encode('utf-8')
            encrypted_data = serpent_encrypt(secret_data.encode('utf-8'), encryption_key)
            encrypted_b64 = base64.b64encode(encrypted_data).decode('utf-8')
            
            # Store the encrypted secret
            secret_id = str(uuid.uuid4())
            secret_record = {
                'id': secret_id,
                'name': secret_name,
                'encrypted_data': encrypted_b64,
                'sender_id': user_id,
                'sender_name': session.get('full_name', username),
                'recipient_id': recipient['id'],
                'recipient_name': recipient.get('full_name', recipient_username),
                'created_at': datetime.now().isoformat(),
                'viewed': False
            }
            
            secrets_table.insert(secret_record)
            log_action(user_id, 'share_secret', f'Shared secret "{secret_name}" with {recipient_username}')
            
            flash(f'Secret "{secret_name}" encrypted and shared with {recipient_username}!', 'success')
            return redirect(url_for('manage_secrets'))
    
    # GET: Display secrets
    # Get secrets received by this user
    received_secrets = secrets_table.search(Query().recipient_id == user_id)
    
    # Get secrets sent by this user
    sent_secrets = secrets_table.search(Query().sender_id == user_id)
    
    # Get all users for the recipient dropdown
    all_users = admin_table.all()
    # Exclude current user from recipients
    all_users = [u for u in all_users if u.get('id') != user_id]
    
    return render_template('secrets.html',
                         received_secrets=received_secrets,
                         sent_secrets=sent_secrets,
                         all_users=all_users)

@app.route('/secrets/view/<secret_id>')
@login_required
def view_secret(secret_id):
    """View and decrypt a secret"""
    user_id = session['user_id']
    
    # Find the secret
    secret = secrets_table.search(Query().id == secret_id)
    if not secret:
        flash('Secret not found.', 'danger')
        return redirect(url_for('manage_secrets'))
    
    secret = secret[0]
    
    # Verify user is the recipient
    if secret['recipient_id'] != user_id:
        flash('You are not authorized to view this secret.', 'danger')
        return redirect(url_for('manage_secrets'))
    
    # Decrypt the secret
    encryption_key = f"{secret['sender_id']}:{secret['recipient_id']}".encode('utf-8')
    encrypted_data = base64.b64decode(secret['encrypted_data'])
    
    try:
        decrypted_data = serpent_decrypt(encrypted_data, encryption_key).decode('utf-8')
    except Exception as e:
        flash(f'Error decrypting secret: {str(e)}', 'danger')
        return redirect(url_for('manage_secrets'))
    
    # Mark as viewed
    secrets_table.update({'viewed': True}, Query().id == secret_id)
    log_action(user_id, 'view_secret', f'Viewed secret "{secret["name"]}"')
    
    return render_template('view_secret.html',
                         secret=secret,
                         decrypted_data=decrypted_data)
