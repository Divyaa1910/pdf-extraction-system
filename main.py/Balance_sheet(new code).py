import pdfplumber
import re
import json
import os
from pathlib import Path

FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\NCF3(pdf)\To be Jsoned"
PRIMARY_TARGET = "[110000]"
FALLBACK_TARGET = "[100100]"
OUTPUT_FILE = "Balance_sheet_CORRECTED_v2.json"


# ---------------------- NUMERIC CLEANER ----------------------
def clean_numeric(value):
    if value is None:
        return None

    value = str(value).strip()
    value = value.replace(",", "")

    if value == "":
        return None

    if value.upper() in ["YES", "NO"]:
        return value.upper()

    value = re.sub(r'^\([A-Za-z]\)', '', value).strip()

    if re.match(r'^\(.*\)$', value):
        value = "-" + value[1:-1]

    num_match = re.search(r'-?\d+\.?\d*', value)
    if num_match:
        num = num_match.group(0)
        if "." in num:
            return float(num)
        else:
            return int(num)

    return None


# ---------------------- EXTRACT PERIODS ----------------------
def extract_periods(rows):
    periods = []
    seen = set()

    for row in rows[:5]:
        for cell in row:
            if not cell:
                continue

            text = str(cell)
            date_match = re.search(r'\d{2}/\d{2}/20\d{2}', text)
            if date_match:
                date = date_match.group()
                if date not in seen:
                    periods.append(date)
                    seen.add(date)

    return periods


# ---------------------- GET COMPANY NAME ----------------------
def extract_company_name(text):
    first_line = text.split("\n")[0]
    if "limited" in first_line.lower():
        return first_line.strip()
    return "Unknown"


# ---------------------- GET CURRENCY ----------------------
def extract_currency(text):
    match = re.search(r'in\s+(lakhs?|crores?)', text, re.IGNORECASE)
    if match:
        return match.group(0)
    return None


# ---------------------- MAIN PROCESS ----------------------
pdf_files = []

for root, dirs, files in os.walk(FOLDER_PATH):
    for file in files:
        if file.lower().endswith(".pdf"):
            pdf_files.append(os.path.join(root, file))

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

        # -------- FIND BALANCE SHEET PAGE --------
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""

            if (
                (PRIMARY_TARGET in text or FALLBACK_TARGET in text)
                and "balance sheet" in text.lower()
            ):
                start_page = i
                result["company_name"] = extract_company_name(text)
                result["currency"] = extract_currency(text)
                break

        if start_page is None:
            print("❌ Balance Sheet not found")
            continue

        all_rows = []
        found_last_row = False

        # -------- SIMPLE PAGE LOOP (Updated Stop Logic Only) --------
        for i in range(start_page, len(pdf.pages)):

            page = pdf.pages[i]
            tables = page.extract_tables()

            if tables:
                for table in tables:
                    for row in table:
                        if row and any(row):
                            all_rows.append(row)

                            first_col = str(row[0]).lower() if row[0] else ""

                            if (
                                "total assets" in first_col
                                or "total equity and liabilities" in first_col
                            ):
                                found_last_row = True
                                break

                    if found_last_row:
                        break

            if found_last_row:
                break

        if not all_rows:
            print("❌ No table rows extracted")
            continue

        # -------- PERIOD EXTRACTION --------
        periods = extract_periods(all_rows)
        result["periods"] = periods

        if not periods:
            print("⚠ Periods not detected correctly")

        # -------- DATA EXTRACTION --------
        for row in all_rows:

            if not row:
                continue

            label_parts = [str(cell).strip() for cell in row if cell]
            if not label_parts:
                continue

            label = str(row[0]).replace("\n", " ").strip()

            if not label:
                label = "unnamed_row_" + str(all_rows.index(row))

            clean_label = re.sub(r'\W+', '_', label.lower()).strip("_")

            if clean_label not in result["data"]:
                result["data"][clean_label] = {}

            if not periods:
                periods = [f"column_{i + 1}" for i in range(len(row) - 1)]
                result["periods"] = periods

            values = []
            for cell in row[1:]:
                cleaned_value = clean_numeric(cell)
                values.append(cleaned_value)

            if len(values) == 0:
                for period in periods:
                    result["data"][clean_label][period] = None
                continue

            for idx in range(len(periods)):
                if idx < len(values):
                    result["data"][clean_label][periods[idx]] = values[idx]
                else:
                    result["data"][clean_label][periods[idx]] = None

    all_results[filename] = result


# ---------------------- SAVE JSON ----------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"\n✅ DONE. {len(all_results)} companies processed.")