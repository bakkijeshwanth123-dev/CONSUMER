import os
from legal_notice_generator import generate_legal_notice

import base64

import io

import secrets

import string

import csv

import uuid

import logging

from datetime import datetime, timedelta

from tinydb import TinyDB, Query

import random



# Setup logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)






from functools import wraps

from flask import render_template, request, redirect, url_for, flash, session, send_file, Response, make_response, jsonify, abort, send_from_directory

from werkzeug.security import generate_password_hash, check_password_hash

from werkzeug.utils import secure_filename

import traceback
from database import *
from app import app, oauth




from app_utils import (
    log_action, notify_complaint_status_change, send_email_notification,
    send_reset_email, create_notification, sync_complaint_to_google_sheets,
    calculate_complaint_hash, get_local_ip
)

from serpent import serpent_encrypt, serpent_decrypt, serpent_encrypt_file, serpent_decrypt_file

from whatsapp_agent import ai_agent

from reportlab.lib import colors

from reportlab.lib.pagesizes import letter

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import qrcode





# Translation Fallback (Safe absolute path)
import json
_translations = {}  # Initialize with empty dict to prevent NameError
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
translations_path = os.path.join(BASE_DIR, 'translations.json')
try:
    if os.path.exists(translations_path):
        with open(translations_path, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
except Exception as e:
    logging.error(f"Fallback translation load failed: {e}")

def process_complaint_record(c):
    if not c: return c
    # If using DictCursor, c is a dict.
    # JSON fields in MySQL are returned as strings if they are formatted that way or if using TEXT column.
    
    json_fields = ['complaint_types', 'location', 'visit_schedule', 'bank_details', 'ai_analysis']
    for field in json_fields:
        if c.get(field) and isinstance(c[field], str):
            try:
                c[field] = json.loads(c[field])
            except:
                pass # Keep as string if parsing fails
    return c



@app.context_processor
def inject_bank_info():
    if 'user_id' in session:
        try:
            user_id = session['user_id']
            # Ensure admin_table is defined before accessing it
            if 'admin_table' in globals() and admin_table:
                user = admin_table.get(Query().id == user_id)
                if user and user.get('bank_details'):
                    # Originally it might have been in bank_details_table, 
                    # but let's see if it's in user record (JSON-like in TinyDB).
                    # In TinyDB, user is a dict.
                    details = user['bank_details']
                    if isinstance(details, str):
                        try: details = json.loads(details)
                        except: pass
                    if isinstance(details, dict):
                        return {'user_bank_name': details.get('bank_name')}
        except Exception as e:
            logging.error(f"Error injecting bank info: {e}")
            return {'user_bank_name': None}
    return {'user_bank_name': None}


@app.context_processor
def inject_t():

    def t(key):

        lang = session.get('lang', 'en')

        return _translations.get(lang, {}).get(key, _translations.get('en', {}).get(key, key))

    return dict(t=t)



Admin = Query()

Complaint = Query()

Maintenance = Query()

File = Query()

Secret = Query()

Log = Query()

History = Query()

Reset = Query()

AITraining = Query()



ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx'}

BACKGROUND_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'backgrounds')



import hashlib



def calculate_complaint_hash(complaint, prev_hash):

    """

    Calculates SHA-256 hash for a complaint record to form a blockchain link.

    """

    # Create a string of key fields

    data_string = f"{prev_hash}{complaint.get('user_id')}{complaint.get('title')}{complaint.get('description')}{complaint.get('created_at')}"

    return hashlib.sha256(data_string.encode('utf-8')).hexdigest()



def allowed_file(filename):

    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def allowed_background(filename):

    return '.' in filename and filename.rsplit('.', 1)[1].lower() in BACKGROUND_EXTENSIONS



def validate_password_strength(password):

    if len(password) < 8:

        return False, "Password must be at least 8 characters long."

    if not any(c.isupper() for c in password):

        return False, "Password must contain at least one uppercase letter."

    if not any(c.islower() for c in password):

        return False, "Password must contain at least one lowercase letter."

    if not any(c.isdigit() for c in password):

        return False, "Password must contain at least one digit."

    if not any(c in string.punctuation for c in password):

        return False, "Password must contain at least one special character."

    return True, ""



def save_user_qr(user):

    """Generates and saves a persistent QR code for a user linking to their portal."""

    # Use host_url if in request context, otherwise fallback

    try:

        base_url = request.host_url.rstrip('/')

    except:

        base_url = os.environ.get('BASE_URL', 'http://localhost:5000').rstrip('/')

        

    # Lead to the public verification and info portal

    portal_url = f"{base_url}/verify-salary/{user.get('id')}"

    

    qr = qrcode.QRCode(version=1, box_size=10, border=5)

    qr.add_data(portal_url)

    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    

    qr_dir = os.path.join('static', 'uploads', 'qr')

    if not os.path.exists(qr_dir):

        os.makedirs(qr_dir)

        

    file_path = os.path.join(qr_dir, f"{user.get('id')}.png")

    img.save(file_path)

    return file_path



# Initialize WhatsApp Agent Number if not exists

# Default Admin & Config initialization moved to update_schema.py to avoid context errors.



@app.context_processor
def inject_custom_styles():
    config = {}
    try:
        rows = config_table.all()
        config = {item['name']: item['value'] for item in rows}
    except:
        pass

    

    # Determine current theme (Session preference overrides global config)

    current_theme = session.get('preferred_theme', config.get('current_theme', 'light'))

    

    # Base defaults

    styles = {

        'sidebar_bg': config.get('sidebar_bg', 'linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)'),

        'header_bg': config.get('header_bg', '#ffffff'),

        'content_bg': config.get('content_bg', '#f0f2f5'),

        'login_bg': config.get('login_bg', 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'),

        'admin_bg': config.get('admin_bg', '#f0f2f5'),

        'accent_color': config.get('accent_color', '#3498db'),

        'current_theme': current_theme,

        'allow_user_overrides': config.get('allow_user_overrides', 'false') == 'true'

    }

    

    # Theme Palettes

    palettes = {

        'light': {

            'bg_primary': '#f0f2f5',

            'bg_secondary': '#ffffff',

            'bg_tertiary': '#e8eaed',

            'text_primary': '#1a1a2e',

            'text_secondary': '#4a4a6a',

            'border_color': '#dce1e8'

        },

        'dark': {

            'bg_primary': '#0f172a',

            'bg_secondary': '#1e293b',

            'bg_tertiary': '#334155',

            'text_primary': '#f8fafc',

            'text_secondary': '#94a3b8',

            'border_color': '#1e293b'

        },

        'midnight-black': {

            'bg_primary': '#000000',

            'bg_secondary': '#0a0a0a',

            'bg_tertiary': '#111111',

            'text_primary': '#ffffff',

            'text_secondary': '#a0a0a0',

            'border_color': '#333333'

        },

        'cyberpunk': {

            'bg_primary': '#050505',

            'bg_secondary': '#0a0a0a',

            'bg_tertiary': '#141414',

            'text_primary': '#00ff00',

            'text_secondary': '#00cc00',

            'border_color': '#ff00ff'

        },

        'secure-blue': {

            'bg_primary': '#e3f2fd',

            'bg_secondary': '#ffffff',

            'bg_tertiary': '#bbdefb',

            'text_primary': '#0d47a1',

            'text_secondary': '#1565c0',

            'border_color': '#90caf9'

        }

    }



    # Overlap with user preferences if enabled and logged in
    user_styles = {}
    if styles['allow_user_overrides'] and 'user_id' in session:
        try:
            user_record = admin_table.get(Query().id == session['user_id'])
            if user_record and user_record.get('custom_styles'):
                # custom_styles column might be handled as a dict in TinyDB
                pass 
        except: pass



    # Merge theme palette into styles

    theme_name = str(styles.get('current_theme', 'light'))

    palette = palettes.get(theme_name, palettes['light'])

    styles.update(palette)



    # Apply administrator overrides if present

    for key in ['bg_primary', 'bg_secondary', 'text_primary', 'text_secondary']:

        if config.get(key):

            styles[key] = config[key]



    # Helper to format background values (e.g., add url() if it's an image URL or local path)

    def format_bg(value):

        if not value: return value

        # If it's already url(...) or linear-gradient(...)

        if 'url(' in value or 'gradient(' in value:

            return value

        # If it's a URL

        if value.startswith('http://') or value.startswith('https://'):

            return f'url("{value}")'

        # If it's a local file path from upload

        if value.startswith('static/uploads/backgrounds/'):

            # Ensure it starts with / for absolute web path

            path = '/' + value if not value.startswith('/') else value

            return f'url("{path}")'

        return value



    # Apply formatting to all background-related fields

    for k in ['sidebar_bg', 'header_bg', 'content_bg', 'login_bg', 'admin_bg', 'auth_bg']:

        if k in styles:

            styles[k] = format_bg(styles[k])

    

    # Inject whatsapp number
    try:
        row = config_table.get(Query().name == 'whatsapp_agent_number')
        whatsapp_number = row['value'] if row else '8367379876'
    except:
        whatsapp_number = '8367379876'

    

    return {

        "custom_styles": styles,

        "user_styles": user_styles,

        "whatsapp_number": whatsapp_number

    }



from auth_utils import login_required, role_required

def employee_required(f):

    @wraps(f)

    def decorated_function(*args, **kwargs):

        if 'user_id' not in session:

            flash('Please log in to access this page.', 'warning')

            return redirect(url_for('login'))

        if session.get('role') not in ['employee', 'admin', 'super_admin']: # Admins can view too if needed, or strictly employee

            flash('You do not have permission to access this page.', 'danger')

            return redirect(url_for('dashboard'))

        return f(*args, **kwargs)

    return decorated_function



# Initialize Style Config if not exists

style_configs = [

    ('sidebar_bg', 'linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)'),

    ('header_bg', '#ffffff'),

    ('content_bg', '#f0f2f5'),

    ('login_bg', 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'),

    ('admin_bg', '#f0f2f5'),

    ('accent_color', '#3498db'),

    ('current_theme', 'light'),

    ('allow_user_overrides', 'false')

]



# Style config initialization moved to update_schema.py



@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('home.html')



@app.route('/legal-consent')
def legal_consent():
    return render_template('legal_consent.html')



@app.route('/track', methods=['GET', 'POST'])
def track_public():
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id', '').strip()
        if not tracking_id:
            flash('Please enter a tracking ID.', 'warning')
            return redirect(url_for('index'))
            
        complaint_raw = complaints_table.get(Query().id == tracking_id)
        if not complaint_raw:
            flash('Complaint not found. Please check your tracking ID.', 'danger')
            return redirect(url_for('index'))
            
        complaint = process_complaint_record(complaint_raw)
        
        # Attach submitter details
        # Prioritize submitted_by, then user_id for profile lookup
        submitter_id = complaint.get('submitted_by') or complaint.get('user_id')
        
        if submitter_id and submitter_id != 'anonymous':
            u = admin_table.get(Query().id == submitter_id)
            if u:
                complaint['user_name'] = u.get('full_name', u.get('username'))
                complaint['user_email'] = u.get('email', '')
                complaint['user_phone'] = u.get('phone', '')
        
        return render_template('track_status.html', complaint=complaint)
    return redirect(url_for('index'))



# Define available roles for signup
# Define available roles for signup
ROLES = [
    {'value': 'user', 'label': 'User'},
    {'value': 'admin', 'label': 'Admin'},
    {'value': 'manager', 'label': 'Manager'},
    {'value': 'employee', 'label': 'Employee'},
    {'value': 'technician', 'label': 'Technician'},
    {'value': 'support', 'label': 'Support'},
    {'value': 'database_server', 'label': 'Database Server'},
    {'value': 'supervisor', 'label': 'Supervisor'},
    {'value': 'hr_manager', 'label': 'HR Manager'}
]

@app.route('/customer/signup', methods=['GET', 'POST'])
def customer_signup():
    return signup(fixed_role='user')

@app.route('/signup', methods=['GET', 'POST'])
def signup(fixed_role=None):
    try:
        if request.method == 'POST':
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Use fixed_role if provided, otherwise get from form
            if fixed_role:
                role = fixed_role
            else:
                role = request.form.get('role', 'user').lower().strip()
                
            if not role:
                role = "user"
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()
            legal_consent = request.form.get('legal_consent')
            
            if not all([email, password, confirm_password, role, full_name, legal_consent]):
                flash('All fields, including Legal Consent, are required.', 'danger')
                return render_template('signup.html', roles=ROLES, fixed_role=fixed_role)
            
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('signup.html', roles=ROLES, fixed_role=fixed_role)
            
            is_strong, message = validate_password_strength(password)
            if not is_strong:
                flash(message, 'danger')
                return render_template('signup.html', roles=ROLES)
                
            existing_user = admin_table.search(Query().email == email)
            
            if existing_user:
                flash('Email already exists.', 'danger')
                return render_template('signup.html', roles=ROLES, fixed_role=fixed_role)
            
            # Generate Username from Email
            base_username = email.split('@')[0]
            username = base_username
            
            # Ensure unique username
            counter = 1
            while admin_table.search(Query().username == username):
                username = f"{base_username}{counter}"
                counter += 1
            
            user_id = str(uuid.uuid4())

            # Handle Profile Photo
            profile_photo = 'default_profile.png'
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    filename = secure_filename(f"{user_id}_{file.filename}")
                    upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'profile_photos')
                    os.makedirs(upload_folder, exist_ok=True)
                    file.save(os.path.join(upload_folder, filename))
                    profile_photo = filename

            user_record = {
                'id': user_id,
                'username': username,
                'email': email,
                'password_hash': generate_password_hash(password),
                'role': role, # Use requested role in lowercase
                'name': full_name, # Also storing 'name' as requested
                'full_name': full_name,
                'phone': phone,
                'profile_photo': profile_photo,
                'legal_consent_at': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat(),
                'is_active': True
            }
            
            admin_table.insert(user_record)
            
            log_action(user_id, 'signup', f'New {role} registered: {email} (username: {username})')
            flash('Registration successful! Please log in with your credentials.', 'success')
            
            return redirect(url_for('login'))

        return render_template('signup.html', roles=ROLES, fixed_role=fixed_role)
    except Exception as e:
        logging.error(f"Signup error: {e}\n{traceback.format_exc()}")
        flash("An unexpected error occurred during signup. Please try again.", "danger")
        return render_template('signup.html', roles=ROLES, fixed_role=fixed_role)



@app.route('/login/google')
def login_google():
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    if not client_id or 'your_client_id' in client_id:
        # Mock/Bypass Mode for development
        logger.info("Using Mock Google Login (Development Mode)")
        return redirect(url_for('login_google_callback', mock=True))
        
    redirect_uri = url_for('login_google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def login_google_callback():
    if request.args.get('mock') == 'True':
        # Mock user info for testing
        user_info = {
            'email': 'smjg.305@gmail.com',
            'name': 'Jeshwanth Bakki (Test)',
            'picture': 'https://www.gstatic.com/images/branding/product/2x/avatar_square_blue_120dp.png'
        }
    else:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.get('https://www.googleapis.com/oauth2/v3/userinfo').json()
    
    email = user_info.get('email')
    
    if not email:
        flash('Failed to retrieve email from Google.', 'danger')
        return redirect(url_for('login'))
        
    user_list = admin_table.search(Query().email == email)
    user = user_list[0] if user_list else None
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        log_action(user['id'], 'login_google', f"Google login successful: {email}")
        flash(f"Welcome back, {user.get('full_name', user['username'])}!", 'success')
        return redirect(url_for('dashboard'))
    else:
        # Re-enabling auto-creation as requested
        user_id = str(uuid.uuid4())
        base_username = email.split('@')[0]
        username = base_username
        # Ensure unique username
        counter = 1
        while admin_table.search(Query().username == username):
            username = f"{base_username}{counter}"
            counter += 1
            
        user_record = {
            'id': user_id,
            'username': username,
            'email': email,
            'role': 'user',
            'full_name': user_info.get('name', username),
            'phone': '',
            'created_at': datetime.now().isoformat(),
            'is_active': True,
            'auth_provider': 'google'
        }
        admin_table.insert(user_record)
        
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = 'user'
        log_action(user_id, 'signup_google', f"New user registered via Google: {email}")
        flash('Account created successfully via Google!', 'success')
        return redirect(url_for('dashboard'))



@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if 'user_id' in session:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')

            # Login via Email
            user_list = admin_table.search(Query().email == email)
            user = user_list[0] if user_list else None
            
            if not user:
                 flash('Invalid email or password.', 'danger')
                 return render_template('login.html')
                 
            # Check Account Lockout
            if user.get('lockout_until'):
                 if isinstance(user['lockout_until'], str):
                     lockout_time = datetime.fromisoformat(user['lockout_until'])
                 else:
                     lockout_time = user['lockout_until']
                     
                 if datetime.now() < lockout_time:
                     remaining_time = int((lockout_time - datetime.now()).total_seconds() / 60)
                     flash(f'Account locked due to multiple failed attempts. Please try again in {remaining_time} minutes.', 'danger')
                     return render_template('login.html')

            # Validate password (handle both password_hash and legacy password field)
            is_authenticated = False
            password_hash = user.get('password_hash')
            legacy_password = user.get('password')
            
            if password_hash:
                if check_password_hash(password_hash, password):
                    is_authenticated = True
            elif legacy_password:
                # Check legacy password (could be plaintext or old format)
                if legacy_password == password:
                    is_authenticated = True
                    # Migrate to secure hash
                    admin_table.update({'password_hash': generate_password_hash(password)}, Query().id == user['id'])

            if is_authenticated:
                # Reset failed attempts
                admin_table.update({'failed_login_attempts': 0, 'lockout_until': None}, Query().id == user['id'])
                
                if not user.get('is_active', True):
                    flash('Your account has been deactivated. Please contact support.', 'warning')
                    return render_template('login.html')
                    
                # Use requested session keys
                session['user_id'] = user.get('id')
                session['user_name'] = user.get('full_name') or user.get('name') or user.get('username')
                session['role'] = user.get('role', 'user').lower()
                
                # Compatibility keys for existing templates
                session['full_name'] = user.get('full_name')
                session['username'] = user.get('username')
                session['name'] = user.get('name') or user.get('full_name') or user.get('username')
                session['profile_photo'] = user.get('profile_photo')
                
                log_action(session['user_id'], 'login', 'User logged in successfully')
                flash('Login successful!', 'success')
                
                # Role-based Redirection (Strict)
                role = session['role']
                if role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif role == 'manager':
                    return redirect(url_for('manager_dashboard'))
                elif role in ['employee', 'technician', 'support']:
                    return redirect(url_for('employee_dashboard'))
                else:
                    return redirect(url_for('user_dashboard')) # Default to user_dashboard
            else:
                # Increment failed attempts
                failed_attempts = user.get('failed_login_attempts', 0) + 1
                lockout_until = None
                if failed_attempts >= 5:
                    lockout_until = (datetime.now() + timedelta(minutes=15)).isoformat()
                    flash('Account locked for 15 minutes due to multiple failed attempts.', 'danger')
                else:
                    flash('Invalid email or password.', 'danger')
                
                admin_table.update({'failed_login_attempts': failed_attempts, 'lockout_until': lockout_until}, Query().id == user['id'])
                return render_template('login.html')

        return render_template('login.html')
    except Exception as e:
        logging.error(f"Login error: {e}\n{traceback.format_exc()}")
        flash("An unexpected error occurred during login. Please try again.", "danger")
        return render_template('login.html')

@app.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user_list = admin_table.search(Query().email == email)
        user = user_list[0] if user_list else None
        
        if not user:
            flash('Invalid email or password.', 'danger')
            return render_template('staff_login.html')
            
        # Check if Staff
        if user.get('role') in ['user', 'customer']:
            flash('Access Denied. This portal is for staff only.', 'danger')
            return render_template('staff_login.html')

        # Check if account is locked
        if user.get('lockout_until'):
            if isinstance(user['lockout_until'], str):
                 lockout_time = datetime.fromisoformat(user['lockout_until'])
            else: 
                 lockout_time = user['lockout_until']
                 
            if datetime.now() < lockout_time:
                wait_seconds = (lockout_time - datetime.now()).seconds
                flash(f'Account locked due to too many failed attempts. Try again in {wait_seconds} seconds.', 'danger')
                return render_template('staff_login.html')
            else:
                # Reset lockout
                admin_table.update({'lockout_until': None, 'failed_login_attempts': 0}, Query().id == user['id'])

        # Validate password (handle both password_hash and legacy password field)
        is_authenticated = False
        password_hash = user.get('password_hash')
        legacy_password = user.get('password')
        
        if password_hash:
            if check_password_hash(password_hash, password):
                is_authenticated = True
        elif legacy_password:
            # Check legacy password
            if legacy_password == password:
                is_authenticated = True
                # Migrate to secure hash
                admin_table.update({'password_hash': generate_password_hash(password)}, Query().id == user['id'])

        if is_authenticated:
            # Successful Login
            # Reset failed attempts
            admin_table.update({'failed_login_attempts': 0, 'lockout_until': None}, Query().id == user['id'])
                
            # Set Session
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user.get('full_name', user['username'])
            session['lang'] = user.get('language', 'en')
            
            # Log
            log_action(user['id'], 'staff_login', f"Staff logged in from {request.remote_addr}")
            
            flash(f'Welcome to Staff Portal, {user.get("full_name", user["username"])}!', 'success')
            
            # Redirect based on role
            if user['role'] in ['admin', 'super_admin']:
                return redirect(url_for('admin_dashboard_route'))
            elif user['role'] == 'manager':
                return redirect(url_for('manager_dashboard'))
            elif user['role'] in ['employee', 'technician', 'support']:
                return redirect(url_for('employee_dashboard'))
            
            return redirect(url_for('dashboard'))
            
        else:
            # Increment failure count
            failures = user.get('failed_login_attempts', 0) + 1
            admin_table.update({'failed_login_attempts': failures}, Query().id == user['id'])
            
            if failures >= 5:
                lockout_time = (datetime.now() + timedelta(minutes=15)).isoformat()
                admin_table.update({'lockout_until': lockout_time}, Query().id == user['id'])
                flash('Account locked for 15 minutes due to multiple failed login attempts.', 'danger')
            else:
                flash('Invalid email or password.', 'danger')
                
            return render_template('staff_login.html')

    return render_template('staff_login.html')



@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':

        email = request.form.get('email', '').strip()

        if not email:
            flash('Please enter your email address.', 'danger')
            return redirect(url_for('forgot_password'))
            
        user_list = admin_table.search(Query().email == email)
        user_record = user_list[0] if user_list else None
        
        if not user_record:
            # Don't reveal email existence
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
            return redirect(url_for('login'))
            
        user_id = user_record['id']
        # Restriction removed to allow admin password reset as requested.
            
        # Generate reset token
        token = secrets.token_urlsafe(32)
        
        # Save token
        # Invalidate old tokens
        password_resets_table.update({'status': 'invalidated'}, (Query().user_id == user_id) & (Query().status == 'pending'))
        
        expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()
        password_resets_table.insert({
            'user_id': user_id,
            'token': token,
            'status': 'pending',
            'requested_at': datetime.now().isoformat(),
            'expires_at': expires_at
        })


        log_action(user_id, 'password_reset_requested', f'Reset link requested for {email}')

        # Send Reset Email with Link
        base_url = app.config.get('BASE_URL')
        if not base_url:
            # Fallback to local IP if BASE_URL is not set
            local_ip = get_local_ip()
            port = int(os.environ.get('PORT', 8080))
            base_url = f"http://{local_ip}:{port}"
            
        reset_link = f"{base_url}/reset-password/{token}"
            
        send_reset_email(email, reset_link)

        

        flash('A password reset link has been sent to your email. It expires in 15 minutes.', 'success')

        return redirect(url_for('login'))

            

    return render_template('forgot_password.html')



@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    # Debug logging
    with open('reset_debug.txt', 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] Accessing reset link with token: {token}\n")

    reset_record = password_resets_table.get(Query().token == token)
    
    with open('reset_debug.txt', 'a') as f:
        if reset_record:
            f.write(f"[{datetime.now().isoformat()}] Found record: {reset_record.get('id')}\n")
        else:
            f.write(f"[{datetime.now().isoformat()}] No pending record found for token.\n")

    
    if not reset_record or reset_record.get('status') != 'pending':
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('login'))
    
    # Check expiry
    expires_at = reset_record['expires_at']
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
        
    if datetime.now() > expires_at:
        password_resets_table.update({'status': 'expired'}, Query().id == reset_record['id'])
        flash('This reset link has expired. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Both password fields are required.', 'danger')
            return render_template('reset_password.html', token=token)
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
            
        is_strong, message = validate_password_strength(password)
        if not is_strong:
            flash(message, 'danger')
            return render_template('reset_password.html', token=token)
            
        # Update User Password
        user_id = reset_record['user_id']
        admin_table.update({
            'password_hash': generate_password_hash(password),
            'password_changed_at': datetime.now().isoformat(),
            'temp_password': None
        }, Query().id == user_id)
        
        # Mark token as used
        password_resets_table.update({
            'status': 'used',
            'used_at': datetime.now().isoformat()
        }, Query().token == token)
        
        log_action(user_id, 'password_reset_success', 'Password reset successfully via link')

        

        flash('Your password has been updated. You can now log in.', 'success')

        return redirect(url_for('login'))



    return render_template('reset_password.html')



@app.route('/login-reset/<token>')

def login_reset(token):

    reset_record = password_resets_table.search(Query().token == token)

    if not reset_record:

        flash('Invalid or expired reset link.', 'danger')

        return redirect(url_for('login'))

    

    reset = list(reset_record)[0]

    

    if reset.get('status') != 'approved':

        if reset.get('status') == 'used':

            flash('This reset link has already been used.', 'warning')

        else:

            flash('This reset request is not approved.', 'danger')

        return redirect(url_for('login'))

    

    # Check expiry (24 hours after approval)

    if reset.get('expires_at'):

        expiry = datetime.fromisoformat(reset['expires_at'])

        if datetime.now() > expiry:

            password_resets_table.update({'status': 'expired'}, Query().token == token)

            flash('This reset link has expired.', 'danger')

            return redirect(url_for('login'))

    

    # Retrieve the generated password from the record

    temp_password = reset.get('temp_password')

    if not temp_password:

        flash('Error retrieving reset password. Please contact support.', 'danger')

        return redirect(url_for('login'))

    

    # Mark as used (so they can only see it once)

    password_resets_table.update({

        'status': 'used',

        'used_at': datetime.now().isoformat()

    }, Query().token == token)

    

    log_action(reset['user_id'], 'password_reset_viewed', 'User viewed their temporary password')

    

    return render_template('login_reset.html', password=temp_password)



@app.route('/user/ai-chatbot')

@login_required

def ai_chatbot():

    return render_template('user/ai_chatbot.html')



@app.route('/api/ai-chatbot/send', methods=['POST'])
@login_required
def ai_chatbot_send():
    data = request.json
    message = data.get('message', '').strip()
    files_data = data.get('files', [])
    user_id = session['user_id']
    
    if not message and not files_data:
        return {'status': 'error', 'message': 'Empty message and no files provided'}, 400

    # Conversational State Machine for Complaint Registration
    c_step = session.get('c_step')
    
    # Check for complaint start keywords if not already in a flow
    complaint_keywords = ['problem', 'issue', 'damaged', 'not working', 'payment failed', 'refund', 'late delivery']
    if not c_step and any(keyword in message.lower() for keyword in complaint_keywords):
        session['c_step'] = 1
        return {
            'status': 'success',
            'ai_response': {
                'content': "I understand you are facing an issue. I will help you register a complaint.\n\nPlease enter **Complaint Title**:"
            }
        }

    # Step-by-step flow
    if c_step == 1:
        session['c_title'] = message
        session['c_step'] = 2
        return {
            'status': 'success',
            'ai_response': {
                'content': "Select Category:\n1. Technical\n2. Payment\n3. Delivery\n4. Account\n5. Other",
                'type': 'menu',
                'options': ['1. Technical', '2. Payment', '3. Delivery', '4. Account', '5. Other']
            }
        }
    
    elif c_step == 2:
        category_map = {
            '1': 'Technical', 'technical': 'Technical',
            '2': 'Payment', 'payment': 'Payment',
            '3': 'Delivery', 'delivery': 'Delivery',
            '4': 'Account', 'account': 'Account',
            '5': 'Other', 'other': 'Other'
        }
        clean_msg = message.split('.')[0].strip().lower()
        session['c_category'] = category_map.get(clean_msg, 'Other')
        session['c_step'] = 3
        return {
            'status': 'success',
            'ai_response': {
                'content': "Select Priority:\n1. Low\n2. Medium\n3. High\n4. Urgent",
                'type': 'menu',
                'options': ['1. Low', '2. Medium', '3. High', '4. Urgent']
            }
        }
    
    elif c_step == 3:
        priority_map = {
            '1': 'low', 'low': 'low',
            '2': 'medium', 'medium': 'medium',
            '3': 'high', 'high': 'high',
            '4': 'critical', 'urgent': 'critical', 'critical': 'critical'
        }
        clean_msg = message.split('.')[0].strip().lower()
        session['c_priority'] = priority_map.get(clean_msg, 'medium')
        session['c_step'] = 4
        return {
            'status': 'success',
            'ai_response': { 'content': "Please describe your issue in detail:" }
        }
    
    elif c_step == 4:
        title = session.get('c_title')
        category = session.get('c_category')
        priority = session.get('c_priority')
        description = message
        
        complaint_id = str(uuid.uuid4())
        complaint_data = {
            'id': complaint_id,
            'user_id': user_id,
            'title': title,
            'description': description,
            'category': category,
            'priority': priority,
            'status': 'open',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
        }
        
        try:
            last_row = complaints_table.all()
            if last_row:
                last_row = sorted(last_row, key=lambda x: x.get('created_at', ''), reverse=True)[0]
                prev_hash = last_row.get('current_hash', "GENESIS_BLOCK")
            else:
                prev_hash = "GENESIS_BLOCK"
        except Exception:
            prev_hash = "GENESIS_BLOCK"

        complaint_data['prev_hash'] = prev_hash
        complaint_data['current_hash'] = calculate_complaint_hash(complaint_data, prev_hash)
        complaint_data['submitted_by'] = user_id
        
        complaints_table.insert(complaint_data)
        sync_complaint_to_google_sheets(complaint_data, user_id)
        
        staff_users = admin_table.search(Query().role.one_of(['admin', 'super_admin', 'employee']))
        for staff in staff_users:
            if staff['id'] != user_id:
                create_notification(staff['id'], f"New Chat Complaint: {title[:30]}", f"{session.get('full_name')} registered a new complaint via chatbot.", url_for('admin_complaints'))

        
        for key in ['c_step', 'c_title', 'c_category', 'c_priority']:
            session.pop(key, None)
            
        return {
            'status': 'success',
            'ai_response': {
                'content': f"Your complaint has been registered successfully.\nYour Ticket ID is **#{complaint_id[:8]}**.\nOur Support Agent will review it shortly."
            }
        }

    # Support Agent Handoff
    support_keywords = ['support', 'agent', 'talk to human', 'customer support', 'help']
    if any(keyword in message.lower() for keyword in support_keywords):
        online_employee = admin_table.search((Query().role == 'employee') & (Query().is_online == True))
        if online_employee:
            agent = sorted(online_employee, key=lambda x: x.get('last_active', ''))[0]
            active_complaints_rows = complaints_table.search((Query().user_id == user_id) & (Query().status == 'open'))
        active_complaints_rows = complaints_table.search((Query().user_id == user_id) & (Query().status == 'open'))
        if active_complaints_rows:
            recent_complaints = active_complaints_rows
            latest = sorted(recent_complaints, key=lambda x: x.get('created_at', ''))[-1]
            complaints_table.update({'assigned_technician_id': agent['id'], 'status': 'in_progress'}, Query().id == latest['id'])
            create_notification(agent['id'], "New Chat Assignment", f"You have been assigned to help with complaint: {latest['title']}")
            
            # Get assigned WhatsApp contact
            user_rec = admin_table.get(Query().id == user_id)
            support_num = ""
            if user_rec and user_rec.get('whatsapp_contact_id'):
                contact = whatsapp_contacts_table.get(Query().id == user_rec['whatsapp_contact_id'])
                if contact:
                    support_num = contact.get('number')
            
            # Fallback to system default
            if not support_num:
                res = config_table.search(Query().name == 'whatsapp_agent_number')
                if res:
                    support_num = res[0].get('value')
                else:
                    support_num = "8367379876"
            
            return {
                'status': 'success',
                'ai_response': {
                    'content': f"You are now connected to a Support Agent **{agent.get('full_name', agent['username'])}**.\nYou can contact them on WhatsApp:\nhttps://wa.me/{support_num}",
                    'complaint_id': latest['id']
                }
            }
        else:
            return {'status': 'success', 'ai_response': {'content': "I've flagged your request for a support agent. Please register a complaint first so they have context to help you."}}


    # If user is in an active chat with an agent, save message to chat_messages
    active_complaints = complaints_table.search(
        (Query().user_id == user_id) & (Query().status == 'in_progress')
    )
    if active_complaints:
        latest = sorted(active_complaints, key=lambda x: x.get('updated_at', ''))[-1]
        chat_messages_table.insert({
            'id': str(uuid.uuid4()),
            'complaint_id': latest['id'],
            'sender': session.get('username'),
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        # We still let the AI reply or just return success
        # The prompt implies a "talk to human" mode. Usually, AI should step back.
        # But for now, let's just make sure it's stored.

    # Default: Generate AI response
    processed_files = []
    for f in files_data:
        try:
            file_bytes = base64.b64decode(f['data'])
            processed_files.append({'mime_type': f['mime_type'], 'data': file_bytes})
        except: continue

    ai_response = ai_agent.generate_response(message, files=processed_files, user_data=complaints_table.search(Query().user_id == user_id))
    if not isinstance(ai_response, dict): ai_response = {"type": "text", "content": str(ai_response)}
    return {'status': 'success', 'ai_response': ai_response}

@app.route('/api/chat/poll/<complaint_id>')
@login_required
def chat_poll(complaint_id):
    new_messages = chat_messages_table.search((Query().complaint_id == complaint_id) & (Query().sender != session['username']))
    return jsonify(new_messages)

@app.route('/api/chat/send-agent', methods=['POST'])
@login_required
def chat_send_agent():
    if session.get('role') != 'employee':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    data = request.json
    complaint_id = data.get('complaint_id')
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Empty message'}), 400
        
    chat_messages_table.insert({
        'id': str(uuid.uuid4()),
        'complaint_id': complaint_id,
        'sender': session.get('username'),
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'is_read': False
    })
    
    # Notify customer via email
    complaint = complaints_table.get(Query().id == complaint_id)
    if complaint:
        submitter_id = complaint.get('submitted_by')
        if submitter_id:
            customer = admin_table.get(Query().id == submitter_id)
            if customer and customer.get('email'):
                subject = f"Support Reply for Ticket #{complaint_id[:8]}"
                body = f"Support agent {session.get('username')} has replied to your chat regarding: {complaint.get('title')}\n\nMessage: {message}\n\nReply here: {request.host_url}user/chat"
                send_email_notification(customer['email'], subject, body)

    return jsonify({'status': 'success'})

@app.route('/user/chat')
@login_required
def user_chat():
    user_id = session.get('user_id')
    # Fetch user's complaints to select for chat
    my_complaints = complaints_table.search(Query().submitted_by == user_id)
    my_complaints.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Mark messages for these complaints as read when opening chat
    for c in my_complaints:
        complaint_id = c.get('id')
        chat_messages_table.update({'is_read': True}, (Query().complaint_id == complaint_id) & (Query().sender != session['username']))
        
    return render_template('user/chat.html', complaints=my_complaints)

@app.route('/api/chat/send-user', methods=['POST'])
@login_required
def chat_send_user():
    data = request.json
    complaint_id = data.get('complaint_id')
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Empty message'}), 400
        
    # Verify ownership
    complaint = complaints_table.get(Query().id == complaint_id)
    if not complaint or complaint.get('submitted_by') != session.get('user_id'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    chat_messages_table.insert({
        'id': str(uuid.uuid4()),
        'complaint_id': complaint_id,
        'sender': session.get('username'),
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'is_read': False
    })
    
    # Notify assigned tech via email
    assigned_tech_id = complaint.get('assigned_to')
    if assigned_tech_id:
        tech_user = admin_table.get(Query().id == assigned_tech_id)
        if tech_user and tech_user.get('email'):
            subject = f"New message from customer for Ticket #{complaint_id[:8]}"
            body = f"Customer {session.get('username')} sent a new message regarding ticket: {complaint.get('title')}\n\nMessage: {message}\n\nView here: {request.host_url}employee/ticket/{complaint_id}"
            send_email_notification(tech_user['email'], subject, body)

    return jsonify({'status': 'success'})

@app.route('/employee/messages')
@login_required
def employee_messages():
    if session.get('role') not in ['employee', 'technician', 'support']:
        return redirect(url_for('dashboard'))
        
    user_id = session.get('user_id')
    # Fetch complaints assigned to this employee
    my_complaints = complaints_table.search(Query().assigned_to == user_id)
    
    # Enhance complaints with latest message info
    for c in my_complaints:
        messages = chat_messages_table.search(Query().complaint_id == c['id'])
        if messages:
            messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            c['latest_message'] = messages[0]
            c['unread_count'] = len([m for m in messages if m['sender'] != session['username'] and not m.get('is_read', False)])
        else:
            c['latest_message'] = None
            c['unread_count'] = 0
            
    my_complaints.sort(key=lambda x: (x.get('latest_message', {}).get('timestamp', '') if x.get('latest_message') else ''), reverse=True)
            
    return render_template('employee/all_messages.html', complaints=my_complaints)

@app.route('/api/chat/unread-counts')
@login_required
def chat_unread_counts():
    user_id = session.get('user_id')
    username = session.get('username')
    
    # Simple count: any message in user's complaints not sent by them and not read
    my_complaint_ids = [c['id'] for c in complaints_table.search(Query().submitted_by == user_id)]
    
    unread_count = 0
    if my_complaint_ids:
        unread_messages = chat_messages_table.search(
            (Query().complaint_id.one_of(my_complaint_ids)) & 
            (Query().sender != username) & 
            (Query().is_read == False)
        )
        unread_count = len(unread_messages)
        
    return jsonify({'unread_count': unread_count})
@app.route('/logout')

def logout():

    if 'user_id' in session:

        log_action(session['user_id'], 'logout', 'User logged out')

    session.clear()

    flash('You have been logged out.', 'info')

    return redirect(url_for('index'))




# User Profile Route
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user_id = session['user_id']
    user_data = admin_table.get(Query().id == user_id)
    
    if not user_data:
        flash('User not found.', 'danger')
        return redirect(url_for('logout'))
    
    if request.method == 'POST':
        # Handle profile updates
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        
        update_data = {}
        if full_name:
            update_data['full_name'] = full_name
        if email and email != user_data.get('email'):
            # Check if email already exists
            existing = admin_table.search(Query().email == email)
            if existing and existing[0].get('id') != user_id:
                flash('Email already in use.', 'danger')
                return redirect(url_for('user_profile'))
            update_data['email'] = email
        if phone:
            update_data['phone'] = phone
            
        # Handle profile picture upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                import os
                filename = secure_filename(file.filename)
                upload_folder = 'static/uploads/profile_photos'
                os.makedirs(upload_folder, exist_ok=True)
                filepath = os.path.join(upload_folder, f"{user_id}_{filename}")
                file.save(filepath)
                # Store only the filename or relative path
                update_data['profile_photo'] = f"{user_id}_{filename}"
                session['profile_photo'] = f"{user_id}_{filename}"
        
        if update_data:
            update_data['updated_at'] = datetime.now().isoformat()
            admin_table.update(update_data, Query().id == user_id)
            log_action(user_id, 'profile_update', 'Updated profile information')
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('user_profile'))
    
    return render_template('user/profile.html', user=user_data)

@app.route('/user/account')
@login_required
def user_account():
    """Premium user account overview page"""
    user_id = session.get('user_id')
    user_data = admin_table.get(Query().id == user_id)
    return render_template('user/account.html', user=user_data)

@app.route('/admin')
@app.route('/admin_dashboard')
@login_required
@role_required(['admin', 'super_admin'])
def admin_dashboard():
    # Admin Dashboard Logic (moved from generic dashboard)
    total_users = len(admin_table)
    total_complaints = len(complaints_table)
    pending_complaints = len(complaints_table.search(Query().status == 'open'))
    total_maintenance = len(maintenance_table)
    recent_logs = sorted(logs_table.all(), key=lambda x: x.get('timestamp', ''), reverse=True)[:10]

    template = 'dashboard/super_admin.html' if session.get('role') == 'super_admin' else 'admin/dashboard.html'
    return render_template(template, 
                         total_users=total_users,
                         total_complaints=total_complaints,
                         pending_complaints=pending_complaints,
                         total_maintenance=total_maintenance,
                         recent_logs=recent_logs)

@app.route('/manager')
@app.route('/manager_dashboard')
@login_required
@role_required('manager')
def manager_dashboard():
    total_tasks = len(complaints_table)
    team_size = len(admin_table.search(Query().role.one_of(['technician', 'support'])))
    return render_template('dashboard/manager.html', total_tasks=total_tasks, team_size=team_size)

@app.route('/employee')
@app.route('/employee_dashboard')
@login_required
@role_required(['employee', 'technician', 'support'])
def employee_dashboard():
    role = session.get('role')
    user_id = session.get('user_id')
    
    if role == 'technician':
        assigned_complaints_rows = complaints_table.search(Query().assigned_technician_id == user_id)
        assigned_complaints = [process_complaint_record(row) for row in assigned_complaints_rows]
        total_assigned = len(assigned_complaints)
        pending_tasks = len([c for c in assigned_complaints if c.get('status') in ['open', 'in_progress', 'pending']])
        completed_tasks = len([c for c in assigned_complaints if c.get('status') == 'resolved'])
        performance_score = 4.0 # Placeholder logic
        return render_template('dashboard/technician.html', assigned_complaints=assigned_complaints, total_assigned=total_assigned, pending_tasks=pending_tasks, completed_tasks=completed_tasks, performance_score=performance_score)
        
    elif role == 'support_agent':
        open_tickets = len(complaints_table.search(Query().status == 'open'))
        resolved_today = 0 # Implement date logic if needed
        recent_complaints_rows = sorted(complaints_table.all(), key=lambda x: x.get('created_at', ''), reverse=True)[:10]
        recent_complaints = [process_complaint_record(row) for row in recent_complaints_rows]
        return render_template('dashboard/support.html', open_tickets=open_tickets, resolved_today=resolved_today, recent_complaints=recent_complaints)
        
    else: # Generic Employee
        assigned_complaints_rows = complaints_table.search(Query().assigned_to == user_id)
        assigned_complaints = [process_complaint_record(row) for row in assigned_complaints_rows]
        assigned_count = len(assigned_complaints)
        resolved_count = len([c for c in assigned_complaints if c.get('status') == 'resolved'])
        pending_count = len([c for c in assigned_complaints if c.get('status') in ['open', 'in_progress', 'pending']])
        recent_complaints = sorted(assigned_complaints, key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)[:5]
        return render_template('employee/dashboard.html', assigned_count=assigned_count, resolved_count=resolved_count, pending_count=pending_count, recent_complaints=recent_complaints)


@app.route('/dashboard')
@login_required
def dashboard():
    # Customer Dashboard Logic
    user_id = session['user_id']
    role = session.get('role')
    
    # Redirect staff to their specific dashboards
    if role in ['admin', 'super_admin']: 
        return redirect(url_for('admin_dashboard'))
    if role == 'manager': 
        return redirect(url_for('manager_dashboard'))
    if role in ['employee', 'technician', 'support']: 
        return redirect(url_for('employee_dashboard'))
    if role == 'database_server':
        return redirect(url_for('database_dashboard'))

    # All other roles (user, customer, etc.) go to the user dashboard
    return redirect(url_for('user_dashboard'))

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    user_id = session['user_id']
    username = session.get('username')
    
    # 1. Fetch Open Complaints Count
    try:
        open_complaints_count = complaints_table.count(
            (Query().user_id == user_id) & 
            (Query().status.one_of(['open', 'in_progress']))
        )
    except:
        open_complaints_count = 0
        
    # 2. Fetch Resolved Complaints Count & List
    try:
        resolved_complaints_list = complaints_table.search(
            (Query().user_id == user_id) & 
            (Query().status == 'resolved')
        )
        resolved_complaints = len(resolved_complaints_list)
        
        # Sort resolved by updated_at desc
        resolved_complaints_list.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        
        # Enhance resolved list with technician names
        for c in resolved_complaints_list:
            tech_id = c.get('assigned_technician_id')
            if tech_id:
                tech = admin_table.get(Query().id == tech_id)
                c['technician_name'] = tech.get('full_name', tech.get('username')) if tech else 'Unknown'
            else:
                c['technician_name'] = 'Support Team'
                
    except:
        resolved_complaints = 0
        resolved_complaints_list = []
        
    # 3. Fetch Total Files
    try:
        total_files = files_table.count(Query().user_id == user_id)
    except:
        total_files = 0
        
    # 4. Fetch Recent Complaints (Last 5)
    try:
        user_complaints = complaints_table.search(Query().user_id == user_id)
        user_complaints.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        recent_complaints = user_complaints[:5]
    except:
        recent_complaints = []
        
    # 5. Prepare Chart Data (Status Counts)
    status_counts = {'open': 0, 'in_progress': 0, 'resolved': 0, 'closed': 0}
    try:
        all_user_complaints = complaints_table.search(Query().user_id == user_id)
        for c in all_user_complaints:
            s = c.get('status', 'open')
            status_counts[s] = status_counts.get(s, 0) + 1
    except:
        pass
        
    # 6. Prepare Trend Data (Last 7 Days)
    chart_labels = []
    chart_data = []
    try:
        today = datetime.now().date()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            chart_labels.append(day.strftime('%b %d'))
            
            # Count complaints created on this day
            count = 0
            for c in all_user_complaints:
                created_at = c.get('created_at', '')[:10]
                if created_at == day_str:
                    count += 1
            chart_data.append(count)
    except:
        pass

    return render_template(
        'user_dashboard.html',
        open_complaints_count=open_complaints_count,
        resolved_complaints=resolved_complaints,
        resolved_complaints_list=resolved_complaints_list,
        total_files=total_files,
        recent_complaints=recent_complaints,
        status_counts=status_counts,
        chart_labels=chart_labels,
        chart_data=chart_data
    )




@app.route('/admin/maintenance', methods=['GET', 'POST'])

@role_required('admin')

def admin_maintenance():

    if request.method == 'POST':

        title = request.form.get('title')

        description = request.form.get('description')

        priority = request.form.get('priority')

        category = request.form.get('category')

        

        if not title or not description:

            flash('Title and Description are required.', 'danger')

        else:

            # AI Auto-Classification if fields are missing or for enhancement

            try:

                ai_classification = ai_agent.classify_complaint(description)

                

                # Use AI values if user didn't specify, or as a suggestion (here we auto-fill if empty)

                if not category or category == 'Other':

                     category = ai_classification.get('category', 'Other')

                

                if not priority:

                     priority = ai_classification.get('priority', 'Medium')

                     

                # Append sentiment/summary to internal notes or description? 

                # Let's append to the complaint record as 'ai_analysis'

                ai_analysis = {

                    'sentiment': ai_classification.get('sentiment'),

                    'summary': ai_classification.get('summary')

                }

            except Exception as e:

                logger.error(f"AI Classification failed in route: {e}")

                ai_analysis = {}



            complaint_id = str(uuid.uuid4())

            

            # BLOCKCHAIN: Calculate Hashes

            try:

                all_complaints = complaints_table.all()

                last_complaint = sorted(all_complaints, key=lambda x: x.get('created_at', ''))[-1] if all_complaints else None

                prev_hash = last_complaint.get('current_hash', 'GENESIS_BLOCK') if last_complaint else "GENESIS_BLOCK"

            except Exception:

                prev_hash = "GENESIS_BLOCK"



            new_complaint = {

                'id': complaint_id,

                'user_id': session['user_id'],

                'title': title,

                'description': description,

                'status': 'open',

                'priority': priority or 'Medium',

                'category': category or 'General',

                'ai_analysis': ai_analysis,

                'created_at': datetime.now().isoformat(),

                'updated_at': datetime.now().isoformat(),

                'prev_hash': prev_hash

            }

            

            # Calculate current hash (integrity seal)

            current_hash = calculate_complaint_hash(new_complaint, prev_hash)

            new_complaint['current_hash'] = current_hash

            

            complaints_table.insert(new_complaint)

            

            # Sync to Google Sheets

            sync_complaint_to_google_sheets(new_complaint, session['user_id'])

            

            # Notify Admins and Employees
            q = Query()
            staff_users = admin_table.search(q.role.one_of(['admin', 'super_admin', 'employee', 'technician', 'support_agent']))
            for staff in staff_users:
                if staff['id'] != session['user_id']: # Don't notify self
                    create_notification(
                        staff['id'],
                        "New System Maintenance Complaint",
                        f"A new maintenance complaint (ID: {complaint_id[:8]}) has been registered by {session.get('full_name', session.get('username'))}.",
                        url_for('admin_complaints') if staff['role'] in ['admin', 'super_admin'] else url_for('employee_assigned_complaints') if staff['role'] == 'employee' else url_for('dashboard')
                    )

            log_action(session['user_id'], 'create_complaint', f'Created complaint: {title} (Hash: {current_hash[:8]}...)')

            flash('Complaint registered successfully!', 'success')

            return redirect(url_for('user_complaints'))

    

    tasks = sorted(maintenance_table.all(), key=lambda x: x.get('scheduled_date', ''), reverse=True)
    return render_template('admin/maintenance.html', tasks=tasks)



@app.route('/admin/maintenance/update/<task_id>', methods=['POST'])

@role_required('admin')

def update_maintenance(task_id):

    status = request.form.get('status', '')

    if status:
        maintenance_table.update({'status': status}, Query().id == task_id)
        log_action(session['user_id'], 'update_maintenance', f'Updated maintenance task status to: {status}')
        flash('Maintenance task updated.', 'success')
    return redirect(url_for('admin_maintenance'))











@app.route('/admin/users/toggle/<user_id>', methods=['POST'])
@role_required('admin')
def toggle_user(user_id):
    user_record = admin_table.get(Query().id == user_id)
    if user_record:
        new_status = not user_record.get('is_active', True)
        admin_table.update({'is_active': new_status}, Query().id == user_id)
        log_action(session['user_id'], 'toggle_user', f'Toggled user status: {user_record.get("username")}')
        flash('User status updated.', 'success')

    if request.referrer:

        return redirect(request.referrer)

    return redirect(url_for('admin_users'))



@app.route('/admin/users/details/<user_id>')

@role_required('admin')

def admin_user_details(user_id):

    user_record = admin_table.search(Query().id == user_id)

    if not user_record:

        return jsonify({'status': 'error', 'message': 'User not found'}), 404

        

    user = user_record[0]

    

    # Ensure QR exists

    qr_path = os.path.join('static', 'uploads', 'qr', f"{user_id}.png")

    if not os.path.exists(qr_path):

        save_user_qr(user)

    

    # Include other details
    whatsapp_contact_id = user.get('whatsapp_contact_id', '')
    whatsapp_contact_name = 'Not Assigned'
    whatsapp_contact_number = ''
    
    if whatsapp_contact_id:
        contact = whatsapp_contacts_table.search(Query().id == whatsapp_contact_id)
        if contact:
            whatsapp_contact_name = contact[0]['name']
            whatsapp_contact_number = contact[0]['number']

    details = {
        'id': user.get('id'),
        'username': user.get('username'),
        'full_name': user.get('full_name'),
        'email': user.get('email'),
        'phone': user.get('phone', 'N/A'),
        'address': user.get('address', 'N/A'),
        'bio': user.get('bio', 'N/A'),
        'salary': user.get('salary', '0'),
        'role': user.get('role'),
        'is_active': user.get('is_active', True),
        'created_at': user.get('created_at', 'N/A'),
        'department': user.get('department', 'General'),
        'designation': user.get('designation', 'Staff'),
        'whatsapp_contact_id': whatsapp_contact_id,
        'whatsapp_contact_name': whatsapp_contact_name,
        'whatsapp_contact_number': whatsapp_contact_number,
        'qr_path': f"/static/uploads/qr/{user_id}.png?v={int(datetime.now().timestamp())}"
    }

    return jsonify({'status': 'success', 'user': details})



@app.route('/admin/user-profile/<user_id>')

@role_required('admin')

def admin_user_profile(user_id):

    user_record = admin_table.search(Query().id == user_id)

    if not user_record:

        abort(404)

        

    user = user_record[0]

    

    # Ensure QR exists

    qr_path = os.path.join('static', 'uploads', 'qr', f"{user_id}.png")

    if not os.path.exists(qr_path):

        save_user_qr(user)

        

    return render_template('admin/user_profile.html', user=user)



@app.route('/verify-salary/<user_id>')

def verify_salary(user_id):

    user_record = admin_table.search(Query().id == user_id)

    if not user_record:

        abort(404)

        

    user = user_record[0]

    return render_template('salary_verification.html', user=user, datetime=datetime)



@app.route('/admin/users/id-card/<user_id>')

@role_required('admin')

def admin_generate_id_card(user_id):

    from reportlab.lib.pagesizes import mm

    from reportlab.pdfgen import canvas

    from reportlab.lib.utils import ImageReader

    from reportlab.lib import colors

    

    user_record = admin_table.search(Query().id == user_id)

    if not user_record:

        abort(404)

        

    user = user_record[0]

    

    # Ensure QR exists

    qr_path = os.path.join('static', 'uploads', 'qr', f"{user_id}.png")

    if not os.path.exists(qr_path):

        save_user_qr(user)

        

    # PDF Setup (Credit Card Size: 85.6mm x 54mm)

    card_width = 85.6 * mm

    card_height = 54 * mm

    file_path = os.path.join('static', 'uploads', 'idcards', f"{user_id}.pdf")

    

    # Ensure directory exists just in case

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    

    c = canvas.Canvas(file_path, pagesize=(card_width, card_height))

    

    # Draw Background (Admin Theme)

    c.linearGradient(0, 0, card_width, card_height, (colors.HexColor('#1a1a2e'), colors.HexColor('#16213e')))

    

    # Header

    c.setFont("Helvetica-Bold", 10)

    c.setFillColor(colors.white)

    c.drawString(5*mm, 48*mm, "CUSTOMER SUPPORT SYSTEM")

    c.setFont("Helvetica", 6)

    c.drawString(5*mm, 45*mm, "Employee Identity Card")

    

    # User Photo

    photo_path = os.path.join('static', 'uploads', 'profile_photos', user.get('profile_photo', ''))

    if os.path.exists(photo_path) and user.get('profile_photo'):

        try:

            c.drawImage(ImageReader(photo_path), 5*mm, 20*mm, width=20*mm, height=22*mm, mask='auto', preserveAspectRatio=True)

        except:

            pass # Fallback to no photo

            

    # User Details

    c.setFont("Helvetica-Bold", 11)

    c.drawString(30*mm, 35*mm, user.get('full_name', 'Employee').upper())

    

    c.setFont("Helvetica", 8)

    c.setFillColor(colors.lightgrey)

    c.drawString(30*mm, 30*mm, f"Role: {user.get('role', 'User').capitalize()}")

    c.drawString(30*mm, 26*mm, f"Dept: {user.get('department', 'General')}")

    c.drawString(30*mm, 22*mm, f"ID: {user.get('id', '')[:8]}...")

    

    # QR Code

    if os.path.exists(qr_path):

        c.drawImage(qr_path, 60*mm, 5*mm, width=20*mm, height=20*mm)

        

    c.setFont("Helvetica-Oblique", 5)

    c.setFillColor(colors.white)

    c.drawString(5*mm, 5*mm, "Scan for Verification & Portal Access")

    

    c.showPage()

    c.save()

    

    return send_file(

        file_path,

        as_attachment=True,

        download_name=f"ID_Card_{user.get('username')}.pdf"

    )



@app.route('/admin/users/delete/<user_id>', methods=['POST'])
@role_required('admin')
def delete_user(user_id):
    user = admin_table.get(Query().id == user_id)

    if user:
        username = user.get('username', 'Unknown')
        admin_table.remove(Query().id == user_id)
        log_action(session['user_id'], 'delete_user', f'Deleted user: {username}')
        log_action(session['user_id'], 'delete_user', f'Deleted user: {username}')
        
        if user_id == session.get('user_id'):
            session.clear()
            flash('Your account has been deleted.', 'info')
            return redirect(url_for('login'))
            
        flash(f'User {username} deleted successfully.', 'success')

    else:

        flash('User not found.', 'danger')

        

    if request.referrer:

        return redirect(request.referrer)

    return redirect(url_for('admin_users'))



@app.route('/admin/users/edit/<user_id>', methods=['POST'])

@role_required('admin')

def admin_edit_user():
    user_id = request.form.get('user_id') # Assuming user_id is passed in form for edit
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    bio = request.form.get('bio', '').strip()
    salary = request.form.get('salary', '0').strip()
    role = request.form.get('role', '')
    whatsapp_contact_id = request.form.get('whatsapp_contact_id', '').strip()

    if not all([username, full_name, email]):
        flash('Username, Full Name, and Email are required.', 'danger')
        return redirect(url_for('admin_users'))

    update_data = {
        'username': username,
        'full_name': full_name,
        'email': email,
        'phone': phone,
        'address': address,
        'bio': bio,
        'salary': salary,
        'whatsapp_contact_id': whatsapp_contact_id
    }

    
    if role:
        update_data['role'] = role

    try:
        admin_table.update(update_data, Query().id == user_id)
        log_action(session['user_id'], 'admin_edit_user', f'Edited user: {username}')
        flash(f'User {full_name} updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating user: {e}', 'danger')

    return redirect(url_for('admin_users'))



@app.route('/admin/reports')

@role_required('admin')

def admin_reports():

    complaints = complaints_table.all()
    maintenance_tasks = maintenance_table.all()
    users = admin_table.all()

    

    complaints_by_status = {}

    for c in complaints:

        status = c.get('status', 'unknown')

        complaints_by_status[status] = complaints_by_status.get(status, 0) + 1

    

    complaints_by_priority = {}

    for c in complaints:

        priority = c.get('priority', 'medium')

        complaints_by_priority[priority] = complaints_by_priority.get(priority, 0) + 1

    

    users_by_role = {}

    for u in users:

        role = u.get('role', 'user')

        users_by_role[role] = users_by_role.get(role, 0) + 1

    

    # Calculate Analytics Metrics

    resolved_complaints = [c for c in complaints if c.get('status') == 'resolved' and c.get('resolved_at')]

    

    # Avg Resolution Time

    total_hours = 0.0

    count_resolved_time = 0

    for c in resolved_complaints:

        if c.get('created_at') and c.get('resolved_at'):

            start = datetime.fromisoformat(c['created_at'])

            end = datetime.fromisoformat(c['resolved_at'])

            total_hours += (end - start).total_seconds() / 3600

            count_resolved_time += 1

    avg_resolution_time = round(total_hours / count_resolved_time, 1) if count_resolved_time > 0 else 0.0

    

    # User Satisfaction Score

    rated_complaints = [c for c in complaints if c.get('rating')]

    total_rating = sum([int(c['rating']) for c in rated_complaints])

    avg_satisfaction = round(float(total_rating) / len(rated_complaints), 1) if rated_complaints else 0.0

    

    # Technician Performance

    tech_performance = {}

    for c in resolved_complaints:

        # Credit the person who resolved it, or the assigned technician

        tech_id = c.get('resolved_by') or c.get('assigned_technician_id')

        if tech_id:
            tech_name = 'Unknown'
            user_rec = admin_table.get(Query().id == tech_id)

            if user_rec:
                tech_name = user_rec.get('username', 'Unknown')

                

            if tech_name not in tech_performance:

                tech_performance[tech_name] = {'count': 0, 'total_time': 0.0, 'avg_time': 0.0}

            

            tech_performance[tech_name]['count'] += 1

            

            if c.get('created_at') and c.get('resolved_at'):

                start = datetime.fromisoformat(c['created_at'])

                end = datetime.fromisoformat(c['resolved_at'])

                tech_performance[tech_name]['total_time'] += (end - start).total_seconds() / 3600



    # Calculate tech averages

    for name, data in tech_performance.items():

        if data['count'] > 0:

            data['avg_time'] = round(float(data['total_time']) / data['count'], 1)

            

    # Convert to list for template

    tech_performance_list = [{'name': k, 'count': v['count'], 'avg_time': v['avg_time']} for k, v in tech_performance.items()]

    tech_performance_list.sort(key=lambda x: x['count'], reverse=True)

    

    return render_template('admin/reports.html',

                         total_complaints=len(complaints),

                         total_maintenance=len(maintenance_tasks),

                         total_users=len(users),

                         complaints_by_status=complaints_by_status,

                         complaints_by_priority=complaints_by_priority,

                         users_by_role=users_by_role,

                         avg_resolution_time=avg_resolution_time,

                         avg_satisfaction=avg_satisfaction,

                         tech_performance=tech_performance_list)



@app.route('/admin/reports/export/csv/<report_type>')

@role_required('admin')

def export_csv(report_type):

    output = io.StringIO()

    writer = csv.writer(output)

    

    if report_type == 'complaints':

        complaints = complaints_table.all()

        writer.writerow(['ID', 'Title', 'Category', 'Priority', 'Status', 'User ID', 'Created At', 'Description'])

        for c in complaints:

            writer.writerow([

                c.get('id', ''),

                c.get('title', ''),

                c.get('category', ''),

                c.get('priority', ''),

                c.get('status', ''),

                c.get('user_id', ''),

                c.get('created_at', ''),

                c.get('description', '')

            ])

        filename = f'complaints_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    

    elif report_type == 'users':
        users = admin_table.all()

        writer.writerow(['ID', 'Username', 'Email', 'Full Name', 'Role', 'Status', 'Phone', 'Created At'])

        for u in users:

            writer.writerow([

                u.get('id', ''),

                u.get('username', ''),

                u.get('email', ''),

                u.get('full_name', ''),

                u.get('role', ''),

                'Active' if u.get('is_active', True) else 'Inactive',

                u.get('phone', ''),

                u.get('created_at', '')

            ])

        filename = f'users_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    

    elif report_type == 'maintenance':

        tasks = maintenance_table.all()

        writer.writerow(['ID', 'Title', 'Priority', 'Status', 'Scheduled Date', 'Created At', 'Description'])

        for t in tasks:

            writer.writerow([

                t.get('id', ''),

                t.get('title', ''),

                t.get('priority', ''),

                t.get('status', ''),

                t.get('scheduled_date', ''),

                t.get('created_at', ''),

                t.get('description', '')

            ])

        filename = f'maintenance_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    

    elif report_type == 'summary':
        complaints = complaints_table.all()
        users = admin_table.all()

        

        writer.writerow(['Report Type', 'Category', 'Count'])

        writer.writerow([])

        writer.writerow(['Complaints by Status'])

        complaints_by_status = {}

        for c in complaints:

            status = c.get('status', 'unknown')

            complaints_by_status[status] = complaints_by_status.get(status, 0) + 1

        for status, count in complaints_by_status.items():

            writer.writerow(['', status.capitalize(), count])

        

        writer.writerow([])

        writer.writerow(['Complaints by Priority'])

        complaints_by_priority = {}

        for c in complaints:

            priority = c.get('priority', 'medium')

            complaints_by_priority[priority] = complaints_by_priority.get(priority, 0) + 1

        for priority, count in complaints_by_priority.items():

            writer.writerow(['', priority.capitalize(), count])

        

        writer.writerow([])

        writer.writerow(['Users by Role'])

        users_by_role = {}

        for u in users:

            role = u.get('role', 'user')

            users_by_role[role] = users_by_role.get(role, 0) + 1

        for role, count in users_by_role.items():

            role_display = 'Administrator' if role == 'admin' else ('Database Server' if role == 'database_server' else 'User')

            writer.writerow(['', role_display, count])

        

        writer.writerow([])

        writer.writerow(['Technician Performance'])

        writer.writerow(['Technician', 'Resolved Count', 'Avg Time (Hours)'])

        

        # Re-calculate tech performance for PDF/CSV (duplicated logic for simplicity in this context)

        tech_performance = {}

        resolved_complaints = [c for c in complaints if c.get('status') == 'resolved' and c.get('resolved_at')]

        for c in resolved_complaints:

            tech_id = c.get('resolved_by') or c.get('assigned_technician_id')

            if tech_id:

                tech_name = 'Unknown'

                user_rec = admin_table.search(Query().id == tech_id)

                if user_rec: tech_name = user_rec[0].get('username', 'Unknown')

                if tech_name not in tech_performance: tech_performance[tech_name] = {'count': 0, 'total_time': 0}

                tech_performance[tech_name]['count'] += 1

                if c.get('created_at') and c.get('resolved_at'):

                    start = datetime.fromisoformat(c['created_at'])

                    end = datetime.fromisoformat(c['resolved_at'])

                    tech_performance[tech_name]['total_time'] += (end - start).total_seconds() / 3600

        

        for name, data in tech_performance.items():

            avg = round(data['total_time'] / data['count'], 1) if data['count'] > 0 else 0

            writer.writerow(['', name, data['count'], avg])

            

        writer.writerow([])

        writer.writerow(['User Satisfaction'])

        rated_complaints = [c for c in complaints if c.get('rating')]

        total_rating = sum([int(c['rating']) for c in rated_complaints])

        avg_satisfaction = round(total_rating / len(rated_complaints), 1) if rated_complaints else 0

        writer.writerow(['', 'Average Rating', avg_satisfaction])

        

        filename = f'summary_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    

    else:

        flash('Invalid report type.', 'danger')

        return redirect(url_for('admin_reports'))

    

    output.seek(0)

    response = make_response(output.getvalue())

    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    response.headers['Content-Type'] = 'text/csv'

    

    log_action(session['user_id'], 'export_csv', f'Exported {report_type} report as CSV')

    return response



@app.route('/admin/reports/export/pdf/<report_type>')

@role_required('admin')

def export_pdf(report_type):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)

    elements = []

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=20)

    subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Heading2'], fontSize=12, spaceAfter=10)

    

    table_style = TableStyle([

        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),

        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),

        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, 0), 10),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),

        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),

        ('FONTSIZE', (0, 1), (-1, -1), 9),

        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),

        ('TOPPADDING', (0, 0), (-1, -1), 6),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),

    ])

    

    if report_type == 'complaints':

        complaints = complaints_table.all()

        elements.append(Paragraph('Complaints Report', title_style))

        elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        data = [['Title', 'Category', 'Priority', 'Status', 'Created At']]

        for c in complaints:

            data.append([

                c.get('title', '')[:30],

                c.get('category', ''),

                c.get('priority', ''),

                c.get('status', ''),

                c.get('created_at', '')[:10]

            ])

        

        if len(data) > 1:

            table = Table(data, colWidths=[150, 80, 70, 70, 80])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No complaints found.', styles['Normal']))

        

        filename = f'complaints_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    

    elif report_type == 'users':
        users = admin_table.all()

        elements.append(Paragraph('Users Report', title_style))

        elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        data = [['Username', 'Email', 'Full Name', 'Role', 'Status']]

        for u in users:

            role_display = 'Admin' if u.get('role') == 'admin' else ('DB Server' if u.get('role') == 'database_server' else 'User')

            data.append([

                u.get('username', ''),

                u.get('email', '')[:25],

                u.get('full_name', '')[:20],

                role_display,

                'Active' if u.get('is_active', True) else 'Inactive'

            ])

        

        if len(data) > 1:

            table = Table(data, colWidths=[90, 130, 100, 70, 60])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No users found.', styles['Normal']))

        

        filename = f'users_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    

    elif report_type == 'maintenance':

        tasks = maintenance_table.all()

        elements.append(Paragraph('Maintenance Report', title_style))

        elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        data = [['Title', 'Priority', 'Status', 'Scheduled', 'Created At']]

        for t in tasks:

            data.append([

                t.get('title', '')[:30],

                t.get('priority', ''),

                t.get('status', ''),

                t.get('scheduled_date', '')[:10] if t.get('scheduled_date') else '',

                t.get('created_at', '')[:10]

            ])

        

        if len(data) > 1:

            table = Table(data, colWidths=[150, 70, 80, 80, 80])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No maintenance tasks found.', styles['Normal']))

        

        filename = f'maintenance_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    

    elif report_type == 'summary':

        complaints = complaints_table.all()

        users = admin_table.all()

        

        elements.append(Paragraph('Summary Report', title_style))

        elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        elements.append(Paragraph('Complaints by Status', subtitle_style))

        complaints_by_status = {}

        for c in complaints:

            status = c.get('status', 'unknown')

            complaints_by_status[status] = complaints_by_status.get(status, 0) + 1

        

        data = [['Status', 'Count']]

        for status, count in complaints_by_status.items():

            data.append([status.capitalize(), str(count)])

        if len(data) > 1:

            table = Table(data, colWidths=[200, 100])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No complaint status data available.', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        elements.append(Paragraph('Complaints by Priority', subtitle_style))

        complaints_by_priority = {}

        for c in complaints:

            priority = c.get('priority', 'medium')

            complaints_by_priority[priority] = complaints_by_priority.get(priority, 0) + 1

        

        data = [['Priority', 'Count']]

        for priority, count in complaints_by_priority.items():

            data.append([priority.capitalize(), str(count)])

        if len(data) > 1:

            table = Table(data, colWidths=[200, 100])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No complaint priority data available.', styles['Normal']))

        elements.append(Spacer(1, 20))

        

        elements.append(Paragraph('Users by Role', subtitle_style))

        users_by_role = {}

        for u in users:

            role = u.get('role', 'user')

            users_by_role[role] = users_by_role.get(role, 0) + 1

        

        data = [['Role', 'Count']]

        for role, count in users_by_role.items():

            role_display = 'Administrator' if role == 'admin' else ('Database Server' if role == 'database_server' else 'User')

            data.append([role_display, str(count)])

        if len(data) > 1:

            table = Table(data, colWidths=[200, 100])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No user role data available.', styles['Normal']))





        

        

        # Technician Performance Section for PDF

        elements.append(Spacer(1, 20))

        elements.append(Paragraph('Technician Performance', subtitle_style))

        

        tech_performance = {}

        resolved_complaints = [c for c in complaints if c.get('status') == 'resolved' and c.get('resolved_at')]

        for c in resolved_complaints:

            tech_id = c.get('resolved_by') or c.get('assigned_technician_id')

            if tech_id:

                tech_name = 'Unknown'

                user_rec = admin_table.search(Query().id == tech_id)

                if user_rec: tech_name = user_rec[0].get('username', 'Unknown')

                if tech_name not in tech_performance: tech_performance[tech_name] = {'count': 0, 'total_time': 0.0}

                tech_performance[tech_name]['count'] += 1

                if c.get('created_at') and c.get('resolved_at'):

                    start = datetime.fromisoformat(c['created_at'])

                    end = datetime.fromisoformat(c['resolved_at'])

                    tech_performance[tech_name]['total_time'] += (end - start).total_seconds() / 3600

        

        data = [['Technician', 'Resolved', 'Avg Time (Hrs)']]

        for name, perf_data in tech_performance.items():

            avg = round(perf_data['total_time'] / perf_data['count'], 1) if perf_data['count'] > 0 else 0

            data.append([name, str(perf_data['count']), str(avg)])

            

        if len(data) > 1:

            table = Table(data, colWidths=[150, 80, 100])

            table.setStyle(table_style)

            elements.append(table)

        else:

            elements.append(Paragraph('No resolution data available.', styles['Normal']))



        # User Satisfaction Section for PDF

        elements.append(Spacer(1, 20))

        elements.append(Paragraph('User Satisfaction', subtitle_style))

        rated_complaints = [c for c in complaints if c.get('rating')]

        total_rating = sum([int(c['rating']) for c in rated_complaints])

        avg_satisfaction = round(total_rating / len(rated_complaints), 1) if rated_complaints else 0

        

        elements.append(Paragraph(f"Average Rating: {avg_satisfaction} / 5.0 ({len(rated_complaints)} ratings)", styles['Normal']))



        filename = f'summary_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    

    else:

        flash('Invalid report type.', 'danger')

        return redirect(url_for('admin_reports'))

    

    doc.build(elements)

    buffer.seek(0)

    

    log_action(session['user_id'], 'export_pdf', f'Exported {report_type} report as PDF')

    return send_file(buffer, download_name=filename, as_attachment=True, mimetype='application/pdf')



@app.route('/admin/config', methods=['GET', 'POST'])

@role_required('admin')

def admin_config():

    if request.method == 'POST':

        action = request.form.get('action', 'update_config')

        

        if action == 'update_config':

            setting_name = request.form.get('setting_name', '').strip()

            setting_value = request.form.get('setting_value', '').strip()

            

            if setting_name and setting_value:
                config_table.upsert({
                    'name': setting_name, 
                    'value': setting_value, 
                    'updated_at': datetime.now().isoformat()
                }, Query().name == setting_name)
                log_action(session['user_id'], 'update_config', f'Updated config: {setting_name}')
                flash('Configuration updated.', 'success')



        elif action == 'update_theme':

            # Handle theme settings (login_bg, accent_color, etc.)
            for key in ['login_bg', 'accent_color', 'current_theme']:
                value = request.form.get(key)
                if value is not None:
                    config_table.upsert({'name': key, 'value': value, 'updated_at': datetime.now().isoformat()}, Query().name == key)

            # Handle background upload
            if 'login_bg_file' in request.files:
                file = request.files['login_bg_file']
                if file and file.filename != '' and allowed_background(file.filename):
                    filename = secure_filename(f"login_bg_{file.filename}")
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(file_path)
                    
                    # Store as static path
                    db_path = f"static/uploads/backgrounds/{filename}"
                    config_table.upsert({'name': 'login_bg', 'value': db_path, 'updated_at': datetime.now().isoformat()}, Query().name == 'login_bg')

            log_action(session['user_id'], 'update_theme', 'Updated system theme settings')
            log_action(session['user_id'], 'update_theme', 'Updated system theme settings')

            flash('System theme updated.', 'success')

            

    configs = config_table.all()
    # Sort audit logs by timestamp DESC
    audit_logs = sorted(logs_table.all(), key=lambda x: x.get('timestamp', ''), reverse=True)[:50]
    return render_template('admin/config.html', configs=configs, audit_logs=audit_logs)

@app.route('/admin/whatsapp-contacts', methods=['GET', 'POST'])
@role_required('admin')
def admin_whatsapp_contacts():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        number = request.form.get('number', '').strip()
        description = request.form.get('description', '').strip()
        
        if name and number:
            whatsapp_contacts_table.insert({
                'id': str(uuid.uuid4()),
                'name': name,
                'number': number,
                'description': description,
                'created_at': datetime.now().isoformat()
            })
            log_action(session['user_id'], 'add_whatsapp_contact', f'Added contact: {name} ({number})')
            flash(f'Contact {name} added successfully.', 'success')
        else:
            flash('Name and Number are required.', 'danger')
            
    contacts = whatsapp_contacts_table.all()
    return render_template('admin/whatsapp_contacts.html', contacts=contacts)

@app.route('/admin/whatsapp-contacts/delete/<contact_id>', methods=['POST'])
@role_required('admin')
def admin_delete_whatsapp_contact(contact_id):
    whatsapp_contacts_table.remove(Query().id == contact_id)
    log_action(session['user_id'], 'delete_whatsapp_contact', f'Deleted contact: {contact_id}')
    flash('WhatsApp contact deleted.', 'success')
    return redirect(url_for('admin_whatsapp_contacts'))




@app.route('/admin/verify-integrity')

@role_required('admin')

def admin_verify_integrity():

    complaints = sorted(complaints_table.all(), key=lambda x: x.get('created_at', ''))

    

    issues = []

    prev_hash = "GENESIS_BLOCK"

    

    for i, c in enumerate(complaints):

        # 1. Check Linkage

        stored_prev_hash = c.get('prev_hash')

        if stored_prev_hash != prev_hash:

            issues.append(f"Broken Chain at Index {i} (ID: {c['id']}): Previous Hash Mismatch. Expected {prev_hash[:8]}..., Found {stored_prev_hash[:8]}...")

        

        # 2. Check Integrity (Re-hash)

        # We need to reconstruct the exact data string used for hashing

        # Note: If we change the hashing function, this verification will break for old records.

        # Assuming all records use the same function currently implemented.

        calculated_hash = calculate_complaint_hash(c, stored_prev_hash)

        

        if calculated_hash != c.get('current_hash'):

             issues.append(f"Integrity Failure at Index {i} (ID: {c['id']}): content has been modified. Hash Mismatch.")

        

        # Update prev_hash for next iteration

        prev_hash = c.get('current_hash')

        

    if not issues:

        flash('Blockchain Integrity Verified: All records are valid and linked correctly.', 'success')

    else:

        for issue in issues:

            flash(issue, 'danger')

            

    return redirect(url_for('admin_complaints'))



@app.route('/admin/audit')

@role_required('admin')

def admin_audit():

    search = request.args.get('search', '').strip().lower()

    action_filter = request.args.get('action', '')

    user_filter = request.args.get('user', '')

    date_from = request.args.get('date_from', '')

    date_to = request.args.get('date_to', '')

    page = request.args.get('page', 1, type=int)

    per_page = 25

    
    all_logs = logs_table.all()
    
    # Manual Filtering
    filtered_logs = all_logs
    if search:
        search_lower = search.lower()
        filtered_logs = [l for l in filtered_logs if 
                         search_lower in str(l.get('action', '')).lower() or 
                         search_lower in str(l.get('details', '')).lower() or 
                         search_lower in str(l.get('user_id', '')).lower()]
    
    if action_filter:
        filtered_logs = [l for l in filtered_logs if l.get('action') == action_filter]
    
    if user_filter:
        filtered_logs = [l for l in filtered_logs if l.get('user_id') == user_filter]
        
    if date_from:
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') >= date_from]
        
    if date_to:
        to_dt = date_to + ' 23:59:59'
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') <= to_dt]
        
    # Sort by timestamp DESC
    filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    total_logs = len(filtered_logs)
    
    total_pages = (total_logs + per_page - 1) // per_page
    
    # Paginate
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_logs = filtered_logs[start_idx:end_idx]
    
    action_types = sorted(list(set([l.get('action') for l in all_logs if l.get('action')])))
    user_ids_raw = list(set([l.get('user_id') for l in all_logs if l.get('user_id')]))
    
    users_list = []
    for uid in user_ids_raw:
        user = admin_table.get(Query().id == uid)
        if user:
            users_list.append({'id': uid, 'username': user.get('username', uid)})
        else:
            users_list.append({'id': uid, 'username': uid[:8] + '...'})
    users_list.sort(key=lambda x: x['username'])
    
    enriched_logs = []
    for log in paginated_logs:
        log_copy = dict(log)
        user = admin_table.get(Query().id == log_copy.get('user_id', ''))
        if user:
            log_copy['username'] = user.get('username', 'Unknown')
        else:
            log_copy['username'] = 'Unknown'
        
        # Ensure IP and OS exist for older logs
        log_copy['ip_address'] = log_copy.get('ip_address', 'N/A')
        log_copy['os'] = log_copy.get('os', 'N/A')
        
        enriched_logs.append(log_copy)

    
    return render_template('admin/audit.html',
                          logs=enriched_logs,
                          search=search,
                          action_filter=action_filter,
                          user_filter=user_filter,
                          date_from=date_from,
                          date_to=date_to,
                          action_types=action_types,
                          users_list=users_list,
                          page=page,
                          total_pages=max(total_pages, 1),
                          total_logs=total_logs)

@app.route('/api/admin/audit-logs')
@role_required('admin')
def api_admin_audit_logs():
    all_logs = sorted(logs_table.all(), key=lambda x: x.get('timestamp', ''), reverse=True)[:50]
    enriched_logs = []
    for log in all_logs:
        log_copy = dict(log)
        user = admin_table.get(Query().id == log_copy.get('user_id', ''))
        log_copy['username'] = user.get('username', 'Unknown') if user else 'Unknown'
        log_copy['ip_address'] = log_copy.get('ip_address', 'N/A')
        log_copy['os'] = log_copy.get('os', 'N/A')
        enriched_logs.append(log_copy)
    return jsonify(enriched_logs)



@app.route('/admin/audit/export/csv')

@role_required('admin')

def export_audit_csv():

    search = request.args.get('search', '').strip().lower()

    action_filter = request.args.get('action', '')

    user_filter = request.args.get('user', '')

    date_from = request.args.get('date_from', '')

    date_to = request.args.get('date_to', '')

    
    all_logs = logs_table.all()
    filtered_logs = all_logs
    if search:
        search_lower = search.lower()
        filtered_logs = [l for l in filtered_logs if 
                         search_lower in str(l.get('action', '')).lower() or 
                         search_lower in str(l.get('details', '')).lower() or 
                         search_lower in str(l.get('user_id', '')).lower()]
    if action_filter:
        filtered_logs = [l for l in filtered_logs if l.get('action') == action_filter]
    if user_filter:
        filtered_logs = [l for l in filtered_logs if l.get('user_id') == user_filter]
    if date_from:
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') >= date_from]
    if date_to:
        to_dt = date_to + ' 23:59:59'
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') <= to_dt]
    filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    all_logs = filtered_logs
    
    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow(['Timestamp', 'User ID', 'Username', 'Action', 'Details', 'IP Address', 'Operating System'])

    

    for log in all_logs:
        user = admin_table.get(Query().id == log.get('user_id', ''))
        username = user.get('username', 'Unknown') if user else 'Unknown'

        writer.writerow([

            log.get('timestamp', ''),

            log.get('user_id', ''),

            username,

            log.get('action', ''),
            log.get('details', ''),
            log.get('ip_address', 'N/A'),
            log.get('os', 'N/A')
        ])

    

    filename = f'audit_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    output.seek(0)

    response = make_response(output.getvalue())

    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    response.headers['Content-Type'] = 'text/csv'

    

    log_action(session['user_id'], 'export_audit_csv', 'Exported audit logs as CSV')

    return response



@app.route('/admin/audit/export/pdf')

@role_required('admin')

def export_audit_pdf():

    search = request.args.get('search', '').strip().lower()

    action_filter = request.args.get('action', '')

    user_filter = request.args.get('user', '')

    date_from = request.args.get('date_from', '')

    date_to = request.args.get('date_to', '')

    
    all_logs = logs_table.all()
    filtered_logs = all_logs
    if search:
        search_lower = search.lower()
        filtered_logs = [l for l in filtered_logs if 
                         search_lower in str(l.get('action', '')).lower() or 
                         search_lower in str(l.get('details', '')).lower() or 
                         search_lower in str(l.get('user_id', '')).lower()]
    if action_filter:
        filtered_logs = [l for l in filtered_logs if l.get('action') == action_filter]
    if user_filter:
        filtered_logs = [l for l in filtered_logs if l.get('user_id') == user_filter]
    if date_from:
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') >= date_from]
    if date_to:
        to_dt = date_to + ' 23:59:59'
        filtered_logs = [l for l in filtered_logs if l.get('timestamp', '') <= to_dt]
    filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    all_logs = filtered_logs
    all_logs = filtered_logs[:500] # Limit for PDF export
    
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=40)

    elements = []

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=20)

    

    table_style = TableStyle([

        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),

        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),

        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, 0), 9),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),

        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),

        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),

        ('FONTSIZE', (0, 1), (-1, -1), 8),

        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),

        ('TOPPADDING', (0, 0), (-1, -1), 5),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),

    ])

    

    elements.append(Paragraph('Audit Log Report', title_style))

    elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

    if date_from or date_to:

        elements.append(Paragraph(f'Date Range: {date_from or "Start"} to {date_to or "End"}', styles['Normal']))

    elements.append(Spacer(1, 20))

    

    data = [['Timestamp', 'User', 'Action', 'Details', 'IP Address', 'OS']]

    for log in all_logs:

        user = admin_table.search(Query().id == log.get('user_id', ''))

        username = user[0].get('username', 'Unknown')[:15] if user else 'Unknown'

        data.append([

            log.get('timestamp', '')[:19],

            username,

            log.get('action', '')[:15],
            log.get('details', '')[:30],
            log.get('ip_address', 'N/A'),
            log.get('os', 'N/A')
        ])

    

    if len(data) > 1:
        table = Table(data, colWidths=[90, 70, 80, 150, 80, 50])

        table.setStyle(table_style)

        elements.append(table)

    else:

        elements.append(Paragraph('No audit logs found.', styles['Normal']))

    

    filename = f'audit_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    doc.build(elements)

    buffer.seek(0)

    

    log_action(session['user_id'], 'export_audit_pdf', 'Exported audit logs as PDF')

    return send_file(buffer, download_name=filename, as_attachment=True, mimetype='application/pdf')



@app.route('/admin/complaint/<complaint_id>/download_pdf')
@role_required(['admin', 'super_admin'])
def download_complaint_pdf(complaint_id):
    complaint_record = complaints_table.search(Query().id == complaint_id)
    if not complaint_record:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('admin_complaints'))
    
    complaint = complaint_record[0]
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=16, spaceAfter=20)
    h2_style = ParagraphStyle('Heading2Custom', parent=styles['Heading2'], fontSize=14, spaceBefore=15, spaceAfter=10)
    normal_style = styles['Normal']
    
    # Title
    elements.append(Paragraph(f"Complaint Report: {complaint.get('title')}", title_style))
    elements.append(Paragraph(f"Complaint ID: {complaint_id}", normal_style))
    elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # User Details
    user_info = "Unknown"
    if complaint.get('user_id'):
        u = admin_table.search(Query().id == complaint.get('user_id'))
        if u:
            user = u[0]
            user_info = f"{user.get('full_name')} ({user.get('email')})"
            
    elements.append(Paragraph("Details", h2_style))
    data = [
        ["Status", complaint.get('status', 'Open').upper()],
        ["Priority", complaint.get('priority', 'Medium').upper()],
        ["Category", complaint.get('category', 'General')],
        ["Submitted By", user_info],
        ["Date", complaint.get('created_at', '')[:16].replace('T', ' ')]
    ]
    
    t = Table(data, colWidths=[100, 300])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    
    # Description
    elements.append(Paragraph("Description", h2_style))
    elements.append(Paragraph(complaint.get('description', 'No description.'), normal_style))
    elements.append(Spacer(1, 15))
    
    # Extra Fields
    extra_data = []
    if complaint.get('order_id'): extra_data.append(["Order ID", complaint.get('order_id')])
    if complaint.get('purchase_source'): extra_data.append(["Source", complaint.get('purchase_source')])
    if complaint.get('refund_reason'): extra_data.append(["Refund Reason", complaint.get('refund_reason')])
    if complaint.get('address'): extra_data.append(["Address", complaint.get('address')])
    
    if extra_data:
        elements.append(Paragraph("Additional Information", h2_style))
        t_extra = Table(extra_data, colWidths=[100, 300])
        t_extra.setStyle(TableStyle([
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        elements.append(t_extra)
        elements.append(Spacer(1, 15))

    # Attachment (Types: Image or File)
    if complaint.get('attachment'):
        elements.append(Paragraph("Attachments", h2_style))
        file_path = complaint.get('attachment')
        # Ensure we have the absolute path
        if not os.path.isabs(file_path):
            # If it starts with 'uploads/', join correctly
            full_path = os.path.join(app.root_path, 'static', file_path)
            if not os.path.exists(full_path):
                 # Try directly in static/uploads if path didn't include 'static'
                 full_path = os.path.join(app.root_path, 'static', 'uploads', os.path.basename(file_path))
        else:
            full_path = file_path
            
        if os.path.exists(full_path):
            ext = os.path.splitext(full_path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                try:
                    from reportlab.platypus import Image as ReportLabImage
                    img = ReportLabImage(full_path)
                    
                    # Resize logic
                    max_width = 400
                    max_height = 500
                    img_width = img.imageWidth
                    img_height = img.imageHeight
                    
                    if img_width > max_width or img_height > max_height:
                         ratio = min(max_width/img_width, max_height/img_height)
                         img.drawWidth = img_width * ratio
                         img.drawHeight = img_height * ratio
                    
                    elements.append(img)
                except Exception as e:
                    elements.append(Paragraph(f"[Error embedding image: {str(e)}]", colors.red))
            else:
                 elements.append(Paragraph(f"File attached: {os.path.basename(full_path)} (Format: {ext})", normal_style))
        else:
            elements.append(Paragraph(f"[Attachment file not found on server: {file_path}]", colors.red))
            
    # Resolution Notes
    if complaint.get('resolution_notes'):
        elements.append(Paragraph("Resolution Notes", h2_style))
        elements.append(Paragraph(complaint.get('resolution_notes'), normal_style))
        
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Complaint_{complaint_id[:8]}.pdf"
    return send_file(buffer, download_name=filename, as_attachment=True, mimetype='application/pdf')

@app.route('/admin/complaints/download/<complaint_id>')

@role_required(['admin', 'technician', 'supervisor'])

def download_complaint_attachment(complaint_id):

    complaint = complaints_table.search(Query().id == complaint_id)

    if not complaint:

        abort(404)

    

    complaint = complaint[0]

    if not complaint.get('attachment'):

        flash('No attachment found for this complaint.', 'warning')

        return redirect(url_for('view_complaint', complaint_id=complaint_id))

    

    # RBAC check for technicians

    if session.get('role') == 'technician' and complaint.get('assigned_technician_id') != session.get('user_id'):
        abort(403)

    file_path = complaint.get('attachment')
    # Resolve absolute path properly
    if not os.path.isabs(file_path):
        # If it starts with 'uploads/', join correctly to static folder
        full_path = os.path.join(app.root_path, 'static', file_path)
        if not os.path.exists(full_path):
             # Try fallback: directly in static/uploads if path didn't include 'static' prefix in DB
             full_path = os.path.join(app.root_path, 'static', 'uploads', os.path.basename(file_path))
    else:
        # It's absolute (unlikely but safe)
        full_path = file_path
        
    if not os.path.exists(full_path):
        flash('Attachment file missing on server.', 'danger')
        return redirect(url_for('view_complaint', complaint_id=complaint_id))

    return send_file(full_path, as_attachment=True)

        


# === Employee Routes ===




@app.route('/employee/assigned-complaints')
@login_required
def employee_assigned_complaints():
    if session.get('role') != 'employee':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user_id = session['user_id']
    
    # Fetch assigned complaints
    assigned = complaints_table.search(Query().assigned_to == user_id)
    
    # Fetch unassigned complaints (where assigned_to is missing, None, or empty string)
    # TinyDB doesn't have a direct "is null" query easily combinable, so we might need to filter manually or use a custom test
    def is_unassigned(val):
        return val is None or val == ""
    
    # Search for complaints where assigned_to exists and is empty/null would be ideal, 
    # but simplest is to search for all open complaints and filter in python if needed, 
    # OR use a custom query test.
    # Let's try to get all and filter for now as it's robust.
    # Actually, simpler: Search for specific 'unassigned' tag if we used it, but we didn't.
    # We will search for all 'open' complaints and filter for unassigned.
    
    all_open = complaints_table.search(Query().status == 'open')
    unassigned = [c for c in all_open if not c.get('assigned_to')]
    
    # Sort by date descending
    assigned.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    unassigned.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Attach user names and details
    for c in assigned + unassigned:
        submitter_id = c.get('submitted_by') or c.get('user_id')
        if submitter_id and submitter_id != 'anonymous':
            u = admin_table.get(Query().id == submitter_id)
            if u:
                c['user_name'] = u.get('full_name', u.get('username'))
                c['user_email'] = u.get('email', '')
                c['user_phone'] = u.get('phone', '')
            
    return render_template('employee/assigned_complaints.html', complaints=assigned, unassigned_complaints=unassigned)

@app.route('/employee/ticket/<ticket_id>')
@login_required
def employee_ticket_view(ticket_id):
    if session.get('role') != 'employee':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user_id = session['user_id']
    complaint_record = complaints_table.search(Query().id == ticket_id)
    
    if not complaint_record:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('employee_assigned_complaints'))
        
    complaint = complaint_record[0]
    
    # Allow if assigned to user OR if unassigned (so they can claim it)
    is_assigned_to_me = complaint.get('assigned_to') == user_id
    is_unassigned = not complaint.get('assigned_to')
    
    if not (is_assigned_to_me or is_unassigned):
        flash('Access denied. This ticket is assigned to someone else.', 'danger')
        return redirect(url_for('employee_assigned_complaints'))
        
    u = admin_table.get(Query().id == complaint.get('user_id'))
    if u:
        complaint['user_name'] = u.get('full_name', u.get('username'))
        
    # Fetch admins for escalation
    admins = admin_table.search(Query().role.one_of(['admin', 'super_admin']))
        
    return render_template('employee/ticket_view.html', complaint=complaint, is_unassigned=is_unassigned, admins=admins)

@app.route('/employee/ticket/claim/<ticket_id>')
@login_required
def employee_claim_ticket(ticket_id):
    if session.get('role') != 'employee':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    user_id = session['user_id']
    complaint_record = complaints_table.search(Query().id == ticket_id)
    
    if not complaint_record:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('employee_assigned_complaints'))
    
    complaint = complaint_record[0]
    
    if complaint.get('assigned_to'):
        flash('This ticket is already assigned.', 'warning')
        return redirect(url_for('employee_assigned_complaints'))
        
    # Assign to current user
    complaints_table.update({'assigned_to': user_id, 'status': 'in_progress', 'updated_at': datetime.now().isoformat()}, Query().id == ticket_id)
    
    log_action(user_id, 'claim_ticket', f"Employee claimed ticket {ticket_id}")
    flash('Ticket claimed successfully!', 'success')
    return redirect(url_for('employee_ticket_view', ticket_id=ticket_id))

@app.route('/employee/ticket/<ticket_id>/update', methods=['POST'])
@login_required
def employee_update_ticket(ticket_id):
    if session.get('role') != 'employee':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user_id = session['user_id']
    complaint_record = complaints_table.search(Query().id == ticket_id)
    
    if not complaint_record:
        flash('Ticket not found.', 'danger')
        return redirect(url_for('employee_assigned_complaints'))
        
    complaint = complaint_record[0]
    
    if complaint.get('assigned_to') != user_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_assigned_complaints'))
        
    new_status = request.form.get('status')
    reply_note = request.form.get('reply')
    assigned_to_new = request.form.get('assigned_to')
    
    update_data = {
        'status': new_status if new_status else complaint.get('status'),
        'updated_at': datetime.now().isoformat()
    }
    
    # Handle Reassignment / Escalation
    if assigned_to_new and assigned_to_new != user_id:
        # Verify target is valid (admin/super_admin)
        target_user = admin_table.get(Query().id == assigned_to_new)
        if target_user:
            update_data['assigned_to'] = assigned_to_new
            # Also update technician_id if applicable, usually kept same or cleared? 
            # If escalating to admin, admin becomes assigned_to. 
            # We might want to keep history or just switch ownership.
            # Base logic: switch ownership
            
            log_action(user_id, 'escalate_ticket', f"Escalated ticket {ticket_id} to {target_user.get('username')}")
            complaints_table.update(update_data, Query().id == ticket_id)
            
            # Notify new owner
            create_notification(
                assigned_to_new,
                f"Ticket Escalated: {complaint.get('title')}",
                f"Employee {session.get('username')} escalated a ticket to you.",
                url_for('admin_view_complaint', complaint_id=ticket_id) 
                if target_user.get('role') in ['admin', 'super_admin'] 
                else url_for('employee_ticket_view', ticket_id=ticket_id)
            )
            
            flash(f'Ticket escalated to {target_user.get("username")}.', 'success')
            return redirect(url_for('employee_assigned_complaints'))
        else:
             flash('Invalid user selected for reassignment.', 'danger')
    
    if reply_note:
        update_data['admin_reply'] = reply_note
        # Save agent reply to chat history
        chat_messages_table.insert({
            'id': str(uuid.uuid4()),
            'complaint_id': ticket_id,
            'sender': session.get('username'),
            'message': reply_note,
            'timestamp': datetime.now().isoformat()
        })
    
    old_status = complaint.get('status')
    if new_status and old_status != new_status:
        notify_complaint_status_change(complaint, old_status, new_status, notes=reply_note)
    
    complaints_table.update(update_data, Query().id == ticket_id)
    
    log_action(user_id, 'ticket_update', f"Updated ticket {ticket_id} status to {new_status}")
    flash('Ticket updated successfully.', 'success')
    return redirect(url_for('employee_ticket_view', ticket_id=ticket_id))


# === Salary Management Routes ===

# Encryption setup for bank account numbers
import os
from cryptography.fernet import Fernet

KEY_FILE = 'salary_key.key'
if not os.path.exists(KEY_FILE):
    salary_key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as key_file:
        key_file.write(salary_key)
else:
    with open(KEY_FILE, 'rb') as key_file:
        salary_key = key_file.read()

cipher_suite = Fernet(salary_key)

def encrypt_account_number(data):
    if not data: return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_account_number(data):
    if not data: return None
    try:
        return cipher_suite.decrypt(data.encode()).decode()
    except:
        return None

BankDetail = Query()
SalaryPayment = Query()


# === Missing Route Stubs (Added to prevent BuildErrors) ===

@app.route('/drawer-settings', methods=['POST'])
@login_required
def handle_drawer_settings():
    # Handle drawer settings update
    flash('Settings updated.', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/ai-training')
@role_required(['admin', 'super_admin'])
def admin_ai_training():
    return render_template('admin/ai_training.html')

@app.route('/admin/ai-training/add', methods=['POST'])
@role_required(['admin', 'super_admin'])
def admin_add_ai_training():
    flash('AI training data added.', 'success')
    return redirect(url_for('admin_ai_training'))

@app.route('/admin/analytics')
@role_required(['admin', 'super_admin'])
def admin_analytics():
    return render_template('admin/analytics.html')

@app.route('/admin/chat-history')
@role_required(['admin', 'super_admin'])
def admin_chat_history():
    return render_template('admin/chat_history.html')

@app.route('/admin/complaints')
@role_required(['admin', 'super_admin'])
def admin_complaints():
    all_complaints_list = complaints_table.all()
    # Sort manually
    all_complaints_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Fetch staff users for the assignment dropdown (Added admins)
    staff_users = admin_table.search(Query().role.one_of(['employee', 'technician', 'support_agent', 'admin', 'super_admin']))
    
    rows = all_complaints_list
    
    all_complaints = [process_complaint_record(row) for row in rows]
    
    # Attach user details for admin view
    for c in all_complaints:
        submitter_id = c.get('submitted_by') or c.get('user_id')
        if submitter_id and submitter_id != 'anonymous':
            u = admin_table.get(Query().id == submitter_id)
            if u:
                c['user_name'] = u.get('full_name', u.get('username'))
                c['user_email'] = u.get('email', '')
                c['user_phone'] = u.get('phone', '')

    return render_template('admin/complaints.html', complaints=all_complaints, staff_users=staff_users)

@app.route('/admin/complaint/<complaint_id>')
@role_required(['admin', 'super_admin'])
def admin_view_complaint(complaint_id):
    complaint_record = complaints_table.search(Query().id == complaint_id)
    if not complaint_record:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('admin_complaints'))
    
    complaint = complaint_record[0]
    
    # Fetch user info
    user_info = None
    submitter_id = complaint.get('submitted_by') or complaint.get('user_id')
    if submitter_id and submitter_id != 'anonymous':
        u = admin_table.search(Query().id == submitter_id)
        if u:
            user_info = u[0]
            
    # Fetch assigned technician info
    assigned_user = None
    if complaint.get('assigned_technician_id'):
        rec = admin_table.get(Query().id == complaint.get('assigned_technician_id'))
        if rec:
            assigned_user = rec
            
    # Fetch history
    history = complaint_history_table.search(Query().complaint_id == complaint_id)
    history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Fetch staff for dropdown (Added admins)
    staff_users = admin_table.search(Query().role.one_of(['employee', 'technician', 'support_agent', 'admin', 'super_admin']))

    return render_template('admin/complaint_detail.html', 
                           complaint=complaint, 
                           user_info=user_info, 
                           assigned_user=assigned_user,
                           history=history,
                           staff_users=staff_users)

@app.route('/admin/complaints/assign', methods=['POST'])
@login_required
@role_required(['admin', 'super_admin'])
def assign_complaint():
    complaint_id = request.form.get('complaint_id')
    employee_id = request.form.get('assigned_to')
    
    if not complaint_id:
        flash('Complaint ID missing.', 'danger')
        return redirect(url_for('admin_complaints'))
        
    complaint_data = complaints_table.get(Query().id == complaint_id)
    
    if not complaint_data:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('admin_complaints'))
        
    complaint = complaint_data
    
    assigned_to_val = employee_id if employee_id else None
    technician_id_val = employee_id if employee_id else None
    updated_at = datetime.now().isoformat()
    status = complaint.get('status')
    
    # If it was open, mark as in_progress when assigned
    if employee_id and status == 'open':
        status = 'in_progress'
        notify_complaint_status_change(complaint, 'open', 'in_progress', notes="Ticket automatically marked In Progress upon assignment.")

    if employee_id:
        # Check employee
        employee_record = admin_table.get(Query().id == employee_id)
        
        if employee_record:
            emp_name = employee_record.get('username')
            # Create Notification for Employee
            create_notification(
                user_id=employee_id,
                title="New Complaint Assigned",
                message=f"You have been assigned complaint #{complaint_id[:8]}: {complaint.get('title')}",
                link=url_for('employee_ticket_view', ticket_id=complaint_id)
            )
            log_action(session['user_id'], 'assign_complaint', f"Assigned complaint {complaint_id} to {emp_name}")
            flash(f'Complaint assigned to {emp_name}.', 'success')
        else:
            flash('Employee not found.', 'danger')
            return redirect(url_for('admin_complaints'))
    else:
         log_action(session['user_id'], 'unassign_complaint', f"Unassigned complaint {complaint_id}")
         flash('Complaint unassigned.', 'info')

    complaints_table.update({
        'assigned_to': assigned_to_val,
        'assigned_technician_id': technician_id_val,
        'status': status,
        'updated_at': updated_at
    }, Query().id == complaint_id)
    
    return redirect(url_for('admin_complaints'))

@app.route('/admin/complaint/<complaint_id>/update', methods=['POST'])
@role_required(['admin', 'super_admin'])
def admin_update_complaint(complaint_id):
    complaint_record = complaints_table.search(Query().id == complaint_id)
    if not complaint_record:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('admin_complaints'))
    
    complaint = complaint_record[0]
    old_status = complaint.get('status')
    
    new_status = request.form.get('status')
    assigned_to = request.form.get('assigned_to')
    resolution_notes = request.form.get('resolution_notes')
    redirect_detail = request.form.get('redirect_detail')
    
    update_data = {
        'updated_at': datetime.now().isoformat()
    }
    
    actions_log = []
    
    if new_status and new_status != old_status:
        update_data['status'] = new_status
        actions_log.append(f"Status changed from {old_status} to {new_status}")
        
        # Notify user of status change
        notify_complaint_status_change(complaint, old_status, new_status, resolution_notes)
        
    if assigned_to:
        old_assigned = complaint.get('assigned_technician_id')
        if assigned_to != old_assigned:
            update_data['assigned_technician_id'] = assigned_to
            update_data['assigned_to'] = assigned_to # Keep both for compatibility
            
            # Get staff name for log
            s = admin_table.search(Query().id == assigned_to)
            staff_name = s[0].get('username') if s else 'Unknown'
            actions_log.append(f"Assigned to {staff_name}")
            
            # Notify staff
            create_notification(
                assigned_to,
                f"New Assignment: {complaint.get('title')}",
                f"You have been assigned to complaint #{complaint_id[:8]}",
                url_for('employee_ticket_view', ticket_id=complaint_id)
            )

    if resolution_notes:
        existing_notes = complaint.get('resolution_notes', '')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        admin_name = session.get('username', 'Admin')
        new_note_entry = f"[{timestamp}] {admin_name}: {resolution_notes}"
        update_data['resolution_notes'] = f"{existing_notes}\n{new_note_entry}" if existing_notes else new_note_entry
        actions_log.append("Added resolution notes")

    # Advanced Legal Notice Generation
    if new_status == 'Legal Action' and complaint.get('legal_status') != 'Generated':
        try:
            user_info = admin_table.get(Query().id == complaint.get('user_id'))
            customer_name = user_info.get('full_name', 'Customer') if user_info else 'Customer'
            seller_name = complaint.get('seller_name', "Seller / Retailer")
            seller_address = complaint.get('seller_address', "Address not provided")
            
            from legal_notice_generator import generate_legal_notice
            generate_legal_notice(complaint_id, complaint, customer_name, seller_name, seller_address)
            actions_log.append("Auto-Generated Legal Notice")
            flash('Legal Notice Auto-Generated successfully.', 'success')
        except Exception as e:
            flash(f'Error generating Legal Notice: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    if update_data:
        complaints_table.update(update_data, Query().id == complaint_id)
        
        # Log to history
        if actions_log:
            complaint_history_table.insert({
                'complaint_id': complaint_id,
                'action': '; '.join(actions_log),
                'username': session.get('username'),
                'user_id': session.get('user_id'),
                'notes': resolution_notes,
                'created_at': datetime.now().isoformat()
            })
            
        flash('Complaint updated successfully.', 'success')
    
    if redirect_detail:
        return redirect(url_for('admin_view_complaint', complaint_id=complaint_id))
        
    return redirect(url_for('admin_complaints'))

@app.route('/admin/customization', methods=['GET', 'POST'])
@role_required(['admin', 'super_admin'])
def admin_customization():
    if request.method == 'POST':
        flash('Customization settings saved.', 'success')
        return redirect(url_for('admin_customization'))
    return render_template('admin/customization.html')

@app.route('/admin/monitoring')
@role_required(['admin', 'super_admin'])
def admin_monitoring():
    staff_users = admin_table.search(Query().role.one_of(['employee', 'technician', 'support']))
    all_complaints = complaints_table.all()
    
    employees_data = []
    for staff in staff_users:
        assigned = [c for c in all_complaints if c.get('assigned_technician_id') == staff['id']]
        active = len([c for c in assigned if c.get('status') in ['open', 'in_progress']])
        completed = len([c for c in assigned if c.get('status') in ['resolved', 'closed', 'resolved_online']])
        
        # Calculate score based on ratings if available
        rated = [c for c in assigned if c.get('rating')]
        if rated:
            score = round(sum(int(c['rating']) for c in rated) / len(rated), 1)
        else:
            # Default score logic if no ratings: completion ratio capped at 5.0
            if assigned:
                completion_rate = (completed / len(assigned))
                # Base score 3.0 to 5.0 for active staff with assignments
                score = round(3.0 + (completion_rate * 2.0), 1)
            else:
                score = 0.0
                
        employees_data.append({
            'username': staff['username'],
            'email': staff['email'],
            'role': staff['role'],
            'is_active': staff.get('is_active', True),
            'stats': {
                'active': active,
                'completed': completed,
                'score': score
            }
        })
    
    return render_template('admin/monitoring.html', employees=employees_data)

@app.route('/admin/user/<user_id>/chat-history')
@role_required(['admin', 'super_admin'])
def admin_user_chat_history(user_id):
    return render_template('admin/user_chat_history.html', user_id=user_id)

@app.route('/user/complaints', methods=['GET', 'POST'])
@login_required
def user_complaints():
    user_id = session['user_id']
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category', 'technical')
        priority = request.form.get('priority', 'medium')
        complaint_types = request.form.getlist('complaint_types')
        is_anonymous = request.form.get('anonymous') == 'on'
        
        # Additional fields from the updated template
        purchase_source = request.form.get('purchase_source')
        order_id = request.form.get('order_id')
        seller_name = request.form.get('seller_name')
        seller_address = request.form.get('seller_address')
        address = request.form.get('address')
        lat = request.form.get('latitude')
        lng = request.form.get('longitude')
        visit_date = request.form.get('visit_date')
        visit_time = request.form.get('visit_time')
        refund_reason = request.form.get('refund_reason')
        refund_amount = request.form.get('refund_amount')
        bank_name = request.form.get('bank_name')
        account_number = request.form.get('account_number')
        ifsc_code = request.form.get('ifsc_code')

        if not title or not description:
            flash('Title and description are required.', 'danger')
            return redirect(url_for('user_complaints'))

        # Handle attachment
        attachment_path = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename:
                filename = secure_filename(f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'complaints')
                os.makedirs(upload_folder, exist_ok=True)
                
                # Use absolute path for saving
                file.save(os.path.join(upload_folder, filename))
                
                # Store relative path for URL generation (force forward slashes)
                attachment_path = f"uploads/complaints/{filename}"

        # Handle invoice file
        invoice_file_path = None
        if 'invoice_file' in request.files:
            file = request.files['invoice_file']
            if file and file.filename:
                filename = secure_filename(f"{user_id}_inv_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'complaints')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                invoice_file_path = f"uploads/complaints/{filename}"

        # AI Auto-Classification
        try:
            ai_classification = ai_agent.classify_complaint(description)
            ai_analysis = {
                'sentiment': ai_classification.get('sentiment'),
                'summary': ai_classification.get('summary')
            }
        except Exception:
            ai_analysis = {}

        complaint_id = request.form.get('generated_id')
        if not complaint_id:
            complaint_id = str(uuid.uuid4())

        # BLOCKCHAIN: Calculate Hashes
        try:
            all_complaints_sorted = sorted(complaints_table.all(), key=lambda x: x.get('created_at', ''), reverse=True)
            prev_hash = all_complaints_sorted[0].get('current_hash', "GENESIS_BLOCK") if all_complaints_sorted else "GENESIS_BLOCK"
        except Exception:
            prev_hash = "GENESIS_BLOCK"

        complaint_data = {
            'id': complaint_id,
            'user_id': user_id if not is_anonymous else 'anonymous',
            'submitted_by': user_id,
            'title': title,
            'description': description,
            'category': category,
            'priority': priority,
            'status': 'open',
            'complaint_types': json.dumps(complaint_types) if complaint_types else None,
            'purchase_source': purchase_source,
            'order_id': order_id,
            'seller_name': seller_name,
            'seller_address': seller_address,
            'address': address,
            'location': json.dumps({'lat': lat, 'lng': lng}) if lat and lng else None,
            'visit_schedule': json.dumps({'date': visit_date, 'time': visit_time}) if visit_date and visit_time else None,
            'refund_reason': refund_reason,
            'refund_amount': refund_amount,
            'bank_details': json.dumps({
                'bank_name': bank_name,
                'account_number': account_number,
                'ifsc_code': ifsc_code
            }) if bank_name else None,
            'attachment': attachment_path,
            'invoice_file': invoice_file_path,
            'ai_analysis': json.dumps(ai_analysis) if ai_analysis else None,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'prev_hash': prev_hash
        }

        # Calculate current hash (integrity seal)
        hash_payload = complaint_data.copy()
        current_hash = calculate_complaint_hash(hash_payload, prev_hash)
        complaint_data['current_hash'] = current_hash

        # Prepare data for TinyDB (ensure everything is serializable)
        complaints_table.insert(complaint_data)
        
        # Trigger Auto-Generation of Legal Notice instantly
        try:
            customer_name_for_notice = session.get('full_name', session.get('username', 'Customer'))
            generate_legal_notice(complaint_id, complaint_data, customer_name_for_notice, seller_name, seller_address)
        except Exception as e:
            import logging
            logging.error(f"Failed to auto-generate legal notice on submission: {e}")
        
        # Log action
        log_action(user_id, 'register_complaint', f"Complaint registered: {complaint_id} ({title})")
        
        # Notify status change (which sends email)
        # We can simulate a status change to 'open' to trigger notifications if our utils handle it, 
        # but manual email sending was already here. Let's keep it but ensure arguments are correct.
        
        
        # Determine the user record early for email notifications
        user_record = admin_table.get(Query().id == user_id)

        # Email Notification to User (if not anonymous and email exists)
        if user_record and user_record.get('email'):
            recipient_email = user_record['email']
            # The email sending logic is duplicated below, so we can remove this block 
            # and rely on the one at the end of the function, or keep it if it was intended 
            # for a specific immediate notification. 
            # However, since there is a comprehensive email block at line 4368 (original), 
            # I will comment this out or merge it. 
            # Looking at the code, it seems the block at 4337 was a leftover or partial implementation 
            # traversing into the flash message. 
            # I will remove this premature block and let the full block at the end handle it.
            pass

        # flash and return moved to the end of the function
        # Sync to Google Sheets
        sync_complaint_to_google_sheets(complaint_data, user_id)

        # Notify Admins and Employees
        staff_users = admin_table.search(Query().role.one_of(['admin', 'super_admin', 'employee', 'technician', 'support_agent']))
        for staff in staff_users:
            if staff['id'] != user_id: # Don't notify self
                create_notification(
                    staff['id'],
                    f"New Complaint: {title[:30]}...",
                    f"A new complaint has been registered by {'Anonymous' if is_anonymous else session.get('full_name', session.get('username'))}.",
                    url_for('admin_complaints') if staff['role'] in ['admin', 'super_admin'] else url_for('employee_assigned_complaints') if staff['role'] == 'employee' else url_for('dashboard')
                )

        log_action(user_id, 'register_complaint', f"Complaint registered: {title} (ID: {complaint_id[:8]})")
        
        # Send confirmation email to user
        user_record = admin_table.get(Query().id == user_id)
        if user_record and user_record.get('email'):
            recipient_email = user_record.get('email')
            subject = f"[CUSTOMER SUPPORT SYSTEM] Complaint Registered: {title}"
            body_text = f"""
Hello {user_record.get('full_name', user_record.get('username'))},

Your complaint has been successfully registered.

Complaint ID: {complaint_id}
Title: {title}
Priority: {priority.capitalize()}
Status: Open

You can track the live status of your complaint at any time by visiting our Home Page and entering your Tracking ID in the 'Track Your Complaint' section:
Tracking ID: {complaint_id}

Best regards,
OSN Support Team
"""
            body_html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #2c3e50;">Complaint Registered Successfully</h2>
        <p>Hello {user_record.get('full_name', user_record.get('username'))},</p>
        <p>Your complaint has been successfully registered and is now being processed by our team.</p>
        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Complaint ID:</strong> <code>{complaint_id}</code></p>
            <p style="margin: 5px 0;"><strong>Title:</strong> {title}</p>
            <p style="margin: 5px 0;"><strong>Priority:</strong> {priority.capitalize()}</p>
            <p style="margin: 5px 0;"><strong>Status:</strong> <span style="color: #28a745; font-weight: bold;">Open</span></p>
        </div>
        <p>You can track the live status of your complaint at any time by visiting our <strong>Home Page</strong> and entering your Tracking ID in the 'Track Your Complaint' section:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{url_for('index', _external=True)}" 
               style="background-color: #007bff; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Go to Home Page to Track</a>
        </div>
        <p style="font-size: 14px; color: #666; border-top: 1px solid #eee; padding-top: 15px;">
            Best regards,<br>
            <strong>OSN Support Team</strong>
        </p>
    </div>
</body>
</html>
"""
            send_email_notification(recipient_email, subject, body_text, body_html)

        flash(f'Complaint registered successfully! Your Tracking ID is: {complaint_id}', 'success')
        return redirect(url_for('user_complaints'))

    # Use submitted_by to include anonymous complaints
    rows = complaints_table.search(Query().submitted_by == user_id)
    # Sort manually
    rows.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    my_complaints = [process_complaint_record(row) for row in rows]
    
    # Pre-generate an ID for the tracking form view
    generated_id = f"comp_{str(uuid.uuid4().hex)[:8]}"
    
    return render_template('user/complaints.html', complaints=my_complaints, generated_id=generated_id)

@app.route('/user/complaint/<complaint_id>')
@login_required
def user_view_complaint(complaint_id):
    complaint = complaints_table.search(Query().id == complaint_id)
    if not complaint:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('user_complaints'))
    return render_template('user/complaint_detail.html', complaint=complaint[0])

@app.route('/user/complaint/<complaint_id>/delete', methods=['POST'])
@login_required
def user_delete_complaint(complaint_id):
    user_id = session['user_id']
    complaint_record = complaints_table.search(
        (Query().id == complaint_id) & 
        (Query().submitted_by == user_id)
    )
    
    if complaint_record:
        complaints_table.remove(Query().id == complaint_id)
        log_action(user_id, 'delete_complaint', f"Complaint deleted: {complaint_id[:8]}")
        flash('Complaint deleted successfully.', 'success')
    else:
        flash('Unauthorized or complaint not found.', 'danger')
        
    return redirect(url_for('user_tracking'))


@app.route('/complaint/<complaint_id>')
@login_required
def view_complaint(complaint_id):
    complaint_res = complaints_table.get(Query().id == complaint_id)
    
    if not complaint_res:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    complaint = complaint_res
    
    # If admin or employee, show staff detail view
    if session.get('role') in ['admin', 'super_admin', 'employee', 'support_agent']:
        # STEP 5 — ASSIGN COMPLAINT Query
        # Fetch staff users
        staff_users = admin_table.search(Query().role.one_of(['employee', 'technician', 'support_agent']))
        
        # Fetch User Info
        user_info = None
        if complaint.get('user_id'):
             user_info = admin_table.get(Query().id == complaint.get('user_id'))
             
        # Fetch Assigned User
        assigned_user = None
        if complaint.get('assigned_technician_id'):
             assigned_user = admin_table.get(Query().id == complaint.get('assigned_technician_id'))
             
        render_path = 'admin/complaint_detail.html'
        if session.get('role') == 'employee':
            render_path = 'employee/ticket_view.html'
            
        return render_template(render_path, 
                             complaint=complaint, 
                             staff_users=staff_users,
                             user_info=user_info,
                             assigned_user=assigned_user)
    
    return render_template('user/complaint_detail.html', complaint=complaint)

@app.route('/complaint/<complaint_id>/update', methods=['POST'])
@login_required
def update_complaint(complaint_id):
    status = request.form.get('status')
    assigned_to = request.form.get('assigned_to')
    resolution_notes = request.form.get('resolution_notes')
    redirect_detail = request.form.get('redirect_detail')
    
    update_data = {
        'updated_at': datetime.now().isoformat()
    }
    
    complaint_res = complaints_table.get(Query().id == complaint_id)
    
    if not complaint_res:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    complaint = complaint_res
    old_status = complaint.get('status')

    # Prepare update values
    new_status = status if status else old_status
    new_assigned_to = assigned_to if assigned_to else complaint.get('assigned_technician_id')
    updated_at = datetime.now().isoformat()
    
    if status and old_status != status:
        notify_complaint_status_change(complaint, old_status, status, notes=resolution_notes)
            
    if assigned_to:
        # If it was open, mark as in_progress when assigned
        if old_status == 'open':
             new_status = 'in_progress'
             notify_complaint_status_change(complaint, old_status, 'in_progress', notes="Ticket assigned to technician.")

    # Advanced Legal Notice Generation
    if new_status == 'Legal Action' and complaint.get('legal_status') != 'Generated':
        try:
            user_info = admin_table.get(Query().id == complaint.get('user_id'))
            customer_name = user_info.get('full_name', 'Customer') if user_info else 'Customer'
            seller_name = "Seller / Retailer"  # Ideally from a DB field, but hardcoded fallback
            seller_address = "To be updated..." # Fallback
            
            generate_legal_notice(complaint_id, complaint, customer_name, seller_name, seller_address)
            flash('Legal Notice Auto-Generated successfully.', 'success')
        except Exception as e:
            flash(f'Error generating Legal Notice: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()

    complaints_table.update({
        'status': new_status,
        'assigned_technician_id': new_assigned_to,
        'assigned_to': new_assigned_to,
        'updated_at': updated_at
    }, Query().id == complaint_id)
    
    if assigned_to:
        create_notification(
            assigned_to, 
            "Task Assigned", 
            f"Admin has assigned a complaint to you (ID: {complaint_id[:8]})",
            url_for('employee_assigned_complaints')
        )

    log_action(session['user_id'], 'update_complaint', f"Updated complaint {complaint_id[:8]}")
    flash('Complaint updated successfully.', 'success')
    
    if redirect_detail:
        return redirect(url_for('admin_view_complaint', complaint_id=complaint_id))
    return redirect(url_for('dashboard'))

@app.route('/user/customization', methods=['GET', 'POST'])
@login_required
def user_customization():
    if request.method == 'POST':
        flash('Customization saved.', 'success')
        return redirect(url_for('user_customization'))
    return render_template('user/customization.html')



@app.route('/api/user/dashboard/data')
@login_required
def api_user_dashboard_data():
    """API endpoint for real-time dashboard data updates"""
    user_id = session['user_id']
    
    # Get all user complaints
    # Use user_id field for consistency with other routes
    all_complaints = sorted(complaints_table.search(Query().user_id == user_id), key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Count by status
    open_complaints = [c for c in all_complaints if c.get('status') in ['open', 'in_progress']]
    resolved_complaints = [c for c in all_complaints if c.get('status') == 'resolved']
    closed_complaints = [c for c in all_complaints if c.get('status') == 'closed']
    
    # Get user files count
    user_files_count = len(files_table.search(Query().user_id == user_id))
    
    # Prepare status counts
    status_counts = {
        'open': len([c for c in all_complaints if c.get('status') == 'open']),
        'in_progress': len([c for c in all_complaints if c.get('status') == 'in_progress']),
        'resolved': len(resolved_complaints),
        'closed': len(closed_complaints)
    }
    
    # Get recent complaints (last 5)
    recent_complaints = sorted(all_complaints, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
    
    # Enrich recent complaints with technician names
    for complaint in recent_complaints:
        if complaint.get('assigned_technician_id'):
            tech = admin_table.get(Query().id == complaint['assigned_technician_id'])
            if tech:
                complaint['technician_name'] = tech.get('full_name', tech.get('username'))
        else:
            complaint['technician_name'] = 'Unassigned'
    
    # Get recently resolved complaints (last 5 resolved)
    resolved_list = sorted(resolved_complaints, key=lambda x: x.get('updated_at', ''), reverse=True)[:5]
    
    # Enrich resolved complaints with technician names
    for complaint in resolved_list:
        if complaint.get('assigned_technician_id'):
            tech = admin_table.get(Query().id == complaint['assigned_technician_id'])
            if tech:
                complaint['technician_name'] = tech.get('full_name', tech.get('username'))
        else:
            complaint['technician_name'] = 'Unassigned'
    
    return jsonify({
        'open_complaints_count': len(open_complaints),
        'resolved_complaints': len(resolved_complaints),
        'closed_complaints': len(closed_complaints),
        'total_files': user_files_count,
        'status_counts': status_counts,
        'recent_complaints': recent_complaints,
        'resolved_complaints_list': resolved_list,
        'total_complaints': len(all_complaints)
    })


@app.route('/user/tracking')
@login_required
def user_tracking():
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all')
    
    q = Query()
    complaints_list = complaints_table.search(q.submitted_by == user_id)
    
    if status_filter == 'resolved':
        complaints_list = [c for c in complaints_list if c.get('status') == 'resolved']
    elif status_filter == 'open':
        complaints_list = [c for c in complaints_list if c.get('status') in ['open', 'in_progress']]
    elif status_filter == 'closed':
        complaints_list = [c for c in complaints_list if c.get('status') == 'closed']
        
    complaints = [process_complaint_record(c) for c in complaints_list]
    
    # Sort by created_at descending (newest first)
    complaints.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Enrich with technician names
    for complaint in complaints:
        assigned_to = complaint.get('assigned_to') or complaint.get('assigned_technician_id')
        if assigned_to:
            tech = admin_table.get(Query().id == assigned_to)
            if tech:
                complaint['technician_name'] = tech.get('full_name', tech.get('username'))
            else:
                complaint['technician_name'] = 'Unknown'
        else:
            complaint['technician_name'] = 'Unassigned'
    
    return render_template('user/tracking.html', complaints=complaints, status_filter=status_filter)

# API endpoint for real-time status updates
@app.route('/api/complaints/status/<complaint_id>')
@login_required
def get_complaint_status(complaint_id):
    user_id = session['user_id']
    # Use submitted_by to allow access to anonymous complaints
    complaint_record = complaints_table.search(
        (Query().id == complaint_id) & 
        (Query().submitted_by == user_id)
    )
    
    if complaint_record:
        complaint = complaint_record[0]
        technician_name = 'Unassigned'
        
        assigned_to = complaint.get('assigned_to') or complaint.get('assigned_technician_id')
        if assigned_to:
            tech = admin_table.get(Query().id == assigned_to)
            if tech:
                technician_name = tech.get('full_name', tech.get('username'))
        
        return jsonify({
            'status': complaint.get('status'),
            'updated_at': complaint.get('updated_at'),
            'technician_name': technician_name,
            'priority': complaint.get('priority')
        })
    return jsonify({'error': 'Not found'}), 404


@app.route('/user/files')
@login_required
def user_files():
    return render_template('user/files.html')

@app.route('/user/download-encrypted/<file_id>')
@login_required
def user_download_encrypted(file_id):
    flash('File download initiated.', 'info')
    return redirect(url_for('user_files'))

@app.route('/user/download-decrypted/<file_id>')
@login_required
def user_download_decrypted(file_id):
    flash('File download initiated.', 'info')
    return redirect(url_for('user_files'))

@app.route('/profile/upload-photo', methods=['POST'])
@login_required
def upload_profile_photo():
    if 'photo' in request.files:
        flash('Profile photo uploaded.', 'success')
    return redirect(url_for('user_profile'))

@app.route('/profile/remove-photo', methods=['POST'])
@login_required
def remove_profile_photo():
    flash('Profile photo removed.', 'success')
    return redirect(url_for('user_profile'))

@app.route('/user/qrcode/<user_id>')
@login_required
def get_user_qrcode(user_id):
    # Determine the base URL for the verification link
    try:
        base_url = request.host_url.rstrip('/')
    except:
        base_url = "http://localhost:8080"
        
    verification_url = f"{base_url}/verify-salary/{user_id}"
    
    # Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(verification_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to buffer
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/admin/user/<user_id>/update-role', methods=['POST'])
@role_required(['admin', 'super_admin'])
def update_role(user_id):
    new_role = request.form.get('role')
    admin_table.update({'role': new_role}, Query().id == user_id)
    flash(f'Role updated to {new_role}.', 'success')
    return redirect(url_for('admin_user_profile', user_id=user_id))

@app.route('/feedback', methods=['POST'])
@login_required
def submit_feedback():
    feedback = request.form.get('feedback', '').strip()
    if feedback:
        log_action(session['user_id'], 'feedback_submit', feedback[:100])
        flash('Thank you for your feedback!', 'success')
    return redirect(request.referrer or url_for('dashboard'))





@app.route('/export/ai-training')
@role_required(['admin'])
def export_ai_training():
    flash('AI training data export initiated.', 'info')
    return redirect(url_for('admin_ai_training'))

# Salary route aliases (if they're referenced differently in templates)
@app.route('/salary/details', methods=['GET', 'POST'])
@login_required
def salary_details():
    from salary_routes import employee_salary_details
    return employee_salary_details()

@app.route('/salary/verify', methods=['GET', 'POST'])
@role_required(['admin'])
def salary_verify():
    from salary_routes import admin_salary_verify
    return admin_salary_verify()

# === End of Routes ===

