import gspread
from google.oauth2.service_account import Credentials
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class GoogleSheetsSync:
    def __init__(self, credentials_file, sheet_id):
        """Initialize Google Sheets client"""
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.enabled = False
        
        try:
            self._initialize_client()
            self.enabled = True
            logger.info("Google Sheets sync initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets sync: {str(e)}")
            self.enabled = False
    
    def _initialize_client(self):
        """Initialize the Google Sheets client with service account credentials"""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")
        
        # Define the scope
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Authenticate using service account
        creds = Credentials.from_service_account_file(self.credentials_file, scopes=scope)
        self.client = gspread.authorize(creds)
        
        # Open the spreadsheet
        self.spreadsheet = self.client.open_by_key(self.sheet_id)
        
        # Get or create the worksheet
        self.worksheet = self._get_or_create_worksheet()
    
    def _get_or_create_worksheet(self):
        """Get the complaints worksheet or create it if it doesn't exist"""
        worksheet_name = "Complaints"
        
        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            logger.info(f"Found existing worksheet: {worksheet_name}")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=14)
            logger.info(f"Created new worksheet: {worksheet_name}")
            
            # Set up headers
            headers = [
                "Complaint ID",
                "Title",
                "Description",
                "Category",
                "Priority",
                "Status",
                "User ID",
                "User Name",
                "User Email",
                "Created At",
                "Updated At",
                "Assigned To",
                "Notes",
                "Resolution"
            ]
            worksheet.append_row(headers)
            
            # Format header row
            worksheet.format('A1:N1', {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            logger.info("Headers added to worksheet")
        
        return worksheet
    
    def sync_complaint(self, complaint_data, user_data=None):
        """Sync a complaint to Google Sheets (add or update)"""
        if not self.enabled:
            logger.warning("Google Sheets sync is disabled")
            return False
        
        try:
            complaint_id = complaint_data.get('id', '')
            
            # Prepare row data
            row_data = self._prepare_row_data(complaint_data, user_data)
            
            # Check if complaint already exists
            existing_row = self._find_complaint_row(complaint_id)
            
            if existing_row:
                # Update existing row
                self.worksheet.update(f'A{existing_row}:N{existing_row}', [row_data])
                logger.info(f"Updated complaint {complaint_id} in Google Sheets (row {existing_row})")
            else:
                # Add new row
                self.worksheet.append_row(row_data)
                logger.info(f"Added new complaint {complaint_id} to Google Sheets")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync complaint to Google Sheets: {str(e)}")
            return False
    
    def _prepare_row_data(self, complaint_data, user_data=None):
        """Prepare complaint data for Google Sheets row"""
        return [
            complaint_data.get('id', ''),
            complaint_data.get('title', ''),
            complaint_data.get('description', ''),
            complaint_data.get('category', ''),
            complaint_data.get('priority', ''),
            complaint_data.get('status', ''),
            complaint_data.get('user_id', ''),
            user_data.get('full_name', '') if user_data else '',
            user_data.get('email', '') if user_data else '',
            complaint_data.get('created_at', ''),
            complaint_data.get('updated_at', datetime.now().isoformat()),
            complaint_data.get('assigned_to', ''),
            complaint_data.get('notes', ''),
            complaint_data.get('resolution', '')
        ]
    
    def _find_complaint_row(self, complaint_id):
        """Find the row number of a complaint by ID"""
        try:
            # Get all values in column A (Complaint ID)
            complaint_ids = self.worksheet.col_values(1)
            
            # Find the row (add 1 because list is 0-indexed but sheets are 1-indexed)
            if complaint_id in complaint_ids:
                return complaint_ids.index(complaint_id) + 1
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding complaint row: {str(e)}")
            return None
    
    def bulk_sync_complaints(self, complaints_list, users_dict=None):
        """Sync multiple complaints at once"""
        if not self.enabled:
            logger.warning("Google Sheets sync is disabled")
            return False
        
        success_count = 0
        fail_count = 0
        
        for complaint in complaints_list:
            user_data = None
            if users_dict and complaint.get('user_id'):
                user_data = users_dict.get(complaint.get('user_id'))
            
            if self.sync_complaint(complaint, user_data):
                success_count += 1
            else:
                fail_count += 1
        
        logger.info(f"Bulk sync completed: {success_count} succeeded, {fail_count} failed")
        return True


# Global instance (will be initialized in app.py)
sheets_sync = None

def init_sheets_sync(credentials_file, sheet_id):
    """Initialize the global Google Sheets sync instance"""
    global sheets_sync
    sheets_sync = GoogleSheetsSync(credentials_file, sheet_id)
    return sheets_sync

def sync_complaint_to_sheets(complaint_data, user_data=None):
    """Helper function to sync a complaint"""
    if sheets_sync and sheets_sync.enabled:
        return sheets_sync.sync_complaint(complaint_data, user_data)
    return False
