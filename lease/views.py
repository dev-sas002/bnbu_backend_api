from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import Lease
from .serializers import LeaseSerializer, LeaseUploadSerializer, RevisedLeaseUploadSerializer
from rest_framework.permissions import IsAuthenticated
from .permissions import IsClientOrAdmin  # Import the custom permission class

class LeaseViewSet(viewsets.ModelViewSet):
    queryset = Lease.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['address1', 'city']
    permission_classes = [IsAuthenticated, IsClientOrAdmin]  # Update permission classes

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
        city = request.query_params.get('city')
        status_value = request.query_params.get('status')

        leases = Lease.objects.all()
        
        if address:
            leases = leases.filter(address1__icontains=address)
        if city:
            leases = leases.filter(city__icontains=city)
        if status_value:
            leases = leases.filter(status=status_value)

        serializer = self.get_serializer(leases, many=True)
        return Response(serializer.data if leases.exists() else {'detail': 'No leases found.'}, status=status.HTTP_200_OK)
