#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["tree-sitter>=0.25", "tree-sitter-java>=0.23", "tree-sitter-javascript>=0.23",
#                 "tree-sitter-typescript>=0.23", "pyyaml>=6.0"]
# ///
"""jevkit - the part of a jevmcp check that does not depend on what is being checked.

Every tool family asks Jev fixed questions about many items (a spec sentence and its code, a failed
CI step, a unit of code and the project's rules). How the answers are gathered is the same for all of
them, and it is the part that was measured (spec drift 1.6.0, 115 graded claims):

- every item is asked once;
- an item the single-answer gate does NOT settle is asked `samples - 1` more times, and is decided
  only if every answer agrees and none is below a floor - so re-asking can only move an item OUT of
  `review`, never quietly into it;
- answers are cached as a LIST per exact request, so an unchanged item costs nothing the second time
  and the agreement gate never sees one answer three times.

The HTTP client, the cache file, the key lookup and the errors (Stop = fix your setup, VendorStop =
TypeSafe could not be used) are spec_drift's, so every tool behaves the same way when things fail.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import spec_drift as dd

PRICE_PER_TOKEN = 0.042 / 1_000_000     # USD per input token; output is free
FIXED_TOKENS = 259                      # what every request costs before its content (measured, 24/24)
CHARS_PER_TOKEN = 3.4                   # spec_drift.estimate_cost's measured average for code and JSON


@dataclass
class Item:
    """One request: what is shown (`state`) and what is asked (`questions`). `name` is how the
    item is reported when it cannot be checked."""
    name: str
    state: dict
    questions: dict
    meta: dict = field(default_factory=dict)


@dataclass
class Screened:
    """The outcome for one item. `answers` holds every independent answer used, first one first."""
    item: Item
    action: str | None = None
    confidence: float = 0.0
    why: str = ""
    answers: list[dict] = field(default_factory=list)
    error: str | None = None
    request_id: str | None = None
    upstream_ms: str | None = None

    @property
    def first(self) -> dict:
        return self.answers[0] if self.answers else {}


@dataclass
class Run:
    results: list[Screened]
    tokens: int = 0
    problems: list[str] = field(default_factory=list)     # exit 2: fix your setup
    vendor: list[str] = field(default_factory=list)       # exit 3: TypeSafe could not be used
    replayed: int = 0

    @property
    def cost_usd(self) -> float:
        return round(self.tokens * PRICE_PER_TOKEN, 6)

    @property
    def complete(self) -> bool:
        return not self.problems and not self.vendor and all(r.error is None for r in self.results)


def estimate_tokens(item: Item) -> int:
    """Input tokens one request will cost: the fixed charge plus the body. Used before anything is
    sent, so a user can be told the price."""
    body = json.dumps({"state": dd.canonical(item.state), "questions": item.questions}, ensure_ascii=False)
    return FIXED_TOKENS + int(len(body) / CHARS_PER_TOKEN)


def estimate_cost(items: list[Item], samples: int = 1) -> float:
    return round(sum(estimate_tokens(i) for i in items) * max(1, samples) * PRICE_PER_TOKEN, 6)


def screen(items: list[Item], key: str,
           classify: Callable[[dict], tuple[str, float, str]],
           classify_samples: Callable[[list[dict]], tuple[str, float, str] | None],
           settled: set[str], *, jobs: int = 4, samples: int = 3, use_cache: bool = True,
           cancelled: Callable[[], bool] | None = None,
           on_answer: Callable[[int, int], None] | None = None) -> Run:
    """Ask Jev about every item, `jobs` at a time, then re-ask what one answer did not settle.

    `classify(answer)` gives (action, confidence, why) for one answer; `classify_samples(answers)`
    gives a decision only when several answers agree (else None, and the single-answer action
    stands). Actions in `settled` are final after one answer and are never asked again.

    Once `cancelled()` returns true nothing further is sent. A rejected key stops the run (a
    problem); exhausted credits stop it too (a vendor failure). Neither is ever reported as a pass:
    items that were not checked carry `error`, and `Run.complete` is False."""
    run = Run(results=[Screened(item=i) for i in items])
    store = dd.load_cache() if use_cache else {}
    keys = [dd._cache_key(i.state, i.questions) for i in items]
    cache_lock, done_lock, done, replayed = threading.Lock(), threading.Lock(), [0], [0]

    def answer_n(k: int, n: int) -> dict:
        with cache_lock:
            have = store.get(keys[k], [])
            if n < len(have):
                replayed[0] += 1
                return {"answers": have[n], "usage": {"input_tokens": 0}, "_cached": True}
        got = dd.ask(items[k].state, items[k].questions, key, cancelled=cancelled)
        if use_cache and "answers" in got:
            with cache_lock:
                store.setdefault(keys[k], []).append(got["answers"])
        return got

    def first(k: int) -> dict:
        if cancelled and cancelled():
            return {"_error": "cancelled before it was sent"}
        try:
            return answer_n(k, 0)
        except dd.Stop as e:
            return {"_stop": e}
        finally:
            if on_answer:
                with done_lock:
                    done[0] += 1
                    n = done[0]
                on_answer(n, len(items))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        got = list(pool.map(first, range(len(items))))
    try:
        for r, ans in zip(run.results, got):
            if "_stop" in ans:
                raise ans["_stop"]
            if "_error" in ans:
                r.error = ans["_error"][:200]
                run.vendor.append(f"{r.item.name} was not checked - API error: {ans['_error'][:120]}")
                continue
            r.answers = [ans["answers"]]
            r.action, r.confidence, r.why = classify(ans["answers"])
            r.request_id, r.upstream_ms = ans.get("_request_id"), ans.get("_upstream_ms")
            run.tokens += ans.get("usage", {}).get("input_tokens", 0)
    except dd.VendorStop as e:
        run.vendor.append(f"the run stopped early: {e}")
    except dd.Stop as e:
        run.problems.append(f"the run stopped early: {e}")
    for r in run.results:
        if r.action is None and r.error is None:
            r.error = "not checked: the run stopped early"

    undecided = [k for k, r in enumerate(run.results) if r.action is not None and r.action not in settled]
    if samples > 1 and undecided and not run.problems and not run.vendor and not (cancelled and cancelled()):
        def again(k: int) -> list[dict]:
            return [answer_n(k, n) for n in range(1, samples)]
        try:
            with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
                more = list(pool.map(again, undecided))
        except dd.VendorStop as e:
            run.vendor.append(f"re-asking stopped early: {e}")
            more = []
        except dd.Stop as e:
            run.problems.append(f"re-asking stopped early: {e}")
            more = []
        for k, extra in zip(undecided, more):
            r = run.results[k]
            good = [m["answers"] for m in extra if "_error" not in m and "answers" in m]
            run.tokens += sum(m.get("usage", {}).get("input_tokens", 0) for m in extra if "_error" not in m)
            r.answers.extend(good)
            decided = classify_samples(r.answers)
            if decided:
                r.action, r.confidence, r.why = decided
    if use_cache:
        dd.save_cache(store)
    run.replayed = replayed[0]
    return run


def agreement(answers: list[dict], question: str, floor: float) -> tuple[str, float] | None:
    """The choice every answer gave to `question`, with the mean confidence, if all agree and none
    is below `floor`; else None. The building block of every classify_samples."""
    if len(answers) < 2:
        return None
    votes = [a.get(question, {}).get("choice") for a in answers]
    confs = [a.get(question, {}).get("confidence", 0.0) for a in answers]
    if None in votes or len(set(votes)) > 1 or min(confs) < floor:
        return None
    return votes[0], sum(confs) / len(confs)
