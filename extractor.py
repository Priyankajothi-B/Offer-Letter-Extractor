# extractor.py
import re
import os
import fitz  # PyMuPDF
import pdfplumber

def clean_company_name(raw_name):
    """Cleans up company name by removing extra prefixes/suffixes but keeping Pvt. Ltd., Limited, etc."""
    if not raw_name:
        return None
    raw_name = raw_name.strip()
    raw_name = re.sub(r"^(for|welcome to|we are pleased to offer you|we are delighted to offer you)\s+", "", raw_name, flags=re.IGNORECASE)
    raw_name = re.sub(r"^(with|at|by|on behalf of)\s+", "", raw_name, flags=re.IGNORECASE)
    raw_name = re.sub(r"\s+Offer Letter$", "", raw_name, flags=re.IGNORECASE)
    raw_name = re.sub(r"[^A-Za-z0-9&\.\,\s\-]", "", raw_name)
    return raw_name.strip(" ,.-")

def parse_amount_from_string(s):
    """Extracts the first numeric amount from a string and returns as int."""
    if not s:
        return None
    m = re.search(r'(\d[\d,]*\.?\d*)', str(s))
    if not m:
        return None
    num_str = m.group(1).replace(',', '')
    try:
        return int(round(float(num_str)))
    except:
        try:
            return int(num_str)
        except:
            return None

def extract_from_pdf(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    # Extract text with PyMuPDF
    doc = fitz.open(pdf_path)
    text_per_page = [page.get_text("text") or "" for page in doc]
    full_text = "\n".join(text_per_page)

    # --- Name extraction ---
    name = None
    name_pattern = re.compile(r"Dear\s+(?:Mr\.|Ms\.|Mrs\.)?\s*([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)", re.IGNORECASE)
    nm = name_pattern.search(full_text)
    if nm:
        name = nm.group(1).strip()

    # --- Company extraction ---
    company_name = None
    company_pattern = re.compile(
        r"\b([A-Z][A-Za-z0-9&\s\.\,]*(?:Private Limited|Pvt\.? Ltd\.?|Ltd\.?|Limited|Corporation|Inc\.?|LLP|Services Limited|Technologies|Mindtree|Zoho|TCS|Infosys))\b",
        re.IGNORECASE
    )
    for ptext in text_per_page:
        match = company_pattern.search(ptext)
        if match:
            company_name = clean_company_name(match.group(1))
            break

    if not company_name:
        m = re.search(r"welcome to\s+([A-Za-z0-9&\.\,\s\-]{2,120})(?:\(|,|\.|\n|$)", full_text, re.IGNORECASE)
        if m:
            company_name = clean_company_name(m.group(1).strip())

    if not company_name:
        m = re.search(r"([A-Za-z0-9&\.\,\s\-]{2,120}?)\s*\(\s*hereinafter\s+referred\s+to\s+as\s+['\"]?Company['\"]?\s*\)", full_text, re.IGNORECASE)
        if m:
            company_name = clean_company_name(m.group(1).strip())

    if not company_name:
        known = ["Zoho", "TCS", "Infosys", "LTI Mindtree", "Wipro", "Accenture", "HCL", "Tech Mahindra"]
        for kw in known:
            if re.search(re.escape(kw), full_text, re.IGNORECASE):
                company_name = kw
                break

    # --- Salary extraction ---
    annual_candidates = []
    monthly_candidates = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            largest_table = None
            largest_size = 0
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    if table and len(table) > 1 and len(table[0]) > 0:
                        size = len(table) * len(table[0])
                        if size > largest_size:
                            largest_size = size
                            largest_table = table

            if largest_table:
                header = [(h or "").strip().lower() for h in largest_table[0]]
                annual_keywords = ["annual", "per annum", "pa", "p.a.", "ctc", "salary", "package", "compensation"]
                monthly_keywords = ["monthly", "per month", "pm", "p.m.", "stipend"]
                annual_cols = [i for i, h in enumerate(header) if any(k in h for k in annual_keywords)]
                monthly_cols = [i for i, h in enumerate(header) if any(k in h for k in monthly_keywords)]

                total_row_keywords = ["total cost", "total ctc", "total package", "total compensation", "(a+b+c)", "cost to company", "total"]

                total_rows = []
                for row in largest_table[1:]:
                    combined = " ".join([(c or "").strip().lower() for c in row])
                    if any(kw in combined for kw in total_row_keywords):
                        total_rows.append(row)

                if total_rows:
                    for r in total_rows:
                        for cidx in annual_cols:
                            if cidx < len(r):
                                val = parse_amount_from_string(r[cidx])
                                if val:
                                    annual_candidates.append(val)
                    if not annual_candidates:
                        for r in total_rows:
                            for cidx in monthly_cols:
                                if cidx < len(r):
                                    val = parse_amount_from_string(r[cidx])
                                    if val:
                                        monthly_candidates.append(val)

                if not annual_candidates:
                    for r in largest_table[1:]:
                        for cidx in annual_cols:
                            if cidx < len(r):
                                val = parse_amount_from_string(r[cidx])
                                if val:
                                    annual_candidates.append(val)
                if not annual_candidates and not monthly_candidates:
                    for r in largest_table[1:]:
                        for cidx in monthly_cols:
                            if cidx < len(r):
                                val = parse_amount_from_string(r[cidx])
                                if val:
                                    monthly_candidates.append(val)

                if not annual_candidates and not monthly_candidates:
                    last = largest_table[-1]
                    for cell in last:
                        val = parse_amount_from_string(cell)
                        if val:
                            monthly_candidates.append(val)
    except:
        pass

    if not annual_candidates:
        patterns_annual = [
            r'(?:total cost to company|total ctc|total package|total compensation|ctc)[^\d₹Rs\r\n]{0,60}(?:₹|Rs\.?|INR)?\s*([0-9\.,]+)',
            r'([0-9\.,]+)\s*(?:per annum|per year|pa|p\.a\.|annual|annum|annually|yearly|ctc)',
        ]
        for pat in patterns_annual:
            m = re.search(pat, full_text, flags=re.I | re.S)
            if m:
                val = parse_amount_from_string(m.group(1))
                if val:
                    annual_candidates.append(val)

    if not annual_candidates:
        patterns_monthly = [
            r'(?:stipend|monthly salary|monthly|per month|pm|p\.m\.)[^\d₹Rs]{0,40}(?:₹|Rs\.?|INR)?\s*([0-9\.,]+)',
            r'(?:₹|Rs\.?|INR)\s*([0-9\.,]+)\s*(?:per month|monthly|pm|p\.m\.)'
        ]
        for pat in patterns_monthly:
            m = re.search(pat, full_text, flags=re.I | re.S)
            if m:
                val = parse_amount_from_string(m.group(1))
                if val:
                    monthly_candidates.append(val)

    chosen_salary = None
    salary_label = None
    if annual_candidates:
        chosen_salary = max(annual_candidates)
        salary_label = "(Annual)"
    elif monthly_candidates:
        chosen_salary = max(monthly_candidates)
        salary_label = "(Monthly)"

    formatted_salary = None
    if chosen_salary:
        formatted_salary = f"₹{chosen_salary:,} {salary_label}" if salary_label else f"₹{chosen_salary:,}"

    return {
        "name": name,
        "company": company_name,
        "salary": formatted_salary
    }
