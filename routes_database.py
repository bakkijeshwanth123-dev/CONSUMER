
import os
import json
import datetime
from flask import render_template, request, redirect, url_for, flash, session, current_app, send_file
from werkzeug.utils import secure_filename
from app import app
from database import * # Import all tables
from auth_utils import login_required, role_required
from app_utils import log_action

# Helper to get all TinyDB tables mapping
def get_tables_map():
    return {
        'Users (Admin)': admin_table,
        'Complaints': complaints_table,
        'Complaint History': complaint_history_table,
        'Files': files_table,
        'Chats': chat_messages_table,
        'WhatsApp Contacts': whatsapp_contacts_table,
        'Refunds': refunds_table,
        # Add access logs if stored in Tinydb, but it seems they might be in a file? 
        # Checking app_utils: log_action likely writes to a file or a table. 
        # If it writes to a table, we should include it. Assuming 'access_logs.json' -> table name?
        # Let's assume standard tables for now.
    }

@app.route('/database/dashboard')
@login_required
@role_required(['database_server', 'super_admin'])
def database_dashboard():
    # Gather Stats
    stats = {
        'users': len(admin_table.all()),
        'complaints': len(complaints_table.all()),
        'files': 0, # Calculated below
        'db_size': 0
    }
    
    # Calculate total DB size (approx sum of json files)
    total_size = 0
    for f in os.listdir('.'):
        if f.endswith('.json'):
            total_size += os.path.getsize(f)
    stats['db_size'] = round(total_size / 1024, 2) # KB
    
    # Recent Uploads & File Stats
    recent_uploads = []
    upload_root = os.path.join(app.root_path, 'static', 'uploads')
    file_count = 0
    
    if os.path.exists(upload_root):
        all_files = []
        for root, dirs, files in os.walk(upload_root):
            for name in files:
                file_count += 1
                filepath = os.path.join(root, name)
                stats['files'] = file_count
                
                # Collect file info for recent list
                try:
                    mtime = os.path.getmtime(filepath)
                    all_files.append({
                        'original_filename': name,
                        'file_size': os.path.getsize(filepath),
                        'uploaded_at': datetime.datetime.fromtimestamp(mtime).isoformat(),
                        'mtime': mtime
                    })
                except OSError:
                    pass
        
        # Sort by mtime desc and take top 5
        all_files.sort(key=lambda x: x['mtime'], reverse=True)
        recent_uploads = all_files[:5]
    
    # Pass both stats dict and individual variables for template compatibility
    return render_template('database_server/dashboard.html', 
                          stats=stats, 
                          total_files=stats['files'],
                          encrypted_files=len(files_table.search(Query().is_encrypted == True)),
                          total_backups=len(backups_table),
                          recent_uploads=recent_uploads)

@app.route('/database/data')
@login_required
@role_required(['database_server', 'super_admin'])
def database_data():
    tables = get_tables_map().keys()
    selected_table = request.args.get('table')
    data = []
    
    if selected_table and selected_table in get_tables_map():
        table = get_tables_map()[selected_table]
        data = table.all()
        
    return render_template('database_server/data.html', tables=tables, selected_table=selected_table, data=data)

@app.route('/database/logs')
@login_required
@role_required(['database_server', 'super_admin'])
def database_logs():
    search = request.args.get('search', '').lower()
    action_filter = request.args.get('action', '')
    
    # Fetch logs from logs_table
    logs = logs_table.all()
    
    if search:
        logs = [l for l in logs if search in l.get('action', '').lower() or search in l.get('details', '').lower() or search in l.get('user_id', '').lower()]
    
    if action_filter:
        logs = [l for l in logs if l.get('action') == action_filter]
    
    # Sort by timestamp desc
    logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Get unique action types for filter dropdown
    action_types = sorted(list(set([l.get('action') for l in logs_table.all() if l.get('action')])))
    
    return render_template('database_server/logs.html', 
                          logs=logs[:100], 
                          search=search, 
                          action_filter=action_filter,
                          action_types=action_types)

@app.route('/database/files', methods=['GET', 'POST'])
@login_required
@role_required(['database_server', 'super_admin'])
def database_files():
    search = request.args.get('search', '').lower()
    assigned_filter = request.args.get('assigned', '')
    
    # Fetch from TinyDB
    all_files = files_table.all()
    
    # Filter by filename
    if search:
        all_files = [f for f in all_files if search in f.get('original_filename', '').lower()]
    
    # Filter by assignment
    if assigned_filter == 'assigned':
        all_files = [f for f in all_files if f.get('user_id')]
    elif assigned_filter == 'unassigned':
        all_files = [f for f in all_files if not f.get('user_id')]
        
    return render_template('database_server/files.html', 
                          files=all_files, 
                          search=search, 
                          assigned_filter=assigned_filter)

@app.route('/database/download-encrypted/<file_id>')
@login_required
@role_required(['database_server', 'super_admin'])
def database_download_encrypted(file_id):
    file_record = files_table.get(Query().id == file_id)
    if not file_record:
        flash('File record not found in database.', 'danger')
        return redirect(url_for('database_files'))
    
    # Attempt to send file from static/uploads (relative path stored in record)
    filepath = file_record.get('filepath')
    if not filepath:
        flash('File path not recorded.', 'danger')
        return redirect(url_for('database_files'))
        
    absolute_path = os.path.join(app.root_path, 'static', filepath)
    if os.path.exists(absolute_path):
        return send_file(absolute_path, as_attachment=True, download_name=file_record.get('original_filename'))
    
    flash('Physical file not found on server.', 'danger')
    return redirect(url_for('database_files'))

@app.route('/database/files/delete', methods=['POST'])
@login_required
@role_required(['database_server', 'super_admin'])
def database_delete_file():
    file_id = request.form.get('file_id')
    if file_id:
        file_record = files_table.get(Query().id == file_id)
        if file_record:
            # Delete physical file
            filepath = file_record.get('filepath')
            if filepath:
                abs_path = os.path.join(app.root_path, 'static', filepath)
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            
            # Delete from DB
            files_table.remove(Query().id == file_id)
            flash('File record and physical file deleted.', 'success')
            log_action(session['user_id'], 'delete_file_admin', f"Deleted file ID {file_id}")
        else:
            flash('File record not found.', 'danger')
            
    return redirect(url_for('database_files'))

@app.route('/database/map')
@login_required
@role_required(['database_server', 'super_admin'])
def database_map():
    # Fetch complaints with location data
    complaints = complaints_table.all()
    mapped_complaints = []
    
    for c in complaints:
        loc = c.get('location')
        if loc and loc.get('lat') and loc.get('lng'):
            mapped_complaints.append({
                'id': c.get('id'),
                'title': c.get('title'),
                'status': c.get('status'),
                'lat': loc.get('lat'),
                'lng': loc.get('lng'),
                'category': c.get('category', 'General'),
                'created_at': c.get('created_at', '')
            })
            
    return render_template('database_server/map.html', complaints=mapped_complaints)
