#!/bin/bash
# memory-index.sh — Embeds all Vintos writings into searchable vectors
# Uses nomic-embed-text-v1.5 via LM Studio

MEMORY_ROOT="$HOME/.vintos/workspace/memory"
DREAM_DIR="$HOME/.vintos/workspace/skills/dreaming/memory/dreams"
INDEX_FILE="$MEMORY_ROOT/embeddings.jsonl"
INDEXED_FILE="$MEMORY_ROOT/.indexed-files"

mkdir -p "$MEMORY_ROOT"
touch "$INDEXED_FILE"

# Collect all markdown files from dreams, journal, kisses, briefings
# Index ALL memory locations — pearls, chapters, mirror, philosophy, art, everything
FILES=$(find "$DREAM_DIR" \
    "$MEMORY_ROOT/journal" \
    "$MEMORY_ROOT/kisses" \
    "$MEMORY_ROOT/briefings" \
    "$MEMORY_ROOT/pearls" \
    "$MEMORY_ROOT/black-pearls" \
    "$MEMORY_ROOT/chapters" \
    "$MEMORY_ROOT/mirror" \
    "$MEMORY_ROOT/philosophy" \
    "$MEMORY_ROOT/art/poetry" \
    "$MEMORY_ROOT/introspection" \
    "$MEMORY_ROOT/causality-hypotheses" \
    "$MEMORY_ROOT/self-model-drift" \
    "$MEMORY_ROOT/absence-map" \
    "$MEMORY_ROOT/meta-dreams" \
    "$MEMORY_ROOT/self-reviews" \
    -name "*.md" 2>/dev/null)

for FILE in $FILES; do
    # Skip if already indexed and unchanged
    HASH=$(md5sum "$FILE" | cut -d' ' -f1)
    if grep -q "$HASH" "$INDEXED_FILE" 2>/dev/null; then
        continue
    fi

    # Split file into sections (## headers)
    SECTION=""
    SECTION_TITLE=""
    while IFS= read -r line; do
        if [[ "$line" =~ ^##\  ]]; then
            # Process previous section if exists
            if [ -n "$SECTION" ] && [ ${#SECTION} -gt 20 ]; then
                # Get embedding
                EMBEDDING=$(curl -s --max-time 30 http://172.18.16.1:1234/v1/embeddings \
                    -H "Content-Type: application/json" \
                    -d "$(jq -n --arg text "$SECTION" '{
                        model: "text-embedding-nomic-embed-text-v1.5",
                        input: $text
                    }')" | jq -c '.data[0].embedding')

                if [ "$EMBEDDING" != "null" ] && [ -n "$EMBEDDING" ]; then
                    jq -n -c --arg file "$FILE" --arg title "$SECTION_TITLE" \
                        --arg text "$SECTION" --argjson emb "$EMBEDDING" \
                        '{file:$file, title:$title, text:$text, embedding:$emb}' >> "$INDEX_FILE"
                fi
            fi
            SECTION_TITLE="$line"
            SECTION=""
        else
            SECTION="$SECTION $line"
        fi
    done < "$FILE"

    # Process last section
    if [ -n "$SECTION" ] && [ ${#SECTION} -gt 20 ]; then
        EMBEDDING=$(curl -s --max-time 30 http://172.18.16.1:1234/v1/embeddings \
            -H "Content-Type: application/json" \
            -d "$(jq -n --arg text "$SECTION" '{
                model: "text-embedding-nomic-embed-text-v1.5",
                input: $text
            }')" | jq -c '.data[0].embedding')

        if [ "$EMBEDDING" != "null" ] && [ -n "$EMBEDDING" ]; then
            jq -n -c --arg file "$FILE" --arg title "$SECTION_TITLE" \
                --arg text "$SECTION" --argjson emb "$EMBEDDING" \
                '{file:$file, title:$title, text:$text, embedding:$emb}' >> "$INDEX_FILE"
        fi
    fi

    echo "$HASH" >> "$INDEXED_FILE"
    echo "INDEXED: $FILE"
done

TOTAL=$(wc -l < "$INDEX_FILE" 2>/dev/null || echo 0)
echo "INDEX_COMPLETE: $TOTAL entries"
