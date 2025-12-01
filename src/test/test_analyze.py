from ..analyze import get_repo_context


class TestGetRepoContext:
    """Tests for get_repo_context."""

    def test_read_files(self):
        context = get_repo_context(
            readme_md="src/test/testdata/README.md",
            claude_md="src/test/testdata/CLAUDE.md",
            agents_md="src/test/testdata/AGENTS.md",
        )
        assert "README.md was read correctly" in context
        assert "CLAUDE.md was read correctly" in context
        assert "AGENTS.md was read correctly" in context
