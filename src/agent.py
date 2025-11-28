import inspect
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Self, TypedDict, get_args, get_origin, get_type_hints

import requests
from docstring_parser import parse
from rich.console import Console
from rich.markup import escape

_UPDATE_USER_FUNC_NAME = "update_user"
_SET_TODOS_FUNC_NAME = "set_todos"

console = Console(stderr=True)


class CompletionApiError(Exception):
    """Base exception for Completion API errors."""


class APIKeyMissingError(CompletionApiError):
    """Raised when the API key variable is not set."""


class APIRequestError(CompletionApiError):
    """Raised when the CompletionApi API request fails."""

    def __init__(self, status_code: int, response_text: str):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"API request failed with status {status_code}: {response_text}")


class AgentError(Exception):
    """Base exception for Agent-related errors."""


class MaxIterationsReachedError(AgentError):
    """Raised when the agent reaches the maximum number of iterations."""


class EmptyResponseError(AgentError):
    """Raised when the agent returns an empty response."""


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


def complete(
    model: str,
    system_prompt: str,
    tools: list[Callable],
    messages: list,
    api_key: str,
    endpoint: str,
    response_format: dict = None,
) -> dict:
    """
    Calls the openai compatible completions API.

    :param model: The model to use for completions.
    :param system_prompt: The initial system prompt to provide to the model.
    :param tools: Any tools the model may use.
    :param messages: The history of messages. The system prompt will be prepended.
    :param api_key: The API key for the endpoint
    :param endpoint: The endpoint to make a request to
    :param response_format: The structured format to respond with if the model supports it.
    :return: The completion response json.
    """

    tools_prompt = [tool_prompt(tool) for tool in tools]

    # Build request payload
    payload = {
        "model": model,
        "tools": tools_prompt,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]
        + messages,
        "usage": {"include": True},
    }

    # Add response_format if provided
    if response_format:
        payload["response_format"] = response_format

    try:
        resp = requests.post(
            url=endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
    except requests.exceptions.RequestException as e:
        raise CompletionApiError(f"Network error when calling CompletionApi API: {e}") from e

    if resp.status_code != 200:
        raise APIRequestError(resp.status_code, resp.text)

    try:
        return resp.json()
    except json.JSONDecodeError as e:
        raise CompletionApiError(f"Failed to parse JSON response: {e}") from e


def run_agent(agent, prompt="", output_schema=None):
    """Runs the agent once, returning its decoded output."""
    result = agent.run(prompt=prompt, output_schema=output_schema)
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        raise Exception(f"Error parsing JSON response: {e}\nRaw response: {result}") from e


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
    endpoint: str
    api_key: str
    agent_name: str = "Agent"
    todos: list = None
    max_iterations: int = 50
    max_retries_on_empty: int = 2  # Number of times to retry on empty response
    task: str = ""

    def __post_init__(self):
        # Initialize usage tracking
        self.usage_stats = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_cached_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "iterations": 0,
        }

    def _update_usage(self, result: dict) -> None:
        """Update usage statistics from API response."""
        usage = result.get("usage", {})
        if not usage:
            return

        self.usage_stats["iterations"] += 1
        self.usage_stats["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.usage_stats["total_completion_tokens"] += usage.get("completion_tokens", 0)
        self.usage_stats["total_tokens"] += usage.get("total_tokens", 0)
        self.usage_stats["total_cost"] += usage.get("cost", 0.0)

        # Track cached tokens if available
        prompt_details = usage.get("prompt_tokens_details", {})
        cached = prompt_details.get("cached_tokens", 0)
        self.usage_stats["total_cached_tokens"] += cached

    def get_usage_stats(self) -> dict:
        """Get a copy of the current usage statistics."""
        return self.usage_stats.copy()

    def print_usage_summary(self) -> None:
        """Print a summary of token usage and costs to stderr."""
        stats = self.usage_stats

        # Only print if there were any iterations
        if stats["iterations"] == 0:
            return

        console.print(f"\n[bold cyan]{'─' * 40}[/bold cyan]")
        console.print(f"[bold cyan]{self.agent_name} Usage Summary[/bold cyan]")
        console.print(f"[bold cyan]{'─' * 40}[/bold cyan]")
        console.print(f"[dim]Model:[/dim] {self.model}")
        console.print(f"[dim]API calls:[/dim] {stats['iterations']}")
        console.print(f"[cyan]Total tokens:[/cyan] [bold]{stats['total_tokens']:,}[/bold]")
        console.print(f"  Prompt tokens: {stats['total_prompt_tokens']:,}")
        console.print(f"  Completion tokens: {stats['total_completion_tokens']:,}")

        if stats["total_cached_tokens"] > 0:
            cache_pct = (
                (stats["total_cached_tokens"] / stats["total_prompt_tokens"] * 100)
                if stats["total_prompt_tokens"] > 0
                else 0
            )
            savings = f"({cache_pct:.1f}% cache hit rate)"
            console.print(f"  [green]Cached tokens: {stats['total_cached_tokens']:,} {savings}[/green]")

        if stats["total_cost"] > 0:
            console.print(f"[cyan]Total cost:[/cyan] [bold]${stats['total_cost']:.6f}[/bold]")


    def _call_tool(self, tool: Callable, tool_call: ToolCall) -> ToolCallResult:
        """Execute a single tool call and return the result."""
        tool_args = json.loads(tool_call.function.arguments)

        try:
            tool_result = tool(**tool_args)

            # Convert result to string if needed
            content = tool_result if isinstance(tool_result, str) else json.dumps(tool_result)

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

    def _maybe_update_user(self, tool_calls: list[ToolCall], messages) -> None:
        update_user_call = next(
            (tool_call for tool_call in tool_calls
             if tool_call.function.name == _UPDATE_USER_FUNC_NAME),
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
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_id,
                "content": "Message displayed to user successfully.",
            }
        )

    def _maybe_set_todos(self, tool_calls: list[ToolCall], messages: list) -> None:
        """Handle set_todos pseudo-tool calls."""
        set_todos_call = next(
            (tool_call for tool_call in tool_calls
             if tool_call.function.name == _SET_TODOS_FUNC_NAME),
            None,  # default if no match
        )
        if not set_todos_call:
            return

        result = self._call_tool(self.set_todos, set_todos_call)
        messages.append(result.message)

        self._render_todos()

    def _call_tools(self, tool_calls_raw: list[dict], messages: list) -> None:
        """Execute tool calls from the LLM."""
        tool_calls = [ToolCall.from_dict(tc) for tc in tool_calls_raw]

        tool_map = {tool.__name__: tool for tool in self.tools}
        # Add set_todos as a special method-based tool
        tool_map["set_todos"] = self.set_todos

        # Handle pseudo-tools first (they print before actual tool execution logs)
        self._maybe_update_user(tool_calls, messages)
        self._maybe_set_todos(tool_calls, messages)

        # Filter to actual tool calls (excluding pseudo-tools)
        actual_tool_calls = [
            tc for tc in tool_calls
            if tc.function.name not in [_UPDATE_USER_FUNC_NAME, _SET_TODOS_FUNC_NAME]
        ]

        if len(actual_tool_calls) == 0:
            return

        # Execute all tools in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(actual_tool_calls), 10)) as executor:
            # Submit all tool calls
            future_to_call = {
                executor.submit(self._call_tool, tool_map[tc.function.name], tc): tc
                for tc in actual_tool_calls
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
            messages.extend([r.message for r in results])

    def _render_todos(self) -> None:
        """Render the current TODO list to the console."""
        console.print("\n[bold cyan]TODO List:[/bold cyan]")
        if self.todos:
            for todo in self.todos:
                status_marker = {
                    "pending": "[ ]",
                    "in_progress": "[→]",
                    "completed": "[✓]"
                }.get(todo["status"], "[ ]")
                status_color = {
                    "pending": "white",
                    "in_progress": "yellow",
                    "completed": "green"
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

    def run(self, task: str = "", prompt: str = "", output_schema: dict = None) -> str:
        messages = []
        if prompt:
            messages.append({
                "role": "user",
                "content": prompt,
            })
        self.task = task

        # Print task at the start if provided
        if self.task:
            console.print(f"\n[bold cyan]Task: {escape(self.task)}[/bold cyan]")

        # Prepare response_format if output_schema is provided
        response_format = None
        if output_schema:
            response_format = {"type": "json_schema", "json_schema": output_schema}
        empty_retries = self.max_retries_on_empty
        # Call the agent in a loop until the finish reason isn't a tool call.
        for iteration in range(self.max_iterations):
            if self.todos:
                todo_summary = []
                for todo in self.todos:
                    status_marker = {
                        "pending": "[ ]",
                        "in_progress": "[→]",
                        "completed": "[✓]"
                    }.get(todo["status"], "[ ]")
                    todo_summary.append(f"{status_marker} {todo['content']}")

                messages.append({
                    "role": "system",
                    "content": "Reminder: You are currently doing the following:\n" + "\n".join(todo_summary)
                })
            else:
                messages.append({
                    "role": "system",
                    "content": "Reminder: you currently have no items in your TODO list",
                })

            # Call the API with response_format from the start
            result = complete(
                system_prompt=self.instruction,
                tools=self.tools + [self.set_todos, update_user],
                messages=messages,
                response_format=response_format,
                model=self.model,
                api_key=self.api_key,
                endpoint=self.endpoint,
            )

            # Track usage from this iteration
            self._update_usage(result)

            first_choice = result["choices"][0]
            assistant_message = first_choice["message"]
            messages.append(assistant_message)

            finish_reason = first_choice.get("finish_reason")
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls or finish_reason != "tool_calls":
                # No more tool calling to do. Return the response.
                content = assistant_message.get("content", "")
                if not content:
                    if empty_retries > 0:
                        console.print(
                            f"\n[dim yellow]ERROR: LLM finished without producing requested content. Retrying ({empty_retries} retries remaining)...[/dim yellow]"
                        )
                        empty_retries -= 1
                        # Add a user message prompting the LLM to try again
                        messages.append(
                            {
                                "role": "user",
                                "content": "Please provide the requested output in the specified format. You did not produce any output in your last response.",
                            }
                        )
                        continue

                    raise EmptyResponseError(
                        f"Agent completed but returned an empty response. "
                        f"Finish reason: {finish_reason}, Iterations: {iteration + 1}"
                    )

                return content

            # Print reasoning if present (from extended thinking models)
            reasoning = assistant_message.get('reasoning')
            if reasoning:
                console.print("\n[dim cyan]Reasoning:[/dim cyan]")
                console.print(f"[dim italic]{escape(reasoning)}[/dim italic]")

            if assistant_message.get("content"):
                console.print(f"\n[bold white]{escape(assistant_message['content'])}[/bold white]")

            self._call_tools(tool_calls, messages)

        # Reached max iterations without completing
        console.print(f"\n[dim]Reached maximum iterations ({self.max_iterations})[/dim]")
        last_message = messages[-1] if messages else None
        raise MaxIterationsReachedError(
            f"Agent reached maximum iterations ({self.max_iterations}) without completing. "
            f"Last message finish reason: {last_message.get('finish_reason') if last_message else 'N/A'}. "
            f"Consider increasing max_iterations or checking if the agent is stuck in a loop."
        )


def tool_prompt(tool: Callable) -> dict:
    """
    Converts a Python function into OpenAI tool schema format.
    """
    # Get function name
    name = tool.__name__

    # Parse docstring
    docstring = parse(tool.__doc__ or "")
    description = docstring.short_description or ""
    if docstring.long_description:
        description += "\n\n" + docstring.long_description

    # Get function signature and type hints
    sig = inspect.signature(tool)
    type_hints = get_type_hints(tool)

    # Build properties and required list
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip if no default value, it's required
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

        # Get type annotation
        param_type = type_hints.get(param_name, str)
        json_type, items = _python_type_to_json_schema(param_type)

        # Find parameter description from docstring
        param_desc = ""
        for doc_param in docstring.params:
            if doc_param.arg_name == param_name:
                param_desc = doc_param.description or ""
                break

        # Build property definition
        prop = {"type": json_type, "description": param_desc}

        if items:
            prop["items"] = items

        properties[param_name] = prop

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _python_type_to_json_schema(python_type):
    """
    Converts Python type hints to JSON Schema types.
    Returns (type, items) tuple where items is used for array types.
    """
    # Handle List types
    origin = get_origin(python_type)
    if origin is list:
        args = get_args(python_type)
        if args:
            item_type = args[0]

            # Check if the list item is a TypedDict
            if hasattr(item_type, '__annotations__'):
                # Build object schema from TypedDict annotations
                properties = {}
                required = []
                for field_name, field_type in item_type.__annotations__.items():
                    json_type, _ = _python_type_to_json_schema(field_type)
                    properties[field_name] = {"type": json_type}
                    required.append(field_name)

                return "array", {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            else:
                json_type, _ = _python_type_to_json_schema(item_type)
                return "array", {"type": json_type}
        return "array", {"type": "string"}

    # Handle basic types
    type_mapping = {str: "string", int: "integer", float: "number", bool: "boolean", dict: "object"}

    return type_mapping.get(python_type, "string"), None


def print_combined_usage(agents: list[Agent]) -> None:
    """
    Print combined usage statistics for multiple agents.

    :param agents: List of Agent instances
    """
    console.print(f"\n[bold magenta]{'═' * 50}[/bold magenta]")
    console.print("[bold magenta]Combined Usage Summary[/bold magenta]")
    console.print(f"[bold magenta]{'═' * 50}[/bold magenta]")

    total_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cached_tokens = 0
    total_cost = 0.0
    total_iterations = 0

    # Print individual agent stats and accumulate totals
    for agent in agents:
        stats = agent.get_usage_stats()
        if stats["iterations"] > 0:
            console.print(f"\n[bold cyan]{agent.agent_name}:[/bold cyan]")
            console.print(f"  Model: [dim]{agent.model}[/dim]")
            console.print(f"  API calls: {stats['iterations']}")
            console.print(
                f"  Tokens: {stats['total_tokens']:,} ({stats['total_prompt_tokens']:,} prompt + {stats['total_completion_tokens']:,} completion)"
            )
            if stats["total_cached_tokens"] > 0:
                console.print(f"  [green]Cached: {stats['total_cached_tokens']:,}[/green]")
            if stats["total_cost"] > 0:
                console.print(f"  Cost: ${stats['total_cost']:.6f}")

            # Accumulate totals
            total_tokens += stats["total_tokens"]
            total_prompt_tokens += stats["total_prompt_tokens"]
            total_completion_tokens += stats["total_completion_tokens"]
            total_cached_tokens += stats["total_cached_tokens"]
            total_cost += stats["total_cost"]
            total_iterations += stats["iterations"]

    # Print totals
    console.print(f"\n[bold yellow]{'─' * 50}[/bold yellow]")
    console.print("[bold yellow]Total Across All Agents:[/bold yellow]")
    console.print(f"  Total API calls: {total_iterations}")
    console.print(
        f"  Total tokens: [bold]{total_tokens:,}[/bold] ({total_prompt_tokens:,} prompt + {total_completion_tokens:,} completion)"
    )
    if total_cached_tokens > 0:
        cache_pct = (total_cached_tokens / total_prompt_tokens * 100) if total_prompt_tokens > 0 else 0
        console.print(f"  [green]Total cached: {total_cached_tokens:,} ({cache_pct:.1f}% cache hit rate)[/green]")
    if total_cost > 0:
        console.print(f"  [bold]Total cost: ${total_cost:.6f}[/bold]")
    console.print(f"[bold magenta]{'═' * 50}[/bold magenta]\n")
