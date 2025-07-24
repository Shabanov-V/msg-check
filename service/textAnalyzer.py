from google import genai
from google.genai import types
import time
import sys
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed

class TextAnalyzer:
    def __init__(self, key, base_prompt):
        self.client = genai.Client(api_key=key)
        self.model = "gemini-2.0-flash"
        self.base_prompt = base_prompt

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(30))
    def __generate_content_with_retry(self, client, model, base_prompt, text):
        return client.models.generate_content(
            model=model,
            config=types.GenerateContentConfig(
                temperature=0,
                system_instruction=base_prompt,
                response_mime_type="application/json",
                response_schema=genai.types.Schema(
                    required = ["found"],
                    type = genai.types.Type.OBJECT,
                    properties = {
                        "found": genai.types.Schema(
                            type = genai.types.Type.BOOLEAN,
                        ),
                        "results": genai.types.Schema(
                            type = genai.types.Type.ARRAY,
                            items = genai.types.Schema(
                                type = genai.types.Type.OBJECT,
                                required = ["chat_id", "message_id", "text"],
                                properties = {
                                    "chat_id": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "message_id": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "text": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                },
                            ),
                        ),
                        "Events": genai.types.Schema(
                            type = genai.types.Type.ARRAY,
                            items = genai.types.Schema(
                                type = genai.types.Type.OBJECT,
                                required = ["chat_id", "message_id", "start_datetime", "end_datetime", "title", "description"],
                                properties = {
                                    "chat_id": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "message_id": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "start_datetime": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "end_datetime": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "title": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                    "description": genai.types.Schema(
                                        type = genai.types.Type.STRING,
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            contents=[text]
        )

    def __checkMessages(self, text):
        response = None
        try:
            response = self.__generate_content_with_retry(self.client, self.model, self.base_prompt, text)
        except Exception as e:
            if (not hasattr(e, "code") or e.code != 429):
                sys.stderr.write("{}: Failed to get response: {}\n".format(datetime.now(), e))
        if response is None:
            raise Exception("Failed to get response")
        return response

    def findMessages(self, text):
        response = self.__checkMessages(text)
        if response is None or not response.parsed['found']:
            return None 
        
        print("Messages found in: {}".format(text))
        results = response.parsed.get('results', [])
        events = response.parsed.get('Events', [])
        return {"results": results, "Events": events}