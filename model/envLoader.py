import os
from dotenv import load_dotenv
from functools import cached_property

class EnvLoader:
    def __init__(self, env_file=None):
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        self._validate()

    def _validate(self):
        required = [
            "TELEGRAM_API_ID",
            "TELEGRAM_API_HASH",
            "OPENROUTER_API_KEY",
            "BASE_PROMPT_FILE",
            "TARGET_DIALOG_FILTER",
            "OUTPUT_DIALOG_ID",
            "ERROR_DIALOG_ID",
            "CALENDAR_ID",
        ]
        missing = [key for key in required if not self.get(key)]
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
        if self.whatsapp_enabled:
            self._validate_whatsapp()

    def _validate_whatsapp(self):
        required = ["WAHA_API_KEY", "WHATSAPP_TARGET_LABEL"]
        missing = [key for key in required if not self.get(key)]
        if missing:
            raise EnvironmentError(f"WAHA_API_URL is set but missing required WhatsApp variables: {', '.join(missing)}")

    def get(self, key, default=None):
        return os.getenv(key, default)

    @property
    def telegram_api_id(self):
        return self.get("TELEGRAM_API_ID")

    @property
    def telegram_api_hash(self):
        return self.get("TELEGRAM_API_HASH")
    
    @property
    def phone_number(self):
        return self.get("PHONE_NUMBER")
    
    @property
    def password(self):
        return self.get("PASSWORD")
    
    @property
    def openrouter_api_key(self):
        return self.get("OPENROUTER_API_KEY")

    @property
    def llm_model(self):
        return self.get("LLM_MODEL", "google/gemini-2.0-flash-exp:free")

    @cached_property
    def base_prompt(self):
        base_prompt_file = self.get("BASE_PROMPT_FILE")
        with open(base_prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    @cached_property
    def phase2_prompt(self):
        phase2_file = self.get("PHASE2_PROMPT_FILE", "base_phase2.prompt")
        with open(phase2_file, "r", encoding="utf-8") as f:
            return f.read()
    
    @property
    def target_dialog_filter(self):
        return self.get("TARGET_DIALOG_FILTER")
    
    @property
    def output_dialog_id(self):
        return int(self.get("OUTPUT_DIALOG_ID"))
    
    @property
    def error_dialog_id(self):
        return int(self.get("ERROR_DIALOG_ID"))
    
    @property
    def calendar_id(self):
        return self.get("CALENDAR_ID")

    @property
    def timezone(self):
        return self.get("TIMEZONE", "Europe/Madrid")

    @property
    def waha_api_url(self):
        return self.get("WAHA_API_URL")

    @property
    def waha_api_key(self):
        return self.get("WAHA_API_KEY")

    @property
    def waha_session(self):
        return self.get("WAHA_SESSION", "default")

    @property
    def whatsapp_target_label(self):
        return self.get("WHATSAPP_TARGET_LABEL")

    @property
    def whatsapp_enabled(self):
        return bool(self.waha_api_url)

    @property
    def log_verbosity(self):
        return self.get("LOG_VERBOSITY", "normal").lower()
