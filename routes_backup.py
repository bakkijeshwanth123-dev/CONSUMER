
import os
import shutil
import datetime
import subprocess
from flask import render_template, request, redirect, url_for, flash, send_file, session
from app import app
from auth_utils import login_required, role_required
from app_utils import log_action

BACKUP_DIR = 'backups'
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

@app.route('/database/backup', methods=['GET', 'POST'])
@login_required
@role_required(['database_server', 'admin', 'super_admin'])
def database_backup():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            try:
                # Create a timestamped backup of all .json files
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_filename = f'tinydb_backup_{timestamp}.zip'
                backup_path = os.path.join(BACKUP_DIR, backup_filename)
                
                # Zip all .json files in the root
                import zipfile
                with zipfile.ZipFile(backup_path, 'w') as zipf:
                    for f in os.listdir('.'):
                        if f.endswith('.json'):
                            zipf.write(f)
                
                log_action(session['user_id'], 'create_backup', f'Created TinyDB backup: {backup_filename}')
                flash(f'Backup created successfully: {backup_filename}', 'success')
                
            except Exception as e:
                flash(f'Error creating backup: {str(e)}', 'danger')
                
        elif action == 'delete':
            filename = request.form.get('filename')
            try:
                if not filename or '..' in filename or not filename.endswith('.zip'):
                     flash('Invalid filename.', 'danger')
                else:
                    path = os.path.join(BACKUP_DIR, filename)
                    if os.path.exists(path):
                        os.remove(path)
                        log_action(session['user_id'], 'delete_backup', f'Deleted backup: {filename}')
                        flash('Backup deleted successfully.', 'success')
                    else:
                        flash('Backup file not found.', 'danger')
            except Exception as e:
                flash(f'Error deleting backup: {str(e)}', 'danger')
                
        elif action == 'restore':
            filename = request.form.get('filename')
            try:
                backup_path = os.path.join(BACKUP_DIR, filename)
                if not filename or '..' in filename or not os.path.exists(backup_path):
                    flash('Backup file not found or invalid.', 'danger')
                    return redirect(url_for('database_backup'))

                # Extract and overwrite .json files
                import zipfile
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall('.')
                
                log_action(session['user_id'], 'restore_backup', f'Restored database from: {filename}')
                flash('Database restored successfully from backup.', 'success')
                
            except Exception as e:
                flash(f'Error restoring backup: {str(e)}', 'danger')
                
        return redirect(url_for('database_backup'))

    # GET: List backups
    backups = []
    if os.path.exists(BACKUP_DIR):
        for f in os.listdir(BACKUP_DIR):
            if f.endswith('.zip') or f.endswith('.sql'): # Show legacy sql if any
                path = os.path.join(BACKUP_DIR, f)
                size = os.path.getsize(path) / (1024 * 1024) # MB
                created = datetime.datetime.fromtimestamp(os.path.getctime(path)).strftime('%Y-%m-%d %H:%M:%S')
                backups.append({'name': f, 'size': round(size, 2), 'created': created})
    
    backups.sort(key=lambda x: x['created'], reverse=True)
    
    return render_template('database_server/backup.html', backups=backups)

@app.route('/database/backup/download/<filename>')
@login_required
@role_required(['database_server', 'admin', 'super_admin'])
def download_backup(filename):
    # Security check
    if '..' in filename or not (filename.endswith('.sql') or filename.endswith('.zip')):
         return "Invalid filename", 400
    return send_file(os.path.join(BACKUP_DIR, filename), as_attachment=True)
