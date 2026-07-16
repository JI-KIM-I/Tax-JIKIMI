# RAG sources 폴더

여기에 국세청 안내자료/법령 조문/연금 가이드 등을 `.txt`로 저장하세요.

권장 메타데이터 형식:

```txt
title: 금융소득종합과세 안내
category: 금융소득
source: 국세청
date: 2026-01
---
본문 내용...
```

파일을 추가하거나 수정한 뒤에는 backend 폴더에서 아래 명령어를 실행하세요.

```bash
python rag/build_index.py
```
