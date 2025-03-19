import os
from dotenv import load_dotenv

class EnvLoader:
    def __init__(self, env_file=None):
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

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
    def gemini_key(self):
        return self.get("GEMINI_KEY")
    
    @property
    def base_prompt(self):
        return self.get("BASE_PROMPT")
    
    @property
    def target_dialog_filter(self):
        return self.get("TARGET_DIALOG_FILTER")
    
    @property
    def output_dialog_id(self):
        return int(self.get("OUTPUT_DIALOG_ID"))
    
    @property
    def error_dialog_id(self):
        return int(self.get("ERROR_DIALOG_ID"))
