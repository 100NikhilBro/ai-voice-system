import re
from typing import Tuple, List, Dict, Any

class PIIDetector:
    """
    PII Identification and Protection Engine.
    Identifies sensitive personal information (Names, Emails, Phones, Government IDs, Street Addresses)
    and performs deterministic attribute masking while flagging records with metadata.
    """

    # Compiled Regular Expressions for Common PII Patterns
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
    PHONE_PATTERN = re.compile(r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b')
    GOV_ID_PATTERN = re.compile(r'\b(?:SSN[-\s]?)?[0-9]{3}[-\s]?[0-9]{2}[-\s]?[0-9]{4}\b', re.IGNORECASE)
    ADDRESS_PATTERN = re.compile(r'\b\d{1,5}\s+[A-Za-z0-9\s.,]+(?:Terrace|Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way)\b(?:[A-Za-z0-9\s,]+[A-Z]{2}\s+\d{5})?', re.IGNORECASE)

    # Contextual Name Patterns for Support Tickets and Inquiries
    NAME_PATTERNS = [
        re.compile(r'(?:My name is|I am|Name:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', re.IGNORECASE),
        re.compile(r'(?:Sincerely|Regards|Thank you),\s*\n+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', re.MULTILINE),
        re.compile(r'(?:wife|husband|spouse|child|applicant|patient)(?:,\s*|\s+named\s+)([A-Z][a-z]+\s+[A-Z][a-z]+)', re.IGNORECASE)
    ]

    def detect(self, text: str) -> Dict[str, Any]:
        """Detect all PII entities and return classification details."""
        detected_types: List[str] = []
        matches: Dict[str, List[str]] = {}

        # 1. Emails
        emails = self.EMAIL_PATTERN.findall(text)
        if emails:
            detected_types.append("EMAIL")
            matches["EMAIL"] = emails

        # 2. Phone Numbers
        phones = self.PHONE_PATTERN.findall(text)
        if phones:
            detected_types.append("PHONE")
            matches["PHONE"] = phones

        # 3. Government / Tax IDs
        gov_ids = self.GOV_ID_PATTERN.findall(text)
        if gov_ids:
            detected_types.append("GOV_ID")
            matches["GOV_ID"] = gov_ids

        # 4. Physical Street Addresses
        addresses = self.ADDRESS_PATTERN.findall(text)
        if addresses:
            detected_types.append("ADDRESS")
            matches["ADDRESS"] = addresses

        # 5. Names via Contextual Patterns
        names = []
        for pat in self.NAME_PATTERNS:
            found = pat.findall(text)
            if found:
                for item in found:
                    if isinstance(item, tuple):
                        item = item[0]
                    item = item.strip()
                    if item and item not in names:
                        names.append(item)
        if names:
            detected_types.append("NAME")
            matches["NAME"] = names

        has_pii = len(detected_types) > 0
        return {
            "has_pii": has_pii,
            "pii_types": detected_types,
            "matches": matches
        }

    def mask(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Mask detected PII with semantic tokens and return masked text + metadata.
        Example: 'Marcus Vance' -> '[NAME_MASKED]'
        """
        detection = self.detect(text)
        if not detection["has_pii"]:
            return text, detection

        masked_text = text

        # Mask Street Addresses first to avoid partial numeric collisions
        if "ADDRESS" in detection["matches"]:
            for addr in detection["matches"]["ADDRESS"]:
                masked_text = masked_text.replace(addr, "[ADDRESS_MASKED]")

        # Mask Emails
        if "EMAIL" in detection["matches"]:
            for email in detection["matches"]["EMAIL"]:
                masked_text = masked_text.replace(email, "[EMAIL_MASKED]")

        # Mask Government / Tax IDs
        if "GOV_ID" in detection["matches"]:
            for gid in detection["matches"]["GOV_ID"]:
                masked_text = masked_text.replace(gid, "[GOV_ID_MASKED]")

        # Mask Phone Numbers
        if "PHONE" in detection["matches"]:
            for phone in detection["matches"]["PHONE"]:
                masked_text = masked_text.replace(phone, "[PHONE_MASKED]")

        # Mask Names
        if "NAME" in detection["matches"]:
            for name in detection["matches"]["NAME"]:
                masked_text = masked_text.replace(name, "[NAME_MASKED]")

        return masked_text, detection

pii_detector = PIIDetector()
