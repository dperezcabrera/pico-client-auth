"""Tests for pqc_jwt module (ML-DSA JWT decode and verification)."""

from datetime import timedelta

import pytest

oqs = pytest.importorskip("oqs")

from pico_client_auth.errors import AuthConfigurationError, TokenExpiredError, TokenInvalidError
from pico_client_auth.pqc_jwt import decode_and_verify


class TestValidMLDSA65:
    def test_valid_token_decodes(self, mldsa65_keypair, make_pqc_token):
        public_key, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key, algorithm="ML-DSA-65", kid="pqc-key-65")
        claims = decode_and_verify(token, public_key, "ML-DSA-65", "https://auth.example.com", "my-api")
        assert claims["sub"] == "user-123"
        assert claims["email"] == "user@example.com"
        assert claims["role"] == "admin"
        assert claims["org_id"] == "org-1"


class TestValidMLDSA87:
    def test_valid_token_decodes(self, mldsa87_keypair, make_pqc_token):
        public_key, secret_key = mldsa87_keypair
        token = make_pqc_token(secret_key, algorithm="ML-DSA-87", kid="pqc-key-87")
        claims = decode_and_verify(token, public_key, "ML-DSA-87", "https://auth.example.com", "my-api")
        assert claims["sub"] == "user-123"
        assert claims["iss"] == "https://auth.example.com"


class TestExpiredToken:
    def test_expired_token_raises(self, mldsa65_keypair, make_pqc_token):
        public_key, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key, expires_delta=timedelta(seconds=-60))
        with pytest.raises(TokenExpiredError, match="expired"):
            decode_and_verify(token, public_key, "ML-DSA-65", "https://auth.example.com", "my-api")


class TestBadSignature:
    def test_wrong_key_raises(self, mldsa65_keypair, make_pqc_token):
        _, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key)

        # Verify against a different key pair
        other_sig = oqs.Signature("ML-DSA-65")
        other_pub = other_sig.generate_keypair()

        with pytest.raises(TokenInvalidError):
            decode_and_verify(token, other_pub, "ML-DSA-65", "https://auth.example.com", "my-api")


class TestWrongAudience:
    def test_wrong_audience_raises(self, mldsa65_keypair, make_pqc_token):
        public_key, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key)
        with pytest.raises(TokenInvalidError, match="audience"):
            decode_and_verify(token, public_key, "ML-DSA-65", "https://auth.example.com", "wrong-audience")


class TestWrongIssuer:
    def test_wrong_issuer_raises(self, mldsa65_keypair, make_pqc_token):
        public_key, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key)
        with pytest.raises(TokenInvalidError, match="issuer"):
            decode_and_verify(token, public_key, "ML-DSA-65", "https://wrong-issuer.com", "my-api")


class TestUnsupportedAlgorithm:
    def test_unsupported_algorithm_raises(self, mldsa65_keypair, make_pqc_token):
        public_key, secret_key = mldsa65_keypair
        token = make_pqc_token(secret_key)
        with pytest.raises(TokenInvalidError, match="Unsupported PQC algorithm"):
            decode_and_verify(token, public_key, "ML-DSA-44", "https://auth.example.com", "my-api")


class TestMalformedToken:
    def test_missing_parts_raises(self, mldsa65_keypair):
        public_key, _ = mldsa65_keypair
        with pytest.raises(TokenInvalidError, match="Malformed JWT"):
            decode_and_verify("not.a-valid-token", public_key, "ML-DSA-65", "https://auth.example.com", "my-api")
