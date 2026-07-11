"""Integration with pico-fastapi controllers: markers must be honored.

client-auth's other e2e tests use raw @app.get routes; THIS is the pairing
that was never tested and silently broke (markers lost on the DI wrapper,
nested routers on starlette >= 1.x). Requires pico-fastapi (test dep).
"""

import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pico_fastapi import controller, get
from pico_ioc import DictSource, configuration, init

from pico_client_auth import allow_anonymous


@controller(prefix="/it")
class ItController:
    @allow_anonymous
    @get("/public")
    async def public(self):
        return {"ok": True}

    @get("/private")
    async def private(self):
        return {"secret": True}


def test_controller_markers_enforced():
    cfg = configuration(
        DictSource(
            {
                "fastapi": {"title": "t"},
                "auth_client": {"enabled": True, "issuer": "http://t", "audience": "t"},
            }
        )
    )
    container = init(modules=["pico_fastapi", "pico_client_auth", sys.modules[__name__]], config=cfg)
    with TestClient(container.get(FastAPI)) as client:
        assert client.get("/it/public").status_code == 200
        assert client.get("/it/private").status_code == 401
