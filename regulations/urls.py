from django.urls import path
from .views import RegulationsChatGPTAPIView

urlpatterns = [
  path("regulations/chatgpt/", RegulationsChatGPTAPIView.as_view(), name="regulations-chatgpt-api"),
]

