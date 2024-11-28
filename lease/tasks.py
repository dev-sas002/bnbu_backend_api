# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/tasks.py
from __future__ import absolute_import, unicode_literals
from datetime import datetime, timezone
import json
from celery import group, shared_task
import openai
import tiktoken
from django.conf import settings
import time
from .models import Document
from .integrations.openai_integration import call_gpt_api
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1)
def process_document_chunks(self, document_id, chunks):
    from .models import Document

    # Initialize created_time in case of an error
    created_time = None

    try:
        document = Document.objects.get(id=document_id)
        gpt_responses = []

        for chunk in chunks:
            # Call GPT API with the chunk
            response = call_gpt_api(chunk)
            gpt_responses.append(response)

        # Consolidate responses
        consolidated_response = "\n\n".join(gpt_responses)
        encoding = tiktoken.get_encoding("cl100k_base")
        combined_tokens = len(encoding.encode(consolidated_response))

        # If the combined summary is still too long, summarize it
        if combined_tokens > 4096:
            final_summary_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Please summarize the following document to fit within the token limit.",
                    },
                    {"role": "user", "content": consolidated_response},
                ],
            )
            # Only assign consolidated_response after summarization
            consolidated_response = final_summary_response["choices"][0]["message"][
                "content"
            ].strip()

        # If final_summary_response exists, extract created_time
        if final_summary_response and "created" in final_summary_response:
            created_time = final_summary_response["created"]
            if isinstance(created_time, (int, float)):
                created_time = datetime.fromtimestamp(
                    created_time, tz=timezone.utc
                ).isoformat()

        # Determine the status based on the analysis result
        if "approved" in consolidated_response.lower():
            status = "Approved"
        elif "rejected" in consolidated_response.lower():
            status = "Rejected"
        else:
            status = "Draft"

        # Store the GPT response as a text string in JSON format
        gpt_response_text = json.dumps(
            {
                "status": status,
                "message": consolidated_response,
                "created_time": created_time,
            }
        )

        # Store the response text in the document's gpt_response field
        document.status = status
        document.gpt_response = gpt_response_text
        document.gpt_created_time = created_time
        document.save()

        return {
            "status": status,
            "message": consolidated_response,
            "created_time": created_time,
        }

    except Exception as e:
        logger.error(f"Error processing document chunks: {str(e)}")
        return {
            "status": "Error",
            "message": str(e),
            "created_time": created_time,
        }
