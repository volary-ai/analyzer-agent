"""Tests for print_issues.py."""

from ..print_issues import render_summary_markdown


class TestRenderSummaryMarkdown:

    def smoke_test_no_eval(self):
        """Test that we can successfully render something on non-evaluated issues."""
        with open("src/volary_analyzer/test/testdata/please-issues.json") as f:
            analysis = tech_debt_analysis.model_validate_json(f.read())
        md = render_summary_markdown(analysis)
        assert md.startswith('|')
        assert md.endswith('|')
        assert 'Evaluation' not in md

    def smoke_test_eval(self):
        """Test that we can successfully render something on evaluated issues."""
        with open("src/volary_analyzer/test/testdata/please-issues-evaluated.json") as f:
            analysis = tech_debt_analysis.model_validate_json(f.read())
        md = render_summary_markdown(analysis)
        assert md.startswith('|')
        assert md.endswith('|')
        assert 'Evaluation' in md
