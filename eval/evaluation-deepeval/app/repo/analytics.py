"""
Aggregate evaluation snapshots with pandas for the scientific summary UI.
"""

from __future__ import annotations

import math

import pandas as pd

from app.repo.snapshot import Snapshot


def _norm_label(raw: str | None) -> str:
    text = (raw or "").strip()
    return text if text else "(no label)"


def snapshot_to_frame(snap: Snapshot) -> pd.DataFrame:
    """One row per (model, test_id, metric)."""
    rows: list[dict] = []
    for model_id, results in snap.models.items():
        for test_id, ev in results.items():
            label = _norm_label(
                snap.tests[test_id].label if test_id in snap.tests else None
            )
            res = ev.result
            test_success = bool(res.success) if res else False
            metrics = res.metrics_data if (res and res.metrics_data) else []
            if not metrics:
                rows.append(
                    {
                        "model": model_id,
                        "test_id": test_id,
                        "label": label,
                        "status": ev.status,
                        "metric": None,
                        "score": None,
                        "metric_success": None,
                        "test_success": test_success,
                    }
                )
                continue
            for md in metrics:
                rows.append(
                    {
                        "model": model_id,
                        "test_id": test_id,
                        "label": label,
                        "status": ev.status,
                        "metric": md.name,
                        "score": md.score,
                        "metric_success": bool(md.success),
                        "test_success": test_success,
                    }
                )
    return pd.DataFrame(rows)


def _safe_float(value: float | None) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def _result_duration_tokens(res) -> tuple[float | None, float | None]:
    """Match UI: completion_time / token_cost, then additional_metadata duration / total_tokens."""
    if res is None:
        return None, None
    sec = getattr(res, "completion_time", None)
    tokens = getattr(res, "token_cost", None)
    meta = getattr(res, "additional_metadata", None)
    if meta is not None:
        if hasattr(meta, "model_dump"):
            meta = meta.model_dump()
        if isinstance(meta, dict):
            if meta.get("duration") is not None:
                sec = meta.get("duration")
            if meta.get("total_tokens") is not None:
                tokens = meta.get("total_tokens")
    try:
        sec = float(sec) if sec is not None else None
    except (TypeError, ValueError):
        sec = None
    try:
        tokens = float(tokens) if tokens is not None else None
    except (TypeError, ValueError):
        tokens = None
    return sec, tokens


def _usage_row_per_test(snap: Snapshot) -> pd.DataFrame:
    """One row per (model, test_id): eval wall time (s) and token count from TestResult."""
    rows: list[dict] = []
    for model_id, results in snap.models.items():
        for test_id, ev in results.items():
            res = ev.result
            duration_sec, token_count = _result_duration_tokens(res)
            rows.append(
                {
                    "model": model_id,
                    "test_id": test_id,
                    "duration_sec": duration_sec,
                    "tokens": token_count,
                }
            )
    return pd.DataFrame(rows)


def _mean_std_n(series: pd.Series) -> dict[str, float | int | None]:
    valid = series.dropna()
    count = int(valid.shape[0])
    if count == 0:
        return {"mean": None, "std": None, "n": 0}
    mean_val = float(valid.mean())
    std_val = float(valid.std(ddof=0)) if count > 1 else 0.0
    return {
        "mean": _safe_float(mean_val),
        "std": _safe_float(std_val),
        "n": count,
    }


def _metric_stats(group: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    """mean, std, n per metric name inside a grouped slice."""
    out: dict[str, dict[str, float | int | None]] = {}
    sub = group[group["metric"].notna()]
    if sub.empty:
        return out
    for metric_name, chunk in sub.groupby("metric", sort=True):
        scores = chunk["score"].dropna()
        count = int(scores.shape[0])
        if count == 0:
            out[str(metric_name)] = {"mean": None, "std": None, "n": 0}
            continue
        mean_val = float(scores.mean())
        std_val = float(scores.std(ddof=0)) if count > 1 else 0.0
        out[str(metric_name)] = {
            "mean": _safe_float(mean_val),
            "std": _safe_float(std_val),
            "n": count,
        }
    return out


def summarize_by_model(df: pd.DataFrame, snap: Snapshot, usage: pd.DataFrame | None = None) -> list[dict]:
    """Per subject model: test counts, errors, pass rate, time/tokens, per-metric stats."""
    if usage is None:
        usage = _usage_row_per_test(snap)
    if df.empty:
        if usage.empty:
            return []
        rows_out: list[dict] = []
        for model_id, uchunk in usage.groupby("model", sort=True):
            rows_out.append(
                {
                    "model": model_id,
                    "n_tests": int(uchunk.shape[0]),
                    "errors": 0,
                    "pass_rate": None,
                    "time_sec": _mean_std_n(uchunk["duration_sec"]),
                    "tokens": _mean_std_n(uchunk["tokens"]),
                    "by_metric": {},
                }
            )
        return rows_out
    # One row per (model, test_id) for error / success / n_tests
    first = df.groupby(["model", "test_id"], sort=True).first().reset_index()
    rows_out: list[dict] = []
    for model_id, chunk in first.groupby("model", sort=True):
        error_mask = chunk["status"].astype(str) == "error"
        errors = int(error_mask.sum())
        n_tests = int(chunk.shape[0])
        pass_rate = (
            float(chunk["test_success"].mean())
            if n_tests and chunk["test_success"].notna().any()
            else None
        )
        metric_slice = df[df["model"] == model_id]
        uchunk = usage[usage["model"] == model_id] if not usage.empty else usage
        rows_out.append(
            {
                "model": model_id,
                "n_tests": n_tests,
                "errors": errors,
                "pass_rate": _safe_float(pass_rate) if pass_rate is not None else None,
                "time_sec": _mean_std_n(uchunk["duration_sec"]),
                "tokens": _mean_std_n(uchunk["tokens"]),
                "by_metric": _metric_stats(metric_slice),
            }
        )
    return rows_out


def summarize_model_label_matrix(df: pd.DataFrame, metric: str) -> dict:
    """
    Heatmap payload: labels as rows, models as columns; mean ± std per cell.
    """
    sub = df[(df["metric"] == metric) & df["score"].notna()]
    models = sorted(sub["model"].dropna().unique().tolist())
    labels = sorted(sub["label"].dropna().unique().tolist())
    cells_mean: list[list[float | None]] = []
    cells_std: list[list[float | None]] = []
    cells_n: list[list[int]] = []
    for lab in labels:
        row_mean: list[float | None] = []
        row_std: list[float | None] = []
        row_n: list[int] = []
        for model_id in models:
            piece = sub[(sub["label"] == lab) & (sub["model"] == model_id)][
                "score"
            ]
            count = int(piece.shape[0])
            if count == 0:
                row_mean.append(None)
                row_std.append(None)
                row_n.append(0)
                continue
            row_mean.append(_safe_float(float(piece.mean())))
            row_std.append(
                _safe_float(float(piece.std(ddof=0))) if count > 1 else 0.0
            )
            row_n.append(count)
        cells_mean.append(row_mean)
        cells_std.append(row_std)
        cells_n.append(row_n)

    # Footer row ALL: per model over all labels
    row_all_mean: list[float | None] = []
    row_all_std: list[float | None] = []
    row_all_n: list[int] = []
    for model_id in models:
        piece = sub[sub["model"] == model_id]["score"]
        count = int(piece.shape[0])
        if count == 0:
            row_all_mean.append(None)
            row_all_std.append(None)
            row_all_n.append(0)
            continue
        row_all_mean.append(_safe_float(float(piece.mean())))
        row_all_std.append(
            _safe_float(float(piece.std(ddof=0))) if count > 1 else 0.0
        )
        row_all_n.append(count)

    return {
        "metric": metric,
        "rows": labels + ["ALL"],
        "cols": models,
        "cells_mean": cells_mean + [row_all_mean],
        "cells_std": cells_std + [row_all_std],
        "cells_n": cells_n + [row_all_n],
    }


def build_summary(snap: Snapshot) -> dict:
    df = snapshot_to_frame(snap)
    usage_df = _usage_row_per_test(snap)
    metrics = sorted(df["metric"].dropna().unique().tolist())
    matrix: dict[str, dict] = {}
    for metric_name in metrics:
        matrix[metric_name] = summarize_model_label_matrix(df, metric_name)
    n_tests_df = int(df["test_id"].nunique()) if not df.empty else 0
    n_models_df = int(df["model"].nunique()) if not df.empty else 0
    n_tests_u = int(usage_df["test_id"].nunique()) if not usage_df.empty else 0
    n_models_u = int(usage_df["model"].nunique()) if not usage_df.empty else 0
    return {
        "metrics": metrics,
        "per_model": summarize_by_model(df, snap, usage_df),
        "matrix": matrix,
        "n_tests": max(n_tests_df, n_tests_u),
        "n_models": max(n_models_df, n_models_u),
    }
