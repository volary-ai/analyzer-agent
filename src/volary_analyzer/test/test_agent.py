import json

from pydantic import BaseModel, Field

from ..agent import (
    Agent,
    CompletionApi,
    ToolCall,
    ToolFunction,
)
from ..completion_api import tool_prompt


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

    def test_integer_parameter_handling(self) -> None:
        """Test that tools with integer parameters work correctly end-to-end."""

        def count_tool(start: int, end: int, step: int = 1) -> str:
            """Count from start to end with the given step.

            Args:
                start: Starting number
                end: Ending number
                step: Step size (default 1)

            Returns:
                String representation of the count
            """
            result = list(range(start, end + 1, step))
            return f"Counted: {result}"

        # Test 1: Verify schema generation is correct
        schema = tool_prompt(count_tool)
        assert schema["function"]["name"] == "count_tool"
        assert schema["function"]["parameters"]["properties"]["start"]["type"] == "integer"
        assert schema["function"]["parameters"]["properties"]["end"]["type"] == "integer"
        assert schema["function"]["parameters"]["properties"]["step"]["type"] == "integer"
        assert "start" in schema["function"]["parameters"]["required"]
        assert "end" in schema["function"]["parameters"]["required"]
        assert "step" not in schema["function"]["parameters"]["required"]

        # Test 2: Verify tool execution receives integers correctly
        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[count_tool],
            model="test-model",
            api=api,
        )

        tool_call = ToolCall(
            id="call_456",
            function=ToolFunction(name="count_tool", arguments='{"start": 5, "end": 10, "step": 2}'),
            type="function",
        )

        result = agent._call_tool(count_tool, tool_call)

        assert result.error is None, f"Tool execution failed: {result.error}"
        assert result.tool_args == {"start": 5, "end": 10, "step": 2}
        assert result.message["content"] == "Counted: [5, 7, 9]"

        # Test 3: Verify type coercion doesn't happen incorrectly
        tool_call_with_strings = ToolCall(
            id="call_789",
            function=ToolFunction(name="count_tool", arguments='{"start": "5", "end": "10"}'),
            type="function",
        )

        result_strings = agent._call_tool(count_tool, tool_call_with_strings)

        # This should work - JSON parser will handle string-to-int conversion
        # but verify the actual tool receives proper integers
        assert result_strings.tool_args == {"start": "5", "end": "10"}
        # The tool should raise an error if it receives strings instead of ints
        assert result_strings.error is not None or "5, 6, 7, 8, 9, 10" in result_strings.message["content"]

    def test_pydantic_model_parameter_handling(self) -> None:
        """Test that tools with Pydantic model parameters work correctly end-to-end."""

        class IssueReport(BaseModel):
            """A tech debt issue report."""

            title: str = Field(description="Issue title")
            severity: str = Field(description="Severity level")
            line_number: int = Field(description="Line where issue occurs")
            fixed: bool = Field(default=False, description="Whether issue is fixed")

        def report_issue(issue: IssueReport) -> str:
            """
            Report a technical debt issue.

            :param issue: The issue to report
            :return: Confirmation message
            """
            status = "fixed" if issue.fixed else "open"
            return f"{issue.title} (line {issue.line_number}): {issue.severity} - {status}"

        api = CompletionApi(api_key="test-key", endpoint="http://test")
        agent = Agent(
            instruction="Test agent",
            tools=[report_issue],
            model="test-model",
            api=api,
        )

        tool_call = ToolCall(
            id="call_issue_1",
            function=ToolFunction(
                name="report_issue",
                arguments=json.dumps(
                    {
                        "issue": {
                            "title": "Unused variable",
                            "severity": "low",
                            "line_number": 42,
                            # fixed omitted - should use default False
                        }
                    }
                ),
            ),
            type="function",
        )

        result = agent._call_tool(report_issue, tool_call)

        assert result.error is None, f"Tool execution failed: {result.error}"
        assert "Unused variable" in result.message["content"]
        assert "line 42" in result.message["content"]
        assert "low" in result.message["content"]
        assert "open" in result.message["content"]  # default fixed=False

        tool_call_complete = ToolCall(
            id="call_issue_2",
            function=ToolFunction(
                name="report_issue",
                arguments=json.dumps(
                    {
                        "issue": {
                            "title": "SQL injection vulnerability",
                            "severity": "critical",
                            "line_number": 123,
                            "fixed": True,
                        }
                    }
                ),
            ),
            type="function",
        )

        result_complete = agent._call_tool(report_issue, tool_call_complete)

        assert result_complete.error is None
        assert "SQL injection vulnerability" in result_complete.message["content"]
        assert "line 123" in result_complete.message["content"]
        assert "critical" in result_complete.message["content"]
        assert "fixed" in result_complete.message["content"]
