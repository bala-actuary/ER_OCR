#!/usr/bin/env python3
"""
Split Electoral Roll PDFs into individual page files.

Reads original multi-page PDFs from Input/ER_Downloads/AC-xxx/{english,tamil}/
and splits them into single-page PDFs in Input/split_files/AC-xxx/{english,tamil}/.

English PDFs: first 2 pages (metadata) are skipped.
Tamil PDFs:   first 3 pages (metadata) are skipped.

Usage:
    python split_pdfs.py                    # Interactive prompt for AC number
    python split_pdfs.py --ac AC-188        # Direct AC specification
    python split_pdfs.py --ac AC-188 --force  # Overwrite existing split files
"""

import argparse
import glob
import os
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

SCRIPT_DIR = Path(__file__).parent
DOWNLOADS_DIR = SCRIPT_DIR / "Input" / "ER_Downloads"
SPLIT_DIR = SCRIPT_DIR / "Input" / "split_files"

# Pages to skip (0-based index): English skips first 2, Tamil skips first 3
SKIP_PAGES = {
    "english": 2,
    "tamil": 3,
}


def list_available_acs() -> list[str]:
    """List AC directories available in ER_Downloads."""
    if not DOWNLOADS_DIR.exists():
        return []
    return sorted(
        d.name for d in DOWNLOADS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("AC-")
    )


def split_pdfs_for_language(input_folder: Path, output_folder: Path, skip_pages: int,
                            language: str, force: bool = False) -> dict:
    """Split all PDFs in input_folder into individual pages.

    Returns dict with stats: {total_files, total_pages, skipped_existing, errors}.
    """
    stats = {"total_files": 0, "total_pages": 0, "skipped_existing": 0, "errors": 0}

    pdf_files = sorted(glob.glob(str(input_folder / "**" / "*.pdf"), recursive=True))
    if not pdf_files:
        print(f"  No PDF files found in {input_folder}")
        return stats

    output_folder.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdf_files:
        stats["total_files"] += 1
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]

        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            if total_pages <= skip_pages:
                print(f"  WARNING: {os.path.basename(pdf_path)} has only {total_pages} page(s), "
                      f"need >{skip_pages} — skipping")
                continue

            for page_idx in range(skip_pages, total_pages):
                original_page_num = page_idx + 1
                out_filename = f"{base_name}_page_{original_page_num}.pdf"
                out_path = output_folder / out_filename

                if out_path.exists() and not force:
                    stats["skipped_existing"] += 1
                    continue

                writer = PdfWriter()
                writer.add_page(reader.pages[page_idx])
                with open(out_path, "wb") as f:
                    writer.write(f)

                stats["total_pages"] += 1

        except Exception as e:
            print(f"  ERROR processing {os.path.basename(pdf_path)}: {e}")
            stats["errors"] += 1

    return stats


def prompt_ac_number() -> str:
    """Interactively prompt the user for an AC number."""
    available = list_available_acs()
    if available:
        print(f"\nAvailable ACs in {DOWNLOADS_DIR}:")
        for ac in available:
            print(f"  {ac}")
        print()

    ac = input("Please enter the Assembly Constituency No in AC-xxx format, example AC-188: ").strip()
    return ac


def validate_ac(ac_name: str) -> Path:
    """Validate AC directory exists and has english/tamil subdirs. Returns AC path."""
    if not ac_name.startswith("AC-"):
        print(f"ERROR: '{ac_name}' is not in AC-xxx format (e.g., AC-188)")
        sys.exit(1)

    ac_path = DOWNLOADS_DIR / ac_name
    if not ac_path.exists():
        available = list_available_acs()
        print(f"ERROR: Directory not found: {ac_path}")
        print(f"\nPlease create your input folder at: {DOWNLOADS_DIR / 'AC-xxx'}")
        print("Place English PDFs in the 'english' subfolder and Tamil PDFs in the 'tamil' subfolder.")
        if available:
            print(f"\nExisting AC directories: {', '.join(available)}")
        sys.exit(1)

    for lang in ("english", "tamil"):
        lang_path = ac_path / lang
        if not lang_path.exists():
            print(f"ERROR: Missing '{lang}' subfolder in {ac_path}")
            print(f"Expected: {lang_path}")
            sys.exit(1)

    return ac_path


def main():
    parser = argparse.ArgumentParser(
        description="Split Electoral Roll PDFs into individual page files."
    )
    parser.add_argument("--ac", type=str, default=None,
                        help="Assembly Constituency in AC-xxx format (e.g., AC-188)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing split files")
    args = parser.parse_args()

    # Get AC number
    ac_name = args.ac if args.ac else prompt_ac_number()
    ac_path = validate_ac(ac_name)

    # Output directory
    output_base = SPLIT_DIR / ac_name
    print(f"\n{'='*60}")
    print(f"Splitting PDFs for {ac_name}")
    print(f"  Source:  {ac_path}")
    print(f"  Output:  {output_base}")
    if args.force:
        print(f"  Mode:    FORCE (overwriting existing files)")
    print(f"{'='*60}\n")

    grand_total_files = 0
    grand_total_pages = 0

    for language, skip_count in SKIP_PAGES.items():
        input_folder = ac_path / language
        output_folder = output_base / language

        pdf_count = len(glob.glob(str(input_folder / "**" / "*.pdf"), recursive=True))
        print(f"[{language.upper()}] Found {pdf_count} PDF(s), skipping first {skip_count} page(s) each...")

        stats = split_pdfs_for_language(
            input_folder, output_folder, skip_count, language, force=args.force
        )

        grand_total_files += stats["total_files"]
        grand_total_pages += stats["total_pages"]

        print(f"  Split {stats['total_files']} file(s) -> {stats['total_pages']} page(s)")
        if stats["skipped_existing"] > 0:
            print(f"  Skipped {stats['skipped_existing']} existing file(s) (use --force to overwrite)")
        if stats["errors"] > 0:
            print(f"  {stats['errors']} error(s) encountered")
        print()

    print(f"{'='*60}")
    print(f"Done! Total: {grand_total_files} PDF(s) -> {grand_total_pages} page(s)")
    print(f"Split files saved to: {output_base}")
    print(f"\nNext step: python extract_ocr.py {ac_name} --workers 4")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
