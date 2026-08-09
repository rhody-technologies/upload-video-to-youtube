#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Batch YouTube uploader
# Uploads every video file in VIDEOS_DIR to YouTube.
# Title    = filename (without extension)
# Desc     = "voice memos - 7/26/2026"
# Playlist = optional, set PLAYLIST_ID below
# ─────────────────────────────────────────────────────────────

VIDEOS_DIR="/Users/kd/Desktop/voice-memos/Videos"
UPLOADER="$(dirname "$0")/main.py"
DESCRIPTION="voice memos - 7/26/2026"
PLAYLIST_ID="PL7Sw76q6oLI9vsIz9-XIgMMC488OzBWhN"
PRIVACY="private"
CATEGORY="25"

# Video file extensions to match
EXTENSIONS=("mp4" "mov" "avi" "mkv" "m4v" "wmv" "flv" "webm")

# ─────────────────────────────────────────────────────────────

# Build the find command to match all supported extensions
FIND_ARGS=()
for ext in "${EXTENSIONS[@]}"; do
    FIND_ARGS+=(-o -iname "*.${ext}")
done
# Remove leading -o
FIND_ARGS=("${FIND_ARGS[@]:1}")

# Collect matching files into an array (bash 3.2 compatible)
FILES=()
while IFS= read -r -d '' file; do
    FILES+=("$file")
done < <(find "$VIDEOS_DIR" -maxdepth 1 \( "${FIND_ARGS[@]}" \) -print0 | sort -z)

TOTAL=${#FILES[@]}

if [[ $TOTAL -eq 0 ]]; then
    echo "No video files found in: $VIDEOS_DIR"
    exit 1
fi

echo "Found $TOTAL video(s) to upload."
echo "────────────────────────────────────────"

SUCCESS=0
FAILED=()

for FILE in "${FILES[@]}"; do
    # Extract filename without extension as title
    BASENAME=$(basename "$FILE")
    TITLE="${BASENAME%.*}"

    echo ""
    echo "[$((SUCCESS + ${#FAILED[@]} + 1))/$TOTAL] $BASENAME"
    echo "  Title: $TITLE"

    python3 "$UPLOADER" "$FILE" \
        --title       "$TITLE" \
        --description "$DESCRIPTION" \
        --category    "$CATEGORY" \
        --privacy     "$PRIVACY" \
        --playlist    "$PLAYLIST_ID"

    if [[ $? -eq 0 ]]; then
        SUCCESS=$((SUCCESS + 1))
    else
        echo "  [WARN] Upload failed for: $BASENAME"
        FAILED+=("$BASENAME")
    fi

    echo "────────────────────────────────────────"
done

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "Upload complete: $SUCCESS/$TOTAL succeeded"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Failed uploads:"
    for f in "${FAILED[@]}"; do
        echo "  ✗ $f"
    done
    exit 1
fi