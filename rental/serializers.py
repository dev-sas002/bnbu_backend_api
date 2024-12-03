# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/rental/serializers.py
from rest_framework import serializers
from rental.models import RentalProperty


class RentalPropertySerializer(serializers.ModelSerializer):

    class Meta:
        model = RentalProperty
        fields = "__all__"
