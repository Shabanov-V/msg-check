# Design: Telegram Message Analyzer

> **Status**: Approved
> **Author**: Design Architect Agent
> **Date**: March 28, 2026
> **Scope**: Full system — `main.py`, `model/`, `service/`

This design has been split into focused documents. See the individual docs below.

## Design Documents

| Document | Scope | Description |
|----------|-------|-------------|
| [System Overview & Architecture](system-overview.design.md) | Full system | Problem statement, tech stack, architecture patterns, component diagram, integrations, configuration, design decisions, risks |
| [Message Processing Pipeline](message-processing.design.md) | `main.py`, `messageService.py`, `util.py` | Core data flow, orchestrator, message fetching/filtering/forwarding, state machine, error handling |
| [LLM Integration](llm-integration.design.md) | `textAnalyzer.py`, hallucination recovery | OpenRouter integration, request/response schema, structured output, ID hallucination recovery |
| [Calendar & Event Deduplication](calendar-deduplication.design.md) | `calendarService.py`, event handling | Google Calendar integration, fuzzy deduplication algorithm, event creation flow |
| [Data Model & Persistence](data-model.design.md) | `dbService.py`, SQLite schema | ER diagram, table schemas, DBService methods, connection patterns |
| [Prompt Optimization](prompt-optimization.design.md) | `textAnalyzer.py`, prompts | Two-phase LLM approach, timezone/end-time offloading to Python, source-language output |
| [WhatsApp Integration](whatsapp-waha-integration.design.md) | `source/`, `model/` | Multi-source abstraction, WAHA HTTP API integration, UnifiedMessage model |

## Known Issues (discovered during verification)

All issues below have been resolved:

1. ~~**Missing dependencies**~~: `google-api-python-client` and `google-auth` added to `requirements.txt`.
2. ~~**Syntax bug**~~: Orphaned `except Exception` block removed from `main.py`.
3. ~~**README outdated**~~: References to `messageServiceDB.py`, "Google GenAI", and stale env var names have been updated.
