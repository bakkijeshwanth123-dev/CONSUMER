
import imaplib
import email
from email.header import decode_header
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Message
from werkzeug.utils import secure_filename
from app import app, mail
from app_utils import log_action
from auth_utils import login_required, role_required
import logging

# IMAP Configuration
IMAP_SERVER = 'imap.gmail.com'

def get_imap_connection():
    try:
        username = app.config.get('MAIL_USERNAME')
        password = app.config.get('MAIL_PASSWORD')
        
        if not username or not password:
            return None, "Email credentials not configured."
            
        mail_conn = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail_conn.login(username, password)
        return mail_conn, None
    except Exception as e:
        return None, str(e)

def decode_mime_words(s):
    if not s: return ""
    return ''.join(
        word.decode(encoding or 'utf-8') if isinstance(word, bytes) else word
        for word, encoding in decode_header(s)
    )

@app.route('/admin/gmail')
@login_required
@role_required(['admin', 'super_admin'])
def admin_gmail():
    return render_template('admin/gmail.html')

@app.route('/admin/gmail/send', methods=['POST'])
@login_required
@role_required(['admin', 'super_admin'])
def admin_gmail_send():
    to_addr = request.form.get('to')
    subject = request.form.get('subject')
    body = request.form.get('body')
    uploaded_files = request.files.getlist('attachments')
    
    if not to_addr or not subject or not body:
        return jsonify({'success': False, 'message': 'All fields are required.'})
        
    try:
        msg = Message(subject=subject, recipients=[to_addr], body=body)
        
        for f in uploaded_files:
            if f and f.filename:
                filename = secure_filename(f.filename)
                msg.attach(filename, f.content_type, f.read())
                
        mail.send(msg)
        log_action(session['user_id'], 'admin_email_sent', f"Sent email to {to_addr}: {subject}")
        return jsonify({'success': True, 'message': f'Email sent successfully to {to_addr}'})
        
    except Exception as e:
        logging.error(f"Email send error: {e}")
        return jsonify({'success': False, 'message': f'Failed: {str(e)}'})

@app.route('/admin/gmail/folder/<folder_name>/json')
@login_required
@role_required(['admin', 'super_admin'])
def admin_gmail_folder_json(folder_name):
    # Map common names to probable IMAP folders
    folder_map = {
        'inbox': 'inbox',
        'sent': '"[Gmail]/Sent Mail"' # Common for Gmail, might need adjustment
    }
    
    imap_folder = folder_map.get(folder_name, 'inbox')
    
    # Fetch latest 20 emails
    mail_conn, error = get_imap_connection()
    if not mail_conn:
        return jsonify({'error': error}), 500
        
    try:
        # Check if folder works, if sent fails try fallback
        typ, data = mail_conn.select(imap_folder)
        if typ != 'OK' and folder_name == 'sent':
            # Fallback for some non-English or different structures
            imap_folder = 'Sent' 
            mail_conn.select(imap_folder)

        # Efficiently get latest emails by sequence number without searching all
        # The SELECT command returns the total number of messages in data[0]
        num_msgs = int(data[0]) if data and data[0] else 0
        
        latest_email_ids = []
        if num_msgs > 0:
            # Sequence numbers: last 20 messages, newest first
            start = max(1, num_msgs - 19)
            latest_email_ids = [str(i).encode() for i in range(num_msgs, start - 1, -1)]
        
        emails = []
        for e_id in latest_email_ids:
            # Fetch headers only using PEEK to avoid marking unread emails as read
            try:
                _, msg_data = mail_conn.fetch(e_id, "(BODY.PEEK[HEADER])")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = decode_mime_words(msg.get("Subject"))
                        
                        # Use 'To' for Sent, 'From' for Inbox
                        if folder_name == 'sent':
                             sender_recipient = decode_mime_words(msg.get("To"))
                        else:
                             sender_recipient = decode_mime_words(msg.get("From"))
                             
                        date_ = msg.get("Date")
                        
                        emails.append({
                            'id': e_id.decode(),
                            'subject': subject or "(No Subject)",
                            'sender_recipient': sender_recipient, # Generic name for UI
                            'date': date_
                        })
            except Exception as e:
                logging.error(f"Error fetching email {e_id}: {e}")
                continue
        
        mail_conn.close()
        mail_conn.logout()
        return jsonify({'emails': emails})
        
    except Exception as e:
        logging.error(f"IMAP Fetch Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/gmail/message/<folder_name>/<msg_id>')
@login_required
@role_required(['admin', 'super_admin'])
def admin_gmail_message_content(folder_name, msg_id):
    # Map common names to probable IMAP folders
    folder_map = {
        'inbox': 'inbox',
        'sent': '"[Gmail]/Sent Mail"' 
    }
    imap_folder = folder_map.get(folder_name, 'inbox')

    mail_conn, error = get_imap_connection()
    if not mail_conn:
        return jsonify({'error': error}), 500
        
    try:
        # Select folder
        typ, data = mail_conn.select(imap_folder)
        if typ != 'OK' and folder_name == 'sent':
            imap_folder = 'Sent'
            mail_conn.select(imap_folder)
        _, msg_data = mail_conn.fetch(msg_id, "(RFC822)")
        
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        subject = decode_mime_words(msg.get("Subject"))
        from_ = decode_mime_words(msg.get("From"))
        to_ = decode_mime_words(msg.get("To"))
        date_ = msg.get("Date")
        
        body = ""
        html_body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        decoded_payload = payload.decode(charset, errors='replace')
                        
                        if "attachment" not in content_disposition:
                            if content_type == "text/plain" and not body:
                                body = decoded_payload
                            elif content_type == "text/html" and not html_body:
                                html_body = decoded_payload
                except:
                    pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
                if msg.get_content_type() == "text/html":
                    html_body = body
                    body = "" # Clear plain text if it's html
            except:
                pass

        mail_conn.close()
        mail_conn.logout()
        
        return jsonify({
            'id': msg_id,
            'subject': subject,
            'from': from_,
            'to': to_,
            'date': date_,
            'body': body,
            'html': html_body or None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
