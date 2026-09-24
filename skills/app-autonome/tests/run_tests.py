#!/usr/bin/env python3
"""
Deterministic tests of the skill's guardrails: they verify that validate_package.py
and smoke_test.cjs catch EVERY known network channel, and let a compliant tool
through. This is what makes the "nothing leaves the computer" promise verifiable,
not merely declared.

Each fixture in tests/fixtures/ contains either zero violations ("clean-" fixtures)
or one precise violation. The EXPECTED table below declares, for each of them, the
validator's exit code, the patterns that must appear in its output, and the expected
smoke test verdict. The "leak-*" fixtures are the keystone: they PASS the static
validator (dynamically built URL or constructor, invisible without execution) and
MUST fail the smoke test's network assertion: the proof that the two layers are
complementary. Special case: link-preconnect-external is caught by BOTH layers (the
smoke test via its live-DOM check, its only defense for a file without the
template's structure, which escapes the validator, like the docs/index.html hero
page).

Usage: python3 run_tests.py          (from any directory)

Exit codes:
  0 = every test passes (static AND smoke)
  1 = at least one expected/actual mismatch -> a guardrail regressed, FIX IT
  3 = static phase 100% green but smoke test skipped (node or Playwright/Chromium
      missing); in CI, require 0: a 3 means the environment is incomplete

CONTRACT NOTE: the "patterns" are substrings of the scripts' messages. Any
rewording in validate_package.py or smoke_test.cjs must be mirrored here; that
is deliberate: the messages are part of the contract.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
VALIDATOR = HERE.parent / "scripts" / "validate_package.py"
SMOKE = HERE.parent / "scripts" / "smoke_test.cjs"

# smoke: "ok" = must pass with 0 outgoing requests; "leak" = must fail on an
# outgoing request; "preconnect" = must fail on the DOM preconnection check;
# None = not relevant (the violation is purely static).
EXPECTED = [
    {"fixture": "clean-minimal.html", "exit": 0, "patterns": ["0 error"], "smoke": "ok"},
    {"fixture": "clean-lib-inert-urls.html", "exit": 0,
     "patterns": ["0 error", "URL string", "fetch() present in LIBRARIES"],
     "smoke": "ok"},
    {"fixture": "leak-image-load.html", "exit": 0, "patterns": ["0 error"], "smoke": "leak"},
    {"fixture": "leak-on-tab-click.html", "exit": 0, "patterns": ["0 error"], "smoke": "leak"},
    # WebSocket with a dynamically resolved constructor: invisible to static
    # analysis, and a WS handshake never shows in route(); exercises routeWebSocket.
    {"fixture": "leak-websocket-dynamic.html", "exit": 0, "patterns": ["0 error"], "smoke": "leak"},
    # preconnect: no interceptable request; exercises the live-DOM check.
    {"fixture": "link-preconnect-external.html", "exit": 1,
     "patterns": ["loaded at runtime", "<link>"], "smoke": "preconnect"},
    {"fixture": "fetch-app-code.html", "exit": 1, "patterns": ["fetch() detected in APP CODE"], "smoke": None},
    {"fixture": "sendbeacon-app-code.html", "exit": 1, "patterns": ["sendBeacon"], "smoke": None},
    {"fixture": "websocket-app-code.html", "exit": 1, "patterns": ["WebSocket detected in APP CODE"], "smoke": None},
    {"fixture": "realtime-app-code.html", "exit": 1, "patterns": ["EventSource", "RTCPeerConnection"], "smoke": None},
    {"fixture": "script-src-external.html", "exit": 1,
     "patterns": ["loaded at runtime", "<script-src>"], "smoke": None},
    {"fixture": "img-src-relative.html", "exit": 1, "patterns": ["<img-src>"], "smoke": None},
    {"fixture": "srcset-remote.html", "exit": 1, "patterns": ["<srcset>"], "smoke": None},
    {"fixture": "a-ping.html", "exit": 1, "patterns": ["<ping>"], "smoke": None},
    {"fixture": "meta-refresh-url.html", "exit": 1, "patterns": ["<meta-refresh>"], "smoke": None},
    {"fixture": "link-css-relative.html", "exit": 1, "patterns": ["<link-stylesheet>"], "smoke": None},
    {"fixture": "css-url-mixed.html", "exit": 1,
     "patterns": ["external CSS url()", "relative CSS url()"], "smoke": None},
    {"fixture": "worker-and-module.html", "exit": 1,
     "patterns": ['type="module"', "new Worker("], "smoke": None},
]

SMOKE_PATTERNS = {"ok": (0, "0 outgoing requests"), "leak": (1, "outgoing request"),
                  "preconnect": (1, "preconnection")}


def run_cmd(cmd):
    """Runs a command, returns (code, output). Timeout/absence = failure, not a crash."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT after 120 s"
    except FileNotFoundError as e:
        return -1, f"COMMAND NOT FOUND: {e.filename or cmd[0]}"


def check(name, expected_code, patterns, code, output, details):
    """Compares expected/actual, feeds details on mismatch. Returns True if OK."""
    ok = True
    if code != expected_code:
        details.append(f"{name}: exit code {code} (expected {expected_code})")
        ok = False
    for pattern in patterns:
        if pattern not in output:
            details.append(f"{name}: pattern missing from output: \"{pattern}\"")
            ok = False
    if not ok:
        excerpt = "\n      ".join(output.strip().splitlines()[-8:])
        details.append(f"{name}, last lines of output:\n      {excerpt}")
    return ok


def main():
    missing = [e["fixture"] for e in EXPECTED if not (FIXTURES / e["fixture"]).is_file()]
    if missing:
        print(f"ERROR: fixture(s) not found: {', '.join(missing)}")
        return 1

    details = []
    rows = []
    static_ok = True
    smoke_skipped = False
    smoke_ok = True

    # --- Phase 1: does the static validator return the expected verdicts? ---
    for e in EXPECTED:
        fixture_path = FIXTURES / e["fixture"]
        code, output = run_cmd([sys.executable, str(VALIDATOR), str(fixture_path)])
        ok = check(e["fixture"], e["exit"], e["patterns"], code, output, details)
        static_ok = static_ok and ok
        rows.append([e["fixture"], f"exit {e['exit']} → {code}", "OK" if ok else "MISMATCH"])

    # --- Phase 2: does the smoke test's network assertion keep its promises? ---
    relevant = [e for e in EXPECTED if e["smoke"]]
    for i, e in enumerate(relevant):
        fixture_path = FIXTURES / e["fixture"]
        code, output = run_cmd(["node", str(SMOKE), str(fixture_path)])
        if code == 3 or "COMMAND NOT FOUND" in output:
            # No browser (or no node): incomplete environment, not a regression;
            # skipped for all (no point retrying the rest).
            smoke_skipped = True
            for rest in relevant[i:]:
                rows.append([rest["fixture"] + " (smoke)", "SKIPPED", "SKIPPED"])
            break
        expected_code, pattern = SMOKE_PATTERNS[e["smoke"]]
        ok = check(e["fixture"] + " (smoke)", expected_code, [pattern], code, output, details)
        smoke_ok = smoke_ok and ok
        rows.append([e["fixture"] + " (smoke)", f"exit {expected_code} → {code}", "OK" if ok else "MISMATCH"])

    # --- Report ---
    print(f"\n=== Guardrail tests ({len(EXPECTED)} fixtures) ===\n")
    width = max(len(r[0]) for r in rows)
    for name, expected_actual, verdict in rows:
        print(f"  {name.ljust(width)}  {expected_actual.ljust(14)}  {verdict}")
    if details:
        print("\n  Mismatches:")
        for d in details:
            print("    - " + d)

    if not static_ok or not smoke_ok:
        print("\nFAILED: a guardrail no longer catches what it must (or blocks a compliant tool).")
        return 1
    if smoke_skipped:
        print("\nPARTIAL: static phase 100% green, but the smoke test's network assertion could")
        print("not be exercised (node or Playwright/Chromium missing). In CI, this 3 must fail.")
        return 3
    print("\nOK: every known network channel is caught, and compliant tools pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
