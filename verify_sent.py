
import os
import uuid
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure app can be imported
sys.path.append(os.getcwd())

from app import app, admin_table, TinyDB, Query
from flask import session

class TestGmailSentView(unittest.TestCase):
    def setUp(self):
        self.ctx = app.test_request_context()
        self.ctx.push()
        self.client = app.test_client()
        
        # Setup Admin User
        self.admin_id = str(uuid.uuid4())
        admin_table.insert({
            'id': self.admin_id,
            'username': 'test_admin_sent',
            'full_name': 'Test Admin Sent',
            'email': 'admin_sent@test.com',
            'role': 'admin',
            'is_active': True
        })
        
        # Login
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin_id
            sess['role'] = 'admin'
            sess['username'] = 'test_admin_sent'
            sess['_fresh'] = True

    def tearDown(self):
        admin_table.remove(Query().id == self.admin_id)
        self.ctx.pop()

    @patch('routes_gmail.get_imap_connection')
    def test_sent_json(self, mock_conn):
        # Mock IMAP connection
        mock_mail = MagicMock()
        mock_conn.return_value = (mock_mail, None)
        
        # Mock folder selection
        mock_mail.select.return_value = ('OK', [b'10'])
        
        # Mock search response
        mock_mail.search.return_value = ('OK', [b'100 101'])
        
        # Mock fetch response for Sent
        def mock_fetch(msg_id, parts):
            return ('OK', [(
                f'{msg_id} (RFC822.HEADER)'.encode(), 
                f'Subject: Sent Test {msg_id.decode()}\r\nTo: recipient@example.com\r\nDate: Wed, 01 Jan 2025\r\n\r\n'.encode()
            )])
            
        mock_mail.fetch.side_effect = mock_fetch
        
        # Test Sent Folder
        resp = self.client.get('/admin/gmail/folder/sent/json')
        print(f"\nGET /admin/gmail/folder/sent/json Status: {resp.status_code}")
        
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        print("Sent Response Data:", data)
        
        try:
            self.assertTrue(len(data['emails']) > 0)
            
            # Find any valid email (100 or 101)
            email_obj = next((e for e in data['emails'] if 'Sent Test' in e['subject']), None)
            self.assertIsNotNone(email_obj, "No 'Sent Test' email found")
            self.assertIn('Sent Test', email_obj['subject'])
            self.assertIn('recipient@example.com', email_obj['sender_recipient'])
        except AssertionError as e:
            print(f"ASSERTION FAILED: {e}")
            raise e
        
        # Verify correct folder was selected
        # Note: In our code we attempt "[Gmail]/Sent Mail" first, then "Sent" if fail.
        # Since mock returns OK, it should be "[Gmail]/Sent Mail"
        mock_mail.select.assert_called_with('"[Gmail]/Sent Mail"')

    @patch('routes_gmail.get_imap_connection')
    def test_sent_message_content(self, mock_conn):
        mock_mail = MagicMock()
        mock_conn.return_value = (mock_mail, None)
        mock_mail.select.return_value = ('OK', None)
        
        mock_mail.fetch.return_value = ('OK', [(
            b'100 (RFC822)', 
            b'Subject: Sent Detail\r\nTo: recipient@example.com\r\n\r\nBody Content'
        )])
        
        resp = self.client.get('/admin/gmail/message/sent/100')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        
        self.assertEqual(data['subject'], 'Sent Detail')
        self.assertIn('recipient@example.com', str(data)) # Recipient might be in 'from' depending on parser or raw check

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGmailSentView)
    unittest.TextTestRunner(verbosity=2).run(suite)
