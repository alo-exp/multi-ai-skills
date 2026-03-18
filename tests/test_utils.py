"""
Unit tests for skills/orchestrator/engine/utils.py

UT-UT-01: pre_clean_text strips URLs
UT-UT-02: pre_clean_text strips query-string parameters
UT-UT-03: pre_clean_text strips base64 blobs
UT-UT-04: pre_clean_text neutralizes word=word patterns
UT-UT-05: pre_clean_text strips ChatGPT citation markers
UT-UT-06: pre_clean_text passes plain text through unchanged
UT-UT-07: deduplicate_response slices at marker
UT-UT-08: deduplicate_response returns full text when marker absent
UT-UT-09: deduplicate_response handles marker at very end
"""

import sys
from pathlib import Path

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from utils import pre_clean_text, deduplicate_response


# ── pre_clean_text ─────────────────────────────────────────────────────────────

class TestPreCleanText:
    def test_ut_ut_01_strips_urls(self):
        text = "Visit https://example.com/page?q=1 for details."
        result = pre_clean_text(text)
        assert "https://" not in result
        assert "[URL]" in result

    def test_ut_ut_02_strips_query_strings(self):
        text = "See page?foo=bar&baz=qux here."
        result = pre_clean_text(text)
        assert "[PARAMS]" in result
        assert "foo=bar" not in result

    def test_ut_ut_03_strips_base64_blobs(self):
        blob = "A" * 80  # 80-char alphanumeric blob
        text = f"Data: {blob} end."
        result = pre_clean_text(text)
        assert "[B64]" in result

    def test_ut_ut_04_neutralizes_word_equals_word(self):
        text = "key=value and name=test"
        result = pre_clean_text(text)
        assert "key:value" in result
        assert "name:test" in result
        assert "=" not in result

    def test_ut_ut_05_strips_chatgpt_citations(self):
        text = "The answer is 42citeturn3view5 according to sources."
        result = pre_clean_text(text)
        assert "[cite]" in result
        assert "citeturn" not in result

    def test_ut_ut_06_plain_text_unchanged(self):
        text = "This is a normal sentence with no special patterns."
        result = pre_clean_text(text)
        assert result == text


# ── deduplicate_response ──────────────────────────────────────────────────────

class TestDeduplicateResponse:
    def test_ut_ut_07_slices_at_marker(self):
        text = "Part one. End of Report. Part two (duplicate)."
        result = deduplicate_response(text)
        assert result == "Part one. End of Report."
        assert "duplicate" not in result

    def test_ut_ut_08_returns_full_when_no_marker(self):
        text = "No marker in this text at all."
        result = deduplicate_response(text)
        assert result == text

    def test_ut_ut_09_handles_marker_at_end(self):
        text = "Content here. End of Report."
        result = deduplicate_response(text)
        assert result == text
