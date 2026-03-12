from datetime import datetime
import uuid
from flask import render_template, request, redirect, url_for, flash, session
from app import app
from database import *
from app_utils import log_action, create_notification
from auth_utils import login_required, role_required

Refund = Query()

# Staff: Request Refund
@app.route('/staff/refund/request', methods=['GET', 'POST'])
@login_required
@role_required(['employee', 'technician', 'support', 'manager', 'admin', 'super_admin'])
def staff_refund_request():
    if request.method == 'POST':
        user_email = request.form.get('user_email', '').strip()
        amount = request.form.get('amount', '0')
        reason = request.form.get('reason', '').strip()
        
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                flash('Amount must be greater than zero.', 'danger')
                return redirect(url_for('staff_refund_request'))
        except ValueError:
            flash('Invalid amount.', 'danger')
            return redirect(url_for('staff_refund_request'))
            
        # Find user
        user_record = admin_table.search(Query().email == user_email)
        if not user_record:
            flash('User with this email not found.', 'danger')
            return redirect(url_for('staff_refund_request'))
            
        user_id = user_record[0]['id']
        
        refund_data = {
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'user_email': user_email,
            'staff_id': session['user_id'],
            'amount': amount_float,
            'reason': reason,
            'status': 'Pending',
            'created_at': datetime.now().isoformat(),
            'processed_at': None
        }
        
        refunds_table.insert(refund_data)
        log_action(session['user_id'], 'refund_request', f'Requested refund of ₹{amount_float} for {user_email}')
        
        flash('Refund request submitted for admin approval.', 'success')
        return redirect(url_for('staff_refund_request'))
        
    # Get recent requests by this staff member
    recent_requests = refunds_table.search(Query().staff_id == session['user_id'])
    # Sort by created_at desc
    recent_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return render_template('refund/request.html', recent_requests=recent_requests[:10])

# Employee: Verify/Reject Refund from Ticket
@app.route('/employee/ticket/<ticket_id>/refund/<action>', methods=['POST'])
@login_required
@role_required(['employee', 'manager', 'admin', 'super_admin'])
def employee_refund_action(ticket_id, action):
    # Verify permission
    if session.get('role') == 'employee':
        # Ensure assigned
        complaint = complaints_table.search(Query().id == ticket_id)
        if not complaint or complaint[0].get('assigned_to') != session['user_id']:
             flash('Access denied.', 'danger')
             return redirect(url_for('employee_assigned_complaints'))
    
    complaint = complaints_table.search(Query().id == ticket_id)[0]
    user_id = complaint['user_id']
    
    if action == 'verify':
        # Create Refund Record
        refund_id = str(uuid.uuid4())
        refund_data = {
            'id': refund_id,
            'complaint_id': ticket_id,
            'user_id': user_id,
            'staff_id': session['user_id'],
            'amount': float(complaint.get('refund_amount', 0)),
            'reason': complaint.get('refund_reason', 'Refund Request from Complaint'),
            'bank_details': complaint.get('bank_details'),
            'status': 'Pending',
            'created_at': datetime.now().isoformat(),
            'processed_at': None
        }
        refunds_table.insert(refund_data)
        
        # Update Complaint
        complaints_table.update({'refund_status': 'verified', 'refund_id': refund_id}, Query().id == ticket_id)
        
        # Notify Admin
        admin_users = admin_table.search(Query().role.one_of(['admin', 'super_admin']))
        for admin in admin_users:
            create_notification(
                admin['id'],
                "New Verified Refund",
                f"Employee verified refund for Ticket #{ticket_id[:8]}. Action required.",
                url_for('admin_refund_manage')
            )
            
        flash('Refund verified and forwarded to admin.', 'success')
        
    elif action == 'reject':
        complaints_table.update({'refund_status': 'rejected'}, Query().id == ticket_id)
        
        create_notification(
            user_id,
            "Refund Request Rejected",
            f"Your refund request for Ticket #{ticket_id[:8]} was rejected by the technician.",
            url_for('user_view_complaint', complaint_id=ticket_id)
        )
        flash('Refund request rejected.', 'warning')
        
    return redirect(url_for('employee_ticket_view', ticket_id=ticket_id))

# Admin: Manage Refunds
@app.route('/admin/refund/manage', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'super_admin'])
def admin_refund_manage():
    if request.method == 'POST':
        refund_id = request.form.get('refund_id')
        action = request.form.get('action') # 'approve' or 'reject'
        
        refund_record = refunds_table.search(Query().id == refund_id)
        if not refund_record:
            flash('Refund record not found.', 'danger')
            return redirect(url_for('admin_refund_manage'))
            
        refund_item = refund_record[0]
        
        if action == 'approve':
            refunds_table.update({
                'status': 'Paid',
                'processed_at': datetime.now().isoformat(),
                'processed_by': session['user_id']
            }, Query().id == refund_id)
            
            # Update Linked Complaint if exists
            if refund_item.get('complaint_id'):
                complaints_table.update({'refund_status': 'paid'}, Query().id == refund_item['complaint_id'])
            
            # Notify user
            create_notification(
                refund_item['user_id'],
                "Refund Processed",
                f"A refund of ₹{refund_item['amount']:.2f} has been processed.",
                url_for('user_refund_history')
            )
            
            log_action(session['user_id'], 'refund_approve', f'Approved refund {refund_id} for ₹{refund_item["amount"]}')
            flash('Refund approved and marked as paid.', 'success')
            
        elif action == 'reject':
            refunds_table.update({
                'status': 'Rejected',
                'processed_at': datetime.now().isoformat(),
                'processed_by': session['user_id']
            }, Query().id == refund_id)
            
            if refund_item.get('complaint_id'):
                complaints_table.update({'refund_status': 'rejected'}, Query().id == refund_item['complaint_id'])
            
            # Notify User
            create_notification(
                refund_item['user_id'],
                "Refund Rejected",
                f"Your refund request for ₹{refund_item['amount']:.2f} has been rejected by Admin.",
                url_for('user_refund_history')
            )
            
            log_action(session['user_id'], 'refund_reject', f'Rejected refund {refund_id}')
            flash('Refund request rejected.', 'info')
            
        return redirect(url_for('admin_refund_manage'))
        
    all_requests = refunds_table.all()
    
    # Enrich with user info and source complaint
    for req in all_requests:
        # Priority 1: User details stored in refund record (for manual entries)
        # Priority 2: Fetch from user record if user_id exists
        if req.get('user_id'):
            user_data = admin_table.get(Query().id == req['user_id'])
            if user_data:
                req['user_name'] = req.get('user_name') or user_data.get('full_name', user_data.get('username'))
                req['user_email'] = req.get('user_email') or user_data.get('email')
                req['user_mobile'] = req.get('user_mobile') or user_data.get('mobile')
            
        if req.get('complaint_id'):
            comp = complaints_table.search(Query().id == req['complaint_id'])
            if comp:
                req['source'] = f"Ticket #{req['complaint_id'][:8]}"
                # Ensure bank details are present in refund record, if not fetch from complaint
                if not req.get('bank_details'):
                    req['bank_details'] = comp[0].get('bank_details')
        else:
             req['source'] = req.get('source') or "Manual Request"

    all_requests.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return render_template('admin/refund_management.html', requests=all_requests)

@app.route('/admin/refund/add', methods=['POST'])
@login_required
@role_required(['admin', 'super_admin'])
def admin_add_manual_refund():
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    mobile = request.form.get('mobile', '').strip()
    amount = request.form.get('amount', '0')
    reason = request.form.get('reason', '').strip()
    
    bank_name = request.form.get('bank_name', '').strip()
    account_number = request.form.get('account_number', '').strip()
    ifsc_code = request.form.get('ifsc_code', '').strip()
    
    try:
        amount_float = float(amount)
        if amount_float <= 0:
            flash('Amount must be greater than zero.', 'danger')
            return redirect(url_for('admin_refund_manage'))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('admin_refund_manage'))
        
    # Link to user if exists
    user_record = admin_table.search(Query().email == email)
    user_id = user_record[0]['id'] if user_record else None
    
    refund_id = str(uuid.uuid4())
    refund_data = {
        'id': refund_id,
        'user_id': user_id,
        'user_email': email,
        'user_name': name,
        'user_mobile': mobile,
        'amount': amount_float,
        'reason': reason,
        'bank_details': {
            'bank_name': bank_name,
            'account_number': account_number,
            'ifsc_code': ifsc_code
        },
        'status': 'Paid', # Admin manual entry is usually already paid or immediate
        'created_at': datetime.now().isoformat(),
        'processed_at': datetime.now().isoformat(),
        'processed_by': session['user_id'],
        'source': 'Manual Entry (Admin)'
    }
    
    refunds_table.insert(refund_data)
    
    if user_id:
        create_notification(
            user_id,
            "Refund Processed",
            f"A manual refund of ₹{amount_float:.2f} has been recorded for you.",
            url_for('user_refund_history')
        )
        
    log_action(session['user_id'], 'admin_manual_refund', f'Recorded manual refund for {email} - ₹{amount_float}')
    flash('Manual refund recorded successfully.', 'success')
    return redirect(url_for('admin_refund_manage'))

# User: Refund History
@app.route('/user/refund/history')
@login_required
def user_refund_history():
    user_id = session['user_id']
    user_refunds = refunds_table.search(Query().user_id == user_id)
    user_refunds.sort(key=lambda x: x.get('processed_at', '') or '', reverse=True)
    
    return render_template('user/refund_history.html', refunds=user_refunds)
