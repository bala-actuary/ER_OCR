#!/usr/bin/env python3
"""
Comprehensive data quality analysis for Electoral Roll OCR output CSVs.
Analyzes all 60 CSV files in output/AC-184-Part-1-50/
"""

import csv
import io
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# Force UTF-8 output so Tamil characters don't crash on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT_DIR = r"C:\Users\balaa\Dev\NTK\ElectorialData\ER_OCR\output\AC-184-Part-1-50"
ENCODING = "utf-8-sig"

COLUMNS = [
    "AC No", "Part No", "Serial No", "EPIC ID",
    "Name (English)", "Name (Tamil)",
    "Relation Name (English)", "Relation Name (Tamil)",
    "Relation Type", "House No",
    "Age", "Gender", "DOB", "ContactNo"
]

EPIC_PATTERN = re.compile(r'^[A-Z]{3}\d{7}$')
VALID_RELATION_TYPES = {"Father", "Mother", "Husband", "Other", ""}
VALID_GENDERS = {"Male", "Female"}

# Patterns for suspicious content in English name fields
SUSPICIOUS_NAME_RE = re.compile(r'[^A-Za-z\s\-\.\'\u0B80-\u0BFF]')
# Strictly non-ASCII and non-Tamil for name issues
NONASCII_OR_DIGIT_IN_NAME = re.compile(r'[^A-Za-z\s\-\.\']')

# For artifact scanning
CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
PIPE_RE = re.compile(r'\|')
BRACKET_RE = re.compile(r'[\[\]{}]')
DOUBLE_SPACE_RE = re.compile(r'  +')

TAMIL_RANGE = re.compile(r'[\u0B80-\u0BFF]')
ASCII_IN_TAMIL = re.compile(r'[A-Za-z0-9]')

def load_all_csvs(output_dir):
    """Load all CSV files from the output directory."""
    records = []
    file_stats = {}
    csv_files = sorted(Path(output_dir).glob("*.csv"))

    for csv_path in csv_files:
        fname = csv_path.name
        file_records = []
        try:
            with open(csv_path, encoding=ENCODING, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row['_filename'] = fname
                    file_records.append(row)
                    records.append(row)
        except Exception as e:
            print(f"ERROR reading {fname}: {e}")
        file_stats[fname] = len(file_records)

    return records, file_stats, csv_files

def sep(title, char='='):
    width = 100
    print()
    print(char * width)
    print(f"  {title}")
    print(char * width)

def subsep(title):
    sep(title, '-')

def val(row, col):
    """Get value safely, stripping whitespace."""
    v = row.get(col, "")
    if v is None:
        return ""
    return v.strip()

def val_raw(row, col):
    """Get raw value without stripping."""
    v = row.get(col, "")
    if v is None:
        return ""
    return v

def main():
    print("Loading CSV files...")
    records, file_stats, csv_files = load_all_csvs(OUTPUT_DIR)

    total_files = len(csv_files)
    total_records = len(records)

    sep("ELECTORAL ROLL OCR - DATA QUALITY ANALYSIS REPORT")
    print(f"Output directory : {OUTPUT_DIR}")
    print(f"Total CSV files  : {total_files}")
    print(f"Total records    : {total_records}")
    print()
    print("Files with record counts:")
    for fname, count in file_stats.items():
        marker = "  (EMPTY)" if count == 0 else ""
        print(f"  {fname:<80} {count:>3} records{marker}")

    # =========================================================================
    # 1. FILL RATE PER FIELD
    # =========================================================================
    sep("1. FILL RATE PER FIELD")

    if total_records == 0:
        print("No records found.")
    else:
        print(f"{'Column':<35} {'Non-Empty':>10} {'Total':>8} {'Fill %':>8}")
        print("-" * 65)
        for col in COLUMNS:
            non_empty = sum(1 for r in records if val(r, col) != "")
            pct = 100.0 * non_empty / total_records
            flag = ""
            if pct < 95:
                flag = "  <-- LOW"
            if pct < 50:
                flag = "  <-- VERY LOW"
            print(f"  {col:<33} {non_empty:>10} {total_records:>8} {pct:>7.1f}%{flag}")

    # =========================================================================
    # 2. EPIC ID ISSUES
    # =========================================================================
    sep("2. EPIC ID ISSUES")

    epic_issues = []
    for r in records:
        epic = val(r, "EPIC ID")
        if epic == "" or not EPIC_PATTERN.match(epic):
            epic_issues.append(r)

    if not epic_issues:
        print("No EPIC ID issues found.")
    else:
        print(f"Total issues: {len(epic_issues)}")
        print()
        print(f"  {'Serial No':<12} {'EPIC ID':<20} {'Filename'}")
        print(f"  {'-'*12} {'-'*20} {'-'*70}")
        for r in epic_issues:
            serial = val(r, "Serial No")
            epic = val(r, "EPIC ID")
            fname = r.get('_filename', '')
            issue_type = "EMPTY" if epic == "" else f"BAD FORMAT: '{epic}'"
            print(f"  {serial:<12} {issue_type:<30} {fname}")

    # =========================================================================
    # 3. NAME (ENGLISH) ISSUES
    # =========================================================================
    sep("3. NAME (ENGLISH) ISSUES")

    name_eng_issues = []
    for r in records:
        name = val(r, "Name (English)")
        if name == "":
            name_eng_issues.append((r, "EMPTY"))
            continue
        # Check for suspicious characters: digits, special symbols (not space/hyphen/period/apostrophe)
        suspicious = re.findall(r'[^A-Za-z\s\-\.\']', name)
        if suspicious:
            name_eng_issues.append((r, f"SUSPICIOUS CHARS: {suspicious}"))

    if not name_eng_issues:
        print("No Name (English) issues found.")
    else:
        print(f"Total issues: {len(name_eng_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Issue':<40} {'Value':<40} {'Filename'}")
        print(f"  {'-'*12} {'-'*40} {'-'*40} {'-'*50}")
        for r, issue in name_eng_issues:
            serial = val(r, "Serial No")
            name = val(r, "Name (English)")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {issue:<40} {repr(name):<40} {fname}")

    # =========================================================================
    # 4. RELATION NAME (ENGLISH) ISSUES
    # =========================================================================
    sep("4. RELATION NAME (ENGLISH) ISSUES")

    rel_eng_issues = []
    for r in records:
        name = val(r, "Relation Name (English)")
        if name == "":
            rel_eng_issues.append((r, "EMPTY"))
            continue
        suspicious = re.findall(r'[^A-Za-z\s\-\.\']', name)
        if suspicious:
            rel_eng_issues.append((r, f"SUSPICIOUS CHARS: {suspicious}"))

    if not rel_eng_issues:
        print("No Relation Name (English) issues found.")
    else:
        print(f"Total issues: {len(rel_eng_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Issue':<40} {'Value':<40} {'Filename'}")
        print(f"  {'-'*12} {'-'*40} {'-'*40} {'-'*50}")
        for r, issue in rel_eng_issues:
            serial = val(r, "Serial No")
            name = val(r, "Relation Name (English)")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {issue:<40} {repr(name):<40} {fname}")

    # =========================================================================
    # 5. RELATION TYPE ISSUES
    # =========================================================================
    sep("5. RELATION TYPE ISSUES")

    rel_type_issues = []
    rel_type_counts = defaultdict(int)
    for r in records:
        rt = val(r, "Relation Type")
        rel_type_counts[rt] += 1
        if rt not in VALID_RELATION_TYPES:
            rel_type_issues.append(r)

    print("Relation Type value distribution:")
    for rt, count in sorted(rel_type_counts.items(), key=lambda x: -x[1]):
        display = repr(rt) if rt == "" else rt
        flag = ""
        if rt not in VALID_RELATION_TYPES:
            flag = "  <-- INVALID"
        print(f"  {display:<30} {count:>6}{flag}")

    print()
    if not rel_type_issues:
        print("No invalid Relation Type values found.")
    else:
        print(f"Total invalid Relation Type records: {len(rel_type_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Relation Type':<30} {'Filename'}")
        print(f"  {'-'*12} {'-'*30} {'-'*70}")
        for r in rel_type_issues:
            serial = val(r, "Serial No")
            rt = val(r, "Relation Type")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {repr(rt):<30} {fname}")

    # =========================================================================
    # 6. AGE ISSUES
    # =========================================================================
    sep("6. AGE ISSUES")

    age_issues = []
    age_dist = defaultdict(int)
    for r in records:
        age_str = val(r, "Age")
        if age_str == "":
            age_issues.append((r, "EMPTY"))
            age_dist["EMPTY"] += 1
            continue
        try:
            age = int(age_str)
            if age < 18 or age > 120:
                age_issues.append((r, f"OUT OF RANGE: {age}"))
                age_dist[f"OUT_OF_RANGE"] += 1
            else:
                age_dist["OK"] += 1
        except ValueError:
            age_issues.append((r, f"NON-NUMERIC: '{age_str}'"))
            age_dist["NON_NUMERIC"] += 1

    print(f"Age distribution summary: {dict(age_dist)}")
    print()
    if not age_issues:
        print("No age issues found.")
    else:
        print(f"Total age issues: {len(age_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Issue':<30} {'Value':<15} {'Filename'}")
        print(f"  {'-'*12} {'-'*30} {'-'*15} {'-'*70}")
        for r, issue in age_issues:
            serial = val(r, "Serial No")
            age_str = val(r, "Age")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {issue:<30} {repr(age_str):<15} {fname}")

    # =========================================================================
    # 7. GENDER ISSUES
    # =========================================================================
    sep("7. GENDER ISSUES")

    gender_issues = []
    gender_counts = defaultdict(int)
    for r in records:
        g = val(r, "Gender")
        gender_counts[g] += 1
        if g not in VALID_GENDERS:
            gender_issues.append(r)

    print("Gender value distribution:")
    for g, count in sorted(gender_counts.items(), key=lambda x: -x[1]):
        display = repr(g) if g == "" else g
        flag = ""
        if g not in VALID_GENDERS:
            flag = "  <-- INVALID"
        print(f"  {display:<20} {count:>6}{flag}")

    print()
    if not gender_issues:
        print("No gender issues found.")
    else:
        print(f"Total gender issues: {len(gender_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Gender Value':<30} {'Filename'}")
        print(f"  {'-'*12} {'-'*30} {'-'*70}")
        for r in gender_issues:
            serial = val(r, "Serial No")
            g = val(r, "Gender")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {repr(g):<30} {fname}")

    # =========================================================================
    # 8. HOUSE NO ISSUES
    # =========================================================================
    sep("8. HOUSE NO ISSUES")

    house_empty = []
    house_suspicious = []
    house_counts = defaultdict(int)

    # Allowed chars in house no (after stripping leading apostrophe for Excel compat)
    house_allowed = re.compile(r"^'?[A-Za-z0-9\s/\-\.,]+$")

    for r in records:
        raw_house = val_raw(r, "House No")
        house = val(r, "House No")
        if house == "":
            house_empty.append(r)
            house_counts["EMPTY"] += 1
        else:
            if not house_allowed.match(house):
                house_suspicious.append((r, house))
                house_counts["SUSPICIOUS"] += 1
            else:
                house_counts["OK"] += 1

    print(f"House No summary: {dict(house_counts)}")
    print()

    if house_empty:
        print(f"EMPTY House No records: {len(house_empty)}")
        print(f"  {'Serial No':<12} {'EPIC ID':<15} {'Filename'}")
        print(f"  {'-'*12} {'-'*15} {'-'*70}")
        for r in house_empty:
            serial = val(r, "Serial No")
            epic = val(r, "EPIC ID")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {epic:<15} {fname}")
    else:
        print("No empty House No records.")

    print()
    if house_suspicious:
        print(f"SUSPICIOUS House No records: {len(house_suspicious)}")
        print(f"  {'Serial No':<12} {'House No':<30} {'Filename'}")
        print(f"  {'-'*12} {'-'*30} {'-'*70}")
        for r, house in house_suspicious:
            serial = val(r, "Serial No")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {repr(house):<30} {fname}")
    else:
        print("No suspicious House No values.")

    # =========================================================================
    # 9. SERIAL NO ISSUES
    # =========================================================================
    sep("9. SERIAL NO ISSUES")

    serial_issues = []

    # Check empty and non-numeric
    for r in records:
        sn = val(r, "Serial No")
        if sn == "":
            serial_issues.append((r, "EMPTY"))
        elif not sn.isdigit():
            serial_issues.append((r, f"NON-NUMERIC: '{sn}'"))

    # Check duplicates within the same file
    file_serials = defaultdict(list)
    for r in records:
        fname = r.get('_filename', '')
        sn = val(r, "Serial No")
        if sn:
            file_serials[fname].append((sn, r))

    dup_issues = []
    for fname, sn_list in file_serials.items():
        seen = defaultdict(list)
        for sn, r in sn_list:
            seen[sn].append(r)
        for sn, recs in seen.items():
            if len(recs) > 1:
                for r in recs:
                    dup_issues.append((r, f"DUPLICATE serial {sn} in file ({len(recs)} times)"))

    all_serial_issues = serial_issues + dup_issues

    if not all_serial_issues:
        print("No Serial No issues found.")
    else:
        print(f"Total Serial No issues: {len(all_serial_issues)}")
        print()
        print(f"  {'Serial No':<12} {'Issue':<50} {'Filename'}")
        print(f"  {'-'*12} {'-'*50} {'-'*70}")
        for r, issue in all_serial_issues:
            serial = val(r, "Serial No")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {issue:<50} {fname}")

    # =========================================================================
    # 10. TAMIL NAME ISSUES
    # =========================================================================
    sep("10. NAME (TAMIL) AND RELATION NAME (TAMIL) ISSUES")

    tamil_name_empty = []
    tamil_name_ascii = []
    tamil_relname_empty = []
    tamil_relname_ascii = []

    for r in records:
        tn = val(r, "Name (Tamil)")
        tr = val(r, "Relation Name (Tamil)")

        if tn == "":
            tamil_name_empty.append(r)
        else:
            # Check for ASCII chars that suggest OCR confusion
            ascii_chars = ASCII_IN_TAMIL.findall(tn)
            if ascii_chars:
                tamil_name_ascii.append((r, tn, ascii_chars))

        if tr == "":
            tamil_relname_empty.append(r)
        else:
            ascii_chars = ASCII_IN_TAMIL.findall(tr)
            if ascii_chars:
                tamil_relname_ascii.append((r, tr, ascii_chars))

    subsep("10a. Name (Tamil) — EMPTY")
    if not tamil_name_empty:
        print("No empty Name (Tamil) found.")
    else:
        print(f"Total empty: {len(tamil_name_empty)}")
        print(f"  {'Serial No':<12} {'EPIC ID':<15} {'Filename'}")
        print(f"  {'-'*12} {'-'*15} {'-'*70}")
        for r in tamil_name_empty:
            serial = val(r, "Serial No")
            epic = val(r, "EPIC ID")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {epic:<15} {fname}")

    subsep("10b. Name (Tamil) — Contains ASCII/English chars")
    if not tamil_name_ascii:
        print("No Name (Tamil) with ASCII chars found.")
    else:
        print(f"Total affected: {len(tamil_name_ascii)}")
        print(f"  {'Serial No':<12} {'ASCII Chars':<20} {'Value':<40} {'Filename'}")
        print(f"  {'-'*12} {'-'*20} {'-'*40} {'-'*50}")
        for r, tn, ascii_chars in tamil_name_ascii:
            serial = val(r, "Serial No")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {str(ascii_chars):<20} {repr(tn):<40} {fname}")

    subsep("10c. Relation Name (Tamil) — EMPTY")
    if not tamil_relname_empty:
        print("No empty Relation Name (Tamil) found.")
    else:
        print(f"Total empty: {len(tamil_relname_empty)}")
        print(f"  {'Serial No':<12} {'EPIC ID':<15} {'Filename'}")
        print(f"  {'-'*12} {'-'*15} {'-'*70}")
        for r in tamil_relname_empty:
            serial = val(r, "Serial No")
            epic = val(r, "EPIC ID")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {epic:<15} {fname}")

    subsep("10d. Relation Name (Tamil) — Contains ASCII/English chars")
    if not tamil_relname_ascii:
        print("No Relation Name (Tamil) with ASCII chars found.")
    else:
        print(f"Total affected: {len(tamil_relname_ascii)}")
        print(f"  {'Serial No':<12} {'ASCII Chars':<20} {'Value':<40} {'Filename'}")
        print(f"  {'-'*12} {'-'*20} {'-'*40} {'-'*50}")
        for r, tr, ascii_chars in tamil_relname_ascii:
            serial = val(r, "Serial No")
            fname = r.get('_filename', '')
            print(f"  {serial:<12} {str(ascii_chars):<20} {repr(tr):<40} {fname}")

    # =========================================================================
    # 11. ARTIFACT / NOISE ANALYSIS
    # =========================================================================
    sep("11. ARTIFACT / NOISE ANALYSIS (ALL TEXT FIELDS)")

    TEXT_FIELDS = [
        "EPIC ID", "Name (English)", "Name (Tamil)",
        "Relation Name (English)", "Relation Name (Tamil)",
        "Relation Type", "House No", "Serial No",
        "AC No", "Part No"
    ]

    artifact_issues = []

    for r in records:
        serial = val(r, "Serial No")
        fname = r.get('_filename', '')

        for field in TEXT_FIELDS:
            raw = val_raw(r, field)
            v = raw  # keep raw to detect leading/trailing whitespace

            if raw != raw.strip():
                artifact_issues.append((fname, serial, field, repr(raw), "LEADING/TRAILING WHITESPACE"))

            v_stripped = v.strip()

            if PIPE_RE.search(v_stripped):
                artifact_issues.append((fname, serial, field, repr(v_stripped), "PIPE CHARACTER '|'"))

            if BRACKET_RE.search(v_stripped):
                artifact_issues.append((fname, serial, field, repr(v_stripped), "BRACKET CHARACTER []{}"))

            if DOUBLE_SPACE_RE.search(v_stripped):
                artifact_issues.append((fname, serial, field, repr(v_stripped), "DOUBLE SPACE"))

            if CONTROL_CHAR_RE.search(v_stripped):
                artifact_issues.append((fname, serial, field, repr(v_stripped), "CONTROL CHARACTER"))

            # Check for unusual Unicode (not ASCII, not Tamil script range)
            for ch in v_stripped:
                cp = ord(ch)
                # Skip ASCII printable (32-126), Tamil (0x0B80-0x0BFF), common spaces
                if cp < 32 or cp == 127:
                    continue  # Already caught by control char check
                if 32 <= cp <= 126:
                    continue  # Normal ASCII
                if 0x0B80 <= cp <= 0x0BFF:
                    continue  # Tamil script
                # Everything else is unusual Unicode
                artifact_issues.append((fname, serial, field, repr(v_stripped), f"UNUSUAL UNICODE: U+{cp:04X} '{ch}' (name: {unicodedata.name(ch, 'UNKNOWN')})"))
                break  # one report per field per record

    if not artifact_issues:
        print("No artifact/noise issues found.")
    else:
        print(f"Total artifact issues: {len(artifact_issues)}")
        print()
        print(f"  {'Filename':<70} {'Serial':<8} {'Field':<30} {'Issue'}")
        print(f"  {'-'*70} {'-'*8} {'-'*30} {'-'*50}")
        for fname, serial, field, value, issue in artifact_issues:
            print(f"  {fname:<70} {serial:<8} {field:<30} {issue}")
            print(f"    Value: {value}")

    # =========================================================================
    # 12. AC NO AND PART NO CONSISTENCY
    # =========================================================================
    sep("12. AC NO AND PART NO CONSISTENCY")

    ac_values = defaultdict(int)
    part_values = defaultdict(int)
    empty_ac = []
    empty_part = []

    for r in records:
        ac = val(r, "AC No")
        part = val(r, "Part No")
        ac_values[ac] += 1
        part_values[part] += 1
        if ac == "":
            empty_ac.append(r)
        if part == "":
            empty_part.append(r)

    print("AC No values found:")
    for ac, count in sorted(ac_values.items(), key=lambda x: -x[1]):
        display = repr(ac) if ac == "" else ac
        print(f"  {display:<20} {count:>6} records")

    print()
    print("Part No values found:")
    for part, count in sorted(part_values.items(), key=lambda x: -x[1]):
        display = repr(part) if part == "" else part
        print(f"  {display:<20} {count:>6} records")

    print()
    if not empty_ac:
        print("AC No: All records have a value.")
    else:
        print(f"EMPTY AC No: {len(empty_ac)} records")
        for r in empty_ac:
            print(f"  Serial {val(r, 'Serial No')} in {r.get('_filename','')}")

    if not empty_part:
        print("Part No: All records have a value.")
    else:
        print(f"EMPTY Part No: {len(empty_part)} records")
        for r in empty_part:
            print(f"  Serial {val(r, 'Serial No')} in {r.get('_filename','')}")

    if len(ac_values) == 1 and "" not in ac_values:
        print("AC No is CONSISTENT across all records.")
    else:
        print(f"AC No has {len(ac_values)} distinct value(s) — may be inconsistent.")

    if len(part_values) == 1 and "" not in part_values:
        print("Part No is CONSISTENT across all records.")
    elif len(part_values) <= 10:
        print(f"Part No has {len(part_values)} distinct value(s) — see distribution above.")
    else:
        print(f"Part No has {len(part_values)} distinct value(s) — highly variable.")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    sep("SUMMARY OF ALL ISSUES")

    print(f"Total files analyzed      : {total_files}")
    print(f"Total records analyzed    : {total_records}")
    print(f"Empty files (0 records)   : {sum(1 for c in file_stats.values() if c == 0)}")
    print()
    print(f"EPIC ID issues            : {len(epic_issues)}")
    print(f"Name (English) issues     : {len(name_eng_issues)}")
    print(f"Relation Name (EN) issues : {len(rel_eng_issues)}")
    print(f"Relation Type issues      : {len(rel_type_issues)}")
    print(f"Age issues                : {len(age_issues)}")
    print(f"Gender issues             : {len(gender_issues)}")
    print(f"House No empty            : {len(house_empty)}")
    print(f"House No suspicious       : {len(house_suspicious)}")
    print(f"Serial No issues          : {len(all_serial_issues)}")
    print(f"Name (Tamil) empty        : {len(tamil_name_empty)}")
    print(f"Name (Tamil) ASCII mix    : {len(tamil_name_ascii)}")
    print(f"Rel Name (Tamil) empty    : {len(tamil_relname_empty)}")
    print(f"Rel Name (Tamil) ASCII    : {len(tamil_relname_ascii)}")
    print(f"Artifact/noise issues     : {len(artifact_issues)}")
    print()

    total_issues = (len(epic_issues) + len(name_eng_issues) + len(rel_eng_issues) +
                    len(rel_type_issues) + len(age_issues) + len(gender_issues) +
                    len(house_empty) + len(house_suspicious) + len(all_serial_issues) +
                    len(tamil_name_empty) + len(tamil_name_ascii) +
                    len(tamil_relname_empty) + len(tamil_relname_ascii) +
                    len(artifact_issues))
    print(f"TOTAL ISSUES ACROSS ALL CATEGORIES: {total_issues}")

if __name__ == "__main__":
    main()
