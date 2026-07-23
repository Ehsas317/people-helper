#!/bin/bash
# Build the people-helper.skill archive
# Usage: ./build.sh
# Output: ../people-helper.skill (tar.gz)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
ARCHIVE="$PARENT_DIR/people-helper.skill"

cd "$SCRIPT_DIR"

# Validate package contents
if [ ! -f "SKILL.md" ]; then
    echo "ERROR: SKILL.md not found" >&2
    exit 1
fi
if [ ! -f "manifest.yaml" ]; then
    echo "ERROR: manifest.yaml not found" >&2
    exit 1
fi

# Build the archive
# Format: tar.gz with skill/ as the root
tar czf "$ARCHIVE" \
    SKILL.md \
    manifest.yaml \
    platforms/ \
    references/ \
    scripts/

echo "Built: $ARCHIVE"
ls -lh "$ARCHIVE"
echo ""
echo "To inspect:"
echo "  tar tzf $ARCHIVE"
echo ""
echo "To extract:"
echo "  mkdir people-helper-package && tar xzf $ARCHIVE -C people-helper-package"
echo ""
echo "To install in Claude Skills: upload $ARCHIVE"
echo "To install in Hermes:        copy SKILL.md and platforms/hermes.yaml"
echo "To install in Cursor:        copy platforms/cursor.md as .cursorrules"
echo "To install in Cline:         paste platforms/cline.md into Custom Instructions"
echo "To install in OpenAI GPT:    paste platforms/gpt.md as Instructions, add Actions"
echo "To install as MCP server:    copy platforms/mcp.json into mcp.json"

