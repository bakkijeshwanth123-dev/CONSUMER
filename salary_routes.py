import os
import uuid
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session, current_app
from flask_mail import Message
from app import app, mail
from database import *
from app_utils import create_notification, log_action
from auth_utils import login_required, role_required

Admin = Query()
# --- Salary Management Routes ---

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

# Email notification helper
def send_salary_email(recipient_email, subject, body_html):
    """Send salary-related email notifications"""
    try:
        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            html=body_html
        )
        mail.send(msg)
        logging.info(f"Salary email sent to {recipient_email}: {subject}")
        return True
    except Exception as e:
        logging.error(f"Failed to send salary email to {recipient_email}: {str(e)}")
        return False

# Employee Salary Details Route
@app.route('/employee/salary/details', methods=['GET', 'POST'])
@login_required
def employee_salary_details():
    user_id = session['user_id']
    existing_record = bank_details_table.search(BankDetail.employee_id == user_id)
    
    if request.method == 'POST':
        # Check if already verified
        if existing_record and existing_record[0].get('is_verified'):
            flash('Your bank details are verified and locked. Contact admin for changes.', 'warning')
            return redirect(url_for('employee_salary_details'))
            
        bank_name = request.form.get('bank_name', '').strip()
        account_holder = request.form.get('account_holder', '').strip()
        account_number = request.form.get('account_number', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        account_type = request.form.get('account_type', 'Savings')
        upi_id = request.form.get('upi_id', '').strip()
        pan_number = request.form.get('pan_number', '').strip()
        
        # Mandatory fields check excluding account_number if it's an update and not provided
        if not all([bank_name, account_holder, ifsc_code]):
            flash('Please fill all mandatory fields.', 'danger')
            return redirect(url_for('employee_salary_details'))
            
        if not existing_record and not account_number:
            flash('Account number is required for first-time submission.', 'danger')
            return redirect(url_for('employee_salary_details'))

        # Handle File Upload
        verification_image = request.files.get('verification_image')
        image_path = existing_record[0].get('verification_image') if existing_record else None
        
        if verification_image and verification_image.filename:
            file_ext = os.path.splitext(verification_image.filename)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.pdf']:
                flash('Invalid file format. Please upload JPG, PNG, or PDF.', 'danger')
                return redirect(url_for('employee_salary_details'))
            
            filename = f"salary_{user_id}_{int(datetime.now().timestamp())}{file_ext}"
            upload_dir = os.path.join('static', 'uploads', 'salary_docs')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            save_path = os.path.join(upload_dir, filename)
            verification_image.save(save_path)
            image_path = save_path.replace('\\', '/')

        # Encrypt Account Number ONLY if provided
        data = {
            'employee_id': user_id,
            'bank_name': bank_name,
            'account_holder_name': account_holder,
            'ifsc_code': ifsc_code,
            'account_type': account_type,
            'upi_id': upi_id,
            'pan_number': pan_number,
            'verification_image': image_path,
            'is_verified': False,
            'updated_at': datetime.now().isoformat()
        }
        
        if account_number:
            data['account_number_enc'] = encrypt_account_number(account_number)
        
        if existing_record:
            bank_details_table.update(data, BankDetail.employee_id == user_id)
            log_action(user_id, 'salary_update', 'Updated bank details and/or verification image')
            flash('Bank details updated successfully. Pending admin verification.', 'success')
        else:
            if not image_path:
                flash('Verification image is mandatory for first-time submission.', 'danger')
                return redirect(url_for('employee_salary_details'))
                
            data['created_at'] = datetime.now().isoformat()
            data['id'] = str(uuid.uuid4())
            bank_details_table.insert(data)
            log_action(user_id, 'salary_create', 'Created bank details and uploaded verification image')
            flash('Bank details submitted successfully. Pending admin verification.', 'success')
            
        return redirect(url_for('employee_salary_details'))

    # GET Request
    details = existing_record[0] if existing_record else None
    masked_acc_num = "Not Set"
    if details:
        raw_num = decrypt_account_number(details.get('account_number_enc'))
        if raw_num:
            masked_acc_num = "XXXX-XXXX-" + raw_num[-4:] if len(raw_num) > 4 else raw_num
            
    payments = salary_payments_table.search(SalaryPayment.employee_id == user_id)
    payments.sort(key=lambda x: x.get('payment_date', ''), reverse=True)
            
    user_data = admin_table.get(Query().id == user_id)
            
    return render_template('employee/salary_details.html', 
                         details=details, 
                         masked_acc_num=masked_acc_num, 
                         user=user_data,
                         payments=payments)

# Admin - View All Salary Accounts
@app.route('/admin/salary/accounts')
@role_required(['admin', 'super_admin', 'hr_manager'])
def admin_salary_accounts():
    all_details = bank_details_table.all()
    
    # Enrich with user names
    enriched_details = []
    for d in all_details:
        user_data = admin_table.get(Query().id == d['employee_id'])
        if user_data:
            d['employee_name'] = user_data.get('full_name', user_data.get('username'))
            d['employee_email'] = user_data.get('email')
            d['employee_role'] = user_data.get('role')
            d['profile_picture'] = user_data.get('profile_photo') # Pass profile photo
            
            # Decrypt for Admin View (show full number)
            raw_num = decrypt_account_number(d.get('account_number_enc'))
            d['visible_acc_num'] = raw_num if raw_num else 'N/A'
            # Also provide masked version
            d['masked_acc_num'] = "XXXX-XXXX-" + raw_num[-4:] if raw_num and len(raw_num) > 4 else (raw_num if raw_num else 'N/A')
            enriched_details.append(d)
            
    return render_template('admin/salary_accounts.html', bank_details=enriched_details)

# Admin - Verify Bank Details
@app.route('/admin/salary/verify', methods=['GET', 'POST'])
@role_required(['admin', 'super_admin', 'hr_manager'])
def admin_salary_verify():
    action = request.form.get('action')
    emp_id = request.form.get('employee_id')
    
    if action == 'verify':
        bank_details_table.update({
            'is_verified': True,
            'verified_by': session['user_id'],
            'verified_at': datetime.now().isoformat()
        }, BankDetail.employee_id == emp_id)
        
        # Notify employee
        emp_data = admin_table.get(Query().id == emp_id)
        if emp_data:
            emp_email = emp_data.get('email')
            emp_name = emp_data.get('full_name', emp_data.get('username'))

            
            create_notification(
                emp_id,
                "Bank Details Verified",
                "Your bank account details have been verified by admin.",
                url_for('employee_salary_details')
            )
            
            # Send email notification
            if emp_email:
                email_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                        <h2 style="color: #28a745;">✓ Bank Details Verified</h2>
                        <p>Dear {emp_name},</p>
                        <p>Your bank account details have been successfully verified by the admin.</p>
                        <p>Your account is now ready for salary processing. You can view your details anytime in the employee portal.</p>
                        <p style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #28a745;">
                            <strong>Note:</strong> Your bank details are now locked for security. If you need to make changes, please contact the admin.
                        </p>
                        <p style="margin-top: 30px;">Best regards,<br>HR Team</p>
                    </div>
                </body>
                </html>
                """
                send_salary_email(emp_email, "Bank Details Verified - Salary Account", email_body)
        
        log_action(session['user_id'], 'salary_verify', f'Verified bank details for employee {emp_id}')
        flash('Bank details verified and locked.', 'success')
        
    elif action == 'reject':
        bank_details_table.update({
            'is_verified': False,
            'verified_by': None,
            'verified_at': None
        }, BankDetail.employee_id == emp_id)
        
        # Notify employee
        emp_data = admin_table.get(Query().id == emp_id)
        if emp_data:
            emp_email = emp_data.get('email')
            emp_name = emp_data.get('full_name', emp_data.get('username'))
            
            create_notification(
                emp_id,
                "Bank Details Rejected",
                "Your bank account details need correction. Please update and resubmit.",
                url_for('employee_salary_details')
            )
            
            # Send email notification
            if emp_email:
                email_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                        <h2 style="color: #ffc107;">⚠ Bank Details Need Correction</h2>
                        <p>Dear {emp_name},</p>
                        <p>Your bank account details require correction before they can be verified.</p>
                        <p>Please review and update your information in the employee portal, then resubmit for verification.</p>
                        <p style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 4px solid #ffc107;">
                            <strong>Action Required:</strong> Log in to the employee portal and update your bank details.
                        </p>
                        <p style="margin-top: 30px;">Best regards,<br>HR Team</p>
                    </div>
                </body>
                </html>
                """
                send_salary_email(emp_email, "Bank Details Require Correction", email_body)
        
        log_action(session['user_id'], 'salary_reject', f'Rejected bank details for employee {emp_id}')
        flash('Bank details rejected. Employee can now update.', 'warning')
        
    return redirect(url_for('admin_salary_accounts'))

# Admin - Delete Salary Account
@app.route('/admin/salary/delete', methods=['POST'])
@role_required(['admin', 'super_admin'])
def admin_salary_delete():
    emp_id = request.form.get('employee_id')
    
    # Get employee details before deletion for notification
    emp_data = admin_table.get(Query().id == emp_id)
    bank_record = bank_details_table.search(BankDetail.employee_id == emp_id)
    
    if bank_record:
        # Delete the salary account
        bank_details_table.remove(BankDetail.employee_id == emp_id)
        
        # Notify employee
        if emp_data:
            emp_email = emp_data.get('email')
            emp_name = emp_data.get('full_name', emp_data.get('username'))
            
            create_notification(
                emp_id,
                "Salary Account Deleted",
                "Your salary account has been removed by admin. Please contact HR if this was unexpected.",
                url_for('employee_salary_details')
            )
            
            # Send email notification
            if emp_email:
                email_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                        <h2 style="color: #dc3545;">⚠ Salary Account Deleted</h2>
                        <p>Dear {emp_name},</p>
                        <p>Your salary account has been removed from the system by an administrator.</p>
                        <p style="margin-top: 20px; padding: 15px; background-color: #f8d7da; border-left: 4px solid #dc3545;">
                            <strong>Action Required:</strong> If you believe this was done in error, please contact the HR department immediately.
                        </p>
                        <p>If you need to set up a new salary account, please submit your bank details again through the employee portal.</p>
                        <p style="margin-top: 30px;">Best regards,<br>HR Team</p>
                    </div>
                </body>
                </html>
                """
                send_salary_email(emp_email, "Salary Account Deleted", email_body)
        
        log_action(session['user_id'], 'salary_delete', f'Deleted salary account for employee {emp_id}')
        flash(f'Salary account deleted successfully for {emp_data.get("full_name", "employee")}.', 'success')
    else:
        flash('Salary account not found.', 'danger')
        
    return redirect(url_for('admin_salary_accounts'))


# Admin - Salary Payment Processing
@app.route('/admin/salary/payments', methods=['GET', 'POST'])
@role_required(['admin', 'super_admin', 'hr_manager'])
def admin_salary_payments():
    if request.method == 'POST':
        selected_employees = request.form.getlist('employee_ids[]')
        
        for emp_id in selected_employees:
            amount = request.form.get(f'amount_{emp_id}', '0')
            payment_method = request.form.get(f'method_{emp_id}', 'Bank Transfer')
            notes = request.form.get(f'notes_{emp_id}', '').strip()
            
            try:
                amount_float = float(amount)
                if amount_float > 0:
                    payment_data = {
                        'id': str(uuid.uuid4()),
                        'employee_id': emp_id,
                        'amount': amount_float,
                        'payment_date': datetime.now().isoformat(),
                        'payment_method': payment_method,
                        'reference_number': f'PAY-{datetime.now().strftime("%Y%m%d")}-{str(uuid.uuid4())[:8]}',
                        'processed_by': session['user_id'],
                        'notes': notes,
                        'status': 'Completed',
                        'created_at': datetime.now().isoformat()
                    }
                    
                    salary_payments_table.insert(payment_data)
                    
                    # Notify employee
                    emp_data = admin_table.get(Query().id == emp_id)
                    if emp_data:
                        emp_email = emp_data.get('email')
                        emp_name = emp_data.get('full_name', emp_data.get('username'))
                        
                        create_notification(
                            emp_id,
                            "Salary Payment Processed",
                            f"Salary payment of ₹{amount_float:,.2f} has been processed via {payment_method}.",
                            url_for('employee_salary_details')
                        )
                        
                        # Send email notification
                        if emp_email:
                            email_body = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                                    <h2 style="color: #007bff;">💰 Salary Payment Processed</h2>
                                    <p>Dear {emp_name},</p>
                                    <p>Your salary payment has been successfully processed!</p>
                                    <div style="margin: 20px 0; padding: 20px; background-color: #e7f3ff; border-radius: 8px;">
                                        <h3 style="margin-top: 0; color: #007bff;">Payment Details</h3>
                                        <table style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; font-weight: bold;">Amount:</td>
                                                <td style="padding: 8px 0;">₹{amount_float:,.2f}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; font-weight: bold;">Payment Method:</td>
                                                <td style="padding: 8px 0;">{payment_method}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; font-weight: bold;">Reference Number:</td>
                                                <td style="padding: 8px 0;">{payment_data['reference_number']}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; font-weight: bold;">Date:</td>
                                                <td style="padding: 8px 0;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                                            </tr>
                                        </table>
                                    </div>
                                    <p style="margin-top: 20px; padding: 15px; background-color: #d4edda; border-left: 4px solid #28a745;">
                                        <strong>Note:</strong> The amount should reflect in your account within 1-2 business days.
                                    </p>
                                    <p style="margin-top: 30px;">Best regards,<br>HR & Finance Team</p>
                                </div>
                            </body>
                            </html>
                            """
                            send_salary_email(emp_email, f"Salary Payment Processed - ₹{amount_float:,.2f}", email_body)
                    
                    # Update Salary in User Management (Individual update)
                    if emp_data:
                        # Only update salary for staff/employees, not customers/users
                        if emp_data.get('role') not in ['customer', 'user']:
                            admin_table.update({'salary': str(amount_float)}, Query().id == emp_id)
                            logging.info(f"Auto-updated salary for {emp_id} to {amount_float}")

                    log_action(session['user_id'], 'salary_payment', f'Processed payment of ₹{amount_float} for employee {emp_id}')
            except ValueError:
                continue
        
        flash('Salary payments processed successfully.', 'success')
        return redirect(url_for('admin_salary_payments'))
    
    # GET - Show verified employees for payment
    verified_details = bank_details_table.search(BankDetail.is_verified == True)
    
    # Enrich with user data and payment history
    employees_list = []
    for d in verified_details:
        user_data = admin_table.get(Query().id == d['employee_id'])
        if user_data:
            employee_info = {
                'id': d['employee_id'],
                'name': user_data.get('full_name', user_data.get('username')),
                'email': user_data.get('email'),
                'role': user_data.get('role'),
                'bank_name': d.get('bank_name'),
                'masked_acc_num': "XXXX-" + decrypt_account_number(d.get('account_number_enc', ''))[-4:] if d.get('account_number_enc') else 'N/A'
            }
            
            # Get last payment
            payments = salary_payments_table.search(SalaryPayment.employee_id == d['employee_id'])
            if payments:
                last_payment = sorted(payments, key=lambda x: x.get('payment_date', ''), reverse=True)[0]
                employee_info['last_payment'] = last_payment
            else:
                employee_info['last_payment'] = None
                
            employees_list.append(employee_info)
    
    # Get recent payment history
    all_payments = sorted(salary_payments_table.all(), key=lambda x: x.get('payment_date', ''), reverse=True)[:20]
    for payment in all_payments:
        u_data = admin_table.get(Query().id == payment['employee_id'])
        if u_data:
            payment['employee_name'] = u_data.get('full_name', u_data.get('username'))
    
    return render_template('admin/salary_payments.html', employees=employees_list, recent_payments=all_payments)
