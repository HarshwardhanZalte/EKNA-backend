from django.db import models
from django.conf import settings

# Create your models here.

class Organization(models.Model):
    org_name = models.CharField(max_length=100)
    description = models.TextField()
    org_owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.org_name} - {self.org_owner}"


class Document(models.Model):
    SCOPE = [('PERSONAL', 'Personal'), ('ORGANIZATION', 'Organization')]

    doc_name = models.CharField(max_length=100)
    doc_url = models.URLField()
    doc_owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    doc_scope = models.CharField(max_length=15, choices=SCOPE, default='PERSONAL')
    doc_org = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, default=None)
    doc_type = models.CharField(max_length=100, null=True, blank=True, default=None)
    doc_size = models.CharField(max_length=100, null=True, blank=True, default=None)
    is_processed = models.BooleanField(default=False)
    s3_key = models.CharField(max_length=512)

    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.doc_name} - {self.doc_owner}"


class OrganizationMembership(models.Model):
    ROLE = [('MEMBER', 'Member'), ('ADMIN', 'Admin')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(max_length=15, choices=ROLE, default='MEMBER')

    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.user} - {self.organization}"
