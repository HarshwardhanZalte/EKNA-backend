import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from django.conf import settings

# Models
from ekna_app.models import Document
from ekna_ai.models import QnA

# LangChain
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_groq import ChatGroq
from langchain.agents.middleware import SummarizationMiddleware

# Project Imports
from ekna_ai.tools import get_tools_for_user, validate_access, get_allowed_documents
from ekna_ai.prompts import get_system_prompt

logger = logging.getLogger(__name__)


class LoggingMiddleware(AgentMiddleware):
    """
    Middleware to log agent activity. 
    Useful for debugging AI decisions in production.
    """
    def wrap_model_call(self, request: ModelRequest, handler):
        message_count = len(request.messages)
        logger.info(f"[EKNA_AI] Sending {message_count} messages to LLM")
        
        response = handler(request)
        
        # Only log tool calls (important for debugging)
        if hasattr(response, 'messages') and response.messages:
            for msg in response.messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = getattr(tool_call, 'name', 'unknown')
                        tool_input = getattr(tool_call, 'args', {})
                        logger.info(f"Tool call: {tool_name} | Args: {tool_input}")
        
        return response

# SERVICE
class QnAService:
    def __init__(self):
        # Initialize the Chat Model once
        self.llm_model = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=settings.LLM_MODEL_NAME,
            temperature=0.1 
        )

    def ask_question(self, user, question_text, doc_scope='PERSONAL', org_id=None, target_doc_id=None):
        """
        Main entry point for the Q&A feature.
        Handles security, context setup, agent execution, and saving history.
        """
        try:
            # Security Validation 
            try:
                validate_access(user, doc_scope, org_id)
                
                # Extra check: If target_doc_id is provided, verify existence & permission
                if target_doc_id:
                    valid_doc = get_allowed_documents(user, doc_scope, org_id, target_doc_id).exists()
                    if not valid_doc:
                         return self._save_qna(user, question_text, "Error: You do not have permission to access this specific document, or it does not exist.", [], org_id)

            except PermissionError as e:
                return self._save_qna(user, question_text, f"Permission Error: {str(e)}", [], org_id)

            # Context Setup 
            citations = []  

            tools = get_tools_for_user(user, doc_scope, org_id, citations, target_doc_id)

            if target_doc_id:
                try:
                    doc_name = Document.objects.get(id=target_doc_id).doc_name
                    context_label = f"Specific Document: '{doc_name}'"
                except Document.DoesNotExist:
                    context_label = "Specific Document"
            else:
                context_label = "Personal Documents" if doc_scope == 'PERSONAL' else "Organization Documents"
            
            current_date = datetime.now().strftime("%Y-%m-%d")

            # Create Agent
            agent = create_agent(
                model=self.llm_model,
                tools=tools,
                system_prompt=get_system_prompt(context_label, current_date),
                middleware=[
                    LoggingMiddleware(),
                    SummarizationMiddleware(
                        model=self.llm_model,
                        trigger=("tokens", 1200),  # summarize early
                    ),
                ], 
            )

            # Prepare Input & History 
            chat_history = self._get_chat_history_messages(user, org_id=org_id)

            # Construct the input messages list
            messages = chat_history + [{"role": "user", "content": question_text}]

            # Execute Agent with timeout guard
            timeout_seconds = getattr(settings, "QNA_AGENT_TIMEOUT", 60)
            
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(agent.invoke, {"messages": messages})
                    result = future.result(timeout=timeout_seconds)

                # Extract the final text response from the last message in the list
                final_answer = result["messages"][-1].content

            except FuturesTimeoutError:
                logger.error(f"QnA Agent timed out after {timeout_seconds}s for user {user.id}")
                final_answer = "Error: The AI service took too long to respond. Please try again later."

            # Save & Return
            return self._save_qna(user, question_text, final_answer, citations, org_id)

        except Exception as e:
            logger.error(f"QnA Service Error: {e}", exc_info=True)
            return None

    def _get_chat_history_messages(self, user, org_id=None):
        """
        Fetches the last 3 turns of conversation formatted for create_agent.
        Returns: List[Dict]
        """
        # personal and organization contexts.
        qs = QnA.objects.filter(user=user)
        if org_id is None:
            qs = qs.filter(org__isnull=True)
        else:
            qs = qs.filter(org_id=org_id)

        last_interactions = qs.order_by('-created_at')[:3]
        
        history = []
        # Reverse to get chronological order (Oldest -> Newest)
        for qna in reversed(last_interactions):
            history.append({"role": "user", "content": qna.question})
            history.append({"role": "assistant", "content": qna.answer})
            
        return history

    def _save_qna(self, user, question, answer, citations, org_id):
        """
        Saves the interaction to the database.
        """
        return QnA.objects.create(
            user=user,
            question=question,
            answer=answer,
            doc_ref=citations, 
            org_id=org_id
        )