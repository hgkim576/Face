"""AI 관상 분석 앱."""

import base64
import hashlib
import io
import logging
import os
import random
import time

import openai
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gwansang")

# ---------- 상수 ----------
DEFAULT_MODEL = "gpt-4o"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_PIXELS = 40_000_000  # 약 4000만 화소. 작은 파일이 거대한 이미지로 풀리는 것을 막는다
MAX_IMAGE_SIDE = 1024
JPEG_QUALITY = 90
MAX_COMPLETION_TOKENS = 1500
API_TIMEOUT_SECONDS = 30
API_MAX_RETRIES = 1
JOB_WAIT_LIMIT_SECONDS = (API_TIMEOUT_SECONDS + 5) * (API_MAX_RETRIES + 1)
MIN_KNOWN_SECTIONS = 3
SHORT_ANSWER_CHARS = 300  # 제목 없이 이보다 짧은 답은 거절/실패로 본다

NO_FACE = "[NO_FACE]"
MULTI_FACE = "[MULTI_FACE]"

SYSTEM_PROMPT = f"""당신은 전통 관상학에 밝은 친절하고 유쾌한 관상가입니다.
사용자가 보낸 사진 속 얼굴을 보고 재미로 읽는 관상 풀이를 작성합니다.

[사진 확인 규칙]
- 사진에 사람 얼굴이 보이지 않으면 첫 줄에 {NO_FACE} 만 쓰고, 다음 줄에 이유를 한 문장으로 쓰세요.
- 사진에 두 명 이상의 얼굴이 보이면 첫 줄에 {MULTI_FACE} 만 쓰고, 다음 줄에 이유를 한 문장으로 쓰세요.
- 위 두 경우가 아니면 표시 없이 바로 관상 풀이를 작성하세요.

[작성 규칙]
- 전통 관상학 관점에서 이마, 눈썹, 눈, 코, 입, 귀, 턱과 얼굴형을 풀이하세요.
  사진에서 잘 보이지 않는 부위는 보이는 범위에서만 짧게 언급하세요.
- 긍정적이고 유쾌한 톤으로, 단점보다는 장점과 조언 위주로 쓰세요.
- 인종, 성별, 나이를 추정하거나 언급하지 말고, 외모를 평가(잘생김/못생김 등)하거나 비하하는 표현을 쓰지 마세요.
- 인물이 누구인지 식별하거나 추측하지 마세요.
- 한국어 Markdown으로, 아래 다섯 개의 제목을 그대로 순서대로 사용하세요.

## 첫인상 요약
(한두 문장)

## 부위별 관상 풀이
(이마, 눈썹, 눈, 코, 입, 귀, 턱/얼굴형을 각각 목록으로)

## 성격과 기질

## 재물운·직업운·대인운·연애운
(네 가지 운을 각각 목록으로)

## 종합 총평과 한 줄 조언
"""

USER_PROMPT = "이 사진 속 인물의 관상을 봐주세요."

PRIVACY_NOTICE = "사진은 관상 분석을 위해 OpenAI API로 전송되며, 이 앱에는 저장되지 않습니다."
DISCLAIMER = "이 관상 풀이는 엔터테인먼트용이며 과학적 근거가 없습니다."
UPLOAD_SIZE_HINT = "10MB가 넘는 파일은 올라가지 않으며, 파일 이름 옆에 빨간 ! 표시가 나타납니다."
NO_READING_MESSAGE = "관상 풀이를 받지 못했습니다. 얼굴이 잘 보이는 다른 사진으로 다시 시도해 주세요."
TRUNCATED_MESSAGE = "풀이가 길어 마지막 부분이 잘렸을 수 있습니다."


# ---------- UI 상수 ----------
# 결과 섹션: (제목에 들어 있는 키워드, 아이콘)
SECTION_ICONS = [
    ("첫인상", "✨"),
    ("부위", "👁️"),
    ("성격", "🧭"),
    ("운", "🔮"),
    ("총평", "📜"),
]
FORTUNES = [("재물운", "💰"), ("직업운", "💼"), ("대인운", "🤝"), ("연애운", "💕")]

LOADING_MESSAGES = [
    "관상가가 이마를 살펴보는 중...",
    "눈썹의 기운을 읽는 중...",
    "콧대에 깃든 재물운을 헤아리는 중...",
    "입꼬리에 담긴 복을 세어 보는 중...",
    "턱선에서 말년운을 짚어 보는 중...",
]

# 정적 CSS만 사용한다 (모델 응답·사용자 입력은 절대 HTML로 출력하지 않음).
# 색은 라이트/다크 양쪽에서 읽히도록 반투명 주홍과 inherit만 쓴다.
CUSTOM_CSS = """
<style>
.block-container { max-width: 720px; padding-top: 2.5rem; }
.hero { text-align: center; margin-bottom: 1.25rem; }
.hero .seal {
  display: inline-flex; align-items: center; justify-content: center;
  width: 3.5rem; height: 3.5rem; border-radius: 0.6rem;
  background: #B23A2E; color: #FFF8EE; font-size: 2rem; font-weight: 700;
  font-family: "Noto Serif KR", serif; transform: rotate(-4deg);
  box-shadow: 0 2px 8px rgba(178, 58, 46, 0.35); margin-bottom: 0.75rem;
}
.hero .title {
  font-family: "Noto Serif KR", serif; font-size: 2.4rem; font-weight: 700;
  line-height: 1.2; margin: 0;
}
.hero .subtitle { font-size: 1.1rem; font-weight: 500; opacity: 0.85; margin: 0.4rem 0 0.2rem; }
.hero .desc { font-size: 0.92rem; opacity: 0.65; margin: 0; }
[data-testid="stImage"] { display: flex; justify-content: center; }
[data-testid="stImage"] img {
  max-width: min(100%, 360px) !important; height: auto !important; border-radius: 0.75rem;
  display: block; margin: 0 auto;
}
[data-testid="stImage"] > div, [data-testid="stImageContainer"] { width: 100% !important; text-align: center; }
[data-testid="stImageCaption"] { text-align: center; }
[data-testid="stBaseButton-primary"] { min-height: 3.2rem; font-size: 1.1rem; font-weight: 700; }
.footer { text-align: center; font-size: 0.78rem; opacity: 0.55; margin-top: 2.5rem; }
/* 한국어가 단어 중간에서 줄바꿈되지 않도록 */
.hero, .hero p,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] :is(p, li, h3, h4),
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  word-break: keep-all; overflow-wrap: break-word;
}
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 3.5rem; }
  .hero .title { font-size: 1.9rem; }
  [data-testid="stMarkdownContainer"] h3 { font-size: 1.4rem; }
  [data-testid="stMarkdownContainer"] h4 { font-size: 1.15rem; }
}
</style>
"""

HERO_HTML = """
<div class="hero">
  <div class="seal">相</div>
  <p class="title">AI 관상가</p>
  <p class="subtitle">사진 한 장으로 보는 나의 관상</p>
  <p class="desc">얼굴 사진을 올리면 관상가가 이마부터 턱까지 찬찬히 풀이해 드립니다.</p>
</div>
"""

FOOTER_HTML = '<div class="footer">재미로 보는 AI 관상 · Powered by OpenAI</div>'


class ImageValidationError(Exception):
    """사용자에게 그대로 보여줄 수 있는 이미지 검증 오류."""


# ---------- 설정 ----------
def get_config(key: str, default: str | None = None) -> str | None:
    """st.secrets를 먼저 확인하고, 없으면 .env(os.getenv) 값을 사용한다."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # secrets.toml이 없으면 st.secrets 접근 시 예외가 난다 (로컬 환경)
        pass
    return os.getenv(key, default)


# ---------- 이미지 ----------
TOO_MANY_PIXELS_MESSAGE = "사진 해상도가 너무 큽니다. 4000만 화소 이하의 사진을 올려 주세요."


def prepare_image(file_bytes: bytes) -> bytes:
    """이미지를 검증하고 회전 보정, RGB 변환, 리사이즈 후 JPEG 바이트로 돌려준다.

    모든 처리는 메모리에서만 하며 디스크에 저장하지 않는다.
    """
    if len(file_bytes) > MAX_FILE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        raise ImageValidationError(f"파일이 너무 큽니다 ({size_mb:.1f}MB). 10MB 이하의 사진을 올려 주세요.")

    try:
        # Image.open은 헤더만 읽으므로, 픽셀을 풀기 전에 해상도를 먼저 검사할 수 있다
        with Image.open(io.BytesIO(file_bytes)) as img:
            if img.width * img.height > MAX_PIXELS:
                raise ImageValidationError(TOO_MANY_PIXELS_MESSAGE)
            # JPEG는 축소된 크기로 바로 디코딩해 메모리를 아낀다 (다른 형식에서는 무시됨)
            img.draft("RGB", (MAX_IMAGE_SIDE * 2, MAX_IMAGE_SIDE * 2))
            img.load()  # 잘린/손상된 파일을 여기서 걸러낸다
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue()
    except ImageValidationError:
        raise
    except Image.DecompressionBombError as exc:
        logger.warning("해상도가 너무 큰 이미지: %s", exc)
        raise ImageValidationError(TOO_MANY_PIXELS_MESSAGE) from exc
    except Exception as exc:
        logger.warning("이미지 열기 실패: %s", exc)
        raise ImageValidationError("이미지를 열 수 없습니다. 다른 사진 파일을 올려 주세요.") from exc


def to_data_url(jpeg_bytes: bytes) -> str:
    """JPEG 바이트를 OpenAI image_url용 base64 data URL로 변환한다."""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


# ---------- OpenAI ----------
def analyze_face(api_key: str, model: str, image_data_url: str) -> tuple[str, bool, bool]:
    """OpenAI 비전 모델에 이미지를 보내 (응답 텍스트, 거절 여부, 잘림 여부)를 받는다."""
    client = OpenAI(api_key=api_key, timeout=API_TIMEOUT_SECONDS, max_retries=API_MAX_RETRIES)
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    )
    choice = response.choices[0]
    refused = bool(getattr(choice.message, "refusal", None))
    truncated = choice.finish_reason == "length"
    if refused:
        logger.warning("모델이 요청을 거절했습니다.")
    if truncated:
        logger.warning("응답이 max_completion_tokens에서 잘렸습니다.")
    return (choice.message.content or "").strip(), refused, truncated


def count_known_sections(text: str) -> int:
    return sum(1 for title, _ in split_sections(text) if title and section_icon(title))


def classify_result(text: str, refused: bool = False, truncated: bool = False) -> dict:
    """모델 응답을 결과 종류(ok / no_face / multi_face / error)로 분류한다."""
    if refused or not text:
        return {"kind": "error", "text": NO_READING_MESSAGE}

    first_line, _, rest = text.partition("\n")
    if NO_FACE in first_line:
        return {"kind": "no_face", "text": rest.strip()}
    if MULTI_FACE in first_line:
        return {"kind": "multi_face", "text": rest.strip()}

    # 정해진 제목이 거의 없고 짧은 답은 "분석할 수 없습니다" 같은 거절로 본다
    if count_known_sections(text) < MIN_KNOWN_SECTIONS and len(text) < SHORT_ANSWER_CHARS:
        logger.warning("관상 풀이 형식이 아닌 짧은 응답: %r", text[:100])
        return {"kind": "error", "text": NO_READING_MESSAGE}
    return {"kind": "ok", "text": text, "truncated": truncated}


def run_analysis(api_key: str, model: str, jpeg_bytes: bytes) -> dict:
    """분석을 실행하고 예외를 사용자용 메시지로 바꿔 결과 dict로 돌려준다."""
    try:
        text, refused, truncated = analyze_face(api_key, model, to_data_url(jpeg_bytes))
        return classify_result(text, refused, truncated)
    except openai.AuthenticationError:
        logger.exception("OpenAI 인증 실패")
        msg = "API 키가 올바르지 않습니다. OPENAI_API_KEY 설정을 확인해 주세요."
    except openai.RateLimitError:
        logger.exception("OpenAI 요청 한도 초과")
        msg = "요청이 많거나 사용 한도를 넘었습니다. 잠시 후 다시 시도해 주세요."
    except openai.BadRequestError:
        logger.exception("OpenAI 잘못된 요청")
        msg = "요청을 처리할 수 없습니다. 다른 사진으로 시도하거나 OPENAI_MODEL이 이미지 분석을 지원하는지 확인해 주세요."
    except openai.APITimeoutError:
        logger.exception("OpenAI 응답 시간 초과")
        msg = "응답이 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요."
    except openai.APIConnectionError:
        logger.exception("OpenAI 연결 실패")
        msg = "OpenAI 서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도해 주세요."
    except openai.APIError:
        logger.exception("OpenAI API 오류")
        msg = "관상 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    except Exception:
        logger.exception("알 수 없는 오류")
        msg = "알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    return {"kind": "error", "text": msg}


# ---------- 상태 ----------
# session_state 키
#   uploader_key  : 입력 위젯 key 접미사. 올리면 업로더/카메라가 비워진다
#   image_id      : 지금 화면에 있는 사진의 해시
#   result        : 그 사진의 분석 결과 dict (없으면 None)
#   job           : 진행 중인 분석 {"image_id", "started"} (없으면 None). 중복 호출 방지용 잠금
#   active_source : 업로드와 카메라 사진이 모두 있을 때 마지막에 바뀐 쪽 ("upload" / "camera")
def init_state() -> None:
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("image_id", None)
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("job", None)
    st.session_state.setdefault("active_source", "upload")


def reset_all() -> None:
    """'다시 보기': 결과를 지우고 업로더와 카메라를 비운다."""
    st.session_state.uploader_key += 1
    st.session_state.image_id = None
    st.session_state.result = None


def set_active_source(source: str) -> None:
    st.session_state.active_source = source


def request_analysis(image_id: str) -> None:
    """'관상 보기' 클릭 콜백. 진행 중인 분석이나 결과가 있으면 무시해 중복 호출을 막는다."""
    result = st.session_state.result
    if st.session_state.job is not None:
        return
    if result is not None and result["kind"] != "error":
        return
    st.session_state.job = {"image_id": image_id, "started": False}


def run_job(api_key: str, model: str, image_id: str, jpeg_bytes: bytes) -> None:
    """잠금(job)을 잡은 실행만 OpenAI를 호출한다. 끝나면 잠금을 풀고 화면을 다시 그린다."""
    try:
        with st.spinner(random.choice(LOADING_MESSAGES)):
            result = run_analysis(api_key, model, jpeg_bytes)
        # 분석 중에 사진이 바뀌었으면 이전 사진의 결과는 버린다
        if st.session_state.image_id == image_id:
            st.session_state.result = result
    finally:
        st.session_state.job = None
    st.rerun()


def wait_for_job() -> None:
    """다른 실행이 분석 중이면 새로 호출하지 않고 끝날 때까지 기다린 뒤 다시 그린다."""
    deadline = time.monotonic() + JOB_WAIT_LIMIT_SECONDS
    with st.spinner(random.choice(LOADING_MESSAGES)):
        while st.session_state.job is not None and time.monotonic() < deadline:
            time.sleep(0.3)
    if st.session_state.job is not None:
        logger.warning("분석 잠금이 제한 시간 안에 풀리지 않아 해제합니다.")
        st.session_state.job = None
    st.rerun()


# ---------- UI ----------
def show_missing_key_help() -> None:
    st.error("OPENAI_API_KEY가 설정되지 않아 관상을 볼 수 없습니다.")
    st.markdown(
        """
**로컬 실행**: 프로젝트 폴더의 `.env` 파일에 다음을 추가하세요.
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

**Streamlit Cloud**: 앱 설정 > Secrets에 다음을 등록하세요.
```toml
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "gpt-4o"
```
"""
    )


def split_sections(text: str) -> list[tuple[str, str]]:
    """'## 제목' 기준으로 응답을 (제목, 본문) 목록으로 나눈다. 제목 앞의 글은 제목 ''으로 둔다."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    return [(title, "\n".join(body).strip()) for title, body in sections if title or "\n".join(body).strip()]


def section_icon(title: str) -> str | None:
    for keyword, icon in SECTION_ICONS:
        if keyword in title:
            return icon
    return None


def split_fortunes(body: str) -> dict[str, str]:
    """운세 섹션의 목록 항목에서 재물운/직업운/대인운/연애운 내용을 뽑는다."""
    found: dict[str, str] = {}
    for line in body.splitlines():
        item = line.strip()
        if not item.startswith(("-", "*")):
            continue
        item = item.lstrip("-* ").strip()
        for name, _ in FORTUNES:
            if name in item[: len(name) + 6] and name not in found:
                # "**재물운**: 내용" / "재물운 - 내용" 형태에서 이름 부분을 떼어낸다
                content = item.split(name, 1)[1].lstrip("*:：-– ").strip()
                found[name] = content
                break
    return found


def show_fortunes(body: str) -> None:
    fortunes = split_fortunes(body)
    if len(fortunes) < 3:
        st.markdown(body)
        return
    names = [(name, icon) for name, icon in FORTUNES if name in fortunes]
    for row_start in range(0, len(names), 2):
        cols = st.columns(2)
        for col, (name, icon) in zip(cols, names[row_start : row_start + 2]):
            with col, st.container(border=True):
                st.markdown(f"**{icon} {name}**")
                st.markdown(fortunes[name])


def show_reading(text: str) -> None:
    """관상 풀이를 섹션 카드로 보여준다. 섹션을 못 나누면 전체를 그대로 출력한다."""
    sections = split_sections(text)
    known = [s for s in sections if s[0] and section_icon(s[0])]
    if len(known) < MIN_KNOWN_SECTIONS:
        st.markdown(text)
        return

    for title, body in sections:
        if not title:
            if body:
                st.markdown(body)
            continue
        icon = section_icon(title) or "•"
        if "운" in title and any(name in title for name, _ in FORTUNES):
            st.markdown(f"#### {icon} {title}")
            show_fortunes(body)
            continue
        with st.container(border=True):
            st.markdown(f"#### {icon} {title}")
            st.markdown(body)


def show_result(result: dict) -> None:
    kind = result["kind"]
    if kind == "ok":
        st.divider()
        st.markdown("### 🏮 관상 풀이 결과")
        show_reading(result["text"])
        if result.get("truncated"):
            st.info(TRUNCATED_MESSAGE)
        st.caption(DISCLAIMER)
    elif kind == "no_face":
        st.warning("사진에서 얼굴을 찾지 못했습니다. 얼굴이 잘 보이는 사진을 올려 주세요.")
    elif kind == "multi_face":
        st.warning("여러 사람이 함께 있는 사진입니다. 한 사람만 나온 사진을 올려 주세요.")
    else:
        st.error(result["text"])


def render_inputs():
    """업로드/카메라 입력을 그리고 분석할 사진 파일(없으면 None)을 돌려준다.

    탭은 두 입력을 모두 화면에 유지하므로 탭을 바꿔도 올린 사진이 사라지지 않는다.
    카메라는 숨은 탭에서도 권한을 요청하므로 '카메라 켜기'를 켰을 때만 띄운다.
    """
    suffix = st.session_state.uploader_key
    with st.container(border=True):
        tab_upload, tab_camera = st.tabs(["📁 사진 업로드", "📷 카메라로 촬영"])
        with tab_upload:
            uploaded = st.file_uploader(
                "얼굴이 잘 보이는 한 사람의 사진을 올려 주세요 (jpg, png, webp / 최대 10MB)",
                type=["jpg", "jpeg", "png", "webp"],
                key=f"uploader_{suffix}",
                on_change=set_active_source,
                args=("upload",),
            )
            st.caption(UPLOAD_SIZE_HINT)
        with tab_camera:
            shot = None
            if st.toggle("카메라 켜기", key=f"camera_on_{suffix}"):
                shot = st.camera_input(
                    "정면을 바라보고 촬영해 주세요",
                    key=f"camera_{suffix}",
                    on_change=set_active_source,
                    args=("camera",),
                )
        st.caption(f"🔒 {PRIVACY_NOTICE}")

    if uploaded is not None and shot is not None:
        return shot if st.session_state.active_source == "camera" else uploaded
    return uploaded if uploaded is not None else shot


def render_app() -> None:
    api_key = get_config("OPENAI_API_KEY")
    model = get_config("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    if not api_key:
        show_missing_key_help()

    image_file = render_inputs()
    if image_file is None:
        # 사진이 없으면 이전 결과도 비운다
        st.session_state.image_id = None
        st.session_state.result = None
        if st.session_state.job is not None:
            wait_for_job()
        return

    file_bytes = image_file.getvalue()
    image_id = hashlib.sha256(file_bytes).hexdigest()
    if image_id != st.session_state.image_id:
        # 새 사진이 올라오면 이전 결과를 초기화한다
        st.session_state.image_id = image_id
        st.session_state.result = None

    try:
        jpeg_bytes = prepare_image(file_bytes)
    except ImageValidationError as exc:
        st.error(str(exc))
        return

    st.image(jpeg_bytes, caption="분석할 사진")

    job = st.session_state.job
    result = st.session_state.result
    already_done = result is not None and result["kind"] != "error"
    st.button(
        "🔮 관상 보기",
        type="primary",
        width="stretch",
        disabled=not api_key or already_done or job is not None,
        on_click=request_analysis,
        args=(image_id,),
    )

    if job is not None:
        if not job["started"] and job["image_id"] == image_id:
            job["started"] = True
            run_job(api_key, model, image_id, jpeg_bytes)
        else:
            wait_for_job()

    if result is not None:
        show_result(result)
        st.button("↺ 다른 사진으로 다시 보기", on_click=reset_all, width="stretch")


def main() -> None:
    st.set_page_config(page_title="AI 관상가", page_icon="🔮", layout="centered")
    init_state()

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(HERO_HTML, unsafe_allow_html=True)
    render_app()
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
