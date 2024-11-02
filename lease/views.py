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
            serializer.update(lease, serializer.validated_data)
            return Response({'status': 'revised documents uploaded'}, status=status.HTTP_200_OK)
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
                leases = leases.filter(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = timezone.now().date()

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

    @action(detail=False, methods=['get'], url_path='download/lease/(?P<lease_id>\d+)/version/(?P<version>\d+)')
    def download_document(self, request, lease_id=None, version=None):
        # Fetch the specific document by lease ID and version
        try:
            document = Document.objects.get(lease_id=lease_id, version=version)
        except Document.DoesNotExist:
            return Response({'detail': 'Document or version not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if the document has a file
        if document.file:
            file_path = document.file.path
            
            # Define a generator function to stream the file
            def file_iterator(file_name, chunk_size=512):
                with open(file_name, 'rb') as f:
                    while chunk := f.read(chunk_size):
                        yield chunk
            
            response = StreamingHttpResponse(file_iterator(file_path), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{document.file.name}"'
            return response
        
        return Response({'detail': 'Document file not found.'}, status=status.HTTP_404_NOT_FOUND)
