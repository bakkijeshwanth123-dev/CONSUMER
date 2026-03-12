
from flask import session, request, render_template as flask_render_template, redirect, url_for, jsonify
from app import app
import functools
import os

# Monkeypatch render_template to support mobile overrides
import flask
original_render_template = flask.render_template

def get_mobile_template(template_name):
    if session.get('is_mobile'):
        # Map specific templates to mobile versions
        mobile_map = {
            'home.html': 'mobile/home.html',
            'index.html': 'mobile/home.html',
            'login.html': 'mobile/login.html',
            'signup.html': 'mobile/signup.html',
            'user_dashboard.html': 'mobile/user_dashboard.html',
            'dashboard.html': 'mobile/user_dashboard.html', # fallback/alias
            'user/complaints.html': 'mobile/user_complaints.html',
            'user/tracking.html': 'mobile/user_tracking.html',
            'user/files.html': 'mobile/user_files.html',
            'admin/dashboard.html': 'mobile/admin_dashboard.html',
            'dashboard/super_admin.html': 'mobile/admin_dashboard.html',
            'employee/dashboard.html': 'mobile/employee_dashboard.html',
            'dashboard/technician.html': 'mobile/employee_dashboard.html',
            'dashboard/support.html': 'mobile/employee_dashboard.html',
        }
        
        if template_name in mobile_map:
            return mobile_map[template_name]
            
        # Generic check for mobile/ subfolder
        mobile_path = f"mobile/{template_name}"
        if os.path.exists(os.path.join(app.template_folder, mobile_path)):
            return mobile_path
            
    return template_name

def patched_render_template(template_name_or_list, **context):
    if isinstance(template_name_or_list, str):
        template_name_or_list = get_mobile_template(template_name_or_list)
    return original_render_template(template_name_or_list, **context)

flask.render_template = patched_render_template

# ... monkeypatching logic above ...

# Add a route to serve the PWA manifest
@app.route('/manifest.json')
def serve_manifest():
    from flask import send_from_directory
    import os
    return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.json')

# Inject 'is_mobile' into templates
@app.context_processor
def inject_mobile():
    return dict(is_mobile=session.get('is_mobile', False))

@app.route('/mobile/toggle')
def toggle_mobile():
    session['is_mobile'] = not session.get('is_mobile', False)
    # If enabling mobile, redirect to dashboard or login
    if session['is_mobile']:
        return redirect(url_for('dashboard', mobile=1))
    return redirect(request.referrer or url_for('dashboard'))
