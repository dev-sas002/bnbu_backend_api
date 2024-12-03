# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/views.py
from rental.models import RentalProperty
from rental.serializers import RentalPropertySerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from bnbu_constants.utility import (calculate_monthly_profit, validate_file_type, file_to_df, validate_df, normalize_df,
                                    normalize_column, clean_price, process_rental_properties)
from rest_framework.response import Response
import bnbu_constants.constants as constants
from django.db.models import Max
import datetime


class RentalPropertyViewSet(viewsets.ModelViewSet):
    queryset = RentalProperty.objects.all().order_by('-created_at')
    serializer_class = RentalPropertySerializer

    @action(detail=False, methods=['post'], url_path='upload-properties')
    def upload_rental_properties(self, request):

        # Step 1: Get the file from the request body
        # file = 'rental/data.xlsx'
        file = request.FILES.get("file")
        print("Received file:", file)

        if not file:
            print("No file found in the request.")
            return Response({"success": False,
                             "message": "File does not found"},
                             status=status.HTTP_400_BAD_REQUEST)

        print(f"File received: {file.name}, File size: {file.size} bytes")

        # Step 2: Validate file type
        if not validate_file_type(file):
            print(f"Invalid file type: {file.name}. Expected extensions: {constants.VALID_FILE_EXTENSION}")
            return Response({"success": False,
                             "message": f"Invalid file extension : only {constants.VALID_FILE_EXTENSION} are allowed"},
                             status=status.HTTP_400_BAD_REQUEST)

        print("File type validated successfully.")

        # Step 3: Convert file to DataFrame
        df = file_to_df(file)
        if df.empty:
            print("File is empty or could not be parsed into DataFrame.")
            return Response({"success": False,
                             "message": "File does not contain any data"},
                             status=status.HTTP_400_BAD_REQUEST)

        print(f"DataFrame created successfully with {len(df)} rows.")

        # Step 4: Validate DataFrame columns
        missing_cols = validate_df(df)
        if missing_cols:
            print(f"Missing required columns: {missing_cols}")
            return Response({"success": False,
                             "message": f"File must contain {constants.REQUIRED_COLS}. You must include {missing_cols}"},
                             status=status.HTTP_400_BAD_REQUEST)

        print("All required columns are present in the DataFrame.")

        # Step 5: Normalize the columns
        print("Normalizing columns: 'Ba', 'Br', and 'Sq. ft.'")
        normalize_column(df, "Ba")
        normalize_column(df, "Br")
        normalize_column(df, "Sq. ft.")

        # Step 6: Clean and process 'Price' column
        print("Cleaning 'Price' column...")
        df["Price"] = df["Price"].apply(clean_price)
        print("Price column cleaned.")

        # Step 7: Get the latest batch ID and calculate the new batch ID
        latest_batch = RentalProperty.objects.aggregate(Max('batch_id'))
        latest_batch_id = latest_batch['batch_id__max'] or 0
        new_batch_id = latest_batch_id + 1

        # Step 8: Normalize the DataFrame
        print("Normalizing DataFrame...")
        df = normalize_df(df)
        print("DataFrame normalized.")

        # Step 9: Process rental properties (the main business logic)
        print("Processing rental properties...")
        processed_df = process_rental_properties(df, new_batch_id)
        print("Rental properties processed successfully.")

        # Step 10: Save properties with the new batch ID
        for _, row in processed_df.iterrows():
            rental_property = RentalProperty(
                location=row['Location'],
                rent=row['Price'],
                no_of_bedrooms=row['Br'],
                no_of_bathrooms=row['Ba'],
                square_feet=row['Sq. ft.'],
                property_zillow_link=row['Link'],
                adr=row['ADR'], 
                occupancy_rate=row['Occupancy'],
                utilities=row['utilities'],
                yearly_projected_revenue=row['Revenue'],
                monthly_estimated_profit=row['monthly_estimated_profit'],
                batch_id=new_batch_id,
                property_status=row['property_status'],
                created_at= datetime.datetime.now(),
                updated_at=datetime.datetime.now(),
            )
            data = calculate_monthly_profit(rental_property.yearly_projected_revenue, rental_property.rent, rental_property.no_of_bedrooms)
            rental_property.yearly_rent_cost_util = data[2]
            rental_property.save() 

        print(f"Batch {new_batch_id} processed successfully.")

        return Response({"success": True,
                         "message": f"Successfully processed batch {new_batch_id}",
                         "data": processed_df.to_dict(orient='records')},
                         status=status.HTTP_201_CREATED)
        