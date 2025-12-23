from fastapi.routing import APIRoute

from src.agents.http_api import app


def test_admin_prompts_upsert_registered_once() -> None:
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/v1/admin/prompts"
        and "POST" in route.methods
    ]
    assert len(routes) == 1



def test_rate_limit_identity_includes_path() -> None:
    from src.agents.http_api import _rate_limit_identity

    key = _rate_limit_identity("secret", "/v1/query")
    other = _rate_limit_identity("secret", "/v1/ingest")
    assert key != other
    assert key.startswith("secret:")


def test_rate_limit_identity_defaults_to_anonymous() -> None:
    from src.agents.http_api import _rate_limit_identity

    identity = _rate_limit_identity(None, "/v1/query")
    assert identity.startswith("anonymous:")
