#!/usr/bin/env python3
"""겸손몰 후기 분석 리포트 → PDF (v6: 가로 16:9 PPT, 수빈 제외 + 건수 맥락화)"""
import json, collections, re, base64, os, subprocess
from datetime import date

ROOT=os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT)
d=json.load(open("data.json")); groups=json.load(open("groups.json")); revs=list(d["reviews"].values())
MIG={"제품관련불편":"부정","교환요청":"교환/반품","반품요청":"교환/반품","추가구매":"긍정","추가구매희망":"긍정"}
CATS6=["긍정","부정","양도/거래","교환/반품","중립/단순수령","배송관련불편"]
def cat_of(s): return MIG.get(s.get("category"),s.get("category"))
STAT=["베개","사각","펜레스트","파인라이너","세종","베개집","베개샘"]
def is_mun(r): return any(k in r.get("product_name","") for k in STAT)

cat=collections.Counter(); pos_ex=collections.Counter(); neg_ex=collections.Counter()
for r in revs:
    mun=is_mun(r)
    for s in (r.get("classification") or {}).get("segments") or []:
        c=cat_of(s)
        if c in CATS6: cat[c]+=1
        if not mun:
            for h in s.get("hashtags",[]):
                if h=="#배송": continue
                if c=="긍정": pos_ex[h]+=1
                elif c=="부정": neg_ex[h]+=1
dates=sorted([r.get("written_at","") for r in revs if re.match(r"\d{4}",r.get("written_at",""))])
date_from,date_to=dates[0][:10],dates[-1][:10]; TOTAL=len(revs)
SUM=sum(cat.values()); POS=cat["긍정"]; NEG=cat["부정"]
mon=collections.Counter()
for r in revs:
    w=r.get("written_at","")
    if re.match(r"\d{4}-\d{2}",w): mon[w[:7]]+=1

def ff(w,fn):
    b=base64.b64encode(open(os.path.join(ROOT,"fonts",fn),"rb").read()).decode()
    return f"@font-face{{font-family:'Paperlogy';font-weight:{w};src:url('data:font/ttf;base64,{b}') format('truetype');}}"
FONTS="\n".join([ff(w,fn) for w,fn in [(300,"Paperlogy-3Light.ttf"),(400,"Paperlogy-4Regular.ttf"),(500,"Paperlogy-5Medium.ttf"),(600,"Paperlogy-6SemiBold.ttf"),(700,"Paperlogy-7Bold.ttf"),(800,"Paperlogy-8ExtraBold.ttf"),(900,"Paperlogy-9Black.ttf")]])
CC={"긍정":"#60a5fa","부정":"#ef4444","중립/단순수령":"#22c55e","양도/거래":"#16a34a","교환/반품":"#fb923c","배송관련불편":"#c084fc"}
GOLD="#cc9166"; TODAY=date.today().isoformat()

def donut(segs):
    total=sum(v for _,v,_ in segs); acc=0; stops=[]
    for l,v,c in segs:
        s=acc/total*360; acc+=v; e=acc/total*360
        stops.append(f"{c} {s:.1f}deg {e:.1f}deg")
    leg="".join(f'<div class="lg"><span class="dot" style="background:{c}"></span><span class="lg-l">{l}</span><b>{v}</b><i>{v/total*100:.0f}%</i></div>' for l,v,c in segs)
    return f'<div class="donut" style="background:conic-gradient({",".join(stops)})"><div class="dhole"><b>{total:,}</b><span>반응</span></div></div><div class="legend">{leg}</div>'

def hbars(items,mx,color):
    return '<div class="chart">'+"".join(f'<div class="bar-row"><div class="bar-l">{l}</div><div class="bar-t"><div class="bar-f" style="width:{int(v/mx*100)}%;background:{color}"></div></div><div class="bar-v">{v}</div></div>' for l,v in items)+'</div>'

def statrow(cards):
    return '<div class="statrow">'+"".join(f'<div class="sc"><div class="sc-n" style="color:{c}">{n}</div><div class="sc-l">{l}</div>{f"<div class=sc-s>{s}</div>" if s else ""}</div>' for n,l,c,s in cards)+'</div>'

def gaugelist(rows):
    out=""
    for label,pos,neg in rows:
        p=pos/(pos+neg)*100
        out+=f'<div class="gg-row"><div class="gg-l">{label}</div><div class="gg-bar"><div class="gg-pos" style="width:{p:.0f}%"></div><div class="gg-pct">{p:.0f}%</div></div><div class="gg-cnt">긍 {pos}·부 {neg}</div></div>'
    return f'<div class="gaugelist">{out}</div>'

# 키워드별 수빈+문구 제외 전체 부정 건수 (맥락용)
KWTOTAL={"#사이즈":231,"#내구성":66,"#재질":83,"#마감":100,"#사용성":77,"#퀄리티":42}
KW={
"#사이즈":[("겸손구두",88,['평소 신는 치수인데 크게 나옴 — 한 치수 작게 교환 요청','복숭아뼈가 신발 라인에 닿아 통증','뒤꿈치가 헐렁해 보호대로도 해결 안 됨']),
  ("2025 색안경",50,['얼굴 평수 예측이 빗나감 — 57도 부족·54는 후회','54·57 잘못 골라 맞교환·양도 빈번','작은 얼굴엔 너무 크게 느껴짐']),
  ("퍼자마",26,['"넉넉한 S"인데 바지가 작게 나옴','허리밴드가 짧아 단추 풀어도 안 맞음','상하의 비율이 어긋남']),
  ("껑·건",17,['모자 깊이가 얕아 머리에 붕 뜸','"두상에 맞춘다"더니 안 감싸짐'])],
"#내구성":[("퍼자마",19,['라운드 티의 목이 금방 늘어남','세탁 후 옆으로 늘어나 기장이 짧아짐','면 소재가 힘없이 처짐']),
  ("발옷",10,['양말에 구멍 난 채로 배송된 불량','반나절 신었는데 발목이 뜯어지고 보풀','빨아도 잔털이 끝없이 나옴']),
  ("별(티셔츠)",10,['첫 세탁에 목이 늘어남','한 번 세탁 후 옷이 헤져 교환 요청','밑단 결이 안 맞아 울고 보풀']),
  ("겸손구두",7,['하루 만에 앞 가죽이 터져 나옴','구두 고리가 잘 빠짐'])],
"#재질":[("겸손지갑",16,['가죽이 너무 딱딱하고 뻣뻣함','여닫기가 빡빡해 사용 불편','"부드러운 양가죽이었으면"']),
  ("퍼자마",15,['텐셀 면티가 힘없이 늘어짐','옷감이 생각보다 얇음']),
  ("겸손구두",12,['자주색 가죽이 특히 딱딱','부드러울 줄 알았는데 경직됨']),
  ("여름니트",11,['원단이 두껍고 까끌까끌','목·팔끝이 따가움','"시원한 느낌이 없다"'])],
"#마감":[("별(티셔츠)",24,['어깨 봉제선 마무리가 거슬림','넥라인·암홀 오버록이 그대로 노출','"이 가격에 박음질이 싸구려"','색상이 영상보다 어두움']),
  ("퍼자마",12,['바지 주름·봉제 불량','단추·밴드 마감이 엉성']),
  ("2024 색안경",11,['안경집 마무리가 허술','천 접착이 약해 벌어짐','이음새가 거칠어 "초등학생 가위질"']),
  ("겸손구두",11,['밑창·접착부 마감','가죽 이음새가 고르지 않음'])],
"#사용성":[("겸손지갑",27,['딱딱·뻣뻣해 여닫기 빡빡','카드가 칸에 거의 안 들어감','애매한 수납 용량','두꺼운 물건이 안 들어감']),
  ("겸손구두",18,['가죽이 딱딱해 뼈가 닿아 아픔','장식 징이 발에 쓸림','뒷부분 마찰로 피부 벗겨짐']),
  ("퍼자마",10,['밑위가 배겨 불편','허리 조절이 번거로움']),
  ("겸손주방가위",4,['손잡이 돌기가 없어 손이 찝힘','쓸 때마다 손이 아픔'])],
"#퀄리티":[("별(티셔츠)",11,['박음질·만듦새가 아쉬움','어깨 마감 완성도가 떨어짐','실밥이 너덜너덜','"기본 완성도 자체에 문제"']),
  ("퍼자마",7,['홍보 대비 품질이 조악','한 번 입고 개서 보관']),
  ("2024 색안경",4,['마감·완성도가 기대 미달','이음새가 정교하지 못함']),
  ("여름니트",3,['"가격 대비 최악"','어깨 솔기가 터짐','양산 품질 실망'])],
}
KWHEAD={"#사이즈":"치수와 핏이 안 맞는다","#내구성":"오래 못 가고 변형된다","#재질":"소재·촉감이 기대와 다르다","#마감":"마무리 디테일이 거칠다","#사용성":"쓰고 입기 불편하다","#퀄리티":"전반적 완성도가 아쉽다"}
KWNOTE={
"#사이즈":"사이즈는 수빈과 무관하게 <b>전 제품군 통틀어 1위</b>(231건) 불만이다. 신발·안경처럼 <b>착용해 봐야 아는 품목</b>에 집중된다. 구두는 \"평소보다 크게 나온다\"가 일관돼 표기 기준만 내려도 해결되고, 색안경은 얼굴 평수 편차가 커 실측·핏 가이드가 답이다.",
"#내구성":"수빈(전체의 62%)을 빼면 66건. 퍼자마·발옷·별의 <b>'첫 세탁 직후' 변형</b>이 공통점이다. 출고 전 세탁 테스트로 걸러낼 수 있는 결함이며, 구두에선 \"하루 만에 앞 가죽이 터졌다\"는 사례도 있다.",
"#재질":"수빈 제외 83건. <b>'딱딱함'과 '까끌거림' 두 갈래</b>다. 지갑·구두는 가죽이 단단해 사용을 방해하고, 여름니트는 두껍고 까칠해 계절감을 해친다. 소재 불량이 아니라 <b>'그 제품에 맞는 소재인가'</b>의 문제다.",
"#마감":"수빈 제외 100건. 무게중심이 <b>'별(티셔츠)'</b>로 쏠린다. 오버록 노출·거친 이음새가 \"이 가격에?\"라는 실망을 부른다. <b>검수 강화만으로</b> 막을 수 있어 비용 대비 효과가 가장 크다.",
"#사용성":"수빈 제외 77건. 핵심은 <b>'소재 경직성'</b>이다. 지갑은 딱딱해 여닫기·수납을 방해하고, 구두는 단단한 가죽이 뼈에 닿는다. 주방가위마저 손잡이 설계로 손이 아프다. <b>쓰기 불편하면 재구매로 안 이어진다.</b>",
"#퀄리티":"수빈 제외 42건. 1위는 <b>별(티셔츠)</b>. 봉제·완성도 불만이 누적돼 \"다신 안 산다\"로 이어진다. 개별 수정이 아니라 <b>완성도 기준 자체</b>를 다시 세워야 풀린다.",
}
KWQUOTE={
"#사이즈":("구두·운동화 모두 275를 신어서 275를 주문했는데 신어보니 크네요. 270으로 교환 가능할까요?","겸손구두 후기"),
"#내구성":("여자 구두가 하루 만에 앞 가죽이 뛰어나오네요. 겸손 옷도 안주머니가 하루 만에 터졌습니다.","겸손구두 후기"),
"#재질":("제품이 너무 딱딱하고 빡빡해서 사용할 수가 없어요. 커버를 닫고 열기가 어려울 정도로…","겸손지갑 후기"),
"#마감":("가격에 비해 봉제가 너무 싸구려예요. 넥라인·암홀 오버록이 그대로 노출돼 있네요.","별(티셔츠) 후기"),
"#사용성":("가죽이 너무 딱딱해 안쪽 뼈가 닿아 신을 수가 없어요. 엄마·친구들 다 신겨봐도 다들 뼈가 닿아서…","겸손구두 후기"),
"#퀄리티":("기본적인 제품 완성도 자체에 문제가 있어요. 단순히 '기대와 달랐다' 수준이 아니에요.","별(티셔츠) 후기"),
}

S=[]
# 1 표지
S.append(f"""<section class="slide cover">
  <div class="cv-tag">REVIEW INTELLIGENCE REPORT</div>
  <h1 class="cv-title">겸손몰 고객 후기<br><span class="gold">감성·키워드 심층 분석</span></h1>
  <div class="cv-sub">상품 사용후기 {TOTAL:,}건의 정성·정량 분석 보고서</div>
  <div class="cv-meta"><div><span>분석 대상</span><b>{TOTAL:,}건</b></div><div><span>수집 기간</span><b>{date_from} ~ {date_to}</b></div><div><span>발행일</span><b>{TODAY}</b></div></div>
</section>""")

# 2 개요
S.append(f"""<section class="slide"><div class="sno">01</div><h2>분석 개요와 방법</h2>
  <div class="cols">
    <p>본 보고서는 겸손몰 '상품 사용후기' <b>{TOTAL:,}건</b>({date_from}~{date_to})을 AI로 분류·태깅해 집계·해석한 것이다. 별점의 이분법을 넘어, 한 후기 안의 여러 의견을 <b>의미 단위로 분리</b>해 카테고리와 키워드를 부여했다. "디자인은 예쁜데 사이즈가 작다"는 '긍정·#디자인'과 '부정·#사이즈'로 나뉜다.</p>
    <p>카테고리는 <b>6종</b>(긍정·부정·중립·양도/거래·교환/반품·배송), 키워드는 <b>14종</b>(#사이즈 #재질 #마감 #디자인 #사용성 등)으로 세분했다. 키워드 집계는 성격이 다른 <b>만년필·문구류를 제외</b>한 수치이며, 분석 내내 반복 확인된 사실 하나 — <b>'수빈'(수건·가운)이 부정 평가의 큰 몫을 단독으로 차지</b>한다는 점을 미리 밝혀 둔다.</p>
  </div>
</section>""")

# 3 핵심요약
S.append(f"""<section class="slide"><div class="sno">02</div><h2>핵심 요약</h2>
  <div class="keygrid">
    <div class="key"><span class="kn">1</span><div><b>전반적으로 호의적</b> — 긍정({POS:,})이 부정({NEG:,})의 약 {POS/NEG:.1f}배. 기본 신뢰는 견고하다.</div></div>
    <div class="key"><span class="kn">2</span><div><b>만족 = 디자인·소재·가벼움</b> — #디자인({pos_ex['#디자인']})·#재질({pos_ex['#재질']})·#무게감({pos_ex['#무게감']})에 반응.</div></div>
    <div class="key"><span class="kn">3</span><div><b>불만 = 사이즈·내구성</b> — 사이즈는 구두·색안경, 내구성은 거의 수빈에 집중.</div></div>
    <div class="key"><span class="kn">4</span><div><b>수빈은 단일 이슈</b> — 내구성·재질·마감·퀄리티 1위가 모두 수빈. 빼면 별·구두·지갑이 과제.</div></div>
    <div class="key"><span class="kn">5</span><div><b>사이즈 정보가 최고의 투자</b> — 교환·양도의 공통 뿌리. 실측표 하나가 만족·비용을 동시 개선.</div></div>
  </div>
</section>""")

# 4 분포
S.append(f"""<section class="slide"><div class="sno">03</div><h2>전체 반응 분포</h2>
  <div class="split">
    <div class="donutwrap">{donut([(c,cat[c],CC[c]) for c in CATS6])}</div>
    <div class="rtext">
      {statrow([(f"{POS:,}","긍정",CC['긍정'],f"{POS/SUM*100:.0f}%"),(f"{NEG:,}","부정",CC['부정'],f"{NEG/SUM*100:.0f}%"),(f"{POS/NEG:.1f}배","긍/부",GOLD,"만족 우위")])}
      <p>긍정이 부정의 두 배를 넘지만, 주목할 건 <b>그 밖의 신호</b>다. '양도/거래'({cat['양도/거래']})와 '교환/반품'({cat['교환/반품']})이 각각 300건을 넘는데, 이면엔 \"내게 안 맞아서\"라는 <b>사이즈 사유</b>가 깔려 있다. 동시에 활발한 양도 시장은 제품 수요와 리세일 가치의 방증이기도 하다.</p>
      <p>'배송관련불편'({cat['배송관련불편']})은 비중은 낮지만 대부분 <b>'지연'</b> 호소다. 품질과 무관하나 기다림에 대한 커뮤니케이션이 체감 만족을 좌우한다.</p>
    </div>
  </div>
</section>""")

# 5 긍정
pm=pos_ex.most_common(1)[0][1]
S.append(f"""<section class="slide"><div class="sno">04</div><h2>만족의 동력 — 고객은 무엇에 반응하는가</h2>
  <div class="split">
    <div>{hbars([(t,n) for t,n in pos_ex.most_common(6)],pm,CC['긍정'])}</div>
    <div class="rtext">
      <p><b>#디자인({pos_ex['#디자인']})</b>이 압도적 1순위. "예쁘다"보다 <b>"오래 기다린 보람", "영상과 똑같다"</b>처럼 기대와 실물이 일치했을 때의 만족이 두드러진다. 긴 대기가 오히려 만족을 증폭한다.</p>
      <p><b>#재질·#퀄리티</b>는 손에 닿는 경험(촉감·고급감), <b>#색상</b>은 "화면과 일치", <b>#무게감({pos_ex['#무게감']})</b>은 한 방향 — <b>"생각보다 가볍다"</b>. 가벼움은 가방·우산·안경에서 일관된 강점이다. #사용성 긍정의 상당수는 만년필 필기감으로, 11장에서 따로 다룬다.</p>
    </div>
  </div>
</section>""")

# 6 만족 제품군
S.append(f"""<section class="slide"><div class="sno">05</div><h2>가장 사랑받는 제품군</h2>
  {gaugelist([("2024 겸손색안경",208,29),("겸손주방가위",69,11),("발옷",141,24),("겸손넥타이·넥카프",89,20),("해바라기",39,5)])}
  <p class="undertext">공통점은 <b>'기능·외관이 명확하고 사이즈 변수가 작다'</b>는 것. 발·몸에 꼭 맞을 필요가 없어 사이즈 실패가 적고, 디자인·소재 만족이 그대로 평가에 반영된다. 반대로 뒤에서 볼 불만 제품군은 대부분 <b>'사이즈·착용' 변수가 큰 품목</b>이다.</p>
</section>""")

# 7 불만 개괄
nm=neg_ex.most_common(1)[0][1]
S.append(f"""<section class="slide"><div class="sno">06</div><h2>불만의 지형 — 어디서 무너지는가</h2>
  <div class="split">
    <div>{hbars([(t,n) for t,n in neg_ex.most_common(6)],nm,CC['부정'])}</div>
    <div class="rtext">
      <p>부정은 <b>#사이즈({neg_ex['#사이즈']})·#내구성({neg_ex['#내구성']})</b>의 양강이다. 그런데 함정이 있다 — 내구성·재질·마감·퀄리티의 큰 몫이 <b>'수빈' 한 제품</b>에서 나온다(내구성은 62%).</p>
      <p>그래서 이 보고서는 <b>다음 7~12장에서 수빈을 제외</b>하고 "수빈 말고 무엇이 문제인가"를 보고, <b>수빈은 13장에서 따로</b> 집중한다. 떼어놓고 보면 '별·퍼자마·지갑·구두'라는 진짜 과제가 드러난다.</p>
    </div>
  </div>
</section>""")

# 8~13 키워드 (가로 2단: 좌 카드, 우 건수+서술+인용)
for i,tag in enumerate(["#사이즈","#내구성","#재질","#마감","#사용성","#퀄리티"],7):
    rows=KW[tag]; cmax=rows[0][1]
    cards=""
    for j,(g,n,faults) in enumerate(rows):
        lis="".join(f"<li>{f}</li>" for f in faults[:3])
        top=" top" if j==0 else ""
        flag='<span class="flag">최다</span>' if j==0 else ''
        w=int(n/cmax*100); bc=GOLD if j==0 else CC["부정"]
        cards+=f'<div class="pcard{top}"><div class="pc-h">{g}{flag}<span class="pc-n">{n}건</span></div><div class="pc-bar"><div class="pc-fill" style="width:{w}%;background:{bc}"></div></div><ul>{lis}</ul></div>'
    q,src=KWQUOTE[tag]
    badge='' if tag=="#사이즈" else '<span class="extag">수빈 제외</span>'
    S.append(f"""<section class="slide"><div class="sno">{i:02d}</div>
      <h2>{tag} — {KWHEAD[tag]}{badge}</h2>
      <div class="kwsplit">
        <div class="kwleft"><div class="pgrid2">{cards}</div></div>
        <div class="kwright">
          <div class="bigstat"><div class="bs-n" style="color:{CC['부정']}">{KWTOTAL[tag]}<span>건</span></div><div class="bs-l">수빈·문구 제외 부정 건수</div></div>
          <p class="note">{KWNOTE[tag]}</p>
          <div class="quote">“{q}”<span class="qsrc">— {src}</span></div>
        </div>
      </div>
    </section>""")

# 14 수빈
S.append(f"""<section class="slide"><div class="sno">13</div><h2>집중 분석 — '수빈'이라는 단일 변수</h2>
  {statrow([("73%","제품군 부정 비율",CC['부정'],"긍 88·부 234"),("4관왕","내구성·재질·마감·퀄리티 1위",GOLD,"모든 핵심 불만"),("62%","#내구성 중 수빈 비중",CC['부정'],"150 / 240건")])}
  <div class="cols">
    <p>수빈은 부정 #내구성 150·#재질 77·#마감 35·#퀄리티 67에서 모두 <b>제품군 1위</b>다. 불만 양상은 한 곳으로 수렴한다 — <b>'세탁하면 보풀이 일고 먼지가 난다'</b>. "세탁할수록 악화", "오래된 수건 같다", "발걸레로도 좀…"이라는 표현에, 받자마자 석유 냄새 호소까지 반복된다.</p>
    <p>이는 관리 부주의가 아닌 <b>원단·원사 자체의 문제</b>다. 수빈은 '제품 전반의 약점'이 아니라 <b>독립적으로 분리해 다룰 단일 결함</b>. 소재만 교체해도 내구성은 절반 이하, 재질·퀄리티도 큰 폭으로 준다 — <b class="gold">가장 적은 노력으로 가장 큰 개선</b>이 가능한 지점이다.</p>
  </div>
</section>""")

# 15 문구
mp=collections.Counter(); mc=collections.Counter(); mn_n=0
for r in revs:
    if not is_mun(r): continue
    mn_n+=1
    for s in (r.get("classification") or {}).get("segments") or []:
        c=cat_of(s)
        if c in CATS6: mc[c]+=1
        if c=="긍정":
            for h in s.get("hashtags",[]): mp[h]+=1
mpm=mp.most_common(1)[0][1]
S.append(f"""<section class="slide"><div class="sno">14</div><h2>문구 제품군 — 다른 결의 만족</h2>
  <div class="split">
    <div>{hbars([(t.replace('#',''),n) for t,n in mp.most_common(5)],mpm,CC['긍정'])}</div>
    <div class="rtext">
      <p>베개·세종·사각·파인라이너 등 <b>{mn_n}건</b> · 만족 <b>{mc['긍정']/(mc['긍정']+mc['부정'])*100:.0f}%</b>. 긍정 1위는 압도적으로 <b>#사용성 = 필기감</b>이다. "저중심이라 편하다", "박종진 터치"처럼 <b>손으로 쓰는 경험</b>이 핵심 가치다.</p>
      <p>아쉬움은 <b>케이스 마감</b>(천 접착·거친 절삭면)과 잉크·촉 관리 난이도. 본체는 만족스러운데 <b>부속이 발목</b>을 잡는다. '필기감'이라는 확실한 무기에 케이스 마무리만 보완하면 된다.</p>
    </div>
  </div>
</section>""")

# 16 거래운영
S.append(f"""<section class="slide"><div class="sno">15</div><h2>거래·운영 신호 — 교환·양도·배송</h2>
  <div class="ops3">
    <div class="opc"><div class="oph" style="color:{CC['교환/반품']}">교환·반품 {cat['교환/반품']}건</div><ul><li>사이즈 안 맞음("커서/작아서")</li><li>수빈 보풀·세탁 후 변형</li><li>마감·품질 불량(도색·단차)</li><li>색상이 사진과 다름</li></ul></div>
    <div class="opc"><div class="oph" style="color:{CC['양도/거래']}">양도·거래 {cat['양도/거래']}건</div><ul><li><b>색안경 사이즈</b>(54↔57)</li><li>안 어울려서(취향·얼굴형)</li><li>테만·렌즈 등 부분 거래</li><li>중복 구매·득템 양도</li></ul></div>
    <div class="opc"><div class="oph" style="color:{CC['배송관련불편']}">배송 불편 {cat['배송관련불편']}건</div><ul><li><b>지연</b> — "너무 오래 기다림"</li><li>색상·사이즈 누락</li><li>배송완료 표시 후 미수령</li><li>가방 손잡이 직접 조립</li></ul></div>
  </div>
  <p class="undertext">교환·양도 모두 뿌리는 <b>사이즈 적합성</b>, 배송은 <b>지연 커뮤니케이션</b>이 체감 불만을 좌우한다.</p>
</section>""")

# 17 추이
recent=sorted(mon)[-12:]; mmax=max(mon[m] for m in recent)
S.append(f"""<section class="slide"><div class="sno">16</div><h2>후기량의 흐름</h2>
  {hbars([(m,mon[m]) for m in recent],mmax,GOLD)}
  <p class="undertext">2026년 봄(4~5월)에 후기량 정점 — 신상·시즌 구매가 몰린 시기. 후기가 급증하는 달일수록 그 시기 제품 평가가 브랜드 인상을 좌우하므로, <b>출시 직후 집중 모니터링</b>이 필요하다. (최근 달은 집계 진행 중.)</p>
</section>""")

# 18 결론
S.append(f"""<section class="slide"><div class="sno">17</div><h2>결론 & 제언</h2>
  <div class="cc6">
    <div class="ccx"><div class="cch gold">① 즉시 · 수빈 소재</div><p>내구성·재질·마감·퀄리티를 한 몸에 진 단일 제품. 원사 교체 또는 세탁 가이드. 최소 비용·최대 효과.</p></div>
    <div class="ccx"><div class="cch gold">② 구조 · 사이즈 정보</div><p>구두("크게 나옴")·색안경(평수 편차). 실측표·핏 가이드로 교환·양도 동시 감축.</p></div>
    <div class="ccx"><div class="cch gold">③ 디테일 · 마감 검수</div><p>별의 오버록 노출, 색안경 케이스 이음새. 검수 강화만으로 "이 가격에?" 차단.</p></div>
    <div class="ccx"><div class="cch gold">④ 소재 경직성</div><p>지갑·구두의 "딱딱해 불편". 쓰기 불편하면 재구매 안 됨. 유연 소재 옵션 검토.</p></div>
    <div class="ccx"><div class="cch gold">⑤ 강점 강화</div><p>디자인·가벼움·필기감은 확실한 무기. 상세페이지·마케팅에서 적극 부각.</p></div>
    <div class="ccx"><div class="cch gold">⑥ 커뮤니케이션</div><p>배송 지연 자동 안내, 출시 직후 후기 집중 모니터링으로 선제 관리.</p></div>
  </div>
  <p class="endline gold">'수빈'이라는 단일 이슈와 '사이즈·마감'이라는 구조적 과제를 분리해, 각각 다른 방식으로 접근하라.</p>
</section>""")

CSS=f"""<style>{FONTS}
*{{margin:0;padding:0;box-sizing:border-box;}}
@page{{size:1280px 720px;margin:0;}}
body{{font-family:'Paperlogy',sans-serif;background:#0a0a0c;color:#dfe0e6;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
.slide{{width:1280px;height:720px;padding:42px 56px;position:relative;page-break-after:always;overflow:hidden;background:radial-gradient(130% 70% at 85% 0%,#14161b 0%,#0a0a0c 60%);display:flex;flex-direction:column;}}
.gold{{color:{GOLD};}}
.sno{{position:absolute;top:34px;right:50px;font-size:72px;font-weight:900;color:#16181d;line-height:1;}}
h2{{font-size:30px;font-weight:800;color:#fff;letter-spacing:-0.8px;margin-bottom:22px;padding-bottom:14px;border-bottom:2px solid #1f2128;}}
p{{font-size:15.5px;line-height:1.7;color:#c4c6cd;margin-bottom:15px;letter-spacing:-0.2px;}}
p b{{color:#fff;font-weight:700;}} p b.gold{{color:{GOLD};}}
.cover{{justify-content:center;align-items:flex-start;}}
.cv-tag{{font-size:15px;letter-spacing:5px;color:{GOLD};font-weight:600;margin-bottom:24px;}}
.cv-title{{font-size:60px;font-weight:900;color:#fff;line-height:1.12;letter-spacing:-2px;margin-bottom:20px;}}
.cv-sub{{font-size:18px;color:#9498a3;margin-bottom:54px;}}
.cv-meta{{display:flex;gap:52px;border-top:1px solid #26282e;padding-top:28px;}}
.cv-meta span{{display:block;font-size:13px;color:#777a88;letter-spacing:1px;margin-bottom:8px;}}
.cv-meta b{{display:block;font-size:22px;color:#fff;font-weight:700;}}
.cols{{column-count:2;column-gap:44px;flex:1;}}
.cols p{{break-inside:avoid;}}
.split{{display:grid;grid-template-columns:1fr 1fr;gap:40px;flex:1;align-items:center;}}
.rtext p:last-child,.split p:last-child{{margin-bottom:0;}}
.undertext{{margin-top:18px;font-size:15px;}}
/* keygrid */
.keygrid{{display:flex;flex-direction:column;gap:13px;flex:1;justify-content:center;}}
.key{{display:flex;gap:16px;background:#121419;border:1px solid #1f2128;border-radius:12px;padding:16px 22px;align-items:center;}}
.kn{{flex-shrink:0;width:34px;height:34px;border-radius:50%;background:{GOLD};color:#000;font-size:17px;font-weight:900;display:flex;align-items:center;justify-content:center;}}
.key div:last-child{{font-size:16px;line-height:1.55;color:#c4c6cd;}} .key b{{color:#fff;}}
/* donut */
.donutwrap{{display:flex;align-items:center;gap:32px;}}
.donut{{width:220px;height:220px;border-radius:50%;flex-shrink:0;position:relative;}}
.dhole{{position:absolute;inset:48px;background:#0c0d10;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;}}
.dhole b{{font-size:34px;font-weight:900;color:#fff;line-height:1;}} .dhole span{{font-size:13px;color:#777a88;margin-top:4px;}}
.legend{{display:flex;flex-direction:column;gap:9px;}}
.lg{{display:flex;align-items:center;gap:9px;font-size:15px;color:#c4c6cd;}}
.dot{{width:12px;height:12px;border-radius:3px;flex-shrink:0;}} .lg-l{{width:96px;}} .lg b{{color:#fff;width:42px;}} .lg i{{color:#777a88;font-style:normal;font-size:13px;}}
/* stat */
.statrow{{display:flex;gap:14px;margin-bottom:18px;}}
.sc{{flex:1;background:#121419;border:1px solid #1f2128;border-radius:12px;padding:16px;text-align:center;}}
.sc-n{{font-size:36px;font-weight:900;line-height:1;}} .sc-l{{font-size:14px;color:#c4c6cd;margin-top:8px;}} .sc-s{{font-size:12px;color:#777a88;margin-top:3px;}}
/* bars */
.chart{{display:flex;flex-direction:column;gap:12px;}}
.bar-row{{display:flex;align-items:center;gap:12px;}}
.bar-l{{width:104px;text-align:right;font-size:14px;color:#cdcdcd;font-weight:600;flex-shrink:0;}}
.bar-t{{flex:1;height:15px;background:#16181d;border-radius:8px;overflow:hidden;}}
.bar-f{{height:100%;border-radius:8px;}} .bar-v{{width:46px;font-size:15px;font-weight:700;color:#fff;}}
/* gauge */
.gaugelist{{display:flex;flex-direction:column;gap:13px;margin-bottom:10px;}}
.gg-row{{display:flex;align-items:center;gap:16px;}}
.gg-l{{width:210px;font-size:16px;color:#fff;font-weight:600;flex-shrink:0;}}
.gg-bar{{flex:1;height:26px;background:#16181d;border-radius:7px;overflow:hidden;position:relative;}}
.gg-pos{{height:100%;background:linear-gradient(90deg,#3b82f6,{CC['긍정']});border-radius:7px;}}
.gg-pct{{position:absolute;left:14px;top:0;height:26px;display:flex;align-items:center;font-size:15px;font-weight:800;color:#fff;}}
.gg-cnt{{width:110px;font-size:13px;color:#777a88;text-align:right;}}
/* keyword slide */
.extag{{font-size:14px;font-weight:700;color:{GOLD};background:#1a1610;border:1px solid rgba(204,145,102,.4);padding:3px 12px;border-radius:18px;margin-left:12px;vertical-align:middle;}}
.kwsplit{{display:grid;grid-template-columns:1.15fr 1fr;gap:30px;flex:1;}}
.pgrid2{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:11px;height:100%;}}
.pcard{{background:#121419;border:1px solid #1f2128;border-radius:11px;padding:13px 15px;position:relative;display:flex;flex-direction:column;}}
.pcard.top{{border:2px solid {GOLD};background:#1a1610;}}
.pc-h{{display:flex;align-items:baseline;gap:7px;font-size:16px;font-weight:800;color:#fff;margin-bottom:8px;}}
.pc-n{{margin-left:auto;font-size:12px;color:#777a88;font-weight:500;}}
.flag{{background:{GOLD};color:#000;font-size:10px;font-weight:800;padding:1px 8px;border-radius:8px;}}
.pc-bar{{height:5px;background:#0a0a0c;border-radius:4px;overflow:hidden;margin-bottom:9px;}} .pc-fill{{height:100%;border-radius:4px;}}
.pcard ul{{list-style:none;display:flex;flex-direction:column;gap:5px;}}
.pcard li{{font-size:12.5px;color:#bcbfc8;line-height:1.4;padding-left:11px;position:relative;}}
.pcard li:before{{content:'';position:absolute;left:0;top:6px;width:4px;height:4px;border-radius:50%;background:{CC['부정']};}}
.pcard.top li:before{{background:{GOLD};}}
.kwright{{display:flex;flex-direction:column;}}
.bigstat{{background:#1a1610;border:1px solid rgba(204,145,102,.35);border-radius:12px;padding:14px 20px;margin-bottom:14px;display:flex;align-items:center;gap:16px;}}
.bs-n{{font-size:44px;font-weight:900;line-height:1;}} .bs-n span{{font-size:18px;margin-left:3px;}}
.bs-l{{font-size:14px;color:#c4c6cd;line-height:1.4;}}
.note{{background:#101216;border-left:3px solid {GOLD};border-radius:0 10px 10px 0;padding:15px 18px;font-size:14.5px;line-height:1.65;color:#c4c6cd;margin-bottom:14px;flex:1;}}
.note b{{color:#fff;}}
.quote{{background:#0e1014;border:1px solid #1f2128;border-radius:10px;padding:14px 18px;font-size:14px;line-height:1.55;color:#d4d6dd;font-style:italic;}}
.qsrc{{display:block;font-style:normal;font-size:12px;color:#777a88;margin-top:7px;text-align:right;}}
/* ops */
.ops3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;flex:1;}}
.opc{{background:#121419;border:1px solid #1f2128;border-radius:12px;padding:18px 20px;}}
.oph{{font-size:17px;font-weight:800;margin-bottom:13px;}}
.opc ul{{list-style:none;display:flex;flex-direction:column;gap:9px;}}
.opc li{{font-size:14px;color:#bcbfc8;line-height:1.4;padding-left:12px;position:relative;}}
.opc li:before{{content:'';position:absolute;left:0;top:7px;width:5px;height:5px;border-radius:50%;background:{GOLD};}} .opc li b{{color:#fff;}}
/* conclusion */
.cc6{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;flex:1;}}
.ccx{{background:#121419;border:1px solid #1f2128;border-radius:11px;padding:16px 18px;}}
.cch{{font-size:16px;font-weight:800;margin-bottom:9px;}}
.ccx p{{font-size:13.5px;line-height:1.5;color:#bcbfc8;margin:0;}}
.endline{{font-size:17px;font-weight:700;text-align:center;background:#101216;border:1px solid #26282e;border-radius:12px;padding:16px;margin-top:14px;}}
</style>"""
HTML=f"<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>{CSS}</head><body>{''.join(S)}</body></html>"
open("_report.html","w",encoding="utf-8").write(HTML)
print(f"HTML: {len(S)}슬라이드")
out=f"겸손몰_후기분석_report_{date.today().strftime('%Y%m%d')}.pdf"
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome","--headless","--disable-gpu","--no-pdf-header-footer",f"--print-to-pdf={os.path.join(ROOT,out)}","file://"+os.path.join(ROOT,"_report.html")],capture_output=True)
print(out)
