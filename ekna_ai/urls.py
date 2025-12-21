from django.urls import path
from .views import AskQuestionView, ChatHistoryView

urlpatterns = [
    path('ask/', AskQuestionView.as_view(), name='qna-ask'),
    path('history/', ChatHistoryView.as_view(), name='chat-history'),
]