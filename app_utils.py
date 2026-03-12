import logging
import uuid
import socket
import uuid
from datetime import datetime
from flask import request, session, url_for
from flask_mail import Message
import hashlib
import json
import os
from database import notifications_table, logs_table, admin_table, Query

# Global mail instance will be set by app.py
mail = None

def init_utils(mail_instance):
    global mail
    mail = mail_instance

def get_local_ip():
    """Returns the local IP address of the machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't even have to be reachable
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def create_notification(user_id, title, message, link=None):
    """Adds a persistent notification for a specific user."""
    try:
        notifications_table.insert({
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'title': title,
            'message': message,
            'link': link,
            'is_read': False,
            'created_at': datetime.now().isoformat()
        })
        logging.info(f"Notification created for user {user_id}: {title}")
    except Exception as e:
        logging.error(f"Failed to create notification: {e}")

def log_action(user_id, action, details=""):
    ip_address = "N/A"
    os_info = "N/A"
    
    try:
        from flask import request
        if request:
            if request.headers.getlist("X-Forwarded-For"):
                ip_address = request.headers.getlist("X-Forwarded-For")[0]
            else:
                ip_address = request.remote_addr
            
            ua = request.user_agent
            platform = ua.platform
            
            if platform:
                os_map = {
                    'android': 'Android', 'iphone': 'iOS', 'ipad': 'iOS',
                    'win32': 'Windows', 'windows': 'Windows', 'macos': 'macOS', 'linux': 'Linux'
                }
                os_info = os_map.get(platform.lower(), platform.capitalize())
            else:
                os_info = "Unknown"
    except RuntimeError:
        pass

    try:
        logs_table.insert({
            'user_id': user_id,
            'action': action,
            'details': details,
            'ip_address': ip_address,
            'os': os_info,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"Failed to log action: {e}")

def calculate_complaint_hash(complaint_data, prev_hash):
    """Calculates SHA-256 hash of complaint data for blockchain integrity."""
    data_to_hash = complaint_data.copy()
    data_to_hash.pop('current_hash', None)
    
    try:
        serialized_data = json.dumps(data_to_hash, sort_keys=True, default=str)
    except TypeError:
        serialized_data = str(data_to_hash)
    
    combined_data = f"{prev_hash}{serialized_data}"
    return hashlib.sha256(combined_data.encode('utf-8')).hexdigest()

def sync_complaint_to_google_sheets(complaint_data, user_id=None):
    """Sync complaint data to Google Sheets"""
    try:
        from google_sheets_sync import sync_complaint_to_sheets
        
        user_data = None
        if user_id:
            try:
                user_data = admin_table.get(Query().id == user_id)
            except:
                pass
        
        sync_complaint_to_sheets(complaint_data, user_data)
        logging.debug(f"Synced complaint {complaint_data.get('id')} to Google Sheets")
    except ImportError:
         logging.warning("google_sheets_sync module not found. Skipping sync.")
    except Exception as e:
        logging.error(f"Failed to sync complaint to Google Sheets: {str(e)}")

def send_email_notification(recipient_email, subject, body_text, body_html=None):
    if not mail:
        logging.debug("Email notifications disabled: Mail not initialized")
        return False
    
    try:
        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            body=body_text,
            html=body_html
        )
        mail.send(msg)
        logging.info(f"Email sent to {recipient_email}: {subject}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email to {recipient_email}: {str(e)}")
        return False

def send_reset_email(email, reset_link):
    subject = "Reset Your Password - Secure System"
    body_text = f"We received a request to reset your password. Click the link below to securely reset it:\n\n{reset_link}\n\nIf you did not request this, please ignore this email."
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc;">
        <div style="max-width: 600px; width: 100%; margin: 40px auto; background-color: #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
            <!-- Header section -->
            <div style="background: linear-gradient(135deg, #79cd48,red, #d9f065); padding: 40px 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;">Password Reset Request</h1>
            </div>
            
            <!-- Body section -->
            <div style="padding: 40px 30px;">
                <p style="margin-top: 0; margin-bottom: 24px; font-size: 16px; line-height: 1.6; color: #cbd5e1;">Hello,</p>
                <p style="margin-top: 0; margin-bottom: 32px; font-size: 16px; line-height: 1.6; color: #cbd5e1;">We received a request to reset your password for the consumer complaint. You can reset your password securely by clicking the button below.</p>
                
                <div style="text-align: center; margin-bottom: 32px;">
                    <a href="{reset_link}" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #3b82f6, #a855f7); color: #ffffff; text-decoration: none; font-weight: 600; font-size: 16px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(139, 92, 246, 0.3);">
                        Reset Password
                    </a>
                </div>
                
                <p style="margin-top: 0; margin-bottom: 16px; font-size: 14px; line-height: 1.6; color: #94a3b8;">Or copy and paste this link into your browser:</p>
                <p style="margin-top: 0; margin-bottom: 32px; font-size: 13px; line-height: 1.5; color: #60a5fa; word-break: break-all;">
                    <a href="{reset_link}" style="color: #60a5fa; text-decoration: none;">{reset_link}</a>
                </p>
                
                <hr style="border: none; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 30px 0;">
                
                <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #64748b;">If you did not request a password reset, no further action is required and you can safely ignore this email.</p>
            </div>
            
            <!-- Footer section -->
            <div style="background-color: #0f172a; padding: 20px; text-align: center;">
                <p style="margin: 0; font-size: 12px; color: #64748b;">© {datetime.now().year} Secure System. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email_notification(email, subject, body_text, body_html)

def notify_complaint_status_change(complaint, old_status, new_status, notes=None):
    user_id = complaint.get('user_id')
    if not user_id: return False
    
    try:
        user = admin_table.get(Query().id == user_id)
    except:
        return False

    if not user:
        return False
    
    # Check if email_notifications is enabled (default True if column is null or 1)
    # MySQL boolean is 0 or 1.
    if user.get('email_notifications') is not None and not user.get('email_notifications'):
        return False
        
    recipient_email = user.get('email')
    if not recipient_email:
        return False
    
    complaint_title = complaint.get('title', 'Your complaint')
    subject = f"[CUSTOMER SUPPORT SYSTEM] Complaint Status Update: {new_status.capitalize()}"
    body_text = f"Status changed: {old_status} -> {new_status}\nNotes: {notes}"
    body_html = f"<h3>Status changed: {old_status} -> {new_status}</h3><p>Notes: {notes}</p>"
    return send_email_notification(recipient_email, subject, body_text, body_html)
