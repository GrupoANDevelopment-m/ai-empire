#!/usr/bin/env bash
# AI Empire — Run all tests
# Usage:
#   ./scripts/test.sh             # unit + e2e (no chaos)
#   ./scripts/test.sh all         # everything including chaos
#   ./scripts/test.sh integration # only integration tests (need services)
#   ./scripts/test.sh chaos       # only chaos tests (need EMPIRE_CHAOS_TESTS=1)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/orchestrator"

case "${1:-default}" in
  all)
    EMPIRE_CHAOS_TESTS=1 python3 -m pytest tests/ -v
    ;;
  chaos)
    EMPIRE_CHAOS_TESTS=1 python3 -m pytest tests/chaos/ -v
    ;;
  integration)
    python3 -m pytest tests/ -v -m integration
    ;;
  unit)
    python3 -m pytest tests/ -v -m unit
    ;;
  *)
    python3 -m pytest tests/ -v --ignore=tests/chaos
    ;;
esac
