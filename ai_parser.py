"""
AI Parser module for extracting expense data from text and PDFs using Claude.
"""

import base64
import json
import os
from dotenv import load_dotenv
from anthropic import Anthropic

# Load environment variables
load_dotenv()

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# The field list is shared by both entry points; only the framing differs.
# Text is pasted inline, a PDF rides along as an attached document block.
EXPENSE_FIELDS = """Parse this email/document and extract expense information.
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
- expense_date (YYYY-MM-DD format if mentioned)"""

PARSE_PROMPT = EXPENSE_FIELDS + """

Content:
{content}

Return ONLY valid JSON, no other text."""

PDF_PROMPT = EXPENSE_FIELDS + """

The document is attached.{filename_note}

Return ONLY valid JSON, no other text."""

# A request may not exceed 32MB, and base64 inflates the PDF by roughly a third.
# Refusing early gives a readable error instead of an opaque one from the API.
MAX_PDF_BYTES = 20 * 1024 * 1024


def _ask_claude(content) -> dict:
    """
    Send message content to Claude and parse the expense JSON it returns.

    Args:
        content: A string, or a list of content blocks (text, document, ...)

    Returns:
        dict with parsed expense data or error information
    """
    response_text = None

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            messages=[
                {"role": "user", "content": content}
            ]
        )

        response_text = next(
            (block.text for block in message.content if block.type == "text"), ""
        ).strip()

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
            'raw_response': response_text
        }
    except Exception as e:
        return {
            'error': f'AI parsing failed: {str(e)}'
        }


def parse_text_with_claude(text: str) -> dict:
    """
    Parse text content with Claude to extract expense information.

    Args:
        text: The email or document text to parse

    Returns:
        dict with parsed expense data or error information
    """
    # Limit text length to avoid token limits
    text = text[:5000]

    return _ask_claude(PARSE_PROMPT.format(content=text))


def parse_pdf_with_claude(pdf_data: bytes, filename: str = None) -> dict:
    """
    Parse a PDF with Claude by attaching it as a document block.

    Claude renders every page, so this reads scanned and rasterized invoices
    that carry no text layer - the ones local text extraction sees as empty.

    Args:
        pdf_data: Binary PDF data
        filename: Optional filename, which often carries the vendor or invoice number

    Returns:
        dict with parsed expense data or error information
    """
    if not pdf_data:
        return {'error': 'The PDF is empty.'}

    if len(pdf_data) > MAX_PDF_BYTES:
        return {
            'error': f'PDF is too large ({len(pdf_data) // (1024 * 1024)}MB). '
                     f'The limit is {MAX_PDF_BYTES // (1024 * 1024)}MB.'
        }

    filename_note = f' Its filename is "{filename}".' if filename else ''

    return _ask_claude([
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_data).decode("utf-8"),
            },
        },
        {
            "type": "text",
            "text": PDF_PROMPT.format(filename_note=filename_note),
        },
    ])
