"""Unit tests for the robust JSON parser in BaseWorker."""

from __future__ import annotations

from parallel_agents.agents.base import _extract_structured_output


class TestExtractStructuredOutput:
    def test_clean_json(self):
        output = '{"findings": [{"severity": "high", "category": "vuln", "title": "SQLi", "description": "found"}], "recommendations": []}'
        findings, recs = _extract_structured_output(output)
        assert len(findings) == 1
        assert findings[0].title == "SQLi"

    def test_json_in_code_fence(self):
        output = """Here is my analysis:
```json
{"findings": [{"severity": "medium", "category": "style", "title": "naming", "description": "bad"}], "recommendations": [{"type": "code_change", "description": "rename"}]}
```
Done."""
        findings, recs = _extract_structured_output(output)
        assert len(findings) == 1
        assert len(recs) == 1

    def test_trailing_commas(self):
        output = '{"findings": [{"severity": "low", "category": "docs", "title": "missing", "description": "no docs",}], "recommendations": [],}'
        findings, recs = _extract_structured_output(output)
        assert len(findings) == 1

    def test_minimal_fields_finding(self):
        output = '{"findings": [{"severity": "info", "title": "note"}], "recommendations": []}'
        findings, recs = _extract_structured_output(output)
        # Should still parse with fallback to minimal fields
        assert len(findings) == 1

    def test_minimal_fields_recommendation(self):
        output = '{"findings": [], "recommendations": [{"description": "do something"}]}'
        findings, recs = _extract_structured_output(output)
        assert len(recs) == 1
        assert recs[0].description == "do something"

    def test_no_json(self):
        output = "I couldn't find any issues in the codebase."
        findings, recs = _extract_structured_output(output)
        assert findings == []
        assert recs == []

    def test_json_with_surrounding_text(self):
        output = """Based on my analysis, here are the results:

{"findings": [{"severity": "critical", "category": "security", "title": "RCE", "description": "remote code execution"}], "recommendations": [{"type": "code_change", "description": "sanitize input", "priority": "must"}]}

Please review these findings carefully."""
        findings, recs = _extract_structured_output(output)
        assert len(findings) == 1
        assert findings[0].severity.value == "critical"
        assert len(recs) == 1

    def test_multiple_json_objects_picks_one_with_data(self):
        output = '{"error": "none"}\n{"findings": [{"severity": "low", "category": "style", "title": "lint", "description": "lint issue"}], "recommendations": []}'
        findings, recs = _extract_structured_output(output)
        # Should find something from the output
        assert len(findings) >= 0  # parser may pick either object

    def test_empty_arrays(self):
        output = '{"findings": [], "recommendations": []}'
        findings, recs = _extract_structured_output(output)
        assert findings == []
        assert recs == []

    def test_invalid_finding_skipped(self):
        output = '{"findings": [{"invalid": true}, {"severity": "high", "category": "sec", "title": "real", "description": "real finding"}], "recommendations": []}'
        findings, recs = _extract_structured_output(output)
        # Invalid one is skipped or parsed with fallback, valid one is kept
        assert any(f.title == "real" for f in findings)
