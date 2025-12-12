from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from ekna_auth.models import Users
from .models import Organization, OrganizationMembership, Document
from datetime import timedelta
from .serializer import OrganizationSerializer, DocumentSerializer, OrganizationMembershipSerializer
from .utils import get_s3_client, upload_fileobj_to_s3, generate_s3_key
import mimetypes
from django.conf import settings
from django.db import transaction
import os

# Create your views here.

class OrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        organizations = Organization.objects.filter(org_owner=user)
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

        if Organization.objects.filter(org_owner=user).exists():
            memberships = OrganizationMembership.objects.filter(organization__org_owner=user)
            serializer = OrganizationMembershipSerializer(memberships, many=True)
            return Response({"memberships": serializer.data}, status=status.HTTP_200_OK)

        return Response(
            {"error": "You are not an admin of any organization"}, status=status.HTTP_403_FORBIDDEN
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

        doc_scope = request.data.get('doc_scope')
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
                        doc_size=getattr(f, 'size', None)
                    )

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

