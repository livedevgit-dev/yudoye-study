"""
streamlit_app.py — 유도예 학습 앱 (Streamlit 단순 버전)
─────────────────────────────────────────────────────────────────────────────
목적:
  초등학생용 사칙연산 문제를 '출제 + 채점'만 하는 가벼운 단일 파일 앱입니다.
  - 저장(이력/DB) 없음: 점수는 현재 접속 세션 동안만 메모리에 유지됩니다.
  - 객관식 없음: 주관식(숫자 입력)만 사용합니다.
  - 단순 연산 / 서술식(문장제) 두 가지 문제 형태를 지원합니다.

실행:
  pip install -r requirements.txt
  streamlit run streamlit_app.py

배포(Streamlit Community Cloud):
  GitHub에 push → share.streamlit.io 에서 저장소 연결 → main 파일을 streamlit_app.py 로 지정
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ─── 상수 ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
WORD_TEMPLATES_FILE = BASE_DIR / "data" / "word_templates.json"

# 연산별 학습지 기본값 (단순 연산 / 서술식 개수, 최대 자릿수) — 합계 20문제
DEFAULT_WORKSHEET_SPECS: dict[str, dict[str, int]] = {
    "add": {"arithmetic": 3, "word": 2, "max_digits": 4},
    "sub": {"arithmetic": 3, "word": 2, "max_digits": 3},
    "mul": {"arithmetic": 2, "word": 2, "max_digits": 2},
    "div": {"arithmetic": 2, "word": 2, "max_digits": 2},
}

# 서술식 문장에 채워 넣을 이름·물건 후보
NAMES = ["유나", "도윤", "예나", "민수", "지우", "서연", "하준"]
ITEMS = ["사과", "연필", "공", "스티커", "구슬", "책", "젤리", "우유", "쿠키"]

# UI 연산 키 ↔ 표시 기호 ↔ JSON operator 기호
OPERATIONS = {
    "덧셈 (＋)": {"key": "add", "symbol": "+", "json_op": "+"},
    "뺄셈 (－)": {"key": "sub", "symbol": "-", "json_op": "-"},
    "곱셈 (×)": {"key": "mul", "symbol": "×", "json_op": "*"},
    "나눗셈 (÷)": {"key": "div", "symbol": "÷", "json_op": "/"},
}

OP_LABELS = list(OPERATIONS.keys())


@dataclass
class OpWorksheetSpec:
    """연산 하나에 대한 학습지 출제 조건."""

    op_label: str
    op: dict
    arithmetic_count: int
    word_count: int
    max_digits: int

    @property
    def total(self) -> int:
        return self.arithmetic_count + self.word_count


# ─── 한글 조사 처리 ──────────────────────────────────────────────────────────
def has_jongseong(ch: str) -> bool:
    """
    한글 음절 1글자에 받침(종성)이 있는지 판별.
    유니코드 한글은 (초성×21 + 중성)×28 + 종성 + 0xAC00 구조이므로,
    (코드 - 0xAC00) % 28 == 0 이면 종성이 없는 글자(받침 없음)입니다.
    """
    if not ch:
        return False
    code = ord(ch[-1])
    if code < 0xAC00 or code > 0xD7A3:
        return False
    return (code - 0xAC00) % 28 != 0


def resolve_josa(text: str) -> str:
    """
    "단어(이)가" 형태의 조사 마커를 앞 단어 받침에 맞게 변환.
    괄호 안 = 받침 있을 때, 괄호 뒤 = 받침 없을 때.
    예) 사과(을)를 → 사과를 / 연필(을)를 → 연필을
    """
    patterns = [
        (r"([가-힣]+)\(이\)가", ("이", "가")),
        (r"([가-힣]+)\(은\)는", ("은", "는")),
        (r"([가-힣]+)\(을\)를", ("을", "를")),
        (r"([가-힣]+)\(와\)과", ("과", "와")),  # 받침O→과, 받침X→와
    ]
    result = text
    for pattern, (with_j, without_j) in patterns:
        def repl(m: re.Match) -> str:
            word = m.group(1)
            return word + (with_j if has_jongseong(word) else without_j)

        result = re.sub(pattern, repl, result)
    return result


# ─── 데이터 로드 ─────────────────────────────────────────────────────────────
@st.cache_data
def load_word_templates() -> list[dict]:
    """서술식 템플릿 JSON을 읽어 캐시합니다(파일은 한 번만 읽음)."""
    if not WORD_TEMPLATES_FILE.exists():
        return []
    with WORD_TEMPLATES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


# ─── 난수·문제 생성 ──────────────────────────────────────────────────────────
def rand_by_max_digits(max_digits: int) -> int:
    """
    1 ~ max_digits 자리 중 하나를 무작위로 골라 그 범위의 양의 정수를 반환.
    예) 최대 2자리 → 1~9 또는 10~99 중에서 나옴 (자릿수 혼합 출제).
    """
    digits = random.randint(1, max_digits)
    if digits == 1:
        return random.randint(1, 9)
    return random.randint(10 ** (digits - 1), 10**digits - 1)


def _digit_count(n: int) -> int:
    return len(str(abs(n)))


def _rand_division_operands(max_digits: int) -> tuple[int, int, int]:
    """
    나눗셈용 a ÷ b = answer 생성.
    피제수(a), 제수(b), 몫(answer) 모두 max_digits 자리 이하가 되도록 제한합니다.
  (기존 b×answer 방식은 곱이 커져 4자리 피제수가 나올 수 있었음)
    """
    cap = 10**max_digits - 1
    for _ in range(200):
        b = rand_by_max_digits(max_digits)
        max_answer = cap // b
        if max_answer < 1:
            continue
        answer = random.randint(1, max_answer)
        a = b * answer
        if _digit_count(a) <= max_digits and _digit_count(b) <= max_digits:
            return a, b, answer
    b = random.randint(2, min(9, cap))
    answer = random.randint(1, max(1, cap // b))
    return b * answer, b, answer


def generate_arithmetic(op_key: str, symbol: str, max_digits: int) -> dict:
    """단순 연산 문제 1개 생성 (피연산자 + 정답)."""
    a = rand_by_max_digits(max_digits)
    b = rand_by_max_digits(max_digits)

    if op_key == "add":
        answer = a + b
    elif op_key == "sub":
        if b > a:
            a, b = b, a  # 음수 방지: 큰 수 - 작은 수
        answer = a - b
    elif op_key == "mul":
        answer = a * b
    elif op_key == "div":
        a, b, answer = _rand_division_operands(max_digits)
    else:
        answer = a + b

    return {
        "kind": "arithmetic",
        "text": f"{a} {symbol} {b} = ?",
        "answer": answer,
    }


def generate_word(op_key: str, symbol: str, json_op: str, max_digits: int) -> dict:
    """서술식 문제 1개 생성. 연산 결과를 템플릿에 끼워 넣고 조사를 정리."""
    templates = [t for t in load_word_templates() if t.get("operator") == json_op]
    if not templates:
        # 해당 연산 템플릿이 없으면 단순 연산으로 대체
        return generate_arithmetic(op_key, symbol, max_digits)

    a, b, answer = _operands_for_word(op_key, max_digits)
    tpl = random.choice(templates)
    name1, name2 = _pick_two_names()
    item = random.choice(ITEMS)

    text = (
        tpl["template_text"]
        .replace("{name1}", name1)
        .replace("{name2}", name2)
        .replace("{name}", name1)
        .replace("{item}", item)
        .replace("{a}", str(a))
        .replace("{b}", str(b))
    )
    text = resolve_josa(text)

    return {
        "kind": "word",
        "text": text,
        "answer": answer,
        "template_id": tpl.get("template_id"),
    }


def _operands_for_word(op_key: str, max_digits: int) -> tuple[int, int, int]:
    """서술식용 a, b, 정답 생성 (나눗셈은 나누어떨어지게)."""
    a = rand_by_max_digits(max_digits)
    b = rand_by_max_digits(max_digits)
    if op_key == "add":
        return a, b, a + b
    if op_key == "sub":
        if b > a:
            a, b = b, a
        return a, b, a - b
    if op_key == "mul":
        return a, b, a * b
    if op_key == "div":
        return _rand_division_operands(max_digits)
    return a, b, a + b


def _pick_two_names() -> tuple[str, str]:
    """서로 다른 두 이름 선택."""
    name1 = random.choice(NAMES)
    name2 = random.choice(NAMES)
    while name2 == name1 and len(NAMES) > 1:
        name2 = random.choice(NAMES)
    return name1, name2


def make_problem(problem_type: str, op: dict, max_digits: int) -> dict:
    """설정에 맞는 문제 1개 생성."""
    if problem_type == "서술식":
        return generate_word(op["key"], op["symbol"], op["json_op"], max_digits)
    return generate_arithmetic(op["key"], op["symbol"], max_digits)


def make_worksheet_problems(specs: list[OpWorksheetSpec]) -> list[dict]:
    """연산별 개수·자릿수 설정에 따라 학습지 문제 목록을 생성합니다."""
    problems: list[dict] = []
    for spec in specs:
        if spec.total == 0:
            continue
        for _ in range(spec.arithmetic_count):
            problem = generate_arithmetic(spec.op["key"], spec.op["symbol"], spec.max_digits)
            problem["op_label"] = spec.op_label
            problems.append(problem)
        for _ in range(spec.word_count):
            problem = generate_word(
                spec.op["key"], spec.op["symbol"], spec.op["json_op"], spec.max_digits
            )
            problem["op_label"] = spec.op_label
            problems.append(problem)
    random.shuffle(problems)
    for i, problem in enumerate(problems, start=1):
        problem["number"] = i
    return problems


def build_worksheet_summary(specs: list[OpWorksheetSpec]) -> str:
    """학습지 상단에 표시할 연산별 요약 문자열."""
    parts: list[str] = []
    arith_total = word_total = 0
    for spec in specs:
        if spec.total == 0:
            continue
        short = spec.op_label.split()[0]
        parts.append(
            f"{short} {spec.max_digits}자리 "
            f"(단순 {spec.arithmetic_count}+서술 {spec.word_count})"
        )
        arith_total += spec.arithmetic_count
        word_total += spec.word_count
    detail = " · ".join(parts) if parts else "설정된 문제 없음"
    return f"총 {arith_total + word_total}문제 · 단순 연산 {arith_total} · 서술식 {word_total} — {detail}"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_worksheet_html(problems: list[dict], summary: str) -> str:
    """인쇄용 학습지 HTML (iframe 안에서 window.print() 호출)."""
    total = len(problems)
    rows = []
    for p in problems:
        if p.get("kind") == "word":
            body = _escape_html(p["text"])
            rows.append(
                f'<div class="problem word">'
                f'<span class="num">{p["number"]}.</span>'
                f'<span class="text">{body}</span>'
                f'<div class="answer-line"></div>'
                f"</div>"
            )
        else:
            body = _escape_html(p["text"])
            rows.append(
                f'<div class="problem arithmetic">'
                f'<span class="num">{p["number"]}.</span>'
                f'<span class="text">{body}</span>'
                f"</div>"
            )

    problems_html = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    color: #111;
    margin: 0;
    padding: 16px 20px 24px;
    background: #fff;
  }}
  .toolbar {{
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
    align-items: center;
  }}
  .toolbar button {{
    font-size: 15px;
    padding: 8px 18px;
    cursor: pointer;
    border: 1px solid #333;
    border-radius: 6px;
    background: #f5f5f5;
  }}
  .toolbar button.primary {{
    background: #2563eb;
    color: #fff;
    border-color: #2563eb;
  }}
  .worksheet {{
    border: 2px solid #222;
    padding: 20px 24px 28px;
  }}
  h1 {{
    margin: 0 0 6px;
    font-size: 22px;
    text-align: center;
  }}
  .meta {{
    display: flex;
    justify-content: space-between;
    margin: 14px 0 18px;
    font-size: 15px;
  }}
  .meta span {{
    display: inline-block;
    min-width: 140px;
    border-bottom: 1px solid #333;
    padding-bottom: 2px;
  }}
  .settings {{
    text-align: center;
    font-size: 13px;
    color: #444;
    margin-bottom: 16px;
  }}
  .problems {{
    column-count: 2;
    column-gap: 28px;
  }}
  .problem {{
    break-inside: avoid;
    margin-bottom: 18px;
    font-size: 15px;
    line-height: 1.55;
  }}
  .problem .num {{
    font-weight: 700;
    margin-right: 4px;
  }}
  .problem.word .text {{
    display: inline;
  }}
  .problem.word .answer-line {{
    margin-top: 6px;
    margin-left: 22px;
    border-bottom: 1px solid #333;
    height: 22px;
    width: 90px;
  }}
  .problem.arithmetic .text {{
    font-size: 17px;
    font-weight: 600;
  }}
  @media print {{
  .toolbar {{ display: none !important; }}
  body {{ padding: 0; }}
  .worksheet {{ border: none; padding: 0; }}
  }}
</style>
</head>
<body>
  <div class="toolbar no-print">
    <button class="primary" onclick="window.print()">🖨️ 인쇄하기</button>
    <span>아래 학습지가 인쇄됩니다. ({total}문제)</span>
  </div>
  <div class="worksheet">
    <h1>🧮 유도예 학습 앱 — 사칙연산 학습지</h1>
    <div class="settings">{_escape_html(summary)}</div>
    <div class="meta">
      <span>이름:</span>
      <span>날짜:</span>
    </div>
    <div class="problems">
      {problems_html}
    </div>
  </div>
</body>
</html>"""


# ─── 세션 상태 초기화 ────────────────────────────────────────────────────────
def init_state() -> None:
    st.session_state.setdefault("problem", None)
    st.session_state.setdefault("correct", 0)
    st.session_state.setdefault("total", 0)
    st.session_state.setdefault("last_feedback", None)
    st.session_state.setdefault("worksheet", None)
    st.session_state.setdefault("worksheet_summary", "")


# ─── 사이드바: 학습지 구성 ───────────────────────────────────────────────────
def read_worksheet_specs() -> list[OpWorksheetSpec]:
    """사이드바에서 연산별 단순 연산·서술식 개수와 자릿수를 읽습니다."""
    specs: list[OpWorksheetSpec] = []
    for op_label in OP_LABELS:
        op = OPERATIONS[op_label]
        key = op["key"]
        defaults = DEFAULT_WORKSHEET_SPECS[key]
        with st.expander(op_label, expanded=key == "add"):
            arithmetic_count = st.number_input(
                "단순 연산 (계산식)",
                min_value=0,
                max_value=30,
                value=defaults["arithmetic"],
                step=1,
                key=f"ws_arith_{key}",
                help="예: 1234 + 56 = ?",
            )
            word_count = st.number_input(
                "서술식 (문장제)",
                min_value=0,
                max_value=30,
                value=defaults["word"],
                step=1,
                key=f"ws_word_{key}",
            )
            max_digits = st.select_slider(
                "최대 자릿수",
                options=[1, 2, 3, 4],
                value=defaults["max_digits"],
                key=f"ws_digits_{key}",
            )
        specs.append(
            OpWorksheetSpec(
                op_label=op_label,
                op=op,
                arithmetic_count=int(arithmetic_count),
                word_count=int(word_count),
                max_digits=int(max_digits),
            )
        )
    return specs


# ─── 화면: 학습지 출력 ───────────────────────────────────────────────────────
def render_worksheet_mode(specs: list[OpWorksheetSpec]) -> None:
    total = sum(s.total for s in specs)
    summary = build_worksheet_summary(specs)

    st.subheader(f"📄 학습지 출력 ({total}문제)")
    st.caption(
        "사이드바에서 연산마다 단순 연산·서술식 개수와 자릿수를 따로 정한 뒤 "
        "학습지를 만들고 인쇄하세요."
    )

    if total == 0:
        st.warning("출제할 문제가 없습니다. 사이드바에서 연산별 문제 수를 1개 이상 설정해 주세요.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(f"📝 {total}문제 학습지 만들기", type="primary", use_container_width=True):
            st.session_state.worksheet = make_worksheet_problems(specs)
            st.session_state.worksheet_summary = summary
            st.rerun()
    with col_b:
        if st.session_state.worksheet and st.button(
            "🔄 다른 문제로 다시 만들기", use_container_width=True
        ):
            st.session_state.worksheet = make_worksheet_problems(specs)
            st.session_state.worksheet_summary = summary
            st.rerun()

    if st.session_state.worksheet is None:
        st.info(f"**{total}문제 학습지 만들기** 버튼을 누르면 아래에 학습지가 나타납니다.")
        st.markdown(f"현재 설정: {summary}")
        return

    display_summary = st.session_state.get("worksheet_summary", summary)
    html = build_worksheet_html(st.session_state.worksheet, display_summary)
    height = min(500 + 48 * len(st.session_state.worksheet), 2200)
    components.html(html, height=height, scrolling=True)


# ─── 화면: 화면 연습 ─────────────────────────────────────────────────────────
def render_practice_mode(problem_type: str, op: dict, max_digits: int) -> None:
    # 점수 표시
    col1, col2 = st.columns(2)
    col1.metric("맞힌 문제", st.session_state.correct)
    col2.metric("푼 문제", st.session_state.total)

    st.markdown("---")

    if st.session_state.problem is None:
        st.session_state.problem = make_problem(problem_type, op, max_digits)
        st.session_state.last_feedback = None

    problem = st.session_state.problem

    if problem.get("kind") == "word":
        st.subheader("📖 문장을 읽고 숫자로 답하세요")
        st.markdown(f"### {problem['text']}")
    else:
        st.subheader("🔢 계산해서 숫자로 답하세요")
        st.markdown(f"## {problem['text']}")

    with st.form("answer_form", clear_on_submit=False):
        user_answer = st.number_input(
            "답 (숫자만 입력)", step=1, value=0, format="%d"
        )
        submitted = st.form_submit_button("확인", use_container_width=True)

    if submitted:
        st.session_state.total += 1
        if int(user_answer) == int(problem["answer"]):
            st.session_state.correct += 1
            st.session_state.last_feedback = ("ok", "정답이에요! 잘했어요 🎉")
        else:
            st.session_state.last_feedback = (
                "ng",
                f"아쉬워요. 정답은 {problem['answer']} 이에요.",
            )

    if st.session_state.last_feedback:
        kind, msg = st.session_state.last_feedback
        if kind == "ok":
            st.success(msg)
        else:
            st.error(msg)

    if st.button("다음 문제 ▶", type="primary", use_container_width=True):
        st.session_state.problem = make_problem(problem_type, op, max_digits)
        st.session_state.last_feedback = None
        st.rerun()


# ─── 화면 ────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(page_title="유도예 학습 앱", page_icon="🧮")
    init_state()

    st.title("🧮 유도예 학습 앱")
    st.caption("초등 사칙연산 연습 · 화면 풀이 또는 학습지 인쇄")

    with st.sidebar:
        st.header("사용 방법")
        mode = st.radio("모드", ["학습지 출력", "화면 연습"], index=0)
        st.markdown("---")

        worksheet_specs: list[OpWorksheetSpec] = []
        problem_type = "단순 연산"
        op_label = OP_LABELS[0]
        max_digits = 1

        if mode == "학습지 출력":
            st.header("학습지 구성")
            st.caption("연산마다 단순 연산·서술식 개수와 자릿수를 따로 지정합니다.")
            worksheet_specs = read_worksheet_specs()
            ws_total = sum(s.total for s in worksheet_specs)
            st.markdown(f"**총 {ws_total}문제**")
        else:
            st.header("문제 설정")
            problem_type = st.radio("문제 형태", ["단순 연산", "서술식"], index=0)
            op_label = st.selectbox("연산", OP_LABELS, index=0)
            max_digits = st.select_slider("최대 자릿수", options=[1, 2, 3, 4], value=1)
            st.markdown("---")
            if st.button("점수 초기화", use_container_width=True):
                st.session_state.correct = 0
                st.session_state.total = 0
                st.session_state.problem = None
                st.session_state.last_feedback = None
                st.rerun()

    op = OPERATIONS[op_label]

    if mode == "학습지 출력":
        render_worksheet_mode(worksheet_specs)
    else:
        render_practice_mode(problem_type, op, max_digits)


if __name__ == "__main__":
    main()
