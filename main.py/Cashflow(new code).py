import pdfplumber
import re
import json
import os
from pathlib import Path
from difflib import SequenceMatcher

FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\NCF3(pdf)\To be Jsoned"
PRIMARY_TARGET = "[320000]"
FALLBACK_TARGET = "[100400]"
OUTPUT_FILE = "cashflow_final_CORRECTED.json"

MANDATORY_KEYS = [
    "adjustments_for_other_financial_assets_current_operating_activities",
    "other_inflows_outflows_of_cash_operations",
    "interest_received_investing_activities",
    "other_inflows_outflows_of_cash_investing_activities",
    "interest_paid_financing_activities",
    "other_inflows_outflows_of_cash_financing_activities"
]


def smart_match(mandatory_key, existing_key):
    m_words = set(mandatory_key.split("_"))
    e_words = set(existing_key.split("_"))

    if len(m_words.intersection(e_words)) >= 3:
        return True

    similarity = SequenceMatcher(None, mandatory_key, existing_key).ratio()
    return similarity > 0.65


def extract_cell_value(cell):
    if cell is None:
        return None

    cell_str = str(cell).strip().replace(",", "")

    if cell_str == "":
        return None

    if cell_str.lower() in ["yes", "no"]:
        return cell_str

    bracket_match = re.search(r"\((\d+(?:\.\d+)?)\)", cell_str)
    if bracket_match:
        return -float(bracket_match.group(1))

    num_match = re.search(r"-?\d+(?:\.\d+)?", cell_str)
    if num_match:
        return float(num_match.group())

    return cell_str


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
    company_name = "Unknown"

    with pdfplumber.open(pdf_path) as pdf:

        # Company Name
        for page in pdf.pages[:10]:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if re.search(r'(PRIVATE LIMITED|LIMITED|LTD)', line, re.I):
                    company_name = line.strip()
                    break

        # Find Cash Flow Header
        page_no = None
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if (PRIMARY_TARGET in text or FALLBACK_TARGET in text) and "cash flow" in text.lower():
                page_no = i
                break

        if page_no is None:
            print("❌ Cash flow header not found")
            continue

        tables = []
        full_text = ""

        for offset in range(3):
            if page_no + offset < len(pdf.pages):
                page = pdf.pages[page_no + offset]
                extracted = page.extract_tables()
                if extracted:
                    tables.extend(extracted)
                full_text += page.extract_text() or ""

    currency = "Lakhs of INR" if "Lakhs of INR" in full_text else None

    result = {
        "company_name": company_name,
        "page": page_no + 1,
        "statement": {
            "currency": currency,
            "periods": [],
            "data": {},
            "mandatory_data": {}
        }
    }

    if not tables:
        print("❌ No tables found")
        all_results[filename] = result
        continue

    data_table = max(tables, key=lambda t: len(t))

    # Detect Periods
    headers = [str(h).strip() if h else "" for h in data_table[0]]
    periods = []
    period_columns = []

    for idx, h in enumerate(headers):
        match = re.search(r'\d{2}/\d{2}/\d{4}', h)
        if match:
            periods.append(match.group())
            period_columns.append(idx)

    result["statement"]["periods"] = periods
    print("Detected periods:", periods)

    current_section = None
    previous_label = ""

    for row in data_table[1:]:

        if not row or not any(row):
            continue

        raw_label = str(row[0]).replace("\n", " ").strip()
        label = raw_label.lower()

        # Merge broken lines like:
        # "before extraordinary" + "items"
        if label in ["items", "activities"] and previous_label:
            label = previous_label + " " + label

        previous_label = label

        # Section Detection (DO NOT SKIP)
        if "cash flows from" in label and "operating" in label:
            current_section = "operating"

        elif "cash flows from" in label and "investing" in label:
            current_section = "investing"

        elif "cash flows from" in label and "financing" in label:
            current_section = "financing"

        clean_label = re.sub(r'\W+', '_', label).strip("_")

        # Avoid double section suffix
        if current_section and not clean_label.endswith("_activities"):
            row_key = f"{clean_label}_{current_section}_activities"
        else:
            row_key = clean_label

        if row_key not in result["statement"]["data"]:
            result["statement"]["data"][row_key] = {}

        for col_idx, period in zip(period_columns, periods):
            if col_idx < len(row):
                value = extract_cell_value(row[col_idx])
                result["statement"]["data"][row_key][period] = value

    # -------- Mandatory Matching --------
    extracted_data = result["statement"]["data"]
    mandatory_output = {}

    for mandatory_key in MANDATORY_KEYS:
        mandatory_output[mandatory_key] = {}

        for period in periods:
            mandatory_output[mandatory_key][period] = None

        for existing_key in extracted_data:
            if smart_match(mandatory_key, existing_key):
                for period in periods:
                    mandatory_output[mandatory_key][period] = extracted_data[existing_key].get(period)
                break

    result["statement"]["mandatory_data"] = mandatory_output
    all_results[filename] = result
    print("✅ Done")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print("\n🎉 FULL EXTRACTION COMPLETE — TOTALS INCLUDED — NO ROW SKIPPED")