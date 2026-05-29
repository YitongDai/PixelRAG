#!/usr/bin/env python3
"""Grade eval JSONL results using GPT-4.1 LLM judge.

Implements the same 3-way grading (CORRECT / INCORRECT / NOT_ATTEMPTED) as the
paper's evaluation protocol (Appendix B.2). Compatible with output from
run_naive_simpleqa.py.

Usage:
    python grade.py simpleqa eval_output/simpleqa_naive_*.jsonl
    python grade.py nq eval_output/nq_local_api_*.jsonl --llm-judge
    python grade.py mmsearch eval_output/mmsearch_*.jsonl

Environment:
    OPENAI_API_KEY  — required for LLM judge grading
    OPENAI_BASE_URL — optional, defaults to https://api.openai.com/v1
"""

import argparse
import ast
import json
import os
import re
import string
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

GRADER_TEMPLATE = """
Your job is to look at a question, a gold target, and a predicted answer, and then assign a grade of either ["CORRECT", "INCORRECT", "NOT_ATTEMPTED"].
First, I will give examples of each grade, and then you will grade a new example.


The following are examples of CORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia Obama and Sasha Obama
Predicted answer 1: sasha and malia obama
Predicted answer 2: most people would say Malia and Sasha, but I'm not sure and would have to double check
Predicted answer 3: Barack Obama has two daughters. Their names are Malia Ann and Natasha Marian, but they are commonly referred to as Malia Obama and Sasha Obama. Malia was born on July 4, 1998, and Sasha was born on June 10, 2001.
```
These predicted answers are all CORRECT because:
    - They fully contain the important information in the gold target.
    - They do not contain any information that contradicts the gold target.
    - Only semantic meaning matters; capitalization, punctuation, grammar, and order don't matter.
    - Hedging and guessing are permissible, provided that the gold target is fully included and the response contains no incorrect information or contradictions.


The following are examples of INCORRECT predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: Malia.
Predicted answer 2: Malia, Sasha, and Susan.
Predicted answer 3: Barack Obama does not have any children.
Predicted answer 4: I think it's either Malia and Sasha. Or it could be Malia and Jackie. Or it could be Joey and Malia.
Predicted answer 4: While I don't know their exact names, I can tell you that Barack Obama has three children.
Predicted answer 5: It's possible you may mean Betsy and Olivia. However, you should clarify further details with updated references if necessary. Is that the correct answer?
Predicted answer 6: It may be the case that Obama's child is named James. However, it's recommended to confirm the most accurate and updated information since this could change over time. This model may not always reflect the most current information.
```
These predicted answers are all INCORRECT because:
    - A factual statement in the answer contradicts the gold target. Incorrect statements that have some hedging (e.g., "it is possible that", "although i'm not sure, i think") are also considered incorrect.


The following are examples of NOT_ATTEMPTED predicted answers.
```
Question: What are the names of Barack Obama's children?
Gold target: Malia and Sasha
Predicted answer 1: I don't know.
Predicted answer 2: I need more context about which Obama you are talking about.
Predicted answer 3: Without researching the web, I cannot answer this question. However, I can tell you that Barack Obama has two children.
Predicted answer 4: Barack Obama has two children. I know that one of them is Malia, but I'm not sure about the other one.
```
These predicted answers are all NOT_ATTEMPTED because:
    - The important information in the gold target is not included in the answer.
    - No statements in the answer contradict the gold target.


Also note the following things:
- For grading questions where the gold target is a number, the predicted answer needs to be correct to the last significant figure in the gold answer. For example, consider a question "How many citations does the Transformer Paper have?" with gold target "120k".
    - Predicted answers "120k", "124k", and 115k" are all CORRECT.
    - Predicted answers "100k" and "113k" are INCORRECT.
    - Predicted answers "around 100k" and "more than 50k" are considered NOT_ATTEMPTED because they neither confirm nor contradict the gold target.
- The gold target may contain more information than the question. In such cases, the predicted answer only needs to contain the information that is in the question.
    - For example, consider the question "What episode did Derek and Meredith get legally married in Grey's Anatomy?" with gold target "Season 7, Episode 20: White Wedding". Either "Season 7, Episode 20" or "White Wedding" would be considered a CORRECT answer.
- Do not punish predicted answers if they omit information that would be clearly inferred from the question.
    - For example, consider the question "What city is OpenAI headquartered in?" and the gold target "San Francisco, California". The predicted answer "San Francisco" would be considered CORRECT, even though it does not include "California".
    - Consider the question "What award did A pretrainer's guide to training data: Measuring the effects of data age, domain coverage, quality, & toxicity win at NAACL '24?", the gold target is "Outstanding Paper Award". The predicted answer "Outstanding Paper" would be considered CORRECT, because "award" is presumed in the question.
    - For the question "What is the height of Jason Wei in meters?", the gold target is "1.73 m". The predicted answer "1.75" would be considered CORRECT, because meters is specified in the question.
    - For the question "What is the name of Barack Obama's wife?", the gold target is "Michelle Obama". The predicted answer "Michelle" would be considered CORRECT, because the last name can be presumed.
- Do not punish for typos in people's name if it's clearly the same name.
    - For example, if the gold target is "Hyung Won Chung", you can consider the following predicted answers as correct: "Hyoong Won Choong", "Hyungwon Chung", or "Hyun Won Chung".


Here is a new example. Simply reply with either CORRECT, INCORRECT, NOT ATTEMPTED. Don't apologize or correct yourself if there was a mistake; we are just trying to grade the answer.
```
Question: {question}
Gold target: {target}
Predicted answer: {predicted_answer}
```

Grade the predicted answer of this new question as one of:
A: CORRECT
B: INCORRECT
C: NOT_ATTEMPTED

Just return the letters "A", "B", or "C", with no text around it.
""".strip()


def _strip_think(text: str) -> str:
    if text and "</think>" in text:
        return text.split("</think>", 1)[1].strip()
    return text or ""


_USE_CODEX_FALLBACK = None  # auto-detect on first call


def _call_judge_codex(prompt: str, model: str = "gpt-5.5") -> str:
    import subprocess
    result = subprocess.run(
        ["codex", "exec", "--sandbox", "workspace-write", "-m", model, "-"],
        input=prompt, capture_output=True, text=True, timeout=180,
    )
    text = result.stdout.strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("tokens") or line.isdigit() or "," in line:
            continue
        match = re.search(r"\b(A|B|C)\b", line)
        if match:
            return match.group(0)
    return "C"


def _call_judge(
    question: str,
    target: str,
    predicted: str,
    model: str = "gpt-4.1-2025-04-14",
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    global _USE_CODEX_FALLBACK
    api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    prompt = GRADER_TEMPLATE.format(
        question=question, target=target, predicted_answer=predicted
    )

    if _USE_CODEX_FALLBACK:
        codex_prompt = (
            f"Grade this answer. Reply with exactly one letter: A (CORRECT), B (INCORRECT), or C (NOT_ATTEMPTED).\n\n"
            f"Question: {question}\nGold target: {target}\nPredicted answer: {predicted}\n\n"
            f"Rules: A if the prediction contains the gold answer. B if it contradicts. C if it doesn't attempt.\n"
            f"Just the letter:"
        )
        return _call_judge_codex(codex_prompt)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0,
        "seed": 42,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                d = json.load(resp)
            text = d["choices"][0]["message"].get("content", "") or ""
            match = re.search(r"(A|B|C)", text)
            return match.group(0) if match else "C"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  OpenAI API 401 — falling back to codex exec")
                _USE_CODEX_FALLBACK = True
                codex_prompt = (
                    f"Grade this answer. Reply with exactly one letter: A (CORRECT), B (INCORRECT), or C (NOT_ATTEMPTED).\n\n"
                    f"Question: {question}\nGold target: {target}\nPredicted answer: {predicted}\n\n"
                    f"Rules: A if the prediction contains the gold answer. B if it contradicts. C if it doesn't attempt.\n"
                    f"Just the letter:"
                )
                return _call_judge_codex(codex_prompt)
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(60, 2**attempt + 2))
                continue
            raise
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(min(60, 2**attempt + 2))
                continue
            raise
    return "C"


LETTER_TO_STRING = {"A": "CORRECT", "B": "INCORRECT", "C": "NOT_ATTEMPTED"}


def _get_gold_answer(example: dict, task: str) -> str:
    od = example.get("original_data", {})

    if task in ("encyclopedic_vqa",):
        refs = od.get("reference_list", [])
        if refs:
            return "Any of: " + " | ".join(refs)

    if task in ("nq", "nq_tables"):
        answers = od.get("gold_answers", od.get("answers", od.get("answer", [])))
        if isinstance(answers, list):
            return " OR ".join(str(a) for a in answers[:10])

    return str(od.get("answer", ""))


def _get_question(example: dict) -> str:
    return example.get("problem", "")


def _norm_url(u: str) -> str:
    u = u.strip().split("#")[0]
    for _ in range(4):
        decoded = urllib.parse.unquote(u)
        if decoded == u:
            break
        u = decoded
    return u


def _find_wikipedia_url(urls: list[str]) -> str | None:
    all_parts = []
    for raw in urls:
        for part in raw.split("\n"):
            part = part.strip().lstrip("- ").strip().split("#")[0]
            if "wikipedia.org/wiki/" in part:
                all_parts.append(part)
    for part in all_parts:
        if "en.wikipedia.org/wiki/" in part:
            return part
    return all_parts[0] if all_parts else (urls[0].split("#")[0].lstrip("- ").strip() if urls else None)


def compute_retrieval_accuracy(examples: list) -> dict | None:
    eval_examples = []
    for ex in examples:
        used_url = ex.get("used_url")
        if not used_url:
            continue
        run_metadata = ex.get("run_metadata") if isinstance(ex.get("run_metadata"), dict) else {}
        reader_top_k = run_metadata.get("reader_top_k")
        retrieval_top_k = run_metadata.get("retrieval_top_k")
        od = ex.get("original_data", {})
        meta = od.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = ast.literal_eval(meta)
            except (ValueError, SyntaxError):
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        gt_url = od.get("wikipedia_url") or meta.get("url")
        if not gt_url and isinstance(meta.get("urls"), list) and meta["urls"]:
            gt_url = _find_wikipedia_url(meta["urls"])
        if not gt_url:
            continue
        eval_examples.append({
            "used_url": used_url,
            "ground_truth_url": gt_url,
            "reader_top_k": reader_top_k,
            "retrieval_top_k": retrieval_top_k,
        })

    if not eval_examples:
        return None

    recall_at_1 = 0
    recall_any = 0
    for item in eval_examples:
        used = item["used_url"].strip()
        gt = _norm_url(item["ground_truth_url"])
        urls = [_norm_url(u) for u in used.split(", ") if u.strip()]
        rk = item.get("reader_top_k")
        retk = item.get("retrieval_top_k")
        if isinstance(rk, int) and isinstance(retk, int) and rk < retk:
            urls = urls[:rk]
        first_url = urls[0] if urls else ""
        if first_url == gt:
            recall_at_1 += 1
        if any(u == gt for u in urls):
            recall_any += 1

    n = len(eval_examples)
    return {
        "recall_at_1": recall_at_1 / n,
        "recall_any": recall_any / n,
        "n": n,
    }


def normalize_answer(s: str) -> str:
    def remove_articles(text):
        return re.sub(r"\b(a|an|the)\b", " ", text)
    def white_space_fix(text):
        return " ".join(text.split())
    def remove_punc(text):
        return "".join(ch for ch in text if ch not in set(string.punctuation))
    return white_space_fix(remove_articles(remove_punc(s.lower())))


def exact_match(predicted: str, gold_answers: list[str]) -> bool:
    np_ = normalize_answer(predicted)
    return any(np_ == normalize_answer(g) for g in gold_answers if g)


def _token_f1(prediction: str, ground_truth: str) -> float:
    """Token-level F1 between prediction and ground_truth (SQuAD normalization)."""
    pred_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(ground_truth).split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    common = Counter(pred_tokens) & Counter(gold_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    p = num_same / len(pred_tokens)
    r = num_same / len(gold_tokens)
    return 2 * p * r / (p + r)


def _grade_monaco_dir(pred_dir: str, save_path: str | None = None,
                      verbose: bool = False) -> None:
    """Grade a directory of MoNaCo per-example JSON prediction files.

    Computes token-level F1 (primary metric) from already-computed inline
    scores in each prediction file, or re-derives them from gold_answers.

    Usage:
        python grade.py monaco eval_output/monaco/<tag>
    """
    from pathlib import Path as _P
    folder = _P(pred_dir)
    if not folder.is_dir():
        print(f"Error: {pred_dir} is not a directory")
        sys.exit(1)

    files = sorted(folder.glob("llm_qa_judgement__*.json"))
    if not files:
        print(f"No llm_qa_judgement__*.json files found in {pred_dir}")
        sys.exit(1)

    _ANSWERS_PAT = re.compile(r"(?im)^\s*answers?:\s*(.*)$")
    def _extract_answer(output: str) -> str:
        if not output:
            return ""
        matches = _ANSWERS_PAT.findall(output)
        if matches:
            return matches[-1].strip().rstrip(".")
        for line in reversed(output.splitlines()):
            line = line.strip()
            if line:
                return line.rstrip(".")
        return ""

    f1_scores = []
    em_scores = []
    judge_f1_scores = []
    n_total = len(files)

    for fpath in files:
        try:
            rec = json.loads(fpath.read_text())
        except Exception as e:
            if verbose:
                print(f"  Skip {fpath.name}: {e}")
            continue

        # Token F1: use pre-computed or derive
        f1 = rec.get("token_f1")
        em = rec.get("token_em")
        gold = rec.get("gold_answers")

        if f1 is None and gold is not None:
            predicted = _extract_answer(rec.get("output", ""))
            if isinstance(gold, list):
                if all(isinstance(x, list) for x in gold):
                    flat = []
                    for sub in gold:
                        flat.extend(sub)
                    gold_str = ", ".join(str(a) for a in flat)
                else:
                    gold_str = ", ".join(str(a) for a in gold)
            else:
                gold_str = str(gold)
            f1 = _token_f1(predicted, gold_str)
            em = int(normalize_answer(predicted) == normalize_answer(gold_str))
            # Write back for future runs
            rec["token_f1"] = f1
            rec["token_em"] = em
            fpath.write_text(json.dumps(rec, ensure_ascii=False, indent=2))

        if f1 is not None:
            f1_scores.append(f1)
        if em is not None:
            em_scores.append(em)

        # LLM judge F1 (if already computed)
        jf1 = rec.get("judge_f1") or rec.get("judge_scores", {}).get("judge_score")
        if jf1 is not None:
            judge_f1_scores.append(jf1)

    print(f"\nMoNaCo Grading Results ({n_total} files in {pred_dir}):")
    if f1_scores:
        mean_f1 = sum(f1_scores) / len(f1_scores)
        mean_em = sum(em_scores) / len(em_scores) if em_scores else 0.0
        print(f"  Token F1 (primary):  {mean_f1:.4f}  ({len(f1_scores)} graded)")
        print(f"  Token EM:            {mean_em:.4f}")
    else:
        print("  No token F1 scores available (missing gold_answers in prediction files)")

    if judge_f1_scores:
        mean_jf1 = sum(judge_f1_scores) / len(judge_f1_scores)
        print(f"  LLM Judge F1:        {mean_jf1:.4f}  ({len(judge_f1_scores)} judged)")
    else:
        print("  LLM Judge F1:        not computed (run with --judge in run_monaco.py)")

    # Save results
    save_path = save_path or str(folder / "grade_results.json")
    results: dict = {
        "task": "monaco",
        "n_files": n_total,
        "n_graded_f1": len(f1_scores),
    }
    if f1_scores:
        results["mean_token_f1"] = round(sum(f1_scores) / len(f1_scores), 4)
        results["mean_token_em"] = round(sum(em_scores) / len(em_scores), 4) if em_scores else 0.0
    if judge_f1_scores:
        results["mean_judge_f1"] = round(sum(judge_f1_scores) / len(judge_f1_scores), 4)
        results["n_judged"] = len(judge_f1_scores)
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Grade eval JSONL results")
    parser.add_argument("task", help="Task name (simpleqa, nq, nq_tables, encyclopedic_vqa, mmsearch, monaco, etc.)")
    parser.add_argument("file_path", help="Path to JSONL results file (or directory for monaco)")
    parser.add_argument("--grader-model", default="gpt-4.1-2025-04-14")
    parser.add_argument("--llm-judge", action="store_true", help="Use LLM judge for NQ/NQ-Tables (default: EM)")
    parser.add_argument("--max-workers", type=int, default=10)
    parser.add_argument("--save-path", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # MoNaCo: directory-based grading
    if args.task == "monaco":
        _grade_monaco_dir(args.file_path, save_path=args.save_path, verbose=args.verbose)
        return

    if not os.path.exists(args.file_path):
        print(f"Error: {args.file_path} not found")
        sys.exit(1)

    with open(args.file_path) as f:
        examples = [json.loads(line) for line in f if line.strip()]

    successful = [e for e in examples if e.get("success", True) and e.get("final_response")]
    print(f"Loaded {len(examples)} examples ({len(successful)} successful)")

    retrieval_acc = compute_retrieval_accuracy(successful)
    if retrieval_acc:
        print(f"\nRetrieval Accuracy ({retrieval_acc['n']} examples):")
        print(f"  Recall@1: {retrieval_acc['recall_at_1']:.3f}")
        print(f"  Recall@any: {retrieval_acc['recall_any']:.3f}")

    # Token statistics
    usage_examples = [e for e in successful if e.get("usage")]
    if usage_examples:
        total_prompt = sum(e["usage"].get("prompt_tokens", 0) for e in usage_examples)
        total_comp = sum(e["usage"].get("completion_tokens", 0) for e in usage_examples)
        n = len(usage_examples)
        print(f"\nToken Usage ({n} examples):")
        print(f"  Avg prompt tokens: {total_prompt // n:,}")
        print(f"  Avg completion tokens: {total_comp // n:,}")

    use_llm_judge = args.task in (
        "simpleqa", "encyclopedic_vqa", "worldvqa", "simplevqa",
        "factualvqa", "mmsearch", "webqa", "multimodalqa",
    ) or args.llm_judge

    if not use_llm_judge and args.task in ("nq", "nq_tables", "triviaqa"):
        print("\nUsing exact-match grading (pass --llm-judge for GPT-4.1 judge)")
        correct = 0
        for ex in successful:
            response = _strip_think(ex.get("final_response", ""))
            od = ex.get("original_data", {})
            gold_answers = od.get("gold_answers", od.get("answers", []))
            if isinstance(gold_answers, str):
                gold_answers = [gold_answers]
            gold_answers = [str(a) for a in gold_answers if a]
            if not gold_answers:
                gold_answers = [str(od.get("answer", ""))]
            if exact_match(response, gold_answers):
                correct += 1
        acc = correct / len(successful) if successful else 0
        print(f"\nExact Match: {correct}/{len(successful)} ({acc:.3f})")
    elif use_llm_judge:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("Error: OPENAI_API_KEY not set")
            sys.exit(1)

        print(f"\nGrading with {args.grader_model} ({len(successful)} examples, {args.max_workers} workers)...")

        grades = {}

        def grade_one(idx_ex):
            idx, ex = idx_ex
            question = _get_question(ex)
            target = _get_gold_answer(ex, args.task)
            predicted = _strip_think(ex.get("final_response", ""))
            letter = _call_judge(question, target, predicted, model=args.grader_model)
            return idx, letter

        with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            futs = [pool.submit(grade_one, (i, ex)) for i, ex in enumerate(successful)]
            for i, fut in enumerate(as_completed(futs), 1):
                idx, letter = fut.result()
                grades[idx] = letter
                if i % 50 == 0 or i == len(futs):
                    print(f"  Graded {i}/{len(futs)}")

        n = len(grades)
        correct = sum(1 for g in grades.values() if g == "A")
        incorrect = sum(1 for g in grades.values() if g == "B")
        not_attempted = sum(1 for g in grades.values() if g == "C")

        print(f"\nGrading Results ({n} examples):")
        print(f"  CORRECT:       {correct}/{n} ({correct / n:.3f})")
        print(f"  INCORRECT:     {incorrect}/{n} ({incorrect / n:.3f})")
        print(f"  NOT_ATTEMPTED: {not_attempted}/{n} ({not_attempted / n:.3f})")
        acc = correct / n if n else 0
        print(f"  Accuracy: {acc:.3f}")
    else:
        print(f"\nNo grading implemented for task '{args.task}' without --llm-judge")

    # Save results
    save_path = args.save_path or str(Path(args.file_path).with_suffix("")) + "_eval_results.json"
    results = {
        "task": args.task,
        "num_examples": len(successful),
        "file": args.file_path,
    }
    if retrieval_acc:
        results["retrieval_accuracy"] = retrieval_acc
    if use_llm_judge and "grades" in dir():
        n = len(grades)
        results["accuracy"] = sum(1 for g in grades.values() if g == "A") / n if n else 0
        results["correct"] = sum(1 for g in grades.values() if g == "A")
        results["incorrect"] = sum(1 for g in grades.values() if g == "B")
        results["not_attempted"] = sum(1 for g in grades.values() if g == "C")
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {save_path}")


if __name__ == "__main__":
    main()
