#!/usr/bin/env python3
"""감정 2차 판정 — 분류기와 다른 프롬프트로 다시 묻고, 갈리는 건만 검토 큐로.

외부 API를 쓰지 않는다. Claude Code 구독(claude -p)만 쓴다.
  python3 verify_sentiment.py --validate   정답지 100건으로 포착률 측정
  python3 verify_sentiment.py --apply      data.json 전체에 적용
  python3 verify_sentiment.py --new        새로 분류된 것만 (매일 아침)
"""
import json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_pending import claude_env, find_claude

SP = "/private/tmp/claude-501/-Volumes-Mall-new--DATA-NONOHUMBLE-REVIEW/d7f023e1-5fe8-456a-84b2-a7d29e89bc8f/scratchpad"
BATCH = int(os.environ.get("VERIFY_BATCH", "30"))

GRADER = """당신은 쇼핑몰 후기에서 뽑아낸 «대목»의 감정을 판정하는 채점자입니다.
분류표를 채우는 사람이 아니라, 글쓴이의 속내를 읽는 사람입니다.

판정 기준 — 글쓴이가 쓴 감정 «단어»보다 «이 글을 왜 썼는가»를 우선합니다.
- 긍정: 제품이나 경험에 만족함. 표현이 담백하거나 짧아도 만족이면 긍정.
        재구매·추가구매 의사는 가장 강한 긍정. 품절이 아쉽다는 말도 제품 만족의 표현이다.
- 중립: 단순 수령 보고, 사실 서술, 또는 질문. 문제를 언급하더라도
        «수리 되나요» «언제 오나요» «어떻게 쓰나요»처럼 묻는 것이 주된 의도면 중립이다.
- 부정: 제품이나 서비스에 대한 불만·실망이 글의 주된 의도인 경우.

아래 항목마다 한 줄씩, `번호|긍정` `번호|중립` `번호|부정` 중 하나만 출력하세요.
설명·머리말·코드블록 없이 줄만 출력합니다."""

def ask(items):
    lines = [GRADER, ""]
    for n, it in enumerate(items, 1):
        lines += [f"[{n}] 제품: {it['product']}",
                  f"    후기: {(it['content'] or '(본문 없음)')[:400]}",
                  f"    대목: {it['target']}", ""]
    cmd = [find_claude(), "-p", "--output-format", "text"]
    r = subprocess.run(cmd, input="\n".join(lines), capture_output=True,
                       text=True, timeout=900, env=claude_env())
    if r.returncode != 0:
        raise RuntimeError(f"claude -p rc={r.returncode}: {(r.stdout or r.stderr)[:200]}")
    out = {}
    for m in re.finditer(r"^\s*\[?(\d+)\]?\s*\|\s*(긍정|중립|부정)\s*$", r.stdout, re.M):
        out[int(m.group(1))] = m.group(2)
    return out

def run(items, label):
    got, t0 = {}, time.time()
    for i in range(0, len(items), BATCH):
        chunk = items[i:i+BATCH]
        try:
            res = ask(chunk)
        except Exception as e:
            print(f"  배치 {i//BATCH+1} 실패: {str(e)[:140]}", flush=True); continue
        for k, v in res.items():
            if 1 <= k <= len(chunk): got[chunk[k-1]["key"]] = v
        print(f"  {min(i+BATCH,len(items))}/{len(items)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"{label}: {len(got)}/{len(items)}건 판정 · {time.time()-t0:.0f}초", flush=True)
    return got

def validate():
    import glob
    samp = json.load(open(f"{SP}/sample100.json"))
    lab = {os.path.basename(f)[:-5]: json.load(open(f))
           for f in glob.glob(f"{SP}/labels/labels/*.json")}
    items, truth, claude_said = [], {}, {}
    for rv in samp:
        fixed = {i: g for i, g in enumerate(lab.get(rv["id"], {}).get("segments") or [], 1)}
        for i, s in enumerate(rv["segments"], 1):
            g = fixed.get(i)
            if g and g.get("drop"): continue
            key = f"{rv['id']}#{i}"
            items.append({"key": key, "product": rv["product"], "content": rv["content"],
                          "target": (s.get("summary") or "요약 없음") + f" [측면: {s.get('aspect')}]"})
            truth[key] = g["after"]["sentiment"] if g else s.get("sentiment")
            claude_said[key] = s.get("sentiment")
    print(f"검증 대상 세그먼트 {len(items)}개", flush=True)
    got = run(items, "2차 판정")
    keys = [k for k in items if False] or [it["key"] for it in items if it["key"] in got]
    err = [k for k in keys if claude_said[k] != truth[k]]
    dis = [k for k in keys if got[k] != claude_said[k]]
    caught = [k for k in err if k in dis]
    v_ok = sum(1 for k in keys if got[k] == truth[k])
    print("\n" + "─"*52)
    print(f"1차(분류기) 정확도 : {sum(1 for k in keys if claude_said[k]==truth[k])}/{len(keys)}")
    print(f"2차(채점자) 정확도 : {v_ok}/{len(keys)}")
    print(f"두 판정 불일치      : {len(dis)}건 ({len(dis)/len(keys)*100:.1f}%)  ← 사람이 볼 양")
    print(f"1차 오답            : {len(err)}건")
    print(f"그중 불일치로 포착  : {len(caught)}/{len(err)}"
          + (f" = {len(caught)/len(err)*100:.0f}%" if err else ""))
    print("─"*52)
    for k in err:
        print(f"  {'✅잡음' if k in caught else '❌놓침'} {k} 정답 {truth[k]} / 1차 {claude_said[k]} / 2차 {got.get(k)}")
    json.dump({"got": got, "truth": truth, "claude": claude_said},
              open(f"{SP}/verify_validate.json", "w"), ensure_ascii=False)

def apply_all(only_new=False):
    """세그먼트를 2차 판정하고, 1차와 갈리는 건을 검토 큐로 보낸다.
    기존 confidence 게이트는 지우지 않고 _conf_low 로 보존한다.
    only_new=True 면 아직 2차 판정이 없는 세그먼트만 처리한다(매일 아침용)."""
    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    data = json.load(open(DATA))
    reviews = data["reviews"]
    items = []
    for rv in reviews.values():
        for i, sg in enumerate((rv.get("classification") or {}).get("segments") or [], 1):
            if only_new and sg.get("verify"): continue
            items.append({"key": f"{rv['id']}#{i}", "product": rv.get("product_name") or "",
                          "content": rv.get("content") or "",
                          "target": (sg.get("summary") or "요약 없음") + f" [측면: {sg.get('aspect')}]"})
    if not items:
        print("2차 판정할 새 세그먼트 없음.", flush=True); return
    print(f"{'새 ' if only_new else '전체 '}세그먼트 {len(items)}개 · 배치 {BATCH} · {(len(items)+BATCH-1)//BATCH}회", flush=True)
    got, t0, done = {}, time.time(), 0
    for i in range(0, len(items), BATCH):
        chunk = items[i:i+BATCH]
        try:
            res = ask(chunk)
        except Exception as e:
            print(f"  배치 {i//BATCH+1} 실패: {str(e)[:140]}", flush=True); continue
        for k, v in res.items():
            if 1 <= k <= len(chunk): got[chunk[k-1]["key"]] = v
        done = len(got)
        if (i//BATCH) % 10 == 9:
            write_back(data, got); save(DATA, data)
            print(f"  {min(i+BATCH,len(items))}/{len(items)} · 판정 {done} · {time.time()-t0:.0f}s (중간저장)", flush=True)
    write_back(data, got); save(DATA, data)
    dis = sum(1 for rv in reviews.values() if (rv.get("classification") or {}).get("disagree"))
    nr  = sum(1 for rv in reviews.values() if (rv.get("classification") or {}).get("needs_review"))
    print(f"\n판정 {done}/{len(items)} · {time.time()-t0:.0f}초")
    print(f"불일치 후기 {dis}건 · 검토 큐 {nr}건 / {len(reviews)}건")

def write_back(data, got):
    for rv in data["reviews"].values():
        clf = rv.get("classification") or {}
        segs = clf.get("segments") or []
        if not segs: continue
        dis = False; any_v = False
        for i, sg in enumerate(segs, 1):
            v = got.get(f"{rv['id']}#{i}")
            if not v: continue
            any_v = True
            sg["verify"] = v
            if v != sg.get("sentiment"): dis = True
        if not any_v: continue
        if "_conf_low" not in clf:
            clf["_conf_low"] = bool(clf.get("needs_review"))
        clf["disagree"] = dis
        clf["needs_review"] = dis

def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

if __name__ == "__main__":
    if "--validate" in sys.argv: validate()
    elif "--apply" in sys.argv: apply_all()
    elif "--new" in sys.argv: apply_all(only_new=True)
    else: print("사용법: --validate | --apply")
