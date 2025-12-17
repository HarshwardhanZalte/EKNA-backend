import logging
import boto3
from datetime import datetime
from pgvector.django import CosineDistance

# LangChain Tools
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

# Models & Settings
from ekna_app.models import Document, Organization, OrganizationMembership
from ekna_ai.models import DocumentEmbedding
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from django.conf import settings
from ekna_app.utils import get_s3_client

logger = logging.getLogger(__name__)

# --- HELPER: Generate Fresh S3 Link ---
def get_presigned_url(s3_key):
    """
    Generates a temporary public link (valid for 1 hour) for private S3 files.
    """
    try:
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=3600 # 1 Hour
        )
        return url
    except Exception as e:
        logger.error(f"S3 Presign Error: {e}")
        return "#" # Return placeholder if fails

# --- SECURITY ---
def validate_access(user, doc_scope, org_id):
    if doc_scope == 'ORGANIZATION':
        if not org_id:
            raise PermissionError("Organization ID is required for Organization scope.")
        is_owner = Organization.objects.filter(id=org_id, org_owner=user).exists()
        is_member = OrganizationMembership.objects.filter(user=user, organization_id=org_id).exists()
        if not (is_owner or is_member):
            raise PermissionError("Access denied to this organization.")
    return True

def get_allowed_documents(user, doc_scope, org_id, target_doc_id=None):
    if doc_scope == 'ORGANIZATION':
        qs = Document.objects.filter(doc_org_id=org_id, doc_scope='ORGANIZATION')
    else:
        qs = Document.objects.filter(doc_owner=user, doc_scope='PERSONAL')

    if target_doc_id:
        qs = qs.filter(id=target_doc_id)
    return qs

# --- TOOL LOGIC ---

def _logic_vector_search(query, user, doc_scope, org_id, citations_tracker, target_doc_id=None):
    try:
        embeddings_model = HuggingFaceEndpointEmbeddings(
            huggingfacehub_api_token=settings.HUGGINGFACE_API_TOKEN,
            model=settings.EMMBEDDING_MODEL_NAME 
        )
        
        allowed_docs = get_allowed_documents(user, doc_scope, org_id, target_doc_id)
        query_vector = embeddings_model.embed_query(query)

        similar_chunks = DocumentEmbedding.objects.filter(
            doc__in=allowed_docs
        ).annotate(
            distance=CosineDistance('embedding', query_vector)
        ).order_by('distance')[:5]

        if not similar_chunks:
            return "No relevant content found."

        results_text = ""
        for item in similar_chunks:
            # GENERATE FRESH LINK
            fresh_url = get_presigned_url(item.doc.s3_key)
            
            # 1. Give Context + Link to LLM
            results_text += f"\n[Document: {item.doc.doc_name} | Download Link: {fresh_url}]\nContent: {item.chunk}\n"
            
            # 2. Track Citation
            doc_data = {
                'doc_id': item.doc.id,
                'doc_name': item.doc.doc_name,
                'doc_url': fresh_url # Save fresh link to DB reference
            }
            if doc_data['doc_id'] not in [c['doc_id'] for c in citations_tracker]:
                citations_tracker.append(doc_data)
        
        return results_text

    except Exception as e:
        logger.error(f"Vector Search Error: {e}")
        return f"Error: {str(e)}"

def _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso=None, file_type=None, target_doc_id=None):
    qs = get_allowed_documents(user, doc_scope, org_id, target_doc_id)

    if date_iso:
        try:
            search_date = datetime.strptime(date_iso, "%Y-%m-%d").date()
            qs = qs.filter(created_at__date=search_date)
        except ValueError:
            return "Error: Invalid date format."

    if file_type:
        qs = qs.filter(doc_name__icontains=file_type)

    count = qs.count()
    docs = list(qs[:10]) 
    
    msg = f"Found {count} documents."
    if count > 0:
        msg += " Here are the files:"
        for doc in docs:
            # GENERATE FRESH LINK
            fresh_url = get_presigned_url(doc.s3_key)
            
            msg += f"\n- {doc.doc_name} (Link: {fresh_url})"
            
            doc_data = {'doc_id': doc.id, 'doc_name': doc.doc_name, 'doc_url': fresh_url}
            if doc_data['doc_id'] not in [c['doc_id'] for c in citations_tracker]:
                citations_tracker.append(doc_data)
    
    return msg

# --- TOOL FACTORY ---

def get_tools_for_user(user, doc_scope, org_id, citations_tracker, target_doc_id=None):
    @tool
    def search_document_content(query: str):
        """Search inside document text. Returns content AND download links."""
        return _logic_vector_search(query, user, doc_scope, org_id, citations_tracker, target_doc_id)

    @tool
    def query_my_document_stats(date_iso: str, file_type: str):
        """Get metadata/counts of files. Returns names AND download links."""
        return _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso, file_type, target_doc_id)

    @tool
    def web_search(query: str):
        """Search the public internet."""
        return DuckDuckGoSearchRun().invoke(query)

    return [search_document_content, query_my_document_stats, web_search]