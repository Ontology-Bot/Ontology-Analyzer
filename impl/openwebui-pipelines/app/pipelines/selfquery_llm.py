"""
title: SelfQuery LLM
author: ontobot
date: 2026-02-13
version: 1.0
license: MIT
description: Self-querying LLM that generates and executes SPARQL plans before answering.
requirements: ollama, openai, sparqlwrapper
"""

from typing import List, Union, Generator, Iterator, Any, Callable
from pydantic import BaseModel
import os
import queue
import re
import threading
import time
import traceback
import uuid

try:
    from prototypes.selfquery_llm.selfquery_llm import SelfQueryLLM
    from prototypes.utils.main import set_last_message
    from prototypes.utils.llm_adapter import build_llm_adapter
except Exception:
    traceback.print_exc()
    raise

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Pipeline:
    class Valves(BaseModel):
        top_k: int = 3
        query_candidates: int = 3
        timeout_sec: int = 20
        max_rows: int = 100
        max_triples: int = 30
        planner_timeout_sec: int = 45
        planner_max_tokens: int = -1
        schema_graph_uri: str = "http://example.com/output_hierarchy_materialflow_libraries_only-graph"
        include_full_schema_ttl: bool = True
        schema_ttl_max_chars: int = -1
        allow_describe: bool = True
        enable_lexical_search: bool = True
        lexical_match_literals: bool = True
        lexical_match_labels: bool = True
        lexical_match_iri_local_names: bool = True
        lexical_match_predicates: bool = True
        lexical_max_tokens: int = 6
        lexical_max_candidates: int = 4
        max_iterations: int = 5
        min_iterations_before_early_stop: int = 3
        min_score_improvement: float = 0.02
        global_time_budget_sec: int = 90
        max_query_chars: int = 8000
        progress_output_mode: str = "events"  # options: "events", "text", "both"
        LLM_PROVIDER: str = "openai_compat"
        LLM_BASE_URL: str = "https://chat-ai.academiccloud.de/v1/"
        LLM_API_KEY: str
        LLM_DEFAULT_MODEL: str = ""
        SPARQL_BASE_URL: str

    def __init__(self):
        self.type = "manifold"
        self.id = "selfqueryllm"
        self.name = "SelfQueryLLM/"
        self.toggle = True

        self.model = None
        self.client = None
        self.valves = self.Valves(
            **{
                "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "openai_compat"),
                "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://chat-ai.academiccloud.de/v1/"),
                "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
                "LLM_DEFAULT_MODEL": os.getenv("LLM_DEFAULT_MODEL", ""),
                "SPARQL_BASE_URL": os.getenv("SPARQL_BASE_URL", ""),
            }
        )

        logger.info(f"--- {self.name} Initialized ---")

    def _get_models(self) -> List[dict]:
        try:
            if self.client is None:
                self._update()
            if self.client is None:
                raise ValueError("Oops! Forgot to initialize valves!")

            models = self.client.list_models()
            return models
        except Exception as error:
            logger.error(f"Discovery error: {error}")
            fallback = self.valves.LLM_DEFAULT_MODEL or "fallback-model"
            return [{"id": fallback, "name": "SelfQueryLLM (Fallback model)"}]

    def _update(self) -> None:
        if self.valves.SPARQL_BASE_URL == "" or self.valves.LLM_BASE_URL == "":
            logger.error("Empty SPARQL_BASE_URL and LLM_BASE_URL")
            return

        self.model = SelfQueryLLM(
            endpoint=self.valves.SPARQL_BASE_URL,
            top_k=self.valves.top_k,
            query_candidates=self.valves.query_candidates,
            timeout_sec=self.valves.timeout_sec,
            max_rows=self.valves.max_rows,
            max_triples=self.valves.max_triples,
            planner_timeout_sec=self.valves.planner_timeout_sec,
            planner_max_tokens=self.valves.planner_max_tokens,
            schema_graph_uri=self.valves.schema_graph_uri,
            include_full_schema_ttl=self.valves.include_full_schema_ttl,
            schema_ttl_max_chars=self.valves.schema_ttl_max_chars,
            allow_describe=self.valves.allow_describe,
            enable_lexical_search=self.valves.enable_lexical_search,
            lexical_match_literals=self.valves.lexical_match_literals,
            lexical_match_labels=self.valves.lexical_match_labels,
            lexical_match_iri_local_names=self.valves.lexical_match_iri_local_names,
            lexical_match_predicates=self.valves.lexical_match_predicates,
            lexical_max_tokens=self.valves.lexical_max_tokens,
            lexical_max_candidates=self.valves.lexical_max_candidates,
            max_iterations=self.valves.max_iterations,
            min_iterations_before_early_stop=self.valves.min_iterations_before_early_stop,
            min_score_improvement=self.valves.min_score_improvement,
            global_time_budget_sec=self.valves.global_time_budget_sec,
            max_query_chars=self.valves.max_query_chars,
        )
        self.client = build_llm_adapter(
            provider=self.valves.LLM_PROVIDER,
            base_url=self.valves.LLM_BASE_URL,
            api_key=self.valves.LLM_API_KEY,
        )

    def pipelines(self) -> List[dict]:
        return self._get_models()

    async def on_startup(self):
        logger.info(f"on_startup triggered for {__name__}")
        self._update()
        logger.info(f"--- {self.name} Started ---")

    async def on_shutdown(self):
        logger.info(f"on_shutdown triggered for {__name__}")

    async def on_valves_updated(self):
        logger.info("Valves updated")
        self._update()

    def _resolve_progress_mode(self) -> tuple[bool, bool]:
        progress_mode = self.valves.progress_output_mode.strip().lower()
        if progress_mode not in {"events", "text", "both"}:
            progress_mode = "events"
        return progress_mode in {"events", "both"}, progress_mode in {"text", "both"}

   

    def _compact_query_preview(self, value: str) -> str:
        compact = " ".join(str(value).split())
        match = re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", compact, flags=re.IGNORECASE)
        if match:
            compact = compact[match.start():]
        return compact.strip()

    def _to_query_chips(self, payload: dict[str, Any], max_items: int = 4) -> list[str]:
        previews = payload.get("query_previews", [])
        if not isinstance(previews, list):
            return []
        return [self._compact_query_preview(item) for item in previews[:max_items] if str(item).strip()]

    def _build_status_data(self, progress: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        description = str(progress.get("description", "Working on retrieval"))
        payload = progress.get("payload", {}) if isinstance(progress.get("payload", {}), dict) else {}
        done = bool(progress.get("done", False))
        stage = str(progress.get("stage", ""))

        data: dict[str, Any] = {
            "description": description,
            "done": done,
        }

        if stage in {"start", "schema_metadata", "schema_ttl"}:
            data["hidden"] = True

        if stage == "iteration_candidates":
            data["action"] = "queries_generated"
            data["description"] = "Query candidates"
            chips = self._to_query_chips(payload)
            if chips:
                data["queries"] = chips
        elif stage == "iteration_start":
            data["description"] = "Planning retrieval"
        elif stage == "iteration_executed":
            data["description"] = "Query execution"
        elif stage == "iteration_stop":
            data["description"] = "Stopping retrieval"
        elif stage == "complete":
            data["description"] = "Retrieval complete"

        query_parts: list[str] = []
        iteration = payload.get("iteration")
        max_iterations = payload.get("max_iterations")
        if iteration is not None and max_iterations is not None:
            query_parts.append(f"round {iteration}/{max_iterations}")
        elif iteration is not None:
            query_parts.append(f"round {iteration}")

        if "new_candidates" in payload:
            query_parts.append(f"new queries: {payload.get('new_candidates')}")
        if "executed_queries" in payload:
            query_parts.append(f"executed: {payload.get('executed_queries')}")
        if "evidence_count" in payload:
            query_parts.append(f"evidence: {payload.get('evidence_count')}")
        if "stop_reason" in payload:
            query_parts.append(f"stop: {payload.get('stop_reason')}")
        if "selected_evidence" in payload:
            query_parts.append(f"selected: {payload.get('selected_evidence')}")

        if query_parts:
            data["query"] = " | ".join(query_parts)

        if stage == "error":
            data["error"] = True

        return data, payload

    def _format_progress_line(self, progress: dict[str, Any]) -> str:
        status_data, payload = self._build_status_data(progress)
        if status_data.get("hidden"):
            return ""
        description = status_data.get("description", "Working on retrieval")
        details: list[str] = []

        query = status_data.get("query")
        if query:
            details.append(str(query))

        chips = status_data.get("queries", [])
        if isinstance(chips, list) and chips:
            details.append("; ".join(str(item) for item in chips[:3]))

        if not chips and isinstance(payload.get("query_previews"), list) and payload.get("query_previews"):
            details.append("; ".join(self._compact_query_preview(item) for item in payload.get("query_previews", [])[:3]))

        if details:
            return f"[retrieval] {description} | {' | '.join(details)}\n"
        return f"[retrieval] {description}\n"

    def _run_retrieval(
        self,
        request_id: str,
        model_id: str,
        user_message: str,
        retrieval_start: float,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        try:
            retrieval = self.model.process(self.client, model_id, user_message, progress_callback=progress_callback)
            logger.info("[%s] Retrieval complete | duration=%.2fs", request_id, time.monotonic() - retrieval_start)
            return retrieval, None
        except Exception as error:
            retrieval_error = str(error)
            logger.exception(
                "[%s] Retrieval failed after %.2fs; continuing without SPARQL evidence",
                request_id,
                time.monotonic() - retrieval_start,
            )
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "error",
                        "description": "Retrieval failed; continuing with best-effort response",
                        "done": True,
                        "payload": {"error": retrieval_error},
                    }
                )
            return {}, retrieval_error

    def _build_prompt_with_retrieval(
        self,
        request_id: str,
        retrieval: dict[str, Any],
        retrieval_error: str | None,
        user_message: str,
    ) -> tuple[str, list[dict[str, Any]], str]:
        context = retrieval.get("context", "") if retrieval else ""
        evidence = retrieval.get("evidence", []) if retrieval else []

        msg = "Use ontology-grounded SPARQL evidence to answer the user.\n"
        msg += "If evidence is weak, state uncertainty explicitly.\n\n"
        msg += "SPARQL EVIDENCE:\n"
        if retrieval_error:
            msg += f"SPARQL RETRIEVAL UNAVAILABLE: {retrieval_error}\n"
            msg += "Proceed with best-effort answer and clearly mark uncertainty.\n"
        else:
            msg += context if context else "NO RELEVANT EVIDENCE\n"
        msg += "\n\n"
        msg += f"USER QUESTION:\n{user_message}\n\n"
        msg += "Please include a short 'Evidence Used' section with query references.\n"

        logger.info("[%s] Generated evidence count=%d | context_chars=%d", request_id, len(evidence), len(context))
        return msg, evidence, context

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        request_id = uuid.uuid4().hex[:8]
        pipe_start = time.monotonic()

        if self.model is None or self.client is None:
            raise ValueError("Oops! Forgot to initialize valves!")

        model_id = body.get("model", "").split(".", 1)[-1] or self.valves.LLM_DEFAULT_MODEL
        if not model_id:
            raise ValueError("No model selected and LLM_DEFAULT_MODEL is empty")

        logger.info("[%s] Inlet:%s model=%s stream=%s", request_id, __name__, model_id, body.get("stream", False))
        logger.info("[%s] UserQuery len=%d", request_id, len(user_message))

        emit_events, emit_text = self._resolve_progress_mode()

        retrieval_start = time.monotonic()

        try:
            if body.get("stream", False):
                def stream_generator(client):
                    progress_queue: queue.Queue[dict[str, Any]] = queue.Queue()
                    retrieval_done = threading.Event()
                    retrieval_state: dict[str, Any] = {
                        "retrieval": {},
                        "retrieval_error": None,
                    }

                    def on_progress(event: dict[str, Any]) -> None:
                        progress_queue.put(event)

                    def retrieval_worker() -> None:
                        retrieval, retrieval_error = self._run_retrieval(
                            request_id=request_id,
                            model_id=model_id,
                            user_message=user_message,
                            retrieval_start=retrieval_start,
                            progress_callback=on_progress,
                        )
                        retrieval_state["retrieval"] = retrieval
                        retrieval_state["retrieval_error"] = retrieval_error
                        retrieval_done.set()

                    worker = threading.Thread(target=retrieval_worker, name=f"selfquery-progress-{request_id}", daemon=True)
                    worker.start()

                    while not retrieval_done.is_set() or not progress_queue.empty():
                        try:
                            progress = progress_queue.get(timeout=0.2)
                        except queue.Empty:
                            continue

                        status_data, _ = self._build_status_data(progress)

                        if emit_events:
                            if status_data.get("hidden"):
                                continue
                            yield {
                                "event": {
                                    "type": "status",
                                    "data": status_data,
                                }
                            }

                        if emit_text:
                            line = self._format_progress_line(progress)
                            if line:
                                yield line

                    msg, _, _ = self._build_prompt_with_retrieval(
                        request_id=request_id,
                        retrieval=retrieval_state.get("retrieval", {}),
                        retrieval_error=retrieval_state.get("retrieval_error"),
                        user_message=user_message,
                    )
                    set_last_message("user", messages, msg)
                    logger.info("[%s] Final prompt injected into last user message", request_id)

                    logger.info("[%s] Streaming chat started", request_id)
                    chunk_count = 0
                    for chunk in client.stream_text(
                        model=model_id,
                        messages=messages,
                    ):
                        chunk_count += 1
                        if chunk_count % 20 == 0:
                            logger.info("[%s] Streaming progress | chunks=%d", request_id, chunk_count)
                        yield chunk
                    logger.info(
                        "[%s] Streaming finished | chunks=%d | total=%.2fs",
                        request_id,
                        chunk_count,
                        time.monotonic() - pipe_start,
                    )

                return stream_generator(self.client)

            non_stream_progress: list[str] = []

            def on_non_stream_progress(event: dict[str, Any]) -> None:
                line = self._format_progress_line(event)
                if line:
                    non_stream_progress.append(line)

            retrieval, retrieval_error = self._run_retrieval(
                request_id=request_id,
                model_id=model_id,
                user_message=user_message,
                retrieval_start=retrieval_start,
                progress_callback=on_non_stream_progress if emit_text else None,
            )
            msg, _, _ = self._build_prompt_with_retrieval(
                request_id=request_id,
                retrieval=retrieval,
                retrieval_error=retrieval_error,
                user_message=user_message,
            )
            set_last_message("user", messages, msg)
            logger.info("[%s] Final prompt injected into last user message", request_id)

            logger.info("[%s] Non-stream chat started", request_id)
            response = self.client.chat_text(
                model=model_id,
                messages=messages,
            )
            logger.info("[%s] Non-stream chat finished | total=%.2fs", request_id, time.monotonic() - pipe_start)
            if emit_text and non_stream_progress:
                return "".join(non_stream_progress) + response
            return response
        except Exception as error:
            logger.exception("[%s] Pipeline failure after %.2fs", request_id, time.monotonic() - pipe_start)
            return f"Error calling LLM: {str(error)}"