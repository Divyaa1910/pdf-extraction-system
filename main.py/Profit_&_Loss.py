import pdfplumber
import re
import json
import os
from pathlib import Path

FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\FBSC"
TARGET_HEADING = "[100200]"
OUTPUT_FILE = "P&L_sheets.json"

PERIOD_REGEX = r'\d{2}/\d{2}/\d{4}\s*to\s*\d{2}/\d{2}/\d{4}'

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def extract_number(cell):
    if not cell:
        return None
    cell = str(cell).replace(",", "")
    match = re.search(r'-?\d+(?:\.\d+)?', cell)
    if match:
        return float(match.group())
    return None

def merge_split_cells(row):
    merged = []
    buffer = ""
    for cell in row:
        if cell is None:
            continue
        text = str(cell).strip()
        if re.match(r'^\.\d+$', text):
            buffer += text
        else:
            if buffer:
                merged.append(buffer)
            buffer = text
    if buffer:
        merged.append(buffer)
    return merged

pdf_files = []
for root, dirs, files in os.walk(FOLDER_PATH):
    for file in files:
        if file.lower().endswith(".pdf"):
            pdf_files.append(os.path.join(root, file))

print("PDF Found:", len(pdf_files))

all_results = {}

doc_counter = 1

for pdf_path in pdf_files:
    filename = f"document_{doc_counter}"
    doc_counter += 1

    print("\nProcessing:", pdf_path)

    company_name = "Unknown"

    with pdfplumber.open(pdf_path) as pdf:

        # company detection
        for page in pdf.pages[:10]:
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            for i, line in enumerate(lines):
                if re.search(r'(LIMITED|PRIVATE LIMITED|LTD)', line):
                    company_name = line
                    break
            if company_name != "Unknown":
                break

        page_no = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if TARGET_HEADING in text:
                page_no = i
                break

        if page_no is None:
            continue

        page = pdf.pages[page_no]
        tables = page.extract_tables()

        if not tables and page_no + 1 < len(pdf.pages):
            page = pdf.pages[page_no + 1]
            tables = page.extract_tables()

        full_text = page.extract_text() or ""

    currency = "Lakhs of INR" if "Lakhs of INR" in full_text else None

    result = {
        "company_name": company_name,
        "page": page_no + 1,
        "statement": {
            "currency": currency,
            "periods": [],
            "data": {}
        }
    }

    if not tables:
        all_results[filename] = result
        continue

    # choose correct table (largest + has periods)
    selected_table = None
    max_rows = 0

    for t in tables:
        flat = " ".join(str(c) for r in t for c in r if c)
        if re.search(PERIOD_REGEX, flat):
            if len(t) > max_rows:
                selected_table = t
                max_rows = len(t)

    if selected_table is None:
        selected_table = max(tables, key=len)

    headers = selected_table[0]

    periods = []
    for h in headers:
        text = clean_text(h)
        match = re.search(PERIOD_REGEX, text)
        if match:
            periods.append(match.group())

    result["statement"]["periods"] = periods

    total_rows = 0
    extracted_rows = 0

    for raw_row in selected_table[1:]:

        row = merge_split_cells(raw_row)

        if not row:
            continue

        label = clean_text(row[0])
        if not label:
            continue

        total_rows += 1

        key = re.sub(r'\W+', '_', label).lower().strip("_")

        result["statement"]["data"][key] = {}

        for idx, period in enumerate(periods, 1):

            value = None

            if idx < len(row):
                value = extract_number(row[idx])

            result["statement"]["data"][key][period] = value

        extracted_rows += 1

    result["total_rows_in_table"] = total_rows
    result["rows_extracted"] = extracted_rows

    all_results[filename] = result

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2)

print("\nExtraction Complete")
