"""AI engineering layer: providers, prompts, tools, orchestration, retrieval.

Dependency rule: this package may import from `app.modules`, but
`app.modules` must never import from here. Business logic stays LLM-free.
"""
