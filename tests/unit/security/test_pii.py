"""Test PII detection (PT-BR + international patterns)."""
import pytest
from empire.security.pii import detect_pii, redact_pii


class TestPIIDetection:
    """Test PII detection patterns."""
    
    def test_detect_cpf(self, pii_test_text):
        """Should detect Brazilian CPF."""
        results = detect_pii(pii_test_text)
        cpf = [r for r in results if r["entity_type"] == "CPF"]
        assert len(cpf) > 0
        assert "123.456.789-09" in cpf[0]["text"] or "12345678909" in cpf[0]["text"]
    
    def test_detect_cnpj(self, pii_test_text):
        """Should detect Brazilian CNPJ."""
        results = detect_pii(pii_test_text)
        cnpj = [r for r in results if r["entity_type"] == "CNPJ"]
        assert len(cnpj) > 0
    
    def test_detect_email(self, pii_test_text):
        """Should detect email addresses."""
        results = detect_pii(pii_test_text)
        emails = [r for r in results if r["entity_type"] == "EMAIL_ADDRESS"]
        assert len(emails) > 0
        assert "joao@example.com" in emails[0]["text"]
    
    def test_detect_phone_br(self, pii_test_text):
        """Should detect Brazilian phone (9-digit mobile)."""
        results = detect_pii(pii_test_text)
        phones = [r for r in results if r["entity_type"] == "PHONE_NUMBER"]
        assert len(phones) > 0
    
    def test_detect_credit_card(self, pii_test_text):
        """Should detect credit card numbers."""
        results = detect_pii(pii_test_text)
        cc = [r for r in results if r["entity_type"] == "CREDIT_CARD"]
        assert len(cc) > 0
    
    def test_detect_cep(self, pii_test_text):
        """Should detect Brazilian CEP."""
        results = detect_pii(pii_test_text)
        ceps = [r for r in results if r["entity_type"] == "CEP"]
        assert len(ceps) > 0
    
    def test_detect_rg(self, pii_test_text):
        """Should detect Brazilian RG."""
        results = detect_pii(pii_test_text)
        rgs = [r for r in results if r["entity_type"] == "RG"]
        assert len(rgs) > 0
    
    def test_detect_ipv4(self, pii_test_text):
        """Should detect IPv4 addresses."""
        results = detect_pii(pii_test_text)
        ips = [r for r in results if r["entity_type"] == "IP_ADDRESS"]
        assert len(ips) > 0
    
    def test_detect_bearer_token(self, pii_test_text):
        """Should detect Bearer tokens."""
        results = detect_pii(pii_test_text)
        tokens = [r for r in results if r["entity_type"] == "BEARER_TOKEN"]
        assert len(tokens) > 0
    
    def test_detect_openai_key(self, pii_test_text):
        """Should detect OpenAI API keys."""
        results = detect_pii(pii_test_text)
        keys = [r for r in results if r["entity_type"] == "OPENAI_KEY"]
        assert len(keys) > 0
    
    def test_detect_no_pii(self):
        """Should return empty list for clean text."""
        results = detect_pii("Hello world, this is a clean text.")
        assert len(results) == 0
    
    def test_redact_cpf(self):
        """Should replace CPF with mask."""
        text = "Meu CPF é 123.456.789-09 e mora em SP"
        redacted = redact_pii(text)
        assert "123.456.789-09" not in redacted
        assert "***" in redacted or "[REDACTED]" in redacted


class TestPIIStrategies:
    """Test different redaction strategies."""
    
    def test_mask_strategy(self):
        """mask strategy should keep some chars."""
        from empire.security.pii import redact_pii
        text = "Email: joao@example.com"
        redacted = redact_pii(text, strategy="mask")
        assert "joao" not in redacted
        assert "@" not in redacted
    
    def test_replace_strategy(self):
        """replace strategy should use [REDACTED]."""
        from empire.security.pii import redact_pii
        text = "Email: joao@example.com"
        redacted = redact_pii(text, strategy="replace")
        assert "[REDACTED]" in redacted
