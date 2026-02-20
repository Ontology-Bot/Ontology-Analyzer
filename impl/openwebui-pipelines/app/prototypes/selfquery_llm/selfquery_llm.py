from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import logging
import re
import time
from typing import Any, Callable

from SPARQLWrapper import JSON, TURTLE, SPARQLWrapper


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


QUERY_TYPE_RE = re.compile(r"^\s*(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", flags=re.IGNORECASE)
FORBIDDEN_QUERY_RE = re.compile(
    r"\b(INSERT|DELETE|DROP|CLEAR|CREATE|LOAD|COPY|MOVE|ADD|SERVICE|WITH|USING|VALUES\s*\{\s*<http)\b",
    flags=re.IGNORECASE,
)
TEXT_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
USER_QUERY_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-]{2,}")


@dataclass
class QueryEvidence:
    query: str
    query_type: str
    preview: str
    score: float
    error: str | None = None


class SelfQueryLLM:
    def __init__(
        self,
        endpoint: str,
        top_k: int,
        query_candidates: int,
        timeout_sec: int,
        max_rows: int,
        max_triples: int,
        planner_timeout_sec: int,
        planner_max_tokens: int,
        schema_graph_uri: str,
        include_full_schema_ttl: bool,
        schema_ttl_max_chars: int,
        allow_describe: bool,
        enable_lexical_search: bool,
        lexical_match_literals: bool,
        lexical_match_labels: bool,
        lexical_match_iri_local_names: bool,
        lexical_match_predicates: bool,
        lexical_max_tokens: int,
        lexical_max_candidates: int,
        max_iterations: int,
        min_iterations_before_early_stop: int,
        min_score_improvement: float,
        global_time_budget_sec: int,
        max_query_chars: int,
    ):
        self.endpoint = endpoint
        self.top_k = top_k
        self.query_candidates = query_candidates
        self.timeout_sec = timeout_sec
        self.max_rows = max_rows
        self.max_triples = max_triples
        self.planner_timeout_sec = planner_timeout_sec
        self.planner_max_tokens = planner_max_tokens
        self.schema_graph_uri = schema_graph_uri
        self.include_full_schema_ttl = include_full_schema_ttl
        self.schema_ttl_max_chars = schema_ttl_max_chars
        self.allow_describe = allow_describe
        self.enable_lexical_search = enable_lexical_search
        self.lexical_match_literals = lexical_match_literals
        self.lexical_match_labels = lexical_match_labels
        self.lexical_match_iri_local_names = lexical_match_iri_local_names
        self.lexical_match_predicates = lexical_match_predicates
        self.lexical_max_tokens = max(1, lexical_max_tokens)
        self.lexical_max_candidates = max(1, lexical_max_candidates)
        self.max_iterations = max(1, max_iterations)
        self.min_iterations_before_early_stop = max(1, min(min_iterations_before_early_stop, self.max_iterations))
        self.min_score_improvement = max(0.0, min_score_improvement)
        self.global_time_budget_sec = max(1, global_time_budget_sec)
        self.max_query_chars = max(256, max_query_chars)
        self._schema_metadata_cache: str | None = None
        self._schema_ttl_cache: str | None = None
        self._endpoint_candidates_cache = self._build_endpoint_candidates()

    def _build_endpoint_candidates(self) -> list[str]:
        candidates = [self.endpoint]
        if "host.docker.internal" in self.endpoint:
            candidates.append(self.endpoint.replace("host.docker.internal", "172.17.0.1"))

        unique: list[str] = []
        seen: set[str] = set()
        for endpoint in candidates:
            if endpoint not in seen:
                seen.add(endpoint)
                unique.append(endpoint)
        return unique

    def _endpoint_candidates(self) -> list[str]:
        return self._endpoint_candidates_cache

    def process(
        self,
        client: Any,
        model_id: str,
        user_query: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info(
            "[SelfQueryLLM] process start | model=%s | query_len=%d",
            model_id,
            len(user_query),
        )
        self._notify_progress(
            progress_callback,
            stage="start",
            description="Starting ontology retrieval",
            done=False,
            payload={
                "max_iterations": self.max_iterations,
                "min_iterations_before_early_stop": self.min_iterations_before_early_stop,
            },
        )

        schema_metadata, schema_ttl = self._load_schema_context(progress_callback)

        all_candidates: list[str] = []
        all_evidence: list[QueryEvidence] = []
        seen_queries: set[str] = set()
        best_score = 0.0
        stop_reason = "max_iterations"
        iterations_used = 0

        for iteration in range(1, self.max_iterations + 1):
            iterations_used = iteration
            self._notify_progress(
                progress_callback,
                stage="iteration_start",
                description=f"Iteration {iteration}/{self.max_iterations}: planning queries",
                done=False,
                payload={"iteration": iteration, "max_iterations": self.max_iterations},
            )
            if self._global_budget_reached(start, iteration, progress_callback):
                stop_reason = "global_time_budget"
                break

            merged, planner_count, lexical_count = self._plan_iteration_candidates(
                client=client,
                model_id=model_id,
                user_query=user_query,
                schema_metadata=schema_metadata,
                schema_ttl=schema_ttl,
                all_evidence=all_evidence,
                seen_queries=seen_queries,
                iteration=iteration,
            )
            all_candidates.extend(merged)
            self._notify_progress(
                progress_callback,
                stage="iteration_candidates",
                description=f"Iteration {iteration}/{self.max_iterations}: {len(merged)} new queries",
                done=False,
                payload={
                    "iteration": iteration,
                    "planner_candidates": planner_count,
                    "lexical_candidates": lexical_count,
                    "new_candidates": len(merged),
                    "query_previews": [self._short(query, max_len=120) for query in merged[:2]],
                },
            )

            if not merged:
                stop_reason = "no_new_candidates"
                self._notify_progress(
                    progress_callback,
                    stage="iteration_stop",
                    description="Stopping retrieval: no new queries",
                    done=False,
                    payload={"iteration": iteration},
                )
                break

            evidence = self._execute_iteration_candidates(merged, user_query, iteration)
            all_evidence.extend(evidence)
            self._notify_progress(
                progress_callback,
                stage="iteration_executed",
                description=f"Iteration {iteration}/{self.max_iterations}: executed {len(merged)} queries",
                done=False,
                payload={
                    "iteration": iteration,
                    "executed_queries": len(merged),
                    "evidence_count": len(evidence),
                },
            )

            should_stop, best_score = self._evaluate_early_stop(
                all_evidence=all_evidence,
                current_best_score=best_score,
                iteration=iteration,
                progress_callback=progress_callback,
            )
            if should_stop:
                stop_reason = "no_meaningful_improvement"
                break

        return self._build_process_result(
            start=start,
            schema_metadata=schema_metadata,
            all_candidates=all_candidates,
            all_evidence=all_evidence,
            stop_reason=stop_reason,
            iterations_used=iterations_used,
            progress_callback=progress_callback,
        )

    def _load_schema_context(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[str, str]:
        schema_start = time.monotonic()
        schema_warning: str | None = None
        try:
            schema_metadata = self.get_schema_metadata()
        except Exception as error:
            schema_warning = str(error)
            logger.exception("[SelfQueryLLM] schema metadata fetch failed; using empty schema metadata")
            schema_metadata = json.dumps(
                {
                    "classes": [],
                    "properties": [],
                    "warning": schema_warning,
                },
                ensure_ascii=False,
            )
        logger.info(
            "[SelfQueryLLM] schema metadata ready | duration=%.2fs | chars=%d",
            time.monotonic() - schema_start,
            len(schema_metadata),
        )
        self._notify_progress(
            progress_callback,
            stage="schema_metadata",
            description="Schema metadata ready",
            done=False,
            payload={"chars": len(schema_metadata)},
        )

        schema_ttl = ""
        if self.include_full_schema_ttl:
            schema_ttl_start = time.monotonic()
            try:
                schema_ttl = self.get_schema_ttl()
            except Exception:
                logger.exception("[SelfQueryLLM] schema ttl fetch failed; continuing without schema ttl")
                schema_ttl = ""
            logger.info(
                "[SelfQueryLLM] schema ttl ready | duration=%.2fs | chars=%d",
                time.monotonic() - schema_ttl_start,
                len(schema_ttl),
            )
            self._notify_progress(
                progress_callback,
                stage="schema_ttl",
                description="Schema TTL loaded",
                done=False,
                payload={"chars": len(schema_ttl)},
            )

        return schema_metadata, schema_ttl

    def _global_budget_reached(
        self,
        start: float,
        iteration: int,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> bool:
        elapsed = time.monotonic() - start
        if elapsed < self.global_time_budget_sec:
            return False

        logger.warning(
            "[SelfQueryLLM] stopping retrieval at iteration=%d due to time budget | elapsed=%.2fs | budget=%ss",
            iteration,
            elapsed,
            self.global_time_budget_sec,
        )
        self._notify_progress(
            progress_callback,
            stage="iteration_stop",
            description="Stopping retrieval: time budget reached",
            done=False,
            payload={
                "iteration": iteration,
                "elapsed_sec": round(elapsed, 2),
                "budget_sec": self.global_time_budget_sec,
            },
        )
        return True

    def _plan_iteration_candidates(
        self,
        client: Any,
        model_id: str,
        user_query: str,
        schema_metadata: str,
        schema_ttl: str,
        all_evidence: list[QueryEvidence],
        seen_queries: set[str],
        iteration: int,
    ) -> tuple[list[str], int, int]:
        loop_context = self.rank_and_pack_context(sorted(all_evidence, key=lambda item: item.score, reverse=True)[: self.top_k])
        plan_start = time.monotonic()
        planner_candidates = self.generate_sparql_candidates(
            client,
            model_id,
            user_query,
            schema_metadata,
            schema_ttl,
            loop_context=loop_context if all_evidence else "",
            iteration=iteration,
        )
        lexical_candidates = self._build_lexical_candidates(user_query) if self.enable_lexical_search else []

        merged: list[str] = []
        for query in planner_candidates:
            normalized = self._normalize_query(query)
            if normalized in seen_queries:
                continue
            seen_queries.add(normalized)
            merged.append(query)
        for query in lexical_candidates:
            normalized = self._normalize_query(query)
            if normalized in seen_queries:
                continue
            seen_queries.add(normalized)
            merged.append(query)

        logger.info(
            "[SelfQueryLLM] iteration=%d candidates ready | duration=%.2fs | planner=%d | lexical=%d | merged_new=%d",
            iteration,
            time.monotonic() - plan_start,
            len(planner_candidates),
            len(lexical_candidates),
            len(merged),
        )
        return merged, len(planner_candidates), len(lexical_candidates)

    def _execute_iteration_candidates(self, merged: list[str], user_query: str, iteration: int) -> list[QueryEvidence]:
        query_start = time.monotonic()
        evidence = self.execute_sparql_batch(merged, user_query)
        logger.info(
            "[SelfQueryLLM] iteration=%d execution done | duration=%.2fs | evidence=%d",
            iteration,
            time.monotonic() - query_start,
            len(evidence),
        )
        return evidence

    def _evaluate_early_stop(
        self,
        all_evidence: list[QueryEvidence],
        current_best_score: float,
        iteration: int,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[bool, float]:
        next_best_score = max((item.score for item in all_evidence), default=0.0)
        improvement = next_best_score - current_best_score
        can_early_stop = iteration >= self.min_iterations_before_early_stop
        if (
            iteration < self.max_iterations
            and can_early_stop
            and improvement < self.min_score_improvement
        ):
            logger.info(
                "[SelfQueryLLM] stopping after iteration=%d | improvement=%.4f < min=%.4f",
                iteration,
                improvement,
                self.min_score_improvement,
            )
            self._notify_progress(
                progress_callback,
                stage="iteration_stop",
                description="Stopping retrieval: no meaningful improvement",
                done=False,
                payload={
                    "iteration": iteration,
                    "improvement": round(improvement, 4),
                    "minimum_improvement": self.min_score_improvement,
                },
            )
            return True, next_best_score
        return False, next_best_score

    def _build_process_result(
        self,
        start: float,
        schema_metadata: str,
        all_candidates: list[str],
        all_evidence: list[QueryEvidence],
        stop_reason: str,
        iterations_used: int,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        evidence_sorted = sorted(all_evidence, key=lambda item: item.score, reverse=True)
        best = evidence_sorted[: self.top_k]
        context = self.rank_and_pack_context(best)
        logger.info(
            "[SelfQueryLLM] process end | total=%.2fs | selected=%d | context_chars=%d | stop_reason=%s",
            time.monotonic() - start,
            len(best),
            len(context),
            stop_reason,
        )
        self._notify_progress(
            progress_callback,
            stage="complete",
            description=f"Retrieval complete after {iterations_used} iteration(s): {stop_reason}",
            done=True,
            payload={
                "iterations_used": iterations_used,
                "stop_reason": stop_reason,
                "selected_evidence": len(best),
            },
        )
        return {
            "schema_metadata": schema_metadata,
            "queries": all_candidates,
            "evidence": [
                {
                    "query": item.query,
                    "query_type": item.query_type,
                    "preview": item.preview,
                    "score": item.score,
                    "error": item.error,
                }
                for item in best
            ],
            "context": context,
            "iterations_used": iterations_used,
            "stop_reason": stop_reason,
        }

    def _notify_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None,
        stage: str,
        description: str,
        done: bool,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if progress_callback is None:
            return
        event = {
            "stage": stage,
            "description": description,
            "done": done,
            "payload": payload or {},
        }
        try:
            progress_callback(event)
        except Exception:
            logger.exception("[SelfQueryLLM] progress callback failed")

    def get_schema_metadata(self) -> str:
        if self._schema_metadata_cache is not None:
            logger.info("[SelfQueryLLM] using cached schema metadata")
            return self._schema_metadata_cache

        logger.info("[SelfQueryLLM] building schema metadata from endpoint")

        classes = self._run_select(
            """
            SELECT ?class (COUNT(?instance) AS ?instanceCount)
            WHERE {
                ?class a owl:Class .
                OPTIONAL { ?instance a ?class }
            }
            GROUP BY ?class
            ORDER BY DESC(?instanceCount)
            LIMIT 25
            """,
            """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            """,
        )
        properties = self._run_select(
            """
            SELECT ?prop ?domain ?range
            WHERE {
                ?prop a rdf:Property .
                OPTIONAL { ?prop rdfs:domain ?domain }
                OPTIONAL { ?prop rdfs:range ?range }
            }
            LIMIT 30
            """,
            """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            """,
        )

        payload = {
            "classes": classes,
            "properties": properties,
        }
        self._schema_metadata_cache = json.dumps(payload, ensure_ascii=False)
        logger.info(
            "[SelfQueryLLM] schema metadata built | classes=%d | properties=%d",
            len(classes),
            len(properties),
        )
        return self._schema_metadata_cache

    def build_query_prompt(
        self,
        user_query: str,
        schema_metadata: str,
        schema_ttl: str,
        loop_context: str,
        iteration: int,
    ) -> str:
        allowed_types = "SELECT, ASK, CONSTRUCT" + (", DESCRIBE" if self.allow_describe else "")
        prompt = (
            "You are a SPARQL planner. Generate read-only SPARQL queries that can help answer the user question.\n"
            "Rules:\n"
            "1. Generate up to {count} queries.\n"
            "2. Query types allowed: {allowed_types}.\n"
            "3. Keep every query bounded with LIMIT {max_rows} for SELECT and LIMIT {max_triples} for CONSTRUCT when applicable.\n"
            "4. Output STRICT JSON object with key 'queries' and value as string array. No markdown.\n\n"
            "Iteration: {iteration}.\n"
            "Schema metadata:\n{schema}\n\n"
            "User question:\n{question}"
        ).format(
            count=self.query_candidates,
            allowed_types=allowed_types,
            max_rows=self.max_rows,
            max_triples=self.max_triples,
            iteration=iteration,
            schema=schema_metadata,
            question=user_query,
        )
        if iteration < self.min_iterations_before_early_stop:
            prompt += (
                "\n\nPlanning guidance:\n"
                "- Continue exploration for this round.\n"
                "- Prefer focused follow-up read-only queries that test missing entities/relations.\n"
                "- Only return an empty queries list if no safe useful query can be formed."
            )
        if loop_context:
            prompt += "\n\nPrevious evidence summary:\n"
            prompt += loop_context
            prompt += "\n\nIf evidence is already strong, return an empty 'queries' list."
        if schema_ttl:
            prompt += "\n\nSchema TTL (verbatim):\n"
            prompt += schema_ttl
        return prompt

    def generate_sparql_candidates(
        self,
        client: Any,
        model_id: str,
        user_query: str,
        schema_metadata: str,
        schema_ttl: str,
        loop_context: str = "",
        iteration: int = 1,
    ) -> list[str]:
        prompt = self.build_query_prompt(user_query, schema_metadata, schema_ttl, loop_context, iteration)
        logger.info(
            "[SelfQueryLLM] requesting query candidates from LLM | model=%s | prompt_chars=%d | timeout=%ss | max_tokens=%d",
            model_id,
            len(prompt),
            self.planner_timeout_sec,
            self.planner_max_tokens,
        )

        def _call_planner() -> str:
            return client.chat_json(
                model=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0,
                max_tokens=self.planner_max_tokens,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                content = pool.submit(_call_planner).result(timeout=self.planner_timeout_sec)
        except FutureTimeoutError:
            logger.error(
                "[SelfQueryLLM] planner timeout after %ss; using fallback query",
                self.planner_timeout_sec,
            )
            return [self._fallback_query(user_query)] if iteration == 1 else []
        except Exception:
            logger.exception("[SelfQueryLLM] planner call failed; using fallback query")
            return [self._fallback_query(user_query)] if iteration == 1 else []

        logger.info("[SelfQueryLLM] candidate raw response chars=%d", len(content))
        parsed = self._extract_queries(content)
        if parsed:
            logger.info("[SelfQueryLLM] parsed query candidates=%d", len(parsed))
            return parsed[: self.query_candidates]
        logger.warning("[SelfQueryLLM] no valid query candidates parsed; using fallback query")
        return [self._fallback_query(user_query)] if iteration == 1 else []

    def get_schema_ttl(self) -> str:
        if self._schema_ttl_cache is not None:
            logger.info("[SelfQueryLLM] using cached schema ttl")
            return self._schema_ttl_cache

        if self.schema_graph_uri.strip() == "":
            query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
            logger.warning("[SelfQueryLLM] schema_graph_uri is empty; fetching ttl from all graphs")
        else:
            query = (
                "CONSTRUCT { ?s ?p ?o } WHERE { "
                f"GRAPH <{self.schema_graph_uri}> {{ ?s ?p ?o }} "
                "}"
            )
            logger.info("[SelfQueryLLM] fetching schema ttl from graph=%s", self.schema_graph_uri)

        ttl = self._run_construct(query)
        if self.schema_ttl_max_chars > 0 and len(ttl) > self.schema_ttl_max_chars:
            logger.warning(
                "[SelfQueryLLM] schema ttl truncated | original=%d | max=%d",
                len(ttl),
                self.schema_ttl_max_chars,
            )
            ttl = ttl[: self.schema_ttl_max_chars]

        self._schema_ttl_cache = ttl
        return self._schema_ttl_cache

    def execute_sparql_batch(self, candidates: list[str], user_query: str) -> list[QueryEvidence]:
        evidence: list[QueryEvidence] = []
        logger.info("[SelfQueryLLM] executing candidate batch | count=%d", len(candidates))
        for index, query in enumerate(candidates, start=1):
            query_type = self._query_type(query)
            logger.info(
                "[SelfQueryLLM] candidate %d/%d start | type=%s | preview=%s",
                index,
                len(candidates),
                query_type,
                self._short(query),
            )

            safe, reason = self._validate_query(query, query_type=query_type)
            if not safe:
                logger.warning(
                    "[SelfQueryLLM] candidate %d rejected | reason=%s",
                    index,
                    reason,
                )
                evidence.append(
                    QueryEvidence(
                        query=query,
                        query_type=query_type,
                        preview="",
                        score=0.0,
                        error=reason,
                    )
                )
                continue

            try:
                candidate_start = time.monotonic()
                if query_type in {"SELECT", "ASK", "DESCRIBE"}:
                    payload = self._run_raw_json(query)
                    preview, score = self._score_json_payload(payload, user_query)
                else:
                    payload = self._run_construct(query)
                    preview, score = self._score_construct_payload(payload, user_query)
                logger.info(
                    "[SelfQueryLLM] candidate %d success | duration=%.2fs | score=%.3f | preview_chars=%d",
                    index,
                    time.monotonic() - candidate_start,
                    score,
                    len(preview),
                )
                evidence.append(
                    QueryEvidence(
                        query=query,
                        query_type=query_type,
                        preview=preview,
                        score=score,
                    )
                )
            except Exception as error:
                logger.exception("[SelfQueryLLM] candidate %d failed", index)
                evidence.append(
                    QueryEvidence(
                        query=query,
                        query_type=query_type,
                        preview="",
                        score=0.0,
                        error=str(error),
                    )
                )
        return evidence

    def rank_and_pack_context(self, evidence: list[QueryEvidence]) -> str:
        chunks: list[str] = []
        for index, item in enumerate(evidence, start=1):
            block = [
                f"Evidence #{index}",
                f"QueryType: {item.query_type}",
                "Query:",
                item.query,
            ]
            if item.error:
                block.append(f"Error: {item.error}")
            else:
                block.extend([
                    "Top bindings/subgraph:",
                    item.preview,
                ])
            chunks.append("\n".join(block))
        return "\n\n".join(chunks)

    def _extract_queries(self, content: str) -> list[str]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()

        try:
            payload = json.loads(content)
            queries = payload.get("queries", [])
            if isinstance(queries, list):
                return [str(item).strip() for item in queries if str(item).strip()]
        except Exception:
            pass

        fallback = re.findall(r"(?is)((?:SELECT|ASK|CONSTRUCT)\s+.*?)(?=(?:\n\s*(?:SELECT|ASK|CONSTRUCT)\s)|\Z)", content)
        if fallback:
            return [snippet.strip() for snippet in fallback if snippet.strip()]
        return []

    def _query_type(self, query: str) -> str:
        match = QUERY_TYPE_RE.match(query)
        return match.group(1).upper() if match else "UNKNOWN"

    def _validate_query(self, query: str, query_type: str | None = None) -> tuple[bool, str | None]:
        if len(query) > self.max_query_chars:
            return False, f"Query exceeds max_query_chars ({self.max_query_chars})"

        query_type = query_type or self._query_type(query)
        allowed_types = {"SELECT", "ASK", "CONSTRUCT"}
        if self.allow_describe:
            allowed_types.add("DESCRIBE")
        if query_type not in allowed_types:
            return False, f"Only {', '.join(sorted(allowed_types))} are allowed"

        if FORBIDDEN_QUERY_RE.search(query):
            return False, "Query contains forbidden operation"

        if query_type in {"SELECT", "CONSTRUCT"} and "limit" not in query.lower():
            return False, "Row/graph returning query must include LIMIT"

        return True, None

    def _run_select(self, body: str, prefix: str = "") -> list[dict[str, str]]:
        query = f"{prefix}\n{body}"
        logger.info("[SelfQueryLLM] schema SELECT start | timeout=%ss", self.timeout_sec)
        payload = self._run_raw_json(query)
        rows: list[dict[str, str]] = []
        for binding in payload.get("results", {}).get("bindings", [])[: self.max_rows]:
            row: dict[str, str] = {}
            for key, value in binding.items():
                row[key] = value.get("value", "")
            rows.append(row)
        return rows

    def _run_with_endpoint_retry(
        self,
        query: str,
        return_format: Any,
        request_label: str,
        failure_label: str,
        run_query: Callable[[SPARQLWrapper], Any],
    ) -> Any:
        errors: list[Exception] = []
        for endpoint in self._endpoint_candidates():
            sparql = SPARQLWrapper(endpoint)
            sparql.setQuery(query)
            sparql.setReturnFormat(return_format)
            sparql.setTimeout(self.timeout_sec)
            logger.info(
                "[SelfQueryLLM] %s | endpoint=%s | timeout=%ss | query_preview=%s",
                request_label,
                endpoint,
                self.timeout_sec,
                self._short(query),
            )
            try:
                return run_query(sparql)
            except Exception as error:
                errors.append(error)
                logger.warning(
                    "[SelfQueryLLM] %s for endpoint=%s | error=%s",
                    failure_label,
                    endpoint,
                    str(error),
                )

        if errors:
            raise errors[-1]
        raise RuntimeError("No SPARQL endpoint candidates available")

    def _run_raw_json(self, query: str) -> dict[str, Any]:
        query_type = self._query_type(query)
        return_format = TURTLE if query_type == "DESCRIBE" else JSON

        def _runner(sparql: SPARQLWrapper) -> dict[str, Any]:
            if query_type == "DESCRIBE":
                result = sparql.query().convert()
                if isinstance(result, bytes):
                    turtle = result.decode("utf-8", errors="ignore")
                else:
                    turtle = str(result)
                preview, score = self._score_construct_payload(turtle, "")
                return {
                    "results": {
                        "bindings": [
                            {
                                "describe": {
                                    "type": "literal",
                                    "value": preview,
                                }
                            }
                        ]
                    },
                    "_describe_score": score,
                }
            return sparql.queryAndConvert()

        return self._run_with_endpoint_retry(
            query=query,
            return_format=return_format,
            request_label="SPARQL JSON request",
            failure_label="SPARQL JSON request failed",
            run_query=_runner,
        )

    def _run_construct(self, query: str) -> str:
        def _runner(sparql: SPARQLWrapper) -> str:
            result = sparql.query().convert()
            if isinstance(result, bytes):
                return result.decode("utf-8", errors="ignore")
            return str(result)

        return self._run_with_endpoint_retry(
            query=query,
            return_format=TURTLE,
            request_label="SPARQL CONSTRUCT request",
            failure_label="SPARQL CONSTRUCT request failed",
            run_query=_runner,
        )

    def _score_json_payload(self, payload: dict[str, Any], user_query: str) -> tuple[str, float]:
        query_tokens = set(TEXT_TOKEN_RE.findall(user_query.lower()))
        bindings = payload.get("results", {}).get("bindings", [])
        if not bindings and "boolean" in payload:
            answer = str(payload.get("boolean"))
            score = 1.0 if payload.get("boolean") else 0.2
            return f"ASK result: {answer}", score

        lines: list[str] = []
        lexical_hits = 0
        for row in bindings[: self.max_rows]:
            compact: dict[str, str] = {}
            for key, value in row.items():
                text = value.get("value", "")
                compact[key] = text
                tokenized = set(TEXT_TOKEN_RE.findall(text.lower()))
                lexical_hits += len(query_tokens.intersection(tokenized))
            lines.append(json.dumps(compact, ensure_ascii=False))

        preview = "\n".join(lines) if lines else "No rows returned"
        score = min(1.0, (len(lines) / max(1, self.max_rows)) + (lexical_hits * 0.03))
        if "_describe_score" in payload:
            score = max(score, float(payload.get("_describe_score", 0.0)))
        return preview, score

    def _tokenize_user_query(self, user_query: str) -> list[str]:
        seen: set[str] = set()
        tokens: list[str] = []
        for token in USER_QUERY_TOKEN_RE.findall(user_query.lower()):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= self.lexical_max_tokens:
                break
        return tokens

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.split()).strip().lower()

    def _build_lexical_candidates(self, user_query: str) -> list[str]:
        tokens = self._tokenize_user_query(user_query)
        if not tokens:
            return []

        filters: list[str] = []
        for token in tokens:
            escaped = self._escape_literal(token)
            if self.lexical_match_literals:
                filters.append(f"CONTAINS(LCASE(STR(?o)), LCASE('{escaped}'))")
            if self.lexical_match_labels:
                filters.append(f"CONTAINS(LCASE(STR(?label)), LCASE('{escaped}'))")
            if self.lexical_match_iri_local_names:
                filters.append(f"CONTAINS(LCASE(REPLACE(STR(?s), '^.*[#/]', '')), LCASE('{escaped}'))")
                filters.append(f"CONTAINS(LCASE(REPLACE(STR(?o), '^.*[#/]', '')), LCASE('{escaped}'))")
            if self.lexical_match_predicates:
                filters.append(f"CONTAINS(LCASE(REPLACE(STR(?p), '^.*[#/]', '')), LCASE('{escaped}'))")

        if not filters:
            return []

        where = " || ".join(filters)
        queries: list[str] = []

        queries.append(
            "SELECT ?s ?p ?o ?label WHERE { "
            "?s ?p ?o . "
            "OPTIONAL { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label } "
            "OPTIONAL { ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label } "
            f"FILTER({where}) "
            f"}} LIMIT {self.max_rows}"
        )

        queries.append(
            "SELECT ?s ?label WHERE { "
            "?s a ?type . "
            "OPTIONAL { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label } "
            "OPTIONAL { ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label } "
            f"FILTER({where}) "
            f"}} LIMIT {self.max_rows}"
        )

        return queries[: self.lexical_max_candidates]

    def _score_construct_payload(self, turtle_payload: str, user_query: str) -> tuple[str, float]:
        query_tokens = set(TEXT_TOKEN_RE.findall(user_query.lower()))
        lines = [line.strip() for line in turtle_payload.splitlines() if line.strip() and not line.strip().startswith("@prefix")]
        lines = lines[: self.max_triples]

        lexical_hits = 0
        for line in lines:
            tokens = set(TEXT_TOKEN_RE.findall(line.lower()))
            lexical_hits += len(query_tokens.intersection(tokens))

        preview = "\n".join(lines) if lines else "No triples returned"
        score = min(1.0, (len(lines) / max(1, self.max_triples)) + (lexical_hits * 0.03))
        return preview, score

    def _escape_literal(self, raw: str) -> str:
        return raw.replace("\\", "\\\\").replace("'", "\\'")

    def _fallback_query(self, user_query: str) -> str:
        escaped = self._escape_literal(user_query)
        return (
            "SELECT ?s ?p ?o WHERE { "
            "?s ?p ?o . "
            f"FILTER(CONTAINS(LCASE(STR(?s)), LCASE('{escaped}')) || CONTAINS(LCASE(STR(?o)), LCASE('{escaped}'))) "
            f"}} LIMIT {self.max_rows}"
        )

    def _short(self, value: str, max_len: int = 160) -> str:
        compact = " ".join(value.split())
        if len(compact) <= max_len:
            return compact
        return f"{compact[:max_len]}..."
