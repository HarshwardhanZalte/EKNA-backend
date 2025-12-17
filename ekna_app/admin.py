from django.contrib import admin
from .models import Organization, OrganizationMembership, Document

# Register your models here.

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('org_name', 'description', 'org_owner')
    
@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role')
    search_fields = ('user__username', 'organization__org_name')
    list_filter = ('organization', 'role')
    
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_name", "doc_owner", "doc_scope", "doc_org", "doc_type", "doc_size", "is_processed")
    search_fields = ("doc_name", "doc_owner__username", "doc_org__org_name")
    list_filter = ("doc_org", "doc_owner", "is_processed")