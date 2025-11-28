TECH_DEBT_OUTPUT_SCHEMA = {
    "name": "tech_debt_analysis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "description": "Optional: a list of files related to the issue. This can refer to the whole file i.e. just main.go or a specific line i.e. main.go:12",
                            "items": {
                                "type": "string",
                            },
                        },
                        "title": {"type": "string", "description": "The title of the issue"},
                        "description": {
                            "type": "string",
                            "description": "Description of the technical debt issue, including the actions to take",
                        },
                        "kind": {
                            "type": "string",
                            "description": "Optional: The kind of the issue. Should match one of the kinds of technical debt issues identified in the system prompt or be left empty otherwise.",
                        },
                    },
                    "required": ["title", "description"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["issues"],
        "additionalProperties": False,
    },
}
