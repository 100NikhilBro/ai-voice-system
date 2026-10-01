import re
from typing import List, Set, Tuple

class DocumentCleaner:
    """
    Cleans raw document text by:
    - Stripping web navigation artifacts, repeated footers, and marketing boilerplate.
    - Removing near-duplicate paragraphs using 3-shingle Jaccard similarity.
    """

    # Generic Boilerplate Patterns to Strip
    BOILERPLATE_PATTERNS = [
        re.compile(r'Call toll-free \d+[-\d]+\s+for marketing inquiries\.?', re.IGNORECASE),
        re.compile(r'&copy;\s*\d{4}.*?All rights reserved\.?', re.IGNORECASE),
        re.compile(r'Navigation links:.*?(?:Privacy Policy|Terms of Service)\.?', re.IGNORECASE),
        re.compile(r'Protecting families with trusted coverage since \d+\.?', re.IGNORECASE)
    ]

    def clean_text(self, text: str) -> str:
        """Strip boilerplate lines, extra whitespace, and control characters."""
        cleaned = text

        for pattern in self.BOILERPLATE_PATTERNS:
            cleaned = pattern.sub('', cleaned)

        # Normalize linebreaks and whitespace
        lines = [line.strip() for line in cleaned.splitlines()]
        # Remove consecutive blank lines
        filtered_lines = []
        last_blank = False
        for line in lines:
            if not line:
                if not last_blank:
                    filtered_lines.append("")
                last_blank = True
            else:
                filtered_lines.append(line)
                last_blank = False

        return "\n".join(filtered_lines).strip()

    def get_shingles(self, text: str, k: int = 3) -> Set[str]:
        """Compute word k-shingles for Jaccard similarity."""
        words = re.findall(r'\b\w+\b', text.lower())
        if len(words) < k:
            return {" ".join(words)}
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

    def jaccard_similarity(self, s1: Set[str], s2: Set[str]) -> float:
        """Calculate Jaccard similarity coefficient between two shingle sets."""
        if not s1 or not s2:
            return 0.0
        intersection = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return intersection / union if union > 0 else 0.0

    def deduplicate_paragraphs(self, text: str, threshold: float = 0.85) -> Tuple[str, int]:
        """
        Detect and filter out near-duplicate paragraphs.
        Returns cleaned text and count of removed duplicates.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        unique_paragraphs: List[str] = []
        seen_shingles: List[Set[str]] = []
        duplicate_count = 0

        for p in paragraphs:
            shingles = self.get_shingles(p)
            is_dup = False
            for prev_shingles in seen_shingles:
                if self.jaccard_similarity(shingles, prev_shingles) >= threshold:
                    is_dup = True
                    duplicate_count += 1
                    break

            if not is_dup:
                unique_paragraphs.append(p)
                seen_shingles.append(shingles)

        return "\n\n".join(unique_paragraphs), duplicate_count

cleaner = DocumentCleaner()
