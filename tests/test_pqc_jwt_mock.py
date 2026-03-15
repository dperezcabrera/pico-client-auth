"""Tests for pqc_jwt module using mocked oqs (no liboqs required)."""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from pico_client_auth.errors import AuthConfigurationError, TokenExpiredError, TokenInvalidError
from pico_client_auth.pqc_jwt import (
    _b64url_decode,
    _import_oqs,
    _split_token,
    _validate_claims,
    decode_and_verify,
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_token(header: dict, payload: dict, signature: bytes = b"fake-sig") -> str:
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    s = _b64url_encode(signature)
    return f"{h}.{p}.{s}"


def _valid_payload(**overrides) -> dict:
    base = {
        "sub": "user-1",
        "email": "u@test.com",
        "role": "admin",
        "org_id": "org-1",
        "jti": "j1",
        "iss": "https://auth.example.com",
        "aud": "my-api",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    base.update(overrides)
    return base


class TestB64urlDecode:
    def test_decodes_padded(self):
        original = b"hello world"
        encoded = base64.urlsafe_b64encode(original).rstrip(b"=").decode()
        assert _b64url_decode(encoded) == original

    def test_decodes_already_padded(self):
        original = b"test"
        encoded = base64.urlsafe_b64encode(original).decode()
        assert _b64url_decode(encoded) == original


class TestImportOqs:
    def test_raises_when_oqs_not_installed(self):
        with patch.dict("sys.modules", {"oqs": None}):
            with pytest.raises(AuthConfigurationError, match="liboqs-python"):
                _import_oqs()

    def test_returns_oqs_when_installed(self):
        mock_oqs = MagicMock()
        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            result = _import_oqs()
            assert result is mock_oqs


class TestSplitToken:
    def test_valid_three_parts(self):
        a, b, c = _split_token("aaa.bbb.ccc")
        assert (a, b, c) == ("aaa", "bbb", "ccc")

    def test_two_parts_raises(self):
        with pytest.raises(TokenInvalidError, match="expected 3 parts"):
            _split_token("aaa.bbb")

    def test_four_parts_raises(self):
        with pytest.raises(TokenInvalidError, match="expected 3 parts"):
            _split_token("a.b.c.d")


class TestValidateClaims:
    def test_valid_claims_pass(self):
        claims = _valid_payload()
        _validate_claims(claims, "https://auth.example.com", "my-api")

    def test_expired_raises(self):
        claims = _valid_payload(exp=int(time.time()) - 60)
        with pytest.raises(TokenExpiredError, match="expired"):
            _validate_claims(claims, "https://auth.example.com", "my-api")

    def test_no_exp_passes(self):
        claims = _valid_payload()
        del claims["exp"]
        _validate_claims(claims, "https://auth.example.com", "my-api")

    def test_wrong_issuer_raises(self):
        claims = _valid_payload()
        with pytest.raises(TokenInvalidError, match="issuer"):
            _validate_claims(claims, "https://wrong.com", "my-api")

    def test_wrong_audience_raises(self):
        claims = _valid_payload()
        with pytest.raises(TokenInvalidError, match="audience"):
            _validate_claims(claims, "https://auth.example.com", "wrong-aud")

    def test_audience_list_valid(self):
        claims = _valid_payload(aud=["my-api", "other-api"])
        _validate_claims(claims, "https://auth.example.com", "my-api")

    def test_audience_list_invalid(self):
        claims = _valid_payload(aud=["other-api"])
        with pytest.raises(TokenInvalidError, match="audience"):
            _validate_claims(claims, "https://auth.example.com", "my-api")


class TestDecodeAndVerify:
    def test_unsupported_algorithm_raises(self):
        with pytest.raises(TokenInvalidError, match="Unsupported PQC algorithm"):
            decode_and_verify("a.b.c", b"key", "ML-DSA-44", "iss", "aud")

    def test_algorithm_mismatch_raises(self):
        mock_oqs = MagicMock()
        token = _make_token({"alg": "ML-DSA-87", "typ": "JWT"}, _valid_payload())
        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenInvalidError, match="Algorithm mismatch"):
                decode_and_verify(token, b"key", "ML-DSA-65", "https://auth.example.com", "my-api")

    def test_valid_token_with_mock_oqs(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = True
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        payload = _valid_payload()
        token = _make_token({"alg": "ML-DSA-65", "typ": "JWT"}, payload)

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            claims = decode_and_verify(token, b"key", "ML-DSA-65", "https://auth.example.com", "my-api")
            assert claims["sub"] == "user-1"
            mock_oqs.Signature.assert_called_once_with("ML-DSA-65")
            mock_verifier.verify.assert_called_once()

    def test_invalid_signature_raises(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = False
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        token = _make_token({"alg": "ML-DSA-65", "typ": "JWT"}, _valid_payload())

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenInvalidError, match="Invalid signature"):
                decode_and_verify(token, b"key", "ML-DSA-65", "https://auth.example.com", "my-api")

    def test_verify_exception_raises(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.side_effect = RuntimeError("oqs internal error")
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        token = _make_token({"alg": "ML-DSA-65", "typ": "JWT"}, _valid_payload())

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenInvalidError, match="Signature verification failed"):
                decode_and_verify(token, b"key", "ML-DSA-65", "https://auth.example.com", "my-api")

    def test_invalid_header_raises(self):
        mock_oqs = MagicMock()
        bad_header = _b64url_encode(b"not-json")
        payload_b64 = _b64url_encode(b'{"sub":"x"}')
        sig_b64 = _b64url_encode(b"sig")
        token = f"{bad_header}.{payload_b64}.{sig_b64}"

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenInvalidError, match="Invalid JWT header"):
                decode_and_verify(token, b"key", "ML-DSA-65", "iss", "aud")

    def test_expired_token_raises(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = True
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        payload = _valid_payload(exp=int(time.time()) - 60)
        token = _make_token({"alg": "ML-DSA-65", "typ": "JWT"}, payload)

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenExpiredError, match="expired"):
                decode_and_verify(token, b"key", "ML-DSA-65", "https://auth.example.com", "my-api")

    def test_malformed_token_raises(self):
        mock_oqs = MagicMock()
        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            with pytest.raises(TokenInvalidError, match="expected 3 parts"):
                decode_and_verify("only.two", b"key", "ML-DSA-65", "iss", "aud")

    def test_mldsa87_valid(self):
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = True
        mock_oqs = MagicMock()
        mock_oqs.Signature.return_value = mock_verifier

        payload = _valid_payload()
        token = _make_token({"alg": "ML-DSA-87", "typ": "JWT"}, payload)

        with patch.dict("sys.modules", {"oqs": mock_oqs}):
            claims = decode_and_verify(token, b"key", "ML-DSA-87", "https://auth.example.com", "my-api")
            assert claims["sub"] == "user-1"
            mock_oqs.Signature.assert_called_once_with("ML-DSA-87")
