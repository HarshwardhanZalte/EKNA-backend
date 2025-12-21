from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from ekna_auth.models import Users
from .models import Organization, OrganizationMembership, Document
from .serializer import OrganizationSerializer, DocumentSerializer, OrganizationMembershipSerializer
from .utils import upload_fileobj_to_s3, generate_s3_key, delete_file_from_s3
from django.conf import settings
from django.db import transaction
from ekna_app.tasks import process_document_task
from ekna_ai.models import DocumentEmbedding

# Create your views here.

class OrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        memberships = OrganizationMembership.objects.filter(user=user)

        if not memberships.exists():
            return Response({"organizations": []}, status=status.HTTP_200_OK)

        organizations = [membership.organization for membership in memberships]

        serializer = OrganizationSerializer(organizations, many=True)
        return Response({"organizations": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        data = request.data
        org_name = data.get("org_name")
        description = data.get("description")

        if Organization.objects.filter(org_owner=user).exists():
            return Response(
                {"error": "User is already an admin of an organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if OrganizationMembership.objects.filter(user=user).exists():
            return Response(
                {"error": "One User can be a member of only one organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = Organization.objects.create(
            org_name=org_name, description=description, org_owner=user
        )
        OrganizationMembership.objects.create(user=user, organization=organization, role="ADMIN")

        return Response({"message": "Organization created successfully"}, status=status.HTTP_201_CREATED)

    def put(self, request):
        user = request.user
        data = request.data
        org_name = data.get("org_name")
        description = data.get("description")

        try:
            organization = Organization.objects.get(org_owner=user)

            if organization.org_owner != user:
                return Response(
                    {"error": "You are not authorized to update this organization"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            organization.org_name = org_name
            organization.description = description
            organization.save()

        except Organization.DoesNotExist:
            return Response({"error": "Organization not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"message": "Organization updated successfully"}, status=status.HTTP_200_OK)


class OrganizationMembershipView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if OrganizationMembership.objects.filter(user=user).exists():
            org = OrganizationMembership.objects.filter(user=user).first()
            memberships = OrganizationMembership.objects.filter(organization=org.organization)
            serializer = OrganizationMembershipSerializer(memberships, many=True)
            return Response({"memberships": serializer.data}, status=status.HTTP_200_OK)

        return Response(
            {"error": "You are not an member of any organization"}, status=status.HTTP_403_FORBIDDEN
        )

    def post(self, request):
        user = request.user
        email = request.data.get("email")

        try:
            invited_user = Users.objects.get(email=email)
        except Users.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if OrganizationMembership.objects.filter(user=invited_user).exists():
            return Response(
                {"error": "User is already a member of an organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = Organization.objects.filter(org_owner=user).first()
        if not organization:
            return Response(
                {"error": "You are not an admin of any organization"}, status=status.HTTP_403_FORBIDDEN
            )

        OrganizationMembership.objects.create(user=invited_user, organization=organization, role="MEMBER")

        return Response({"message": "User added to organization successfully"}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        user = request.user
        email = request.data.get("email")

        if not Organization.objects.filter(org_owner=user).exists():
            return Response(
                {"error": "You are not an admin of any organization"}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            deleted_user = Users.objects.get(email=email)
        except Users.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        membership = OrganizationMembership.objects.filter(user=deleted_user).first()
        if membership is not None:
            membership.delete()
            return Response({"message": "User removed from organization successfully"}, status=status.HTTP_200_OK)

        return Response({"error": "User is not a member of any organization"}, status=status.HTTP_400_BAD_REQUEST)
    
    
class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user

        # Support multiple files via 'files' field, fall back to single 'file'
        files = request.FILES.getlist('files') or ([request.FILES.get('file')] if request.FILES.get('file') else [])
        if not files:
            return Response({'error': 'At least one file is required (use "files" for multiple).'}, status=status.HTTP_400_BAD_REQUEST)

        doc_scope = request.data.get('doc_scope') or ""
        if not doc_scope:
            return Response({'error': 'doc_scope is required'}, status=status.HTTP_400_BAD_REQUEST)

        doc_scope = doc_scope.upper()
        organization = None

        if doc_scope == 'ORGANIZATION':

            org_qs = Organization.objects.filter(org_owner=user)
            if not org_qs.exists():
                return Response({'error': 'Only an organization owner can upload organization-scoped documents'}, status=status.HTTP_403_FORBIDDEN)
            try:
                organization = org_qs.get()
            except Organization.DoesNotExist:

                return Response({'error': 'Organization not found'}, status=status.HTTP_404_NOT_FOUND)

        elif doc_scope == 'PERSONAL':
            organization = None
        else:
            return Response({'error': 'Invalid document scope. Use "PERSONAL" or "ORGANIZATION".'}, status=status.HTTP_400_BAD_REQUEST)

        successes = []
        failures = []

        for f in files:
            if f is None:
                failures.append({'filename': None, 'error': 'Empty file entry'})
                continue

            try:

                key = generate_s3_key(f.name)
                s3_url = upload_fileobj_to_s3(f, settings.AWS_S3_BUCKET_NAME, key)

                with transaction.atomic():
                    document = Document.objects.create(
                        doc_name=f.name,
                        doc_url=s3_url,
                        doc_owner=user,
                        doc_scope=doc_scope,
                        doc_org=organization,
                        doc_type=getattr(f, 'content_type', None),
                        doc_size=getattr(f, 'size', None),
                        s3_key=key
                    )
                    
                    process_document_task.enqueue(document.pk)

                successes.append({
                    'filename': f.name,
                    'document': DocumentSerializer(document).data
                })

            except Exception as e:
                failures.append({
                    'filename': getattr(f, 'name', None),
                    'error': str(e)
                })

        if not successes:
            return Response({
                'message': 'No files were uploaded.',
                'successes': successes,
                'failures': failures
            }, status=status.HTTP_400_BAD_REQUEST)


        return Response({
            'message': f'{len(successes)} file(s) uploaded successfully.',
            'successes': successes,
            'failures': failures
        }, status=status.HTTP_201_CREATED)    

class DocumentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        doc_id = request.data.get('doc_id')
        user = request.user
        if not doc_id:
            return Response({'error': 'doc_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            document = Document.objects.get(id=doc_id, doc_owner=user)
        except Document.DoesNotExist:
            return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)

        if document.doc_scope == 'ORGANIZATION':
            # Ensure the requesting user is the owner of the *same* organization
            # that this document belongs to, not just any organization.
            if not document.doc_org:
                return Response(
                    {"error": "Organization document is not linked to any organization"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not Organization.objects.filter(id=document.doc_org.pk, org_owner=user).exists():
                return Response(
                    {"error": "You are not an admin of any organization"}, status=status.HTTP_403_FORBIDDEN
                )
            
        deleted_doc = delete_file_from_s3(settings.AWS_S3_BUCKET_NAME, document.s3_key)
        
        if not deleted_doc:
            return Response({'error': 'Failed to delete document from S3'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            document_embeddings = DocumentEmbedding.objects.filter(doc=document)
            document_embeddings.delete()
            document.delete()
            return Response({'message': 'Document deleted successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        scope = request.data.get('doc_scope') or ""
        
        scope = scope.upper()
        
        if scope == 'PERSONAL':
            documents = Document.objects.filter(doc_owner=request.user, doc_scope='PERSONAL').order_by('-created_at')
        elif scope == 'ORGANIZATION':
            org = OrganizationMembership.objects.filter(user=request.user).first()
            if not org:
                return Response({'error': 'User is not a member of any organization'}, status=status.HTTP_400_BAD_REQUEST)
            documents = Document.objects.filter(doc_org=org.organization, doc_scope='ORGANIZATION').order_by('-created_at')
        else:
            return Response({'error': 'Invalid scope. Use "PERSONAL" or "ORGANIZATION".'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)