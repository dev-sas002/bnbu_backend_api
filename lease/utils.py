import os
from PyPDF2 import PdfReader

def split_document_into_chunks(file_path, max_chunk_size=1000):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    pdf_reader = PdfReader(file_path)
    text_content = ""

    # Extract text from all pages
    for page in pdf_reader.pages:
        text_content += page.extract_text()

    # Handle cases where text extraction fails
    if not text_content.strip():
        raise ValueError("Unable to extract text from the PDF. Ensure it contains readable content.")

    # Split text into chunks
    chunks = [text_content[i:i + max_chunk_size] for i in range(0, len(text_content), max_chunk_size)]

    return chunks
