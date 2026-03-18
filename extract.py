#!/usr/bin/env python3
"""
Appropriations Line Items Extractor
Uses Claude API to extract spending tables from Congressional committee report PDFs.
Handles landscape/rotated table pages common in appropriations reports.
"""

import anthropic
import base64
import json
import os
import re
import sys
import time
import pdfplumber
from io import BytesIO
from PIL import Image

API_KEY = "REDACTED"

client = anthropic.Anthropic(api_key=API_KEY)


def fix_json_text(text):
    """Fix common JSON issues from LLM output."""
    if "```" in text:
        match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Fix parenthesized negative numbers: (-1234) -> -1234, (1234) -> -1234
    text = re.sub(r'(?<=[\[,\s])\((\d[\d,]*)\)', lambda m: '-' + m.group(1).replace(',', ''), text)

    # Fix trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)

    return text


def find_table_pages_via_claude(pdf_path):
    """Use Claude to identify the comparative statement table pages."""
    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data,
                    },
                },
                {
                    "type": "text",
                    "text": """Find the COMPARATIVE STATEMENT OF NEW BUDGET (OBLIGATIONAL) AUTHORITY table in this Congressional appropriations committee report.

This table is typically in landscape orientation near the end of the report and spans multiple pages. It shows line-item spending with columns for prior year, budget request, and committee recommendation.

Return JSON with the start and end page numbers (1-indexed) and the column headers:
{"start_page": N, "end_page": M, "columns": ["col1", "col2", ...]}

Return ONLY the JSON."""
                }
            ]
        }],
    )

    text = fix_json_text(response.content[0].text)
    return json.loads(text)


def find_table_pages_heuristic(pdf_path):
    """Use heuristic to find rotated table pages (minimal text = rotated content)."""
    rotated_pages = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        # Scan from the back of the document (tables are near the end)
        for i in range(total - 1, max(0, total - 30), -1):
            text = pdf.pages[i].extract_text() or ""
            # Rotated table pages have very little extractable text (just headers/footers)
            text_len = len(text.strip())
            if text_len < 250 and text_len > 50:  # Has some metadata but no body text
                rotated_pages.append(i)
            elif rotated_pages and text_len > 500:
                # We've found the start of normal content before the table
                break

    return sorted(rotated_pages)


def page_to_image(pdf_path, page_num, resolution=200):
    """Convert a PDF page to a PNG image, auto-rotating if needed."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        img = page.to_image(resolution=resolution)

        # Get the PIL image
        pil_img = img.original

        # Check if we need to rotate - if the page has landscape content in portrait frame
        text = page.extract_text() or ""
        if len(text.strip()) < 250:
            # Likely rotated content - try rotating the image 90 degrees clockwise
            # (landscape table printed sideways on portrait page)
            pil_img = pil_img.rotate(-90, expand=True)

        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()


def extract_page_items(pdf_path, page_num, columns, is_first_page=False):
    """Extract line items from a single page of the comparative statement table."""
    img_data = page_to_image(pdf_path, page_num)
    img_b64 = base64.standard_b64encode(img_data).decode("utf-8")

    cols_str = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(columns))

    prompt = f"""This image shows a page from a COMPARATIVE STATEMENT OF NEW BUDGET (OBLIGATIONAL) AUTHORITY table from a Congressional appropriations committee report.

The table columns are:
{cols_str}

Extract EVERY line item visible on this page. For each item:
- "name": The line item description exactly as shown
- "level": Indentation level:
  0 = Top-level section titles (e.g. "TITLE I—LEGISLATIVE BRANCH", "Grand total")
  1 = Major categories (e.g. "HOUSE OF REPRESENTATIVES", "Salaries and expenses")
  2 = Programs/offices (e.g. "Office of the Speaker")
  3 = Sub-items or detail lines
- "amounts": Array of {len(columns)} numbers matching the columns above.
  - Use null for blank/empty cells
  - Use negative numbers for values shown in parentheses (1,234) = -1234
  - Values are in thousands of dollars
  - Use 0 for dashes or explicit zeros

CRITICAL RULES:
- Extract ALL rows including headers, subtotals, totals, and blank headers
- Do NOT skip any rows visible in the image
- Include section headers even if all amounts are null
- Numbers with commas: 1,234 = 1234 (no commas in JSON)
- Dotted lines (....) separate item names from amounts

Return ONLY a JSON array:
[
  {{"name": "Item name", "level": 0, "amounts": [1234, 5678, 9012, -100, 200]}},
  ...
]"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": prompt}
            ]
        }],
    )

    result_text = fix_json_text(response.content[0].text)

    try:
        items = json.loads(result_text)
        if isinstance(items, dict):
            items = items.get('line_items', items.get('items', []))
        return items
    except json.JSONDecodeError as e:
        print(f"    JSON error on page {page_num + 1}: {e}")
        os.makedirs("extracted", exist_ok=True)
        with open(f"extracted/debug_page_{page_num + 1}.txt", 'w') as f:
            f.write(response.content[0].text)
        return []


def extract_tables_from_pdf(pdf_path, subcommittee, fiscal_year, source_type):
    """Extract spending tables from an appropriations committee report PDF."""
    print(f"\n{'='*60}")
    print(f"Extracting: {subcommittee} {fiscal_year} ({source_type})")
    print(f"PDF: {pdf_path}")
    print(f"{'='*60}")

    # Step 1: Find table pages
    print("  Finding table pages (heuristic)...")
    heuristic_pages = find_table_pages_heuristic(pdf_path)

    if heuristic_pages:
        print(f"  Heuristic found {len(heuristic_pages)} rotated pages: {[p+1 for p in heuristic_pages]}")
        table_pages = heuristic_pages
    else:
        print("  Heuristic failed, using Claude to find pages...")
        try:
            info = find_table_pages_via_claude(pdf_path)
            table_pages = list(range(info['start_page'] - 1, info['end_page']))
            print(f"  Claude found pages {info['start_page']}-{info['end_page']}")
        except Exception as e:
            print(f"  ERROR: Could not find table pages: {e}")
            return None

    # Step 2: Detect columns from first table page
    print("  Detecting column headers...")
    img_data = page_to_image(pdf_path, table_pages[0])
    img_b64 = base64.standard_b64encode(img_data).decode("utf-8")

    col_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {
                    "type": "text",
                    "text": """This is the first page of a COMPARATIVE STATEMENT OF NEW BUDGET AUTHORITY table.

What are the DATA column headers (not the line item descriptions)? These typically include:
- Prior year enacted/appropriation amount
- Budget estimate/request for current year
- Committee recommendation
- Comparison columns (bill vs enacted, bill vs request)

Return ONLY a JSON array of column header strings in order from left to right. Do not include the line item description column.
Example: ["FY 2024 appropriation", "Budget estimate, FY 2025", "Recommended in the bill", "Bill compared with FY 2024 appropriation", "Bill compared with budget estimate"]"""
                }
            ]
        }],
    )

    columns = json.loads(fix_json_text(col_response.content[0].text))
    print(f"  Columns ({len(columns)}): {columns}")

    # Step 3: Extract line items page by page
    all_items = []
    for i, page_num in enumerate(table_pages):
        print(f"  Page {page_num + 1} ({i+1}/{len(table_pages)})...", end=" ", flush=True)
        items = extract_page_items(pdf_path, page_num, columns, is_first_page=(i == 0))
        print(f"{len(items)} items")
        all_items.extend(items)
        if i < len(table_pages) - 1:
            time.sleep(0.5)

    print(f"\n  Total: {len(all_items)} line items extracted")

    result = {
        "columns": columns,
        "line_items": all_items,
        "metadata": {
            "subcommittee": subcommittee,
            "fiscal_year": fiscal_year,
            "source_type": source_type,
            "pdf_path": pdf_path,
            "table_pages": [p + 1 for p in table_pages],
            "extraction_date": time.strftime('%Y-%m-%d'),
            "num_items": len(all_items),
        }
    }

    return result


def save_extraction(result, output_dir="extracted"):
    """Save extraction result to JSON file."""
    os.makedirs(output_dir, exist_ok=True)

    meta = result['metadata']
    safe_name = re.sub(r'[^a-z0-9]+', '_', meta['subcommittee'].lower()).strip('_')
    filename = f"{safe_name}_{meta['fiscal_year'].lower()}_{meta['source_type']}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"  Saved to {filepath}")
    return filepath


def extract_and_save(pdf_path, subcommittee, fiscal_year, source_type, output_dir="extracted"):
    """Extract tables from PDF and save results."""
    result = extract_tables_from_pdf(pdf_path, subcommittee, fiscal_year, source_type)
    if result:
        save_extraction(result, output_dir)
    return result


if __name__ == "__main__":
    pdf_path = "pdfs/CRPT-118hrpt555.pdf"
    if os.path.exists(pdf_path):
        print("Testing extraction on Legislative Branch FY2025 House report...")
        result = extract_and_save(pdf_path, "Legislative Branch", "FY2025", "house")
        if result:
            print(f"\nExtraction complete!")
            print(f"Columns: {result['columns']}")
            print(f"Total line items: {len(result['line_items'])}")
            # Show some sample items with amounts
            print(f"\nSample items with amounts:")
            for item in result['line_items']:
                if item.get('amounts') and any(a is not None and a != 0 for a in item['amounts'] if a is not None):
                    indent = "  " * item.get('level', 0)
                    print(f"  {indent}{item['name']}: {item['amounts']}")
                    if sum(1 for a in item['amounts'] if a is not None and a != 0) > 0:
                        break
            # Show last few items (likely totals)
            print(f"\nLast 5 items:")
            for item in result['line_items'][-5:]:
                indent = "  " * item.get('level', 0)
                print(f"  {indent}{item['name']}: {item['amounts']}")
    else:
        print(f"PDF not found: {pdf_path}")
