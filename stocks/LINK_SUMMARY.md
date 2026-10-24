# YouTube 링크 정리 절차 (새 세션용)

사용자가 YouTube 링크를 주며 "정리해줘"라고 하면 이 순서대로 한다. 결과는
'내 주식 노트' 아티팩트(https://claude.ai/artifact/7EjgjW1bP46gdXJK9xqa4v)의
'영상 정리' 탭에 들어간다. 데이터는 ArtifactData 도구(url=위 아티팩트,
collection "data/users/me")로 읽고 쓴다. 저장소 커밋·푸시는 하지 않는다.

1. 준비: `pip install -q yt-dlp` (이미 있으면 생략). 이 브랜치(claude/dreamy-keller-c66uw9)의 `stocks/` 폴더에서 작업.
2. 영상 정보와 자막 받기 (VIDEO_ID 는 링크의 v= 값):
   ```
   python3 -c "
   import sys,json;sys.path.insert(0,'stocks');import youtube_new as y
   m=y.meta('VIDEO_ID');m['transcript']=y.transcript('VIDEO_ID','yt');json.dump(m,open('video.json','w'),ensure_ascii=False)
   print({k:v for k,v in m.items() if k not in('transcript','description')},len(m['transcript']))"
   ```
   자막이 비어 있으면(방금 끝난 라이브 등) 정리하지 말고 "자막이 아직 없어요, 몇 시간 뒤 다시 요청해 주세요"라고 답한다.
3. 자막은 1만 자 단위 파일로 나눠 끝까지 읽는다.
4. ArtifactData get doc_id "portfolio" — 언급 종목이 보유 종목이면 표시용(쓰지 않음).
5. ArtifactData get doc_id "videos" → items 맨 앞에 추가(같은 id 있으면 건너뜀, 기존 항목 수정 금지), set + if_version.
   형식: {id,url,title,channel(예 "MBN골드 · 진행자", "토마토TV", "이종복TV"),date:"YYYY-MM-DD"(KST),duration:"N분"(라이브면 "N분 (라이브)"),added(오늘),
   oneLine(핵심 한 줄),points(4~6개: 시장 전망·섹터·일정),stocks([{name,view,mine?}] — 진행자 의견·언급 가격;
   보유면 mine:"보유 N주 · 평단 X원 · 현재 Y원 (±z%)"),rules(매매 원칙 3~5개),caution(자동 자막 기반·유료방 홍보·검증되지 않은 수익 주장)}.
   자막이 불분명한 숫자는 빼고, 잘못 들린 종목명은 실제 종목명으로 고치되 확실하지 않으면 "(추정)" 표시. 날짜·요일은 달력으로 확인.
   진행자 의견으로 표현하고 투자 권유로 쓰지 않는다.
6. 한국어로 짧게 답한다: 제목, 한 줄 요약, 핵심 3~4개, 보유 종목 언급 여부.
