"""Live QA evaluation against the real LLM and the indexed Natya-Sarjan book.

Part 1, QA (full pipeline). Every case was checked by hand against the PDF:
- answerable: the expected pages contain the answer, and the required terms
  are the book's own words for it;
- absent: the requested fact appears nowhere in the book's 282 pages, though
  the topic is mentioned (so retrieval returns plausible-looking passages).

Part 2, claim verification (grounding layer only, real LLM verifier). Hand-
written answers are checked against real passages from the index, each citing
its exact page: unsupported ones (invented names, added details, swapped or
generalised meaning) must be rejected *for their content*; faithful
paraphrases must be accepted; wrong or over-broad citations of faithful text
must be rejected *for the page*.

Spends real quota. Stops the whole run on any API error the client's retry
policy cannot absorb, so a broken key or an outage cannot burn the free tier.

    cd backend
    SS_LLM_AUTO_FALLBACK=false python -m evaluation.live_qa_eval [--part verify|qa|all]
                                                                 [--verify-from CASE_ID]
                                                                 [--qa-from CASE_ID]

Required settings (backend/.env, never printed): GROQ_API_KEY,
SS_LLM_PROVIDER=groq, SS_GROQ_MODEL=openai/gpt-oss-120b. SS_LLM_AUTO_FALLBACK
=false on the command line keeps every verdict attributable to that one model.
The index is read from config.DATA_DIR (backend/data, a copy of the indexed
book; doc_id below). Results go to backend/data/eval/live_qa_eval_<part>.json.

The whole run costs roughly 200K tokens, a full free Groq day (TPD limit
200,000), so on the free tier run the parts on separate days:
    ... --part verify      (~15K tokens: 18 claim-verification cases, 4 with no API call)
    ... --part qa          (~185K tokens: 14 QA cases)
--verify-from resumes the verification set after a quota stop.

--qa-from resumes the QA part (with --part qa). It reuses the previous
live_qa_eval_qa.json: completed cases (PASS or FAIL) are kept and not rerun,
only unfinished cases from CASE_ID on are executed, and the previous file is
first copied to a new backup. Results from different code or model settings
are never merged (a fingerprint is stored with them). Progress is saved after
every case; on a daily-quota error the run stops and prints the exact resume
command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import config
from indexing import vector_store
from indexing.hybrid_search import RetrievedChunk
from qa import graph, grounding, llm_client

DOC_ID = "1d9b23967ba2"  # natya-sarjan.pdf
BOOK = "નાટ્યસર્જન"
PAUSE_SECONDS = 65  # lets a per-minute token quota refill between cases

T1 = ("નાટકમાં વાચિક અભિનય અને આંગિક અભિનય એટલે શું?", {197, 201},
      [["વાચિક"], ["આંગિક"], ["સંવાદ"], ["ક્રિયા", "કાર્ય"]])
T2 = "જાપાનની કાબૂકી નાટ્યશૈલીની શરૂઆત કોણે અને કયા વર્ષમાં કરી હતી?"

# (id, kind, question, expected pages, required term groups — each any-of)
CASES = [
    ("T1-run1", "answerable", *T1),
    ("T2-run1", "absent", T2, None, None),
    ("T1-run2", "answerable", *T1),
    ("T2-run2", "absent", T2, None, None),
    ("T1-run3", "answerable", *T1),
    ("T2-run3", "absent", T2, None, None),
    ("A2-fourth-wall", "answerable", "નાટકમાં ચોથી દીવાલ એટલે શું?", {152, 183},
     [["ચોથી દીવાલ"], ["પડદ", "કલ્પિત", "કાલ્પનિક"]]),
    ("U2-shakespeare-birth", "absent", "શેક્સપિયરનો જન્મ કયા વર્ષમાં અને ક્યાં થયો હતો?", None, None),
    ("A3-commanding-image", "answerable", "નાટકની પ્રમુખ છબી એટલે શું?",
     {27, 28, 29, 53, 56, 62, 63, 207, 210, 275}, [["છબી"]]),
    ("U3-asait-veshas", "absent", "ભવાઈના આદ્યપિતા અસાઈત ઠાકરે કુલ કેટલા વેશ લખ્યા હતા?", None, None),
    ("A4-andha-yug-style", "answerable", "‘અંધાયુગ’ નાટક કઈ નાટ્યશૈલીમાં રજૂ કરવામાં આવ્યું હતું?",
     {14, 15}, [["નોહ"], ["કાબૂકી"]]),
    ("A5-cyclorama", "answerable", "સાઈકલૉરામા એટલે શું?", {69, 70}, [["સફેદ"]]),
    ("A6-strasberg", "answerable", "સટ્રેસબર્ગનો નટ પાસે શો આગ્રહ રહેતો?", {190, 191},
     [["પડદો"], ["પાત્ર"]]),
    ("T3-vague", "vague", "નાટક જોયા પછી મનમાં જે રહી જાય તેને શું કહે?", {28, 56},
     [["છબી", "છાપ", "commanding image"]]),
]


# (id, expect, chunk ids of the cited passages, answer)
#
# expect:
#   "reject-content"  must be rejected for what it says (an added word, an
#                     unsupported claim), not merely for its citation. Each
#                     cites its exact page, so the meaning check is reached.
#   "reject-page"     faithful text with a wrong or over-broad citation; must
#                     be rejected for the page, and only for the page.
#   "accept"          faithful paraphrase with its exact page(s); must pass.
# Exact pages were checked against the PDF: chunk 370's sentence is on p.201,
# chunk 16's on p.15, chunk 350's on p.191, chunk 279's on p.152; chunk 122's
# cyclorama definition runs from p.69 onto p.70.
VERIFY_CASES = [
    ("U1-elaboration", "reject-content", [370],
     "આંગિક અભિનય – નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ, શરીરિક અભિવ્યક્તિ (પાનું 201)"),
    ("U2-invented-founder", "reject-content", [16],
     "કાબૂકીની શરૂઆત ઓકુની નામની નર્તકીએ કરી હતી (પાનું 15)"),
    ("U3-invented-director", "reject-content", [16],
     "‘અંધાયુગ’ની રજૂઆત ઇબ્રાહિમ અલ્કાઝીએ જાપાનીઝ ‘નોહ’ અને ‘કાબૂકી’ શૈલીમાં કરી (પાનું 15)"),
    ("U4-swapped-meaning", "reject-content", [370],
     "નાટકના સંવાદો એટલે નટોનો આંગિક અભિનય અને નટોની ક્રિયા એટલે નટોનો વાચિક અભિનય (પાનું 201)"),
    ("U5-disciple-not-influenced", "reject-content", [350],
     "લી સટ્રેસબર્ગ સ્ટાનિસલાવ્સ્કીના શિષ્ય હતા (પાનું 191)"),
    ("U6-invented-purpose", "reject-content", [122],
     "સાઈકલૉરામા એટલે સ્ટેજની પાછળ ગોઠવવામાં આવતો વિશાળ સફેદ પડદો, જે પ્રકાશને પરાવર્તિત કરવા માટે હોય છે (પાનું 70)"),
    ("U7-end-not-start", "reject-content", [279],
     "નાટક પૂરું થતાં કલ્પિત ચોથી દીવાલ ખસી જાય છે (પાનું 152)"),
    ("U8-overgeneralised", "reject-content", [16],
     "‘અંધાયુગ’ હંમેશાં ‘નોહ’ શૈલીમાં જ ભજવાય છે (પાનું 15)"),
    ("F1-reordered-definition", "accept", [370],
     "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનું 201)"),
    ("F2-andha-yug-reworded", "accept", [16],
     "‘અંધાયુગ’ જાપાનની ‘નોહ’ અને ‘કાબૂકી’ શૈલીમાં રજૂ થયું હતું (પાનું 15)"),
    ("F3-strasberg-reworded", "accept", [350],
     "સટ્રેસબર્ગ માટે નાટક શરૂ થતાં જ નટ પાત્રના જીવનમાં પ્રવેશે એટલું પૂરતું નહોતું (પાનું 191)"),
    ("F4-cyclorama-reworded", "accept", [122],
     "સાઈકલૉરામા એ સ્ટેજની પાછળ રાખવામાં આવતો મોટો સફેદ પડદો છે (પાનાં 69-70)"),
    ("F5-fourth-wall-reworded", "accept", [279],
     "નાટક શરૂ થાય ત્યારે મુખ્ય પડદો, એટલે કે કલ્પિત ચોથી દીવાલ, ખસી જાય છે (પાનું 152)"),
    ("F6-influenced-by", "accept", [350],
     "લી સટ્રેસબર્ગ સ્ટાનિસલાવ્સ્કીથી પ્રભાવિત હતા (પાનું 191)"),
    # Page precision. Deterministic: rejected before any LLM call.
    ("W1-whole-chunk-range", "reject-page", [370],
     "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનાં 201-202)"),
    ("W2-wrong-single-page", "reject-page", [350],
     "લી સટ્રેસબર્ગ સ્ટાનિસલાવ્સ્કીથી પ્રભાવિત હતા (પાનું 190)"),
    ("W3-other-page-of-range", "reject-page", [16],
     "‘અંધાયુગ’ જાપાનની ‘નોહ’ અને ‘કાબૂકી’ શૈલીમાં રજૂ થયું હતું (પાનું 14)"),
    ("W4-half-of-a-page-break", "reject-page", [122],
     "“‘સાઈકલૉરામા’ એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ) ગોઠવવામાં આવતો વિશાળ સફેદ પડદો” (પાનું 69)"),
]
# Problems about the citation rather than the content (see qa.grounding).
_PAGE_PROBLEM = ("cites page", "cannot establish which", "cannot read")


def problem_kinds(problems) -> set:
    return {"page" if any(m in p for m in _PAGE_PROBLEM) else "content" for p in problems}


def judge_verification(expect: str, problems) -> str:
    kinds = problem_kinds(problems)
    if expect == "accept":
        return "PASS" if not kinds else "FAIL"
    if expect == "reject-content":
        return "PASS" if "content" in kinds else "FAIL"  # a page-only rejection proves nothing
    if expect == "reject-page":
        return "PASS" if kinds == {"page"} else "FAIL"
    raise ValueError(expect)


VERIFY_PAUSE_SECONDS = 20


def redact(text: str) -> str:
    return re.sub(r"org_[A-Za-z0-9]+", "org_[redacted]", text)


def load_chunks(ids):
    rows = vector_store.get_by_ids(DOC_ID, [f"{DOC_ID}:{i}" for i in ids])
    out = []
    for i in ids:
        row = rows[f"{DOC_ID}:{i}"]
        m = row["metadata"]
        out.append(RetrievedChunk(row["chunk_id"], row["text"], int(m["page_start"]),
                                  int(m["page_end"]), int(m.get("chapter_index", -1)),
                                  m.get("chapter_title", "") or "", 1.0))
    return out


def run_verification_set(llm, guard, start_from=None):
    cases = VERIFY_CASES
    if start_from:
        cases = cases[[c[0] for c in cases].index(start_from):]
    rows = []
    for i, (case_id, expect, ids, answer) in enumerate(cases):
        if i and rows and rows[-1]["decided_by"] == "llm-verifier":
            time.sleep(VERIFY_PAUSE_SECONDS)  # pace only after a real API call
        chunks = load_chunks(ids)
        det = grounding.check_answer(answer, chunks)
        layer, problems, error = "deterministic", list(det.problems), ""
        if not problems:
            layer = "llm-verifier"
            try:
                problems, _ = grounding.verify_claims(det.answer, chunks, llm)
            except llm_client.LLMError as exc:
                error = f"{exc} | provider said: {guard.last_429 or 'n/a'}"[:700]
        if error or guard.blocked:
            verdict = "BLOCKED"
        else:
            verdict = judge_verification(expect, problems)
        rows.append({"id": case_id, "expect": expect, "verdict": verdict, "decided_by": layer,
                     "answer": answer, "problems": problems, "error": error or guard.blocked})
        print(f"[{case_id}] {verdict} expect={expect} decided_by={layer} "
              f"problems={[p[:90] for p in problems]}", flush=True)
        if verdict == "BLOCKED":
            print("STOPPING:", error or guard.blocked, flush=True)
            break
    return rows


_DAILY_QUOTA = re.compile(r"per day|\bTPD\b|\bRPD\b|PerDay", re.IGNORECASE)


def is_daily_quota(message: str) -> bool:
    """Groq: "tokens per day (TPD)"; Gemini: quota ids ending "...PerDay..."."""
    return bool(_DAILY_QUOTA.search(message or ""))


class Guard:
    """Counts provider calls; halts everything on a non-rate-limit API error.

    429s are left to the client's own retry policy (it waits as long as the
    provider asks, and gives up on daily quotas or waits over a minute); if
    the client gives up, the case is BLOCKED and the run stops.
    """

    def __init__(self, llm_cls):
        self.calls, self.rate_limited, self.blocked, self.last_429 = 0, 0, None, ""
        real = llm_cls._complete

        def guarded(llm_self, prompt, system, temperature):
            if self.blocked:
                raise RuntimeError(f"halted after {self.blocked}; no request sent")
            self.calls += 1
            try:
                return real(llm_self, prompt, system, temperature)
            except Exception as exc:
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status == 429:
                    self.rate_limited += 1
                    self.last_429 = redact(str(exc))[:600]
                    if is_daily_quota(str(exc)):
                        # Waiting cannot help today; refuse every further request.
                        self.blocked = f"daily quota exhausted: {self.last_429}"
                else:
                    self.blocked = f"{type(exc).__name__} status={status} {redact(str(exc))[:600]}"
                raise

        llm_cls._complete = guarded


def judge(kind, result, expected, terms):
    if kind == "absent":
        checks = {"declined": not result["found"], "no_citations": not result["citations"]}
    else:
        cited = set(grounding._cited_pages(result["answer"]))
        checks = {
            "found": result["found"],
            "cites_expected_page": bool(cited & expected),
            "required_terms": all(any(t in result["answer"] for t in group) for group in terms),
        }
        if kind == "vague":
            checks["rewritten"] = result["rewrites_used"] >= 1
    return ("PASS" if all(checks.values()) else "FAIL"), checks


# ------------------------------------------------------------ QA resume ----
COMPLETED = ("PASS", "FAIL")
# Source files whose change would change QA behaviour or its judging.
_FINGERPRINT_FILES = (
    "config.py", "qa/graph.py", "qa/grounding.py", "qa/pages.py", "qa/prompt_builder.py",
    "qa/llm_client.py", "indexing/hybrid_search.py", "indexing/bm25_index.py",
    "indexing/vector_store.py", "indexing/embedder.py", "evaluation/live_qa_eval.py",
)
RESUME_COMMAND = ("SS_LLM_AUTO_FALLBACK=false PYTHONPATH=. python -u -m evaluation.live_qa_eval "
                  "--part qa --qa-from {case_id}")


def qa_case_ids() -> List[str]:
    return [case[0] for case in CASES]


def validate_qa_from(case_id: str) -> None:
    if case_id not in qa_case_ids():
        raise SystemExit(f"--qa-from: unknown case id {case_id!r}. "
                         f"Valid ids: {', '.join(qa_case_ids())}")


def code_fingerprint() -> str:
    """Identifies the code and model settings a set of QA results came from."""
    base = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for rel in _FINGERPRINT_FILES:
        digest.update(rel.encode())
        digest.update((base / rel).read_bytes())
    for setting in (config.LLM_PROVIDER, config.GROQ_MODEL, config.GEMINI_MODEL,
                    config.LLM_MAX_RETRIES, config.LLM_AUTO_FALLBACK, DOC_ID):
        digest.update(repr(setting).encode())
    return digest.hexdigest()[:16]


def backup_results(path: Path) -> Optional[Path]:
    """Copy existing results to a new file; never overwrites anything."""
    if not path.exists():
        return None
    data = path.read_bytes()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in range(1000):
        dest = path.with_name(f"{path.stem}.backup-{stamp}{'' if n == 0 else f'-{n}'}{path.suffix}")
        try:
            with open(dest, "xb") as fh:  # exclusive create: fails rather than overwrite
                fh.write(data)
            return dest
        except FileExistsError:
            continue
    raise SystemExit(f"could not create a backup of {path}")


def load_previous(path: Path, fingerprint: str) -> Dict[str, dict]:
    if not path.exists():
        raise SystemExit(f"--qa-from: no previous QA results at {path}; run --part qa without --qa-from first.")
    data = json.loads(path.read_text())
    previous_fp = (data.get("meta") or {}).get("code_fingerprint")
    if previous_fp != fingerprint:
        raise SystemExit(f"--qa-from: {path.name} was produced by different code or settings "
                         f"(fingerprint {previous_fp} vs {fingerprint}). Results would not be comparable; "
                         f"run --part qa without --qa-from to start over (the old file is backed up first).")
    return {row["id"]: row for row in data.get("qa", [])}


def save_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    os.replace(tmp, path)  # never leaves a half-written results file


def qa_summary(rows: List[dict]) -> Dict[str, int]:
    return {v: sum(r["verdict"] == v for r in rows) for v in ("PASS", "FAIL", "BLOCKED", "NOT RUN")}


def first_unfinished(rows: List[dict]) -> Optional[str]:
    return next((r["id"] for r in rows if r["verdict"] not in COMPLETED), None)


def _not_run(case) -> dict:
    case_id, kind, question, _, _ = case
    return {"id": case_id, "kind": kind, "question": question, "verdict": "NOT RUN"}


def run_qa_case(case, answer_fn: Callable[[str], dict], guard) -> dict:
    case_id, kind, question, expected, terms = case
    calls0, limited0 = guard.calls, guard.rate_limited
    result = answer_fn(question)
    if guard.blocked or result["llm_error"]:
        verdict, checks = "BLOCKED", {}
    else:
        verdict, checks = judge(kind, result, expected, terms)
    trace = result["trace"]
    return {
        "id": case_id, "kind": kind, "question": question, "verdict": verdict,
        "checks": checks, "answer": result["answer"], "found": result["found"],
        "rewrites": result["rewrites_used"], "queries": result["queries_tried"],
        "retrieved_by_round": [t.get("query") for t in trace if t["node"] == "retrieve"],
        "sources": [(c["page_start"], c["page_end"], c["chapter_title"]) for c in result["citations"]],
        "grade": [t for t in trace if t["node"] == "grade"],
        "generate": [t for t in trace if t["node"] == "generate"],
        "api_calls": guard.calls - calls0, "rate_limited": guard.rate_limited - limited0,
        "error": guard.blocked or result["llm_error"],
    }


def run_qa_part(answer_fn: Callable[[str], dict], guard, out_path: Path, fingerprint: str,
                start_from: Optional[str] = None, previous: Optional[Dict[str, dict]] = None,
                extra: Optional[dict] = None, sleep: Callable[[float], None] = time.sleep,
                pause: float = PAUSE_SECONDS) -> List[dict]:
    """Run the QA cases, resuming from `start_from` over `previous` results.

    Completed cases (PASS/FAIL) in `previous` are kept and never rerun.
    Unfinished ones before `start_from` stay as they were (BLOCKED or NOT
    RUN). Progress is saved after every case.
    """
    previous = previous or {}
    ids = qa_case_ids()
    start = ids.index(start_from) if start_from else 0
    rows: Dict[str, dict] = {}
    for i, case in enumerate(CASES):
        prior = previous.get(case[0])
        if prior and (prior["verdict"] in COMPLETED or i < start):
            rows[case[0]] = dict(prior, carried_over=True)
        else:
            rows[case[0]] = _not_run(case)

    def snapshot() -> List[dict]:
        return [rows[i] for i in ids]

    def save() -> None:
        save_atomic(out_path, {
            **(extra or {}),
            "meta": {"code_fingerprint": fingerprint, "doc_id": DOC_ID, "start_from": start_from,
                     "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "summary": qa_summary(snapshot())},
            "qa": snapshot(),
        })

    save()
    executed = 0
    for case in CASES[start:]:
        case_id = case[0]
        if rows[case_id]["verdict"] in COMPLETED:
            print(f"[{case_id}] kept from previous run: {rows[case_id]['verdict']} (not rerun)", flush=True)
            continue
        if executed:
            sleep(pause)
        executed += 1
        row = run_qa_case(case, answer_fn, guard)
        rows[case_id] = row
        save()
        print(f"\n[{case_id}] {row['verdict']} {row['checks']} calls={row['api_calls']} "
              f"429s={row['rate_limited']} rewrites={row['rewrites']}", flush=True)
        print("  answer:", row["answer"].replace("\n", " | ")[:400], flush=True)
        if row["verdict"] == "BLOCKED":
            nxt = first_unfinished(snapshot())
            print(f"STOPPING: {row['error']}", flush=True)
            print(f"Progress saved to {out_path}. First unfinished case: {nxt}", flush=True)
            print("Resume with (from backend/):\n  " + RESUME_COMMAND.format(case_id=nxt), flush=True)
            break
    return snapshot()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["all", "verify", "qa"], default="all")
    ap.add_argument("--verify-from", default=None, help="resume the verification set at this case id")
    ap.add_argument("--qa-from", default=None,
                    help="resume the QA part at this case id (requires --part qa)")
    args = ap.parse_args()

    # Everything that can refuse the run happens before any API client exists.
    eval_dir = Path(config.DATA_DIR) / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    qa_path = eval_dir / f"live_qa_eval_{args.part}.json"
    fingerprint = code_fingerprint()
    previous: Dict[str, dict] = {}
    if args.qa_from:
        if args.part != "qa":
            ap.error("--qa-from requires --part qa")
        validate_qa_from(args.qa_from)
        previous = load_previous(qa_path, fingerprint)
    if args.part in ("qa", "all"):
        backup = backup_results(qa_path)
        if backup:
            print(f"Previous results backed up to {backup}", flush=True)

    llm = llm_client.get_llm()
    guard = Guard(type(llm))
    print(f"provider={config.LLM_PROVIDER} client={type(llm).__name__} model={llm.model} "
          f"fallback={config.LLM_AUTO_FALLBACK} retries={config.LLM_MAX_RETRIES} "
          f"fingerprint={fingerprint}", flush=True)

    verify_rows = []
    if args.part in ("all", "verify"):
        print("\n=== Part 2: claim verification set (one call per case)", flush=True)
        verify_rows = run_verification_set(llm, guard, args.verify_from)
        verify_path = eval_dir / f"live_qa_eval_{args.part}.json"
        verify_path.write_text(json.dumps({"verification": verify_rows}, ensure_ascii=False, indent=1))
        if args.part == "verify" or any(r["verdict"] == "BLOCKED" for r in verify_rows):
            print(f"\nDONE verification={ {v: sum(r['verdict'] == v for r in verify_rows) for v in ('PASS', 'FAIL', 'BLOCKED')} } -> {verify_path}", flush=True)
            return
        time.sleep(PAUSE_SECONDS)

    print("\n=== Part 1: QA cases" + (f" (resuming at {args.qa_from})" if args.qa_from else ""), flush=True)
    rows = run_qa_part(lambda q: graph.answer_question(DOC_ID, q, book_title=BOOK), guard, qa_path,
                       fingerprint, start_from=args.qa_from, previous=previous,
                       extra={"verification": verify_rows} if verify_rows else None)
    summary = qa_summary(rows)
    print(f"\nDONE qa={summary} -> {qa_path}", flush=True)
    nxt = first_unfinished(rows)
    if nxt:
        print(f"Unfinished cases remain (first: {nxt}). Resume with:\n  "
              + RESUME_COMMAND.format(case_id=nxt), flush=True)


if __name__ == "__main__":
    main()
