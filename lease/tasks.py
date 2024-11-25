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

@shared_task(bind=True, max_retries=5)
def analyze_chunk(self, chunk, system_message):
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
    except openai.error.RateLimitError as e:
        retry_delay = (2 ** self.request.retries) * 5  # Exponential delay (e.g., 5, 10, 20 seconds)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=retry_delay)
        else:
            return {"status": "Error", "message": "Rate limit exceeded after multiple attempts"}
    except Exception as e:
        return {"status": "Error", "message": str(e)}
        
@shared_task
def process_analysis_results(document_id, chunk_summaries):
    document = Document.objects.get(id=document_id)

    try:
        # Combine all chunk summaries
        error_chunks = [chunk for chunk in chunk_summaries if isinstance(chunk, dict) and chunk.get('status') == 'Error']
        if error_chunks:
            error_messages = "; ".join(chunk.get('message', 'Unknown error') for chunk in error_chunks)
            raise ValueError(f"Errors in chunks: {error_messages}")
        
        combined_summary = " ".join(
            result.get('message', '') if isinstance(result, dict) else str(result)
            for result in chunk_summaries
        )

        # Handle final analysis or summarization if needed
        encoding = tiktoken.get_encoding("cl100k_base")
        combined_tokens = len(encoding.encode(combined_summary))
        if combined_tokens > 4096:
            final_summary_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Please summarize the following document to fit within the token limit."},
                    {"role": "user", "content": combined_summary}
                ]
            )
            combined_summary = final_summary_response['choices'][0]['message']['content']

        # Final analysis on the combined summary
        system_message = f"""
            This GPT acts as a short-term rental contract expert designed to help users, especially students, review rental leases. 
            The primary goal is to assist users in identifying unusual clauses, potential legal risks, and ensuring transparency within the lease documents. 
            It will always identify key financial details such as rent amounts and security deposits from uploaded leases. 
            Additionally, the GPT will carefully review the lease for unfavorable terms to the tenant, such as disproportionate fees, restrictions, or unclear responsibilities, 
            and will make suggestions for favorable terms and strategies for negotiation. 
            For example, it will suggest negotiating points such as reduced late fees, prorated rent for partial occupancy months, or limits on certain restrictions like subletting. 
            It will also ensure that checkbox provisions are correctly applied, particularly regarding assignment, subleasing, and permissions. 
            The length of the lease, any related fees, and responsibilities of both the landlord and tenant are key areas of focus. 
            
            Please analyze the lease document and provide a clear assessment. 
            Specifically, include a status for the lease: 
            - "Approved" if the lease is favorable and there are no significant concerns.
            - "Rejected" if there are major unfavorable clauses or legal risks.
            - "Draft" if the lease is in an incomplete or negotiable state, and suggest any improvements or issues that need addressing.
            
            Please ensure the status is clearly mentioned in the response along with a summary of your findings.
            """
        final_analysis_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": combined_summary}
            ]
        )
        analysis_result = final_analysis_response['choices'][0]['message']['content'].strip()
        created_time = final_analysis_response.get('created')

        # Format created_time as ISO 8601
        if isinstance(created_time, (int, float)):
            created_time = datetime.fromtimestamp(created_time, tz=timezone.utc).isoformat()

        # Determine the status
        if 'approved' in analysis_result.lower():
            status = 'Approved'
        elif 'rejected' in analysis_result.lower():
            status = 'Rejected'
        else:
            status = 'Draft'



        # # Save the results back to the document
        # gpt_response_text = json.dumps({
        #     "status": status,
        #     "message": analysis_result,
        #     "created_time": created_time
        # })
        # document.status = status
        # document.gpt_response = gpt_response_text
        # document.gpt_created_time = created_time
        # document.save()

        # return {
        #         'status': status,
        #         'message': analysis_result,
        #         'created_time': created_time,
        # }
        
        
        # Save results in the database
        document.status = status
        document.gpt_response = json.dumps({
            "status": status,
            "message": analysis_result,
            "created_time": created_time
        })
        document.gpt_created_time = created_time
        document.save()

        return {"status": status, "message": analysis_result}

    except Exception as e:
        document.status = "Error"
        document.gpt_response = json.dumps({"status": "Error", "message": str(e)})
        document.save()
        print("Error occurred:", str(e))
        return {'status': 'Error', 'message': str(e), 'created_time': None}
