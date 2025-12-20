import logging
from datetime import datetime
from typing import Optional
from pgvector.django import CosineDistance

# LangChain Tools
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
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

        chunks_list = list(similar_chunks)

        if not chunks_list:
            return "No relevant content found."

        results_text = ""
        for item in chunks_list:
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
        logger.error(f"Vector search error: {e}", exc_info=True)
        return "Vector search failed."



def _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso=None, file_type=None, target_doc_id=None):
    try:
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
    
    except Exception as e:
        logger.error(f"DB stats error: {e}", exc_info=True)
        return f"Error retrieving document stats: {str(e)}"

# Tool Factory

def get_tools_for_user(user, doc_scope, org_id, citations_tracker, target_doc_id=None):
    @tool
    def search_document_content(query: str):
        """Search inside document text. Returns content AND download links."""
        logger.info(f"Tool: search_document_content | Query: '{query[:100]}'")
        result = _logic_vector_search(query, user, doc_scope, org_id, citations_tracker, target_doc_id)
        return result

    @tool
    def query_my_document_stats(date_iso: Optional[str] = None, file_type: Optional[str] = None):
        """Get metadata/counts of files. Returns names AND download links.
        
        Use this tool when the user asks:
        - "How many documents do I have?"
        - "List my files"
        - "Show me documents from [date]"
        - "What files do I have?"
        
        Parameters:
        - date_iso: Optional date filter in YYYY-MM-DD format (e.g., "2024-01-15")
        - file_type: Optional file type/name filter (e.g., "pdf", "excel", "budget")
        """
        logger.info(f"Tool: query_my_document_stats | Date: {date_iso}, Type: {file_type}")
        result = _logic_db_stats(user, doc_scope, org_id, citations_tracker, date_iso, file_type, target_doc_id)
        return result

    @tool
    def web_search(query: str):
        """
        Search the public internet for current information, news, sports scores, weather, or any information not available in the user's documents.
        
        Use this tool when:
        - User asks about current events, news, or recent information
        - User asks about sports scores, match results, or live data
        - User asks about information that cannot be found in their documents
        - User explicitly requests web/internet search
        
        Examples: "Who won the IND vs SA match yesterday?", "What's the current weather?", "Latest news about AI"
        """
        try:
            logger.info(f"Tool: web_search | Query: '{query[:100]}'")
            search_tool = DuckDuckGoSearchRun()
            result = search_tool.invoke(query)
            if not result:
                logger.warning(f"Web search returned empty result for: '{query[:100]}'")
                return f"No results found for query: {query}. Please try rephrasing your question."
            return result
        except Exception as e:
            logger.error(f"Web search error: {e}", exc_info=True)
            return f"Web search failed: {str(e)}. Please try again or rephrase your query."
    
    return [search_document_content, query_my_document_stats, web_search]