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
  only if every answer came back, agrees and none is below a floor - so re-asking can only move an
  item OUT of `review`, never quietly into it, and a failed re-ask is never a pass;
- answers are cached as a LIST per exact request, so an unchanged item costs nothing the second time
  and the agreement gate never sees one answer three times; items whose requests are exactly the same
  are asked once and share the answers.

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
    """The outcome for one item. `answers` holds the independent answers its action was decided on, first
    one first: every one that came back, or only the first when asking again failed. `note` says why an
    item that was asked again keeps its first answer's action."""
    item: Item
    action: str | None = None
    confidence: float = 0.0
    why: str = ""
    answers: list[dict] = field(default_factory=list)
    error: str | None = None
    request_id: str | None = None
    upstream_ms: str | None = None
    note: str | None = None

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
    problem); exhausted credits stop it too (a vendor failure). After either, no new request starts
    (those already in flight finish), and every answer that came back counts, whatever the item's place
    in the order. Neither is ever reported as a pass: items that were not checked carry `error`, and
    `Run.complete` is False. An item whose asking
    again failed keeps its first answer's action with a `note`, and the failure is in `vendor`. An
    answer that cannot be read (a part missing or of the wrong type, a choice that was not offered:
    dd.unreadable_answer) is an API error for its item in either pass, never a crash of the run or a
    pass, and it is never kept in the cache or replayed from it, so it is asked again."""
    run = Run(results=[Screened(item=i) for i in items])
    store = dd.load_cache() if use_cache else {}
    keys = [dd._cache_key(i.state, i.questions) for i in items]
    alike = dd.asked_alike(keys)              # an item asked exactly as an earlier one shares its answers
    sharing = {k: 0 for k in alike}
    for k in alike:
        sharing[k] += 1
    cache_lock, done_lock, done, replayed = threading.Lock(), threading.Lock(), [0], [0]
    unreadable: set[str] = set()              # cache keys of answers that could not be read: never kept

    def answer_n(k: int, n: int) -> dict:
        """The n-th answer for item k: replayed from the cache, unless it cannot be read (an earlier
        version kept it) - then it is dropped with the ones after it and asked for again (dd.ask checks
        every reply the same way, so classify never sees an answer it cannot read)."""
        with cache_lock:
            have = store.get(keys[k], [])
            if n < len(have):
                if dd.unreadable_answer(have[n], items[k].questions) is None:
                    replayed[0] += 1
                    return {"answers": have[n], "usage": {"input_tokens": 0}, "_cached": True}
                store[keys[k]] = have[:n]
        got = dd.ask(items[k].state, items[k].questions, key, cancelled=cancelled)
        if use_cache and "answers" in got:
            with cache_lock:
                store.setdefault(keys[k], []).append(got["answers"])
        return got

    stopped = threading.Event()               # a rejected key or credits used up: send nothing more

    def first(k: int) -> dict:
        if cancelled and cancelled():
            return {"_error": "cancelled before it was sent"}
        if stopped.is_set():
            return {"_error": "not sent: the run stopped early", "_halted": True}
        try:
            return answer_n(k, 0)
        except dd.Stop as e:                   # reported below, after every answer that came back
            stopped.set()
            return {"_stop": e}
        finally:
            if on_answer:
                with done_lock:
                    done[0] += sharing[k]      # the items that share this answer
                    n = done[0]
                on_answer(n, len(items))

    def ask_each(ks: list[int]) -> list[dict]:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            return list(pool.map(first, ks))
    got = dd.share_answers(alike, list(range(len(items))), ask_each)
    # A stop sends nothing more, but every answer that came back before it counts, whatever its item's
    # place in the order: it is classified and paid for.
    stop: dd.Stop | None = None
    for k, (r, ans) in enumerate(zip(run.results, got)):
        if "_stop" in ans:
            stop = stop or ans["_stop"]
            continue
        if ans.get("_halted"):                 # not sent after a Stop, which is reported below
            continue
        error = ans.get("_error") or (None if isinstance(ans.get("answers"), dict) else "the reply held no answers")
        if error is None:
            try:
                r.action, r.confidence, r.why = classify(ans["answers"])
            except (KeyError, TypeError, AttributeError, ValueError) as e:     # an answer missing a part
                r.action, error = None, f"the reply could not be read ({type(e).__name__}: {e})"
                unreadable.add(keys[k])
        run.tokens += dd._input_tokens(ans)
        if error is not None:
            r.error = error[:200]
            run.vendor.append(f"{r.item.name} was not checked - API error: {error[:120]}")
            continue
        r.answers = [ans["answers"]]
        r.request_id, r.upstream_ms = ans.get("_request_id"), ans.get("_upstream_ms")
    # An item is decided by agreement only when every one of its `samples` answers came back. When
    # asking again fails, it keeps its first answer's action and why, `note` says so, and the run is
    # not complete (dd.ask_again: nothing more is sent after a cancellation or a Stop).
    undecided = [k for k, r in enumerate(run.results) if r.action is not None and r.action not in settled]
    if stop is not None:            # nothing is asked again: each item it cut says so, and the line counts them
        cut = undecided if samples > 1 else []
        for k in cut:
            run.results[k].note = dd.reask_note("not asked: the run stopped early")
        (run.vendor if isinstance(stop, dd.VendorStop) else run.problems).append(
            "the run stopped early" + (f" - {len(cut)} item(s) keep their first answer's label" if cut else "")
            + f": {stop}")
    for r in run.results:
        if r.action is None and r.error is None:
            r.error = "not checked: the run stopped early"
    if samples > 1 and undecided and not run.problems and not run.vendor and not (cancelled and cancelled()):
        halted: list[dd.Stop] = []

        def again(ks: list[int]) -> list[list[dict]]:
            more, stops = dd.ask_again(answer_n, ks, samples, jobs, cancelled)
            halted.extend(stops)
            return more
        more = dd.share_answers(alike, undecided, again)
        vendor, problems = dd.reask_failures(more, halted)
        run.vendor += vendor
        run.problems += problems
        for k, extra in zip(undecided, more):
            r = run.results[k]
            good = [m["answers"] for m in extra if "_error" not in m]
            run.tokens += sum(dd._input_tokens(m) for m in extra)
            if failed := next((m for m in extra if "_error" in m), None):
                r.note = dd.reask_note(failed["_error"])
                if not failed.get("_halted"):
                    run.vendor.append(f"{r.item.name} could not be asked again - API error: "
                                      f"{failed['_error'][:120]} (it keeps its first answer's label)")
                continue
            try:
                decided = classify_samples([*r.answers, *good])
            except (KeyError, TypeError, AttributeError, ValueError) as e:   # a wrong-typed part: confidence null
                error = f"the reply could not be read ({type(e).__name__}: {e})"
                r.note = dd.reask_note(error)
                run.vendor.append(f"{r.item.name} could not be asked again - API error: {error[:120]} "
                                  f"(it keeps its first answer's label)")
                unreadable.add(keys[k])
                continue
            r.answers.extend(good)
            if decided:
                r.action, r.confidence, r.why = decided
    if use_cache:
        dd.save_cache(store, drop=unreadable)
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
