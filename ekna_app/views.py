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