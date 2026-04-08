"""Unit tests for prompt_echo module.

Tests UT-PE-01 through UT-PE-08.
"""

import sys
from pathlib import Path

# Add engine directory to sys.path for bare imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine"))

from prompt_echo import auto_extract_prompt_sigs, is_prompt_echo

FIXTURES = Path(__file__).parent / "fixtures"


class TestAutoExtractPromptSigs:
    """Tests for auto_extract_prompt_sigs()."""

    def test_ut_pe_01_extracts_allcaps_from_structured_prompt(self):
        """UT-PE-01: Extracts ALL-CAPS phrases from structured prompt."""
        prompt = (FIXTURES / "sample-research-prompt.md").read_text(encoding="utf-8")
        sigs = auto_extract_prompt_sigs(prompt)
        assert len(sigs) > 0, "Should extract at least one signature"
        assert any("SYSTEM ROLE" in s for s in sigs), (
            f"Expected 'SYSTEM ROLE & MINDSET' (or substring) in sigs, got: {sigs}"
        )

    def test_ut_pe_02_max_sigs_limits_output(self):
        """UT-PE-02: max_sigs parameter limits output to 5 items."""
        # Create a prompt with 10 ALL-CAPS phrases (each 8+ chars)
        phrases = [
            "FIRST SECTION HEADER",
            "SECOND SECTION HEADER",
            "THIRD SECTION HEADER",
            "FOURTH SECTION HEADER",
            "FIFTH SECTION HEADER",
            "SIXTH SECTION HEADER",
            "SEVENTH SECTION HEADER",
            "EIGHTH SECTION HEADER",
            "NINTH SECTION HEADER",
            "TENTH SECTION HEADER",
        ]
        prompt = "\n".join(phrases)
        sigs = auto_extract_prompt_sigs(prompt, max_sigs=5)
        assert len(sigs) <= 5, f"Expected at most 5 sigs, got {len(sigs)}"

    def test_ut_pe_03_plain_text_returns_empty_or_minimal(self):
        """UT-PE-03: Plain-text prompt returns empty or minimal list."""
        prompt = "Hello, what can you do? Tell me about your capabilities please."
        sigs = auto_extract_prompt_sigs(prompt)
        # Plain text with no ALL-CAPS and no 15+ char words
        assert len(sigs) == 0, f"Expected empty sigs for plain text, got: {sigs}"

    def test_ut_pe_04_fallback_to_long_words(self):
        """UT-PE-04: No ALL-CAPS but has 15+ char words -> falls back to those."""
        prompt = (
            "Please analyze the interoperability and containerization "
            "of this microservicesplatform along with its observabilityframework "
            "and the infrastructuremanagement capabilities."
        )
        sigs = auto_extract_prompt_sigs(prompt)
        # Should find long words (15+ chars) as fallback
        assert len(sigs) > 0, (
            f"Expected fallback to long words, got empty. Prompt has words: "
            f"{[w for w in prompt.split() if len(w) >= 15]}"
        )
        assert all(len(s) >= 15 for s in sigs), (
            f"Fallback sigs should be 15+ chars, got: {sigs}"
        )


class TestIsPromptEcho:
    """Tests for is_prompt_echo()."""

    def test_ut_pe_05_returns_true_for_echoed_prompt(self):
        """UT-PE-05: Returns True when text = first 3000 chars of prompt."""
        prompt = (FIXTURES / "sample-research-prompt.md").read_text(encoding="utf-8")
        sigs = auto_extract_prompt_sigs(prompt)
        # Simulate the platform echoing the prompt text
        echoed_text = prompt[:3000]
        assert is_prompt_echo(echoed_text, sigs) is True

    def test_ut_pe_06_returns_false_for_ai_response(self):
        """UT-PE-06: Returns False for AI response text."""
        prompt = (FIXTURES / "sample-research-prompt.md").read_text(encoding="utf-8")
        sigs = auto_extract_prompt_sigs(prompt)
        ai_response = (
            "# Executive Summary\n"
            "This platform provides comprehensive DevOps capabilities including "
            "CI/CD pipelines, infrastructure as code, and monitoring dashboards.\n\n"
            "## Key Findings\n"
            "The platform excels at container orchestration and has strong "
            "integration capabilities with major cloud providers."
        )
        assert is_prompt_echo(ai_response, sigs) is False

    def test_ut_pe_07_returns_false_when_sig_beyond_sample_size(self):
        """UT-PE-07: Returns False when sig appears only beyond sample_size."""
        # Put the signature far into the text, beyond the sample window
        filler = "a " * 2000  # 4000 chars of filler
        text = filler + "SYSTEM ROLE & MINDSET appears here but is beyond sample_size"
        sigs = ["SYSTEM ROLE & MINDSET"]
        # With default sample_size=3000, the sig at position 4000 should not be found
        assert is_prompt_echo(text, sigs, sample_size=3000) is False

    def test_is_prompt_echo_empty_sigs(self):
        """is_prompt_echo returns False when prompt_sigs is empty."""
        assert is_prompt_echo("any text here", []) is False

    def test_ut_pe_08_backward_compat_key_phrases(self):
        """UT-PE-08: Current sample-research-prompt.md produces expected key sigs."""
        prompt = (FIXTURES / "sample-research-prompt.md").read_text(encoding="utf-8")
        sigs = auto_extract_prompt_sigs(prompt)
        # Should include the major ALL-CAPS section headers
        sigs_joined = " | ".join(sigs)
        assert any("SYSTEM ROLE" in s for s in sigs), (
            f"Expected 'SYSTEM ROLE' phrase in sigs: {sigs_joined}"
        )
        # Check for CONSTRAINTS or NON-NEGOTIABLE
        assert any("CONSTRAINT" in s or "NON-NEGOTIABLE" in s for s in sigs), (
            f"Expected CONSTRAINTS/NON-NEGOTIABLE phrase in sigs: {sigs_joined}"
        )
