import pytest
from src.pii.detector import PIIDetector, pii_detector

def test_pii_detection_email():
    text = "Please send policy details to john.doe@example.com immediately."
    detection = pii_detector.detect(text)
    assert detection["has_pii"] is True
    assert "EMAIL" in detection["pii_types"]
    assert "john.doe@example.com" in detection["matches"]["EMAIL"]

def test_pii_detection_phone():
    text = "Call the applicant at +1 (555) 839-2041 to verify health records."
    detection = pii_detector.detect(text)
    assert detection["has_pii"] is True
    assert "PHONE" in detection["pii_types"]

def test_pii_detection_gov_id():
    text = "Tax ID submitted: SSN-902-48-1192 for underwriting verification."
    detection = pii_detector.detect(text)
    assert detection["has_pii"] is True
    assert "GOV_ID" in detection["pii_types"]

def test_pii_detection_address():
    text = "Customer address is 742 Evergreen Terrace, Springfield, OR 97477."
    detection = pii_detector.detect(text)
    assert detection["has_pii"] is True
    assert "ADDRESS" in detection["pii_types"]

def test_pii_masking_comprehensive():
    sample_text = (
        "My name is Marcus Aurelius Vance, residing at 742 Evergreen Terrace, Springfield, OR 97477.\n"
        "My contact telephone number is +1 (555) 839-2041, and my tax identification number is SSN-902-48-1192.\n"
        "Reach out at marcus.vance.test@example.com."
    )
    masked_text, meta = pii_detector.mask(sample_text)
    assert meta["has_pii"] is True
    assert set(meta["pii_types"]) == {"NAME", "ADDRESS", "PHONE", "GOV_ID", "EMAIL"}

    # Ensure sensitive raw tokens are scrubbed
    assert "Marcus Aurelius Vance" not in masked_text
    assert "marcus.vance.test@example.com" not in masked_text
    assert "SSN-902-48-1192" not in masked_text
    assert "+1 (555) 839-2041" not in masked_text
    assert "742 Evergreen Terrace" not in masked_text

    # Ensure semantic mask tokens appear
    assert "[NAME_MASKED]" in masked_text
    assert "[EMAIL_MASKED]" in masked_text
    assert "[PHONE_MASKED]" in masked_text
    assert "[GOV_ID_MASKED]" in masked_text
    assert "[ADDRESS_MASKED]" in masked_text

def test_pii_clean_text_no_false_positives():
    clean_policy_text = (
        "HealthShield Gold Plan offers up to $350,000 annual sum insured. "
        "Pre-existing conditions have a 36-month waiting period."
    )
    masked_text, meta = pii_detector.mask(clean_policy_text)
    assert meta["has_pii"] is False
    assert meta["pii_types"] == []
    assert masked_text == clean_policy_text
