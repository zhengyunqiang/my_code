"""
RAG (Retrieval-Augmented Generation) service for context injection.
Provides intelligent retrieval of project documents, historical data, and domain knowledge.
"""
import math
from typing import Any, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import Project, ProjectDocument
from app.services.llm_service import llm_service

logger = get_logger(__name__)


class VectorStore:
    """In-memory vector store for semantic search."""

    def __init__(self):
        self.documents: dict[str, dict[str, Any]] = {}
        self.embeddings_index: dict[int, list[float]] = {}

    async def add_document(
        self,
        doc_id: int,
        text: str,
        metadata: dict[str, Any],
        embedding: Optional[list[float]] = None,
    ) -> None:
        """Add a document to the vector store."""
        if embedding is None:
            embedding = await llm_service.embed(text)

        self.documents[str(doc_id)] = {
            "id": doc_id,
            "text": text,
            "metadata": metadata,
            "embedding": embedding,
        }
        self.embeddings_index[doc_id] = embedding

    def cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        score_threshold: float = 0.7,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Optional metadata filters

        Returns:
            List of matching documents with scores
        """
        results = []

        for doc_id, doc_embedding in self.embeddings_index.items():
            # Apply filters if provided
            if filters:
                doc = self.documents[str(doc_id)]
                match = True
                for key, value in filters.items():
                    if doc["metadata"].get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            # Calculate similarity
            score = self.cosine_similarity(query_embedding, doc_embedding)

            if score >= score_threshold:
                results.append({
                    "document": self.documents[str(doc_id)],
                    "score": score,
                })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:top_k]


class RAGService:
    """Service for retrieval-augmented generation."""

    def __init__(self):
        self.vector_store = VectorStore()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize RAG service with existing documents."""
        if self._initialized:
            return

        logger.info("Initializing RAG service...")

        async with get_db_context() as session:
            # Load all processed project documents
            result = await session.execute(
                select(ProjectDocument).where(
                    ProjectDocument.is_processed == True,
                    ProjectDocument.embedding_vector.isnot(None),
                )
            )
            documents = result.scalars().all()

            for doc in documents:
                await self.vector_store.add_document(
                    doc_id=doc.id,
                    text=doc.content_text or "",
                    metadata={
                        "project_id": doc.project_id,
                        "title": doc.title,
                        "document_type": doc.document_type,
                        "file_path": doc.file_path,
                    },
                    embedding=doc.embedding_vector,
                )

            logger.info(f"Loaded {len(documents)} documents into RAG vector store")

        self._initialized = True

    async def add_project_document(
        self,
        project_id: int,
        title: str,
        document_type: str,
        content_text: str,
        file_path: str,
        metadata: Optional[dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> ProjectDocument:
        """
        Add a new document to the RAG knowledge base.

        Args:
            project_id: Associated project ID
            title: Document title
            document_type: Type of document
            content_text: Extracted text content
            file_path: Path to document file
            metadata: Additional metadata
            session: Optional database session

        Returns:
            Created ProjectDocument instance
        """
        # Generate embedding
        embedding = await llm_service.embed(content_text)

        # Create document record
        document = ProjectDocument(
            project_id=project_id,
            title=title,
            document_type=document_type,
            content_text=content_text,
            file_path=file_path,
            embedding_vector=embedding,
            metadata=metadata or {},
            is_processed=True,
        )

        # Add to vector store
        await self.vector_store.add_document(
            doc_id=document.id,
            text=content_text,
            metadata={
                "project_id": project_id,
                "title": title,
                "document_type": document_type,
                **(metadata or {}),
            },
            embedding=embedding,
        )

        # Save to database
        if session:
            session.add(document)
            await session.commit()
            await session.refresh(document)

        logger.info(f"Added document to RAG: {title}")
        return document

    async def retrieve_context(
        self,
        query: str,
        project_id: Optional[int] = None,
        document_types: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant context for a query.

        Args:
            query: Search query
            project_id: Optional project filter
            document_types: Optional document type filters
            top_k: Number of results to return

        Returns:
            List of relevant documents with context
        """
        if not self._initialized:
            await self.initialize()

        # Generate query embedding
        query_embedding = await llm_service.embed(query)

        # Build filters
        filters = {}
        if project_id:
            filters["project_id"] = project_id
        if document_types:
            filters["document_type"] = document_types

        # Search vector store
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters if filters else None,
        )

        logger.info(f"Retrieved {len(results)} context documents for query: {query[:50]}...")
        return results

    async def retrieve_project_context(
        self,
        project_code: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Retrieve full context for a project.

        Args:
            project_code: Project code
            session: Database session

        Returns:
            Project context dictionary
        """
        # Get project
        result = await session.execute(
            select(Project).where(Project.code == project_code)
        )
        project = result.scalar_one_or_none()

        if not project:
            logger.warning(f"Project not found: {project_code}")
            return {}

        # Get project documents
        doc_result = await session.execute(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project.id,
                ProjectDocument.is_processed == True,
            )
        )
        documents = doc_result.scalars().all()

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "code": project.code,
                "description": project.description,
                "tech_stack": project.tech_stack,
                "business_domain": project.business_domain,
                "team_size": project.team_size,
                "complexity_level": project.complexity_level,
                "key_challenges": project.key_challenges,
            },
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "type": doc.document_type,
                    "content": doc.content_text[:500] if doc.content_text else "",
                }
                for doc in documents
            ],
        }

    async def enhance_requirement_with_context(
        self,
        raw_requirement: str,
        project_code: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Enhance a raw requirement with relevant context from RAG.

        Args:
            raw_requirement: Original requirement text
            project_code: Optional project code for context
            session: Optional database session

        Returns:
            Enhanced requirement with context
        """
        context = {
            "original_requirement": raw_requirement,
            "project_context": None,
            "similar_requirements": [],
            "tech_stack_suggestions": [],
        }

        # If project code provided, get project context
        if project_code and session:
            try:
                project_context = await self.retrieve_project_context(
                    project_code, session
                )
                context["project_context"] = project_context

                # Extract tech stack for suggestions
                if project_context.get("project", {}).get("tech_stack"):
                    tech_stack = project_context["project"]["tech_stack"]
                    context["tech_stack_suggestions"] = [
                        tech
                        for category in tech_stack.values()
                        for tech in category
                        if isinstance(category, list)
                    ] if isinstance(tech_stack, dict) else list(tech_stack)

            except Exception as e:
                logger.error(f"Error retrieving project context: {e}")

        # Retrieve similar requirements/documents
        try:
            similar_docs = await self.retrieve_context(
                query=raw_requirement,
                top_k=3,
            )
            context["similar_requirements"] = [
                {
                    "title": doc["document"]["metadata"].get("title", "Unknown"),
                    "type": doc["document"]["metadata"].get("document_type", "Unknown"),
                    "relevance": doc["score"],
                    "snippet": doc["document"]["text"][:300],
                }
                for doc in similar_docs
            ]
        except Exception as e:
            logger.error(f"Error retrieving similar requirements: {e}")

        return context

    async def generate_requirement_summary(
        self,
        raw_requirement: str,
        context: dict[str, Any],
    ) -> str:
        """
        Generate a comprehensive requirement summary using LLM with RAG context.

        Args:
            raw_requirement: Original requirement
            context: Retrieved context

        Returns:
            Enhanced requirement summary
        """
        # Build context prompt
        context_parts = []

        if context.get("project_context"):
            project = context["project_context"].get("project", {})
            context_parts.append(f"""
Project Context:
- Project: {project.get('name', 'Unknown')}
- Domain: {project.get('business_domain', 'Unknown')}
- Tech Stack: {project.get('tech_stack', {})}
- Description: {project.get('description', 'No description available')}
            """.strip())

        if context.get("similar_requirements"):
            context_parts.append("\nSimilar Past Requirements:")
            for req in context["similar_requirements"]:
                context_parts.append(f"- {req['title']}: {req['snippet']}")

        context_str = "\n\n".join(context_parts) if context_parts else "No additional context available."

        # Generate summary using LLM
        prompt = f"""
Based on the following information, generate a comprehensive requirement summary:

Original Requirement:
{raw_requirement}

Context from Similar Projects:
{context_str}

Please provide:
1. A clear, structured requirement summary
2. Key technical requirements inferred
3. Potential skill requirements
4. Any ambiguities that need clarification
"""

        summary = await llm_service.generate(
            prompt=prompt,
            system_prompt="You are an expert technical recruiter and requirement analyst. Extract and structure requirements clearly.",
        )

        return summary


# Global RAG service instance
rag_service = RAGService()


# Import at end to avoid circular dependency
from sqlalchemy import select
