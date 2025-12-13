from django.urls import path
from .views import OrganizationView, OrganizationMembershipView, DocumentUploadView, DocumentDeleteView, DocumentListView

urlpatterns = [
    path('org/', OrganizationView.as_view(), name='organization'),
    path('org-member/', OrganizationMembershipView.as_view(), name='organization_membership'),
    path('doc-upload/', DocumentUploadView.as_view(), name='document_upload'),
    path('doc-delete/', DocumentDeleteView.as_view(), name='document_delete'),
    path('documents/', DocumentListView.as_view(), name='document_list'),
]