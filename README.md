# Telegram Message Analyzer

This project is a **Telegram-based message analyzer** designed to identify and report messages based on customizable criteria. It leverages the **Telethon library** for interacting with Telegram, a **Google GenAI model** for natural language processing, and a **SQLite database** for tracking processed messages.

## Features

- **Automated Message Retrieval**: Fetches messages from specific Telegram groups or channels using dialog filters.
- **AI-Powered Analysis**: Uses a custom prompt and Google GenAI to analyze messages for any user-defined purpose.
- **Database Integration**: Tracks processed messages and stores dialog metadata in a SQLite database.
- **Error Handling and Retry Logic**: Ensures robust execution with retry mechanisms for API calls.
- **Customizable Filters**: Easily configure target dialog filters and output channels via environment variables.

## How It Works

1. **Dialog Filtering**: The script identifies target Telegram dialogs based on a filter name specified in the `.env` file.
2. **Message Retrieval**: It fetches messages from the last processed message onward, filtering for messages within a user-defined time range.
3. **AI Analysis**: Messages are analyzed using a Google GenAI model based on a custom prompt defined in the `base.prompt` file.
4. **Reporting**: Relevant messages are forwarded to a specified Telegram channel, and errors are reported to an error channel.
5. **Database Updates**: The SQLite database is updated with the latest processed message ID and timestamp.

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- A Telegram account with API credentials
- A Google GenAI API key
- SQLite (pre-installed with Python)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/msg-check.git
   cd msg-check
   ```
2. Install dependencies:
   ``` pip install -r requirements.txt ```
3. Create a .env file in the root directory and configure the following variables:
   ```
    TELEGRAM_API_ID=your_telegram_api_id
    TELEGRAM_API_HASH=your_telegram_api_hash
    GEMINI_KEY=your_google_genai_api_key
    TARGET_DIALOG_FILTER=your_target_dialog_filter_name
    OUTPUT_DIALOG_ID=your_output_channel_id
    ERROR_DIALOG_ID=your_error_channel_id
    BASE_PROMPT_FILE=base.prompt
   ```
4. Ensure the base.prompt file contains the AI prompt for analyzing messages.

5. Initialize the SQLite database:
   ``` python -c "from service.messageServiceDB import MessageServiceDB; MessageServiceDB()" ```

## Running the Script
1. Start the script:
   ```python main.py```

The script will:
* Fetch messages from the specified Telegram dialogs.
* Analyze them using the AI model.
* Forward relevant messages to the output channel.
* Log errors to the error channel.

### Example Output
   ``` 
    Execution completed.
    Messages processed: 150,
    Messages found: 12
   ```

## Project Structure
```
.
├── main.py                 # Main script
├── .env                    # Environment variables
├── base.prompt             # AI prompt for message 
├── service/                # Service modules
│   ├── messageServiceDB.py # Database operations
│   ├── textAnalyzer.py     # AI integration
│   └── util.py             # Utility functions
├── model/                  # Model modules
│   └── envLoader.py        # Environment loader
```

## License
This project is licensed under the MIT License