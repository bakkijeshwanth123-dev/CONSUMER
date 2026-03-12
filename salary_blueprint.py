"""
Salary Management Blueprint
Handles employee bank details and admin payroll processing
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from tinydb import Query
from cryptography.fernet import Fernet

from app import (
    app, admin_table, bank_details_table, salary_payments_table,
    log_action, create_notification
)

# Create blueprint
salary_bp = Blueprint('salary', __name__)

# Encryption setup for bank account numbers
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

# Query objects
BankDetail = Query()
SalaryPayment = Query()
User = Query()

# Import decorators from routes
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    if isinstance(roles, str):
        roles = [roles]
        
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Employee Salary Details Route
@salary_bp.route('/employee/salary/details', methods=['GET', 'POST'])
@login_required
def employee_salary_details():
    user_id = session['user_id']
    existing_record = bank_details_table.search(BankDetail.employee_id == user_id)
    
    if request.method == 'POST':
        # Check if already verified
        if existing_record and existing_record[0].get('is_verified'):
            flash('Your bank details are verified and locked. Contact admin for changes.', 'warning')
            return redirect(url_for('salary.employee_salary_details'))
            
        bank_name = request.form.get('bank_name', '').strip()
        account_holder = request.form.get('account_holder', '').strip()
        account_number = request.form.get('account_number', '').strip()
        ifsc_code = request.form.get('ifsc_code', '').strip()
        account_type = request.form.get('account_type', 'Savings')
        upi_id = request.form.get('upi_id', '').strip()
        pan_number = request.form.get('pan_number', '').strip()
        
        if not all([bank_name, account_holder, account_number, ifsc_code]):
            flash('Please fill all mandatory fields.', 'danger')
            return redirect(url_for('salary.employee_salary_details'))

        # Encrypt Account Number
        enc_acc_num = encrypt_account_number(account_number)
        
        data = {
            'employee_id': user_id,
            'bank_name': bank_name,
            'account_holder_name': account_holder,
            'account_number_enc': enc_acc_num,
            'ifsc_code': ifsc_code,
            'account_type': account_type,
            'upi_id': upi_id,
            'pan_number': pan_number,
            'is_verified': False,
            'updated_at': datetime.now().isoformat()
        }
        
        if existing_record:
            bank_details_table.update(data, BankDetail.employee_id == user_id)
            log_action(user_id, 'salary_update', 'Updated bank details')
            flash('Bank details updated successfully. Pending admin verification.', 'success')
        else:
            data['created_at'] = datetime.now().isoformat()
            data['id'] = str(uuid.uuid4())
            bank_details_table.insert(data)
            log_action(user_id, 'salary_create', 'Created bank details')
            flash('Bank details submitted successfully. Pending admin verification.', 'success')
            
        return redirect(url_for('salary.employee_salary_details'))

    # GET Request
    details = existing_record[0] if existing_record else None
    masked_acc_num = "Not Set"
    if details:
        raw_num = decrypt_account_number(details.get('account_number_enc'))
        if raw_num:
            masked_acc_num = "XXXX-XXXX-" + raw_num[-4:] if len(raw_num) > 4 else raw_num
            
    return render_template('employee/salary_details.html', details=details, masked_acc_num=masked_acc_num)

# Admin - View All Salary Accounts
@salary_bp.route('/admin/salary/accounts')
@role_required(['admin', 'super_admin'])
def admin_salary_accounts():
    all_details = bank_details_table.all()
    
    # Enrich with user names
    enriched_details = []
    for d in all_details:
        u = admin_table.search(Query().id == d['employee_id'])
        if u:
            user_data = u[0]
            d['employee_name'] = user_data.get('full_name', user_data.get('username'))
            d['employee_email'] = user_data.get('email')
            d['employee_role'] = user_data.get('role')
            
            # Decrypt for Admin View (show full number)
            raw_num = decrypt_account_number(d.get('account_number_enc'))
            d['visible_acc_num'] = raw_num if raw_num else 'N/A'
            # Also provide masked version
            d['masked_acc_num'] = "XXXX-XXXX-" + raw_num[-4:] if raw_num and len(raw_num) > 4 else (raw_num if raw_num else 'N/A')
            enriched_details.append(d)
            
    return render_template('admin/salary_accounts.html', bank_details=enriched_details)

# Admin - Verify Bank Details
@salary_bp.route('/admin/salary/verify', methods=['POST'])
@role_required(['admin', 'super_admin'])
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
        employee = admin_table.search(Query().id == emp_id)
        if employee:
            create_notification(
                emp_id,
                "Bank Details Verified",
                "Your bank account details have been verified by admin.",
                url_for('salary.employee_salary_details')
            )
        
        log_action(session['user_id'], 'salary_verify', f'Verified bank details for employee {emp_id}')
        flash('Bank details verified and locked.', 'success')
        
    elif action == 'reject':
        bank_details_table.update({
            'is_verified': False,
            'verified_by': None,
            'verified_at': None
        }, BankDetail.employee_id == emp_id)
        
        # Notify employee
        employee = admin_table.search(Query().id == emp_id)
        if employee:
            create_notification(
                emp_id,
                "Bank Details Rejected",
                "Your bank account details need correction. Please update and resubmit.",
                url_for('salary.employee_salary_details')
            )
        
        log_action(session['user_id'], 'salary_reject', f'Rejected bank details for employee {emp_id}')
        flash('Bank details rejected. Employee can now update.', 'warning')
        
    return redirect(url_for('salary.admin_salary_accounts'))

# Admin - Salary Payment Processing
@salary_bp.route('/admin/salary/payments', methods=['GET', 'POST'])
@role_required(['admin', 'super_admin'])
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
                    employee = admin_table.search(Query().id == emp_id)
                    if employee:
                        create_notification(
                            emp_id,
                            "Salary Payment Processed",
                            f"Salary payment of ₹{amount_float:,.2f} has been processed via {payment_method}.",
                            url_for('salary.employee_salary_details')
                        )
                    
                    log_action(session['user_id'], 'salary_payment', f'Processed payment of ₹{amount_float} for employee {emp_id}')
            except ValueError:
                continue
        
        flash('Salary payments processed successfully.', 'success')
        return redirect(url_for('salary.admin_salary_payments'))
    
    # GET - Show verified employees for payment
    verified_details = bank_details_table.search(BankDetail.is_verified == True)
    
    # Enrich with user data and payment history
    employees_list = []
    for d in verified_details:
        u = admin_table.search(Query().id == d['employee_id'])
        if u:
            user_data = u[0]
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
        u = admin_table.search(Query().id == payment['employee_id'])
        if u:
            payment['employee_name'] = u[0].get('full_name', u[0].get('username'))
    
    return render_template('admin/salary_payments.html', employees=employees_list, recent_payments=all_payments)
