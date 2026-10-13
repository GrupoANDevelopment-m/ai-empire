#!/bin/bash
# AI Empire — Verify all installed skills
set -e
cd "$(dirname "$0")/.."

echo "=== Verifying AI Empire Skills ==="
echo ""

SKILLS_DIR=".skills"
TOTAL=0
PASS=0
FAIL=0

for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "browser-automation" ] || [ "$skill_name" = "muapi-studio" ] || [ "$skill_name" = "saas-b2b" ] || [ "$skill_name" = "email" ] || [ "$skill_name" = "calendar" ] || [ "$skill_name" = "crm" ] || [ "$skill_name" = "social-media" ] || [ "$skill_name" = "data-analysis" ] || [ "$skill_name" = "code-execution" ] || [ "$skill_name" = "web-search" ] || [ "$skill_name" = "pdf" ] || [ "$skill_name" = "translation" ] || [ "$skill_name" = "summarization" ] || continue

    # Check for skill.yaml or .skill/skill.yaml
    if [ -f "$skill_dir/skill.yaml" ]; then
        manifest="$skill_dir/skill.yaml"
    elif [ -f "$skill_dir/.skill/skill.yaml" ]; then
        manifest="$skill_dir/.skill/skill.yaml"
    else
        echo "  ✗ $skill_name: missing skill.yaml"
        FAIL=$((FAIL + 1))
        continue
    fi

    TOTAL=$((TOTAL + 1))

    # Check for tools
    if [ -d "$skill_dir/tools" ]; then
        tool_count=$(find "$skill_dir/tools" -name "*.py" | wc -l)
    elif [ -d "$skill_dir/.skill/tools" ]; then
        tool_count=$(find "$skill_dir/.skill/tools" -name "*.py" | wc -l)
    else
        echo "  ✗ $skill_name: no tools/"
        FAIL=$((FAIL + 1))
        continue
    fi

    if [ "$tool_count" -eq 0 ]; then
        echo "  ✗ $skill_name: 0 tools"
        FAIL=$((FAIL + 1))
        continue
    fi

    echo "  ✓ $skill_name: $tool_count tools"
    PASS=$((PASS + 1))
done

echo ""
echo "Total: $TOTAL skills"
echo "Pass:  $PASS"
echo "Fail:  $FAIL"
exit $FAIL
