# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/views.py
from rental.models import RentalProperty
from rental.serializers import RentalPropertySerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from bnbu_constants.utility import (validate_file_type, file_to_df, validate_df, normalize_df,
                                    normalize_column, clean_price)
from rest_framework.response import Response
import bnbu_constants.constants as constants
from django.db.models import Max
from datetime import datetime, timedelta
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from .permissions import IsClientOrAdmin
from rest_framework.permissions import IsAuthenticated
from rental.tasks import process_rental_properties_task

class RentalPropertyPagination(PageNumberPagination):
    page_size = 10  # Default number of items per page
    page_size_query_param = 'page_size'  # Allow client to specify page size
    # max_page_size = 100  # Maximum allowed page size

class RentalPropertyViewSet(viewsets.ModelViewSet):
    queryset = RentalProperty.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated, IsClientOrAdmin]
    serializer_class = RentalPropertySerializer
    pagination_class = RentalPropertyPagination


    @action(detail=False, methods=['post'], url_path='upload-properties')
    def upload_rental_properties(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"success": False, "message": "File not found"}, status=status.HTTP_400_BAD_REQUEST)

        if not validate_file_type(file):
            return Response({"success": False, "message": f"Invalid file type"}, status=status.HTTP_400_BAD_REQUEST)

        df = file_to_df(file)
        if df.empty:
            return Response({"success": False, "message": "File contains no data"}, status=status.HTTP_400_BAD_REQUEST)

        missing_cols = validate_df(df)
        if missing_cols:
            return Response({"success": False, "message": f"Missing columns: {missing_cols}"}, status=status.HTTP_400_BAD_REQUEST)

        normalize_column(df, "Ba")
        normalize_column(df, "Br")
        normalize_column(df, "Sq. ft.")
        df["Price"] = df["Price"].apply(clean_price)

        latest_batch = RentalProperty.objects.aggregate(Max('batch_id'))
        latest_batch_id = latest_batch['batch_id__max'] or 0
        new_batch_id = latest_batch_id + 1

        df = normalize_df(df)

        # Trigger Celery task
        task = process_rental_properties_task.delay(df.to_json(orient='records'), new_batch_id)

        return Response({"success": True, "message": f"Batch {new_batch_id} processing started", "task_id": task.id}, status=status.HTTP_202_ACCEPTED)
    
    @action(detail=False, methods=['get'], url_path='all-properties')
    def all_properties(self, request):
        # Fetch all rental properties
        rental_properties = RentalProperty.objects.all().order_by('-created_at')
        
        # Paginate the results
        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)

        # Serialize the results
        serializer = self.get_serializer(paginated_properties, many=True)

        # Return paginated response
        return paginator.get_paginated_response(serializer.data)


    @action(detail=False, methods=['post'], url_path='filtered-list')
    def filtered_list(self, request):
        filters = request.data
        min_profit = filters.get("min_profit")
        max_profit = filters.get("max_profit")
        status = filters.get("status")
        batch_id = filters.get("batch_id")
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")

        rental_properties = RentalProperty.objects.all()  # Initialize the queryset
        # print( '======')
        # print(rental_properties, '======')
        # Build the query
        query = Q()

        # Apply filters only if they are provided
        if min_profit is not None:
            query &= Q(monthly_estimated_profit__gte=min_profit)
        if max_profit is not None:
            query &= Q(monthly_estimated_profit__lte=max_profit)
        if status is not None:
            query &= Q(property_status=status)
        if batch_id is not None:
            query &= Q(batch_id=batch_id)

        # Handle start_date
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%B %d, %Y').date()
                query &= Q(created_at__gte=start_date)
            except ValueError:
                return Response({'detail': 'Invalid start date format. Use "Month day, year" (e.g., December 3, 2024).'}, 
                                status=status.HTTP_400_BAD_REQUEST)

        # Handle end_date
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%B %d, %Y').date()
                end_date = end_date + timedelta(days=1)  # Make the end_date exclusive
                query &= Q(created_at__lte=end_date)
            except ValueError:
                return Response({'detail': 'Invalid end date format. Use "Month day, year" (e.g., December 3, 2024).'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            end_date = datetime.now().date()

        # print('query', query)
        # If no filters are applied, the query will still be an empty Q() object, which will return all results
        rental_properties = rental_properties.filter(query).order_by('-created_at')
        # print('filtered data', rental_properties)
        # Paginate the results
        paginator = RentalPropertyPagination()
        paginated_properties = paginator.paginate_queryset(rental_properties, request)

        # Serialize the results
        serializer = self.get_serializer(paginated_properties, many=True)
        return paginator.get_paginated_response(serializer.data)
