#!/usr/bin/env python3
"""재분류 표시가 붙은 후기를 v3 기준으로 다시 분류한다.

classify_pending.py 는 '미분류'를 처리하고, 이 스크립트는 '이미 분류됐지만
v3 기준으로 다시 봐야 하는' 후기(classification.reclassify_pending)를 처리한다.

  python3 reclassify_v3.py --limit 30            # 30건만. 시간·토큰 보고
  python3 reclassify_v3.py --limit 30 --dry-run  # 저장 안 함
  python3 reclassify_v3.py                       # 전량 (배치 반복)
"""
import json, os, re, sys, time, subprocess, collections
import taxonomy as T
from classify_pending import build_prompt, parse_json_obj, claude_env, find_claude

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
BATCH = int(os.environ.get("CLASSIFY_BATCH_LIMIT", "40"))


def arg(name, default=None, cast=str):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return cast(sys.argv[i + 1])
    return default


LIMIT = arg("--limit", 0, int)
DRY = "--dry-run" in sys.argv


def run_claude_measured(prompt: str):
    """claude -p 를 JSON 출력으로 돌려 본문과 사용량을 함께 받는다."""
    cmd = [find_claude(), "-p", "--output-format", "json"]
    t0 = time.time()
    # 프롬프트는 stdin 으로. 배치 40건이면 30KB 가 넘는다.
    res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                         timeout=1800, env=claude_env())
    elapsed = time.time() - t0
    if res.returncode != 0:
        dump = "/tmp/nonohumble_reclassify_error.txt"
        with open(dump, "w", encoding="utf-8") as f:
            f.write(f"rc={res.returncode}\n\n--- stdout ---\n{res.stdout}\n\n--- stderr ---\n{res.stderr}")
        raise RuntimeError(f"claude -p 실패(rc={res.returncode}). 전체 출력: {dump}\n"
                           f"  stdout 앞부분: {res.stdout.strip()[:300]}")
    try:
        env = json.loads(res.stdout)
    except json.JSONDecodeError:
        return res.stdout, {}, None, elapsed
    # 로그인 실패·잔액 소진은 종료코드 0 으로 돌아온다. is_error 를 봐야 잡힌다.
    if env.get("is_error"):
        raise RuntimeError(f"claude -p 오류: {str(env.get('result'))[:200]}")
    return env.get("result") or "", env.get("usage") or {}, env.get("total_cost_usd"), elapsed


def main():
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    reviews = data["reviews"]

    targets = [rv for rv in reviews.values()
               if (rv.get("classification") or {}).get("reclassify_pending")]
    if not targets:
        print("✅ 재분류 대상 없음. migrate_v3.py --apply 를 먼저 돌렸는지 확인하세요.")
        return
    total_targets = len(targets)
    if LIMIT:
        targets = targets[:LIMIT]

    print(f"재분류 대상 {total_targets}건 중 이번 실행 {len(targets)}건 "
          f"(배치 {BATCH}건씩 {(len(targets)+BATCH-1)//BATCH}회)\n")

    tin = tout = tcache_r = tcache_w = 0
    cost_sum = 0.0
    t_start = time.time()
    done = failed = 0
    changes = collections.Counter()

    for i in range(0, len(targets), BATCH):
        batch = targets[i:i + BATCH]
        raw, usage, cost, elapsed = run_claude_measured(build_prompt(batch))
        tin  += usage.get("input_tokens", 0)
        tout += usage.get("output_tokens", 0)
        tcache_r += usage.get("cache_read_input_tokens", 0)
        tcache_w += usage.get("cache_creation_input_tokens", 0)
        if cost: cost_sum += cost

        try:
            result = parse_json_obj(raw)
        except Exception as e:
            print(f"  ❌ 배치 {i//BATCH+1} 파싱 실패: {e}")
            failed += len(batch); continue

        for rv in batch:
            clf = result.get(rv["id"]) or result.get(str(rv["id"]))
            if not clf or not clf.get("segments"):
                failed += 1; continue
            before = [s.get("category") for s in (rv.get("classification") or {}).get("segments") or []]
            clf = T.postprocess(clf)
            after = [s.get("category") for s in clf["segments"]]
            if before != after:
                changes[f"{'+'.join(before) or '?'} → {'+'.join(after)}"] += 1
            clf.pop("reclassify_pending", None)
            rv["classification"] = clf
            rv["hashtags"] = clf.get("tags", [])
            done += 1
        print(f"  배치 {i//BATCH+1}: {len(batch)}건 · {elapsed:.0f}초")

    wall = time.time() - t_start
    print(f"\n{'─'*52}")
    print(f"처리      {done}건 성공 / {failed}건 실패")
    print(f"소요 시간  {wall:.0f}초  (건당 {wall/max(done,1):.1f}초)")
    print(f"토큰      입력 {tin:,} · 출력 {tout:,}"
          + (f" · 캐시읽기 {tcache_r:,} · 캐시생성 {tcache_w:,}" if (tcache_r or tcache_w) else ""))
    if done:
        print(f"          건당 평균 입력 {tin//done:,} · 출력 {tout//done:,}")
    if cost_sum:
        print(f"비용      ${cost_sum:.4f}  (건당 ${cost_sum/max(done,1):.5f})")
        print(f"전량({total_targets}건) 환산  약 ${cost_sum/max(done,1)*total_targets:.2f} · "
              f"{wall/max(done,1)*total_targets/60:.0f}분")
    else:
        print(f"전량({total_targets}건) 환산  약 {wall/max(done,1)*total_targets/60:.0f}분")

    if changes:
        print(f"\n분류가 바뀐 것 상위:")
        for k, v in changes.most_common(8):
            print(f"  {v:3d}  {k}")

    if DRY:
        print("\n[DRY-RUN] 저장 안 함")
        return
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)
    print(f"\n💾 저장 완료: {DATA_FILE}")


if __name__ == "__main__":
    main()
