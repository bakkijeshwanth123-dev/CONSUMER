import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, session
from flask_mail import Message
from app import app, mail
from database import *
from app_utils import log_action, create_notification, send_email_notification
from auth_utils import login_required, role_required

@app.route('/admin/register-complaint', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'super_admin', 'hr_manager', 'supervisor'])
def admin_register_complaint():
    try:
        if request.method == 'GET':
            users = admin_table.all()
            users.sort(key=lambda x: x.get('full_name', x.get('username', '')).lower())
            return render_template('admin/register_complaint.html', users=users)

        # POST Logic
        user_id = request.form.get('user_id')
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category', 'technical')
        priority = request.form.get('priority', 'medium')
        complaint_types = request.form.getlist('complaint_types')
        
        # Refund/Bank Details
        purchase_source = request.form.get('purchase_source')
        order_id = request.form.get('order_id')
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

        if not user_id or not title or not description:
            flash('User, Title and Description are required.', 'danger')
            return redirect(url_for('admin_register_complaint'))

        # Handle attachment
        attachment_path = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename:
                filename = secure_filename(f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'complaints')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                attachment_path = f"uploads/complaints/{filename}"

        complaint_id = str(uuid.uuid4())
        
        # Blockchain Hash
        try:
            all_complaints = complaints_table.all()
            last_complaint = sorted(all_complaints, key=lambda x: x.get('created_at', ''))[-1] if all_complaints else None
            prev_hash = last_complaint.get('current_hash', 'GENESIS_BLOCK') if last_complaint else "GENESIS_BLOCK"
        except Exception:
            prev_hash = "GENESIS_BLOCK"

        complaint_data = {
            'id': complaint_id,
            'user_id': user_id,
            'submitted_by': session['user_id'], # Admin who submitted it
            'on_behalf_of': True,
            'title': title,
            'description': description,
            'category': category,
            'priority': priority,
            'status': 'open',
            'complaint_types': complaint_types,
            'purchase_source': purchase_source,
            'order_id': order_id,
            'address': address,
            'location': {'lat': lat, 'lng': lng} if lat and lng else None,
            'visit_schedule': {'date': visit_date, 'time': visit_time} if visit_date and visit_time else None,
            'refund_reason': refund_reason,
            'refund_amount': refund_amount,
            'bank_details': {
                'bank_name': bank_name,
                'account_number': account_number,
                'ifsc_code': ifsc_code
            } if bank_name else None,
            'attachment': attachment_path,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'prev_hash': prev_hash
        }

        # Helper to calculate hash (simplified import/usage)
        import hashlib, json
        def calculate_hash(data, prev):
            block_string = json.dumps(data, sort_keys=True) + prev
            return hashlib.sha256(block_string.encode()).hexdigest()
            
        complaint_data['current_hash'] = calculate_hash(complaint_data, prev_hash)

        complaints_table.insert(complaint_data)
        
        # Notifications
        log_action(session['user_id'], 'admin_register_complaint', f"Complaint registered for User {user_id}: {title}")
        
        # Notify User
        create_notification(
            user_id,
            f"New Complaint Registered",
            f"An admin has registered a complaint on your behalf: {title}",
            url_for('user_view_complaint', complaint_id=complaint_id)
        )

        # Notify Employees
        staff_users = admin_table.search(Query().role.one_of(['employee', 'technician']))
        for staff in staff_users:
            create_notification(
                staff['id'],
                f"New Complaint (Admin): {title[:30]}",
                f"Admin registered a complaint.",
                url_for('employee_assigned_complaints')
            )

        flash('Complaint registered successfully on behalf of user.', 'success')
        return redirect(url_for('admin_complaints'))
    except Exception as e:
        import traceback
        logging.error(f"Error in admin_register_complaint: {e}\n{traceback.format_exc()}")
        flash("An unexpected error occurred while registering the complaint.", "danger")
        return redirect(url_for('admin_dashboard_route'))

@app.route('/admin/users')
@login_required
@role_required(['admin', 'super_admin', 'hr_manager', 'supervisor'])
def admin_users():
    try:
        search = request.args.get('search', '').strip().lower()
        role_filter = request.args.get('role', '')
        status_filter = request.args.get('status', '')
        
        all_users = admin_table.all()
        
        if search:
            all_users = [u for u in all_users if 
                         search in u.get('username', '').lower() or
                         search in u.get('email', '').lower() or
                         search in u.get('full_name', '').lower()]
        
        if role_filter:
            all_users = [u for u in all_users if u.get('role') == role_filter]
        
        if status_filter:
            if status_filter == 'active':
                all_users = [u for u in all_users if u.get('is_active', True)]
            elif status_filter == 'inactive':
                all_users = [u for u in all_users if not u.get('is_active', True)]
        
        all_users = sorted(all_users, key=lambda x: x.get('created_at', ''), reverse=True)
        whatsapp_contacts = whatsapp_contacts_table.all()
        
        return render_template('admin/manage_users.html', users=all_users, 
                              search=search, role_filter=role_filter, status_filter=status_filter,
                              whatsapp_contacts=whatsapp_contacts)
    except Exception as e:
        import traceback
        logging.error(f"Error in admin_users: {e}\n{traceback.format_exc()}")
        flash("An unexpected error occurred while loading users.", "danger")
        return redirect(url_for('admin_dashboard_route'))

@app.route('/admin/update_role', methods=['POST'])
@login_required
@role_required(['admin', 'super_admin'])
def admin_update_role():
    user_id = request.form.get('user_id')
    new_role = request.form.get('new_role')
    
    valid_roles = ['user', 'technician', 'support_agent', 'manager', 'admin', 'super_admin', 'database_server', 'hr_manager', 'employee', 'support']
    if new_role not in valid_roles:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('admin_users'))
        
    admin_table.update({'role': new_role}, Query().id == user_id)
    log_action(session['user_id'], 'role_change', f'Changed role of user {user_id} to {new_role}')
    flash('User role updated successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/generate')
@login_required
@role_required(['admin', 'super_admin'])
def admin_generate_user():
    return render_template('admin/generate_user.html')

@app.route('/admin/users/create', methods=['POST'])
@login_required
@role_required(['admin', 'super_admin'])
def admin_create_user():
    try:
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        salary = request.form.get('salary', '0')
        
        # Basic validation
        if not username or not email or not password or not role:
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin_users'))
            
        # Check if user exists
        if admin_table.search(Query().username == username) or admin_table.search(Query().email == email):
            flash('Username or Email already exists.', 'danger')
            return redirect(url_for('admin_users'))
            
        # Create User
        from werkzeug.security import generate_password_hash
        user_id = str(uuid.uuid4())
        hashed_password = generate_password_hash(password)
        
        user_data = {
            'id': user_id,
            'username': username,
            'full_name': full_name,
            'email': email,
            'password_hash': hashed_password,
            'role': role,
            'salary': salary if role in ['employee', 'manager', 'technician', 'support', 'admin'] else None,
            'created_at': datetime.now().isoformat(),
            'is_active': True,
            'profile_photo': None
        }
        
        admin_table.insert(user_data)
        log_action(session['user_id'], 'create_user', f'Created internal user {username} ({role})')
        
        flash(f'User {username} created successfully with role {role}.', 'success')
        return redirect(url_for('admin_users'))
        
    except Exception as e:
        import traceback
        logging.error(f"Error in admin_create_user: {e}\n{traceback.format_exc()}")
        flash("An unexpected error occurred while creating user.", "danger")
        return redirect(url_for('admin_users'))

@app.route('/admin/customer_notices')
@login_required
@role_required(['admin', 'super_admin'])
def customer_notices():
    # Fetch all complaints that have generated a legal notice
    notices = complaints_table.search(Query().legal_status == 'Generated')
    # Sort by date descending
    notices.sort(key=lambda x: x.get('legal_notice_date', ''), reverse=True)
    return render_template('admin/customer_notices.html', notices=notices)

@app.route('/admin/download_notice/<tracking_id>')
@login_required
@role_required(['admin', 'super_admin'])
def download_notice(tracking_id):
    from flask import send_file
    import os
    
    # Secure the filename
    safe_tracking_id = os.path.basename(tracking_id)
    if not safe_tracking_id.startswith('LEGAL-'):
        flash("Invalid tracking ID format.", "danger")
        return redirect(url_for('customer_notices'))
        
    notice = complaints_table.get(Query().legal_tracking_id == safe_tracking_id)
    if not notice or not notice.get('legal_pdf_path'):
        flash("Legal notice PDF not found in database.", "danger")
        return redirect(url_for('customer_notices'))
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # pdf path in DB is relative to static, e.g., 'legal_notices/LEGAL-2026-0001.pdf'
    pdf_path = os.path.join(base_dir, 'static', notice.get('legal_pdf_path'))
    
    if not os.path.exists(pdf_path):
        flash("Physical PDF file not found on server.", "danger")
        return redirect(url_for('customer_notices'))
        
    return send_file(pdf_path, as_attachment=True, download_name=f"{safe_tracking_id}.pdf")

@app.route('/admin/download_text_notice/<tracking_id>')
@login_required
@role_required(['admin', 'super_admin'])
def download_text_notice(tracking_id):
    from flask import send_file
    import os
    
    # Secure the filename
    safe_tracking_id = os.path.basename(tracking_id)
    if not safe_tracking_id.startswith('LEGAL-'):
        flash("Invalid tracking ID format.", "danger")
        return redirect(url_for('customer_notices'))
        
    notice = complaints_table.get(Query().legal_tracking_id == safe_tracking_id)
    if not notice or not notice.get('legal_txt_path'):
        flash("Legal notice TXT not found in database.", "danger")
        return redirect(url_for('customer_notices'))
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    txt_path = os.path.join(base_dir, 'static', notice.get('legal_txt_path'))
    
    if not os.path.exists(txt_path):
        flash("Physical TXT file not found on server.", "danger")
        return redirect(url_for('customer_notices'))
        
    return send_file(txt_path, as_attachment=True, download_name=f"{safe_tracking_id}.txt")

