from rest_framework import serializers

class RegulationsChatGPTRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField(
        required=True, help_text="The input text to send to ChatGPT."
    )