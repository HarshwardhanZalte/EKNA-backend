# ekna_app/views.py
from ekna_ai.qna_service import QnAService
from ekna_ai.models import QnA
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from ekna_app.models import Organization, OrganizationMembership

# 1. Simple Serializer for the Response
class QnASerializer(serializers.ModelSerializer):
    class Meta:
        model = QnA
        fields = ['id', 'question', 'answer', 'doc_ref', 'created_at']

# 2. The View
class AskQuestionView(APIView):
    """
    Handles user questions using RAG Agent.
    Supports:
    - Personal vs Org scope
    - Specific Document Chat (via target_doc_id)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # 1. Input Validation
        question = request.data.get('question')
        doc_scope = request.data.get('doc_scope', 'PERSONAL').upper()
        target_doc_id = request.data.get('target_doc_id') # Optional: For specific doc chat

        membership = OrganizationMembership.objects.filter(user=request.user).first()
        org_id = membership.organization.pk if membership else None

        if not question:
            return Response({'error': 'Question is required'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Initialize Service
        service = QnAService()
        
        # 3. Call AI Agent
        # Note: This is synchronous (user waits for answer). 
        # For very long chains, you might want to move this to a task + websocket later.
        qna_instance = service.ask_question(
            user=request.user, 
            question_text=question, 
            doc_scope=doc_scope, 
            org_id=org_id,
            target_doc_id=target_doc_id 
        )

        if qna_instance:
            # 4. Return formatted response
            # QnASerializer should include 'doc_ref' field for the frontend to show downloads
            return Response(QnASerializer(qna_instance).data, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Failed to generate an answer. Please check permissions or try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)