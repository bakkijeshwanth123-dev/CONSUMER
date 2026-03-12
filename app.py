import os
import logging
import uuid
from flask import Flask, session, request, redirect, url_for
from flask_mail import Mail, Message
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth
from tinydb import TinyDB, Query
from datetime import datetime, timedelta

logging.basicConfig(level=logging.DEBUG)


# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = 'supersecretkey123'
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)






app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30) # 30-minute auto logout
app.config['BASE_URL'] = os.environ.get('BASE_URL', '').rstrip('/')

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'secureonlinesocialnetwork@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = (
    f'Secure Online Social Network <{app.config["MAIL_USERNAME"]}>'
)

if not app.config['MAIL_PASSWORD']:
    logging.warning("MAIL_PASSWORD is not set in environment variables. Email functionality will be disabled (suppressed).")
    app.config['MAIL_SUPPRESS_SEND'] = True

mail = Mail(app)

# Google OAuth Configuration (Optional)
google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

if google_client_id and google_client_secret:
    try:
        oauth = OAuth(app)
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
    except Exception as e:
        logging.error(f"Failed to register Google OAuth: {e}")
        oauth = OAuth(app) # Initialize empty OAuth to avoid NameError if needed
else:
    logging.warning("Google OAuth credentials missing. Feature disabled.")
    oauth = OAuth(app) # Initialize empty OAuth to avoid NameError if needed

from database import *
from app_utils import init_utils, create_notification, log_action, calculate_complaint_hash, sync_complaint_to_google_sheets, send_reset_email, send_email_notification, notify_complaint_status_change

# Initialize utils with mail instance
init_utils(mail)


import json

# Load translations (Safe absolute path)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
translations_path = os.path.join(BASE_DIR, 'translations.json')
try:
    if os.path.exists(translations_path):
        with open(translations_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)
    else:
        logging.warning("translations.json missing. Using fallback.")
        translations = {}
except Exception as e:
    logging.error(f"Failed to load translations: {e}")
    translations = {}

@app.template_global()
def t(key):
    lang = session.get('lang', 'en')
    return translations.get(lang, {}).get(key, translations.get('en', {}).get(key, key))

@app.route('/set-language/<lang_code>')
def set_language(lang_code):
    if lang_code in translations:
        session['lang'] = lang_code
    return redirect(request.referrer or url_for('dashboard'))

with app.app_context():
    import routes
    import salary_routes
    import refund_routes
    import routes_admin
    import routes_backup
    import routes_database
    import routes_secrets
    import routes_gmail
    import mobile_bridge
