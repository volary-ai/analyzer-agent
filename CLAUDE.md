# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Volary Analyzer Agent - an AI-powered technical debt analysis tool that autonomously explores codebases to identify bugs, technical debt, and improvement opportunities. It's designed as a GitHub Action but can also run locally as a CLI tool.

## Development Commands

### Setup
```bash
make setup           # Install Python 3.12 and sync dependencies using uv
```

### Testing & Validation
```bash
make test           # Run syntax checks (compileall) and pytest tests
```

### Code Quality
```bash
make lint           # Run ruff linter
make format         # Format code with ruff
make fix            # Auto-fix linting issues and format code
make format-check   # Check code formatting without modifying
```

### Building
```bash
make wheel          # Build wheel package (outputs to current directory)
```

### Running Locally
```bash
# Set API key
export COMPLETIONS_API_KEY="<your API key>"

# Run the analyzer
uv run volary-analyzer

# Or install and run
pip install volary_analyzer-*.whl
volary-analyzer

# Available actions: run (default), analyze, eval, print, search
volary-analyzer analyze  # Analysis only (outputs JSON)
volary-analyzer eval     # Evaluate issues from stdin
volary-analyzer print    # Print formatted issues from stdin
volary-analyzer search   # Web search (question from stdin)
```

## Architecture

### Agent System
The codebase implements a multi-agent architecture where agents autonomously use tools to accomplish tasks:

- **Agent class** (`agent.py`): Core agentic loop that executes LLM tool calls until completion. Supports structured output via Pydantic models, TODO tracking, and parallel tool execution. Max 50 iterations by default.
- **Coordinator Agent**: Main analysis orchestrator that explores the repo and delegates complex tasks
- **Delegate Agents**: Sub-agents spawned via `delegate_task()` for focused exploration tasks
- **Search Agent**: Autonomous web search agent using DuckDuckGo for fact-checking (e.g., library versions)

### Analysis Pipeline
1. **Analyze phase** (`analyze.py`): Coordinator agent explores codebase using tools (`ls`, `read_file`, `grep`, `delegate_task`, `web_search`) and outputs `TechDebtAnalysis` with a list of issues
2. **Evaluation phase** (`eval.py`): Evaluates issues on objective/subjective, actionable, production-relevant, scope (local/multi-file), impact, and effort dimensions
3. **Presentation** (`print_issues.py`): Formats and displays evaluated issues to the user

### Tools System
Tools are regular Python functions with docstrings that get converted to OpenAI tool schemas:

- `ls(glob)`: List files (respects .gitignore, limit 100 results)
- `read_file(path, from_line, to_line)`: Read files with git blame annotations
- `grep(pattern, path, file_pattern)`: Search using git grep (respects .gitignore)
- `delegate_task(task, description)`: Spawn sub-agent for complex exploration
- `web_search(question)`: Autonomous web search via sub-agent
- `query_issues(queries)`: Search GitHub issues (only available in GitHub repos with auth)

Pseudo-tools (don't execute but affect agent behavior):
- `update_user(msg)`: Show status updates to user
- `set_todos(todos)`: Update TODO list

### Key Files
- `agent.py`: Core agent implementation with tool calling loop
- `analyze.py`: Main analysis workflow and repo context gathering
- `tools.py`: Tool implementations and factory functions
- `prompts.py`: System prompts for agents (analysis, evaluation, search)
- `output_schemas.py`: Pydantic models for structured outputs
- `completion_api.py`: OpenAI-compatible API client (supports OpenRouter)
- `cli.py`: CLI entry point
- `eval.py`: Issue evaluation logic
- `print_issues.py`: Issue formatting and display

### Prompt Engineering
Prompts are in `prompts.py` and include detailed instructions for:
- What constitutes actionable technical debt vs subjective opinions
- How to evaluate issues objectively
- Examples of good vs bad analysis outputs
- When to delegate tasks vs handle directly

## Code Conventions

- Don't add comments explaining what the next line does. Comments should only be added if the code is surprising in some way.
- Use Python 3.12+ features (the project requires Python 3.12)
- Line length: 120 characters (configured in ruff)
- Use `uv` for dependency management, not pip directly for development
- Tests are in `src/volary_analyzer/test/` subdirectory

## GitHub Action Integration

The project runs as a Docker-based GitHub Action. Configuration in `action.yml` accepts:
- `completions-api-key` (required): API key for LLM provider
- `completions-endpoint` (optional): Custom API endpoint
- `coordinator-model` (optional): Model for main analysis
- `delegate-model` (optional): Model for sub-tasks

Entrypoint is `action.py` which wraps the CLI.

- Don't add comments explaining what the next line does (e.g. `#sort the list\n sorted(list)`). Comments should only be added if the code is surprising in some way e.g. `# filter out the actual tool calls (psudo-calls don't actually run anything)`.