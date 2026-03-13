import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict

# Force UTF-8 stdout to handle Tamil characters on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))


def discover_output_dirs(ac_filter=None):
    """Dynamically discover output directories.

    Checks output/split_files/ first (new layout), then output/ (legacy layout).
    If ac_filter is provided, only return dirs matching that AC.
    """
    dirs = []

    # New layout: output/split_files/AC-xxx/
    new_base = os.path.join(BASE, "output", "split_files")
    if os.path.isdir(new_base):
        for d in sorted(os.listdir(new_base)):
            full = os.path.join(new_base, d)
            if os.path.isdir(full) and d.startswith("AC-"):
                if ac_filter is None or d == ac_filter:
                    dirs.append(full)

    # Legacy layout: output/AC-184-Part-xxx/
    legacy_base = os.path.join(BASE, "output")
    if os.path.isdir(legacy_base):
        for d in sorted(os.listdir(legacy_base)):
            full = os.path.join(legacy_base, d)
            if os.path.isdir(full) and d.startswith("AC-") and full not in dirs:
                if d == "split_files" or d == "merged":
                    continue
                if ac_filter is None or d.startswith(ac_filter):
                    dirs.append(full)

    return dirs


DIRS = discover_output_dirs()  # default: all available

ACTIVE_FIELDS = [
    "AC No", "Part No", "Serial No", "EPIC ID",
    "Name (English)", "Name (Tamil)",
    "Relation Name (English)", "Relation Name (Tamil)",
    "Relation Type", "House No", "Age", "Gender"
]

EPIC_PATTERN = re.compile(r'^[A-Z]{3}\d{7}$')
ASCII_PRINTABLE = re.compile(r'[A-Za-z0-9!@#$%^&*()+={};:\'",.<>/?\\|`~-]')

def has_ascii_contamination(val):
    if not val:
        return False
    ascii_chars = len(ASCII_PRINTABLE.findall(val))
    return ascii_chars > 0


def analyze_directory(dirpath):
    csvfiles = sorted(glob.glob(os.path.join(dirpath, "*.csv")))
    total_files = len(csvfiles)
    total_records = 0

    field_filled = defaultdict(int)
    field_total = defaultdict(int)

    issues = {
        "epic_empty": 0,
        "epic_malformed": 0,
        "name_en_empty": 0,
        "name_ta_empty": 0,
        "rel_name_ta_empty": 0,
        "rel_name_en_empty": 0,
        "age_empty": 0,
        "gender_empty": 0,
        "house_empty": 0,
        "tamil_name_ascii_contamination": 0,
        "tamil_rel_ascii_contamination": 0,
    }

    ac_values = set()
    part_values = set()
    relation_type_values = set()
    gender_values = set()
    age_values_weird = []
    epic_samples_malformed = []

    for fpath in csvfiles:
        with open(fpath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in rows:
            total_records += 1

            for field in ACTIVE_FIELDS:
                val = row.get(field, "").strip()
                field_total[field] += 1
                if val:
                    field_filled[field] += 1

            epic = row.get("EPIC ID", "").strip()
            if not epic:
                issues["epic_empty"] += 1
            elif not EPIC_PATTERN.match(epic):
                issues["epic_malformed"] += 1
                if len(epic_samples_malformed) < 10:
                    epic_samples_malformed.append(epic)

            name_en = row.get("Name (English)", "").strip()
            if not name_en:
                issues["name_en_empty"] += 1

            name_ta = row.get("Name (Tamil)", "").strip()
            if not name_ta:
                issues["name_ta_empty"] += 1
            elif has_ascii_contamination(name_ta):
                issues["tamil_name_ascii_contamination"] += 1

            rel_name_ta = row.get("Relation Name (Tamil)", "").strip()
            if not rel_name_ta:
                issues["rel_name_ta_empty"] += 1
            elif has_ascii_contamination(rel_name_ta):
                issues["tamil_rel_ascii_contamination"] += 1

            rel_name_en = row.get("Relation Name (English)", "").strip()
            if not rel_name_en:
                issues["rel_name_en_empty"] += 1

            age = row.get("Age", "").strip()
            if not age:
                issues["age_empty"] += 1
            else:
                try:
                    age_int = int(age)
                    if age_int < 18 or age_int > 120:
                        age_values_weird.append(age_int)
                except ValueError:
                    age_values_weird.append(age)

            gender = row.get("Gender", "").strip()
            if not gender:
                issues["gender_empty"] += 1
            gender_values.add(gender)

            house = row.get("House No", "").strip()
            if not house:
                issues["house_empty"] += 1

            ac_values.add(row.get("AC No", "").strip())
            part_values.add(row.get("Part No", "").strip())
            relation_type_values.add(row.get("Relation Type", "").strip())

    total_cells = sum(field_total[f] for f in ACTIVE_FIELDS)
    filled_cells = sum(field_filled[f] for f in ACTIVE_FIELDS)
    overall_accuracy = filled_cells / total_cells * 100 if total_cells else 0

    return {
        "dirpath": dirpath,
        "total_files": total_files,
        "total_records": total_records,
        "field_filled": dict(field_filled),
        "field_total": dict(field_total),
        "issues": issues,
        "overall_accuracy": overall_accuracy,
        "filled_cells": filled_cells,
        "total_cells": total_cells,
        "ac_values": ac_values,
        "part_values": part_values,
        "relation_type_values": relation_type_values,
        "gender_values": gender_values,
        "age_values_weird": age_values_weird,
        "epic_samples_malformed": epic_samples_malformed,
    }


def print_dir_report(result):
    d = result["dirpath"]
    print()
    print("=" * 70)
    print(f"DIRECTORY: {os.path.basename(d)}")
    print("=" * 70)
    print(f"CSV files    : {result['total_files']}")
    print(f"Total records: {result['total_records']}")
    print()

    print("Per-field fill rates:")
    print(f"  {'Field':<32} {'Filled':>8} {'Total':>8} {'Rate':>8}")
    print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*8}")
    for f in ACTIVE_FIELDS:
        filled = result["field_filled"].get(f, 0)
        total = result["field_total"].get(f, 0)
        rate = filled / total * 100 if total else 0
        flag = " <--" if rate < 80 else ""
        print(f"  {f:<32} {filled:>8} {total:>8} {rate:>7.1f}%{flag}")

    print()
    print(f"Overall accuracy: {result['filled_cells']}/{result['total_cells']} = {result['overall_accuracy']:.2f}%")

    core_fields = ["EPIC ID", "Name (English)", "Name (Tamil)", "Age", "Gender"]
    core_filled = sum(result["field_filled"].get(f, 0) for f in core_fields)
    core_total = sum(result["field_total"].get(f, 0) for f in core_fields)
    core_acc = core_filled / core_total * 100 if core_total else 0
    print(f"Core fields accuracy (EPIC+Names+Age+Gender): {core_filled}/{core_total} = {core_acc:.2f}%")

    print()
    print("Issues:")
    for k, v in result["issues"].items():
        pct = v / result["total_records"] * 100 if result["total_records"] else 0
        print(f"  {k:<42} {v:>6}  ({pct:.1f}%)")

    print()
    print(f"  Gender values seen     : {sorted(result['gender_values'])}")
    print(f"  Relation types seen    : {sorted(result['relation_type_values'])}")
    print(f"  AC No values seen      : {sorted(result['ac_values'])}")
    print(f"  Part No values (sample): {sorted(list(result['part_values']))[:15]}")
    if result["age_values_weird"]:
        print(f"  Weird age values       : {result['age_values_weird'][:20]}")
    if result["epic_samples_malformed"]:
        print(f"  Malformed EPIC samples : {result['epic_samples_malformed']}")


def count_all_complete(dirpath):
    csvfiles = sorted(glob.glob(os.path.join(dirpath, "*.csv")))
    complete = 0
    total = 0
    for fpath in csvfiles:
        with open(fpath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                if all(row.get(f, "").strip() for f in ACTIVE_FIELDS):
                    complete += 1
    return complete, total


def deep_anomaly_scan(dirs):
    anomalies = defaultdict(list)
    known_prefixes = {"RVJ", "MDJ", "IOD", "JOD"}

    for d in dirs:
        csvfiles = sorted(glob.glob(os.path.join(d, "*.csv")))
        for fpath in csvfiles:
            with open(fpath, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            for i, row in enumerate(rows):
                serial = row.get("Serial No", "").strip()
                epic = row.get("EPIC ID", "").strip()
                name_en = row.get("Name (English)", "").strip()
                name_ta = row.get("Name (Tamil)", "").strip()
                rel_ta = row.get("Relation Name (Tamil)", "").strip()
                rel_en = row.get("Relation Name (English)", "").strip()
                age = row.get("Age", "").strip()
                gender = row.get("Gender", "").strip()
                house = row.get("House No", "").strip()
                part = row.get("Part No", "").strip()
                ac = row.get("AC No", "").strip()
                rel_type = row.get("Relation Type", "").strip()

                fname = os.path.basename(fpath)
                ctx = f"{fname} row {i+1}"

                if gender and gender not in ("Male", "Female"):
                    anomalies["unexpected_gender"].append(f"{ctx}: '{gender}'")

                valid_rel_types = {"S/O", "D/O", "W/O", "H/O", "O/O", "C/O"}
                if rel_type and rel_type not in valid_rel_types:
                    anomalies["unexpected_relation_type"].append(f"{ctx}: '{rel_type}'")

                if serial and not serial.isdigit():
                    anomalies["serial_not_numeric"].append(f"{ctx}: '{serial}'")

                if age:
                    try:
                        a = int(age)
                        if a < 18 or a > 120:
                            anomalies["age_out_of_range"].append(f"{ctx}: {a}")
                    except ValueError:
                        anomalies["age_non_numeric"].append(f"{ctx}: '{age}'")

                if house == "'":
                    anomalies["house_only_apostrophe"].append(ctx)

                if name_en and not all(ord(c) < 128 for c in name_en):
                    anomalies["english_name_non_ascii"].append(f"{ctx}: '{name_en[:40]}'")

                if rel_en and not all(ord(c) < 128 for c in rel_en):
                    anomalies["rel_name_en_non_ascii"].append(f"{ctx}: '{rel_en[:40]}'")

                if epic and EPIC_PATTERN.match(epic) and epic[:3] not in known_prefixes:
                    anomalies["epic_unknown_prefix"].append(f"{ctx}: '{epic}'")

                if part and not part.isdigit():
                    anomalies["part_not_numeric"].append(f"{ctx}: '{part}'")

                if ac and not ac.isdigit():
                    anomalies["ac_not_numeric"].append(f"{ctx}: '{ac}'")

                if name_ta and all(ord(c) < 128 for c in name_ta):
                    anomalies["tamil_name_all_ascii"].append(f"{ctx}: '{name_ta[:40]}'")

                if rel_ta and all(ord(c) < 128 for c in rel_ta):
                    anomalies["tamil_rel_all_ascii"].append(f"{ctx}: '{rel_ta[:40]}'")

                if name_en and len(name_en) <= 2:
                    anomalies["english_name_very_short"].append(f"{ctx}: '{name_en}'")

                if name_ta and len(name_ta) <= 3:
                    anomalies["tamil_name_very_short"].append(f"{ctx}: '{name_ta}'")

                if house and len(house.lstrip("'")) > 20:
                    anomalies["house_very_long"].append(f"{ctx}: '{house[:40]}'")

                # Check for digit-only English names (OCR misread)
                if name_en and name_en.replace(" ", "").isdigit():
                    anomalies["english_name_digits_only"].append(f"{ctx}: '{name_en}'")

                # Check for English name that looks like an EPIC ID
                if name_en and EPIC_PATTERN.match(name_en.replace(" ", "")):
                    anomalies["english_name_looks_like_epic"].append(f"{ctx}: '{name_en}'")

                # House No that is only digits > 4 chars (could be serial leaked in)
                raw_house = house.lstrip("'")
                if raw_house and raw_house.isdigit() and len(raw_house) > 4:
                    anomalies["house_number_suspiciously_large"].append(f"{ctx}: '{house}'")

                # Part No out of expected range (1-350)
                if part and part.isdigit():
                    p = int(part)
                    if p < 1 or p > 400:
                        anomalies["part_out_of_range"].append(f"{ctx}: {p}")

    return anomalies


# ---- MAIN ----

def main():
    parser = argparse.ArgumentParser(description="Analyze CSV output quality")
    parser.add_argument("--ac", type=str, default=None,
                        help="Analyze specific AC (e.g., AC-188)")
    args = parser.parse_args()

    global DIRS
    if args.ac:
        DIRS = discover_output_dirs(ac_filter=args.ac)
    if not DIRS:
        print("No output directories found to analyze.")
        sys.exit(1)

    dir_label = args.ac if args.ac else f"All {len(DIRS)} Directories"
    print("=" * 70)
    print(f"CSV OUTPUT QUALITY ANALYSIS -- {dir_label}")
    print("=" * 70)

    results = []
    for d in DIRS:
        r = analyze_directory(d)
        results.append(r)
        print_dir_report(r)

    # Combined summary
    print()
    print()
    print("=" * 70)
    print(f"COMBINED SUMMARY -- {dir_label}")
    print("=" * 70)

    total_files_all = sum(r["total_files"] for r in results)
    total_records_all = sum(r["total_records"] for r in results)
    print(f"Total CSV files : {total_files_all}")
    print(f"Total records   : {total_records_all}")

    agg_filled = defaultdict(int)
    agg_total = defaultdict(int)
    for r in results:
        for f in ACTIVE_FIELDS:
            agg_filled[f] += r["field_filled"].get(f, 0)
            agg_total[f] += r["field_total"].get(f, 0)

    print()
    print("Per-field fill rates (combined):")
    print(f"  {'Field':<32} {'Filled':>8} {'Total':>8} {'Rate':>8}")
    print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*8}")
    for f in ACTIVE_FIELDS:
        filled = agg_filled[f]
        total = agg_total[f]
        rate = filled / total * 100 if total else 0
        flag = " <--" if rate < 80 else ""
        print(f"  {f:<32} {filled:>8} {total:>8} {rate:>7.1f}%{flag}")

    total_cells_all = sum(r["total_cells"] for r in results)
    filled_cells_all = sum(r["filled_cells"] for r in results)
    overall_all = filled_cells_all / total_cells_all * 100 if total_cells_all else 0
    print(f"\nOverall cell-level accuracy (all dirs): {filled_cells_all}/{total_cells_all} = {overall_all:.2f}%")

    core_fields = ["EPIC ID", "Name (English)", "Name (Tamil)", "Age", "Gender"]
    core_filled_all = sum(agg_filled[f] for f in core_fields)
    core_total_all = sum(agg_total[f] for f in core_fields)
    core_acc_all = core_filled_all / core_total_all * 100 if core_total_all else 0
    print(f"Core fields accuracy (EPIC+Names+Age+Gender): {core_filled_all}/{core_total_all} = {core_acc_all:.2f}%")

    print()
    print("Combined issues:")
    issue_keys = list(results[0]["issues"].keys())
    for k in issue_keys:
        total_issue = sum(r["issues"][k] for r in results)
        pct = total_issue / total_records_all * 100 if total_records_all else 0
        print(f"  {k:<42} {total_issue:>6}  ({pct:.1f}%)")

    print()
    print("Records with ALL 12 fields complete:")
    total_complete_all = 0
    for d in DIRS:
        complete, total = count_all_complete(d)
        pct = complete / total * 100 if total else 0
        print(f"  {os.path.basename(d)}: {complete}/{total} = {pct:.1f}%")
        total_complete_all += complete

    pct_all = total_complete_all / total_records_all * 100 if total_records_all else 0
    print(f"\n  TOTAL complete records: {total_complete_all}/{total_records_all} = {pct_all:.1f}%")

    # Anomaly detection
    print()
    print()
    print("=" * 70)
    print("ANOMALY DETECTION -- New / Unexpected Issue Patterns")
    print("=" * 70)

    anomalies = deep_anomaly_scan(DIRS)

    if anomalies:
        print(f"\nFound {len(anomalies)} anomaly categories:\n")
        for atype, instances in sorted(anomalies.items()):
            count = len(instances)
            samples = instances[:5]
            print(f"  [{atype}]  count={count}")
            for s in samples:
                print(f"    {s}")
            if count > 5:
                print(f"    ... and {count - 5} more")
            print()
    else:
        print("  No anomalies detected beyond standard issue categories.")

    print("Done.")


if __name__ == "__main__":
    main()
