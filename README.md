# 🔮 AI 관상가

얼굴 사진을 올리면 OpenAI 이미지 분석 모델이 전통 관상학 관점에서 관상을 풀이해 주는 Streamlit 웹앱입니다.

- 사진 업로드 또는 카메라 촬영
- 첫인상, 부위별 풀이, 성격과 기질, 재물운·직업운·대인운·연애운, 종합 총평을 섹션별로 표시
- 얼굴이 없거나 여러 명이 있는 사진은 다른 사진을 요청
- 사진은 메모리에서만 처리하며 저장하지 않음

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`.env.example`을 복사해 `.env`를 만들고 키를 넣습니다.

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

```bash
streamlit run app.py
```

브라우저에서 http://localhost:8501 로 접속합니다.

`OPENAI_MODEL`은 생략하면 `gpt-4o`를 사용하며, 이미지 입력을 지원하는 모델이어야 합니다.

## Streamlit Cloud 배포

1. 이 저장소를 GitHub에 push합니다. `.env`는 `.gitignore`에 들어 있어 올라가지 않습니다.
2. [share.streamlit.io](https://share.streamlit.io)에서 **Create app**을 누르고 저장소, 브랜치, 메인 파일 `app.py`를 선택합니다.
3. **Advanced settings > Secrets**(배포 후에는 앱 메뉴 **Settings > Secrets**)에 다음을 입력합니다.
   ```toml
   OPENAI_API_KEY = "sk-..."
   OPENAI_MODEL = "gpt-4o"
   ```
4. 배포가 끝나면 앱 URL에서 동작을 확인합니다.

앱은 Streamlit Secrets를 먼저 읽고, 없으면 `.env`를 읽습니다.

## 주의사항

- 이 앱의 관상 풀이는 엔터테인먼트용이며 과학적 근거가 없습니다.
- 업로드한 사진은 분석을 위해 OpenAI API로 전송됩니다. 다른 사람의 사진은 본인 동의를 받은 경우에만 사용하세요.
- 분석 1회마다 OpenAI API 사용 요금이 발생합니다.
- API 키를 코드나 GitHub에 올리지 마세요.
