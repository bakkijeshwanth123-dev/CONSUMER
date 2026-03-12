import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.units import inch
from PyPDF2 import PdfMerger

# Need database access to fetch/update complaints
from database import complaints_table, Query

def generate_tracking_id():
    """Generates the next LEGAL-YYYY-XXXX tracking ID based on existing DB count for the year."""
    current_year = datetime.now().year
    
    # Simple logic: get all complaints with a legal_tracking_id matching the year
    # to find the max index.
    all_complaints = complaints_table.all()
    max_idx = 0
    prefix = f"LEGAL-{current_year}-"
    
    for c in all_complaints:
        tid = c.get('legal_tracking_id')
        if tid and tid.startswith(prefix):
            try:
                num = int(tid.replace(prefix, ''))
                if num > max_idx:
                    max_idx = num
            except ValueError:
                pass
                
    next_idx = max_idx + 1
    return f"{prefix}{next_idx:04d}"

def generate_legal_notice(complaint_id, complaint, customer_name, seller_name, seller_address):
    """Generates the PDF for a legal notice, embeds images, and attaches PDFs."""
    tracking_id = generate_tracking_id()
    now_date = datetime.now()
    
    # Prepare File Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    notices_dir = os.path.join(base_dir, 'static', 'legal_notices')
    if not os.path.exists(notices_dir):
        os.makedirs(notices_dir)
        
    sig_dir = os.path.join(base_dir, 'static', 'signatures')
    if not os.path.exists(sig_dir):
        os.makedirs(sig_dir)
        
    pdf_filename = f"{tracking_id}.pdf"
    base_pdf_path = os.path.join(notices_dir, pdf_filename)
    
    # Initialize ReportLab
    doc = SimpleDocTemplate(base_pdf_path, pagesize=letter,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)
    Story = []
    styles = getSampleStyleSheet()
    
    # Custom Styles
    styles.add(ParagraphStyle(name='CenterHeading', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=14))
    styles.add(ParagraphStyle(name='CenterSubHeading', parent=styles['Heading2'], alignment=TA_CENTER, fontSize=12))
    styles.add(ParagraphStyle(name='JustifyBodyText', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=14))
    styles.add(ParagraphStyle(name='BoldBody', parent=styles['Normal'], fontSize=11, leading=14, fontName='Helvetica-Bold'))
    
    # -------------------------------------------
    # HEADER
    # -------------------------------------------
    Story.append(HRFlowable(width="100%", thickness=1, color="black", spaceBefore=1, spaceAfter=5))
    Story.append(Paragraph("<b>IN THE CONSUMER LEGAL AUTHORITY</b>", styles['CenterHeading']))
    Story.append(Paragraph("<b>Customer Maintenance & Tracking Tribunal</b>", styles['CenterSubHeading']))
    Story.append(HRFlowable(width="100%", thickness=1, color="black", spaceBefore=5, spaceAfter=20))
    
    Story.append(Paragraph("<u><b>LEGAL NOTICE</b></u>", styles['CenterHeading']))
    Story.append(Spacer(1, 15))
    
    # Tracking ID & Date
    Story.append(Paragraph(f"<b>Tracking ID:</b> {tracking_id}", styles['Normal']))
    Story.append(Paragraph(f"<b>Date:</b> {now_date.strftime('%d %B %Y')}", styles['Normal']))
    Story.append(Spacer(1, 20))
    
    # To Section
    safe_seller_name = seller_name if seller_name else "To Whom It May Concern"
    safe_seller_address = seller_address if seller_address else "Address Withheld / Not Provided"
    
    Story.append(Paragraph("<b>To,</b>", styles['BoldBody']))
    Story.append(Paragraph(f"<b>{safe_seller_name}</b>", styles['Normal']))
    Story.append(Paragraph(f"{safe_seller_address}", styles['Normal']))
    Story.append(Spacer(1, 20))
    
    # Subject
    Story.append(Paragraph("<b>Subject: Legal Notice under Consumer Protection Act</b>", styles['BoldBody']))
    Story.append(Spacer(1, 15))
    
    # Body
    Story.append(Paragraph("Respected Sir/Madam,", styles['Normal']))
    Story.append(Spacer(1, 10))
    
    body_p1 = (f"This notice is issued based on <b>Complaint ID {complaint_id}</b> "
               f"filed by <b>{customer_name}</b> on <b>{complaint.get('created_at', 'Unknown Date')[:10]}</b>.")
    Story.append(Paragraph(body_p1, styles['JustifyBodyText']))
    Story.append(Spacer(1, 10))
    
    Story.append(Paragraph("<b>Complaint Title:</b>", styles['BoldBody']))
    Story.append(Paragraph(complaint.get('title', 'N/A'), styles['Normal']))
    Story.append(Spacer(1, 10))
    
    Story.append(Paragraph("<b>Description:</b>", styles['BoldBody']))
    Story.append(Paragraph(complaint.get('description', 'N/A'), styles['JustifyBodyText']))
    Story.append(Spacer(1, 20))
    
    # -------------------------------------------
    # ATTACHED EVIDENCE SECTION (IMAGES)
    # -------------------------------------------
    Story.append(HRFlowable(width="100%", thickness=1, color="grey", spaceBefore=10, spaceAfter=10))
    Story.append(Paragraph("<b>ATTACHED EVIDENCE</b>", styles['CenterHeading']))
    Story.append(HRFlowable(width="100%", thickness=1, color="grey", spaceBefore=10, spaceAfter=20))
    
    # Get all uploaded images/files from the complaint
    # Assume image_paths and file_paths exist in complaint data or from DB.
    # We will look for standard fields 'image_paths' or 'file_path'/ 'image_path'
    image_paths = complaint.get('image_paths', [])
    if complaint.get('image_path') and complaint.get('image_path') not in image_paths:
        image_paths.append(complaint.get('image_path'))
        
    file_paths = complaint.get('file_paths', [])
    if complaint.get('file_path') and complaint.get('file_path') not in file_paths:
        file_paths.append(complaint.get('file_path'))
             
    # Support 'attachment' field used tightly in the complaints table
    attachment = complaint.get('attachment')
    if attachment:
        # Check if it's an image or a doc based on extension loosely
        if attachment.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            if attachment not in image_paths:
                image_paths.append(attachment)
        else:
            if attachment not in file_paths:
                file_paths.append(attachment)
                
    # Support 'invoice_file' upload from Amazon/Flipkart/Third-Party
    invoice_file = complaint.get('invoice_file')
    if invoice_file:
        if invoice_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            if invoice_file not in image_paths:
                image_paths.append(invoice_file)
        else:
            if invoice_file not in file_paths:
                file_paths.append(invoice_file)

    appended_pdfs = []
             
    Story.append(Paragraph("<b>1) Image Proofs:</b>", styles['BoldBody']))
    Story.append(Spacer(1, 10))
    
    has_images = False
    
    for img_path in image_paths:
        if not img_path: continue
        # Normalize path
        full_img_path = os.path.join(base_dir, 'static', img_path.replace('\\', '/').lstrip('/static/'))
        
        # also check raw path (if it's already full or relative differently)
        if not os.path.exists(full_img_path):
             full_img_path = os.path.join(base_dir, img_path)
             
        if os.path.exists(full_img_path):
            try:
                # Add image to PDF maintaining aspect ratio, max width ~5 inches
                img = RLImage(full_img_path)
                aspect = img.imageWidth / float(img.imageHeight)
                img.drawWidth = 5 * inch
                img.drawHeight = (5 * inch) / aspect
                
                # If height is too big for a page, constrain height instead
                if img.drawHeight > 6 * inch:
                     img.drawHeight = 6 * inch
                     img.drawWidth = (6 * inch) * aspect

                Story.append(img)
                Story.append(Spacer(1, 15))
                has_images = True
            except Exception as e:
                print(f"Legal Notice Error embedding image {full_img_path}: {e}")
                
    if not has_images:
        Story.append(Paragraph("No image evidence attached.", styles['Normal']))
    
    
    Story.append(Spacer(1, 20))
    Story.append(Paragraph("<b>2) Supporting Documents:</b>", styles['BoldBody']))
    Story.append(Spacer(1, 10))
    
    has_docs = False
    for f_path in file_paths:
         if not f_path: continue
         full_f_path = os.path.join(base_dir, 'static', f_path.replace('\\', '/').lstrip('/static/'))
         if not os.path.exists(full_f_path):
              full_f_path = os.path.join(base_dir, f_path)
              
         if os.path.exists(full_f_path):
              ext = full_f_path.lower().split('.')[-1]
              if ext == 'pdf':
                   appended_pdfs.append(full_f_path)
                   has_docs = True
              # Note: We can add DOC to PDF logic here if required using external libs like docx2pdf
              # For now, we will add images that might have been uploaded in the files section
              elif ext in ['jpg', 'jpeg', 'png']:
                   try:
                       img = RLImage(full_f_path)
                       aspect = img.imageWidth / float(img.imageHeight)
                       img.drawWidth = 4 * inch
                       img.drawHeight = (4 * inch) / aspect
                       Story.append(img)
                       has_docs = True
                   except: pass
    
    if has_docs:
         if appended_pdfs:
              Story.append(Paragraph(f"{len(appended_pdfs)} PDF Document(s) will be appended to the end of this notice as an Appendix.", styles['Normal']))
    else:
         Story.append(Paragraph("No additional document evidence attached.", styles['Normal']))
    
    Story.append(HRFlowable(width="100%", thickness=1, color="grey", spaceBefore=20, spaceAfter=20))
    
    # -------------------------------------------
    # CONCLUSION & SIGNATURE
    # -------------------------------------------
    conclusion = ("You are directed to resolve this issue within <b>7 days</b> "
                  "from receipt of this notice failing which further "
                  "legal proceedings will be initiated.")
    Story.append(Paragraph(conclusion, styles['JustifyBodyText']))
    Story.append(Spacer(1, 40))
    
    # Signature
    Story.append(Paragraph("<b>Digitally Signed By:</b>", styles['Normal']))
    
    sig_path = os.path.join(sig_dir, 'admin_signature.png')
    if os.path.exists(sig_path):
         try:
             img = RLImage(sig_path, width=2*inch, height=1*inch)
             Story.append(img)
         except: pass
    else:
         Story.append(Spacer(1, 30)) # Make room if no sig image
         
    Story.append(Paragraph("Admin Authority", styles['Normal']))
    Story.append(Paragraph("Customer Maintenance & Tracking System", styles['Normal']))

    # Build the main PDF
    doc.build(Story)
    
    final_pdf_path = base_pdf_path
    
    # -------------------------------------------
    # MERGE PDFs if there are any attached PDFs
    # -------------------------------------------
    if appended_pdfs:
         try:
             merger = PdfMerger()
             # Append main notice
             merger.append(base_pdf_path)
             # Append attachments
             for attach_pdf in appended_pdfs:
                 merger.append(attach_pdf)
             
             # Overwrite main
             merged_path = base_pdf_path.replace('.pdf', '_merged.pdf')
             merger.write(merged_path)
             merger.close()
             
             # atomic replace
             os.replace(merged_path, base_pdf_path)
         except Exception as e:
             print(f"Error merging PDFs: {e}")
             
    # -------------------------------------------
    # GENERATE TEXT FORMAT
    # -------------------------------------------
    txt_filename = f"{tracking_id}.txt"
    base_txt_path = os.path.join(notices_dir, txt_filename)
    
    txt_content = f"""IN THE CONSUMER LEGAL AUTHORITY
Customer Maintenance & Tracking Tribunal
--------------------------------------------------
LEGAL NOTICE

Tracking ID: {tracking_id}
Date: {now_date.strftime('%d %B %Y')}

To,
{safe_seller_name}
{safe_seller_address}

Subject: Legal Notice under Consumer Protection Act

Respected Sir/Madam,

This notice is issued based on Complaint ID {complaint_id} filed by {customer_name} on {complaint.get('created_at', 'Unknown Date')[:10]}.

Complaint Title:
{complaint.get('title', 'N/A')}

Description:
{complaint.get('description', 'N/A')}

You are directed to resolve this issue within 7 days from receipt of this notice failing which further legal proceedings will be initiated.

Admin Authority
Customer Maintenance & Tracking System
"""
    with open(base_txt_path, 'w', encoding='utf-8') as f:
        f.write(txt_content)
        
    # Update DB
    complaints_table.update({
         'legal_tracking_id': tracking_id,
         'legal_notice_date': now_date.isoformat(),
         'legal_status': 'Generated',
         'legal_pdf_path': f"legal_notices/{pdf_filename}",
         'legal_txt_path': f"legal_notices/{txt_filename}"
    }, Query().id == complaint_id)
    
    return tracking_id
