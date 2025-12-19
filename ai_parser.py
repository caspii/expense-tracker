"""
AI Parser module for extracting expense data from text and PDFs using Claude.
"""

import json
import os
from dotenv import load_dotenv
from anthropic import Anthropic

# Load environment variables
load_dotenv()

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

PARSE_PROMPT = """Parse this email/document and extract expense information.
Return a JSON object with these fields:
- amount (number, required)
- type ("income" or "cost", required)
- cost_category (only if type is "cost": "operations", "freelancers", "equipment", or "other")
  - operations: recurring costs like SaaS, hosting, subscriptions
  - freelancers: payments to contractors, developers, designers
  - equipment: one-off purchases like hardware, software licenses
  - other: anything that doesn't fit above
- currency (3-letter code like USD, EUR, default USD)
- explanation (brief description)
- tags (array of relevant tags like ["software", "hosting"])
- vendor_name (company name)
- invoice_number (if present)
- payment_status (if mentioned: "paid", "unpaid", or "pending")
- expense_date (YYYY-MM-DD format if mentioned)

{subject_line}

Content:
{content}

Return ONLY valid JSON, no other text."""


def parse_text_with_claude(text: str, subject: str = None) -> dict:
    """
    Parse text content with Claude to extract expense information.

    Args:
        text: The email or document text to parse
        subject: Optional subject line for context

    Returns:
        dict with parsed expense data or error information
    """
    # Limit text length to avoid token limits
    text = text[:5000]

    subject_line = f"Subject: {subject}" if subject else ""

    prompt = PARSE_PROMPT.format(
        subject_line=subject_line,
        content=text
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text.strip()

        # Handle potential markdown code blocks in response
        if response_text.startswith('```'):
            # Remove markdown code block wrapper
            lines = response_text.split('\n')
            # Remove first line (```json) and last line (```)
            response_text = '\n'.join(lines[1:-1])

        # Parse JSON response
        data = json.loads(response_text)

        # Ensure required fields have defaults
        if 'amount' not in data:
            data['amount'] = 0
        if 'type' not in data:
            data['type'] = 'cost'
        if 'currency' not in data:
            data['currency'] = 'USD'

        return data

    except json.JSONDecodeError as e:
        return {
            'error': f'Failed to parse AI response as JSON: {str(e)}',
            'raw_response': response_text if 'response_text' in locals() else None
        }
    except Exception as e:
        return {
            'error': f'AI parsing failed: {str(e)}'
        }


def parse_pdf_with_claude(pdf_data: bytes, filename: str = None) -> dict:
    """
    Extract text from PDF and parse with Claude.

    Args:
        pdf_data: Binary PDF data
        filename: Optional filename for context

    Returns:
        dict with parsed expense data or error information
    """
    try:
        import io
        from PyPDF2 import PdfReader

        # Extract text from PDF
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        if not text.strip():
            return {
                'error': 'Could not extract text from PDF. The PDF may be image-based or empty.'
            }

        # Use filename as subject for context
        subject = filename if filename else "PDF Document"

        return parse_text_with_claude(text, subject)

    except ImportError:
        return {
            'error': 'PyPDF2 is not installed. Run: pip install PyPDF2'
        }
    except Exception as e:
        return {
            'error': f'PDF parsing failed: {str(e)}'
        }
