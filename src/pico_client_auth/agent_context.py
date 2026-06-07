"""Agent identity context — companion to ``SecurityContext``.

Where ``SecurityContext`` carries the *service* identity (what HTTP
caller signed the request — proven by ``Authorization: Bearer ...``),
``AgentContext`` carries the *agent* identity propagated alongside
(``X-Agent-Authorization: Bearer ...``). Both can coexist on the same
request: one says WHO the calling service is, the other says WHO is
the LLM agent acting on behalf of WHICH user, with WHAT scopes and
spend limits.

Agent tokens are JWTs validated through the same `TokenValidator` as
service tokens (same algorithm, same JWKS, same issuer/audience for
now — split into a separate validator later if/when the head-agent
issuer differs from the service issuer).

This module is import-time safe: declaring `AgentClaims` and
`AgentContext` does NOT require any service to be running.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AgentClaims:
    """Immutable representation of the agentic claims carried in the
    `X-Agent-Authorization` JWT.

    Required claims (the issuer must populate these):
      - `sub`: agent identifier (e.g. "purchaser-agent-instance-42")
      - `task_type`: free-form ("interactive_purchase", "scheduled_audit")
      - `user_id`: the human in whose name the agent acts
      - `scopes`: list of scope strings the agent is allowed to invoke
                  (e.g. "treasury:write:budget:opex")

    Optional but recommended:
      - `session_id`, `conversation_id`: the conversational context
      - `task_id`: per-task identifier (for spend-limit accounting)
      - `org_id`: the customer's tenant
      - `role`: an agent role (separate from the service role)
      - `spend_limit`: decimal string — total budget for this task
      - `parent_chain`: tuple of mcp-ids that delegated this token down
                       (innermost first: ["io.acme.head-agent",
                       "io.acme.purchaser"])

    `raw_claims` keeps the original dict so the consumer can read
    custom fields without a round-trip through this dataclass."""

    sub: str = ""
    task_type: str = ""
    user_id: str = ""
    session_id: str = ""
    conversation_id: str = ""
    task_id: str = ""
    org_id: str = ""
    role: str = ""
    spend_limit: str = ""
    scopes: tuple[str, ...] = ()
    parent_chain: tuple[str, ...] = ()
    raw_claims: dict[str, Any] | None = None

    @classmethod
    def from_claims_dict(cls, raw: dict[str, Any]) -> "AgentClaims":
        """Build an `AgentClaims` from a JWT payload dict."""
        return cls(
            sub=str(raw.get("sub", "")),
            task_type=str(raw.get("task_type", "")),
            user_id=str(raw.get("user_id", "")),
            session_id=str(raw.get("session_id", "")),
            conversation_id=str(raw.get("conversation_id", "")),
            task_id=str(raw.get("task_id", "")),
            org_id=str(raw.get("org_id", "")),
            role=str(raw.get("role", "")),
            spend_limit=str(raw.get("spend_limit", "")),
            scopes=tuple(raw.get("scopes") or []),
            parent_chain=tuple(raw.get("parent_chain") or []),
            raw_claims=dict(raw),
        )


_agent_var: ContextVar[Optional[AgentClaims]] = ContextVar(
    "_pico_auth_agent",
    default=None,
)


class AgentContext:
    """Singleton-style accessor for the per-request agent identity.

    Mirrors `SecurityContext` API. All methods are static; storage uses
    a `ContextVar` so each async task / thread has its own copy."""

    @staticmethod
    def get() -> Optional[AgentClaims]:
        return _agent_var.get()

    @staticmethod
    def is_present() -> bool:
        return _agent_var.get() is not None

    @staticmethod
    def get_scopes() -> tuple[str, ...]:
        agent = _agent_var.get()
        return agent.scopes if agent else ()

    @staticmethod
    def has_scope(scope: str) -> bool:
        return scope in AgentContext.get_scopes()

    @staticmethod
    def set(agent: AgentClaims) -> None:
        _agent_var.set(agent)

    @staticmethod
    def clear() -> None:
        _agent_var.set(None)
