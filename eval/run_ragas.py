# eval/run_ragas.py
#
# Evaluates the Financial & Regulatory Intelligence Agent using RAGAS metrics.
#
# Metrics scored:
#   faithfulness      — does the answer only contain facts present in retrieved contexts?
#   answer_relevancy  — does the answer directly address the question?
#   context_recall    — does the retrieved context contain the ground truth information?
#   context_precision — is the retrieved context free of irrelevant noise?
#
# Usage:
#   python eval/run_ragas.py                     # run all questions
#   python eval/run_ragas.py --category sql_only # run one category
#   python eval/run_ragas.py --id cross_001      # run one question by id

import os
import sys
import json
import argparse
import django
from datetime import datetime
from typing import Optional

# ── Django bootstrap ──────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
django.setup()
# ─────────────────────────────────────────────────────────────────────────────

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_recall,
    context_precision,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from rag_app.agent import run_agent, clear_session
from rag_app.utils.llm_factory import get_llm


GOLDEN_DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
REPORT_PATH         = os.path.join(os.path.dirname(__file__), "eval_report.json")
EVAL_SESSION_PREFIX = "__ragas_eval__"


def load_golden_dataset(
    category: Optional[str] = None,
    question_id: Optional[str] = None,
) -> list:
    with open(GOLDEN_DATASET_PATH, "r") as f:
        data = json.load(f)

    if question_id:
        data = [q for q in data if q["id"] == question_id]
    elif category:
        data = [q for q in data if q["category"] == category]

    if not data:
        raise ValueError(
            f"No questions found for category='{category}' id='{question_id}'"
        )
    return data


def run_evaluation(questions: list) -> dict:
    """
    Runs the agent on each question, collects answers + contexts,
    then scores them with RAGAS.
    """
    print(f"\n{'─'*60}")
    print(f"  Financial RAG Evaluation  —  {len(questions)} question(s)")
    print(f"{'─'*60}\n")

    # Collect agent responses for each question
    ragas_rows = []

    for i, item in enumerate(questions, 1):
        qid      = item["id"]
        question = item["question"]
        truth    = item["ground_truth"]

        session_id = f"{EVAL_SESSION_PREFIX}{qid}"
        clear_session(session_id)   # ensure clean state

        print(f"[{i}/{len(questions)}] {qid}: {question[:70]}...")

        result   = run_agent(question=question, session_id=session_id)
        answer   = result["answer"]
        contexts = result["contexts"]

        # RAGAS needs at least one context — if tools returned nothing,
        # provide the question itself as a fallback so scoring doesn't crash
        if not contexts:
            contexts = [f"No context retrieved for: {question}"]

        tools_used = [t["tool"] for t in result["tool_calls"]]
        print(f"         tools: {tools_used}")
        print(f"         answer preview: {answer[:100]}...\n")

        ragas_rows.append({
            "question":   question,
            "answer":     answer,
            "contexts":   contexts,
            "ground_truth": truth,
        })

        # Clean up eval session
        clear_session(session_id)

    # ── Build RAGAS dataset ───────────────────────────────────────────────────
    dataset = Dataset.from_dict({
        "question":     [r["question"]     for r in ragas_rows],
        "answer":       [r["answer"]       for r in ragas_rows],
        "contexts":     [r["contexts"]     for r in ragas_rows],
        "ground_truth": [r["ground_truth"] for r in ragas_rows],
    })

    # ── Configure RAGAS to use Gemini (same LLM as the agent) ────────────────
    llm = get_llm(temperature=0.0)
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )

    ragas_llm        = LangchainLLMWrapper(llm)
    ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

    metrics = [faithfulness, answer_relevancy, context_recall, context_precision]
    for metric in metrics:
        metric.llm        = ragas_llm
        metric.embeddings = ragas_embeddings

    # ── Run RAGAS scoring ─────────────────────────────────────────────────────
    print("Running RAGAS scoring...\n")
    scores = evaluate(dataset=dataset, metrics=metrics)

    return scores, ragas_rows


def print_report(scores, questions: list, ragas_rows: list):
    """Prints a human-readable report to the terminal."""
    print(f"\n{'═'*60}")
    print("  RAGAS EVALUATION REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*60}\n")

    score_dict = scores.to_pandas().mean().to_dict()

    metric_labels = {
        "faithfulness":       "Faithfulness      (answer grounded in context)",
        "answer_relevancy":   "Answer relevancy  (directly addresses question)",
        "context_recall":     "Context recall    (retrieved context covers truth)",
        "context_precision":  "Context precision (retrieved context is focused)",
    }

    print("  AGGREGATE SCORES\n")
    overall = []
    for key, label in metric_labels.items():
        score = score_dict.get(key, 0.0)
        overall.append(score)
        bar   = "█" * int(score * 20)
        space = "░" * (20 - len(bar))
        grade = "GOOD" if score >= 0.75 else ("OK" if score >= 0.50 else "NEEDS WORK")
        print(f"  {label}")
        print(f"  {bar}{space}  {score:.3f}  [{grade}]\n")

    avg = sum(overall) / len(overall)
    print(f"  Overall average: {avg:.3f}")
    print(f"\n{'─'*60}\n")

    # Per-question breakdown
    print("  PER-QUESTION BREAKDOWN\n")
    df = scores.to_pandas()
    for i, (item, row) in enumerate(zip(questions, df.itertuples())):
        print(f"  [{item['id']}] {item['question'][:60]}...")
        print(f"    Faithfulness:      {getattr(row, 'faithfulness', 0):.3f}")
        print(f"    Answer relevancy:  {getattr(row, 'answer_relevancy', 0):.3f}")
        print(f"    Context recall:    {getattr(row, 'context_recall', 0):.3f}")
        print(f"    Context precision: {getattr(row, 'context_precision', 0):.3f}")
        print()

    print(f"{'═'*60}\n")


def save_report(scores, questions: list, ragas_rows: list):
    """Saves a machine-readable JSON report for CI/CD integration."""
    df         = scores.to_pandas()
    score_dict = df.mean().to_dict()

    per_question = []
    for item, row in zip(questions, df.itertuples()):
        per_question.append({
            "id":                item["id"],
            "category":          item["category"],
            "question":          item["question"],
            "ground_truth":      item["ground_truth"],
            "agent_answer":      ragas_rows[questions.index(item)]["answer"],
            "faithfulness":      round(getattr(row, "faithfulness", 0), 4),
            "answer_relevancy":  round(getattr(row, "answer_relevancy", 0), 4),
            "context_recall":    round(getattr(row, "context_recall", 0), 4),
            "context_precision": round(getattr(row, "context_precision", 0), 4),
        })

    report = {
        "timestamp":        datetime.now().isoformat(),
        "question_count":   len(questions),
        "aggregate_scores": {k: round(v, 4) for k, v in score_dict.items()},
        "overall_average":  round(sum(score_dict.values()) / len(score_dict), 4),
        "per_question":     per_question,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"  Report saved to: {REPORT_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation on the Financial RAG Agent"
    )
    parser.add_argument(
        "--category",
        choices=["sql_only", "vector_only", "cross_reference"],
        help="Run only questions from one category",
    )
    parser.add_argument(
        "--id",
        dest="question_id",
        help="Run a single question by its ID (e.g. cross_001)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip saving the JSON report",
    )
    args = parser.parse_args()

    questions = load_golden_dataset(
        category    = args.category,
        question_id = args.question_id,
    )

    scores, ragas_rows = run_evaluation(questions)
    print_report(scores, questions, ragas_rows)

    if not args.no_save:
        save_report(scores, questions, ragas_rows)


if __name__ == "__main__":
    main()