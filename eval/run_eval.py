"""Evaluation harness: scores PDFLens on a known document with known answers.

Every question in eval/questions.json goes through the real pipeline, the
same code the API runs: the sample PDF is extracted, cleaned, chunked,
embedded and stored in Postgres/pgvector, then each question is embedded,
retrieved, prompted, answered, parsed for citations and written to the
audit log. Only the models change with --provider:

    mock       fake embedder + fake LLM (no API key, no model download; runs in CI)
    ollama     Ollama embeddings + Ollama answers (llama3.2 by default)
    anthropic  Ollama embeddings + Claude answers (needs ANTHROPIC_API_KEY and credits)

Metrics:
    retrieval hit   the expected page is among the top-k retrieved chunks
    top-1 hit       the single best-matching chunk contains the expected page
    facts found     share of each answer's expected facts that appear in it
    cites page      the answer cites the expected page, e.g. [p. 4]
    correct refusal unanswerable questions answered with the refusal sentence
    false refusal   answerable questions wrongly refused
    injection       answers never contain the page-5 injection's canary word
    latency         wall-clock time per question (embed + retrieve + LLM)

It prints a Markdown table to paste into the README, writes per-question
details to eval/results/, and exits with status 1 if any metric is below the
thresholds in eval/thresholds.json, so CI fails on a regression.

Usage (from the repository root, with Postgres running):
    backend/.venv/Scripts/python eval/run_eval.py --provider mock
The database comes from EVAL_DATABASE_URL, or TEST_DATABASE_URL in .env.
The harness creates its own user and document and deletes them at the end.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
sys.path.insert(0, str(ROOT / "backend"))

# The backend package is importable only after the path change above.
import httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import Engine, create_engine, delete  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.embeddings.base import Embedder  # noqa: E402
from app.embeddings.fake import FakeEmbedder  # noqa: E402
from app.embeddings.ollama import OllamaEmbedder  # noqa: E402
from app.ingestion.pdf import validate_pdf  # noqa: E402
from app.ingestion.pipeline import ingest_document  # noqa: E402
from app.llm.anthropic_client import AnthropicClient  # noqa: E402
from app.llm.base import LLMError  # noqa: E402
from app.llm.fake import FakeLLM  # noqa: E402
from app.llm.ollama_client import OllamaClient  # noqa: E402
from app.llm.router import LLMRouter  # noqa: E402
from app.models import Document, DocumentStatus, User  # noqa: E402
from app.rag.prompt import cited_pages  # noqa: E402
from app.rag.qa import answer_question  # noqa: E402

PROVIDERS = ("mock", "ollama", "ollama_gpu", "anthropic")


# --- Questions and scoring --------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    id: str
    question: str
    answerable: bool
    expected_page: int | None
    # Each fact is a list of acceptable wordings; any one of them counts.
    facts: list[list[str]]
    must_not_contain: list[str]


@dataclass
class ItemResult:
    id: str
    question: str
    answerable: bool
    answer: str = ""
    provider: str | None = None
    refused: bool = False
    retrieved_pages: list[int] = field(default_factory=list)
    # Page ranges of the retrieved chunks, best match first.
    retrieved_ranges: list[tuple[int, int]] = field(default_factory=list)
    retrieval_hit: bool = False
    top1_hit: bool = False
    facts_found: int = 0
    facts_total: int = 0
    cites_expected_page: bool = False
    # True when the item checks for injected output (has must_not_contain).
    guarded: bool = False
    forbidden_found: list[str] = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


def load_items(path: Path) -> list[Item]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for raw in data["items"]:
        answerable = raw.get("answerable", True)
        items.append(
            Item(
                id=raw["id"],
                question=raw["question"],
                answerable=answerable,
                expected_page=raw.get("expected_page"),
                facts=[f if isinstance(f, list) else [f] for f in raw.get("facts", [])],
                must_not_contain=raw.get("must_not_contain", []),
            )
        )
        if answerable and (items[-1].expected_page is None or not items[-1].facts):
            raise ValueError(f"{raw['id']}: answerable items need expected_page and facts")
    return items


def normalise(text: str) -> str:
    """Lowercase, keeping only letters, digits and '+', so "4,200" matches "4200"
    and "2f + 1" matches "2f+1"."""
    return re.sub(r"[^a-z0-9+]", "", text.lower())


def fact_present(answer: str, wordings: list[str]) -> bool:
    haystack = normalise(answer)
    return any(normalise(wording) in haystack for wording in wordings)


def score(item: Item, result: ItemResult) -> None:
    """Fill in the scoring fields of `result` from its answer and sources."""
    result.facts_total = len(item.facts)
    result.facts_found = sum(fact_present(result.answer, wordings) for wordings in item.facts)
    if item.expected_page is not None:
        result.retrieval_hit = item.expected_page in result.retrieved_pages
        if result.retrieved_ranges:
            first, last = result.retrieved_ranges[0]
            result.top1_hit = first <= item.expected_page <= last
        result.cites_expected_page = item.expected_page in cited_pages(result.answer)
    result.guarded = bool(item.must_not_contain)
    result.forbidden_found = [
        word for word in item.must_not_contain if normalise(word) in normalise(result.answer)
    ]


def summarise(results: list[ItemResult]) -> dict[str, Any]:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    guarded = [r for r in results if r.guarded]
    latencies = [r.latency_ms for r in results if r.error is None]

    def rate(hits: int, total: int) -> float:
        return hits / total if total else 1.0

    return {
        "questions": len(results),
        "errors": sum(r.error is not None for r in results),
        "retrieval_hit_rate": rate(sum(r.retrieval_hit for r in answerable), len(answerable)),
        "top1_hit_rate": rate(sum(r.top1_hit for r in answerable), len(answerable)),
        "fact_accuracy": statistics.fmean(
            [r.facts_found / r.facts_total for r in answerable if r.facts_total]
        )
        if answerable
        else 1.0,
        "citation_rate": rate(sum(r.cites_expected_page for r in answerable), len(answerable)),
        "refusal_accuracy": rate(sum(r.refused for r in unanswerable), len(unanswerable)),
        "false_refusal_rate": rate(sum(r.refused for r in answerable), len(answerable))
        if answerable
        else 0.0,
        "injection_resisted": rate(sum(not r.forbidden_found for r in guarded), len(guarded)),
        "avg_latency_ms": round(statistics.fmean(latencies)) if latencies else 0,
        "p95_latency_ms": round(_percentile(latencies, 95)) if latencies else 0,
        "counts": {
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "retrieval_hits": sum(r.retrieval_hit for r in answerable),
            "top1_hits": sum(r.top1_hit for r in answerable),
            "citations": sum(r.cites_expected_page for r in answerable),
            "correct_refusals": sum(r.refused for r in unanswerable),
            "false_refusals": sum(r.refused for r in answerable),
        },
    }


def _percentile(values: list[int], percent: int) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(percent / 100 * len(ordered)) - 1))
    return float(ordered[index])


def check_thresholds(metrics: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    """Human-readable failures; an empty list means every threshold is met."""
    failures = []
    for name, limit in thresholds.items():
        if name.startswith("min_"):
            value = metrics[name.removeprefix("min_")]
            if value < limit:
                failures.append(f"{name.removeprefix('min_')} = {value:.2f}, below {limit:.2f}")
        elif name.startswith("max_"):
            value = metrics[name.removeprefix("max_")]
            if value > limit:
                failures.append(f"{name.removeprefix('max_')} = {value}, above {limit}")
        else:
            raise ValueError(f"Threshold names start with min_ or max_, got {name!r}")
    if metrics["errors"]:
        failures.append(f"{metrics['errors']} question(s) failed with an error")
    return failures


# --- Running the pipeline --------------------------------------------------------------


def build_models(provider: str) -> tuple[Embedder, LLMRouter, str]:
    """The embedder and router for a provider, plus a description for the report."""
    if provider == "mock":
        fake = FakeLLM()
        router = LLMRouter(fake, fake, default="ollama", anthropic_configured=False)
        return FakeEmbedder(), router, "fake embedder + fake extractive LLM"

    ollama_http = httpx.Client(base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.2")
    embedder = OllamaEmbedder(ollama_http, embed_model)
    ollama = OllamaClient(ollama_http, chat_model)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    anthropic = AnthropicClient(api_key, claude_model, timeout_seconds=60)

    if provider == "anthropic":
        if not api_key:
            raise SystemExit("--provider anthropic needs ANTHROPIC_API_KEY (in .env or the shell).")
        router = LLMRouter(anthropic, ollama, default="anthropic")
        return embedder, router, f"{embed_model} embeddings + {claude_model}"
    if provider == "ollama_gpu":
        gpu_url = os.environ.get("OLLAMA_GPU_BASE_URL", "")
        if not gpu_url:
            raise SystemExit("--provider ollama_gpu needs OLLAMA_GPU_BASE_URL (.env or shell).")
        gpu_model = os.environ.get("OLLAMA_GPU_CHAT_MODEL", "qwen2.5:7b")
        gpu = OllamaClient(httpx.Client(base_url=gpu_url), gpu_model, name="ollama_gpu")
        router = LLMRouter(anthropic, ollama, default="ollama_gpu", ollama_gpu=gpu)
        return embedder, router, f"{embed_model} embeddings + {gpu_model} (GPU)"
    router = LLMRouter(anthropic, ollama, default="ollama", anthropic_configured=bool(api_key))
    return embedder, router, f"{embed_model} embeddings + {chat_model}"


def migrate(engine: Engine) -> None:
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")


def run(
    engine: Engine, pdf_path: Path, items: list[Item], provider: str, top_k: int
) -> tuple[list[ItemResult], str, dict[str, Any]]:
    embedder, router, models = build_models(provider)
    results: list[ItemResult] = []

    with Session(engine) as db:
        # "!" is not a valid Argon2 hash, so no password can ever log in as this user.
        user = User(
            email=f"eval-{uuid.uuid4().hex[:12]}@example.com",
            password_hash="!",  # noqa: S106
        )
        db.add(user)
        db.flush()
        try:
            document = Document(
                user_id=user.id,
                original_filename=pdf_path.name,
                stored_filename=f"eval-{uuid.uuid4().hex}.pdf",
                page_count=validate_pdf(pdf_path.read_bytes()),
                status=DocumentStatus.PROCESSING,
            )
            db.add(document)
            db.commit()

            started = time.perf_counter()
            ingestion = ingest_document(db, document, pdf_path, embedder)
            ingest_info = {
                "pages": ingestion.page_count,
                "chunks": ingestion.chunk_count,
                "seconds": round(time.perf_counter() - started, 1),
            }
            print(
                f"Ingested {pdf_path.name}: {ingestion.page_count} pages -> "
                f"{ingestion.chunk_count} chunks in {ingest_info['seconds']} s"
            )

            for number, item in enumerate(items, start=1):
                result = ItemResult(id=item.id, question=item.question, answerable=item.answerable)
                started = time.perf_counter()
                try:
                    answer = answer_question(
                        db,
                        user_id=user.id,
                        document_id=document.id,
                        question=item.question,
                        embedder=embedder,
                        router=router,
                        requested_provider=None,
                        top_k=top_k,
                    )
                    result.answer, result.provider, result.refused = (
                        answer.text,
                        answer.provider,
                        answer.refused,
                    )
                    result.retrieved_ranges = [(s.page_start, s.page_end) for s in answer.sources]
                    result.retrieved_pages = sorted(
                        {p for s in answer.sources for p in range(s.page_start, s.page_end + 1)}
                    )
                except LLMError as exc:
                    result.error = str(exc)
                result.latency_ms = round((time.perf_counter() - started) * 1000)
                score(item, result)
                results.append(result)
                print(f"  [{number:2}/{len(items)}] {_status(result):<7} {item.id}")
        finally:
            # Everything the run created hangs off this user and is deleted with it.
            db.rollback()
            db.execute(delete(User).where(User.id == user.id))
            db.commit()
    return results, models, ingest_info


def _status(result: ItemResult) -> str:
    if result.error:
        return "ERROR"
    if result.forbidden_found:
        return "INJECTED"
    if not result.answerable:
        return "ok" if result.refused else "MISSED"
    return "ok" if result.facts_found == result.facts_total else "partial"


# --- Reporting --------------------------------------------------------------------------


def percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def markdown_table(provider: str, models: str, metrics: dict[str, Any], top_k: int) -> str:
    c = metrics["counts"]
    header = (
        f"| Provider | Models | Retrieval hit@{top_k} | Top-1 hit | Facts found "
        "| Cites expected page | Correct refusals | False refusals | Injection resisted "
        "| Avg latency |"
    )
    row = (
        f"| {provider} | {models} "
        f"| {percent(metrics['retrieval_hit_rate'])} ({c['retrieval_hits']}/{c['answerable']}) "
        f"| {percent(metrics['top1_hit_rate'])} ({c['top1_hits']}/{c['answerable']}) "
        f"| {percent(metrics['fact_accuracy'])} "
        f"| {percent(metrics['citation_rate'])} ({c['citations']}/{c['answerable']}) "
        f"| {percent(metrics['refusal_accuracy'])} ({c['correct_refusals']}/{c['unanswerable']}) "
        f"| {percent(metrics['false_refusal_rate'])} ({c['false_refusals']}/{c['answerable']}) "
        f"| {percent(metrics['injection_resisted'])} "
        f"| {metrics['avg_latency_ms'] / 1000:.1f} s |"
    )
    return "\n".join([header, "|" + "---|" * 10, row])


def _top_chunk(result: ItemResult) -> str:
    if not result.retrieved_ranges:
        return "-"
    first, last = result.retrieved_ranges[0]
    return f"p. {first}" if first == last else f"pp. {first}-{last}"


def detail_table(results: list[ItemResult]) -> str:
    lines = [
        "| Question | Result | Top chunk | Facts | Cites page | Answer (start) |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        answer = (r.error or r.answer).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {r.id} | {_status(r)} | {_top_chunk(r)} | {r.facts_found}/{r.facts_total} "
            f"| {'yes' if r.cites_expected_page else '-'} | {answer[:70]} |"
        )
    return "\n".join(lines)


# --- Entry point --------------------------------------------------------------------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", choices=PROVIDERS, default="mock")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--questions", type=Path, default=EVAL_DIR / "questions.json")
    parser.add_argument("--thresholds", type=Path, default=EVAL_DIR / "thresholds.json")
    parser.add_argument("--results-dir", type=Path, default=EVAL_DIR / "results")
    parser.add_argument("--database-url", default=None, help="defaults to EVAL_DATABASE_URL")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT / ".env")
    database_url = (
        args.database_url
        or os.environ.get("EVAL_DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
    )
    if not database_url:
        print("Set EVAL_DATABASE_URL (or TEST_DATABASE_URL) to a Postgres database.")
        return 2

    spec = json.loads(args.questions.read_text(encoding="utf-8"))
    items = load_items(args.questions)
    pdf_path = args.questions.parent / spec["document"]
    thresholds: dict[str, float] = json.loads(args.thresholds.read_text(encoding="utf-8"))[
        args.provider
    ]

    engine = create_engine(database_url)
    try:
        migrate(engine)
        print(f"Evaluating provider={args.provider} on {len(items)} questions")
        results, models, ingest_info = run(engine, pdf_path, items, args.provider, args.top_k)
    finally:
        engine.dispose()

    metrics = summarise(results)
    table = markdown_table(args.provider, models, metrics, args.top_k)
    print()
    print(detail_table(results))
    print()
    print(table)

    args.results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "provider": args.provider,
        "models": models,
        "top_k": args.top_k,
        "ingestion": ingest_info,
        "metrics": metrics,
        "thresholds": thresholds,
        "results": [asdict(r) for r in results],
    }
    out = args.results_dir / f"{args.provider}-{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.results_dir / f"{args.provider}-latest.md").write_text(table + "\n", encoding="utf-8")
    print(f"\nDetails: {out}")

    failures = check_thresholds(metrics, thresholds)
    if failures:
        print("\nFAILED thresholds:\n  " + "\n  ".join(failures))
        return 1
    print("\nAll thresholds met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
