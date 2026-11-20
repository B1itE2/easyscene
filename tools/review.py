"""AI review helper (system Python, no Blender).

  python3 tools/review.py prepare out/NAME   # writes out/NAME/review_request.md, prints it
  python3 tools/review.py score   out/NAME   # reads out/NAME/review.json, prints PASS/FAIL

An agent that can see images opens the files listed in review_request.md,
scores each rubric item 0-10 and writes review.json:

  {"round": 1, "scores": {"fog_depth": 8, ...}, "issues": ["..."], "changes": ["weather: dense_fog"]}

Agents without vision: show the images to the user and let the user score.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from easyscene import recipes  # noqa: E402


def _load(out):
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return m, recipes.load(m["spec"]["style"])


def prepare(out: Path):
    m, r = _load(out)
    imgs = [p for p in ("still.png", "sheet.png") if (out / p).exists()]
    lines = [f"# Review request: {out.name}", "",
             f"Style: **{r['title']}**  ·  seed {m['seed']}  ·  prompt: {m['spec'].get('prompt', '')}", "",
             "## Look at", *[f"- `{out / p}`" for p in imgs], "",
             "## Score each item 0-10 (10 = film still quality, 7 = good enough to publish)", "",
             "| id | weight | what to judge |", "|---|---|---|"]
    lines += [f"| {it['id']} | {it['weight']} | {it['desc']} |" for it in r["rubric"]]
    rv = r.get("review", {})
    lines += ["", f"Pass: weighted average >= **{rv.get('pass_score', 7)}**, "
              f"at most **{rv.get('max_rounds', 2)}** fix rounds.", "",
              "## If an item scores below 7, change the SPEC (never the code):", ""]
    for k, fx in rv.get("fixes", {}).items():
        lines.append(f"- **{k}**: " + "; ".join(fx))
    lines += ["", "## Write `review.json` next to the images:", "```json",
              json.dumps({"round": 1, "scores": {it["id"]: 0 for it in r["rubric"]},
                          "issues": ["short, concrete"], "changes": ["spec field: new value"]},
                         ensure_ascii=False, indent=2), "```"]
    text = "\n".join(lines) + "\n"
    (out / "review_request.md").write_text(text, encoding="utf-8")
    print(text)


def score(out: Path):
    m, r = _load(out)
    rv = json.loads((out / "review.json").read_text(encoding="utf-8"))
    weights = {it["id"]: it["weight"] for it in r["rubric"]}
    missing = [k for k in weights if k not in rv.get("scores", {})]
    if missing:
        print(f"FAIL: review.json misses scores for {missing}")
        return 2
    total = sum(weights[k] * float(rv["scores"][k]) for k in weights) / sum(weights.values())
    need = r.get("review", {}).get("pass_score", 7.0)
    low = [k for k in weights if float(rv["scores"][k]) < 7]
    ok = total >= need
    print(f"{'PASS' if ok else 'FAIL'}  weighted score {total:.2f} / 10 (need {need})")
    if low:
        print("items below 7: " + ", ".join(low))
        for k in low:
            print(f"  fix {k}: " + "; ".join(r.get("review", {}).get("fixes", {}).get(k, [])))
    rv["weighted"] = round(total, 2)
    rv["passed"] = ok
    (out / "review.json").write_text(json.dumps(rv, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("prepare", "score"):
        print(__doc__)
        sys.exit(2)
    sys.exit((prepare if sys.argv[1] == "prepare" else score)(Path(sys.argv[2])) or 0)
