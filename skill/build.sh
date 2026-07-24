#!/bin/bash
# Build the people-helper.skill archive
# Usage: ./build.sh
# Output: ../people-helper.skill (tar.gz)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
ARCHIVE="$PARENT_DIR/people-helper.skill"

# The skill package includes files from both skill/ and repo root
cd "$PARENT_DIR"

# Validate package contents
if [ ! -f "SKILL.md" ]; then
    echo "ERROR: SKILL.md not found in repo root" >&2
    exit 1
fi
if [ ! -f "skill/manifest.yaml" ]; then
    echo "ERROR: skill/manifest.yaml not found" >&2
    exit 1
fi

# Build the archive
# Format: tar.gz containing:
#   SKILL.md              (repo root — the skill prompt)
#   skill/manifest.yaml   (skill metadata)
#   skill/platforms/      (platform-specific exports)
#   references/           (heuristic + API docs)
#   src/                  (source code, for self-contained skill)
#   people_helper.py      (CLI entry point)
#   requirements.txt      (dependencies)
tar czf "$ARCHIVE" \
    SKILL.md \
    skill/manifest.yaml \
    skill/platforms/ \
    references/ \
    src/ \
    people_helper.py \
    requirements.txt \
    LICENSE

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
echo "To install in Hermes:        copy SKILL.md and skill/platforms/hermes.yaml"
echo "To install in Cursor:        copy skill/platforms/cursor.md as .cursorrules"
echo "To install in Cline:         paste skill/platforms/cline.md into Custom Instructions"
echo "To install in OpenAI GPT:    paste skill/platforms/gpt.md as Instructions, add Actions"
echo "To install as MCP server:    copy skill/platforms/mcp.json into mcp.json"
