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
                system_instruction=base_prompt
            ),
            contents=[text]
        )

    def __checkMessages(self, text):
        response = None
        try:
            response = self.__generate_content_with_retry(self.client, self.model, self.base_prompt, text)
        except Exception as e:
            if (e.code != 429):
                sys.stderr.write("{}: Failed to get response: {}\n".format(datetime.now(), e))
        if response is None:
            raise Exception("Failed to get response")
        return response

    def findMessages(self, text):
        response = self.__checkMessages(text)
        if response is None or response.text.strip() == "None":
            return None 
        else:
            print("Message #{} found in: {}".format(response.text.strip(), text))
        return list(map(lambda x: int(x), response.text.strip().split(',')))