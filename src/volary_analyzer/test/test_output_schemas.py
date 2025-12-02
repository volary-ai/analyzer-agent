"""Tests for output_schemas.py."""

import json
from pathlib import Path

from ..output_schemas import TechDebtAnalysis, TechDebtIssue


class TestBackwardsCompatibility:
    """Tests for backwards compatibility of schema changes."""

    def test_parse_all_testdata_files(self) -> None:
        """Test that all JSON files in testdata/ can be parsed successfully."""
        testdata_dir = Path("src/test/testdata")
        json_files = list(testdata_dir.glob("*.json"))

        assert len(json_files) > 0, "No JSON files found in testdata/"

        for json_file in json_files:
            with open(json_file) as f:
                data = json.load(f)

            # Should parse without errors
            analysis = TechDebtAnalysis.model_validate(data)

            # Should have at least one issue
            assert len(analysis.issues) > 0, f"{json_file.name} has no issues"

            # All issues should have required fields populated
            for issue in analysis.issues:
                assert issue.title, f"Issue in {json_file.name} has no title"
                assert issue.short_description, f"Issue in {json_file.name} has no short_description"
                # impact and recommended_action can be defaults, just verify they exist
                assert issue.impact is not None, f"Issue in {json_file.name} has None impact"
                assert issue.recommended_action is not None, f"Issue in {json_file.name} has None recommended_action"

    def test_old_schema_with_description_field(self) -> None:
        """Test that old schema with 'description' field maps to 'short_description'."""
        old_format = {
            "title": "Test Issue",
            "description": "This is the old description field",
            "kind": "Bug",
        }

        issue = TechDebtIssue.model_validate(old_format)

        assert issue.title == "Test Issue"
        assert issue.short_description == "This is the old description field"
        assert issue.impact == "Not specified"  # default
        assert issue.recommended_action == "See description for details"  # default

    def test_new_schema_with_all_fields(self) -> None:
        """Test that new schema with all fields works correctly."""
        new_format = {
            "title": "Test Issue",
            "short_description": "Brief description",
            "impact": "High impact",
            "recommended_action": "Fix it in file.py:123",
            "files": ["file.py"],
        }

        issue = TechDebtIssue.model_validate(new_format)

        assert issue.title == "Test Issue"
        assert issue.short_description == "Brief description"
        assert issue.impact == "High impact"
        assert issue.recommended_action == "Fix it in file.py:123"
        assert issue.files == ["file.py"]
