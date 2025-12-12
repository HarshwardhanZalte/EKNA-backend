from django.urls import path, include
from .views import OrganizationView, OrganizationMembershipView

urlpatterns = [
    path('org/', OrganizationView.as_view(), name='organization'),
    path('org-member/', OrganizationMembershipView.as_view(), name='organization_membership'),
]