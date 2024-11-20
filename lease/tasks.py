# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/tasks.py

from .models import Document
from celery import shared_task
from lease.utils import analyze_document_with_gpt

@shared_task
def analyze_document_with_gpt_task(document_id):
    try:
        # Fetch the document
        document = Document.objects.get(id=document_id)

        # Perform analysis
        result = analyze_document_with_gpt(document)

        # Return the result without updating the document here
        return result

    except Exception as e:
        # Handle errors gracefully
        return {'status': 'Error', 'message': str(e)}
