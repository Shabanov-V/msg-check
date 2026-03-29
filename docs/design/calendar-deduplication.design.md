# Design: Calendar Integration & Event Deduplication

> **Status**: Approved
> **Author**: Design Architect Agent
> **Date**: March 28, 2026
> **Scope**: `service/calendarService.py`, event handling in `service/messageService.py`
> **See also**: [System Overview](system-overview.design.md) · [Data Model](data-model.design.md) · [LLM Integration](llm-integration.design.md)

---

## 1. Overview

The system automatically detects event-like information in Telegram messages (via LLM analysis) and creates Google Calendar entries. A fuzzy deduplication algorithm prevents the same real-world event from being created multiple times when mentioned in different messages.

---

## 2. `service/calendarService.py` — Google Calendar Integration

| Aspect          | Detail                                                              |
|-----------------|---------------------------------------------------------------------|
| **Purpose**     | Creates and manages Google Calendar events via service account      |
| **Auth**        | Service account credentials from `service_account_creds.json`      |
| **Scopes**      | `https://www.googleapis.com/auth/calendar`                         |
| **Key Methods** | `create_event()`, `get_subscription_link()`, `clear_all_events()`  |

### Methods

**`create_event(name, description, start_datetime, end_datetime)`**
- Creates a Google Calendar event with the given title, description, and time range.
- The description includes the original Telegram message link (appended by the caller).
- Returns the created event object (including `id` for the `google_event_id`).

**`get_subscription_link()`**
- Returns a Google Calendar subscription URL for the configured calendar.

**`clear_all_events()`**
- Deletes all events from the calendar. Intended for manual use only.

---

## 3. Use Case: Automatic Calendar Event Extraction

```mermaid
flowchart LR
    accTitle: Calendar Event Extraction
    accDescr: System detects events in messages and creates Google Calendar entries

    A[LLM detects event<br/>in message] --> B[Extract title, dates,<br/>description]
    B --> C{Duplicate check<br/>fuzzy match > 0.6?}
    C -->|Duplicate| D[Store association<br/>skip creation]
    C -->|New event| E[Create Google<br/>Calendar event]
    E --> F[Store event in<br/>SQLite with<br/>google_event_id]
    D --> G[Continue to<br/>next event]
    F --> G
```

**Actor**: System (triggered during message analysis)

**Preconditions**:
- Google Calendar service account is configured
- Calendar ID is set in environment
- LLM prompt instructs the model to detect events

**Main Flow**:
1. During message analysis, the LLM identifies events with `title`, `start_datetime`, `end_datetime`, and `description`.
2. For each detected event, the system queries SQLite for existing events within a ±2 hour window of the start time.
3. System performs fuzzy title matching using `SequenceMatcher` (threshold: 0.6) and substring containment checks.
4. If a duplicate is detected, the system stores the association (linking the new message to the existing Google event) but does **not** create a new calendar entry.
5. If the event is new, the system creates a Google Calendar event (with a Telegram message link in the description) and stores it in SQLite with the returned `google_event_id`.

**Postconditions**:
- New unique events appear in Google Calendar.
- Duplicate events are tracked but not duplicated in the calendar.
- All events are recorded in the `calendar_events` table.

---

## 4. Event Deduplication Algorithm

```mermaid
flowchart TD
    accTitle: Event Deduplication Algorithm
    accDescr: Detailed flowchart of the fuzzy event deduplication logic

    A["New event detected by LLM<br/>(title, start_time, end_time)"] --> B["Query DB: get_events_starting_around<br/>(start_time ± 120 minutes)"]
    B --> C{Candidates found?}
    C -->|No| D[Create new Google Calendar event]
    C -->|Yes| E["For each candidate:"]
    E --> F["Compute similarity<br/>SequenceMatcher(new_title, candidate_title)"]
    F --> G{"similarity > 0.6<br/>OR new_title ⊂ candidate_title<br/>OR candidate_title ⊂ new_title?"}
    G -->|Yes| H["DUPLICATE<br/>Store with existing google_event_id<br/>Skip calendar creation"]
    G -->|No| I{More candidates?}
    I -->|Yes| E
    I -->|No| D
    D --> J["Store in calendar_events table<br/>with new google_event_id"]
```

### Algorithm Details

The deduplication runs in `MessageService.handle_events()` (and the equivalent inline block in `process_dialogs()`):

1. **Time window query** — `DBService.get_events_starting_around(start_time, window_minutes=120)` returns all stored events whose `start_time` falls within ±2 hours of the new event's start time.

2. **Fuzzy title matching** — For each candidate:
   - Compute `difflib.SequenceMatcher(None, new_title, candidate_title).ratio()`
   - If `ratio > 0.6` → duplicate
   - If `new_title in candidate_title` or `candidate_title in new_title` → duplicate (substring containment)

3. **Duplicate handling** — The event record is still stored in `calendar_events`, but with the **existing** `google_event_id` (linking to the already-created calendar event). No new Google Calendar event is created.

4. **New event handling** — `CalendarService.create_event()` is called. The `google_event_id` from the response is stored in `calendar_events`.

### Candidate Tuple Structure

The `get_events_starting_around()` query returns raw tuples from SQLite:

| Index | Column           |
|-------|------------------|
| 0     | `id`             |
| 1     | `dialog_id`      |
| 2     | `event_id`       |
| 3     | `google_event_id` |
| 4     | `title`          |
| 5     | `start_time`     |
| 6     | `end_time`       |
| 7     | `description`    |
| 8     | `created_at`     |

The algorithm uses index `[4]` for title and `[3]` for `google_event_id`.

### Test Coverage

`verify_deduplication.py` provides standalone test cases for the dedup logic:
- "Team Dinner" vs "Team Dinner with Bob" — expects duplicate (substring match)
- "Dinner" vs "Dinner with Bob" — expects duplicate (substring match)

---

## 5. Event Data Flow Through the System

```mermaid
sequenceDiagram
    accTitle: Event Creation Flow
    accDescr: Shows how an event moves from LLM detection to Google Calendar

    participant LLM as LLM Response
    participant MS as MessageService
    participant DB as DBService
    participant CS as CalendarService
    participant GCal as Google Calendar

    LLM->>MS: Event: {title, start, end, msg_id}
    MS->>MS: Find source message by msg_id + chat_id
    MS->>MS: Parse ISO datetimes
    MS->>DB: get_events_starting_around(start ± 120min)
    DB-->>MS: Candidate events (list of tuples)

    alt Candidates exist
        MS->>MS: SequenceMatcher(new_title, each candidate_title)
        alt similarity > 0.6 or substring match
            MS->>DB: store_calendar_event(google_event_id = existing)
            Note over MS: Skip calendar creation
        else No match
            MS->>CS: create_event(title, desc + msg_link, start, end)
            CS->>GCal: events.insert()
            GCal-->>CS: {id: "google_event_abc"}
            CS-->>MS: created_event
            MS->>DB: store_calendar_event(google_event_id = new)
        end
    else No candidates
        MS->>CS: create_event(title, desc + msg_link, start, end)
        CS->>GCal: events.insert()
        GCal-->>CS: {id: "google_event_abc"}
        CS-->>MS: created_event
        MS->>DB: store_calendar_event(google_event_id = new)
    end
```

---

<small>Generated by Design Architect agent with GitHub Copilot</small>
