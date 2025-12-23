from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Dict, List

from src.schemas.models import Citation, QueryDiagnostics, QueryRequest, QueryResponse
from src.schemas.slots import SlotDefinition, missing_required_slots, get_slot_prompt
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.observability import get_metrics
from src.utils.rerank import get_reranker
from src.utils.session import get_session_store
from src.utils.siliconflow import chat_stream, chat
from src.utils.storage import get_active_prompt, get_doc_lookup
from src.schemas.models import HighlightSpan
from src.utils.tracing import start_span

log = get_logger(__name__)

_SYS_PROMPT_ZH_DEFAULT = (
    "你是一位留学咨询伙伴，需要以平静、富有同理心的语气交流。"
    " 优先使用已知槽位（如学生姓名、阶段、预算、联系方式等）进行个性化回应，清晰列出执行步骤，并在关键建议后附带编号引用。"
    " 遇到信息不足时，用自然对话方式说明缺口并温柔引导用户补充，而不是生硬列清单。"
)
_SYS_PROMPT_EN_DEFAULT = (
    "You are Lumi, a calm study-abroad copilot who speaks with warmth and clarity."
    " Use the provided slot details (name, stage, budget, contact, etc.) to personalize your tone, summarize the next best actions,"
    " and attach numbered citations to every key point. If context is missing, clearly and empathetically explain what you still"
    " need and invite the student to share it."
)


def _explain_like_new_hint(language: str) -> str:
    if language == "zh":
        return "请用简明易懂的方式解释，适合初次了解留学流程的用户，并在每个重点后附引用编号。"
    return "Explain in simple, beginner-friendly terms suitable for someone new to study-abroad, and include numbered citations after each key point."


def _answer_language(req: QueryRequest, session_language: str | None = None) -> str:
    lang = (req.language or "auto").lower()
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    if session_language in {"zh", "en"}:
        return session_language
    return "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in req.question) else "en"


def _slot_suggestions(language: str, missing: List[SlotDefinition]) -> List[str]:
    suggestions: List[str] = []
    for slot in missing:
        prompt_text = get_slot_prompt(slot.name, language) or slot.prompt or slot.description or slot.name.replace("_", " ")
        if language == "zh":
            if not prompt_text:
                prompt_text = slot.name
            if not any("一" <= ch <= "鿿" for ch in prompt_text):
                suggestion = f"请提供{prompt_text}"
            else:
                suggestion = prompt_text
            if suggestion and suggestion[-1] not in "。！？":
                suggestion += "。"
        else:
            if not prompt_text:
                prompt_text = slot.name.replace("_", " ")
            if prompt_text.endswith("?"):
                suggestion = prompt_text
            else:
                suggestion = f"Please provide {prompt_text.rstrip(".")}."
        suggestions.append(suggestion)
    return suggestions
def _system_prompt(language: str) -> str:
    record = get_active_prompt(language)
    if record:
        content = record.get("content")
        if content:
            return str(content)
    return _SYS_PROMPT_ZH_DEFAULT if language == "zh" else _SYS_PROMPT_EN_DEFAULT


def _personalization_notes(language: str, slots: Dict[str, Any]) -> str:
    lines: List[str] = []

    def _text(en: str, zh: str) -> str:
        return zh if language == "zh" else en

    def _clean(value: Any) -> str:
        return str(value).strip()

    name = _clean(slots.get("student_name", "")) if isinstance(slots, dict) else ""
    if name:
        lines.append(
            _text(
                f"Address the student as {name} and keep the tone reassuring.",
                f"称呼学生为{name}，保持温和的语气。",
            )
        )

    stage = _clean(slots.get("current_stage", ""))
    if stage:
        lines.append(
            _text(
                f"They are currently at this stage: {stage}. Tailor the steps accordingly.",
                f"当前阶段：{stage}，请针对该阶段安排步骤。",
            )
        )

    priority = _clean(slots.get("priority_concern", ""))
    if priority:
        lines.append(
            _text(
                f"Primary concern to resolve first: {priority}.",
                f"需要优先解决的核心问题：{priority}。",
            )
        )

    country = _clean(slots.get("target_country", ""))
    if country:
        lines.append(
            _text(
                f"Their destination of interest is {country}; align policy references to this country.",
                f"目标国家为{country}，引用信息需围绕该国政策。",
            )
        )

    timeframe = _clean(slots.get("timeframe", ""))
    if timeframe:
        lines.append(
            _text(
                f"Requested intake/start timeline: {timeframe}.", f"目标入学时间：{timeframe}。"
            )
        )

    budget = slots.get("budget")
    if isinstance(budget, (int, float)) and budget > 0:
        lines.append(
            _text(
                f"Approximate annual budget: {budget}. Keep recommendations financially realistic.",
                f"每年预算约为 {budget}，建议需考虑费用可行性。",
            )
        )

    gpa = slots.get("gpa")
    if isinstance(gpa, (int, float)) and gpa > 0:
        lines.append(
            _text(
                f"Latest GPA/score: {gpa}. Use it when discussing competitiveness.",
                f"近期 GPA/成绩：{gpa}，可用于说明申请竞争力。",
            )
        )

    contact = _clean(slots.get("contact_email", ""))
    if contact:
        lines.append(
            _text(
                f"If sharing follow-up steps, mention that materials can be sent to {contact}.",
                f"若提及后续资料，可说明可发送至 {contact}。",
            )
        )

    if not lines:
        return _text("No personal details captured yet.", "暂无额外的学生画像信息。")
    return "\n".join(lines)


def _build_prompt(
    language: str,
    question: str,
    slots: Dict[str, Any],
    contexts: List[str],
    missing: List[str],
    explain_like_new: bool,
) -> Dict[str, str]:
    sys = _system_prompt(language)
    slot_lines = [f"{k}: {v}" for k, v in slots.items() if v]
    slot_section = "\n".join(slot_lines) if slot_lines else ("暂无槽位信息" if language == "zh" else "(no slots provided)")
    slot_header = "已知槽位" if language == "zh" else "Slots"
    context_section = "\n\n".join([f"[{i + 1}] {c}" for i, c in enumerate(contexts)]) or "(no context)"
    personalization_section = _personalization_notes(language, slots)
    personalization_header = "学生画像提示" if language == "zh" else "Personalization notes"

    if language == "zh":
        missing_label = "待补充槽位"
        missing_value = "、".join(missing) if missing else "无"
    else:
        missing_label = "Missing slots"
        missing_value = ", ".join(missing) if missing else "None"

    extra_guidance = ""
    if explain_like_new:
        extra_guidance = f"\n\n{_explain_like_new_hint(language)}"

    question_label = "提问" if language == "zh" else "Question"
    context_label = "参考语料" if language == "zh" else "Contexts"

    prompt = (
        f"{sys}\n\n"
        f"{personalization_header}:\n{personalization_section}\n\n"
        f"{slot_header}:\n{slot_section}\n\n"
        f"{missing_label}: {missing_value}\n\n"
        f"{question_label}: {question}{extra_guidance}\n\n"
        f"{context_label}:\n{context_section}\n\n"
        "Answer:"
    )
    return {"prompt": prompt, "system": sys}


async def answer_query(req: QueryRequest) -> QueryResponse:
    trace_id = uuid.uuid4().hex
    question_digest = hashlib.sha256(req.question.encode("utf-8")).hexdigest()[:16]
    question_length = len(req.question)
    request_language = (req.language or "auto").lower()

    sessions = get_session_store()
    existing = sessions.get(req.session_id) if req.session_id else None
    language = _answer_language(req, existing.language if existing else None)
    state = sessions.upsert(
        session_id=req.session_id,
        language=language,
        slot_updates=req.slots,
        reset_slots=req.reset_slots,
    )
    language = state.language or language

    base_span_attrs = {
        "trace_id": trace_id,
        "session_id": state.session_id,
        "question.length": question_length,
        "question.hash": question_digest,
        "request.language": request_language,
        "response.language": language,
    }

    metrics = get_metrics()
    index = get_index_manager()
    retrieval_attrs = dict(base_span_attrs)
    alpha_value = getattr(index, "alpha", 0.0)
    if alpha_value is None:
        alpha_value = 0.0
    retrieval_attrs.update(
        {
            "retrieval.top_k": req.top_k,
            "retrieval.k_cite": req.k_cite,
            "retrieval.alpha": float(alpha_value),
        }
    )
    with start_span("rag.retrieval", retrieval_attrs) as retrieval_span:
        start_retrieval = time.perf_counter()
        retrieved = index.query(req.question, top_k=req.top_k)
        retrieval_ms = (time.perf_counter() - start_retrieval) * 1000
        if retrieval_span:
            retrieval_span.set_attribute("retrieval.duration_ms", retrieval_ms)
            retrieval_span.set_attribute("retrieval.result_count", len(retrieved))
            retrieval_span.set_attribute("retrieval.empty", 1 if not retrieved else 0)
    metrics.record_phase("retrieval", retrieval_ms)

    missing_defs = missing_required_slots(state.slots)
    missing_names = [slot.name for slot in missing_defs]
    slot_prompts = {name: get_slot_prompt(name, language) for name in missing_names}
    slot_suggestions = _slot_suggestions(language, missing_defs)

    if not retrieved:
        log.warning("no_chunks_available", trace_id=trace_id)
        metrics.record_empty_retrieval()
        metrics.record_phase("end_to_end", retrieval_ms)
        metrics.record("/v1/query", retrieval_ms)
        return QueryResponse(
            answer="Corpus not indexed yet. Please ingest documents.",
            citations=[],
            trace_id=trace_id,
            session_id=state.session_id,
            slots=state.slots,
            slot_errors=state.slot_errors,
            missing_slots=missing_names,
            slot_prompts=slot_prompts,
            slot_suggestions=slot_suggestions,
        )

    reranker = get_reranker()
    rerank_attrs = dict(base_span_attrs)
    rerank_attrs.update(
        {
            "retrieval.result_count": len(retrieved),
            "rerank.k_cite": req.k_cite,
        }
    )
    with start_span("rag.rerank", rerank_attrs) as rerank_span:
        start_rerank = time.perf_counter()
        reranked = await reranker.rerank(
            req.question,
            retrieved,
            trace_id=trace_id,
            language=language,
        )
        rerank_ms = (time.perf_counter() - start_rerank) * 1000
        if rerank_span:
            rerank_span.set_attribute("rerank.duration_ms", rerank_ms)
            rerank_span.set_attribute("rerank.result_count", len(reranked))
            rerank_span.set_attribute("rerank.fallback", 1 if not reranked else 0)
    if not reranked:
        metrics.record_rerank_fallback()
    metrics.record_phase("rerank", rerank_ms)

    k_cite = min(req.k_cite, len(reranked))

    doc_lookup = get_doc_lookup()
    contexts: List[str] = []
    citations: List[Citation] = []

    for item in reranked[:k_cite]:
        doc_id = item.meta.get("doc_id") or item.chunk_id.split("-")[0]
        doc_meta = doc_lookup.get(doc_id)
        source_name = getattr(doc_meta, "source_name", doc_id)
        domain = getattr(doc_meta, "domain", None)
        url = getattr(doc_meta, "url", None)
        start_idx = item.meta.get("start_idx")
        end_idx = item.meta.get("end_idx")
        last_verified_at = getattr(doc_meta, "updated_at", None)
        header_domain = domain or "general"
        snippet = f"{source_name} | {header_domain}: {item.text}"
        contexts.append(snippet)
        citation_highlights = []
        if start_idx is not None and end_idx is not None:
            citation_highlights = [HighlightSpan(start=start_idx, end=end_idx)]
        citations.append(
            Citation(
                chunk_id=item.chunk_id,
                doc_id=doc_id,
                snippet=item.text[:200],
                score=float(item.score),
                source_name=source_name,
                url=url,
                domain=domain,
                start_char=start_idx,
                end_char=end_idx,
                last_verified_at=last_verified_at,
                highlights=citation_highlights,
            )
        )

    generation_kwargs = {
        "temperature": req.temperature if req.temperature is not None else 0.2,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
        "stop": req.stop if req.stop else None,
        "model": req.model,
    }

    prompt_payload = _build_prompt(language, req.question, state.slots, contexts, missing_names, req.explain_like_new)
    stop_tokens = generation_kwargs.get("stop") or []
    generation_attrs = dict(base_span_attrs)
    generation_attrs.update(
        {
            "retrieval.result_count": len(retrieved),
            "rerank.result_count": len(reranked),
            "generation.target_citations": req.k_cite,
            "generation.temperature": generation_kwargs["temperature"],
            "generation.model": generation_kwargs["model"] or "default",
            "generation.stop_count": len(stop_tokens),
            "generation.explain_like_new": 1 if req.explain_like_new else 0,
        }
    )
    if generation_kwargs["top_p"] is not None:
        generation_attrs["generation.top_p"] = generation_kwargs["top_p"]
    if generation_kwargs["max_tokens"] is not None:
        generation_attrs["generation.max_tokens"] = generation_kwargs["max_tokens"]
    with start_span("rag.generation", generation_attrs) as generation_span:
        start_generation = time.perf_counter()
        answer_text = await chat(
            prompt_payload["prompt"],
            system_message=prompt_payload["system"],
            **generation_kwargs,
        )
        generation_ms = (time.perf_counter() - start_generation) * 1000
        if generation_span:
            generation_span.set_attribute("generation.duration_ms", generation_ms)
            generation_span.set_attribute("generation.citation_count", len(citations))
            generation_span.set_attribute("generation.missing_slots", len(missing_names))
            generation_span.set_attribute("generation.answer_length", len(answer_text))
    metrics.record_phase("generation", generation_ms)

    low_confidence = False
    missing_names_display: List[str] = missing_names
    if missing_names:
        if language == "zh":
            guidance_prefix = "为继续提供协助，请补充以下信息："
        else:
            guidance_prefix = "To continue, please provide:"
        guidance_lines = [guidance_prefix] + [f"- {item}" for item in slot_suggestions]
        answer_text = f"{answer_text}\n\n" + "\n".join(guidance_lines)

    citation_count = len(citations)
    coverage_target = max(req.k_cite, 1)
    metrics.record_citation_coverage(citation_count, coverage_target)

    if citation_count < coverage_target:
        metrics.record_low_confidence()
        low_confidence = True

    end_to_end_ms = retrieval_ms + rerank_ms + generation_ms
    metrics.record_phase("end_to_end", end_to_end_ms)
    metrics.record("/v1/query", end_to_end_ms)

    diagnostics = {
        "retrieval_ms": retrieval_ms,
        "rerank_ms": rerank_ms,
        "generation_ms": generation_ms,
        "end_to_end_ms": end_to_end_ms,
        "low_confidence": low_confidence,
        "citation_coverage": min(citation_count / coverage_target, 1.0),
    }

    return QueryResponse(
        answer=answer_text,
        citations=citations,
        trace_id=trace_id,
        session_id=state.session_id,
        slots=state.slots,
        slot_errors=state.slot_errors,
        missing_slots=missing_names_display,
        slot_prompts=slot_prompts,
        slot_suggestions=slot_suggestions,
        diagnostics=QueryDiagnostics(**diagnostics),
        attachments=req.attachments,
    )


def _format_sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def answer_query_sse(req: QueryRequest) -> AsyncIterator[str]:
    """Server-Sent Events version of the query endpoint.

    Emits `citations`, `chunk`, `completed`, `error` events compatible with the frontend parser.
    """

    try:
        trace_id = uuid.uuid4().hex
        question_digest = hashlib.sha256(req.question.encode("utf-8")).hexdigest()[:16]
        question_length = len(req.question)
        request_language = (req.language or "auto").lower()

        sessions = get_session_store()
        existing = sessions.get(req.session_id) if req.session_id else None
        language = _answer_language(req, existing.language if existing else None)
        state = sessions.upsert(
            session_id=req.session_id,
            language=language,
            slot_updates=req.slots,
            reset_slots=req.reset_slots,
        )
        language = state.language or language

        base_span_attrs = {
            "trace_id": trace_id,
            "session_id": state.session_id,
            "question.length": question_length,
            "question.hash": question_digest,
            "request.language": request_language,
            "response.language": language,
        }

        metrics = get_metrics()
        index = get_index_manager()
        retrieval_attrs = dict(base_span_attrs)
        alpha_value = getattr(index, "alpha", 0.0) or 0.0
        retrieval_attrs.update(
            {
                "retrieval.top_k": req.top_k,
                "retrieval.k_cite": req.k_cite,
                "retrieval.alpha": float(alpha_value),
            }
        )
        with start_span("rag.retrieval", retrieval_attrs) as retrieval_span:
            start_retrieval = time.perf_counter()
            retrieved = index.query(req.question, top_k=req.top_k)
            retrieval_ms = (time.perf_counter() - start_retrieval) * 1000
            if retrieval_span:
                retrieval_span.set_attribute("retrieval.duration_ms", retrieval_ms)
                retrieval_span.set_attribute("retrieval.result_count", len(retrieved))
                retrieval_span.set_attribute("retrieval.empty", 1 if not retrieved else 0)
        metrics.record_phase("retrieval", retrieval_ms)

        missing_defs = missing_required_slots(state.slots)
        missing_names = [slot.name for slot in missing_defs]
        slot_prompts = {name: get_slot_prompt(name, language) for name in missing_names}
        slot_suggestions = _slot_suggestions(language, missing_defs)

        if not retrieved:
            metrics.record_empty_retrieval()
            metrics.record_phase("end_to_end", retrieval_ms)
            metrics.record("/v1/query", retrieval_ms)
            response = QueryResponse(
                answer="Corpus not indexed yet. Please ingest documents.",
                citations=[],
                trace_id=trace_id,
                session_id=state.session_id,
                slots=state.slots,
                slot_errors=state.slot_errors,
                missing_slots=missing_names,
                slot_prompts=slot_prompts,
                slot_suggestions=slot_suggestions,
                attachments=req.attachments,
            )
            yield _format_sse(
                "completed",
                response.model_dump(mode="json"),
            )
            return

        reranker = get_reranker()
        rerank_attrs = dict(base_span_attrs)
        rerank_attrs.update(
            {
                "retrieval.result_count": len(retrieved),
                "rerank.k_cite": req.k_cite,
            }
        )
        with start_span("rag.rerank", rerank_attrs) as rerank_span:
            start_rerank = time.perf_counter()
            reranked = await reranker.rerank(
                req.question,
                retrieved,
                trace_id=trace_id,
                language=language,
            )
            rerank_ms = (time.perf_counter() - start_rerank) * 1000
            if rerank_span:
                rerank_span.set_attribute("rerank.duration_ms", rerank_ms)
                rerank_span.set_attribute("rerank.result_count", len(reranked))
                rerank_span.set_attribute("rerank.fallback", 1 if not reranked else 0)
        if not reranked:
            metrics.record_rerank_fallback()
        metrics.record_phase("rerank", rerank_ms)

        k_cite = min(req.k_cite, len(reranked))
        doc_lookup = get_doc_lookup()
        contexts: List[str] = []
        citations: List[Citation] = []

        for item in reranked[:k_cite]:
            doc_id = item.meta.get("doc_id") or item.chunk_id.split("-")[0]
            doc_meta = doc_lookup.get(doc_id)
            source_name = getattr(doc_meta, "source_name", doc_id)
            domain = getattr(doc_meta, "domain", None)
            url = getattr(doc_meta, "url", None)
            start_idx = item.meta.get("start_idx")
            end_idx = item.meta.get("end_idx")
            last_verified_at = getattr(doc_meta, "updated_at", None)
            header_domain = domain or "general"
            snippet = f"{source_name} | {header_domain}: {item.text}"
            contexts.append(snippet)
            citation_highlights = []
            if start_idx is not None and end_idx is not None:
                citation_highlights = [HighlightSpan(start=start_idx, end=end_idx)]
            citations.append(
                Citation(
                    chunk_id=item.chunk_id,
                    doc_id=doc_id,
                    snippet=item.text[:200],
                    score=float(item.score),
                    source_name=source_name,
                    url=url,
                    domain=domain,
                    start_char=start_idx,
                    end_char=end_idx,
                    last_verified_at=last_verified_at,
                    highlights=citation_highlights,
                )
            )

        # Emit citations early so the client can render context rail while streaming
        yield _format_sse(
            "citations",
            {
                "trace_id": trace_id,
                "session_id": state.session_id,
                "citations": [c.model_dump(mode="json") for c in citations],
                "slots": state.slots,
                "missing_slots": missing_names,
                "slot_prompts": slot_prompts,
                "slot_errors": state.slot_errors,
                "slot_suggestions": slot_suggestions,
                "diagnostics": {
                    "retrieval_ms": retrieval_ms,
                    "rerank_ms": rerank_ms,
                },
            },
        )

        generation_kwargs = {
            "temperature": req.temperature if req.temperature is not None else 0.2,
            "top_p": req.top_p,
            "max_tokens": req.max_tokens,
            "stop": req.stop if req.stop else None,
            "model": req.model,
        }

        prompt_payload = _build_prompt(
            language,
            req.question,
            state.slots,
            contexts,
            missing_names,
            req.explain_like_new,
        )
        stop_tokens = generation_kwargs.get("stop") or []
        generation_attrs = dict(base_span_attrs)
        generation_attrs.update(
            {
                "retrieval.result_count": len(retrieved),
                "rerank.result_count": len(reranked),
                "generation.target_citations": req.k_cite,
                "generation.temperature": generation_kwargs["temperature"],
                "generation.model": generation_kwargs["model"] or "default",
                "generation.stop_count": len(stop_tokens),
                "generation.explain_like_new": 1 if req.explain_like_new else 0,
            }
        )
        if generation_kwargs["top_p"] is not None:
            generation_attrs["generation.top_p"] = generation_kwargs["top_p"]
        if generation_kwargs["max_tokens"] is not None:
            generation_attrs["generation.max_tokens"] = generation_kwargs["max_tokens"]

        answer_parts: List[str] = []
        with start_span("rag.generation", generation_attrs) as generation_span:
            start_generation = time.perf_counter()
            async for delta in chat_stream(
                prompt_payload["prompt"],
                system_message=prompt_payload["system"],
                temperature=generation_kwargs["temperature"],
                top_p=generation_kwargs["top_p"],
                max_tokens=generation_kwargs["max_tokens"],
                stop=generation_kwargs["stop"],
                model=generation_kwargs["model"],
            ):
                if not delta:
                    continue
                answer_parts.append(delta)
                yield _format_sse(
                    "chunk",
                    {"delta": delta, "session_id": state.session_id, "trace_id": trace_id},
                )
            generation_ms = (time.perf_counter() - start_generation) * 1000
            if generation_span:
                generation_span.set_attribute("generation.duration_ms", generation_ms)
                generation_span.set_attribute("generation.citation_count", len(citations))
                generation_span.set_attribute("generation.missing_slots", len(missing_names))
                generation_span.set_attribute("generation.answer_length", sum(len(p) for p in answer_parts))
        metrics.record_phase("generation", generation_ms)

        answer_text = "".join(answer_parts).strip()
        if missing_names:
            if language == "zh":
                guidance_prefix = "为继续提供协助，请补充以下信息："
            else:
                guidance_prefix = "To continue, please provide:"
            guidance_lines = [guidance_prefix] + [f"- {item}" for item in slot_suggestions]
            guidance_block = "\n\n" + "\n".join(guidance_lines)
            answer_text = f"{answer_text}{guidance_block}"
            yield _format_sse(
                "chunk",
                {"delta": guidance_block, "session_id": state.session_id, "trace_id": trace_id},
            )

        citation_count = len(citations)
        coverage_target = max(req.k_cite, 1)
        metrics.record_citation_coverage(citation_count, coverage_target)

        low_confidence = citation_count < coverage_target
        if low_confidence:
            metrics.record_low_confidence()

        end_to_end_ms = retrieval_ms + rerank_ms + generation_ms
        metrics.record_phase("end_to_end", end_to_end_ms)
        metrics.record("/v1/query", end_to_end_ms)

        diagnostics = QueryDiagnostics(
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            generation_ms=generation_ms,
            end_to_end_ms=end_to_end_ms,
            low_confidence=low_confidence,
            citation_coverage=min(citation_count / coverage_target, 1.0),
        )

        response = QueryResponse(
            answer=answer_text or "I was unable to craft a response with the provided information.",
            citations=citations,
            trace_id=trace_id,
            session_id=state.session_id,
            slots=state.slots,
            slot_errors=state.slot_errors,
            missing_slots=missing_names,
            slot_prompts=slot_prompts,
            slot_suggestions=slot_suggestions,
            diagnostics=diagnostics,
            attachments=req.attachments,
        )
        yield _format_sse("completed", response.model_dump(mode="json"))
    except Exception as exc:
        yield _format_sse("error", {"message": str(exc)})
