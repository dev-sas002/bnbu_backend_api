from rental.models import RentalProperty
from rental.serializers import RentalPropertySerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from bnbu_constants.utility import (validate_file_type, file_to_df, validate_df, normalize_df,
                                    normalize_column, clean_price, process_rental_properties)
from rest_framework.response import Response
import bnbu_constants.constants as constants


class RentalPropertyViewSet(viewsets.ModelViewSet):
    queryset = RentalProperty.objects.all().order_by('-created_at')
    serializer_class = RentalPropertySerializer

    @action(detail=False, methods=['post'], url_path='upload-properties')
    def upload_rental_properties(self, request):

        # TO DO -> get the file from the request body
        # file = request.FILES.get("file")
        file = 'rental/data.xlsx'

        if not file:
            return Response({"success": False,
                            "message": "File does not found"},
                            status=status.HTTP_400_BAD_REQUEST)

        if not validate_file_type(file):
            return Response({"success": False,
                            "message": f"Invalid file extension : only {constants.VALID_FILE_EXTENSION} are allowed"},
                            status=status.HTTP_400_BAD_REQUEST)

        df = file_to_df(file)
        if df.empty:
            return Response({"success": False,
                            "message": "File does not contain any data"},
                            status=status.HTTP_400_BAD_REQUEST)

        missing_cols = validate_df(df)
        if missing_cols:
            return Response({"success": False,
                            "message": f"File must contain {constants.REQUIRED_COLS}. You must include {missing_cols}"},
                            status=status.HTTP_400_BAD_REQUEST)

        normalize_column(df, "Ba")
        normalize_column(df, "Br")
        normalize_column(df, "Sq. ft.")
        df["Price"] = df["Price"].apply(clean_price)
        df = normalize_df(df)
        process_rental_properties(df)
