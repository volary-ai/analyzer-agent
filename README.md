# Volary Analyzer Agent

This is an analysis agent to help you improve your code by identifying bugs,
technical debt, and areas for general improvement. It's designed to find things
you might not have spotted and to fix problems for you.


## Usage

The project is designed to be used as a GitHub Action. An example configuration
is as follows:

```yaml
name: tech-debt-analyzer
on:
  workflow_dispatch:
concurrency:
  group: analyzer
  cancel-in-progress: false
jobs:
  analyzer:
    name: analyzer
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: volary-ai/analyzer-agent@65a17b38da9ad954c20403fbbf5902679e15871f
        with:
          completions-api-key: ${{ secrets.OPENROUTER_API_KEY }}
```

## License

This project is currently source-available for internal use only.

- You may clone this repo and use it within your organization (e.g. via GitHub Actions).
- You may not redistribute this code, include it in your own products, or offer it as a service to third parties.
