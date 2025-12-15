import logging
from django.tasks import task 
from ekna_ai.services import DocumentProcessor

logger = logging.getLogger(__name__)

@task(priority=10) 
def process_document_task(doc_id):
    logger.info(f"Task Started: Doc ID {doc_id}")
    try:
        processor = DocumentProcessor()
        processor.process_document(doc_id)
        logger.info(f"Task Finished: Doc ID {doc_id}")
    except Exception as e:
        logger.error(f"Task Failed for Doc ID {doc_id}: {str(e)}")
        raise e 