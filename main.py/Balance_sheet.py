import pdfplumber
import re
import json
import os
import glob
from pathlib import Path
from collections import defaultdict

FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\FBSC"
TARGET_HEADING = "[100100]"
OUTPUT_FILE = "all_Balance_sheet.json"  # Changed to .json

# Scan ALL subfolders recursively
pdf_files = []
for root, dirs, files in os.walk(FOLDER_PATH):
    for file in files:
        if file.lower().endswith('.pdf'):
            pdf_files.append(os.path.join(root, file))

print(f"Found {len(pdf_files)} PDF files")
if pdf_files:
    print("First few:", pdf_files[:3])

all_results = []

for pdf_path in pdf_files:
    filename = Path(pdf_path).stem
    print(f"Processing: {filename}")

    # Extract company name from FIRST page (AOC-4 standard)
    company_name = "Unknown"
    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            first_page_text = pdf.pages[0].extract_text()
            company_patterns = [
                r'Name of the company\s*(.+?)(?=\n|\s*(From|To|\d{2}/\d{2}))',
                r'(?<=Name of the company\n)\s*([A-Z][A-Za-z\s&.,]+?)(?=\n\d{1,2}/\d{2}/\d{4}|\nPart|\n\()',
                r'^([A-Z][A-Z\s&.,]{5,100})$',
            ]
            for pattern in company_patterns:
                matches = re.findall(pattern, first_page_text, re.MULTILINE | re.IGNORECASE)
                if matches:
                    company_name = matches[0].strip()
                    if len(company_name) > 3 and len(company_name) < 100:
                        break
            print(f"    -> Company: {company_name}")

    # Find target page
    page_no = None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if TARGET_HEADING in text:
                page_no = i
                break

    if page_no is None:
        continue

    print(f"  -> Found on page {page_no}")

    # Extract page content
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no]
        tables = page.extract_tables()
        full_text = page.extract_text()

    # Dynamic extraction
    table_match = re.search(r'\[(\d+)\]\s*(.+?)(?=\n|\[)', full_text)
    table_name = table_match.group(2).strip() if table_match else "statement"

    currency_matches = re.findall(r'(INR|Rs\.?|Rupees|rupees)', full_text, re.IGNORECASE)
    currency = currency_matches[0] if currency_matches else None

    extracted_data = {
        filename: {
            "company_name": company_name,
            "page": page_no,
            table_name: {
                "currency": currency,
                "periods": [],
                "data": {}
            }
        }
    }

    # Process tables
    for table in tables:
        if not table or len(table) < 2:
            continue

        headers = [str(cell).strip() if cell else "" for cell in table[0]]
        table_years = sorted(list(set(re.findall(r'20\d{2}', ' '.join(headers)))))
        print(f"    -> Table years: {table_years}")

        extracted_data[filename][table_name]["periods"] = table_years
        year_cols = {re.search(r'20\d{2}', h).group(): idx for idx, h in enumerate(headers) if re.search(r'20\d{2}', h)}

        for row_idx, row in enumerate(table[1:], 1):
            label_raw = str(row[0]).strip() if len(row) > 0 and row[0] else f"row_{row_idx}"
            label_clean = re.sub(r'\d[\d,]*\.?\d*', '', label_raw).strip()
            row_key = re.sub(r'[^\w]', '_', label_clean or label_raw).lower()

            if row_key:
                extracted_data[filename][table_name]["data"][row_key] = {}

                # Create structure for ALL years (null if missing)
                for period in table_years:
                    col_idx = year_cols.get(period)
                    value = None
                    if col_idx is not None and col_idx < len(row):
                        cell = str(row[col_idx]).strip().replace(',', '')
                        try:
                            value = float(cell) if cell.replace('-', '').replace('.', '').isdigit() or cell.startswith(
                                '-') else None
                        except:
                            value = None
                    extracted_data[filename][table_name]["data"][row_key][period] = value

    all_results.append(extracted_data)

# Save as JSON (same structure, proper JSON format)
final_output = {}
for company_data in all_results:
    for filename, content in company_data.items():
        final_output[filename] = content

with open(OUTPUT_FILE + ".json", "w", encoding="utf8") as f:  # Added .json extension + UTF8
    json.dump(final_output, f, indent=2, ensure_ascii=False)

print(f"DONE: {OUTPUT_FILE}.json generated with {len(final_output)} companies")
