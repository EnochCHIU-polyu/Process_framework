"""
Async LLM-as-a-Judge for the PROCESS framework.

Uses the configured LLM backend (Ollama or any OpenAI-compatible endpoint
such as Poe) to automatically score an assistant response on LENS-aligned
hallucination evaluation dimensions.

LENS reference:
  Chen, K. et al. (2024) DiaHalu: A Dialogue-level Hallucination Evaluation
  Benchmark for Large Language Models. EMNLP 2024, Findings.
  https://doi.org/10.18653/v1/2024.findings-emnlp.529

Usage::

    from process_framework.api.llm_judge import llm_judge_evaluate
    scores = await llm_judge_evaluate("What is a black hole?", "A black hole is …", settings)
    # → {"factual_grounding": 5, "semantic_correctness": 4, "reasoning_quality": 5,
    #    "hallucination_level": 5, "answer_accuracy": 4}
"""

from __future__ import annotations

import json
import re
from typing import Dict

from process_framework.api.config import Settings
from process_framework.api.llm import call_llm

# Dimensions returned by the LLM judge (must match EvaluationDimension values)
JUDGE_DIMENSIONS: tuple[str, ...] = (
    "factual_grounding",    # LENS Layer 1 — entity / factual consistency
    "semantic_correctness", # LENS Layer 2 — semantic accuracy
    "reasoning_quality",    # LENS Layer 3 — reasoning coherence
    "hallucination_level",  # existing dimension — overall hallucination level
    "answer_accuracy",      # existing dimension — overall accuracy
)

_JUDGE_PROMPT_TEMPLATE = """\
You are an expert AI response evaluator using the LENS hallucination \
evaluation framework (DiaHalu, EMNLP 2024).

Evaluate the assistant's response for the following conversation turn and \
return a JSON object with integer scores 1–5 for each dimension \
(1 = worst, 5 = best):

Dimensions:
- factual_grounding:    Are all facts and entities correct and well-grounded? \
(LENS Layer 1)
- semantic_correctness: Is the meaning accurate and semantically correct? \
(LENS Layer 2)
- reasoning_quality:    Is the reasoning logical and coherent? \
(LENS Layer 3)
- hallucination_level:  Overall absence of hallucinations \
(5 = no hallucination, 1 = severe hallucination)
- answer_accuracy:      Does the response correctly answer the user's question?

User input:
{user_input}

Assistant response:
{actual_output}

Return ONLY a valid JSON object, for example:
{{"factual_grounding": 4, "semantic_correctness": 5, \
"reasoning_quality": 4, "hallucination_level": 5, "answer_accuracy": 4}}
"""


async def llm_judge_evaluate(
    user_input: str,
    actual_output: str,
    settings: Settings,
    temperature: float = 0.0,
) -> Dict[str, int]:
    """
    Ask the configured LLM to score an assistant response on LENS dimensions.

    Args:
        user_input:    The user's original message.
        actual_output: The assistant's response to evaluate.
        settings:      Loaded :class:`~process_framework.api.config.Settings`.
        temperature:   Sampling temperature (default 0 for deterministic scoring).

    Returns:
        A dict mapping each LENS dimension name to an integer score (1–5).
        On any parsing or upstream error the function returns an empty dict
        so that the calling code can gracefully skip automated scoring.
    """
    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        user_input=user_input.strip(),
        actual_output=actual_output.strip(),
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await call_llm(messages, settings, temperature=temperature)
    except Exception:  # noqa: BLE001  — degrade gracefully on any LLM error
        return {}

    return _parse_scores(raw)


def _parse_scores(raw: str) -> Dict[str, int]:
    """
    Extract the first JSON object from *raw* and validate the scores.

    Returns an empty dict if parsing fails or no valid scores are found.
    """
    # Find the first {...} block (the LLM may wrap it in prose)
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        return {}

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {}

    scores: Dict[str, int] = {}
    for dim in JUDGE_DIMENSIONS:
        raw_val = data.get(dim)
        if raw_val is None:
            continue
        try:
            score = int(raw_val)
            if 1 <= score <= 5:
                scores[dim] = score
        except (TypeError, ValueError):
            pass

    return scores
