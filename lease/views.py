from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import Lease, Document
from .serializers import GPTChatSerializer, LeaseSerializer, LeaseUploadSerializer, RevisedLeaseUploadSerializer, DocumentSerializer
from rest_framework.permissions import IsAuthenticated
from .permissions import IsClientOrAdmin  # Import the custom permission class
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.http import StreamingHttpResponse, Http404
from datetime import timedelta, datetime, timezone
import openai
import PyPDF2
from django.shortcuts import get_object_or_404
from django.conf import settings
import json


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
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                leases = leases.filter(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                end_date = end_date + timedelta(days=1)  # This will now represent the start of the next day
                leases = leases.filter(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = datetime.now().date()

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
            document.gpt_response = response
            document.save()

            results.append({
                'document_id': document_id,
                'detail': f"Document reviewed and status set to {response['status']}",
                'gpt_response': response
            })

        return Response(results, status=status.HTTP_200_OK)
    
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

            openai.api_key = settings.OPENAI_API_KEY
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
            The GPT avoids giving direct legal advice but provides a thorough assessment to help the user feel confident in negotiating and signing a lease. 
            It speaks in a formal and direct manner, ensuring clarity and professionalism in its assessments.

            Please analyze the lease document and provide a clear assessment. 
            Specifically, include a status for the lease: 
            - "Approved" if the lease is favorable and there are no significant concerns.
            - "Rejected" if there are major unfavorable clauses or legal risks.
            - "Draft" if the lease is in an incomplete or negotiable state, and suggest any improvements or issues that need addressing.
            
            Please ensure the status is clearly mentioned in the response along with a summary of your findings.
            
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
            created_time = response.get('created')

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


    @action(detail=True, methods=['post'], url_path='chat')
    def chat_with_gpt(self, request, pk=None):
        # Validate input using GPTChatSerializer
        serializer = GPTChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract validated data
        document_id = serializer.validated_data.get('document_id')
        user_message = serializer.validated_data.get('message')

        # Fetch the document
        document = get_object_or_404(Document, id=document_id)

        # Fetch the summary from the document's GPT review response
        gpt_response_data = document.gpt_response if document.gpt_response else {}
        summary = gpt_response_data.get('message', 'No summary available. Please review the document first.')

        # Prepare the system message with document context
        system_message = f"""
        You are a short-term rental contract expert designed to help users, especially students, review rental leases. Your primary goal is to assist users in identifying unusual clauses, potential legal risks, and ensuring transparency within the lease documents.

        Key responsibilities include:
        - Identifying critical financial details such as rent amounts and security deposits.
        - Reviewing leases for unfavorable terms to the tenant, including disproportionate fees, restrictions, or unclear responsibilities.
        - Making suggestions for favorable terms and negotiation strategies.
        - Ensuring checkbox provisions are correctly applied, particularly regarding assignment, subleasing, and permissions.
        - Focusing on key areas such as lease length, related fees, and responsibilities of both the landlord and tenant.

        Review Summary: {summary}

        The user may ask questions about this document. Provide relevant responses based on the review summary and chat history.
        """

        # Initialize the chat history
        chat_history = document.chat_history or []
        # Add the user's message with a timestamp
        user_message_entry = {
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        chat_history.append(user_message_entry)

        # Set up the OpenAI API key
        openai.api_key = settings.OPENAI_API_KEY

        # Generate a response using OpenAI's GPT model
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {'role': 'system', 'content': system_message},
                *chat_history
            ]
        )

        gpt_response = response['choices'][0]['message']['content']

        # Append the GPT response with a timestamp to the chat history
        gpt_response_entry = {
            'role': 'assistant',
            'content': gpt_response,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        chat_history.append(gpt_response_entry)
        document.chat_history = chat_history
        document.save()

        return Response({
            'response': gpt_response,
            'chat_history': chat_history,
            'summary': summary
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], url_path='get-chat-history')
    def get_chat_history(self, request, pk=None):
        # Fetch the document
        document = get_object_or_404(Document, id=pk)

        # Fetch the GPT response and chat history from the document
        gpt_response_data = document.gpt_response if document.gpt_response else {}
        chat_history = document.chat_history or []

        # Prepare the response data
        response_data = {
        'gpt_response': {
            'message': gpt_response_data.get('message'),
            'status': gpt_response_data.get('status'),
            'created_time': gpt_response_data.get('created_time')
        },
        'chat_history': chat_history,
    }

        return Response(response_data, status=status.HTTP_200_OK)
    