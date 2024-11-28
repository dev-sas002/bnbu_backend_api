from rest_framework import serializers
from rental.models import RentalProperty


class RentalPropertySerializer(serializers.ModelSerializer):

    class Meta:
        model = RentalProperty
        fields = "__all__"
