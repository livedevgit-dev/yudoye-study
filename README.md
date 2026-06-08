# 유도예 학습 앱 (Streamlit)

초등학생용 사칙연산 연습 앱입니다. **문제 출제 + 채점**만 하는 가벼운 단일 파일 Streamlit 앱입니다.

- 단순 연산 / 서술식(문장제) 두 가지 문제 형태
- 사칙연산(＋ － × ÷), 최대 자릿수 1~4
- **주관식(숫자 입력)만** 사용 (객관식 없음)
- 저장/DB 없음 — 점수는 현재 접속 세션 동안에만 유지됩니다

## 파일 구조

```
streamlit_app.py            # 앱 본체 (출제·채점·UI)
requirements.txt            # 의존성 (streamlit)
data/word_templates.json    # 서술식 문장 템플릿 (80종)
```

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

브라우저에서 `http://localhost:8501` 이 자동으로 열립니다.

## Streamlit Community Cloud 배포

1. 이 폴더를 GitHub 저장소에 push 합니다.

```bash
git init
git add .
git commit -m "유도예 학습 앱 (Streamlit)"
git branch -M main
git remote add origin https://github.com/<사용자>/<저장소>.git
git push -u origin main
```

2. [share.streamlit.io](https://share.streamlit.io) 에 GitHub 계정으로 로그인합니다.
3. **New app** → 저장소·브랜치(main) 선택 → Main file path 를 `streamlit_app.py` 로 지정 → Deploy.

> 참고: Streamlit Cloud는 파일시스템이 휘발성이라 점수·이력을 영구 저장하지 않습니다.
> 이 앱은 애초에 저장 기능이 없으므로 그대로 동작합니다.
