"""
Natural language → test runner.
Maps user phrases to pytest invocations and runs them, returning a human-readable result.
"""
from __future__ import annotations
import asyncio
import subprocess
import sys
import re
from pathlib import Path

# Map phrases to test files (or test names)
PHRASE_MAP = [
    # Specific test files
    (r"(?i)\b(circuit\s*breaker|breaker)\b",          "tests/test_circuit_breaker.py"),
    (r"(?i)\b(retry|backoff)\b",                       "tests/test_retry.py"),
    (r"(?i)\b(fallback|chain)\b",                      "tests/test_fallback.py"),
    (r"(?i)\b(self[\s\-]?heal|healing)\b",            "tests/test_self_healing.py"),
    (r"(?i)\b(learning|feedback|ab[\s\-]?test|model[\s\-]?rank)\b", "tests/test_learning.py"),
    (r"(?i)\b(failover|server[\s\-]?pool|health[\s\-]?monitor)\b",   "tests/test_failover.py"),
    (r"(?i)\b(end[\s\-]?to[\s\-]?end|e2e)\b",          "tests/test_e2e_self_healing.py"),
    (r"(?i)\bgateway\b",                               "tests/test_gateway_integration.py"),

    # Whole suites
    (r"(?i)\b(all|everything|full)\b",                 "ALL"),
]


class NLTestRunner:
    """Parse natural language → pytest."""

    def __init__(self, project_root: str | None = None):
        self.project_root = Path(project_root or "/workspace/ai-empire/orchestrator")

    def resolve(self, text: str) -> str:
        """Return the pytest target (file path or ALL)."""
        for pattern, target in PHRASE_MAP:
            if re.search(pattern, text):
                return target
        # Default: run all unit + e2e
        return "ALL_DEFAULT"

    async def run_from_text(self, text: str) -> dict:
        target = self.resolve(text)
        return await self._run_pytest(target)

    async def _run_pytest(self, target: str) -> dict:
        """Run pytest against the target and parse the result."""
        # Build command
        if target == "ALL":
            cmd = ["python3", "-m", "pytest", "tests/", "-v", "--tb=line", "--ignore=tests/chaos"]
        elif target == "ALL_DEFAULT":
            cmd = ["python3", "-m", "pytest", "tests/", "-v", "--tb=line",
                   "--ignore=tests/chaos", "--ignore=tests/test_gateway_integration.py"]
        else:
            cmd = ["python3", "-m", "pytest", target, "-v", "--tb=short"]

        # Run
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            rc = proc.returncode
        except asyncio.TimeoutError:
            return {
                "text": "⏱️ Tests timed out after 5 minutes. That's not normal — let me know what test and I'll investigate.",
                "ok": False,
            }
        except Exception as e:
            return {
                "text": f"❌ Could not run tests: {e}\n\nMake sure you're in the ai-empire/orchestrator directory.",
                "ok": False,
            }

        # Parse results
        passed, failed, skipped, errors = 0, 0, 0, 0
        # Look for "X passed" / "X failed" etc
        summary_match = re.search(
            r"=+\s*(\d+\s+passed|\d+\s+failed|\d+\s+skipped|\d+\s+error)", stdout_text
        )
        # Better: find "N passed" or "N passed, M failed"
        m = re.search(r"(\d+)\s+passed", stdout_text)
        if m: passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", stdout_text)
        if m: failed = int(m.group(1))
        m = re.search(r"(\d+)\s+skipped", stdout_text)
        if m: skipped = int(m.group(1))
        m = re.search(r"(\d+)\s+error", stdout_text)
        if m: errors = int(m.group(1))

        # Build a human-friendly summary
        if rc == 0:
            headline = f"✅ All {passed} tests passed"
            if skipped:
                headline += f" ({skipped} skipped)"
        else:
            headline = f"❌ {failed} failed, {passed} passed"
            if skipped:
                headline += f", {skipped} skipped"
            if errors:
                headline += f", {errors} errors"

        # Get the first few failure messages (if any)
        failure_lines = []
        if rc != 0:
            # Find FAILED lines and the next 3 lines
            for match in re.finditer(r"FAILED\s+(.+?)(?=\n)", stdout_text):
                failure_lines.append(f"  • {match.group(1)}")
                if len(failure_lines) >= 5:
                    break

        # Last lines of output (the summary)
        last_lines = "\n".join(stdout_text.strip().split("\n")[-3:])

        msg = f"**{headline}**\n\n"
        if target == "ALL" or target == "ALL_DEFAULT":
            msg += "Ran the full unit + e2e suite (excluding chaos, which would actually kill your services).\n\n"
        else:
            msg += f"Ran: `{target}`\n\n"
        if failure_lines:
            msg += "Failures:\n" + "\n".join(failure_lines) + "\n\n"
        msg += f"```\n{last_lines}\n```"

        return {
            "text": msg,
            "ok": rc == 0,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "raw": stdout_text if rc != 0 else None,
        }
