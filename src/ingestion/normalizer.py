import re
from typing import Dict, Any

class TerminologyNormalizer:
    """
    Standardizes insurance terminology, category classifications, and document headings.
    Ensures consistent semantic representations across disparate source documents.
    """

    CATEGORY_MAP = {
        "brochure": "product_info",
        "product": "product_info",
        "plans": "product_info",
        "underwriting": "policy_underwriting",
        "policy": "policy_underwriting",
        "guideline": "policy_underwriting",
        "qual": "qualification_rules",
        "eligibility": "qualification_rules",
        "faq": "faq_and_objections",
        "objection": "faq_and_objections",
        "inquiry": "customer_inquiry_samples",
        "ticket": "customer_inquiry_samples"
    }

    TERMINOLOGY_SYNONYMS = [
        (re.compile(r'\bPED\b', re.IGNORECASE), "Pre-Existing Condition (PED)"),
        (re.compile(r'\bOPD\b', re.IGNORECASE), "Outpatient Department Consultation (OPD)"),
        (re.compile(r'\bCo-pay\b', re.IGNORECASE), "Copayment"),
        (re.compile(r'\bCopay\b', re.IGNORECASE), "Copayment"),
        (re.compile(r'\bTPA\b', re.IGNORECASE), "Third-Party Administrator (TPA)"),
        (re.compile(r'\bNCB\b', re.IGNORECASE), "No-Claim Bonus (NCB)")
    ]

    def normalize_category(self, filename: str, explicit_category: str = "") -> str:
        """Derive or normalize category into standard taxonomy."""
        if explicit_category:
            norm = explicit_category.lower().strip()
            for key, val in self.CATEGORY_MAP.items():
                if key in norm:
                    return val

        fn = filename.lower()
        for key, val in self.CATEGORY_MAP.items():
            if key in fn:
                return val

        return "policy_underwriting"

    def normalize_terminology(self, text: str) -> str:
        """Expand and standardize financial/insurance abbreviations."""
        normalized = text
        for pattern, replacement in self.TERMINOLOGY_SYNONYMS:
            normalized = pattern.sub(replacement, normalized)
        return normalized

normalizer = TerminologyNormalizer()
