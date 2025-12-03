"""Tests for print_issues.py."""

from ..output_schemas import EvaluatedTechDebtAnalysis, TechDebtAnalysis
from ..print_issues import render_summary_markdown


class TestRenderSummaryMarkdown:
    def test_no_eval(self):
        """Test that we can successfully render something on non-evaluated issues."""
        with open("src/volary_analyzer/test/testdata/please-issues.json") as f:
            analysis = TechDebtAnalysis.model_validate_json(f.read())
        md = render_summary_markdown(analysis)
        assert md.startswith("|")
        assert md.endswith("|")
        assert "Evaluation" not in md

    def test_eval(self):
        """Test that we can successfully render something on evaluated issues."""
        with open("src/volary_analyzer/test/testdata/please-issues-evaluated.json") as f:
            analysis = EvaluatedTechDebtAnalysis.model_validate_json(f.read())
        md = render_summary_markdown(analysis)
        assert md.startswith("|")
        assert md.endswith("|")
        assert "Evaluation" in md

    def test_render_links(self):
        """Test that we can render GitHub source links in the markdown."""
        with open("src/volary_analyzer/test/testdata/minimal-evaluated.json") as f:
            analysis = EvaluatedTechDebtAnalysis.model_validate_json(f.read())
        md = render_summary_markdown(
            analysis,
            repo="thought-machine/please",
            revision="master",
            files={
                "go.mod",
                "src/cli/logging.go",
                "src/cli/logging/logging.go",
                "tools/build_langserver/langserver_main.go",
            },
        )
        assert "Go mod: [go.mod:59](https://github.com/thought-machine/please/blob/master/go.mod#L59)" in md
        assert (
            "Code file: [src/cli/logging.go](https://github.com/thought-machine/please/blob/master/src/cli/logging.go)"
            in md
        )
        assert (
            "Code file with line: [src/cli/logging/logging.go:64](https://github.com/thought-machine/please/blob/master/src/cli/logging/logging.go#L64)"
            in md
        )
        assert (
            "Code file with multiple lines: [tools/build_langserver/langserver_main.go:43-54](https://github.com/thought-machine/please/blob/master/tools/build_langserver/langserver_main.go#L43-L54)"
            in md
        )
        assert "Not a package: crypto/rand.Read" in md
        assert "Also not a package: dev/build" in md
