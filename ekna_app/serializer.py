from rest_framework import serializers
from .models import Organization, OrganizationMembership, Document


class OrganizationSerializer(serializers.ModelSerializer):
    org_owner = serializers.StringRelatedField()  # uses __str__ of user model

    class Meta:
        model = Organization
        fields = ["id", "org_name", "description", "org_owner"]


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    organization = OrganizationSerializer()

    class Meta:
        model = OrganizationMembership
        fields = ["id", "user", "organization", "role"]


# class DocumentSerializer(serializers.ModelSerializer):
#     doc_owner = serializers.StringRelatedField()

#     class Meta:
#         model = Document
#         fields = ["id", "doc_name", "doc_url", "doc_owner", "doc_scope", "doc_org"]

class DocumentSerializer(serializers.ModelSerializer):
    doc_owner = serializers.StringRelatedField()
    
    class Meta:
        model = Document
        fields = [
            "id",
            "doc_name",
            "doc_url",
            "doc_scope",
            "doc_owner",
            "doc_org",
            "doc_type",
            "doc_size",
            "is_processed",
            "created_at",
        ]