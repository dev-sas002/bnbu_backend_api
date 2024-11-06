from drf_yasg import openapi
from rest_framework.decorators import permission_classes
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegulationsChatGPTRequestSerializer
from rest_framework.permissions import IsAuthenticated
import openai
from django.conf import settings

class RegulationsChatGPTAPIView(APIView):
    # permission_classes = [IsAuthenticated]
    serializer_class = RegulationsChatGPTRequestSerializer

    @swagger_auto_schema(
        operation_description="Send input to the ChatGPT API and get a response.",
        request_body=RegulationsChatGPTRequestSerializer,
        responses={
            200: openapi.Response(
                "Response from ChatGPT",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "data": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            400: openapi.Response(
                "Invalid input",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "errors": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            ),
            500: openapi.Response(
                "Server error",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        # Initialize the serializer with request data
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            prompt = serializer.validated_data.get("prompt")
            if not prompt:
                return Response(
                    {"success": False, "message": "Prompt is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                openai.api_key = settings.OPENAI_API_KEY

                # Prepare the system message with the specific instructions
                system_message = """
                This GPT acts as a knowledgeable consultant specializing in short-term rental (STR) laws, providing users with concise and comprehensive information, advice, 
                and strategies related to the legality of short-term rentals in various areas. Each response begins with a clear status update of the STR legality in the
                specific area: 'SHORT TERM RENTAL ALLOWED,' 'SHORT TERM RENTAL ALLOWED WITH RESTRICTIONS,' or 'SHORT TERM RENTAL NOT ALLOWED.' 
                After this, the GPT offers bullet-point summaries of the relevant regulations, ensuring that users can quickly grasp the key points. 
                It focuses on how to obtain the necessary permits and always includes clickable links to the sources for verification. 
                All URLs in the response will be formatted using Markdown syntax to ensure they are 100% clickable, 
                like this: [Click here](http://example.com). If STRs are banned or restricted, the GPT actively researches and highlights any potential loopholes,
                alternative permits, reclassification strategies, or other legal workarounds that could enable operation in the area. 
                The GPT also automatically checks and verifies whether the property is in the correct zoning area to operate a short-term rental. If there are zoning issues,
                it assists users in understanding and addressing them. The GPT offers balanced, well-rounded insights, considering both the benefits and risks of each option,
                helping users make informed decisions. Responses are informative and thorough, including helpful resources and citations with clickable links to ensure users
                have access to the most relevant and accurate information. URLs and resources cited are formatted as clickable links to ensure easy access. and give me full response
                """

                # Messages to send to the OpenAI API
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ]

                # Call the OpenAI API
                response = openai.ChatCompletion.create(
                    model=settings.MODEL_NAME, messages=messages, temperature=0.7
                )

                # Extract the response content
                chatgpt_response = response.choices[0].message["content"]

                return Response(
                    {
                        "success": True,
                        "message": "ChatGPT response received successfully.",
                        "data": chatgpt_response,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                return Response(
                    {
                        "success": False,
                        "message": f"Error communicating with OpenAI: {str(e)}",
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                {
                    "success": False,
                    "message": "Invalid input.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

