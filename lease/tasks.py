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

    try:
        document = Document.objects.get(id=document_id)
        gpt_responses = []

        for chunk in chunks:
            # Call GPT API with the chunk
            response = call_gpt_api(chunk)
            gpt_responses.append(response)

        # Consolidate responses
        consolidated_response = "\n\n".join(gpt_responses)

        # Update the Document model
        document.gpt_response = {
            'status': 'Approved',
            'message': consolidated_response,
            'created_time': None
        }
        document.status = "Approved"
        document.save()

    except Exception as e:
        logger.info("EXCEPTIONNNNNNNNNNNNN======")
        # Update the document with the error status
        document.status = "Rejected"
        document.gpt_response = {
            'status': 'Error',
            'message': str(e),
            'created_time': None
        }
        document.save()
        raise e