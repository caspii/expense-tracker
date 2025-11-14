import imaplib
import email
from email.header import decode_header
from datetime import datetime
import anthropic
from config import Config


def connect_to_email():
    """Connect to email server via IMAP."""
    mail = imaplib.IMAP4_SSL(Config.EMAIL_IMAP_SERVER)
    mail.login(Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD)
    return mail


def parse_email_with_claude(email_text, email_subject):
    """Use Claude to extract expense data from email text."""
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    
    prompt = f"""Parse this email and extract expense information. Return a JSON object with these fields:
- amount (number)
- type ("income" or "cost")
- currency (3-letter code like USD, EUR)
- explanation (brief description)
- tags (array of relevant tags like ["software", "hosting"])
- vendor_name (company name)
- invoice_number (if present)
- payment_status (if mentioned: "paid", "unpaid", or "pending")

Email Subject: {email_subject}

Email Content:
{email_text}

Return ONLY valid JSON, no other text."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extract JSON from response
    response_text = message.content[0].text
    # Strip markdown code blocks if present
    if response_text.startswith('```'):
        response_text = response_text.split('```')[1]
        if response_text.startswith('json'):
            response_text = response_text[4:]
        response_text = response_text.strip()
    
    import json
    return json.loads(response_text)


def get_attachment(msg):
    """Extract first PDF attachment from email message."""
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue
        
        filename = part.get_filename()
        if filename and filename.lower().endswith('.pdf'):
            return filename, part.get_payload(decode=True)
    
    return None, None


def fetch_new_emails():
    """
    Fetch unread emails and return list of parsed expense data.
    Returns: List of dicts with expense data and email metadata.
    """
    try:
        mail = connect_to_email()
        mail.select('inbox')
        
        # Search for unread emails
        status, messages = mail.search(None, 'UNSEEN')
        email_ids = messages[0].split()
        
        expenses = []
        
        for email_id in email_ids:
            # Fetch email
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Get subject
                    subject = decode_header(msg['Subject'])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    
                    # Get sender
                    sender = msg.get('From')
                    sender_email = email.utils.parseaddr(sender)[1]
                    sender_domain = sender_email.split('@')[1] if '@' in sender_email else ''
                    
                    # Get date
                    email_date = email.utils.parsedate_to_datetime(msg['Date'])
                    
                    # Get email body
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    # Get PDF attachment
                    attachment_filename, attachment_data = get_attachment(msg)
                    
                    # Parse with Claude
                    try:
                        parsed_data = parse_email_with_claude(body[:3000], subject)  # Limit body length
                        
                        expense_data = {
                            'amount': parsed_data.get('amount'),
                            'type': parsed_data.get('type', 'cost'),
                            'currency': parsed_data.get('currency', 'USD'),
                            'explanation': parsed_data.get('explanation', ''),
                            'tags': parsed_data.get('tags', []),
                            'vendor_name': parsed_data.get('vendor_name', ''),
                            'invoice_number': parsed_data.get('invoice_number'),
                            'payment_status': parsed_data.get('payment_status'),
                            'sender_email': sender_email,
                            'sender_domain': sender_domain,
                            'email_subject': subject,
                            'email_date': email_date,
                            'has_attachments': attachment_filename is not None,
                            'attachment_filename': attachment_filename,
                            'attachment_data': attachment_data,
                        }
                        
                        expenses.append(expense_data)
                    
                    except Exception as e:
                        print(f"Error parsing email {email_id}: {e}")
                        continue
            
            # Mark as read
            mail.store(email_id, '+FLAGS', '\\Seen')
        
        mail.close()
        mail.logout()
        
        return expenses
    
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []
