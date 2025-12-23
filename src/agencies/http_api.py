from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from src.agents.rag_agent import answer_query
from src.pipelines.ingest import IngestResult, ingest_content
from src.schemas.models import IngestRequest, QueryRequest, QueryResponse

QueryHandler = Callable[[QueryRequest], Awaitable[QueryResponse]]
IngestHandler = Callable[..., IngestResult]


@dataclass
class HttpAPIAgency:
    """Lightweight wrapper that wires HTTP-facing flows to core agent logic."""

    query_handler: QueryHandler = answer_query
    ingest_handler: IngestHandler = ingest_content

    async def query(self, request: QueryRequest) -> QueryResponse:
        """Resolve a user query using the configured handler."""
        return await self.query_handler(request)

    def ingest(self, request: IngestRequest) -> IngestResult:
        """Ingest raw content into the corpus via the configured handler."""
        return self.ingest_handler(
            request.content,
            source_name=request.source_name,
            doc_id=request.doc_id,
            language=request.language,
            domain=request.domain,
            freshness=request.freshness,
            url=request.url,
            tags=request.tags or None,
            max_chars=request.max_chars,
            overlap=request.overlap,
        )
