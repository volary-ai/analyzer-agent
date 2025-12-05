import inspect
import json
from collections.abc import Callable
from typing import (
    TypedDict,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import httpx
from docstring_parser import parse
from pydantic import BaseModel
from rich.console import Console

TBaseModel = TypeVar("TBaseModel", bound=BaseModel)

console = Console(stderr=True)


class CompletionApiError(Exception):
    """Base exception for Completion API errors."""


class APIRequestError(CompletionApiError):
    """Raised when the CompletionApi API request fails."""

    def __init__(self, status_code: int, response_text: str):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"API request failed with status {status_code}: {response_text}")


class UsageDetails(TypedDict, total=False):
    """Usage details from API response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    prompt_tokens_details: dict  # Contains cached_tokens, etc.


class CompletionMessage(TypedDict, total=False):
    """Message in completion response."""

    role: str
    content: str
    tool_calls: list[dict]
    reasoning: str


class CompletionChoice(TypedDict):
    """Choice in completion response."""

    message: CompletionMessage
    finish_reason: str


class CompletionResponse(TypedDict):
    """Response from completion API."""

    id: str
    choices: list[CompletionChoice]
    usage: UsageDetails


class CompletionApi:
    """
    API client for LLM completions with built-in usage tracking.

    This class wraps the completion API and tracks token usage across multiple
    agents, allowing shared usage statistics when delegating tasks.
    """

    def __init__(self, api_key: str, endpoint: str):
        """
        Initialize the completion API client.

        :param api_key: API key for authentication
        :param endpoint: API endpoint URL
        """
        self.api_key = api_key
        self.endpoint = endpoint
        # Track per-agent usage stats
        self._agent_stats: dict[str, dict] = {}
        # Track global totals
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cached_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.total_iterations = 0

    def complete(
        self,
        agent_name: str,
        model: str,
        system_prompt: str,
        tools: list[Callable],
        messages: list,
        response_format: dict = None,
    ) -> CompletionResponse:
        """
        Make a completion request and track usage.

        :param agent_name: Name of the agent making the request (for tracking)
        :param model: The model to use for completions
        :param system_prompt: The initial system prompt
        :param tools: Tools available to the model
        :param messages: Message history
        :param response_format: Optional structured output format
        :return: The completion response
        """
        # Make the actual API call
        result = complete(
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            messages=messages,
            api_key=self.api_key,
            endpoint=self.endpoint,
            response_format=response_format,
        )

        # Track usage from this call
        self._record_usage(agent_name, model, result.get("usage", {}))

        return result

    def _record_usage(self, agent_name: str, model: str, usage: UsageDetails) -> None:
        """Record usage statistics from an API call."""
        if not usage:
            return

        # Update global totals
        self.total_iterations += 1
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)
        self.total_cost += usage.get("cost", 0.0)

        # Track cached tokens if available
        prompt_details = usage.get("prompt_tokens_details", {})
        cached = prompt_details.get("cached_tokens", 0)
        self.total_cached_tokens += cached

        # Initialize agent stats if needed
        if agent_name not in self._agent_stats:
            self._agent_stats[agent_name] = {
                "model": model,
                "iterations": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cached_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            }

        # Update agent-specific stats
        agent = self._agent_stats[agent_name]
        agent["iterations"] += 1
        agent["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        agent["total_completion_tokens"] += usage.get("completion_tokens", 0)
        agent["total_tokens"] += usage.get("total_tokens", 0)
        agent["total_cost"] += usage.get("cost", 0.0)
        agent["total_cached_tokens"] += cached

    def get_agent_stats(self, agent_name: str) -> dict:
        """Get usage stats for a specific agent."""
        return self._agent_stats.get(
            agent_name,
            {
                "model": "",
                "iterations": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cached_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            },
        )

    def print_usage_summary(self) -> None:
        """Print combined usage summary for all agents to stderr."""
        console.print(f"\n[bold magenta]{'═' * 50}[/bold magenta]")
        console.print("[bold magenta]Combined Usage Summary[/bold magenta]")
        console.print(f"[bold magenta]{'═' * 50}[/bold magenta]")

        # Print individual agent stats
        for agent_name, stats in self._agent_stats.items():
            if stats["iterations"] > 0:
                console.print(f"\n[bold cyan]{agent_name}:[/bold cyan]")
                console.print(f"  Model: [dim]{stats['model']}[/dim]")
                console.print(f"  API calls: {stats['iterations']}")
                console.print(
                    f"  Tokens: {stats['total_tokens']:,} ({stats['total_prompt_tokens']:,} prompt + {stats['total_completion_tokens']:,} completion)"
                )
                if stats["total_cached_tokens"] > 0:
                    console.print(f"  [green]Cached: {stats['total_cached_tokens']:,}[/green]")
                if stats["total_cost"] > 0:
                    console.print(f"  Cost: ${stats['total_cost']:.6f}")

        # Print totals
        if self.total_iterations > 0:
            console.print(f"\n[bold yellow]{'─' * 50}[/bold yellow]")
            console.print("[bold yellow]Total Across All Agents:[/bold yellow]")
            console.print(f"  Total API calls: {self.total_iterations}")
            console.print(
                f"  Total tokens: [bold]{self.total_tokens:,}[/bold] ({self.total_prompt_tokens:,} prompt + {self.total_completion_tokens:,} completion)"
            )
            if self.total_cached_tokens > 0:
                cache_pct = (
                    (self.total_cached_tokens / self.total_prompt_tokens * 100) if self.total_prompt_tokens > 0 else 0
                )
                console.print(
                    f"  [green]Total cached: {self.total_cached_tokens:,} ({cache_pct:.1f}% cache hit rate)[/green]"
                )
            if self.total_cost > 0:
                console.print(f"  [bold]Total cost: ${self.total_cost:.6f}[/bold]")


def complete(
    model: str,
    system_prompt: str,
    tools: list[Callable],
    messages: list,
    api_key: str,
    endpoint: str,
    response_format: dict = None,
) -> CompletionResponse:
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
        resp = httpx.post(
            url=endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
    except httpx.TimeoutException as e:
        raise CompletionApiError(f"Request timed out after 60 seconds: {e}") from e
    except httpx.RequestError as e:
        raise CompletionApiError(f"Network error when calling CompletionApi API: {e}") from e

    if resp.status_code != 200:
        raise APIRequestError(resp.status_code, resp.text)

    try:
        return resp.json()
    except json.JSONDecodeError as e:
        raise CompletionApiError(f"Failed to parse JSON response: {e}") from e


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
        if json_type == "object" and items and isinstance(items, dict) and "properties" in items:
            # This is a Pydantic model schema - inline it directly
            prop = items.copy()
            if param_desc:
                prop["description"] = param_desc
        else:
            prop = {"type": json_type, "description": param_desc}
            if items:
                prop["items"] = items

        properties[param_name] = prop

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


class InvalidToolArgOriginTypeError(Exception):
    """Raised when a tool argument has an unsupported origin type."""

    def __init__(self, origin):
        self.origin = origin
        super().__init__(f"Unsupported tool argument origin type: {origin}")


def _python_type_to_json_schema(python_type):
    """
    Converts Python type hints to JSON Schema types.
    Returns (type, items) tuple where items is used for array types.
    """
    # Handle Pydantic BaseModel types - inline their schema
    if isinstance(python_type, type) and issubclass(python_type, BaseModel):
        schema = python_type.model_json_schema()
        # Return the schema as a dict (not just "object")
        # The caller will need to handle this specially
        return "object", schema

    # Handle Union types (e.g., int | None, Optional[int])
    origin = get_origin(python_type)
    # Check for Union type (both typing.Union and types.UnionType from Python 3.10+)
    if origin is Union or (hasattr(origin, "__name__") and origin.__name__ == "UnionType"):
        # Get the non-None types from the union
        args = get_args(python_type)
        non_none_types = [arg for arg in args if arg is not type(None)]

        # If there's exactly one non-None type, use that
        if len(non_none_types) == 1:
            return _python_type_to_json_schema(non_none_types[0])
        raise InvalidToolArgOriginTypeError(origin=origin)

    # Handle List types
    if origin is list:
        args = get_args(python_type)
        if args:
            item_type = args[0]

            # Check if the list item is a TypedDict
            if hasattr(item_type, "__annotations__"):
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
                    "required": required,
                }
            else:
                json_type, _ = _python_type_to_json_schema(item_type)
                return "array", {"type": json_type}
        return "array", {"type": "string"}

    # Handle basic types
    type_mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
    }

    json_type = type_mapping.get(python_type)
    if json_type is None:
        raise InvalidToolArgOriginTypeError(origin=origin)

    return json_type, None
