# serializers.py
from rest_framework import serializers
from .models import Lease, Document

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'name', 'file','version', 'uploaded_at']

class LeaseSerializer(serializers.ModelSerializer):
    num_of_docs = serializers.IntegerField(read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Lease
        fields = [
            'id', 'date', 'address1', 'address2', 'city', 'state', 'zip_code', 
            'status', 'num_of_docs', 'documents'
        ]

class LeaseUploadSerializer(serializers.ModelSerializer):
    documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Lease
        fields = ['address1', 'address2', 'city', 'state', 'zip_code', 'status', 'documents']

    def create(self, validated_data):
        documents = validated_data.pop('documents', [])
        user = self.context['request'].user
        lease = Lease.objects.create(user=user, **validated_data)  # Associate with the user
        for doc in documents:
            Document.objects.create(lease=lease, file=doc, name=doc.name)  # Set the document name
        return lease
    
class RevisedLeaseUploadSerializer(serializers.Serializer):
    documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=True
    )

    def update(self, instance, validated_data):
        documents = validated_data.pop('documents', [])
        for doc in documents:
            Document.objects.create(lease=instance, file=doc, name=doc.name)
        return instance
    

