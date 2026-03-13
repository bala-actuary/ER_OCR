#!/bin/bash
# Check OCR extraction progress across all AC directories
# Run from anywhere: bash /path/to/check-progress.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W 2>/dev/null || pwd)"
INPUT_DIR="$SCRIPT_DIR/Input/split_files"
OUTPUT_DIR="$SCRIPT_DIR/output/split_files"

echo "============================================"
echo "  OCR Extraction Progress"
echo "  $(date)"
echo "============================================"
echo ""

printf "%-30s %8s %8s %8s %8s\n" "Directory" "Total" "Done" "Pending" "Records"
printf "%-30s %8s %8s %8s %8s\n" "------------------------------" "--------" "--------" "--------" "--------"

total_pairs=0
total_done=0
total_records=0

# Dynamically discover all AC-* directories
for dir_path in "$INPUT_DIR"/AC-*; do
    [ -d "$dir_path" ] || continue
    dir_name=$(basename "$dir_path")

    # Count English PDFs (total pairs)
    input_eng="$dir_path/english"
    if [ -d "$input_eng" ]; then
        pairs=$(ls "$input_eng"/*.pdf 2>/dev/null | wc -l)
    else
        pairs=0
    fi

    # Count processed from checkpoint (new location: inside split_files dir)
    cp_file="$dir_path/checkpoint.json"
    # Fallback to legacy location
    if [ ! -f "$cp_file" ]; then
        cp_file="$SCRIPT_DIR/checkpoints/${dir_name}.json"
    fi
    if [ -f "$cp_file" ]; then
        done=$(python -c "import json; print(len(json.load(open('$cp_file')).get('processed', [])))" 2>/dev/null || echo 0)
    else
        done=0
    fi

    pending=$((pairs - done))

    # Count records in output CSVs
    out_dir="$OUTPUT_DIR/$dir_name"
    # Fallback to legacy output location
    if [ ! -d "$out_dir" ]; then
        out_dir="$SCRIPT_DIR/output/$dir_name"
    fi
    if [ -d "$out_dir" ]; then
        records=$(cat "$out_dir"/*.csv 2>/dev/null | wc -l)
        records=$((records > 0 ? records - $(ls "$out_dir"/*.csv 2>/dev/null | wc -l) : 0))
    else
        records=0
    fi

    printf "%-30s %8d %8d %8d %8d\n" "$dir_name" "$pairs" "$done" "$pending" "$records"

    total_pairs=$((total_pairs + pairs))
    total_done=$((total_done + done))
    total_records=$((total_records + records))
done

printf "%-30s %8s %8s %8s %8s\n" "------------------------------" "--------" "--------" "--------" "--------"
printf "%-30s %8d %8d %8d %8d\n" "TOTAL" "$total_pairs" "$total_done" "$((total_pairs - total_done))" "$total_records"
echo ""
