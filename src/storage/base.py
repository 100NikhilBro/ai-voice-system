from abc import ABC, abstractmethod
from typing import List, Optional
from src.storage.schema import KnowledgeRecord, SearchResult

class BaseKnowledgeStore(ABC):
    """Abstract interface for knowledge base vector and text storage."""

    @abstractmethod
    def initialize_schema(self) -> None:
        """Create tables, vector extensions, and full-text indexes."""
        pass

    @abstractmethod
    def insert_records(self, records: List[KnowledgeRecord]) -> int:
        """Insert or upsert knowledge records with embeddings."""
        pass

    @abstractmethod
    def search_vector(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """Perform dense vector semantic search."""
        pass

    @abstractmethod
    def search_text(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None
    ) -> List[SearchResult]:
        """Perform sparse lexical full-text search."""
        pass

    @abstractmethod
    def get_record(self, record_id: str) -> Optional[KnowledgeRecord]:
        """Fetch single record by unique record_id."""
        pass

    @abstractmethod
    def count_records(self) -> int:
        """Count total stored records."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored records (for testing)."""
        pass
