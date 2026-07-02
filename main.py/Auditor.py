import pdfplumber
import os
import re
import json

PDF_FOLDER = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\FBSC\AOC4"
OUTPUT_FILE = "auditors_data.json"

TABLE_KEYS = [
    "Category of auditor",
    "Name of audit firm",
    "Name of auditor signing report",
    "Firms registration number of audit firm",
    "Membership number of auditor",
    "Address of auditors",
    "Permanent account number of auditor or auditor's firm",
    "SRN of form ADT-1",
    "Date of signing audit report by auditors",
    "Date of signing of balance sheet by auditors"
]

year_regex = re.compile(r"\d{2}/\d{2}/\d{4}\s*to\s*\d{2}/\d{2}/\d{4}")
company_regex = re.compile(r"^(.*?)\s+Standalone Financial Statements", re.IGNORECASE)
currency_regex = re.compile(r"Lakhs of INR", re.IGNORECASE)

def clean(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()

def detect_company(text):
    m = company_regex.search(text)
    return clean(m.group(1)) if m else "Unknown Company"

def detect_currency(text):
    m = currency_regex.search(text)
    return m.group() if m else "Unknown"

def find_years(row):
    years = []
    for cell in row:
        if not cell:
            continue
        match = year_regex.search(cell)
        if match:
            years.append(match.group())
    return years

def is_target_table(table):
    hits = 0
    for row in table:
        row_text = " ".join(row).lower()
        for key in TABLE_KEYS:
            if key.lower() in row_text:
                hits += 1
    return hits >= 4

documents = {}
doc_count = 1

for file in os.listdir(PDF_FOLDER):
    if not file.lower().endswith(".pdf"):
        continue

    path = os.path.join(PDF_FOLDER, file)

    with pdfplumber.open(path) as pdf:

        full_text = ""
        for p in pdf.pages:
            full_text += (p.extract_text() or "") + "\n"

        company = detect_company(full_text)
        currency = detect_currency(full_text)

        table_found = False

        for page_no, page in enumerate(pdf.pages, start=1):

            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:

                cleaned_table = []
                for row in table:
                    if not row:
                        continue
                    cleaned_table.append([clean(cell) for cell in row])

                if not is_target_table(cleaned_table):
                    continue

                table_found = True

                # detect year columns
                periods = []
                for row in cleaned_table[:3]:
                    years = find_years(row)
                    if years:
                        periods = years
                        break

                data_section = {}

                for row in cleaned_table:
                    if len(row) < 1:
                        continue

                    key = row[0]
                    values = row[1:]

                    if not key:
                        continue

                    normalized_key = key.lower().replace(" ", "_")

                    year_map = {}
                    if periods:
                        for i, year in enumerate(periods):
                            value = None
                            if i < len(values) and values[i] != "":
                                value = values[i]
                            year_map[year] = value

                    data_section[normalized_key] = year_map

                documents[f"document_{doc_count}"] = {
                    "company_name": company,
                    "page": page_no,
                    "statement": {
                        "currency": currency,
                        "periods": periods,
                        "data": data_section
                    }
                }

                doc_count += 1
                break

            if table_found:
                break

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(documents, f, indent=2, ensure_ascii=False)

print("Extraction completed.")
print("Saved to:", OUTPUT_FILE)
