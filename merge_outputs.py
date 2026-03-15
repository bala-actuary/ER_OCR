#!/usr/bin/env python3
"""
Merge page-level CSV outputs into part-level and AC-level CSV files.

Reads page-level CSVs from output/split_files/AC-xxx/ and produces:
  1. Part-level CSVs in output/merged_files/parts/AC-xxx/ (one per original PDF part)
  2. AC-level CSV in output/merged_files/ac/AC-xxx.csv (single file for entire constituency)

Example:
    Page CSVs:
        2026-EROLLGEN-S22-184-SIR-FinalRoll-Revision1-ENG-1-WI_page_3.csv
        ...

    Part-level output:
        output/merged_files/parts/AC-188/2026-EROLLGEN-...-ENG-1-WI.csv

    AC-level output:
        output/merged_files/ac/AC-188.csv

Usage:
    python merge_outputs.py                     # Interactive prompt
    python merge_outputs.py --ac AC-188         # Direct AC specification
    python merge_outputs.py --ac AC-188 --force # Re-merge even if already done
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SPLIT_OUTPUT_DIR = SCRIPT_DIR / "output" / "split_files"
MERGED_OUTPUT_DIR = SCRIPT_DIR / "output" / "merged_files" / "parts"
AC_MERGED_DIR = SCRIPT_DIR / "output" / "merged_files" / "ac"

# Regex to extract the _page_NN suffix from CSV filenames
PAGE_SUFFIX_RE = re.compile(r"_page_(\d+)\.csv$")


def list_available_acs() -> list[str]:
    """List AC directories that have split output CSVs."""
    if not SPLIT_OUTPUT_DIR.exists():
        return []
    return sorted(
        d.name for d in SPLIT_OUTPUT_DIR.iterdir()
        if d.is_dir() and d.name.startswith("AC-")
    )


def group_by_part(csv_dir: Path) -> dict[str, list[tuple[int, Path]]]:
    """Group page CSVs by their parent part file.

    Returns dict mapping base_name -> list of (page_no, file_path) tuples, sorted by page_no.
    """
    groups = defaultdict(list)

    for csv_file in sorted(csv_dir.glob("*.csv")):
        match = PAGE_SUFFIX_RE.search(csv_file.name)
        if not match:
            continue
        page_no = int(match.group(1))
        base_name = PAGE_SUFFIX_RE.sub("", csv_file.name)
        groups[base_name].append((page_no, csv_file))

    # Sort each group by page number
    for base_name in groups:
        groups[base_name].sort(key=lambda x: x[0])

    return dict(groups)


def merge_part_csvs(pages: list[tuple[int, Path]], output_path: Path) -> int:
    """Merge multiple page CSVs into a single part CSV.

    Returns the number of data records written.
    """
    all_rows = []
    header = None

    for page_no, csv_path in pages:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                continue
            if header is None:
                header = rows[0]
            # Skip header row, collect data rows
            data_rows = rows[1:]
            all_rows.extend(data_rows)

    if header is None:
        return 0

    # Sort by Serial No (column index 2) -- numeric sort
    def serial_key(row):
        try:
            return int(row[2]) if len(row) > 2 and row[2].strip() else 999999
        except ValueError:
            return 999999

    all_rows.sort(key=serial_key)

    # Write merged CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)

    return len(all_rows)


def load_merge_checkpoint(ac_dir: Path) -> dict:
    """Load merge checkpoint."""
    cp_path = ac_dir / "merge_checkpoint.json"
    if cp_path.exists():
        try:
            with open(cp_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"  WARNING: Corrupt checkpoint at {cp_path}, starting fresh")
    return {"merged_parts": [], "total_records": 0}


def save_merge_checkpoint(ac_dir: Path, data: dict):
    """Save merge checkpoint."""
    cp_path = ac_dir / "merge_checkpoint.json"
    ac_dir.mkdir(parents=True, exist_ok=True)
    with open(cp_path, "w") as f:
        json.dump(data, f, indent=2)


def merge_ac_csv(ac_name: str, merged_dir: Path) -> int:
    """Merge all part-level CSVs into a single AC-level CSV.

    Reads all part CSVs from merged_dir, concatenates and sorts by Part No then Serial No.
    Returns the total number of data records written.
    """
    part_csvs = sorted(f for f in merged_dir.glob("*.csv") if f.name != "merge_checkpoint.json")
    if not part_csvs:
        return 0

    all_rows = []
    header = None

    for csv_path in part_csvs:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                continue
            if header is None:
                header = rows[0]
            all_rows.extend(rows[1:])

    if header is None:
        return 0

    # Sort by Part No (column 1) then Serial No (column 2) -- both numeric
    def ac_sort_key(row):
        try:
            part = int(row[1]) if len(row) > 1 and row[1].strip() else 999999
        except ValueError:
            part = 999999
        try:
            serial = int(row[2]) if len(row) > 2 and row[2].strip() else 999999
        except ValueError:
            serial = 999999
        return (part, serial)

    all_rows.sort(key=ac_sort_key)

    # Write AC-level CSV
    ac_output_path = AC_MERGED_DIR / f"{ac_name}.csv"
    ac_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ac_output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)

    return len(all_rows)


def prompt_ac_number() -> str:
    """Interactively prompt the user for an AC number."""
    available = list_available_acs()
    if available:
        print(f"\nAvailable ACs with split output in {SPLIT_OUTPUT_DIR}:")
        for ac in available:
            csv_count = len(list((SPLIT_OUTPUT_DIR / ac).glob("*.csv")))
            print(f"  {ac} ({csv_count} page CSVs)")
        print()
    else:
        print(f"\nNo AC directories found in {SPLIT_OUTPUT_DIR}")
        print("Run extract_ocr.py first to generate page-level CSVs.")
        sys.exit(1)

    ac = input("Please tell me which AC split files you want to merge in AC-xxx format, example AC-188: ").strip()
    return ac


def main():
    parser = argparse.ArgumentParser(
        description="Merge page-level CSV outputs into part-level CSV files."
    )
    parser.add_argument("--ac", type=str, default=None,
                        help="Assembly Constituency in AC-xxx format (e.g., AC-188)")
    parser.add_argument("--force", action="store_true",
                        help="Re-merge even if checkpoint indicates already done")
    args = parser.parse_args()

    # Get AC number
    ac_name = args.ac if args.ac else prompt_ac_number()

    if not ac_name.startswith("AC-"):
        print(f"ERROR: '{ac_name}' is not in AC-xxx format (e.g., AC-188)")
        sys.exit(1)

    split_dir = SPLIT_OUTPUT_DIR / ac_name
    if not split_dir.exists():
        available = list_available_acs()
        print(f"ERROR: No split output found at {split_dir}")
        if available:
            print(f"Available: {', '.join(available)}")
        sys.exit(1)

    merged_dir = MERGED_OUTPUT_DIR / ac_name

    print(f"\n{'='*60}")
    print(f"Merging page CSVs for {ac_name}")
    print(f"  Source:  {split_dir}")
    print(f"  Output:  {merged_dir}")
    print(f"{'='*60}\n")

    # Group page CSVs by part
    groups = group_by_part(split_dir)
    if not groups:
        print("No page-level CSVs found to merge.")
        sys.exit(0)

    # Load checkpoint
    if args.force:
        checkpoint = {"merged_parts": [], "total_records": 0}
    else:
        checkpoint = load_merge_checkpoint(merged_dir)
    merged_set = set(checkpoint.get("merged_parts", []))
    grand_total_records = checkpoint.get("total_records", 0)

    total_parts = len(groups)
    merged_count = 0
    skipped_count = 0

    for base_name, pages in sorted(groups.items()):
        if base_name in merged_set and not args.force:
            skipped_count += 1
            continue

        output_path = merged_dir / f"{base_name}.csv"
        record_count = merge_part_csvs(pages, output_path)
        grand_total_records += record_count
        merged_count += 1

        print(f"  {base_name}.csv -- {len(pages)} pages, {record_count} records")

        # Update checkpoint
        merged_set.add(base_name)
        checkpoint["merged_parts"] = sorted(merged_set)
        checkpoint["total_records"] = grand_total_records
        checkpoint["last_merged"] = datetime.now().isoformat()
        save_merge_checkpoint(merged_dir, checkpoint)

    # AC-level merge: combine all part CSVs into a single AC file
    ac_record_count = merge_ac_csv(ac_name, merged_dir)
    ac_output_path = AC_MERGED_DIR / f"{ac_name}.csv"

    print(f"\n{'='*60}")
    print(f"Done! Merged {merged_count} part(s) from {total_parts} total")
    if skipped_count > 0:
        print(f"  Skipped {skipped_count} already-merged part(s) (use --force to re-merge)")
    print(f"  Total records: {grand_total_records}")
    print(f"  Part-level files: {merged_dir}")
    print(f"  AC-level file:    {ac_output_path} ({ac_record_count} records)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
