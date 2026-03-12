# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  OSN Serpent-Secure System — PyInstaller Spec
#  Run: pyinstaller serpent_secure.spec
# =============================================================================

import os
import glob

PROJECT_DIR = os.path.dirname(os.path.abspath(SPEC))

# ─── Helper: collect a folder recursively ────────────────────────────────────
def collect_folder(folder, dest_prefix):
    """Returns a list of (src, dest) tuples for all files in folder."""
    result = []
    for root, dirs, files in os.walk(os.path.join(PROJECT_DIR, folder)):
        for fname in files:
            src  = os.path.join(root, fname)
            dest = os.path.relpath(root, PROJECT_DIR)
            result.append((src, dest))
    return result


# ─── Data files to bundle ────────────────────────────────────────────────────
datas = []

# Templates & static assets
datas += collect_folder('templates', 'templates')
datas += collect_folder('static',    'static')

# JSON databases
for db_file in glob.glob(os.path.join(PROJECT_DIR, '*.json')):
    datas.append((db_file, '.'))

# Key files & .env
for extra in ['salary_key.key', '.env', 'translations.json', 'ngrok_status.txt']:
    f = os.path.join(PROJECT_DIR, extra)
    if os.path.exists(f):
        datas.append((f, '.'))

# Uploads folder (empty placeholder ok)
uploads_dir = os.path.join(PROJECT_DIR, 'uploads')
if os.path.isdir(uploads_dir):
    datas += collect_folder('uploads', 'uploads')


# ─── Hidden imports (Flask extensions detected from app.py) ──────────────────
hidden_imports = [
    # Flask core
    'flask', 'flask_session', 'flask_mail', 'flask_socketio',
    'werkzeug', 'werkzeug.serving', 'werkzeug.exceptions',
    'jinja2', 'itsdangerous', 'click',
    # Auth
    'authlib', 'authlib.integrations.flask_client',
    # Data
    'tinydb', 'tinydb.storages', 'tinydb.middlewares',
    # PDF / QR
    'reportlab', 'reportlab.lib', 'reportlab.platypus',
    'reportlab.lib.styles', 'reportlab.lib.units',
    'qrcode', 'qrcode.image.pil',
    # Encryption
    'cryptography', 'cryptography.fernet',
    'werkzeug.security',
    # Email
    'email', 'email.mime', 'email.mime.text', 'email.mime.multipart',
    'email.mime.application',
    # Misc
    'PIL', 'PIL.Image',
    'io', 'json', 'csv', 'threading', 'socket',
    'datetime', 'uuid', 'hashlib', 'base64',
    'collections', 'functools', 'pathlib',
    'engineio', 'socketio',
    # App modules
    'routes', 'routes_admin', 'routes_backup', 'routes_database',
    'routes_secrets', 'routes_gmail', 'refund_routes', 'salary_routes',
    'mobile_bridge', 'database', 'auth_utils', 'app_utils',
    'legal_notice_generator', 'whatsapp_agent',
]


# ─── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ['launcher.py'],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy'],
    noarchive=False,
)

# ─── PYZ archive ──────────────────────────────────────────────────────────────
pyz = PYZ(a.pure)

# ─── EXE ──────────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OSN-Serpent-Secure',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Set True to show console window for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Replace with path to .ico file if you have one
    onefile=True,           # Single self-contained EXE
)
