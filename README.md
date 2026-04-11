# Telegram & WhatsApp Message Analyzer

This project is a **multi-platform message analyzer** that monitors **Telegram** and **WhatsApp** groups for relevant messages based on customizable criteria. It leverages the **Telethon library** for Telegram, **WAHA (WhatsApp HTTP API)** for WhatsApp, an **LLM via OpenRouter** for natural language processing, **Google Calendar API** for automatic event creation, and a **SQLite database** for tracking processed messages.

## Features

- **Multi-Platform Monitoring**: Monitors both **Telegram** (via Telethon) and **WhatsApp** (via WAHA) groups from a single pipeline.
- **Automated Message Retrieval**: Fetches messages from specific groups using Telegram dialog filters and WhatsApp labels.
- **AI-Powered Analysis**: Uses a custom prompt and an LLM (via OpenRouter, default: `google/gemini-2.0-flash-exp:free`) to analyze messages for any user-defined purpose.
- **Calendar Event Extraction**: Automatically detects event-like messages and creates Google Calendar entries with fuzzy deduplication.
- **Human-Friendly Reports**: Sends formatted report messages with source icon, group name, link (Telegram), timestamp, and full message text.
- **Database Integration**: Tracks processed messages and stores dialog metadata in a SQLite database.
- **Error Handling and Retry Logic**: Ensures robust execution with retry mechanisms for API calls (Tenacity).
- **LLM Hallucination Recovery**: Recovers from incorrect message IDs returned by the LLM via text-content fallback matching.
- **Customizable Filters**: Easily configure target dialog filters and output channels via environment variables.
- **Backward Compatible**: WhatsApp integration is fully opt-in — without WAHA configuration, the system works in Telegram-only mode.

## How It Works

1. **Source Initialization**: The script initializes message sources — Telegram (always) and WhatsApp (if WAHA is configured and healthy).
2. **Chat Discovery**: Telegram chats are discovered via dialog filters; WhatsApp chats via labeled groups.
3. **Message Retrieval**: Messages are fetched from all sources since the last cursor, filtered to the last 24 hours. Own messages are excluded.
4. **AI Analysis**: All messages (up to 500) are analyzed together using an LLM (via OpenRouter) based on a custom prompt defined in the `base.prompt` file.
5. **Reporting**: Relevant messages are reported to a specified Telegram channel with formatted reports including source, group name, link (Telegram) or text reference (WhatsApp), and full message text. Reports are staggered so they appear as unread notifications.
6. **Event Creation**: Detected events are created in Google Calendar with fuzzy deduplication to avoid duplicates.
7. **Database Updates**: The SQLite database is updated with the latest processed message cursor per chat.

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- A Telegram account with API credentials
- An OpenRouter API key
- Google Calendar service account credentials (`service_account_creds.json`)
- SQLite (pre-installed with Python)
- *(Optional)* A running [WAHA](https://waha.devlike.pro/) container for WhatsApp support
- *(Optional)* WhatsApp Business with labels for group selection

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/msg-check.git
   cd msg-check
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example environment file and fill in your values:
   ```bash
   cp .env.example .env
   ```
   See `.env.example` for all available configuration variables.

4. Ensure the `base.prompt` file contains the AI prompt for analyzing messages.

5. Place your Google service account credentials file as `service_account_creds.json` in the project root.

### WhatsApp Setup (Optional)

To enable WhatsApp monitoring alongside Telegram:

1. **Deploy WAHA**: Run the [WAHA Docker container](https://waha.devlike.pro/) and authenticate a WhatsApp session via QR code.
2. **Use WhatsApp Business**: Label the groups you want to monitor with a specific label (e.g., "Monitor").
3. **Configure `.env`**: Set the following variables:
   ```
   WAHA_API_URL=http://localhost:3000
   WAHA_API_KEY=your_waha_api_key
   WAHA_SESSION=default
   WHATSAPP_TARGET_LABEL=Monitor
   ```
4. The script will automatically detect the WAHA configuration and include WhatsApp groups in the analysis pipeline. If WAHA is unreachable or the session is not active, WhatsApp is skipped gracefully.

## Running the Script
```bash
python main.py
```

The script will:
* Fetch messages from configured Telegram and WhatsApp sources.
* Analyze them using the LLM.
* Send formatted reports of matched messages to the output channel.
* Create Google Calendar events for detected events.
* Log errors and execution summary to the error channel.

### Example Output
```
Execution completed.
Messages processed: 150,
Messages found: 12,
Events found: 3
```

## Integration Testing

You can use the integration test system to verify and tune your LLM prompts.

### Running Tests
To run the tests with the default test cases and prompt:
```bash
python tests/integration_tester.py
```

### Adding Test Cases
Add new test cases to `tests/test_cases.json` in the following format:
```json
[
  {
    "text": "Your message text here",
    "chat_title": "Optional Group Name",
    "expected": {
      "found": true
    }
  }
]
```

### Testing Custom Prompts
To test a specific prompt file:
```bash
python tests/integration_tester.py --prompt path/to/your.prompt
```

### Options
- `--cases`: Path to the test cases JSON file (default: `tests/test_cases.json`).
- `--prompt`: Path to an optional custom prompt file to use instead of the one defined in `.env`.

## Project Structure
```
.
├── main.py                     # Entry point / orchestrator
├── .env                        # Environment variables (not committed)
├── .env.example                # Example environment configuration
├── base.prompt                 # AI prompt for message analysis
├── requirements.txt            # Python dependencies
├── verify_deduplication.py     # Standalone dedup test
├── source/                     # Message source abstraction layer
│   ├── messageSource.py        # MessageSource protocol definition
│   ├── telegramSource.py       # Telegram source (Telethon)
│   └── whatsappSource.py       # WhatsApp source (WAHA HTTP API)
├── service/                    # Service modules
│   ├── messageService.py       # Core message processing pipeline
│   ├── textAnalyzer.py         # LLM integration via OpenRouter
│   ├── dbService.py            # SQLite database operations
│   ├── calendarService.py      # Google Calendar event creation
│   └── util.py                 # Message formatting & helpers
├── model/                      # Model modules
│   ├── envLoader.py            # Environment configuration loader
│   ├── unifiedMessage.py       # Platform-agnostic message dataclass
│   ├── chatInfo.py             # Platform-agnostic chat info dataclass
│   ├── dialog.py               # Telegram peer wrapper (internal)
│   └── dialogType.py           # Dialog type enum (internal)
└── docs/design/                # Design documentation
```

## Design Documentation

Detailed design documents are available in `docs/design/`:

| Document | Description |
|----------|-------------|
| [System Overview](docs/design/system-overview.design.md) | Architecture, tech stack, integrations, configuration |
| [Message Processing](docs/design/message-processing.design.md) | Core pipeline, data flow, state machine |
| [LLM Integration](docs/design/llm-integration.design.md) | OpenRouter integration, structured output, hallucination recovery |
| [Calendar & Deduplication](docs/design/calendar-deduplication.design.md) | Google Calendar integration, fuzzy dedup algorithm |
| [Data Model](docs/design/data-model.design.md) | SQLite schema, ER diagram, persistence layer |
| [Bugfixes & Improvements](docs/design/bugfixes-and-improvements.design.md) | Completed 15-step fix plan |
| [WhatsApp Integration](docs/design/whatsapp-waha-integration.design.md) | WAHA-based WhatsApp source with abstraction layer |

## License
This project is licensed under the MIT License