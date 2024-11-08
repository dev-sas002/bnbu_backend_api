from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import Lease, Document
from .serializers import LeaseSerializer, LeaseUploadSerializer, RevisedLeaseUploadSerializer, DocumentSerializer
from rest_framework.permissions import IsAuthenticated
from .permissions import IsClientOrAdmin  # Import the custom permission class
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.http import StreamingHttpResponse, Http404
from datetime import timedelta
import openai
import PyPDF2
from django.shortcuts import get_object_or_404
from django.conf import settings


class LeaseViewSet(viewsets.ModelViewSet):
    queryset = Lease.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['address1', 'city']
    permission_classes = [IsAuthenticated, IsClientOrAdmin]  # Update permission classes
    pagination_class = PageNumberPagination
    serializer_class = LeaseSerializer
    

    def get_serializer_class(self):
        if self.action == 'upload_lease':
            return LeaseUploadSerializer
        return LeaseSerializer
    
    @action(detail=False, methods=['post'], url_path='upload')
    def upload_lease(self, request):
        # Create a mutable copy of request.data
        data = request.data.copy()
        # Set the user from the request
        data['user'] = request.user.id

        # Use LeaseUploadSerializer to validate and create the Lease
        serializer = LeaseUploadSerializer(data=data, context={'request': request})  # Pass request in context
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        lease = serializer.save()  # This will now have access to self.context['request']
        
        # Serialize the lease with the documents included
        lease_serializer = LeaseSerializer(lease)
        return Response(lease_serializer.data, status=status.HTTP_201_CREATED)
    
    # Update Lease record
    @action(detail=True, methods=['put'], url_path='update')
    def update_lease(self, request, pk=None):
        lease = self.get_object()
        serializer = LeaseSerializer(lease, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Delete Lease record
    @action(detail=True, methods=['delete'], url_path='delete')
    def delete_lease(self, request, pk=None):
        lease = self.get_object()
        lease.delete()
        return Response({'status': 'Lease deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'], url_path='revised')
    def revised_lease(self, request, pk=None):
        lease = self.get_object()
        serializer = RevisedLeaseUploadSerializer(data=request.data)

        if serializer.is_valid():
            # Get the document IDs from the serializer update method
            document_ids = serializer.update(lease, serializer.validated_data)
            return Response(
                {'status': 'revised documents uploaded', 'document_ids': document_ids},
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        address = request.query_params.get('address')
        start_date = request.query_params.get('start_date')  
        end_date = request.query_params.get('end_date')     
        status_value = request.query_params.get('status')

        leases = Lease.objects.all()
        
        # Filter by address if provided (search in both address1 and address2)
        if address:
            leases = leases.filter(Q(address1__icontains=address) | Q(address2__icontains=address))

        # Filter by created_at for date range
        if start_date:
            try:
                start_date = timezone.datetime.strptime(start_date, '%Y-%m-%d').date()
                leases = leases.filter(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
                end_date = end_date + timedelta(days=1)  # This will now represent the start of the next day
                leases = leases.filter(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = timezone.now().date()

        # Apply ordering to ensure consistency in pagination
        leases = leases.order_by('-created_at')

        # Filter by status if provided
        if status_value:
            leases = leases.filter(status=status_value)

        # Apply pagination
        page = self.paginate_queryset(leases)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(leases, many=True)
        return Response(serializer.data if leases.exists() else {'detail': 'No leases found.'}, status=status.HTTP_200_OK)

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by('-uploaded_at')
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['lease', 'version']
    search_fields = ['name']

    @action(detail=False, methods=['get'], url_path='preview/(?P<document_id>\d+)')
    def preview_document(self, request, document_id=None):
        # Fetch the specific document by document ID
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if the document has a file
        if document.file:
            file_path = document.file.path
            
            # Define a generator function to stream the file
            def file_iterator(file_name, chunk_size=512):
                with open(file_name, 'rb') as f:
                    while chunk := f.read(chunk_size):
                        yield chunk
            
            response = StreamingHttpResponse(file_iterator(file_path), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{document.file.name}"'
            return response
        
        return Response({'detail': 'Document file not found.'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='lease/(?P<lease_id>\d+)/documents')
    def list_document_names(self, request, lease_id=None):
        # Fetch documents related to the specified lease ID
        documents = Document.objects.filter(lease_id=lease_id).order_by('version')
        
        if not documents.exists():
            return Response({'detail': 'No documents found for this lease.'}, status=status.HTTP_404_NOT_FOUND)

        # Format the document names
        document_names = [
            {
              'id': doc.id,
              'lease_id': doc.lease_id,
              'name': f"{doc.file.name.split('/')[-1].rsplit('.', 1)[0]}_v{doc.version}",
              'uploaded_at': doc.uploaded_at,
              'status': doc.status,
            }
            for doc in documents
        ]
        
        return Response(document_names, status=status.HTTP_200_OK)
    
    # @action(detail=True, methods=['post'], url_path='review')
    # def review_document(self, request, pk=None):
    #     # Get the document object
    #     document = get_object_or_404(Document, pk=pk)

    #     # Check if the document has a file
    #     if not document.file:
    #         return Response({'detail': 'Document file not found.'}, status=status.HTTP_404_NOT_FOUND)

    #     # Extract text from the PDF file and send it to OpenAI for document review
    #     response = self._analyze_document_with_gpt(document)

    #     # Set the document status based on GPT's response
    #     document.status = response['status']
    #     document.save()

    #     return Response({
    #         'detail': f"Document reviewed and status set to {response['status']}",
    #         'gpt_response': response
    #     }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='review')
    def review_documents(self, request, pk=None):
        document_ids = request.data.get('document_ids', [])  # Get a list of document IDs from the request data
        results = []

        if not document_ids:
            return Response({'detail': 'No document IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)

        for document_id in document_ids:
            document = get_object_or_404(Document, pk=document_id)

            # Check if the document has a file
            if not document.file:
                results.append({'document_id': document_id, 'detail': 'Document file not found.'})
                continue

            # Extract text from the PDF file and send it to OpenAI for document review
            response = self._analyze_document_with_gpt(document)

            # Set the document status based on GPT's response
            document.status = response['status']
            document.save()

            results.append({
                'document_id': document_id,
                'detail': f"Document reviewed and status set to {response['status']}",
                'gpt_response': response
            })

        return Response(results, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat_with_gpt(self, request, pk=None):
        # Get the document object
        document = get_object_or_404(Document, pk=pk)

        user_message = request.data.get('message', '')

        if not user_message:
            return Response({'detail': 'Message is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch document information to dynamically adjust the prompt
        document_info = {
            'name': document.name,
            'status': document.status,
            'version': document.version,
            'uploaded_at': document.uploaded_at,
        }

        openai.api_key = settings.OPENAI_API_KEY

        # Prepare the system prompt with document context
        system_message = f"""
        You are a helpful assistant specializing in lease document review. Here's the context for this document:
        
        Document Name: {document_info['name']}
        Status: {document_info['status']}
        Version: {document_info['version']}
        Uploaded At: {document_info['uploaded_at']}
        
        The user may ask you questions about this document. Provide relevant responses based on the information above.
        """

        # Send the user message along with the dynamic context
        response = self._chat_with_gpt(user_message, document)

        return Response({
            'response': response['message'],
            'status': response['status']
        }, status=status.HTTP_200_OK)
    
    def _analyze_document_with_gpt(self, document):
        # Extract text from the PDF file
        try:
            with open(document.file.path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ''
                for page in reader.pages:
                    text += page.extract_text()

            if not text:
                raise ValueError("No text found in the document.")

            # Retrieve lease details, including address fields
            lease = document.lease  # Assuming the Document model has a ForeignKey to Lease
            address_details = {
                "address1": lease.address1,
                "address2": lease.address2,
                "city": lease.city,
                "state": lease.state,
                "zip_code": lease.zip_code
            }

            openai.api_key = settings.OPENAI_API_KEY
            # Define the system message for the document analysis, including lease details
            system_message = f"""
            The Lease Review API is designed to assist users in reviewing and managing lease documents, 
            particularly for short-term rental agreements. The API provides tenant-centered insights, negotiation assistance, 
            and status updates on each document's completion level. The key functions include analysis, chat support, document 
            version comparison, and collaborative feedback. The following guidelines apply:

            **Lease Details**:
            - Property Address: {address_details['address1']}, {address_details['address2']}
            - City: {address_details['city']}
            - State: {address_details['state']}
            - Zip Code: {address_details['zip_code']}

            **Document Analysis Objective**:
            - Review the document's terms including rent, tenant and landlord responsibilities, access rules, fees, and compliance.
            - Use the address details in the summary, where applicable, to make the analysis specific to the property.
            - Set a status of **Approved** if the document is clear and tenant-friendly, **Draft** if incomplete, or **Rejected** if there are high-risk issues.
            - Recommend negotiation points where applicable, taking into account regulations and tenant rights.

            **Additional Requirements**:
            - Include any property-specific clauses that reference the property at {address_details['address1']} in the analysis.
            - Answer as if you are reviewing the document for this specific property in {address_details['city']}, {address_details['state']}, {address_details['zip_code']}.
            - Notify the user of any unreadable sections in the document.

            - **Chat Functionality**:
            - Users may ask questions; answers should reference prior responses for continuity and avoid redundancy.
            - Advise on tenant protections and relevant lease requirements, focusing on legal considerations and tenant-friendly options.

            - **Version Comparison**:
            - When a new version is uploaded, compare with previous versions and summarize key changes.

            - **Readability Check**:
            - If sections are unreadable, notify the user specifying affected sections.

            Please analyze the following document and provide a summary including its status and specific details for the property at {address_details['address1']}, {address_details['city']}, {address_details['state']}.
            Document Text:
            {text}
            """


            # Call OpenAI API with the system message
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": "Please review this document and determine its status."}
                ]
            )
            
            analysis_result = response['choices'][0]['message']['content'].strip()

            # Determine the status based on the analysis result
            if 'approved' in analysis_result.lower():
                status = 'Approved'
            elif 'rejected' in analysis_result.lower():
                status = 'Rejected'
            else:
                status = 'Draft'

            return {
                'status': status,
                'message': analysis_result
            }

        except Exception as e:
            return {
                'status': 'Error',
                'message': str(e)
            }

    def _chat_with_gpt(self, user_message, document):
        """
        Function to handle a chat with GPT for lease-related questions.
        It dynamically adjusts based on the user's message and the document context.
        """
        try:
            # Extract text from the document
            with open(document.file.path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ''
                for page in reader.pages:
                    text += page.extract_text()

            if not text:
                raise ValueError("No text found in the document.")
            
            openai.api_key = settings.OPENAI_API_KEY

            # Define the system message for dynamic lease-related questions
            system_message = """
            You are an expert assistant specializing in lease document review. The following lease document is provided,
            and your task is to answer user questions based on the content of the document. Your answers should be clear,
            concise, and reflect the information contained in the document. You may assist with questions on:

            - Rent payment terms
            - Tenant and landlord responsibilities
            - Lease duration and termination clauses
            - Fees, deposits, or other financial obligations
            - Specific conditions (such as pets, maintenance, etc.)
            - Any unclear or missing sections that need clarification

            **Guidelines for answering:**
            - Reference specific sections or clauses in the document if applicable.
            - If a section is unclear, mention it and suggest clarification.
            - If the document lacks certain information (such as rent payment details), mention that.
            - Focus on helping the user understand their rights and obligations under the lease.
            
            **Note**: Always base your responses on the provided lease document. If the document doesn't address the user's question directly, inform them accordingly.
            """

            # Combine the system message with the user input and document text
            conversation_history = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"User is asking the following question about the lease document:\n\n{user_message}\n\nHere is the document content:\n{text}"}
            ]

            # Call OpenAI API for dynamic chat interaction
            response = openai.ChatCompletion.create(
                model=settings.MODEL_NAME,
                messages=conversation_history,
                temperature=0.7,
            )

            # Parse the response from GPT
            message = response['choices'][0]['message']['content'].strip()

            return {'message': message, 'status': 'success'}

        except Exception as e:
            return {'message': str(e), 'status': 'error'}
