import os
from pathlib import Path

import pytest

from ..tools import _should_ignore, grep, ls, read_file


class TestReadFile:
    """Tests for the read_file function."""

    def test_read_file_basic(self, tmp_path: Path) -> None:
        """Test basic file reading."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        # Change to tmp directory to test relative paths
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = read_file("test.txt")
            assert "line 1" in result
            assert "line 2" in result
            assert "line 3" in result
        finally:
            os.chdir(original_dir)

    def test_read_file_with_line_range(self, tmp_path: Path) -> None:
        """Test reading a specific line range."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = read_file("test.txt", from_line="2", to_line="4")
            lines = result.split("\n")
            # Should only have lines 2-4
            assert len([line for line in lines if line.strip()]) >= 3
            assert "line 2" in result
            assert "line 3" in result
            assert "line 4" in result
            assert "line 1" not in result or lines[0].strip() == ""
            assert "line 5" not in result
        finally:
            os.chdir(original_dir)

    def test_read_file_nonexistent(self) -> None:
        """Test reading a nonexistent file raises an error."""
        with pytest.raises(FileNotFoundError):
            read_file("nonexistent_file_12345.txt")

    def test_read_file_with_git_blame_testdata(self) -> None:
        """Test reading a tracked file includes git blame information."""
        result = read_file("src/test/testdata/please-issues.json", from_line="1", to_line="10")

        # Should contain JSON content
        assert "{" in result or "issues" in result

        # Git blame output includes dates or commit info
        # Even if git blame fails, we should get line numbers with → separator
        assert "→" in result or "(" in result

    def test_read_file_testdata_full_file(self) -> None:
        """Test reading full testdata file."""
        result = read_file("src/test/testdata/please-issues.json")

        # Should contain the JSON structure
        assert "issues" in result
        assert "title" in result
        assert "description" in result

    def test_read_file_testdata_line_range(self) -> None:
        """Test reading a specific line range from testdata."""
        result = read_file("src/test/testdata/volary-v1.json", from_line="1", to_line="20")

        lines = result.split("\n")
        # Should have content but be limited
        assert len(lines) <= 25  # Some buffer for formatting
        assert "{" in result  # JSON structure


class TestLsFunction:
    """Tests for the ls function with gitignore filtering."""

    def test_ls_basic(self, tmp_path: Path) -> None:
        """Test basic file listing."""
        # Create test files
        (tmp_path / "file1.py").write_text("test")
        (tmp_path / "file2.py").write_text("test")
        (tmp_path / "file3.txt").write_text("test")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = ls("*.py")
            assert "file1.py" in result
            assert "file2.py" in result
            assert "file3.txt" not in result
        finally:
            os.chdir(original_dir)

    def test_ls_recursive(self, tmp_path: Path) -> None:
        """Test recursive file listing."""
        # Create nested structure
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "file1.py").write_text("test")
        (tmp_path / "dir2").mkdir()
        (tmp_path / "dir2" / "file2.py").write_text("test")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = ls("**/*.py")
            assert any("file1.py" in f for f in result)
            assert any("file2.py" in f for f in result)
        finally:
            os.chdir(original_dir)

    def test_ls_filters_node_modules(self, tmp_path: Path) -> None:
        """Test that node_modules is filtered out."""
        (tmp_path / "good_file.py").write_text("test")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "bad_file.py").write_text("test")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = ls("**/*.py")
            assert "good_file.py" in result
            assert not any("node_modules" in f for f in result)
        finally:
            os.chdir(original_dir)

    def test_ls_filters_pycache(self, tmp_path: Path) -> None:
        """Test that __pycache__ is filtered out."""
        (tmp_path / "good_file.py").write_text("test")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "bad_file.pyc").write_text("test")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = ls("**/*")
            assert "good_file.py" in result
            assert not any("__pycache__" in f for f in result)
        finally:
            os.chdir(original_dir)

    def test_ls_respects_gitignore(self, tmp_path: Path) -> None:
        """Test that .gitignore patterns are respected."""
        (tmp_path / ".gitignore").write_text("ignored_dir/\n*.ignored\n")
        (tmp_path / "good_file.py").write_text("test")
        (tmp_path / "ignored_dir").mkdir()
        (tmp_path / "ignored_dir" / "bad_file.py").write_text("test")
        (tmp_path / "test.ignored").write_text("test")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Reset the cached gitignore spec
            import src.tools as tools

            tools._gitignore_spec = None

            result = ls("**/*")
            assert "good_file.py" in result
            # The ignored directory itself might show up, but files inside it should not
            assert not any("bad_file.py" in f for f in result)
            assert "test.ignored" not in result
        finally:
            os.chdir(original_dir)


class TestGrepFunction:
    """Tests for the grep function."""

    def setup_git_repo(self, tmp_path: Path) -> str:
        """Helper to set up a git repo for testing."""
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        os.system("git init -q")
        os.system("git config user.email 'test@test.com'")
        os.system("git config user.name 'Test User'")
        return original_dir

    def test_grep_basic(self, tmp_path: Path) -> None:
        """Test basic grep functionality."""
        (tmp_path / "test.py").write_text("import os\nimport sys\nprint('hello')")

        original_dir = self.setup_git_repo(tmp_path)
        try:
            os.system("git add test.py")
            result = grep("import", ".", "*.py")
            assert "import os" in result
            assert "import sys" in result
            assert "print" not in result
        finally:
            os.chdir(original_dir)

    def test_grep_with_pattern(self, tmp_path: Path) -> None:
        """Test grep with regex pattern."""
        (tmp_path / "test.py").write_text("def foo():\n    pass\ndef bar():\n    pass\nclass Baz:\n    pass")

        original_dir = self.setup_git_repo(tmp_path)
        try:
            os.system("git add test.py")
            result = grep("def.*:", ".", "*.py")
            assert "def foo" in result
            assert "def bar" in result
            assert "class Baz" not in result
        finally:
            os.chdir(original_dir)

    def test_grep_no_matches(self, tmp_path: Path) -> None:
        """Test grep with no matches."""
        (tmp_path / "test.py").write_text("print('hello')")

        original_dir = self.setup_git_repo(tmp_path)
        try:
            os.system("git add test.py")
            result = grep("nonexistent_pattern_xyz", ".", "*.py")
            assert "No matches found" in result
        finally:
            os.chdir(original_dir)

    def test_grep_respects_gitignore(self, tmp_path: Path) -> None:
        """Test that grep respects .gitignore (via git grep)."""
        (tmp_path / ".gitignore").write_text("ignored.py\n")
        (tmp_path / "good.py").write_text("TODO: fix this")
        (tmp_path / "ignored.py").write_text("TODO: this should not appear")

        original_dir = self.setup_git_repo(tmp_path)
        try:
            os.system("git add .gitignore good.py")
            result = grep("TODO", ".", "*.py")
            assert "good.py" in result
            assert "ignored.py" not in result
        finally:
            os.chdir(original_dir)


class TestShouldIgnore:
    """Tests for the _should_ignore helper function."""

    def test_ignores_node_modules(self) -> None:
        """Test that node_modules paths are ignored."""
        assert _should_ignore("node_modules/package/file.js")
        assert _should_ignore("src/node_modules/file.js")

    def test_ignores_git(self) -> None:
        """Test that .git paths are ignored."""
        assert _should_ignore(".git/config")
        assert _should_ignore("subdir/.git/hooks/pre-commit")

    def test_ignores_pycache(self) -> None:
        """Test that __pycache__ paths are ignored."""
        assert _should_ignore("__pycache__/module.pyc")
        assert _should_ignore("src/__pycache__/test.pyc")

    def test_ignores_venv(self) -> None:
        """Test that virtual env paths are ignored."""
        assert _should_ignore(".venv/lib/python3.10/site-packages")
        assert _should_ignore("venv/bin/activate")

    def test_allows_normal_files(self) -> None:
        """Test that normal files are not ignored."""
        assert not _should_ignore("src/main.py")
        assert not _should_ignore("README.md")
        assert not _should_ignore("tests/test_main.py")
