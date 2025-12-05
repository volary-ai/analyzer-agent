from pydantic import BaseModel, Field

from ..agent import (
    TODO,
)
from ..completion_api import (
    _python_type_to_json_schema,
    tool_prompt,
)


class TestToolPrompt:
    """Tests for the tool_prompt function."""

    def test_tool_prompt_basic_function(self) -> None:
        """Test tool_prompt with a basic function."""

        def simple_tool(name: str, count: int = 5) -> str:
            """
            A simple test tool.

            :param name: The name parameter
            :param count: The count parameter
            :return: A result string
            """
            return f"Result: {name} x {count}"

        result = tool_prompt(simple_tool)

        assert result["type"] == "function"
        assert result["function"]["name"] == "simple_tool"
        assert "simple test tool" in result["function"]["description"].lower()

        params = result["function"]["parameters"]
        assert params["type"] == "object"
        assert "name" in params["properties"]
        assert "count" in params["properties"]

        # name is required (no default), count is optional (has default)
        assert "name" in params["required"]
        assert "count" not in params["required"]

        # Check types
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["count"]["type"] == "integer"

    def test_tool_prompt_with_list_of_dicts(self) -> None:
        """Test tool_prompt with List[Dict] parameter."""

        def list_tool(items: list[dict]) -> str:
            """
            A tool that takes a list of dicts.

            :param items: List of items
            :return: Result
            """
            return "done"

        result = tool_prompt(list_tool)

        params = result["function"]["parameters"]
        assert params["properties"]["items"]["type"] == "array"
        assert params["properties"]["items"]["items"]["type"] == "object"

    def test_tool_prompt_with_typed_dict(self) -> None:
        """Test tool_prompt with List[TODO] parameter."""

        def set_todos(todos: list[TODO]) -> str:
            """
            Updates the TODO list.

            :param todos: The complete list of TODO items
            :return: Confirmation message
            """
            return "updated"

        result = tool_prompt(set_todos)

        params = result["function"]["parameters"]
        assert params["properties"]["todos"]["type"] == "array"

        # Check that the array items have the TODO structure
        items = params["properties"]["todos"]["items"]
        assert items["type"] == "object"
        assert "content" in items["properties"]
        assert "status" in items["properties"]
        assert items["properties"]["content"]["type"] == "string"
        assert items["properties"]["status"]["type"] == "string"

        # Check required fields
        assert "content" in items["required"]
        assert "status" in items["required"]

    def test_tool_prompt_with_no_params(self) -> None:
        """Test tool_prompt with a function that has no parameters."""

        def no_params() -> str:
            """A function with no parameters."""
            return "done"

        result = tool_prompt(no_params)

        params = result["function"]["parameters"]
        assert params["properties"] == {}
        assert params["required"] == []

    def test_tool_prompt_with_pydantic_model(self) -> None:
        """Test tool_prompt with a Pydantic BaseModel parameter."""

        class TestIssue(BaseModel):
            """A test issue model."""

            title: str = Field(description="The issue title")
            description: str = Field(description="Issue description")
            priority: int = Field(description="Priority level")
            tags: list[str] = Field(default=[], description="Issue tags")

        def report_issue(issue: TestIssue) -> str:
            """
            Report an issue for evaluation.

            :param issue: The issue to report
            :return: Evaluation result
            """
            return "evaluated"

        result = tool_prompt(report_issue)

        assert result["type"] == "function"
        assert result["function"]["name"] == "report_issue"

        params = result["function"]["parameters"]
        assert params["type"] == "object"
        assert "issue" in params["properties"]

        # Check that the issue parameter has the full Pydantic schema inlined
        issue_schema = params["properties"]["issue"]
        assert issue_schema["type"] == "object"
        assert "properties" in issue_schema
        assert "title" in issue_schema["properties"]
        assert "description" in issue_schema["properties"]
        assert "priority" in issue_schema["properties"]
        assert "tags" in issue_schema["properties"]

        # Verify field types
        assert issue_schema["properties"]["title"]["type"] == "string"
        assert issue_schema["properties"]["description"]["type"] == "string"
        assert issue_schema["properties"]["priority"]["type"] == "integer"
        assert issue_schema["properties"]["tags"]["type"] == "array"
        assert issue_schema["properties"]["tags"]["items"]["type"] == "string"

        # Check required fields (tags has default, so not required)
        assert "required" in issue_schema
        assert "title" in issue_schema["required"]
        assert "description" in issue_schema["required"]
        assert "priority" in issue_schema["required"]
        assert "tags" not in issue_schema["required"]


class TestPythonTypeToJsonSchema:
    """Tests for the _python_type_to_json_schema function."""

    def test_basic_types(self) -> None:
        """Test conversion of basic Python types."""
        assert _python_type_to_json_schema(str) == ("string", None)
        assert _python_type_to_json_schema(int) == ("integer", None)
        assert _python_type_to_json_schema(float) == ("number", None)
        assert _python_type_to_json_schema(bool) == ("boolean", None)
        assert _python_type_to_json_schema(dict) == ("object", None)

    def test_list_of_strings(self) -> None:
        """Test List[str] conversion."""
        json_type, items = _python_type_to_json_schema(list[str])
        assert json_type == "array"
        assert items == {"type": "string"}

    def test_list_of_ints(self) -> None:
        """Test List[int] conversion."""
        json_type, items = _python_type_to_json_schema(list[int])
        assert json_type == "array"
        assert items == {"type": "integer"}

    def test_list_of_typed_dict(self) -> None:
        """Test List[TODO] conversion."""
        json_type, items = _python_type_to_json_schema(list[TODO])
        assert json_type == "array"
        assert items["type"] == "object"
        assert "content" in items["properties"]
        assert "status" in items["properties"]
        assert items["properties"]["content"]["type"] == "string"
        assert items["properties"]["status"]["type"] == "string"
        assert "content" in items["required"]
        assert "status" in items["required"]

    def test_optional_types(self) -> None:
        """Test that Optional types (Union with None) extract the correct base type."""
        # Test int | None (Python 3.10+ syntax)
        json_type, items = _python_type_to_json_schema(int | None)
        assert json_type == "integer", "int | None should return 'integer', not 'string'"
        assert items is None

        # Test str | None
        json_type, items = _python_type_to_json_schema(str | None)
        assert json_type == "string"
        assert items is None

        # Test float | None
        json_type, items = _python_type_to_json_schema(float | None)
        assert json_type == "number"
        assert items is None

        # Test bool | None
        json_type, items = _python_type_to_json_schema(bool | None)
        assert json_type == "boolean"
        assert items is None

    def test_pydantic_basemodel(self) -> None:
        """Test that Pydantic BaseModel types are converted to full schemas."""

        class SimpleModel(BaseModel):
            """A simple test model."""

            name: str
            count: int

        json_type, schema = _python_type_to_json_schema(SimpleModel)

        # Should return "object" as the type
        assert json_type == "object"

        # Should return the full Pydantic schema
        assert schema is not None
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert "required" in schema
        assert "name" in schema["required"]
        assert "count" in schema["required"]
