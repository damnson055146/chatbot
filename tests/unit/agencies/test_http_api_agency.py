import pytest

from src.agencies.http_api import HttpAPIAgency
from src.schemas.models import IngestRequest, QueryRequest, QueryResponse


@pytest.mark.asyncio
async def test_http_api_agency_query_invokes_handler():
    captured = {}

    async def fake_query(request: QueryRequest) -> QueryResponse:
        captured["request"] = request
        return QueryResponse(
            answer="ok",
            citations=[],
            trace_id="trace",
            session_id="session",
        )

    agency = HttpAPIAgency(query_handler=fake_query)
    request = QueryRequest(question="Hello there")

    result = await agency.query(request)

    assert result.answer == "ok"
    assert captured["request"] is request


def test_http_api_agency_ingest_invokes_handler():
    captured = {}

    def fake_ingest(content: str, **kwargs):
        captured["content"] = content
        captured["kwargs"] = kwargs
        return "ingested"

    agency = HttpAPIAgency(ingest_handler=fake_ingest)
    request = IngestRequest(
        source_name="visa_rules",
        content="Student visa requires proof of funds.",
        doc_id=None,
        language="en",
        domain="visa",
        freshness="2025-01-01",
        url="https://example.edu/visa",
        tags=["policy"],
        max_chars=400,
        overlap=40,
    )

    result = agency.ingest(request)

    assert result == "ingested"
    assert captured["content"] == request.content
    assert captured["kwargs"]["source_name"] == request.source_name
    assert captured["kwargs"]["language"] == request.language
    assert captured["kwargs"]["tags"] == request.tags
    assert captured["kwargs"]["max_chars"] == request.max_chars
