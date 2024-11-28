import openai
import tiktoken
import logging
from django.conf import settings
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI API key
openai.api_key = settings.OPENAI_API_KEY


def call_gpt_api(chunk, max_chunk_tokens=4096, model="gpt-4", max_response_tokens=1000):
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

    encoding = tiktoken.get_encoding("cl100k_base")
    chunk_tokens = len(encoding.encode(chunk))

    # Summarize if the chunk exceeds the token limit
    if chunk_tokens + max_response_tokens > max_chunk_tokens:
        logger.info("Chunk exceeds token limit. Summarizing the text.")
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Please summarize the following text to fit within the token limit.",
                },
                {"role": "user", "content": chunk},
            ],
            max_tokens=max_response_tokens,
        )

    else:
        # Analyze the chunk directly
        logger.info("Processing chunk directly.")
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": chunk},
            ],
            max_tokens=max_response_tokens,
        )

    return response["choices"][0]["message"]["content"].strip()
