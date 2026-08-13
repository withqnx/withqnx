# 겸손몰(NONOHUMBLE) 후기분석 시스템 — 운영 런북

> 이 폴더(`~/nonohumble-review`)가 **운영 기준 폴더**다. 크롤·배포·보고서는 모두 여기서 실행한다.
> NAS(`/Volumes/Mall(new)/DATA/NONOHUMBLE_REVIEW/`)는 **백업/산출물 보관용** — 거기서 크롤하지 말 것.
> (둘 다 같은 `withqnx/withqnx` 레포 클론이라, 두 곳에서 크롤하면 data.json이 엇갈려 git 충돌난다.)

## 핵심 제약
- **크롤링은 한국 IP에서만 된다.** cafe24 게시판이 해외 IP를 차단 → GitHub Actions(미국)에서 돌리면 0건. 반드시 이 Mac(한국)에서 실행.
- 비밀파일(`.env`, `인수인계_HANDOVER.md`)은 `.gitignore`로 제외됨. **절대 커밋 금지.**

## 자격증명 / 비용
- 키는 `.env`에 있음 (`ANTHROPIC_API_KEY`, `CF_*`). 현재 키 그대로 사용.
- **Anthropic/Cloudflare API 잔액이 소진되면 즉시 사용자에게 알릴 것.** 그때 새 키를 받아 `.env`와 GitHub Secrets를 교체한다.

## 자동 실행 — 매일 오전 8시 (2026-08-11~)
launchd `com.nonohumble.crawl`(`~/Library/LaunchAgents/com.nonohumble.crawl.plist`)가 **매일 08:00**에
`auto_crawl.sh`를 실행: **수집 → Claude Code 분류 → 커밋 → push(3회 재시도) → Cloudflare 배포 대기**. 완전 자동, 사람 개입·브라우저 없음.
- 신규 후기 0건이면 커밋하지 않음(빈 커밋·불필요 배포 방지).
- 브라우저를 띄우려면 `OPEN_SITE=1 bash auto_crawl.sh`.
- 로그: `/tmp/nonohumble_crawl.log`, 에러: `/tmp/nonohumble_crawl_error.log`.
- 즉시 1회 실행: `launchctl start com.nonohumble.crawl`
- ⚠️ **8시에 Mac이 꺼져있거나 잠들어 있으면 그 시각엔 못 돌고, 깨어난 직후 1회 실행**된다(launchd 동작). 정각 보장이 필요하면 `pmset repeat wake` 로 자동 기상 설정 필요(관리자 권한 — 사용자가 직접 실행).

## 대시보드 진입 (2026-08-13~)
게이트 비밀번호 하나로 권한이 갈린다. **별도 관리자 버튼 없음.**
- 일반 비번 → 일반 모드 / 관리자 비번 → 관리자 모드(Publish·Review 탭 노출, 우상단 🔓 Admin 배지)
- 관리자 해제는 탭/브라우저 닫기(sessionStorage 기준).

## ⚠️ git push 인증 — 이 저장소는 withqnx 고정
Mac에 GitHub 계정이 2개(`withqnx`, `10MH`) 로그인돼 있어, **gh 활성 계정이 `10MH`로 바뀌면 push가 403**으로 실패한다(팀 브레인 `10MH/tenmilhee-brain` 작업 후 발생).
→ 이 저장소 `.git/config`에 **withqnx 자격증명을 고정**해둠(전역 설정·다른 세션에 영향 없음, 토큰은 파일에 저장 안 하고 gh 키체인에서 조회):
```bash
git config --local --replace-all credential.helper ""
git config --local --add credential.helper '!f() { echo username=withqnx; echo "password=$(gh auth token --user withqnx)"; }; f'
```
push 403이 다시 나면 위 설정이 살아있는지 `git config --local --get-all credential.helper`로 확인.

## 분류 방식 — Claude Code(구독) 사용 (2026-08-11~)
후기 분류는 **Anthropic API 키 대신 Claude Code(`claude -p` 헤드리스, 구독)** 로 처리한다.
- `crawl.py` 는 `CLASSIFY_MODE=claude` 이면 **수집만** 하고 분류는 건너뜀(미분류로 저장).
- `classify_pending.py` 가 미분류 후기를 모아 `claude -p` 로 **배치 분류** → data.json 갱신.
- 분류 기준(`CLASSIFY_SYSTEM`)은 crawl.py 단일 출처. `CLASSIFY_MODE` 미지정 시 기본값은 예전처럼 `api`.

## 명령 모음
```bash
# 환경 로드 (모든 작업 전)
cd ~/nonohumble-review
source ~/.nonohumble_venv/bin/activate
set -a; source .env; set +a

# 1) 크롤 + 분류 + 배포 (권장: 한 방에)
bash ~/nonohumble-review/auto_crawl.sh
#   = 수집(CLASSIFY_MODE=claude) → Claude Code 분류 → 커밋 → push(3회 재시도) → 배포대기 → 사이트 오픈

#   수동 단계별:
CLASSIFY_MODE=claude python3 crawl.py     # 신규 후기 수집만
python3 classify_pending.py               # 미분류분 Claude Code 배치 분류
git add data.json && git commit -m crawl && git push   # → GitHub Actions가 Cloudflare 배포
#   (옛 방식: 그냥 `python3 crawl.py` 하면 Haiku API로 분류. .env에 ANTHROPIC_API_KEY 필요)

# 2) PDF 보고서 생성 (가로 16:9, Chrome headless --print-to-pdf)
python3 build_report.py   # → 겸손몰_후기분석_report_YYYYMMDD.pdf

# 3) 로컬 미리보기
python3 server.py         # http://localhost:7878
```

## 분류 기준 (단일 출처)
- `분류 가이드 v2.md`가 기준. crawl.py의 시스템 프롬프트와 **항상 동일하게 유지**.
- 카테고리 6 / 해시태그 14 / confidence.

## 산출물 / 링크
- 대시보드: https://nonohumble-review.pages.dev
- 저장소: https://github.com/withqnx/withqnx (main)
- 자세한 인수인계: NAS의 `인수인계_HANDOVER.md` (비밀 포함, 커밋 금지)

## 통계 해석 원칙
후기는 자기선택 편향 표본. **절대 %는 신뢰 어렵고, 상대 비교·패턴은 신뢰 가능**(나침반이지 자(ruler) 아님). 사내 실제 반품·교환율과 교차검증 권장.
