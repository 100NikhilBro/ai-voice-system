import json
import logging
from pathlib import Path
from typing import List
import pytest
from src.retrieval.service import retrieval_service
from src.storage.schema import Q2EvaluationResult
from src.config import settings

logger = logging.getLogger(__name__)

BENCHMARK_CASES = [
    {
        "query_id": "Q2-BENCH-01",
        "category": "product_info",
        "user_question": "What are the coverage benefits and room rent limits under the HealthShield Gold Plan?",
        "expected_source": "sample_product_brochure.html",
        "expected_keywords": ["Gold", "Single Private Room", "350,000"],
        "expect_grounded": True,
    },
    {
        "query_id": "Q2-BENCH-02",
        "category": "policy_underwriting",
        "user_question": "What is the waiting period for pre-existing medical conditions under the Platinum plan?",
        "expected_source": "sample_underwriting_policy.txt",
        "expected_keywords": ["24 months", "Platinum"],
        "expect_grounded": True,
    },
    {
        "query_id": "Q2-BENCH-03",
        "category": "qualification_rules",
        "user_question": "What is the maximum entry age for applicants and what screening is required for seniors aged 60 to 65?",
        "expected_source": "sample_qualification_rules.json",
        "expected_keywords": ["65", "tele-medical", "blood sugar"],
        "expect_grounded": True,
    },
    {
        "query_id": "Q2-BENCH-04",
        "category": "faq_and_objections",
        "user_question": "How many hours prior to planned hospital admission must I present my card for cashless pre-authorization?",
        "expected_source": "sample_faqs_and_objections.md",
        "expected_keywords": ["48 hours", "cashless", "TPA"],
        "expect_grounded": True,
    },
    {
        "query_id": "Q2-BENCH-05",
        "category": "faq_and_objections",
        "user_question": "Customer objection: other policies advertise immediate coverage, why is the waiting period for pre-existing conditions so long?",
        "expected_source": "sample_faqs_and_objections.md",
        "expected_keywords": ["adverse selection", "risk pool", "Day 1"],
        "expect_grounded": True,
    },
    {
        "query_id": "Q2-BENCH-06-FALLBACK",
        "category": "safe_fallback",
        "user_question": "What is the flight cancellation reimbursement policy for delayed international flights?",
        "expected_source": None,
        "expected_keywords": [],
        "expect_grounded": False,
    }
]

def evaluate_single_query(case: dict) -> Q2EvaluationResult:
    query = case["user_question"]
    resp = retrieval_service.retrieve(query, top_k=3)

    if not case["expect_grounded"]:
        if not resp.grounded_answer_available:
            return Q2EvaluationResult(
                query_id=case["query_id"],
                category=case["category"],
                user_question=query,
                retrieved_record_id=None,
                retrieved_title=None,
                source_reference=None,
                similarity_score=0.0,
                relevance_explanation="Correctly identified out-of-scope query and returned explicit safe fallback without hallucination.",
                verdict="SAFE_FALLBACK"
            )
        else:
            return Q2EvaluationResult(
                query_id=case["query_id"],
                category=case["category"],
                user_question=query,
                retrieved_record_id=resp.results[0].record_id if resp.results else None,
                retrieved_title=resp.results[0].title if resp.results else None,
                source_reference=resp.top_citation,
                similarity_score=resp.results[0].score if resp.results else 0.0,
                relevance_explanation="Hallucination risk: returned results for out-of-scope question.",
                verdict="INCORRECT"
            )

    # In-scope evaluation
    if not resp.grounded_answer_available or not resp.results:
        return Q2EvaluationResult(
            query_id=case["query_id"],
            category=case["category"],
            user_question=query,
            retrieved_record_id=None,
            retrieved_title=None,
            source_reference=None,
            similarity_score=0.0,
            relevance_explanation="Failed to retrieve relevant knowledge record.",
            verdict="INCORRECT"
        )

    # Look for expected source in top retrieved results
    target_chunk = None
    for chunk in resp.results:
        if case["expected_source"] and case["expected_source"] in chunk.source:
            target_chunk = chunk
            break

    # If not found in top_k, use the top chunk to inspect
    eval_chunk = target_chunk if target_chunk is not None else resp.results[0]
    matched_source = bool(case["expected_source"] and case["expected_source"] in eval_chunk.source)
    content_lower = eval_chunk.content.lower()
    matched_kws = [kw for kw in case["expected_keywords"] if kw.lower() in content_lower]
    keyword_coverage = len(matched_kws) / len(case["expected_keywords"]) if case["expected_keywords"] else 1.0

    if matched_source and keyword_coverage >= 0.5:
        verdict = "CORRECT"
        explanation = (
            f"Successfully retrieved exact verified chunk (ID: {eval_chunk.record_id}) from {eval_chunk.source}. "
            f"Matched key domain concepts: {matched_kws}."
        )
    elif matched_source:
        verdict = "PARTIALLY_CORRECT"
        explanation = f"Matched source {eval_chunk.source} but key terms missing: {[k for k in case['expected_keywords'] if k.lower() not in content_lower]}."
    else:
        verdict = "INCORRECT"
        explanation = f"Retrieved chunk from {eval_chunk.source}, expected {case['expected_source']}."

    citation = f"Source: {eval_chunk.source} (ID: {eval_chunk.record_id})"
    return Q2EvaluationResult(
        query_id=case["query_id"],
        category=case["category"],
        user_question=query,
        retrieved_record_id=eval_chunk.record_id,
        retrieved_title=eval_chunk.title,
        source_reference=citation,
        similarity_score=eval_chunk.score,
        relevance_explanation=explanation,
        verdict=verdict
    )

def test_q2_benchmark_suite():
    """Run full benchmark suite and assert all test queries pass."""
    results: List[Q2EvaluationResult] = []
    for case in BENCHMARK_CASES:
        eval_result = evaluate_single_query(case)
        results.append(eval_result)
        logger.info(f"[{eval_result.verdict}] {eval_result.query_id}: {eval_result.relevance_explanation}")

    # Export report artifact
    report_file = settings.KB_STORE_DIR / "q2_benchmark_report.json"
    settings.KB_STORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)

    # Verify verdicts
    for r in results:
        assert r.verdict in ("CORRECT", "SAFE_FALLBACK"), f"Benchmark failure for {r.query_id}: {r.relevance_explanation}"

if __name__ == "__main__":
    test_q2_benchmark_suite()
    print("All Q2 benchmark test queries executed successfully!")
