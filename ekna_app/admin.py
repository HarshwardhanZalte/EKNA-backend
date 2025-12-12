from django.contrib import admin
from .models import Organization, OrganizationMembership, Document

# Register your models here.

admin.site.register(Organization)
admin.site.register(OrganizationMembership)
admin.site.register(Document)
