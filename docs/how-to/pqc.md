# How to Enable Post-Quantum (ML-DSA) JWT Verification

This guide covers enabling ML-DSA-65 and ML-DSA-87 post-quantum signature verification in pico-client-auth.

---

## Prerequisites

- Python 3.11+ (tested on 3.11, 3.12, 3.13 and 3.14)
- `liboqs` C library installed on the system
- `liboqs-python` Python bindings

---

## Step 1: Install the PQC Extra

```bash
pip install pico-client-auth[pqc]
```

This installs `liboqs-python`, which provides Python bindings for the Open Quantum Safe liboqs C library.

> **Note**: `liboqs-python` requires the `liboqs` C library to be installed on the system. On systems where it's not available via package manager, build it from source (see [Docker Setup](#docker-setup) below).

---

## Step 2: Configure Accepted Algorithms

Add ML-DSA algorithms to `accepted_algorithms` in your configuration:

```yaml
# application.yaml
auth_client:
  issuer: https://auth.example.com
  audience: my-api
  accepted_algorithms:
    - RS256
    - ML-DSA-65
```

Supported algorithms:

| Algorithm | NIST Level | Key Size | Signature Size |
|-----------|-----------|----------|----------------|
| `ML-DSA-65` | Level 3 (minimum recommended) | 1,952 bytes | 3,309 bytes |
| `ML-DSA-87` | Level 5 (highest) | 2,592 bytes | 4,627 bytes |

---

## Step 3: Serve ML-DSA Keys via JWKS

Your auth server's JWKS endpoint must serve ML-DSA public keys using the `AKP` key type (per [draft-ietf-cose-dilithium](https://datatracker.ietf.org/doc/draft-ietf-cose-dilithium/)):

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-key-1",
      "alg": "RS256",
      "n": "...",
      "e": "AQAB"
    },
    {
      "kty": "AKP",
      "kid": "pqc-key-1",
      "alg": "ML-DSA-65",
      "pub": "<base64url-encoded raw public key bytes>"
    }
  ]
}
```

---

## How It Works

When a JWT arrives, `TokenValidator` reads the `alg` header and dispatches:

1. **RS256** tokens are verified via PyJWT (existing path)
2. **ML-DSA-65 / ML-DSA-87** tokens are verified via `pqc_jwt` using liboqs
3. Tokens with algorithms **not** in `accepted_algorithms` are rejected with `TokenInvalidError`

The dispatch is transparent — `SecurityContext`, `@requires_role`, `@requires_group`, and all other features work identically regardless of algorithm.

---

## Graceful Degradation

If `liboqs-python` is not installed but an ML-DSA token arrives, `AuthConfigurationError` is raised with a clear message:

```
liboqs-python is required for ML-DSA verification.
Install it with: pip install pico-client-auth[pqc]
```

RS256 tokens continue to work without liboqs.

---

## Docker Setup

For environments where liboqs is not available via package manager, build from source:

```dockerfile
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake gcc g++ git ninja-build && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/open-quantum-safe/liboqs /tmp/liboqs && \
    cmake -S /tmp/liboqs -B /tmp/liboqs/build \
        -GNinja -DBUILD_SHARED_LIBS=ON -DOQS_BUILD_ONLY_LIB=ON && \
    cmake --build /tmp/liboqs/build --parallel $(nproc) && \
    cmake --install /tmp/liboqs/build && \
    ldconfig && rm -rf /tmp/liboqs

RUN pip install pico-client-auth[pqc]
```

---

## Testing PQC Tokens

PQC test fixtures are provided in conftest.py (skip automatically when liboqs is not installed):

```python
import pytest

def test_mldsa65_token(mldsa65_keypair, make_pqc_token):
    oqs = pytest.importorskip("oqs")
    public_key, secret_key = mldsa65_keypair
    token = make_pqc_token(secret_key, algorithm="ML-DSA-65")
    # Use token in your test...
```

Run PQC tests via Docker:

```bash
make pqc-test
```

Or via tox (requires liboqs installed locally):

```bash
tox -e pqc-py312
```

---

## Migration Strategy

A typical migration path from RS256 to ML-DSA:

1. **Phase 1**: Add `ML-DSA-65` to `accepted_algorithms` alongside `RS256`
2. **Phase 2**: Auth server issues ML-DSA tokens for new clients, RS256 for existing
3. **Phase 3**: All clients migrated — remove `RS256` from `accepted_algorithms`

```yaml
# Phase 1: Accept both
auth_client:
  accepted_algorithms:
    - RS256
    - ML-DSA-65

# Phase 3: PQC only
auth_client:
  accepted_algorithms:
    - ML-DSA-65
```
