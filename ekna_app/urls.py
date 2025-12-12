from django.urls import path, include
from .views import OrganizationView, OrganizationMembershipView, DocumentUploadView

urlpatterns = [
    path('org/', OrganizationView.as_view(), name='organization'),
    path('org-member/', OrganizationMembershipView.as_view(), name='organization_membership'),
    path('document/', DocumentUploadView.as_view(), name='document_upload')
]