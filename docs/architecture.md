# Architecture Overview -- pico-client-auth

`pico-client-auth` is a thin authentication layer that sits between **pico-fastapi**'s middleware pipeline and your application controllers. Its purpose is to validate JWT tokens, populate a request-scoped `SecurityContext`, and enforce role-based access control.

---

## 1. High-Level Design

```mermaid
graph TD
    subgraph FastAPI_Layer [FastAPI Host]
        API[FastAPI Application]
    end

    subgraph Auth_Layer [pico-client-auth]
        MW[Auth Middleware]
        TV[TokenValidator]
        JC[JWKSClient]
        RR[RoleResolver]
        SC[SecurityContext]
    end

    subgraph IoC_Layer [Pico-IoC]
        Container[Container]
        Config[AuthClientSettings]
    end

    subgraph Auth_Server [External Auth Server]
        JWKS[JWKS Endpoint]
    end

    API -->|priority=10| MW
    MW -->|Validates token| TV
    TV -->|Fetches keys| JC
    JC -->|HTTP GET| JWKS
    MW -->|Resolves roles| RR
    MW -->|Populates| SC
    Container -->|Provides| Config
    Container -->|Injects| TV
    Container -->|Injects| JC
    Container -->|Injects| RR
```

---

## 2. Request Lifecycle

```mermaid
sequenceDiagram
    participant Client
    participant Outer as Outer Middleware<br/>(CORS, Session)
    participant Scope as PicoScopeMiddleware
    participant Auth as AuthFastapiConfigurer<br/>(priority=10)
    participant Handler as Controller Method

    Client->>Outer: HTTP Request
    activate Outer
    Outer->>Scope: Forward
    activate Scope
    Scope->>Scope: Create request scope
    Scope->>Auth: Forward (scope active)
    activate Auth

    Note over Auth: 1. Match route endpoint
    Note over Auth: 2. Check @allow_anonymous

    alt @allow_anonymous
        Auth->>Handler: Skip auth, forward
    else Requires auth
        Note over Auth: 3. Extract Bearer token
        Auth->>Auth: TokenValidator.validate(token)
        Auth->>Auth: RoleResolver.resolve(claims)
        Auth->>Auth: SecurityContext.set(claims, roles)

        alt @requires_role and missing role
            Auth-->>Client: 403 Forbidden
        else
            Auth->>Handler: Forward (context populated)
            activate Handler
            Handler->>Handler: SecurityContext.require()
            Handler-->>Auth: Response
            deactivate Handler
        end
    end

    Auth->>Auth: SecurityContext.clear() [finally]
    Auth-->>Scope: Response
    deactivate Auth
    Scope->>Scope: Cleanup request scope
    Scope-->>Outer: Response
    deactivate Scope
    Outer-->>Client: HTTP Response
    deactivate Outer
```

---

## 3. Component Model

### Internal Components (not exported)

| Component | Type | Responsibility |
|-----------|------|----------------|
| `JWKSClient` | `@component` singleton | Fetch and cache JWKS with TTL |
| `TokenValidator` | `@component` singleton | Decode JWT, validate signature/issuer/audience |
| `DefaultRoleResolver` | `@component` fallback | Extract `[claims.role]` as default role list |
| `AuthFastapiConfigurer` | `@component` singleton | Register middleware, enforce config, wire pipeline |

### Public API (exported)

| Symbol | Type | Description |
|--------|------|-------------|
| `SecurityContext` | Static class | ContextVar-backed accessor for claims and roles |
| `TokenClaims` | `@dataclass(frozen=True)` | Immutable JWT claim fields |
| `allow_anonymous` | Decorator | Skip auth on endpoint |
| `requires_role` | Decorator | Require specific role(s) |
| `RoleResolver` | Protocol | Override role extraction logic |
| `AuthClientSettings` | `@configured` dataclass | Configuration from `auth_client` prefix |

---

## 4. JWKS Key Management

```mermaid
stateDiagram-v2
    [*] --> Empty: App starts
    Empty --> Fetched: First token arrives → fetch JWKS
    Fetched --> Fetched: kid found in cache → use cached key
    Fetched --> Refreshing: kid NOT found (key rotation)
    Refreshing --> Fetched: Re-fetch JWKS, kid found
    Refreshing --> Error: kid still not found → KeyError
    Fetched --> Expired: TTL elapsed
    Expired --> Fetched: Next request → re-fetch JWKS
```

The `JWKSClient` caches all signing keys indexed by `kid`. When a token arrives with an unknown `kid`:

1. Force-refresh the JWKS cache (handles key rotation)
2. If the `kid` is still not found, raise `KeyError` (wrapped as `TokenInvalidError`)

---

## 5. Middleware Priority

`AuthFastapiConfigurer` uses `priority = 10`, placing it as an **inner** middleware (after `PicoScopeMiddleware`):

```mermaid
graph TB
    subgraph Outer ["Outer Configurers (priority < 0)"]
        direction TB
        O1["priority = -100<br/>e.g. CORS"]
        O2["priority = -50<br/>e.g. Session"]
    end

    SM[PicoScopeMiddleware<br/>request / session / websocket scopes]

    subgraph Inner ["Inner Configurers (priority >= 0)"]
        direction TB
        I1["priority = 0<br/>e.g. Health routes"]
        I2["priority = 10<br/>AuthFastapiConfigurer"]
        I3["priority = 50<br/>e.g. Audit logging"]
        I1 --> I2 --> I3
    end

    Outer --> SM --> Inner
```

This means the auth middleware **has access to the pico-ioc request scope** and can resolve request-scoped services if needed.

---

## 6. SecurityContext Design

`SecurityContext` follows the Spring `SecurityContextHolder` pattern: a static class backed by `ContextVar` for async-safe, task-isolated storage.

```mermaid
graph LR
    MW[Auth Middleware] -->|set| CV[ContextVar<br/>claims + roles]
    Handler[Controller] -->|get/require| CV
    Service[Service Layer] -->|get/require| CV
    MW -->|clear in finally| CV
```

Key properties:

- **Async-safe**: Each `asyncio.Task` gets its own copy (ContextVar semantics)
- **No dependency injection required**: `SecurityContext.require()` can be called from any code within the request
- **Always cleaned up**: The `finally` block in the middleware ensures no leakage between requests

---

## 7. Error Response Model

All authentication/authorization errors return JSON with a consistent schema:

| Status | Condition | Response Body |
|--------|-----------|---------------|
| 401 | No Bearer token | `{"detail": "Missing or invalid Authorization header"}` |
| 401 | Expired token | `{"detail": "Token has expired"}` |
| 401 | Invalid signature | `{"detail": "Invalid token: ..."}` |
| 403 | Missing role | `{"detail": "Requires one of roles: ['admin']"}` |

---

## 8. Architectural Intent

**pico-client-auth exists to:**

- Provide **secure-by-default** authentication for pico-fastapi apps
- Keep auth logic **out of controllers** (declarative decorators instead)
- Support **JWKS-based key rotation** without application restarts
- Enable **testable security** via `RoleResolver` override and container overrides

It does *not* attempt to:

- Implement OAuth flows (login, token issuance, refresh)
- Manage user sessions or cookies
- Replace a full identity provider
- Handle API key authentication
