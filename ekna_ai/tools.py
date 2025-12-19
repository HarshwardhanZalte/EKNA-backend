import logging
from datetime import datetime
from pgvector.django import CosineDistance

# LangChain Tools
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from pgvector.django import CosineDistance
from langchain_huggingface import HuggingFaceEmbeddings


# Models & Settings
from ekna_app.models import Document, Organization, OrganizationMembership
from ekna_ai.models import DocumentEmbedding


from django.conf import settings

logger = logging.getLogger(__name__)

# Security
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

# Tool Logic


def _logic_vector_search(query, user, doc_scope, org_id, citations_tracker, target_doc_id=None):
    try:
        embeddings_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        allowed_docs = get_allowed_documents(user, doc_scope, org_id, target_doc_id)

        query_vector = embeddings_model.embed_query(query)

        TOP_K = getattr(settings, "QNA_TOP_K_CHUNKS", 10)

        similar_chunks = (
            DocumentEmbedding.objects.filter(doc__in=allowed_docs)
            .annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:TOP_K]
        )

        if not similar_chunks:
            return "No relevant content found."

        results_text = ""
        for item in similar_chunks:
            doc_url = item.doc.doc_url
            results_text += (
                f"\n[Document: {item.doc.doc_name} | Link: {doc_url}]\n"
                f"{item.chunk}\n"
            )

            if item.doc.id not in [c["doc_id"] for c in citations_tracker]:
                citations_tracker.append({
                    "doc_id": item.doc.id,
                    "doc_name": item.doc.doc_name,
                    "doc_url": doc_url
                })

        return results_text

    except Exception as e:
        logger.error(f"Vector Search Error: {e}")
        return "Vector search failed."



def _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso=None, file_type=None, target_doc_id=None):
    # For stats queries, we want ALL documents, not just the target_doc_id
    # target_doc_id is only used for content search, not for counting/stats
    qs = get_allowed_documents(user, doc_scope, org_id, target_doc_id=None)

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
            doc_url = doc.doc_url
            uploaded_at = doc.created_at.strftime("%Y-%m-%d %H:%M")

            msg += f"\n- {doc.doc_name} | Uploaded: {uploaded_at} | Link: {doc_url}"

            doc_data = {
                'doc_id': doc.pk,
                'doc_name': doc.doc_name,
                'doc_url': doc_url,
                'uploaded_at': uploaded_at,
            }
            if doc_data['doc_id'] not in [c['doc_id'] for c in citations_tracker]:
                citations_tracker.append(doc_data)
    
    return msg

# Tool Factory

def get_tools_for_user(user, doc_scope, org_id, citations_tracker, target_doc_id=None):
    @tool
    def search_document_content(query: str):
        """Search inside document text. Returns content AND download links."""
        return _logic_vector_search(query, user, doc_scope, org_id, citations_tracker, target_doc_id)

    @tool
    def query_my_document_stats(date_iso: str, file_type: str):
        """Get metadata/counts of files. Returns names AND download links."""
        return _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso, file_type, target_doc_id)

    tools = [search_document_content, query_my_document_stats]

    enable_web_search = getattr(settings, "ENABLE_WEB_SEARCH", False)
    if enable_web_search:
        @tool
        def web_search(query: str):
            """Search the public internet."""
            return DuckDuckGoSearchRun().invoke(query)

        tools.append(web_search)

    return tools