"""
Q3 Language-Aware ASR Evaluation Tests
======================================
Tests the ASR evaluator module across all 6 benchmark cases:
1. Taglish / code-switching
2. English insurance loanwords
3. Indonesian finance loanwords
4. Colloquial Indonesian
5. Regional Javanese speech markers
6. nggih vs nggak acoustic ambiguity check
"""

import sys
import logging
import pytest
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.voice.localized.asr_evaluator import ASREvaluator, calculate_wer

logger = logging.getLogger(__name__)


def test_wer_calculation():
    assert calculate_wer("hello world", "hello world") == 0.0
    assert calculate_wer("hello world", "hello there world") == 0.5
    assert calculate_wer("angsuran motor", "angsuran mobil") == 0.5


def test_asr_benchmark_suite():
    evaluator = ASREvaluator()
    report = evaluator.run_benchmark_suite()

    assert report["total_benchmark_cases"] == 7
    assert report["average_wer"] <= 0.10, f"WER too high: {report['average_wer']}"
    assert report["average_domain_term_recall"] >= 0.90, f"Term recall too low: {report['average_domain_term_recall']}"
    assert report["nggih_vs_nggak_polarity_accuracy"] == 1.0
    assert report["overall_status"] == "VERIFIED_PASS"

    # Verify report file was saved
    report_file = ROOT_DIR / "domains" / "q3_asr_evaluation_report.json"
    assert report_file.exists()

    logger.info("[PASS] test_asr_benchmark_suite passed successfully.")


if __name__ == "__main__":
    test_wer_calculation()
    test_asr_benchmark_suite()
    print("ALL ASR EVALUATION TESTS PASSED!")
