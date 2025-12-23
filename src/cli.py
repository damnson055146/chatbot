from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, Dict

import yaml
import uvicorn

from src.agents.rag_agent import answer_query
from src.pipelines.ingest import ingest_file
from src.schemas.models import QueryRequest
from src.utils.env import load_env_file
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.session import get_session_store

load_env_file()
log = get_logger(__name__)


def _load_config(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with cfg_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def _apply_config(config: Dict[str, Any]) -> None:
    retrieval = config.get("retrieval", {})
    alpha = retrieval.get("alpha")
    if alpha is not None:
        manager = get_index_manager()
        manager.configure(alpha=float(alpha))

    sf_cfg = config.get("siliconflow", {})
    env_map = {
        "base": "SILICONFLOW_BASE",
        "chat_model": "SILICONFLOW_MODEL",
        "embed_model": "SILICONFLOW_EMBED_MODEL",
        "rerank_model": "SILICONFLOW_RERANK_MODEL",
    }
    for key, env_var in env_map.items():
        value = sf_cfg.get(key)
        if value:
            os.environ[env_var] = str(value)

    auth_cfg = config.get("auth", {})
    if "api_token" in auth_cfg:
        log.warning("config_api_token_ignored", msg="Use .env for API_AUTH_TOKEN")
    if rate := auth_cfg.get("rate_limit"):
        os.environ["API_RATE_LIMIT"] = str(rate)
    if window := auth_cfg.get("rate_window"):
        os.environ["API_RATE_WINDOW"] = str(window)


def _parse_slots(raw_slots: list[str]) -> Dict[str, str]:
    slots: Dict[str, str] = {}
    for item in raw_slots:
        if "=" not in item:
            log.warning("slot_format_invalid", slot=item)
            continue
        key, value = item.split("=", 1)
        slots[key.strip()] = value.strip()
    return slots


def cmd_ingest(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    result = ingest_file(
        Path(args.path),
        doc_id=args.doc_id,
        language=args.language,
        domain=args.domain,
        freshness=args.freshness,
        url=args.url,
        tags=args.tags,
        max_chars=args.max_chars,
        overlap=args.overlap,
    )
    log.info(
        "ingest_complete",
        doc_id=result.document.doc_id,
        version=result.document.version,
        chunks=result.chunk_count,
        raw=str(result.raw_path),
        processed=str(result.chunk_path),
    )


def cmd_query(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    app_cfg = config.get("app", {})
    language = args.language or app_cfg.get("language", "auto")
    top_k = args.top_k if args.top_k is not None else app_cfg.get("top_k", 8)
    k_cite = args.k_cite if args.k_cite is not None else app_cfg.get("k_cite", 2)
    slots = _parse_slots(args.slot or [])
    reset_slots = args.reset_slot or []

    req = QueryRequest(
        question=args.question,
        language=language,
        k_cite=k_cite,
        top_k=top_k,
        slots=slots,
        session_id=args.session_id,
        reset_slots=reset_slots,
    )

    async def run() -> None:
        resp = await answer_query(req)
        log.info("answer", trace_id=resp.trace_id, session_id=resp.session_id)
        print(resp.answer)
        for i, c in enumerate(resp.citations, 1):
            print(f"[{i}] {c.doc_id}::{c.snippet} (score={c.score:.3f})")
        if resp.session_id:
            print(f"Session: {resp.session_id}")
        if resp.missing_slots:
            print("Missing slots:")
            for slot_name in resp.missing_slots:
                prompt = resp.slot_prompts.get(slot_name)
                if prompt:
                    print(f" - {slot_name}: {prompt}")
                else:
                    print(f" - {slot_name}")
        if resp.slot_suggestions:
            print("Guidance:")
            for suggestion in resp.slot_suggestions:
                print(f" - {suggestion}")

    asyncio.run(run())


def cmd_session(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    store = get_session_store()
    if args.list:
        sessions = store.list_sessions()
        if not sessions:
            print("No active sessions.")
            return
        for state in sessions:
            ttl = state.remaining_ttl_seconds if state.remaining_ttl_seconds is not None else "n/a"
            print(f"{state.session_id} | lang={state.language} | slots={state.slot_count} | ttl={ttl}s | updated={state.updated_at.isoformat()}")
        return

    if not args.session_id:
        raise SystemExit("Provide --session-id or --list to manage sessions.")

    if args.clear:
        if store.get(args.session_id) is None:
            print("Session not found.")
            return
        store.clear(args.session_id)
        print(f"Cleared session {args.session_id}")
        return

    payload = store.export(args.session_id)
    if payload is None:
        print("Session not found.")
        return

    print(f"Session: {payload.session_id} (language={payload.language})")
    if payload.slots:
        print("Slots:")
        for key, value in payload.slots.items():
            print(f" - {key}: {value}")
    else:
        print("Slots: (none)")
    ttl = payload.remaining_ttl_seconds if payload.remaining_ttl_seconds is not None else "n/a"
    print(f"TTL remaining: {ttl}s")
    print(f"Slot count: {payload.slot_count}")
    print(f"Created: {payload.created_at.isoformat()}")
    print(f"Updated: {payload.updated_at.isoformat()}")




def cmd_index_health(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    manager = get_index_manager()
    if args.refresh:
        manager.rebuild()
    health = manager.health()
    last_build = health.last_build_at.isoformat() if health.last_build_at else "n/a"
    print("Documents:", health.document_count)
    print("Chunks:", health.chunk_count)
    print("Last build:", last_build)
    if health.errors:
        print("Errors:")
        for err in health.errors:
            print(" -", err)


def cmd_rebuild_index(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    manager = get_index_manager()
    manager.rebuild()
    health = manager.health()
    log.info(
        "index_rebuild_complete",
        documents=health.document_count,
        chunks=health.chunk_count,
    )


def cmd_serve(args: argparse.Namespace, config: Dict[str, Any]) -> None:
    app_path = args.app
    host = args.host
    port = args.port
    reload = args.reload
    log.info("api_serve_start", app=app_path, host=host, port=port, reload=reload)
    uvicorn.run(app_path, host=host, port=port, reload=reload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Study-Abroad RAG Assistant CLI")
    parser.add_argument("--config", help="Path to YAML config", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Ingest a text/markdown file and build chunks")
    p_ing.add_argument("path", help="Path to input file (txt/md)")
    p_ing.add_argument("--doc-id", dest="doc_id")
    p_ing.add_argument("--language", default="auto")
    p_ing.add_argument("--domain")
    p_ing.add_argument("--freshness")
    p_ing.add_argument("--url")
    p_ing.add_argument("--tags", nargs="*", default=None, help="Optional tags for manifest")
    p_ing.add_argument("--max-chars", type=int, default=800)
    p_ing.add_argument("--overlap", type=int, default=120)
    p_ing.set_defaults(func=cmd_ingest)

    p_q = sub.add_parser("query", help="Ask a question against the indexed corpus")
    p_q.add_argument("question", help="User question")
    p_q.add_argument("--language")
    p_q.add_argument("--top-k", type=int)
    p_q.add_argument("--k-cite", type=int)
    p_q.add_argument(
        "--slot",
        action="append",
        default=[],
        help="Provide slot values as key=value; repeat for multiple slots",
    )
    p_q.add_argument("--session-id")
    p_q.add_argument(
        "--reset-slot",
        action="append",
        default=None,
        help="Remove a slot before querying; repeat per slot name",
    )
    p_q.set_defaults(func=cmd_query)

    p_session = sub.add_parser("session", help="Inspect or manage in-memory sessions")
    p_session.add_argument("--list", action="store_true", help="List all active sessions")
    p_session.add_argument("--session-id", help="Session identifier to inspect or clear")
    p_session.add_argument("--clear", action="store_true", help="Clear the specified session")
    p_session.set_defaults(func=cmd_session)


    p_health = sub.add_parser("index-health", help="Display index health information")
    p_health.add_argument("--refresh", action="store_true", help="Trigger a rebuild before reporting")
    p_health.set_defaults(func=cmd_index_health)

    p_rebuild = sub.add_parser("rebuild-index", help="Force an index rebuild")
    p_rebuild.set_defaults(func=cmd_rebuild_index)

    p_serve = sub.add_parser("serve", help="Run the HTTP API server")
    p_serve.add_argument("--app", default="src.agents.http_api:app", help="ASGI app import path")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    config = _load_config(args.config)
    _apply_config(config)
    args.func(args, config)


if __name__ == "__main__":
    main()

