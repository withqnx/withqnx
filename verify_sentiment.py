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

def auto_ok_type(sg):
    """1·2차가 갈려도 사람이 볼 필요 없는 유형이면 그 이름, 아니면 None.
    두 판정기가 애초에 다른 기준을 쓰게 만들어져 생기는 구조적 불일치라 1차(규칙)를 따른다.
    이석원 승인 2026-09-30. 재구매희망은 v3.4 예외를 지켜보는 중이라 항상 사람에게 올린다."""
    a, b = sg.get("sentiment"), sg.get("verify")
    intent, aspect = sg.get("intent") or "없음", sg.get("aspect")
    if intent == "재구매희망":
        return None
    if intent in ("교환·반품", "양도·거래", "문의"):
        return "의도가_분류결정"      # 파생 카테고리가 의도로 정해져 감정이 갈려도 숫자 불변
    if aspect == "배송·포장" and a == "중립" and b == "긍정":
        return "배송_기다림서술"      # "오래 기다렸지만 좋다" — 제품 칭찬은 다른 대목에 있음
    if intent == "제품제안":
        return "제품제안"             # 제안 자체는 중립, 칭찬은 다른 대목에 있음
    if intent == "없음" and a == "부정" and b == "중립":
        return "작은불만_부정유지"    # 작은 불만도 제품 문제를 말했으면 부정
    return None


def mark_review(clf):
    """세그먼트별 판정을 보고 disagree(원래 불일치)·needs_review(사람이 볼 것)를 다시 계산."""
    dis = need = False
    for sg in clf.get("segments") or []:
        sg.pop("_auto_ok", None)
        v = sg.get("verify")
        if not v or v == sg.get("sentiment") or sg.get("_gold"):
            continue
        dis = True
        t = auto_ok_type(sg)
        if t:
            sg["_auto_ok"] = t
        else:
            need = True
    clf["disagree"] = dis
    clf["needs_review"] = need


def write_back(data, got):
    for rv in data["reviews"].values():
        clf = rv.get("classification") or {}
        segs = clf.get("segments") or []
        if not segs: continue
        any_v = False
        for i, sg in enumerate(segs, 1):
            v = got.get(f"{rv['id']}#{i}")
            if not v: continue
            any_v = True
            sg["verify"] = v
        if not any_v: continue
        if "_conf_low" not in clf:
            clf["_conf_low"] = bool(clf.get("needs_review"))
        mark_review(clf)

def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


JUDGE = """당신은 쇼핑몰 후기의 «대목» 하나를 두고 두 판정자가 내린 서로 다른 답 중
어느 쪽이 옳은지 고르는 심판입니다.

판정 기준 — 글쓴이가 쓴 감정 «단어»보다 «이 글을 왜 썼는가»를 우선합니다.
- 긍정: 제품·경험에 만족. 담백해도 만족이면 긍정. 재구매 의사는 가장 강한 긍정.
        품절이 아쉽다는 말도 제품 만족의 표현이다.
- 중립: 단순 수령 보고, 사실 서술, 또는 질문. 문제를 언급하더라도 묻는 것이
        주된 의도면 중립이다.
- 부정: 제품·서비스에 대한 불만·실망이 글의 주된 의도인 경우.

두 답 중 하나를 고르세요. 항목마다 한 줄씩 `번호|A` 또는 `번호|B` 만 출력합니다.
설명·머리말 없이 줄만 출력하세요."""

def ask_judge(items):
    lines = [JUDGE, ""]
    for n, it in enumerate(items, 1):
        lines += [f"[{n}] 제품: {it['product']}",
                  f"    후기: {(it['content'] or '(본문 없음)')[:400]}",
                  f"    대목: {it['target']}",
                  f"    A: {it['A']}    B: {it['B']}", ""]
    cmd = [find_claude(), "-p", "--output-format", "text"]
    r = subprocess.run(cmd, input="\n".join(lines), capture_output=True,
                       text=True, timeout=900, env=claude_env())
    if r.returncode != 0:
        raise RuntimeError(f"claude -p rc={r.returncode}: {(r.stdout or r.stderr)[:200]}")
    out = {}
    for m in re.finditer(r"^\s*\[?(\d+)\]?\s*\|\s*([AB])\s*$", r.stdout, re.M):
        out[int(m.group(1))] = m.group(2)
    return out

def judge():
    """검증셋에서 두 판정이 갈린 건만 심판에게 물어 채점한다."""
    import random
    V = json.load(open(f"{SP}/verify_validate.json"))
    got, truth, first = V["got"], V["truth"], V["claude"]
    samp = {rv["id"]: rv for rv in json.load(open(f"{SP}/sample100.json"))}
    dis = [k for k in got if k in truth and got[k] != first[k]]
    random.seed(11)
    items = []
    for k in dis:
        rid, idx = k.split("#"); rv = samp[rid]; sg = rv["segments"][int(idx)-1]
        flip = random.random() < 0.5          # 위치 편향 제거
        A, B = (got[k], first[k]) if flip else (first[k], got[k])
        items.append({"key": k, "product": rv["product"], "content": rv["content"],
                      "target": (sg.get("summary") or "요약 없음") + f" [측면: {sg.get('aspect')}]",
                      "A": A, "B": B, "A_is_2nd": flip})
    print(f"갈린 {len(items)}건을 심판에게 물어본다 (A/B 위치는 무작위)", flush=True)
    picks = {}
    for i in range(0, len(items), BATCH):
        chunk = items[i:i+BATCH]
        res = ask_judge(chunk)
        for kk, vv in res.items():
            if 1 <= kk <= len(chunk): picks[chunk[kk-1]["key"]] = vv
    right = pick2 = 0
    rows = []
    for it in items:
        p = picks.get(it["key"])
        if not p: continue
        chosen = it["A"] if p == "A" else it["B"]
        ok = chosen == truth[it["key"]]
        right += ok
        pick2 += (chosen == got[it["key"]])
        rows.append((it["key"], truth[it["key"]], first[it["key"]], got[it["key"]], chosen, ok))
    n = len(rows)
    print("\n" + "─"*56)
    print(f"심판 정확도 : {right}/{n} = {right/n*100:.0f}%")
    print(f"  (참고) 1차를 그냥 믿었다면 : {sum(1 for r in rows if r[2]==r[1])}/{n}")
    print(f"  (참고) 2차를 그냥 믿었다면 : {sum(1 for r in rows if r[3]==r[1])}/{n}")
    print(f"  심판이 2차를 고른 비율     : {pick2}/{n}")
    print("─"*56)
    for k, t, f1, f2, ch, ok in rows:
        print(f"  {'✅' if ok else '❌'} {k:12s} 정답 {t} / 1차 {f1} / 2차 {f2} → 심판 {ch}")

if __name__ == "__main__":
    if "--validate" in sys.argv: validate()
    elif "--apply" in sys.argv: apply_all()
    elif "--new" in sys.argv: apply_all(only_new=True)
    elif "--judge" in sys.argv: judge()
    else: print("사용법: --validate | --apply")
