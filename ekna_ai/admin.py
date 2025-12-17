from django.contrib import admin
from .models import DocumentEmbedding, QnA
# Register your models here.

@admin.register(DocumentEmbedding)
class DocumentEmbeddingAdmin(admin.ModelAdmin):
    list_display = ['doc', 'chunk_index']

@admin.register(QnA)
class QnAAdmin(admin.ModelAdmin):
    list_display = ['user', 'question', 'answer']
    list_filter = ['user']