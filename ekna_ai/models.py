from django.db import models
from django.conf import settings
from ekna_app.models import Document, Organization
from pgvector.django import VectorField, HnswIndex

class DocumentEmbedding(models.Model):
    doc = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='embeddings')
    chunk = models.TextField()
    chunk_index = models.IntegerField(default=0) 
    embedding = VectorField(dimensions=384)
    
    class Meta:
        unique_together = ('doc', 'chunk_index') 
        
        indexes = [
            HnswIndex(
                name='embedding_index',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops']
            ),
        ]
    
    def __str__(self):
        return f"{self.doc.doc_name} - Chunk {self.chunk_index}"
    

class QnA(models.Model):
    question = models.TextField()
    answer = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, default=None)
    
    doc_ref = models.JSONField(default=list, blank=True) 
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.question[:50]}..."