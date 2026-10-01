#!/usr/bin/env python3
"""
Question 2 Benchmark Evaluation Runner
=======================================
Executes the mandatory benchmark evaluation suite required by the PDF Assessment (Page 2).
Covers:
1. Product Information
2. Policy Underwriting
3. Qualification Rules
4. FAQ
5. Grounded Objection Handling
6. Safe Fallback / Anti-Hallucination Guardrail

Saves JSON evaluation report to domains/health_insurance/kb_store/q2_benchmark_report.json
"""

import sys
import json
from pathlib import Path

# Ensure workspace root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.retrieval.service import retrieval_service
from tests.test_q2_benchmark import BENCHMARK_CASES, evaluate_single_query
from src.config import settings

def print_separator(char="=", length=100):
    print(char * length)

def main():
    print_separator()
    print(" QUESTION 2: HEALTH INSURANCE KNOWLEDGE BASE BENCHMARK SUITE")
    print(f" Storage Engine: {type(retrieval_service.store).__name__}")
    print(f" Embedding Provider: {type(retrieval_service.retriever.store).__name__} (dim={settings.EMBEDDING_DIM})")
    print(f" Indexed Records in DB: {retrieval_service.store.count_records()}")
    print_separator()

    results = []
    correct_count = 0
    fallback_count = 0

    for i, case in enumerate(BENCHMARK_CASES, 1):
        res = evaluate_single_query(case)
        results.append(res)

        if res.verdict == "CORRECT":
            correct_count += 1
            status_symbol = "[PASS - CORRECT]"
        elif res.verdict == "SAFE_FALLBACK":
            fallback_count += 1
            status_symbol = "[PASS - SAFE FALLBACK]"
        else:
            status_symbol = f"[FAIL - {res.verdict}]"

        print(f"\n[{i}/{len(BENCHMARK_CASES)}] {res.query_id} ({res.category})")
        print(f" Question   : \"{res.user_question}\"")
        print(f" Status     : {status_symbol}")
        print(f" Record ID  : {res.retrieved_record_id or 'None (Grounded Fallback)'}")
        print(f" Citation   : {res.source_reference or 'None'}")
        print(f" Score      : {res.similarity_score:.4f}")
        print(f" Explanation: {res.relevance_explanation}")

    print("\n" + "=" * 100)
    print(" BENCHMARK SUMMARY")
    print(f" Total Queries Evaluated : {len(results)}")
    print(f" In-Scope Correct Matches: {correct_count}/5")
    print(f" Safe Fallback Verified  : {fallback_count}/1")
    total_passed = correct_count + fallback_count
    accuracy = (total_passed / len(results)) * 100
    print(f" Overall Accuracy        : {accuracy:.1f}%")
    print("=" * 100)

    # Save to kb_store
    report_path = settings.KB_STORE_DIR / "q2_benchmark_report.json"
    settings.KB_STORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)
    print(f"Verifiable benchmark report saved to: {report_path}\n")

    return 0 if total_passed == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())
