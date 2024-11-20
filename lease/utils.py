# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/utils.py
from datetime import datetime, timezone
import openai
import tiktoken
import PyPDF2
from django.conf import settings
import time
import json


def analyze_document_with_gpt(document):
        try:
            # Extract text from the PDF file
            with open(document.file.path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                num_pages = len(reader.pages)
                chunk_size = 5  # Max pages per chunk for large documents
                chunks = []

                # Split the document into chunks of pages
                for i in range(0, num_pages, chunk_size):
                    chunk_text = ''
                    for j in range(i, min(i + chunk_size, num_pages)):
                        chunk_text += reader.pages[j].extract_text()
                    chunks.append(chunk_text)

            if not chunks:
                raise ValueError("No text found in the document.")

            # Initialize OpenAI API
            openai.api_key = settings.OPENAI_API_KEY
            encoding = tiktoken.get_encoding("cl100k_base")
            time_to_wait = 0

            # Define the system message for the document analysis, including lease details
            system_message = f"""
            This GPT acts as a short-term rental contract expert designed to help users, especially students, review rental leases. 
            The primary goal is to assist users in identifying unusual clauses, potential legal risks, and ensuring transparency within the lease documents. 
            It will always identify key financial details such as rent amounts and security deposits from uploaded leases. 
            Additionally, the GPT will carefully review the lease for unfavorable terms to the tenant, such as disproportionate fees, restrictions, or unclear responsibilities, 
            and will make suggestions for favorable terms and strategies for negotiation. 
            For example, it will suggest negotiating points such as reduced late fees, prorated rent for partial occupancy months, or limits on certain restrictions like subletting. 
            It will also ensure that checkbox provisions are correctly applied, particularly regarding assignment, subleasing, and permissions. 
            The length of the lease, any related fees, and responsibilities of both the landlord and tenant are key areas of focus. 
            
            As part of the detailed review, the response will include:
            The property address mentioned in the lease.
            The landlord’s name, contact information, and stated responsibilities.
            The tenant’s name and obligations.
            Key financial terms, such as rent amount, security deposit, payment schedule, late fees, and additional charges.
            Lease duration, including the start date, end date, and terms for renewal or termination.
            Responsibilities for maintenance, utilities, and any shared obligations between the landlord and tenant.
            Identification of unusual clauses or potential legal risks that may pose challenges or are unfavorable to the tenant.
            Recommendations for negotiation, clarification, or improvement where applicable.
            Verification that provisions related to subleasing, assignments, and permissions are clear and appropriate.
            Additional fees or charges specified in the lease, such as property taxes or insurance costs.
            Any other relevant details or findings from the document.

            The GPT avoids giving direct legal advice but provides a thorough assessment to help the user feel confident in negotiating and signing a lease. 
            It speaks in a formal and direct manner, ensuring clarity and professionalism in its assessments.

            Please analyze the lease document and provide a clear assessment. 
            Specifically, include a status for the lease: 
            - "Approved" if the lease is favorable and there are no significant concerns.
            - "Rejected" if there are major unfavorable clauses or legal risks.
            - "Draft" if the lease is in an incomplete or negotiable state, and suggest any improvements or issues that need addressing.
            
            Please analyze the lease document and provide a clear assessment. Include the status and a detailed summary of findings in the response.
            """

            chunk_summaries = []

            # Process each chunk and summarize if needed
            for chunk in chunks:
                if time_to_wait > 0:
                    time.sleep(time_to_wait)

                chunk_tokens = len(encoding.encode(chunk))

                # If chunk exceeds token limit, summarize it
                if chunk_tokens > 4096:
                    summary_response = openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": "Please summarize the following text to fit within the token limit."},
                            {"role": "user", "content": chunk}
                        ]
                    )
                    chunk_summary = summary_response['choices'][0]['message']['content']
                else:
                    # Analyze the chunk directly
                    response = openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": chunk}
                        ]
                    )
                    chunk_summary = response['choices'][0]['message']['content']

                chunk_summaries.append(chunk_summary)
                time_to_wait = 20  # Throttle to avoid rate limits

            # Combine all chunk summaries
            combined_summary = " ".join(chunk_summaries)
            combined_tokens = len(encoding.encode(combined_summary))

            # If the combined summary is still too long, summarize it
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
            final_analysis_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": combined_summary}
                ]
            )
            
            analysis_result = final_analysis_response['choices'][0]['message']['content'].strip()
            created_time = final_analysis_response.get('created')

            # Ensure created_time is a string in ISO 8601 format
            if isinstance(created_time, (int, float)):
                created_time = datetime.fromtimestamp(created_time, tz=timezone.utc).isoformat()

            # Determine the status based on the analysis result
            if 'approved' in analysis_result.lower():
                status = 'Approved'
            elif 'rejected' in analysis_result.lower():
                status = 'Rejected'
            else:
                status = 'Draft'
            
            # Store the GPT response as a text string in JSON format
            gpt_response_text = json.dumps({
                "status": status,
                "message": analysis_result,
                "created_time": created_time
            })

            # Store the response text in the document's gpt_response field
            document.status = status
            document.gpt_response = gpt_response_text
            document.gpt_created_time = created_time
            document.save()

            return {
                'status': status,
                'message': analysis_result,
                'created_time': created_time,
            }

        except Exception as e:
            return {
                'status': 'Error',
                'message': str(e)
            }

