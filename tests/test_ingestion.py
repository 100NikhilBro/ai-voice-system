from pathlib import Path
import pytest
from src.ingestion.parser import DocumentParser, parser
from src.ingestion.cleaner import DocumentCleaner, cleaner
from src.ingestion.normalizer import TerminologyNormalizer, normalizer
from src.ingestion.chunker import SemanticChunker, chunker
from src.config import settings

def test_cleaner_boilerplate_removal():
    dirty_text = (
        "Call toll-free 1-800-555-0199 for marketing inquiries.\n"
        "HealthShield provides comprehensive inpatient protection.\n"
        "&copy; 2026 All rights reserved.\n"
        "Navigation links: Home | Plans | Privacy Policy."
    )
    cleaned = cleaner.clean_text(dirty_text)
    assert "Call toll-free" not in cleaned
    assert "&copy;" not in cleaned
    assert "Navigation links:" not in cleaned
    assert "HealthShield provides comprehensive inpatient protection." in cleaned

def test_cleaner_paragraph_deduplication():
    repeated_p1 = "Comprehensive health insurance covers emergency accidental hospital visits from day one."
    repeated_p2 = "Comprehensive health insurance covers emergency accidental hospital visits from day one."
    different_p = "Outpatient consultations require a twenty dollar copayment on Silver plans."

    text = f"{repeated_p1}\n\n{repeated_p2}\n\n{different_p}"
    deduped, count = cleaner.deduplicate_paragraphs(text, threshold=0.85)
    assert count == 1
    assert deduped.count("Comprehensive health insurance covers emergency") == 1
    assert "Outpatient consultations require" in deduped

def test_normalizer_category_mapping():
    assert normalizer.normalize_category("sample_product_brochure.html") == "product_info"
    assert normalizer.normalize_category("sample_underwriting_policy.txt") == "policy_underwriting"
    assert normalizer.normalize_category("sample_qualification_rules.json") == "qualification_rules"
    assert normalizer.normalize_category("sample_faqs_and_objections.md") == "faq_and_objections"
    assert normalizer.normalize_category("sample_customer_inquiry_pii.txt") == "customer_inquiry_samples"

def test_normalizer_terminology_expansion():
    text = "Waiting period applies to PED. Routine checkup requires OPD consultation and Copay."
    normalized = normalizer.normalize_terminology(text)
    assert "Pre-Existing Condition (PED)" in normalized
    assert "Outpatient Department Consultation (OPD)" in normalized
    assert "Copayment" in normalized

def test_parser_and_chunker_schema_integrity():
    raw_docs_dir = settings.RAW_DOCS_DIR
    sample_json = raw_docs_dir / "sample_qualification_rules.json"
    assert sample_json.exists(), f"Sample file {sample_json} missing"

    parsed = parser.parse_file(sample_json)
    assert parsed["title"]
    assert parsed["format"] == "json"
    assert "raw_text" in parsed

    chunks = chunker.chunk_document(
        doc_data=parsed,
        cleaned_text=parsed["raw_text"],
        category="qualification_rules",
        source=sample_json.name,
        has_pii=False,
        pii_types=[]
    )

    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk.record_id.startswith("kb_qual_")
        assert chunk.category == "qualification_rules"
        assert chunk.source.startswith("sample_qualification_rules.json#chunk_")
        assert chunk.version == "1.0"
        assert isinstance(chunk.has_pii, bool)
        assert len(chunk.content) > 20
