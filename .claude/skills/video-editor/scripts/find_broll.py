"""Find licensed B-roll for the key phrases of an edit, then (after the user approves) download it, write credits and
place each insert on its phrase in the edit plan.

Step 1 - search (metadata only, nothing downloaded):
  python -I find_broll.py search <moments.json> <plan.json> <out_candidates.json> [--context flood] [--max 5] [--per 3] [--gap 6]
    moments.json from pick_moments.py. Picks up to --max phrases (rarest first, >= --gap s apart, not on cards, intro
    shots, split screens or behind-word windows), searches Wikimedia Commons for each (video first, then pictures),
    keeps free licences only (CC0, public domain, CC BY, CC BY-SA), landscape >= 1000 px, no maps/logos/diagrams, and
    prints a numbered list: phrase, file, licence, author, size, length, page URL. Show it to the user.
Step 2 - fetch the approved ones (a download: the user must have said yes to these files and sizes):
  python -I find_broll.py fetch <candidates.json> <plan.json> --pick 1a 2b 4a --dir ../broll [--len 2.2]
    1a = phrase 1, candidate a. Downloads with a contact User-Agent, appends CREDITS.md in --dir, and adds a "broll"
    entry on the clip that holds the phrase (starts 0.2 s before it, --len seconds, never past the clip).
Commons rejects anonymous downloads (HTTP 429): set UA below to name the project and a contact URL (no e-mail).
Commons only: films and TV are not licensed B-roll, even when they look good in reference edits.
"""
import argparse, html, json, pathlib, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from edit_plan import build_timeline

UA = {"User-Agent": "video-editor-skill-tests/1.2 (https://github.com/phumrapee47/skills-video-editor)"}
FREE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? [0-9.]+( [a-z]{2})?|CC BY(-SA)?)", re.I)
BAD = re.compile(r"\b(map|logo|diagram|chart|graph|flag|icon|svg|coat of arms|seal|screenshot|poster|text)\b", re.I)


def api(params):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))


def strip(s): return re.sub("<[^>]+>", "", html.unescape(s or "")).strip()


def search(query, kind, n=12):
    d = api({"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:{kind}", "gsrnamespace": 6, "gsrlimit": n,
             "prop": "imageinfo", "iiprop": "url|size|extmetadata|mediatype"})
    out = []
    for p in d.get("query", {}).get("pages", {}).values():
        ii = p.get("imageinfo", [{}])[0]; m = ii.get("extmetadata", {}); lic = m.get("LicenseShortName", {}).get("value", "")
        w, h = ii.get("width", 0), ii.get("height", 0); dur = float(ii.get("duration", 0) or 0)
        title = p["title"][5:]
        if not FREE.match(lic) or BAD.search(title) or w < 1000 or w < h: continue
        if kind == "video" and (dur < 2 or ii["size"] > 120e6): continue
        if kind == "bitmap" and ii["size"] > 25e6: continue
        out.append({"title": title, "kind": kind, "license": lic, "author": strip(m.get("Artist", {}).get("value"))[:80],
                    "w": w, "h": h, "duration": round(dur, 1), "mb": round(ii["size"] / 1e6, 1), "url": ii["url"].split("?")[0],
                    "page": ii.get("descriptionurl", ""), "index": p.get("index", 99)})
    return out


def relevance(c, toks):
    t = c["title"].lower(); hit = sum(1 for x in toks if x in t)
    return hit * 2 + (1.5 if c["kind"] == "video" else 0) - c["index"] * 0.05 + (0.5 if c["w"] >= 1920 else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("search"); s1.add_argument("moments"); s1.add_argument("plan"); s1.add_argument("out")
    s1.add_argument("--max", type=int, default=5); s1.add_argument("--per", type=int, default=3); s1.add_argument("--gap", type=float, default=6.0)
    s1.add_argument("--context", default="", help="topic word(s) added to every search, e.g. flood")
    s2 = sub.add_parser("fetch"); s2.add_argument("candidates"); s2.add_argument("plan"); s2.add_argument("--pick", nargs="+", required=True)
    s2.add_argument("--dir", required=True); s2.add_argument("--len", type=float, default=2.2)
    a = ap.parse_args()
    if a.cmd == "search":
        mom = json.load(open(a.moments, encoding="utf-8")); pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
        tl, total = build_timeline(plan); src = next(c["src"] for c in plan["clips"] if not c.get("card"))
        busy = [(c["start"] + b["start"] - 0.5, c["start"] + b["end"] + 0.5) for c in tl for b in c.get("behind", [])]
        pool = []
        for b in mom["broll"]:
            c = next((c for c in tl if c.get("src") == src and c["in"] <= b["src_time"] < c["out"]), None)
            if not c or c.get("card") or c.get("captions") is False or c.get("fit") == "stack": continue
            t = c["start"] + (b["src_time"] - c["in"]) / c["speed"]
            if any(x <= t <= y for x, y in busy): continue
            pool.append({**b, "t": round(t, 2)})
        # search every phrase (with the topic word), then keep the phrases whose results really match their words
        for b in pool:
            toks = [x for x in b["phrase"].split() if len(x) > 2]; q = (b["phrase"] + " " + a.context).strip()
            cands = []
            for kind in ("video", "bitmap"):
                try: cands += search(q, kind)
                except Exception as e: print("search failed:", e)
                time.sleep(1)
            for c in cands: c["rel"] = round(relevance(c, toks + a.context.split()), 2)
            if not any(c["rel"] >= 2 and any(t in c["title"].lower() for t in toks) for c in cands) and len(toks) > 1:
                for t in sorted(toks, key=len, reverse=True):      # too narrow: one word at a time (longest = most specific)
                    q2 = (t + " " + a.context).strip(); more = []
                    for kind in ("video", "bitmap"):
                        try: more += search(q2, kind)
                        except Exception as e: print("search failed:", e)
                        time.sleep(1)
                    for c in more: c["rel"] = round(relevance(c, [t] + a.context.split()), 2)
                    if any(t in c["title"].lower() for c in more): cands, q = more, q2; break
            b["candidates"] = sorted(cands, key=lambda c: -c["rel"])[: a.per]
            b["best"] = b["candidates"][0]["rel"] if b["candidates"] and any(t in b["candidates"][0]["title"].lower() for t in toks) else -9
            b["query"] = q
        result = []
        for b in sorted(pool, key=lambda b: -b["best"]):
            if b["best"] < 2 or any(abs(b["t"] - q["t"]) < a.gap for q in result): continue   # 2 = at least one word in a title
            result.append(b)
            if len(result) >= a.max: break
        result.sort(key=lambda b: b["t"])
        for k, b in enumerate(result, 1):
            print(f"\n{k}. \"{b['phrase']}\" (search: {b['query']}) at {b['t']:.1f} s  | {b['sentence']}")
            for j, c in enumerate(b["candidates"]):
                print(f"   {k}{chr(97 + j)}  {c['title'][:70]} | {c['kind']} {c['w']}x{c['h']} {c['duration']}s {c['mb']} MB | {c['license']} | {c['author'][:40]}")
        print(f"\n{len(pool)} phrases searched, {len(result)} kept (results matched their words)")
        json.dump(result, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"\nwrote {a.out}; total if all 'a' picks were taken: {sum(r['candidates'][0]['mb'] for r in result if r['candidates']):.1f} MB")
    else:
        res = json.load(open(a.candidates, encoding="utf-8")); pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
        d = pathlib.Path(a.dir); d.mkdir(parents=True, exist_ok=True); cred = d / "CREDITS.md"
        if not cred.exists(): cred.write_text("# B-roll credits (Wikimedia Commons)\n\n", encoding="utf-8")
        src = next(c["src"] for c in plan["clips"] if not c.get("card"))
        for p in a.pick:
            k, j = int(p[:-1]) - 1, ord(p[-1]) - 97; b = res[k]; c = b["candidates"][j]
            ext = c["url"].rsplit(".", 1)[-1].lower(); fn = d / f"auto_{k + 1}{p[-1]}_{re.sub(r'[^a-z0-9]+', '_', b['phrase'])}.{ext}"
            data = urllib.request.urlopen(urllib.request.Request(c["url"], headers=UA), timeout=300).read(); fn.write_bytes(data); time.sleep(2)
            with open(cred, "a", encoding="utf-8") as f: f.write(f"- {fn.name}: \"{c['title']}\" by {c['author']}, {c['license']}, {c['page']}\n")
            clip = next(cl for cl in plan["clips"] if cl.get("src") == src and cl["in"] <= b["src_time"] < cl["out"])
            sp = clip.get("speed", 1.0); s = max(0.0, (b["src_time"] - clip["in"]) / sp - 0.2); e = min((clip["out"] - clip["in"]) / sp - 0.05, s + a.len)
            rel = str(pathlib.Path(fn).resolve().relative_to(pp.parent.resolve().parent)).replace("\\", "/")
            clip.setdefault("broll", []).append({"src": "../" + rel, "start": round(s, 2), "end": round(e, 2), **({"in": 0.3} if c["kind"] == "video" else {})})
            print(f"{p}: {fn.name} {len(data) / 1e6:.1f} MB -> clip {clip['in']:.1f}-{clip['out']:.1f} s at {s:.2f}-{e:.2f}")
        json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("updated", pp.name, "and", cred)
