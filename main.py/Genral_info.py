import pdfplumber
import pandas as pd
import re
import json
import os
from datetime import datetime
from pathlib import Path

# Configuration - Update folder path here
FOLDER_PATH = r"C:\Users\Divya Shinde\PycharmProjects\PythonProject\FBSC"
TARGET_TABLE = "[400100]"
OUTPUT_FILE = "extracted_data.json"

all_results = []


def normalize_value(value):
    # Convert numbers, preserve text - removes newlines
    if pd.isna(value) or value in ["", None, "-"]:
        return None
    val_str = str(value).strip().replace(",", "").replace("₹", "").replace("$", "").replace("\n", " ").replace("\\n",
                                                                                                               " ")
    try:
        return float(val_str) if val_str.replace(".", "").replace("-", "").isdigit() else val_str.strip()
    except:
        return val_str.strip()


def clean_headers(headers):
    # Extract ALL years/periods from headers dynamically
    year_pattern = r'(20\d{2}|FY\s*\d{2}-\d{2}|PY\s*\d{2}-\d{2}|Mar\s*\d{2}|\d{2}-\d{2})'
    all_years = sorted(list(set(re.findall(year_pattern, ' '.join(str(h) for h in headers)))))

    # Map each column to its year/period
    year_mapping = {}
    cleaned_headers = []
    for i, h in enumerate(headers):
        h_str = str(h).strip() if h else f"col_{i}"
        h_str = re.sub(r'[\n\r\\n\s]+', ' ', h_str)

        year_match = re.search(year_pattern, h_str)
        if year_match:
            year_key = year_match.group(1).replace(' ', '_').strip()
            year_mapping[i] = year_key
            cleaned_headers.append(year_key)
        else:
            cleaned_headers.append(f"col_{i}")

    return cleaned_headers, all_years, year_mapping


def extract_company_name(text):
    # Extract company name using multiple patterns
    patterns = [
        r"(?:CIN[:\s]+[A-Z0-9]+[\s\S]*?)([A-Z][A-Z\s]{10,}(?:LIMITED|LTD|PRIVATE\s+LIMITED))",
        r"([A-Z]{3,}\s+[A-Z]{3,}\s+(?:LIMITED|PVT\.?\s+LTD|PRIVATE\s+LIMITED))"
    ]
    text_clean = re.sub(r'[\n\r\\n\s]+', ' ', text)
    for pattern in patterns:
        match = re.search(pattern, text_clean, re.I)
        if match:
            return re.sub(r'\s+', ' ', match.group(1)).strip().upper()
    return "UNKNOWN_COMPANY"


# Find all PDF files in folder
pdf_files = []
for root, dirs, files in os.walk(FOLDER_PATH):
    for file in files:
        if file.lower().endswith('.pdf'):
            pdf_files.append(os.path.join(root, file))

print(f"Processing {len(pdf_files)} PDF files")
print(f"Target table: {TARGET_TABLE}")

# Process each PDF file
for idx, pdf_file in enumerate(pdf_files, 1):
    print(f"Processing file {idx}/{len(pdf_files)}: {os.path.basename(pdf_file)}")

    table_data = {}
    company_name = None
    table_found = False
    target_page = None
    years_found = []

    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Scan all pages for target table
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""

                # Check if target table exists on this page
                if TARGET_TABLE in page_text:
                    print(f"  Target table found on page {page_num}")
                    table_found = True
                    target_page = page_num

                    # Extract company name
                    if not company_name:
                        company_name = extract_company_name(page_text)

                    # Extract table from this page only
                    tables = page.extract_tables()
                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        headers, all_years, year_mapping = clean_headers(table[0])
                        years_found = all_years
                        df = pd.DataFrame(table[1:], columns=headers)
                        df = df.dropna(how="all")

                        # Process table rows - Fixed year structure for ALL years
                        for _, row in df.iterrows():
                            label = str(row[headers[0]]).strip()
                            if label:
                                # Initialize ALL years with null
                                row_data = {year: None for year in all_years}

                                # Fill actual values from table columns
                                for col_idx in range(1, len(headers)):
                                    value = normalize_value(row[headers[col_idx]])
                                    if value is not None and col_idx in year_mapping:
                                        year_key = year_mapping[col_idx]
                                        row_data[year_key] = value

                                table_data[label] = row_data
                        break  # First valid table
                    break  # Stop after target table

    except Exception as e:
        print(f"  Error processing file: {e}")
        continue

    # Store results
    result = {
        "filename": os.path.basename(pdf_file),
        "metadata": {
            "company_name": company_name or "NOT_FOUND",
            "table_found": table_found,
            "target_table": TARGET_TABLE,
            "page_number": target_page,
            "years_found": years_found,
            "total_rows": len(table_data)
        },
        "disclosure_data": table_data
    }

    all_results.append(result)
    status = "SUCCESS" if table_found else "NO_TABLE"
    print(f"  Status: {status}, Rows: {len(table_data)}")

# Generate final output
summary = {
    "target_table": TARGET_TABLE,
    "stats": {
        "total_files": len(pdf_files),
        "tables_found": sum(1 for r in all_results if r["metadata"]["table_found"]),
        "extracted_at": datetime.now().isoformat()
    },
    "results": all_results
}

# Save JSON
with open(OUTPUT_FILE, "w", encoding="utf8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f"\nExtraction complete. Output saved to: {OUTPUT_FILE}")
print(f"Tables found: {summary['stats']['tables_found']}/{len(pdf_files)} files")
