from google import genai
from google.genai import types
import time
import sys

class TextAnalyzer:
    def __init__(self, key, base_prompt):
        self.client = genai.Client(api_key=key)
        self.model = "gemini-2.0-flash"
        self.base_prompt = base_prompt
        

    def __checkMessages(self, text):
        response = None
        for attempt in range(10):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    config=types.GenerateContentConfig(
                        system_instruction = self.base_prompt
                    ),
                    contents=[text]
                )
            except Exception as e:
                sys.stderr.write("Failed to get response: {}".format(e))
                time.sleep(10)
                print("Attempt #{}".format(attempt))
                continue
        if response is None:
            raise Exception("Failed to get response")
            
        print("AI Response: ", response.text)
        return response

    def findMessages(self, text):
        response = self.__checkMessages(text)
        if response is None or response.text.strip() == "None":
            return None 
        return list(map(lambda x: int(x), response.text.strip().split(',')))