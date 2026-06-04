# 겸손은힘들다 후기 인텔리전스 — 설치 & 사용 가이드

## 1. 폴더 확인

다운로드한 파일들이 같은 폴더에 있어야 합니다:
```
nonohumble-reviews/
├── crawl.py
├── index.html
└── README.md  (지금 이 파일)
```

---

## 2. 터미널에서 필수 라이브러리 설치 (최초 1회)

```bash
pip install requests beautifulsoup4
```

---

## 3. (선택) AI 분류 사용하기

후기 분류를 키워드 방식 대신 Claude AI가 자동으로 해주도록 하려면:

**방법 A — 환경변수 설정 (권장)**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
매번 터미널을 새로 열면 다시 입력해야 하니,
`~/.zshrc` 파일 맨 아래에 위 줄을 추가하면 자동 적용됩니다.

**방법 B — 코드에 직접 입력**
`crawl.py` 파일을 TextEdit으로 열고
`ANTHROPIC_API_KEY = ""` 부분의 따옴표 안에 키를 붙여넣기.

API 키 없이도 키워드 기반 자동 분류가 작동합니다.

---

## 4. 크롤링 실행

```bash
cd ~/Desktop/nonohumble-reviews   # 폴더 위치에 맞게 수정
python crawl.py
```

처음 실행 시 `data.json` 파일이 생성됩니다.
매일 실행하면 새 후기만 추가로 수집됩니다.

---

## 5. 대시보드 열기

`index.html` 파일을 더블클릭하거나:
```bash
open index.html
```

---

## 6. 매일 자동 실행 설정 (선택)

터미널에서 아래 명령어로 매일 오전 9시에 자동 실행:

```bash
crontab -e
```

에디터가 열리면 아래 줄 추가 (경로는 실제 위치로 수정):
```
0 9 * * * cd ~/Desktop/nonohumble-reviews && python crawl.py
```

---

## 7. 더 많은 과거 후기 수집

`crawl.py` 파일에서 아래 줄의 숫자를 늘리면 됩니다:
```python
MAX_PAGES = 5   # ← 20이나 50으로 늘리면 과거 후기까지 수집
```

---

## 대시보드 기능

| 탭 | 내용 |
|---|---|
| 오늘의 현황 | 오늘 새로 올라온 후기 목록 + 원문 링크 |
| 상품별 분석 | 아이템별 후기 유형 비율 차트 · 클릭하면 필터링 |
| 사진 모아보기 | 첨부 사진 그리드 · 숨기기/보이기 토글 |
