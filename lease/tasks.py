# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/tasks.py
from __future__ import absolute_import, unicode_literals
from celery import shared_task
import openai
import tiktoken
from django.conf import settings
import time

@shared_task(bind=True)
def analyze_chunk(self, chunk, system_message):
    retry_attempts = 3
    for attempt in range(retry_attempts):
        try:
            openai.api_key = settings.OPENAI_API_KEY
            encoding = tiktoken.get_encoding("cl100k_base")
            chunk_tokens = len(encoding.encode(chunk))
            
            # Summarize if the chunk exceeds token limit
            if chunk_tokens > 4096:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Please summarize the following text to fit within the token limit."}, 
                        {"role": "user", "content": chunk}
                    ]
                )
                return response['choices'][0]['message']['content']
            else:
                # Analyze the chunk directly
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": chunk}
                    ]
                )
                return response['choices'][0]['message']['content']
        except openai.error.RateLimitError:
            if attempt < retry_attempts - 1:
                time.sleep(30)  # Wait for 20 seconds before retrying
            else:
                return {"status": "Error", "message": "Rate limit exceeded after multiple attempts"}
        except Exception as e:
            return str(e)
