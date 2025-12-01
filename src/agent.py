"""
Analyzer agent - generates technical debt issues from a codebase.
"""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import (
    Self,
    TypedDict,
    TypeVar,
    overload,
)

from pydantic import BaseModel
from rich.console import Console
from rich.markup import escape

from .completion_api import CompletionApi

TBaseModel = TypeVar("TBaseModel", bound=BaseModel)

_UPDATE_USER_FUNC_NAME = "update_user"
_SET_TODOS_FUNC_NAME = "set_todos"

console = Console(stderr=True)


class AgentError(Exception):
    """Base exception for Agent-related errors."""


class MaxIterationsReachedError(AgentError):
    """Raised when the agent reaches the maximum number of iterations."""


class EmptyResponseError(AgentError):
    """Raised when the agent returns an empty response."""

class BadFinishReason(AgentError):
    """Raised when the agent reaches a bad finish reason."""
    def __init__(self, reason: str):
        super().__init__(f"Agent completed with unexpected finish reason: {reason}")
        self.reason = reason

# This is a virtual function all agents have access to, to keep the user updated
def update_user(msg: str) -> None:
    """
    Keeps the user up to date with your current thinking as you explore the repository.

    <good-usage reason="short and addressing the user">
    Let me identify key areas of tech debt in the repo. Let's start with gathering some basic information.
    </good-usage>

    <bad-usage reason="longer and addressing self>
    We are tasked with identifying key areas of tech debt in the repo. We should start by gathering information about
    the structure of the repo and then produce an actionable list of the most pertinent issues.
    </bad-usage>

    Usage notes:
    - Keep the message reasonably short (around 200 characters max)
    - Address the user as if they've asked you to perform this task

    :param msg: The message to display to the user
    """
    pass


@dataclass
class ToolFunction:
    """Represents the function part of a tool call."""

    name: str
    arguments: str  # JSON string

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Construct from API response dict."""
        return cls(name=data["name"], arguments=data["arguments"])


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""

    id: str
    function: ToolFunction
    type: str  # Always "function"

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Construct from API response dict."""
        return cls(
            id=data["id"],
            function=ToolFunction.from_dict(data["function"]),
            type=data.get("type", "function"),
        )


class ToolMessage(TypedDict):
    """Represents a tool response message."""

    role: str  # Always "tool"
    tool_call_id: str
    content: str


@dataclass
class ToolCallResult:
    """Result of executing a single tool call."""

    call: ToolCall
    message: ToolMessage = None
    error: Exception = None

    @property
    def tool_name(self) -> str:
        """Get the tool name from the call."""
        return self.call.function.name

    @property
    def tool_id(self) -> str:
        """Get the tool call ID."""
        return self.call.id

    @property
    def tool_args(self) -> dict:
        """Get the parsed tool arguments."""
        return json.loads(self.call.function.arguments)


class TODO(TypedDict):
    """Represents a single TODO item."""

    content: str
    status: str  # "pending", "in_progress", or "completed"


@dataclass
class Agent:
    instruction: str
    tools: list[Callable]
    model: str
    api: CompletionApi
    agent_name: str = "Agent"
    todos: list = None
    max_iterations: int = 50
    max_retries_on_empty: int = 2  # Number of times to retry on empty response
    task: str = ""

    def __post_init__(self):
        # Store messages from last run for continuation
        self.messages = []

    def _call_tool(self, tool: Callable, tool_call: ToolCall) -> ToolCallResult:
        """Execute a single tool call and return the result."""
        tool_args = json.loads(tool_call.function.arguments)

        try:
            tool_result = tool(**tool_args)

            # Convert result to string if needed
            if isinstance(tool_result, str):
                content = tool_result
            else:
                content = json.dumps(tool_result)

            return ToolCallResult(
                call=tool_call,
                message={
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": content,
                },
            )

        except Exception as e:
            return ToolCallResult(
                call=tool_call,
                error=e,
                message={
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"Error: {str(e)}",
                },
            )

    def _maybe_update_user(self, tool_calls: list[ToolCall]) -> None:
        update_user_call = next(
            (tool_call for tool_call in tool_calls if tool_call.function.name == _UPDATE_USER_FUNC_NAME),
            None,  # default if no match
        )
        if not update_user_call:
            return

        tool_args = json.loads(update_user_call.function.arguments)
        tool_id = update_user_call.id

        # Print the user update in bold white
        msg = tool_args.get("msg", "")
        if msg:
            console.print(f"\n[bold white]{escape(msg)}[/bold white]")

        # Add success response to messages
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": "Message displayed to user successfully.",
            }
        )

    def _maybe_set_todos(self, tool_calls: list[ToolCall]) -> None:
        """Handle set_todos pseudo-tool calls."""
        set_todos_call = next(
            (tool_call for tool_call in tool_calls if tool_call.function.name == _SET_TODOS_FUNC_NAME),
            None,  # default if no match
        )
        if not set_todos_call:
            return

        result = self._call_tool(self.set_todos, set_todos_call)
        self.messages.append(result.message)

        self._render_todos()

    def _call_tools(self, tool_calls_raw: list[dict]) -> None:
        """Execute tool calls from the LLM."""
        tool_calls = [ToolCall.from_dict(tc) for tc in tool_calls_raw]

        tool_map = {tool.__name__: tool for tool in self.tools}
        # Add set_todos as a special method-based tool
        tool_map["set_todos"] = self.set_todos

        # Handle pseudo-tools first (they print before actual tool execution logs)
        self._maybe_update_user(tool_calls)
        self._maybe_set_todos(tool_calls)

        # Filter to actual tool calls (excluding pseudo-tools)
        actual_tool_calls = [
            tc for tc in tool_calls if tc.function.name not in [_UPDATE_USER_FUNC_NAME, _SET_TODOS_FUNC_NAME]
        ]

        if len(actual_tool_calls) == 0:
            return

        # Execute all tools in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(actual_tool_calls), 10)) as executor:
            # Submit all tool calls
            future_to_call = {
                executor.submit(self._call_tool, tool_map[tc.function.name], tc): tc for tc in actual_tool_calls
            }

            # Collect results as they complete
            results = []
            for future in as_completed(future_to_call):
                result = future.result()
                results.append(result)

            # Sort by tool_call_id to maintain deterministic ordering
            results.sort(key=lambda r: r.tool_id)

            # Print all results sequentially
            for result in results:
                # Print tool execution info (without agent name, use task if available)
                task_prefix = f"[{self.task}] " if self.task else ""
                console.print(f"\n[dim]{task_prefix}Executing tool: {result.tool_name}[/dim]")
                console.print(f"[dim]Arguments: {json.dumps(result.tool_args, indent=2)}[/dim]")

                if result.error:
                    console.print(f"[dim red]Error: {result.error}[/dim red]")
                else:
                    result_preview = result.message["content"][:200]
                    console.print(
                        f"[dim]Result: {escape(result_preview)}{'...' if len(result.message['content']) > 200 else ''}[/dim]"
                    )

            # Add all messages to the message list
            self.messages.extend([r.message for r in results])

    def _render_todos(self) -> None:
        """Render the current TODO list to the console."""
        console.print("\n[bold cyan]TODO List:[/bold cyan]")
        if self.todos:
            for todo in self.todos:
                status_marker = {
                    "pending": "[ ]",
                    "in_progress": "[→]",
                    "completed": "[✓]",
                }.get(todo["status"], "[ ]")
                status_color = {
                    "pending": "white",
                    "in_progress": "yellow",
                    "completed": "green",
                }.get(todo["status"], "white")
                console.print(f"  [{status_color}]{status_marker} {escape(todo['content'])}[/{status_color}]")
        else:
            console.print("  [dim](empty)[/dim]")

    def set_todos(self, todos: list[TODO]) -> str:
        """
        Updates the TODO list. This completely replaces the existing TODO list.

        Each TODO should have:
        - content: A description of the task
        - status: One of "pending", "in_progress", or "completed"

        :param todos: The complete list of TODO items, replacing any existing TODOs
        :return: Confirmation message
        """
        self.todos = todos
        return f"TODO list updated with {len(todos)} items"

    def _run(
        self,
        task: str = "",
        prompt: str = "",
        output_schema: dict | None = None,
        should_continue: bool = False,
    ) -> str:
        """
        Internal method that runs the agent loop and returns the raw string content.
        Continues from previous messages if they exist.

        :param task: Optional task description for logging
        :param prompt: Optional user prompt to start with
        :param output_schema: Optional JSON schema for structured output
        :return: Raw string content from the LLM
        """
        if not should_continue:
            self.messages = []

        if prompt:
            self.messages.append(
                {
                    "role": "user",
                    "content": prompt,
                }
            )
        self.task = task

        # Print task at the start if provided
        if self.task:
            console.print(f"\n[bold cyan]Task: {escape(self.task)}[/bold cyan]")

        # Prepare response_format if output_schema is provided
        response_format = None
        if output_schema:
            response_format = {"type": "json_schema", "json_schema": output_schema}
        # Call the agent in a loop until the finish reason isn't a tool call.
        for iteration in range(self.max_iterations):
            if self.todos:
                todo_summary = []
                for todo in self.todos:
                    status_marker = {
                        "pending": "[ ]",
                        "in_progress": "[→]",
                        "completed": "[✓]",
                    }.get(todo["status"], "[ ]")
                    todo_summary.append(f"{status_marker} {todo['content']}")

                self.messages.append(
                    {
                        "role": "system",
                        "content": "Reminder: You are currently doing the following:\n" + "\n".join(todo_summary),
                    }
                )
            else:
                self.messages.append(
                    {
                        "role": "system",
                        "content": "Reminder: you currently have no items in your TODO list",
                    }
                )

            # Call the API with response_format from the start
            result = self.api.complete(
                agent_name=self.agent_name,
                model=self.model,
                system_prompt=self.instruction,
                tools=self.tools + [self.set_todos, update_user],
                messages=self.messages,
                response_format=response_format,
            )

            first_choice = result["choices"][0]
            assistant_message = first_choice["message"]
            self.messages.append(assistant_message)

            finish_reason = first_choice.get("finish_reason")
            tool_calls = assistant_message.get("tool_calls")

            if finish_reason == "stop":
                # No more tool calling to do. Return the response.
                content = assistant_message.get("content", "")
                if not content:
                    raise EmptyResponseError(
                        f"Agent completed but returned an empty response. "
                        f"Finish reason: {finish_reason}, Iterations: {iteration + 1}"
                    )

                return content
            elif finish_reason == "tool_calls":
                # Print reasoning if present (from extended thinking models)
                reasoning = assistant_message.get("reasoning")
                if reasoning:
                    console.print("\n[dim cyan]Reasoning:[/dim cyan]")
                    console.print(f"[dim italic]{escape(reasoning)}[/dim italic]")

                if assistant_message.get("content"):
                    console.print(f"\n[bold white]{escape(assistant_message['content'])}[/bold white]")

                self._call_tools(tool_calls)
            else:
                # Probably the error or legnth reasons
                raise BadFinishReason(finish_reason)
        # Reached max iterations without completing
        console.print(f"\n[dim]Reached maximum iterations ({self.max_iterations})[/dim]")
        last_message = self.messages[-1] if self.messages else None
        raise MaxIterationsReachedError(
            f"Agent reached maximum iterations ({self.max_iterations}) without completing. "
            f"Last message finish reason: {last_message.get('finish_reason') if last_message else 'N/A'}. "
            f"Consider increasing max_iterations or checking if the agent is stuck in a loop."
        )

    @overload
    def run(self, task: str = "", prompt: str = "", should_continue: bool = False) -> str:
        pass  # Used for typing exclusively

    @overload
    def run(
        self,
        task: str = "",
        prompt: str = "",
        output_class: type[TBaseModel] = ...,
        should_continue: bool = False,
    ) -> TBaseModel:
        pass  # Used for typing exclusively

    def run(
        self,
        task: str = "",
        prompt: str = "",
        output_class: type[TBaseModel] | None = None,
        should_continue: bool = False,
    ) -> str | TBaseModel:
        """
        Run the agent and return results.

        :param task: Optional task description for logging
        :param prompt: Optional user prompt to start with
        :param output_class: Optional Pydantic model class to validate and parse output
        :param should_continue: Whether the agent should continue from the previous context messages, or start a new thread.
        :return: If model_class provided, returns instance of that model; otherwise returns raw string
        """
        # If model_class is provided, derive the schema and parse the result
        if output_class is not None:
            if BaseModel is None or not issubclass(output_class, BaseModel):
                raise ValueError("model_class must be a Pydantic BaseModel subclass")

            # Generate schema from Pydantic model
            schema = output_class.model_json_schema()
            output_schema = {
                "name": output_class.__name__.lower(),
                "strict": False,
                "schema": schema,
            }

            # Run with schema
            result = self._run(
                task=task,
                prompt=prompt,
                output_schema=output_schema,
                should_continue=should_continue,
            )

            # Parse and validate with Pydantic
            try:
                return output_class.model_validate_json(result)
            except Exception as e:
                raise Exception(
                    f"Error validating response with {output_class.__name__}: {e}\nRaw response: {result}"
                ) from e

        # Otherwise, just return the raw string
        return self._run(task=task, prompt=prompt, should_continue=should_continue)
