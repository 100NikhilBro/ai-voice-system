import numpy as np
import pytest
from src.retrieval.embeddings import get_embedding_provider
from src.storage.factory import get_knowledge_store
from src.storage.local_store import LocalHybridKnowledgeStore
from src.storage.postgres_store import PostgresKnowledgeStore
from src.storage.schema import KnowledgeRecord
from src.retrieval.hybrid_retriever import HybridRetriever

def test_local_embedding_provider_properties():
    provider = get_embedding_provider()
    assert provider.dimension == 384

    vec = provider.embed_text("HealthShield Platinum comprehensive hospitalization coverage")
    assert len(vec) == 384
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-4

def test_local_embedding_batch_consistency():
    provider = get_embedding_provider()
    texts = [
        "Gold plan inpatient room rent limit is single private room.",
        "Cashless admission must be submitted 48 hours in advance for planned surgeries."
    ]
    batch_vecs = provider.embed_batch(texts)
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384
    assert len(batch_vecs[1]) == 384

    # Compare batch against single embed
    single_0 = provider.embed_text(texts[0])
    sim = np.dot(batch_vecs[0], single_0)
    assert sim > 0.9999

def test_local_hybrid_store_vector_and_text(tmp_path):
    db_file = tmp_path / "test_local.db"
    store = LocalHybridKnowledgeStore(str(db_file))
    provider = get_embedding_provider()

    records = [
        KnowledgeRecord(
            record_id="test_001",
            title="Waiting Period Policy",
            content="Pre-existing condition waiting period is 24 months for Platinum tier.",
            category="policy_underwriting",
            source="policy.txt#chunk_1",
            embedding=provider.embed_text("Pre-existing condition waiting period is 24 months for Platinum tier.")
        ),
        KnowledgeRecord(
            record_id="test_002",
            title="OPD Copayment Rules",
            content="Outpatient pharmacy charges require a 20 percent copayment.",
            category="product_info",
            source="brochure.html#chunk_2",
            embedding=provider.embed_text("Outpatient pharmacy charges require a 20 percent copayment.")
        )
    ]

    inserted = store.insert_records(records)
    assert inserted == 2
    assert store.count_records() == 2

    # Vector search
    q_vec = provider.embed_text("How many months is the waiting period for Platinum pre-existing conditions?")
    vec_results = store.search_vector(q_vec, top_k=2)
    assert len(vec_results) == 2
    assert vec_results[0].record_id == "test_001"
    assert vec_results[0].score > 0.50

    # Text search
    text_results = store.search_text("copayment pharmacy", top_k=2)
    assert len(text_results) >= 1
    assert text_results[0].record_id == "test_002"

def test_hybrid_retriever_safe_fallback(tmp_path):
    db_file = tmp_path / "test_fallback.db"
    store = LocalHybridKnowledgeStore(str(db_file))
    provider = get_embedding_provider()

    records = [
        KnowledgeRecord(
            record_id="health_001",
            title="Health Insurance Inpatient Benefits",
            content="Covers hospital room stay and ICU care for human policyholders.",
            category="product_info",
            source="brochure.html#chunk_1",
            embedding=provider.embed_text("Covers hospital room stay and ICU care for human policyholders.")
        )
    ]
    store.insert_records(records)

    retriever = HybridRetriever(store, similarity_threshold=0.40)

    # In-scope query
    resp_in = retriever.retrieve("inpatient hospital room stay and ICU care")
    assert resp_in.grounded_answer_available is True
    assert len(resp_in.results) > 0
    assert resp_in.top_citation is not None
    assert resp_in.fallback_message is None

    # Out-of-scope query
    resp_out = retriever.retrieve("airline lost baggage compensation claim status")
    assert resp_out.grounded_answer_available is False
    assert len(resp_out.results) == 0
    assert resp_out.top_citation is None
    assert "Information unavailable" in (resp_out.fallback_message or "")
