import json

from ..agent import (
    Agent,
    CompletionApi,
    ToolCall,
    ToolFunction,
)


class TestToolCalling:
    """Tests for tool calling behavior."""

    def test_call_tool_success(self) -> None:
        """Test that _call_tool executes a tool and returns the correct result."""

        def dummy_tool(name: str, count: int) -> str:
            """A dummy tool for testing."""
            return f"Called with {name} x {count}"

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[dummy_tool],
            model="test-model",
            api=api,
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

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[dict_tool],
            model="test-model",
            api=api,
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

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[failing_tool],
            model="test-model",
            api=api,
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

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[tool_a, tool_b],
            model="test-model",
            api=api,
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

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[real_tool],
            model="test-model",
            api=api,
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

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[],
            model="test-model",
            api=api,
        )

        agent._call_tools([])

        assert len(agent.messages) == 0
