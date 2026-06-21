#!/usr/bin/env python3
"""Offline decision-log review loop. Judging is done by Claude (this assistant),
not an LLM-API call — see ADR 0004 (judge step) and 0005.

Workflow:
  1. dump-judge   -> writes unjudged rows to YAML; Claude fills `judge_verdict`.
  2. apply-judge  -> writes those verdicts back into decision_log.
  3. dump-confirm -> writes judge<>phase1 disagreements; the user confirms
                     `human_label` (ground truth).
  4. apply-human  -> writes human_label back.
  5. export-eval  -> appends human-labeled rows to tests/eval_set.yaml (dedup).

Run from repo root:  python tools/review_decisions.py <cmd> [args]
"""

import argparse
import os
import sys

import yaml

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.dbService import DBService


def phase1_to_pred(phase1_verdict: str) -> str:
    """Phase-1 verdict expressed as a relevance prediction."""
    return "relevant" if phase1_verdict == "reported" else "not"


def is_disagreement(row: dict) -> bool:
    """A judged row whose judge_verdict contradicts Phase-1 — a candidate mistake."""
    jv = row.get("judge_verdict")
    return jv is not None and jv != phase1_to_pred(row["phase1_verdict"])


def rows_to_review(rows: list, label_field: str) -> list:
    """Compact, fill-in-the-blank YAML view of rows for a human/Claude pass."""
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "chat_title": r.get("chat_title") or "",
            "phase1_verdict": r["phase1_verdict"],
            "judge_verdict": r.get("judge_verdict"),
            label_field: None,
            "text": r.get("text", ""),
        })
    return out


def eval_items_from_labeled(rows: list) -> list:
    """Turn human-labeled rows into eval_set.yaml items, deduped by message identity."""
    seen = {}
    for r in rows:
        if not r.get("human_label"):
            continue
        key = (r["source"], r["chat_id"], r["message_id"])
        seen[key] = {  # later row wins on relabel
            "message_id": r["message_id"],
            "chat_title": r.get("chat_title") or "",
            "system_reported": r["phase1_verdict"] == "reported",
            "predicted": phase1_to_pred(r["phase1_verdict"]),
            "label": r["human_label"],
            "text": r.get("text", ""),
        }
    return list(seen.values())


def merge_eval_items(existing: list, new: list) -> list:
    """Append new items, skipping ones whose (chat_title, text) already exist."""
    have = {(it.get("chat_title", ""), it.get("text", "")) for it in existing}
    merged = list(existing)
    for it in new:
        if (it["chat_title"], it["text"]) not in have:
            merged.append(it)
            have.add((it["chat_title"], it["text"]))
    return merged


# -- CLI commands --

def cmd_dump_judge(db, args):
    rows = db.get_unjudged_rows()
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(rows_to_review(rows, "judge_verdict"), f, allow_unicode=True, sort_keys=False)
    print(f"Wrote {len(rows)} unjudged rows -> {args.out}. Fill `judge_verdict` (relevant|not).")


def cmd_apply_judge(db, args):
    with open(args.in_file, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    n = 0
    for it in items:
        if it.get("judge_verdict") in ("relevant", "not"):
            db.set_judge_verdict(it["id"], it["judge_verdict"])
            n += 1
    print(f"Applied {n} judge verdicts.")


def cmd_dump_confirm(db, args):
    diffs = [r for r in db.get_decision_rows() if is_disagreement(r)]
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(rows_to_review(diffs, "human_label"), f, allow_unicode=True, sort_keys=False)
    print(f"Wrote {len(diffs)} judge/Phase-1 disagreements -> {args.out}. Confirm `human_label`.")


def cmd_apply_human(db, args):
    with open(args.in_file, encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    n = 0
    for it in items:
        if it.get("human_label") in ("relevant", "not"):
            db.set_human_label(it["id"], it["human_label"])
            n += 1
    print(f"Applied {n} human labels.")


def cmd_export_eval(db, args):
    new = eval_items_from_labeled(db.get_decision_rows())
    existing = []
    if os.path.exists(args.eval):
        with open(args.eval, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or []
    merged = merge_eval_items(existing, new)
    added = len(merged) - len(existing)
    with open(args.eval, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False)
    print(f"Exported {added} new labeled items -> {args.eval} ({len(merged)} total).")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="messages.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("dump-judge"); s.add_argument("--out", default="judge.yaml"); s.set_defaults(fn=cmd_dump_judge)
    s = sub.add_parser("apply-judge"); s.add_argument("in_file"); s.set_defaults(fn=cmd_apply_judge)
    s = sub.add_parser("dump-confirm"); s.add_argument("--out", default="confirm.yaml"); s.set_defaults(fn=cmd_dump_confirm)
    s = sub.add_parser("apply-human"); s.add_argument("in_file"); s.set_defaults(fn=cmd_apply_human)
    s = sub.add_parser("export-eval"); s.add_argument("--eval", default="tests/eval_set.yaml"); s.set_defaults(fn=cmd_export_eval)

    args = p.parse_args()
    db = DBService(db_path=args.db)
    args.fn(db, args)


if __name__ == "__main__":
    main()
