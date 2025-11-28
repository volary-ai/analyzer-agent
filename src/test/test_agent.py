import json

from ..agent import (
    TODO,
    Agent,
    ToolCall,
    ToolFunction,
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

    def test_unknown_type_defaults_to_string(self) -> None:
        """Test that unknown types default to string."""

        class CustomType:
            pass

        json_type, items = _python_type_to_json_schema(CustomType)
        assert json_type == "string"
        assert items is None


class TestToolCalling:
    """Tests for tool calling behavior."""

    def test_call_tool_success(self) -> None:
        """Test that _call_tool executes a tool and returns the correct result."""

        def dummy_tool(name: str, count: int) -> str:
            """A dummy tool for testing."""
            return f"Called with {name} x {count}"

        agent = Agent(
            instruction="Test agent",
            tools=[dummy_tool],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        tool_call = ToolCall(
            id="call_123",
            function=ToolFunction(name="dummy_tool", arguments='{"name": "test", "count": 5}'),
            type="function",
        )

        result = agent._call_tool(dummy_tool, tool_call)

        assert result.tool_name == "dummy_tool"
        assert result.tool_id == "call_123"
        assert result.tool_args == {"name": "test", "count": 5}
        assert result.error is None
        assert result.message["role"] == "tool"
        assert result.message["tool_call_id"] == "call_123"
        assert result.message["content"] == "Called with test x 5"

    def test_call_tool_returns_dict(self) -> None:
        """Test that _call_tool handles tools that return dicts."""

        def dict_tool() -> dict:
            """A tool that returns a dict."""
            return {"status": "success", "count": 42}

        agent = Agent(
            instruction="Test agent",
            tools=[dict_tool],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        tool_call = ToolCall(
            id="call_456",
            function=ToolFunction(name="dict_tool", arguments="{}"),
            type="function",
        )

        result = agent._call_tool(dict_tool, tool_call)

        # Should be JSON serialized
        assert result.error is None
        content = json.loads(result.message["content"])
        assert content["status"] == "success"
        assert content["count"] == 42

    def test_call_tool_with_error(self) -> None:
        """Test that _call_tool handles errors correctly."""

        def failing_tool() -> str:
            """A tool that always fails."""
            raise ValueError("Something went wrong")

        agent = Agent(
            instruction="Test agent",
            tools=[failing_tool],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        tool_call = ToolCall(
            id="call_error",
            function=ToolFunction(name="failing_tool", arguments="{}"),
            type="function",
        )

        result = agent._call_tool(failing_tool, tool_call)

        assert result.error is not None
        assert isinstance(result.error, ValueError)
        assert result.message["role"] == "tool"
        assert result.message["tool_call_id"] == "call_error"
        assert "Something went wrong" in result.message["content"]

    def test_call_tools_updates_messages(self) -> None:
        """Test that _call_tools properly updates the messages list."""

        def tool_a(value: str) -> str:
            return f"A: {value}"

        def tool_b(number: int) -> str:
            return f"B: {number}"

        agent = Agent(
            instruction="Test agent",
            tools=[tool_a, tool_b],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        tool_calls_raw = [
            {
                "id": "call_a",
                "type": "function",
                "function": {"name": "tool_a", "arguments": '{"value": "hello"}'},
            },
            {
                "id": "call_b",
                "type": "function",
                "function": {"name": "tool_b", "arguments": '{"number": 42}'},
            },
        ]

        agent._call_tools(tool_calls_raw)

        # Should have 2 tool response messages
        assert len(agent.messages) == 2

        # Check first message
        assert agent.messages[0]["role"] == "tool"
        assert agent.messages[0]["tool_call_id"] == "call_a"
        assert "A: hello" in agent.messages[0]["content"]

        # Check second message
        assert agent.messages[1]["role"] == "tool"
        assert agent.messages[1]["tool_call_id"] == "call_b"
        assert "B: 42" in agent.messages[1]["content"]

    def test_call_tools_filters_pseudo_tools(self) -> None:
        """Test that _call_tools doesn't execute pseudo-tools as regular tools."""

        def real_tool() -> str:
            return "real result"

        agent = Agent(
            instruction="Test agent",
            tools=[real_tool],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        tool_calls_raw = [
            {
                "id": "call_update",
                "type": "function",
                "function": {
                    "name": "update_user",
                    "arguments": '{"msg": "Working on it..."}',
                },
            },
            {
                "id": "call_real",
                "type": "function",
                "function": {"name": "real_tool", "arguments": "{}"},
            },
        ]

        agent._call_tools(tool_calls_raw)

        # Should have messages for update_user and real_tool
        assert len(agent.messages) == 2

        # update_user message should be first
        assert agent.messages[0]["tool_call_id"] == "call_update"
        assert "displayed to user successfully" in agent.messages[0]["content"].lower()

        # real_tool message should be second
        assert agent.messages[1]["tool_call_id"] == "call_real"
        assert agent.messages[1]["content"] == "real result"

    def test_call_tools_with_empty_list(self) -> None:
        """Test that _call_tools handles empty tool call lists."""

        agent = Agent(
            instruction="Test agent",
            tools=[],
            model="test-model",
            endpoint="http://test",
            api_key="test-key",
        )

        agent._call_tools([])

        assert len(agent.messages) == 0
