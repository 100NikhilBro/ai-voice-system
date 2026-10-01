import re
from typing import List, Dict, Any
from src.storage.schema import KnowledgeRecord

class SemanticChunker:
    """
    Splits normalized and cleaned documents into semantically coherent chunks
    conforming to the assessment schema:
    - record_id: e.g. kb_product_001
    - title: chunk section title
    - content: chunk body text
    - category / source: category / source reference
    - version / PII: version / has_pii boolean
    """

    def __init__(self, target_chunk_size: int = 300, chunk_overlap: int = 50):
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(
        self,
        doc_data: Dict[str, Any],
        cleaned_text: str,
        category: str,
        source: str,
        has_pii: bool,
        pii_types: List[str]
    ) -> List[KnowledgeRecord]:
        """Convert a cleaned document into structured KnowledgeRecord chunks."""
        # Split on markdown headers or double linebreaks
        sections = re.split(r'\n(?=#{1,4}\s+|[0-9]+\.\s+[A-Z\s]{4,})', cleaned_text)
        if len(sections) <= 1:
            sections = [p.strip() for p in cleaned_text.split("\n\n") if len(p.strip()) > 30]

        records: List[KnowledgeRecord] = []
        base_prefix = self._get_category_prefix(category)
        doc_title = doc_data.get("title", source)
        version = doc_data.get("version", "1.0")

        chunk_idx = 1
        for sec in sections:
            sec = sec.strip()
            if not sec or len(sec) < 40:
                continue

            # Extract sub-title if section starts with a header
            first_line = sec.splitlines()[0].strip("#* \t")
            sub_title = f"{doc_title} - {first_line[:60]}" if first_line != doc_title else doc_title

            # Word-level chunking if section is very large
            words = sec.split()
            if len(words) > self.target_chunk_size + self.chunk_overlap:
                start = 0
                while start < len(words):
                    end = min(start + self.target_chunk_size, len(words))
                    chunk_text = " ".join(words[start:end])

                    record = KnowledgeRecord(
                        record_id=f"{base_prefix}_{chunk_idx:03d}",
                        title=sub_title,
                        content=chunk_text,
                        category=category,
                        source=f"{source}#chunk_{chunk_idx}",
                        version=version,
                        has_pii=has_pii,
                        pii_types=pii_types,
                        metadata={
                            "word_count": len(words[start:end]),
                            "parent_doc": source
                        }
                    )
                    records.append(record)
                    chunk_idx += 1
                    start += (self.target_chunk_size - self.chunk_overlap)
            else:
                record = KnowledgeRecord(
                    record_id=f"{base_prefix}_{chunk_idx:03d}",
                    title=sub_title,
                    content=sec,
                    category=category,
                    source=f"{source}#chunk_{chunk_idx}",
                    version=version,
                    has_pii=has_pii,
                    pii_types=pii_types,
                    metadata={
                        "word_count": len(words),
                        "parent_doc": source
                    }
                )
                records.append(record)
                chunk_idx += 1

        return records

    def _get_category_prefix(self, category: str) -> str:
        """Generate human-readable prefix matching PDF example."""
        mapping = {
            "product_info": "kb_product",
            "policy_underwriting": "kb_policy",
            "qualification_rules": "kb_qual",
            "faq_and_objections": "kb_faq",
            "customer_inquiry_samples": "kb_inquiry"
        }
        return mapping.get(category, "kb_record")

chunker = SemanticChunker()
