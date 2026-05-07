#!/usr/bin/env python3
"""
Auto-test script for AI-XBrain unified agent.
Tests L1, L2, L3 questions and reports pass/fail.

Usage:
    python scripts/test_questions.py
    python scripts/test_questions.py --url http://127.0.0.1:8001
    python scripts/test_questions.py --level L1
    python scripts/test_questions.py --level L1,L3
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

QUESTIONS_DIR = Path(r"E:\Project\Learn-Project\AI-Engineer\AI-XBrain-Week4\xbrain-learners\W4\questions\student")
DEFAULT_URL = "http://127.0.0.1:8001"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def extract_keywords(expected: str) -> list[str]:
    """Extract must-have terms from expected answer text."""
    kw: list[str] = []

    # Dollar amounts: $56,350 / $7,500
    kw += re.findall(r'\$[\d,]+', expected)

    # Numbers with units (keep surrounding unit for context)
    kw += re.findall(
        r'\d[\d,]*\.?\d*\s*(?:ms|rpm|%|years?|days?|requests?\s+per\s+\w+|requests?/\w+|incidents?|minutes?|hours?)',
        expected, re.I
    )

    # Bare important numbers (dates, port numbers, etc.)
    kw += re.findall(r'\b(?:April\s+\d+,?\s*\d{4}|\d{1,2}\s+\w+\s+\d{4})\b', expected, re.I)

    # Service names
    kw += re.findall(
        r'\b(?:PaymentGW|NotificationSvc|AuthSvc|OrderSvc|FraudDetector|InventorySvc|ReportingSvc)\b',
        expected
    )

    # Person names (two+ title-case words) — strip parenthetical first to avoid "Simple Queue" etc.
    expected_no_parens = re.sub(r'\([^)]*\)', '', expected)
    kw += re.findall(r'[A-Z][a-z]+ [A-Z][a-z]+', expected_no_parens)

    # Key tech / policy terms
    kw += re.findall(
        r'\b(?:SQS|Amazon SQS|HMAC-SHA256|HMAC|JWT|circuit breaker|health check|API key|P1|VP Engineering|Go)\b',
        expected, re.I
    )

    # Dedupe preserving order
    seen: set[str] = set()
    result: list[str] = []
    for k in kw:
        k = k.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            result.append(k)
    return result


def _normalize(text: str) -> str:
    """Normalize text for comparison: strip number commas, lowercase."""
    # Remove thousand-separator commas: 1,000 → 1000
    text = re.sub(r'(\d),(\d)', r'\1\2', text)
    return text.lower()


def _round_numbers(text: str) -> str:
    """Round floats to 1 decimal so 71.98% matches 72% and 0.0839% matches 0.08%."""
    def round_match(m):
        try:
            val = float(m.group(0))
            # Round to 2 sig figs for percentages/ms
            if val >= 10:
                return str(round(val))
            elif val >= 1:
                return f"{val:.1f}"
            else:
                return f"{val:.2f}"
        except Exception:
            return m.group(0)
    return re.sub(r'\d+\.\d+', round_match, text)


def check_keywords(actual: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    actual_norm = _normalize(_round_numbers(actual))
    found, missing = [], []
    for kw in keywords:
        kw_norm = _normalize(_round_numbers(kw))

        # Direct substring match
        if kw_norm in actual_norm:
            found.append(kw)
            continue

        # Flexible number match: allow words between number and unit
        # e.g. "7 incidents" matches "7 total incidents" or "7 new incidents"
        num_match = re.match(r'^(\d[\d.]*)\s+(\w+)', kw_norm)
        if num_match:
            num, unit = num_match.group(1), num_match.group(2)
            pattern = rf'\b{re.escape(num)}\b[^.]*?\b{re.escape(unit)}'
            if re.search(pattern, actual_norm):
                found.append(kw)
                continue

        # Approximate numeric match ±10% for live metrics (ms, rpm, %)
        num_only = re.match(r'^(\d[\d.]*)\s*(ms|rpm|%|requests?)', kw_norm)
        if num_only:
            try:
                target = float(num_only.group(1))
                unit = num_only.group(2)
                pattern = rf'(\d[\d.]*)\s*{re.escape(unit)}'
                for m in re.finditer(pattern, actual_norm):
                    if abs(float(m.group(1)) - target) / max(target, 1) <= 0.10:
                        found.append(kw)
                        break
                else:
                    missing.append(kw)
                continue
            except Exception:
                pass

        missing.append(kw)
    return found, missing


def call_api(url: str, question: str, question_id: str, level: str, timeout: int = 60) -> dict | None:
    payload = {
        "message": question,
        "question_id": question_id,
        "level": level,
    }
    try:
        resp = httpx.post(f"{url}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        return {"error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def run_level(url: str, level_key: str, questions_file: Path) -> tuple[int, int]:
    """Run all questions for a level. Returns (passed, total)."""
    with open(questions_file, encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    passed = 0

    print(f"\n{c(BOLD, '═' * 70)}")
    print(c(BOLD + CYAN, f"  {level_key}  —  {data.get('description', '')}"))
    print(c(BOLD, '═' * 70))

    for q in questions:
        qid = q["id"]
        question = q["question"]
        expected = q.get("expected_answer", "")
        grading = q.get("grading_notes", "")

        print(f"\n{c(BOLD, qid)}  {question}")

        start = time.time()
        result = call_api(url, question, qid, level_key)
        elapsed = time.time() - start

        if "error" in result:
            print(c(RED, f"  ✗ API ERROR: {result['error']}"))
            continue

        actual = result.get("answer", "")
        reasoning = result.get("reasoning", "")
        citations = result.get("citations", [])

        keywords = extract_keywords(expected)
        found, missing = check_keywords(actual, keywords)

        is_pass = len(missing) == 0 or (len(keywords) > 0 and len(missing) / len(keywords) <= 0.25)

        status = c(GREEN, "✓ PASS") if is_pass else c(RED, "✗ FAIL")
        print(f"  {status}  ({elapsed:.1f}s)")

        print(f"  {c(CYAN, 'Expected:')} {expected[:120]}{'...' if len(expected) > 120 else ''}")
        print(f"  {c(CYAN, 'Got:     ')} {actual[:200]}{'...' if len(actual) > 200 else ''}")

        if keywords:
            found_str = "  ".join(c(GREEN, k) for k in found) if found else "—"
            missing_str = "  ".join(c(RED, k) for k in missing) if missing else "—"
            print(f"  Keywords  found: {found_str}")
            if missing:
                print(f"  Keywords missing: {missing_str}")

        if grading:
            print(f"  {c(YELLOW, 'Grading note:')} {grading}")

        if reasoning:
            preview = reasoning.replace("\n", " ")[:120]
            print(f"  {c(CYAN, 'Reasoning:')} {preview}...")

        if citations:
            doc_names = [cit.get("document", "?") for cit in citations[:3]]
            print(f"  Citations: {', '.join(doc_names)}")

        if is_pass:
            passed += 1

    return passed, len(questions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test AI-XBrain questions")
    parser.add_argument("--url", default=DEFAULT_URL, help="Backend URL")
    parser.add_argument("--level", default="L1,L2,L3", help="Levels to test (comma-separated)")
    args = parser.parse_args()

    # Check backend is up
    try:
        resp = httpx.get(f"{args.url}/api/health", timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print(c(RED, f"Backend not reachable at {args.url}: {e}"))
        print("Start it with: .\\scripts\\start-local.ps1")
        sys.exit(1)

    levels = [l.strip().upper() for l in args.level.split(",")]
    level_files = {
        "L1": QUESTIONS_DIR / "L1_questions.json",
        "L2": QUESTIONS_DIR / "L2_questions.json",
        "L3": QUESTIONS_DIR / "L3_questions.json",
    }

    total_passed = 0
    total_questions = 0
    results: list[tuple[str, int, int]] = []

    for level in levels:
        if level not in level_files:
            print(c(YELLOW, f"Unknown level: {level}, skipping"))
            continue
        file = level_files[level]
        if not file.exists():
            print(c(RED, f"File not found: {file}"))
            continue
        passed, total = run_level(args.url, level, file)
        total_passed += passed
        total_questions += total
        results.append((level, passed, total))

    # Summary
    print(f"\n{c(BOLD, '═' * 70)}")
    print(c(BOLD, "  SUMMARY"))
    print(c(BOLD, '═' * 70))
    for level, passed, total in results:
        pct = int(100 * passed / total) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
        print(f"  {level}  [{c(color, bar)}]  {c(color, f'{passed}/{total} ({pct}%)')}")

    overall_pct = int(100 * total_passed / total_questions) if total_questions else 0
    overall_color = GREEN if overall_pct >= 80 else YELLOW if overall_pct >= 50 else RED
    print(f"\n  {c(BOLD, 'Overall:')} {c(overall_color + BOLD, f'{total_passed}/{total_questions} ({overall_pct}%)')}")
    print()


if __name__ == "__main__":
    main()
