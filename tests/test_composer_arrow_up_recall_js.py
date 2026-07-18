"""Pin ArrowUp/ArrowDown history traversal on the chat composer
(static/js/composerArrowUpRecall.js).

Driven through `node --input-type=module` so we exercise the real JS without a
full Vitest/Jest setup (same approach as test_reply_recipients_js.py). Skips
when `node` is not installed rather than failing.

Locks in: empty composer recalls last user message; repeated ArrowUp walks back
through history; ArrowDown walks forward; non-empty composer is untouched unless
already in history; draft is restored on ArrowDown to -1; Shift/Alt/Ctrl/Meta
+ArrowUp are ignored; IME composition does not trigger recall; messages are read
from #chat-history (dataset.raw), session-scoped.
"""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "static" / "js" / "composerArrowUpRecall.js"
_HELPER_URL = _HELPER.as_uri()
_HAS_NODE = shutil.which("node") is not None

_HARNESS = r"""
import { wireArrowUpRecall } from 'HELPER_PATH';

function makeComposer(initial = '') {
  const listeners = { keydown: [], send: [] };
  const composer = {
    value: initial,
    selectionStart: initial.length,
    selectionEnd: initial.length,
    _arrowUpRecallWired: false,
    addEventListener(type, fn) {
      if (listeners[type]) listeners[type].push(fn);
    },
    dispatchKey(opts = {}) {
      let prevented = false;
      const e = {
        key: opts.key ?? 'ArrowUp',
        shiftKey: !!opts.shiftKey,
        altKey: !!opts.altKey,
        ctrlKey: !!opts.ctrlKey,
        metaKey: !!opts.metaKey,
        isComposing: !!opts.isComposing,
        preventDefault() { prevented = true; },
      };
      for (const fn of listeners.keydown) fn(e);
      return prevented;
    },
    dispatchSend() {
      for (const fn of listeners.send) fn({});
    },
  };
  return composer;
}

function runCase(body) {
  const composer = makeComposer(body.initial ?? '');
  if (body.caret != null) {
    composer.selectionStart = body.caret;
    composer.selectionEnd = body.caretEnd ?? body.caret;
  }
  // messages: oldest → newest array (new API)
  const messages = body.messages ?? (body.last ? [body.last] : []);
  let resized = false;
  wireArrowUpRecall(composer, () => messages, {
    autoResize: () => { resized = true; },
  });

  // dispatch a sequence of keys, or a single key
  const events = body.events ?? [body.event ?? {}];
  let lastPrevented = false;
  for (const ev of events) {
    if (ev._send) { composer.value = ''; composer.dispatchSend(); lastPrevented = false; }
    else lastPrevented = composer.dispatchKey(ev);
  }

  return {
    value: composer.value,
    selectionStart: composer.selectionStart,
    selectionEnd: composer.selectionEnd,
    prevented: lastPrevented,
    resized,
  };
}

const cases = CASES_JSON;
const results = cases.map(runCase);
console.log(JSON.stringify(results));
""".replace("HELPER_PATH", _HELPER_URL)


def _run(cases: list) -> list:
    js = _HARNESS.replace("CASES_JSON", json.dumps(cases))
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


# ---------------------------------------------------------------------------
# Original tests (preserved)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_empty_composer_recalls_last_user_message():
    out = _run([{"initial": "", "messages": ["hello again"]}])[0]
    assert out["value"] == "hello again"
    assert out["selectionStart"] == len("hello again")
    assert out["prevented"] is True
    assert out["resized"] is True


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_non_empty_composer_does_not_recall():
    out = _run([{"initial": "draft in progress", "messages": ["ignored"]}])[0]
    assert out["value"] == "draft in progress"
    assert out["prevented"] is False
    assert out["resized"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_whitespace_only_composer_is_not_empty():
    out = _run([{"initial": "   ", "messages": ["ignored"]}])[0]
    assert out["value"] == "   "
    assert out["prevented"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_multiline_caret_navigation_preserved():
    text = "line one\nline two"
    out = _run([{"initial": text, "caret": len(text), "messages": ["ignored"]}])[0]
    assert out["value"] == text
    assert out["prevented"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_modified_arrow_up_ignored():
    cases = [
        {"initial": "", "messages": ["x"], "event": {"shiftKey": True}},
        {"initial": "", "messages": ["x"], "event": {"altKey": True}},
        {"initial": "", "messages": ["x"], "event": {"ctrlKey": True}},
        {"initial": "", "messages": ["x"], "event": {"metaKey": True}},
    ]
    for out in _run(cases):
        assert out["value"] == ""
        assert out["prevented"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_ime_composition_does_not_trigger_recall():
    out = _run([{"initial": "", "event": {"isComposing": True}, "messages": ["ignored"]}])[0]
    assert out["value"] == ""
    assert out["prevented"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_no_recall_when_last_message_missing():
    out = _run([{"initial": "", "messages": []}])[0]
    assert out["value"] == ""
    assert out["prevented"] is False
    assert out["resized"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_wire_is_idempotent():
    js = f"""
    import {{ wireArrowUpRecall }} from '{_HELPER_URL}';
    const composer = {{ _arrowUpRecallWired: false, addEventListener() {{}} }};
    const ok1 = wireArrowUpRecall(composer, () => ['x']);
    const ok2 = wireArrowUpRecall(composer, () => ['y']);
    console.log(JSON.stringify({{ ok1, ok2, wired: composer._arrowUpRecallWired }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(_REPO),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == {"ok1": True, "ok2": True, "wired": True}


# ---------------------------------------------------------------------------
# New tests — full history traversal
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_up_walks_back_through_history():
    msgs = ["first", "second", "third"]
    # Three ArrowUps: newest → oldest
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": [{}, {}, {}],
    }])[0]
    assert out["value"] == "first"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_down_walks_forward_through_history():
    msgs = ["first", "second", "third"]
    # ArrowUp x3, then ArrowDown x2 → lands on "second"
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": [
            {},                            # up → third
            {},                            # up → second
            {},                            # up → first
            {"key": "ArrowDown"},          # down → second
            {"key": "ArrowDown"},          # down → third
        ],
    }])[0]
    assert out["value"] == "third"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_down_to_minus_one_restores_draft():
    msgs = ["first", "second"]
    # Composer is empty, ArrowUp once, ArrowDown once → back to empty draft
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": [
            {},                    # up → second
            {"key": "ArrowDown"},  # down → restored draft ("")
        ],
    }])[0]
    assert out["value"] == ""


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_up_does_not_go_past_oldest():
    msgs = ["only"]
    # Two ArrowUps on a single-message history — should stay at "only"
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": [{}, {}],
    }])[0]
    assert out["value"] == "only"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_down_does_nothing_outside_history():
    out = _run([{
        "initial": "",
        "messages": ["x"],
        "events": [{"key": "ArrowDown"}],
    }])[0]
    assert out["value"] == ""
    assert out["prevented"] is False


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_send_resets_history_index():
    msgs = ["first", "second"]
    # ArrowUp twice, send, then ArrowUp once → should land on "second" again (newest)
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": [
            {},           # up → second
            {},           # up → first
            {"_send": True},
            {},           # up → second (fresh traversal)
        ],
    }])[0]
    assert out["value"] == "second"


# ---------------------------------------------------------------------------
# P2 regression: session beyond page limit without scrolling first
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_up_reaches_all_messages_beyond_page_limit():
    """Regression: with 50 user messages (exceeding any rendered page),
    ArrowUp should walk through ALL of them, not clamp at a page boundary."""
    msgs = [f"msg-{i}" for i in range(50)]
    # Walk through all 50 messages from newest to oldest
    events = [{} for _ in range(50)]
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": events,
    }])[0]
    assert out["value"] == "msg-0", f"Expected oldest message 'msg-0', got {out['value']!r}"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_up_page_limit_then_arrow_down():
    """After exhausting a page-length traversal, ArrowDown should walk
    forward through all messages back to the draft."""
    msgs = [f"msg-{i}" for i in range(50)]
    # Up 50 times (to oldest), then down 25 times (back to 25th newest)
    events = [{} for _ in range(50)] + [{"key": "ArrowDown"} for _ in range(25)]
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": events,
    }])[0]
    assert out["value"] == "msg-25", f"Expected 'msg-25', got {out['value']!r}"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_arrow_up_page_limit_does_not_clamp_at_boundary():
    """The oldest message does NOT clamp traversal — ArrowUp past the
    oldest should stay on the oldest message (no wrap-around)."""
    msgs = [f"msg-{i}" for i in range(50)]
    # 55 ArrowUps on a 50-message history — should stop at oldest
    events = [{} for _ in range(55)]
    out = _run([{
        "initial": "",
        "messages": msgs,
        "events": events,
    }])[0]
    assert out["value"] == "msg-0", f"Expected oldest 'msg-0', got {out['value']!r}"


# ---------------------------------------------------------------------------
# P3 regression: no-op arrow paths must NOT scan chat history
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_no_op_arrow_up_non_empty_does_not_call_provider():
    """ArrowUp on a non-empty live composer must NOT call getUserMessages."""
    called = []
    js = f"""
    import {{ wireArrowUpRecall }} from '{_HELPER_URL}';
    const listeners = [];
    const composer = {{
      value: 'draft',
      selectionStart: 5, selectionEnd: 5,
      _arrowUpRecallWired: false,
      addEventListener(type, fn) {{ if (type === 'keydown') listeners.push(fn); }},
    }};
    let providerCalled = false;
    wireArrowUpRecall(composer, () => {{ providerCalled = true; return ['msg']; }});
    let prevented = false;
    listeners[0]({{
      key: 'ArrowUp', shiftKey: false, altKey: false, ctrlKey: false, metaKey: false,
      isComposing: false,
      preventDefault() {{ prevented = true; }},
    }});
    console.log(JSON.stringify({{ providerCalled, prevented, value: composer.value }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip())
    assert result["providerCalled"] is False, "getUserMessages was called for non-empty ArrowUp"
    assert result["prevented"] is False
    assert result["value"] == "draft"


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_no_op_arrow_down_outside_history_does_not_call_provider():
    """ArrowDown outside history traversal must NOT call getUserMessages."""
    js = f"""
    import {{ wireArrowUpRecall }} from '{_HELPER_URL}';
    const listeners = [];
    const composer = {{
      value: '',
      selectionStart: 0, selectionEnd: 0,
      _arrowUpRecallWired: false,
      addEventListener(type, fn) {{ if (type === 'keydown') listeners.push(fn); }},
    }};
    let providerCalled = false;
    wireArrowUpRecall(composer, () => {{ providerCalled = true; return ['msg']; }});
    let prevented = false;
    listeners[0]({{
      key: 'ArrowDown', shiftKey: false, altKey: false, ctrlKey: false, metaKey: false,
      isComposing: false,
      preventDefault() {{ prevented = true; }},
    }});
    console.log(JSON.stringify({{ providerCalled, prevented, value: composer.value }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip())
    assert result["providerCalled"] is False, "getUserMessages was called for no-op ArrowDown"
    assert result["prevented"] is False
    assert result["value"] == ""


# ---------------------------------------------------------------------------
# DOM helper tests (preserved + extended)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_get_last_user_message_from_chat_history():
    js = f"""
    import {{ getLastUserMessageFromChatHistory }} from '{_HELPER_URL}';
    const chatBox = {{
      id: 'chat-history',
      querySelectorAll(sel) {{
        if (sel !== '.msg-user') return [];
        return [
          {{ dataset: {{ raw: 'first' }}, querySelector: () => null }},
          {{ dataset: {{ raw: 'last raw' }}, querySelector: () => null }},
        ];
      }},
    }};
    const doc = {{
      getElementById(id) {{ return id === 'chat-history' ? chatBox : null; }},
    }};
    console.log(JSON.stringify({{
      fromChat: getLastUserMessageFromChatHistory(doc),
      fromBox: getLastUserMessageFromChatHistory(chatBox),
      empty: getLastUserMessageFromChatHistory({{ getElementById: () => null }}),
      noUsers: getLastUserMessageFromChatHistory({{
        getElementById: () => ({{ querySelectorAll: () => [] }}),
      }}),
    }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == {
        "fromChat": "last raw",
        "fromBox": "last raw",
        "empty": "",
        "noUsers": "",
    }


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_get_user_messages_returns_all_in_order():
    js = f"""
    import {{ getUserMessagesFromChatHistory }} from '{_HELPER_URL}';
    const chatBox = {{
      id: 'chat-history',
      querySelectorAll(sel) {{
        if (sel !== '.msg-user') return [];
        return [
          {{ dataset: {{ raw: 'alpha' }}, querySelector: () => null }},
          {{ dataset: {{ raw: 'beta' }}, querySelector: () => null }},
          {{ dataset: {{ raw: 'gamma' }}, querySelector: () => null }},
        ];
      }},
    }};
    console.log(JSON.stringify(getUserMessagesFromChatHistory(chatBox)));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == ["alpha", "beta", "gamma"]


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_integration_recalls_from_chat_history_dom():
    js = f"""
    import {{
      wireArrowUpRecall,
      getUserMessagesFromChatHistory,
    }} from '{_HELPER_URL}';
    const chatBox = {{
      id: 'chat-history',
      querySelectorAll(sel) {{
        if (sel !== '.msg-user') return [];
        return [{{ dataset: {{ raw: 'stored prompt' }}, querySelector: () => null }}];
      }},
    }};
    const doc = {{ getElementById: (id) => (id === 'chat-history' ? chatBox : null) }};
    const listeners = [];
    const composer = {{
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
      _arrowUpRecallWired: false,
      addEventListener(type, fn) {{ if (type === 'keydown') listeners.push(fn); }},
    }};
    wireArrowUpRecall(composer, () => getUserMessagesFromChatHistory(doc));
    let prevented = false;
    listeners[0]({{
      key: 'ArrowUp',
      shiftKey: false, altKey: false, ctrlKey: false, metaKey: false,
      isComposing: false,
      preventDefault() {{ prevented = true; }},
    }});
    console.log(JSON.stringify({{ value: composer.value, prevented }}));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, encoding="utf-8",
        cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == {"value": "stored prompt", "prevented": True}