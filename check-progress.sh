#!/bin/bash
# Check OCR extraction progress across all batch directories
# Run from anywhere: bash /path/to/ocr/check-progress.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKPOINT_DIR="$SCRIPT_DIR/checkpoints"
OUTPUT_DIR="$SCRIPT_DIR/output"

echo "============================================"
echo "  OCR Extraction Progress"
echo "  $(date)"
echo "============================================"
echo ""

printf "%-25s %8s %8s %8s %8s\n" "Directory" "Total" "Done" "Pending" "Records"
printf "%-25s %8s %8s %8s %8s\n" "-------------------------" "--------" "--------" "--------" "--------"

total_pairs=0
total_done=0
total_records=0

for dir_name in AC-184-Part-1-50 AC-184-Part-51-100 AC-184-Part-101-150 AC-184-Part-151-200 AC-184-Part-201-250 AC-184-Part-251-300 AC-184-Part-301-350 AC-184-Part-351-400; do
    # Count English PDFs (total pairs)
    input_dir="$SCRIPT_DIR/Input/split_files/$dir_name/english"
    if [ -d "$input_dir" ]; then
        pairs=$(ls "$input_dir"/*.pdf 2>/dev/null | wc -l)
    else
        pairs=0
    fi

    # Count processed from checkpoint
    cp_file="$CHECKPOINT_DIR/${dir_name}.json"
    if [ -f "$cp_file" ]; then
        done=$(python -c "import json; print(len(json.load(open('$cp_file')).get('processed', [])))" 2>/dev/null || echo 0)
    else
        done=0
    fi

    pending=$((pairs - done))

    # Count records in output CSVs
    out_dir="$OUTPUT_DIR/$dir_name"
    if [ -d "$out_dir" ]; then
        records=$(cat "$out_dir"/*.csv 2>/dev/null | wc -l)
        records=$((records > 0 ? records - $(ls "$out_dir"/*.csv 2>/dev/null | wc -l) : 0))
    else
        records=0
    fi

    printf "%-25s %8d %8d %8d %8d\n" "$dir_name" "$pairs" "$done" "$pending" "$records"

    total_pairs=$((total_pairs + pairs))
    total_done=$((total_done + done))
    total_records=$((total_records + records))
done

printf "%-25s %8s %8s %8s %8s\n" "-------------------------" "--------" "--------" "--------" "--------"
printf "%-25s %8d %8d %8d %8d\n" "TOTAL" "$total_pairs" "$total_done" "$((total_pairs - total_done))" "$total_records"
echo ""
