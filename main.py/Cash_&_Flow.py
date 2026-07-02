import pdfplumber
import re
import json
import os
from pathlib import Path

FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\FBSC"
TARGET_HEADING = "[100400]"
OUTPUT_FILE = "cashflow_sheets_fixed.json"

pdf_files = []
for root, dirs, files in os.walk(FOLDER_PATH):
    for file in files:
        if file.lower().endswith(".pdf"):
            pdf_files.append(os.path.join(root, file))

print(f"Found {len(pdf_files)} PDF files")


def extract_numeric_value(cell):
    """Bulletproof numeric extraction"""
    if not cell:
        return None

    cell_str = str(cell).replace(",", "").replace(" ", "").strip()
    cell_lower = cell_str.lower()

    if cell_lower in ["yes", "no", "(yes)", "(no)"]:
        return cell_lower

    patterns = [
        r'-?\d+\.?\d*',
        r'-?\d+,\d+\.?\d*',
        r'-?\d+,\d+',
        r'\((\d+\.?\d*)\)',
        r'-?\d+%'
    ]

    for pattern in patterns:
        match = re.search(pattern, cell_str)
        if match:
            try:
                num_str = match.group()
                if num_str.startswith('(') and num_str.endswith(')'):
                    num_str = '-' + num_str[1:-1]
                return float(num_str.replace(',', '').replace('%', ''))
            except:
                continue
    return None


all_results = {}

for pdf_path in pdf_files:
    filename = Path(pdf_path).stem
    print(f"\nProcessing: {filename}")

    company_name = "Unknown"

    with pdfplumber.open(pdf_path) as pdf:
        # -------- COMPANY NAME DETECTION --------
        for page in pdf.pages[:12]:
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                if re.search(r'(PRIVATE LIMITED|LIMITED|LTD)', line):
                    name_parts = [line]
                    if i > 0:
                        prev = lines[i - 1]
                        if not re.search(r'CIN|GST|PAN', prev):
                            name_parts.insert(0, prev)
                    if i > 1:
                        prev2 = lines[i - 2]
                        if prev2.isupper():
                            name_parts.insert(0, prev2)
                    company_name = " ".join(name_parts)
                    company_name = re.sub(r'\s+', ' ', company_name)
                    break
            if company_name != "Unknown":
                break

        print("Company:", company_name)

        # -------- FIND TARGET HEADING --------
        page_no = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if TARGET_HEADING in text:
                page_no = i
                break

        if page_no is None:
            print("Heading not found")
            continue

        print("Heading page:", page_no + 1)

        # -------- SEARCH TABLES IN NEXT 6 PAGES --------
        tables = []
        full_text = ""
        for offset in range(6):
            if page_no + offset < len(pdf.pages):
                page = pdf.pages[page_no + offset]
                extracted = page.extract_tables()
                text = page.extract_text() or ""
                if extracted:
                    tables.extend(extracted)
                    full_text += text

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
        print("No tables found")
        continue

    # -------- FIND BEST TABLE --------
    data_table = None
    best_table_score = 0
    for t in tables:
        if len(t) < 2:
            continue
        joined = " ".join(str(cell) for row in t for cell in row if cell)
        cash_score = joined.lower().count("cash") + joined.lower().count("flow")
        size_score = len(t) * len(t[0]) if t[0] else 0
        if cash_score > best_table_score or (cash_score == best_table_score and size_score > best_table_score):
            data_table = t
            best_table_score = cash_score + size_score / 1000

    if data_table is None:
        data_table = max(tables, key=len)

    headers = data_table[0]

    # -------- PERIOD DETECTION --------
    periods = []
    period_columns = []
    for idx, h in enumerate(headers):
        if not h:
            continue
        clean = str(h).replace("\n", " ").strip()
        match = re.search(r'(\d{2}/\d{2}/\d{4})\s*to\s*(\d{2}/\d{2}/\d{4})', clean, re.I)
        if match:
            period = f"{match.group(1)} to {match.group(2)}"
            periods.append(period)
            period_columns.append(idx)
            continue
        match_single = re.search(r'\d{2}/\d{2}/\d{4}', clean)
        if match_single:
            periods.append(match_single.group())
            period_columns.append(idx)
            continue
        match_year = re.search(r'20\d{2}', clean)
        if match_year:
            periods.append(match_year.group())
            period_columns.append(idx)

    result["statement"]["periods"] = periods
    print(f"Detected {len(periods)} periods: {periods}")

    # -------- FIXED ROW EXTRACTION (EMPTY = NULL) --------
    extracted_rows = 0
    for row_idx, row in enumerate(data_table[1:], 1):
        if not row or len(row) == 0:
            continue

        label = str(row[0]).replace("\n", " ").strip()
        if not label:
            continue

        row_key = re.sub(r'\W+', '_', label).lower().strip("_")

        if row_key in result["statement"]["data"]:
            continue  # Skip duplicates

        result["statement"]["data"][row_key] = {}
        extracted_rows += 1

        # EXACT COLUMN ONLY - NO FALLBACK!
        for col_idx, period in zip(period_columns, periods):
            value = None

            if col_idx < len(row):
                cell_content = str(row[col_idx]).strip() if row[col_idx] else ""

                # STRICT EMPTY CHECK
                if cell_content and cell_content not in ['', ' ', 'nan', 'null', 'N/A']:
                    value = extract_numeric_value(row[col_idx])

            result["statement"]["data"][row_key][period] = value

    all_results[filename] = result
    print(f"✅ Rows: {extracted_rows}, Keys: {len(result['statement']['data'])}")

# -------- SAVE JSON --------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"\n🎉 Extraction Completed Successfully!")
print(f"💾 Saved to: {OUTPUT_FILE}")
