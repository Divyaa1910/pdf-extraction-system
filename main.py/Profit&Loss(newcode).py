import pdfplumber
import re
import json
import os
from pathlib import Path

# ---------------------- CONFIG ----------------------
FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\NCF3(pdf)\To be Jsoned"
HEADINGS = ["[100200]", "[210000]"]  # Profit & Loss heading numbers
OUTPUT_FILE = "Profit_and_Loss_CORRECTEDv2.json"

# Regex to detect the next heading dynamically
HEADING_PATTERN = re.compile(r'\[\d+\]\s*.+')

# ---------------------- NUMERIC CLEANER ----------------------
def clean_numeric(value):
    if value is None:
        return None
    value = str(value).strip().replace(",", "")
    if value.upper() in ["YES", "NO"]:
        return value.upper()
    # Remove any prefix in square brackets like [INR/shares]
    value = re.sub(r'\[.*?\]', '', value).strip()
    if value == "":
        return None
    # Bracket negative numbers
    if re.match(r'^\(.*\)$', value):
        value = "-" + value[1:-1]
    # Extract numeric
    num_match = re.search(r'-?\d+\.?\d*', value)
    if num_match:
        num = num_match.group(0)
        return float(num) if "." in num else int(num)
    return value

# ---------------------- PERIOD EXTRACTION ----------------------
PERIOD_RANGE_REGEX = re.compile(r'\d{2}/\d{2}/20\d{2}\s*to\s*\d{2}/\d{2}/20\d{2}')
SINGLE_DATE_REGEX = re.compile(r'\d{2}/\d{2}/20\d{2}')

def extract_periods(rows):
    periods = []
    seen = set()
    for row in rows[:5]:  # scan first 5 rows
        for cell in row:
            if not cell:
                continue
            text = str(cell).strip()
            match_range = PERIOD_RANGE_REGEX.search(text)
            if match_range and match_range.group() not in seen:
                periods.append(match_range.group())
                seen.add(match_range.group())
            else:
                match_single = SINGLE_DATE_REGEX.search(text)
                if match_single and match_single.group() not in seen:
                    periods.append(match_single.group())
                    seen.add(match_single.group())
        if periods:
            break  # stop after first row with periods
    return periods

# ---------------------- COMPANY NAME ----------------------
def extract_company_name(text):
    first_line = text.split("\n")[0]
    if "limited" in first_line.lower():
        return first_line.strip()
    return "Unknown"

# ---------------------- CURRENCY ----------------------
def extract_currency(text):
    match = re.search(r'in\s+(lakhs?|crores?)', text, re.IGNORECASE)
    return match.group(0) if match else None

# ---------------------- MAIN PROCESS ----------------------
pdf_files = [os.path.join(root, file)
             for root, _, files in os.walk(FOLDER_PATH)
             for file in files if file.lower().endswith(".pdf")]

print(f"Found {len(pdf_files)} PDF files")
all_results = {}

for pdf_path in pdf_files:
    filename = Path(pdf_path).stem
    print(f"\nProcessing: {filename}")

    result = {
        "company_name": "Unknown",
        "currency": None,
        "periods": [],
        "data": {}
    }

    with pdfplumber.open(pdf_path) as pdf:
        start_page = None

        # -------- FIND P&L HEADING PAGE --------
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if any(h in text for h in HEADINGS) and "profit and loss" in text.lower():
                start_page = i
                result["company_name"] = extract_company_name(text)
                result["currency"] = extract_currency(text)
                break

        if start_page is None:
            print("❌ Profit & Loss not found")
            continue

        all_rows = []
        found_next_heading = False

        # -------- EXTRACT TABLES UNTIL NEXT HEADING --------
        for i in range(start_page, len(pdf.pages)):
            page = pdf.pages[i]
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if row and any(row):
                            first_col = str(row[0]).strip() if row[0] else ""
                            # Stop if the first column is a new heading (dynamic detection)
                            if HEADING_PATTERN.match(first_col) and i > start_page:
                                found_next_heading = True
                                break
                            all_rows.append(row)
                    if found_next_heading:
                        break
            if found_next_heading:
                break

        if not all_rows:
            print("❌ No table rows extracted")
            continue

        # -------- PERIOD EXTRACTION --------
        periods = extract_periods(all_rows)
        result["periods"] = periods
        if not periods:
            print("⚠ Periods not detected correctly")
            max_cols = max(len(r) for r in all_rows)
            periods = [f"column_{i+1}" for i in range(1, max_cols)]
            result["periods"] = periods

        # -------- DATA EXTRACTION --------
        header_offset = 1 if periods else 0
        for row in all_rows[header_offset:]:
            if not row:
                continue
            label = str(row[0]).replace("\n", " ").strip() if row[0] else f"unnamed_row_{all_rows.index(row)}"
            clean_label = re.sub(r'\W+', '_', label.lower()).strip("_")
            if clean_label not in result["data"]:
                result["data"][clean_label] = {}

            for idx, period in enumerate(periods):
                value = clean_numeric(row[idx+1]) if idx+1 < len(row) else None
                result["data"][clean_label][period] = value

    all_results[filename] = result

# ---------------------- SAVE JSON ----------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"\n✅ DONE. {len(all_results)} companies processed.")