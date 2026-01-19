"""
JD (Job Description) Generation Service - Phase 1 Core Module.
Handles requirement analysis, clarification, and JD generation using LangGraph orchestration.
"""
import json
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import (
    Client,
    EducationLevel,
    EmploymentType,
    JobPosting,
    Project,
    User,
    WorkExperience,
)
from app.models.schemas import (
    JDRequestCreate,
    JDRequestResponse,
    JobPostingCreate,
)
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service

logger = get_logger(__name__)


class JDRequestStatus(str, Enum):
    """Status of JD generation request."""
    INITIATED = "initiated"
    ANALYZING = "analyzing"
    CLARIFYING = "clarifying"  # Waiting for user answers
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ClarificationQuestion(BaseModel):
    """Clarification question for user."""

    question_id: str
    question: str
    question_type: str  # choice, text, boolean, range
    options: Optional[list[str]] = None
    is_required: bool = True
    priority: str = "high"  # high, medium, low
    context: Optional[str] = None


class JDGenerationRequest:
    """JD generation request state."""

    def __init__(
        self,
        client_id: int,
        raw_requirement: str,
        created_by: int,
        project_id: Optional[int] = None,
        input_files: Optional[list[str]] = None,
        additional_context: Optional[dict[str, Any]] = None,
    ):
        self.request_id = str(uuid.uuid4())
        self.status = JDRequestStatus.INITIATED
        self.client_id = client_id
        self.raw_requirement = raw_requirement
        self.created_by = created_by
        self.project_id = project_id
        self.input_files = input_files or []
        self.additional_context = additional_context or {}

        self.clarification_questions: list[ClarificationQuestion] = []
        self.user_answers: dict[str, str] = {}
        self.enhanced_requirement: Optional[str] = None
        self.generated_jd_id: Optional[int] = None

        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        # Analysis results
        self.requirement_analysis: Optional[dict[str, Any]] = None
        self.rag_context: Optional[dict[str, Any]] = None


class JDGenerationService:
    """Service for generating JDs with LangGraph orchestration."""

    def __init__(self):
        self.active_requests: dict[str, JDGenerationRequest] = {}

    async def create_request(
        self,
        request_data: JDRequestCreate,
    ) -> JDRequestResponse:
        """
        Create a new JD generation request.

        Args:
            request_data: Request creation data

        Returns:
            Response with request ID and initial status
        """
        request = JDGenerationRequest(
            client_id=request_data.client_id,
            raw_requirement=request_data.raw_requirement,
            created_by=request_data.created_by,
            project_id=request_data.project_id,
            input_files=request_data.input_files,
            additional_context=request_data.additional_context,
        )

        self.active_requests[request.request_id] = request

        logger.info(f"Created JD generation request: {request.request_id}")

        return JDRequestResponse(
            request_id=request.request_id,
            status=request.status.value,
            created_at=request.created_at,
        )

    async def analyze_requirement(
        self,
        request_id: str,
    ) -> dict[str, Any]:
        """
        Analyze raw requirement and identify clarification needs.

        Args:
            request_id: Request ID

        Returns:
            Analysis results with clarification questions
        """
        request = self.active_requests.get(request_id)
        if not request:
            raise ValueError(f"Request not found: {request_id}")

        request.status = JDRequestStatus.ANALYZING
        request.updated_at = datetime.utcnow()

        try:
            # Get RAG context if project specified
            rag_context = {}
            if request.project_id:
                async with get_db_context() as session:
                    # Get project
                    project_result = await session.execute(
                        select(Project).where(Project.id == request.project_id)
                    )
                    project = project_result.scalar_one_or_none()

                    if project:
                        rag_context = await rag_service.enhance_requirement_with_context(
                            raw_requirement=request.raw_requirement,
                            project_code=project.code,
                            session=session,
                        )

            request.rag_context = rag_context

            # Analyze requirement with LLM
            analysis = await self._llm_analyze_requirement(request, rag_context)
            request.requirement_analysis = analysis

            # Generate clarification questions based on analysis
            questions = await self._generate_clarification_questions(analysis)
            request.clarification_questions = questions

            request.status = JDRequestStatus.CLARIFYING
            request.updated_at = datetime.utcnow()

            logger.info(f"Completed requirement analysis for request: {request_id}")

            return {
                "request_id": request_id,
                "analysis": analysis,
                "clarification_questions": [
                    q.model_dump() for q in questions
                ],
                "rag_context": {
                    "project_found": bool(rag_context.get("project_context")),
                    "similar_requirements_count": len(
                        rag_context.get("similar_requirements", [])
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Error analyzing requirement for request {request_id}: {e}")
            request.status = JDRequestStatus.FAILED
            raise

    async def _llm_analyze_requirement(
        self,
        request: JDGenerationRequest,
        rag_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Use LLM to analyze the requirement."""

        # Build analysis prompt
        system_prompt = """You are an expert technical recruiter and requirement analyst.
Analyze job requirements and identify missing or ambiguous information."""

        # Build context from RAG
        context_parts = [f"Original Requirement:\n{request.raw_requirement}"]

        if rag_context.get("project_context"):
            project = rag_context["project_context"]["project"]
            context_parts.append(f"""
Project Context:
- Name: {project['name']}
- Domain: {project['business_domain']}
- Tech Stack: {json.dumps(project['tech_stack'], ensure_ascii=False)}
- Complexity: {project['complexity_level']}
            """.strip())

        if rag_context.get("similar_requirements"):
            context_parts.append("\nSimilar Past Requirements:")
            for req in rag_context["similar_requirements"][:2]:
                context_parts.append(f"- {req['title']}: {req['snippet']}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Analyze the following job requirement and provide a structured analysis:

{context_str}

Please provide analysis in the following JSON format:
{{
    "role_identified": "clear/partially_clear/unclear",
    "suggested_title": "Job title suggestion",
    "key_requirements": ["req1", "req2", ...],
    "identified_skills": ["skill1", "skill2", ...],
    "missing_critical_info": [
        {{
            "category": "employment_type|experience|education|salary|location|other",
            "importance": "critical|important|nice_to_have",
            "description": "What's missing and why it matters"
        }}
    ],
    "ambiguities": [
        {{
            "aspect": "Which aspect is ambiguous",
            "clarification_needed": "What needs to be clarified"
        }}
    ],
    "suggested_questions": [
        {{
            "question": "Question to ask",
            "options": ["option1", "option2"],
            "type": "choice|text|boolean",
            "priority": "high|medium|low"
        }}
    ],
    "tech_stack_inference": {{
        "languages": ["Java", "Python"],
        "frameworks": ["Spring", "React"],
        "tools": ["Git", "Jira"],
        "confidence": "high|medium|low"
    }}
}}"""

        analysis_json = await llm_service.generate_structured(
            prompt=prompt,
            system_prompt=system_prompt,
            schema={
                "type": "object",
                "properties": {
                    "role_identified": {"type": "string"},
                    "suggested_title": {"type": "string"},
                    "key_requirements": {"type": "array", "items": {"type": "string"}},
                    "identified_skills": {"type": "array", "items": {"type": "string"}},
                    "missing_critical_info": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {"type": "string"},
                                "importance": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "ambiguities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "aspect": {"type": "string"},
                                "clarification_needed": {"type": "string"},
                            },
                        },
                    },
                    "suggested_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "string"}},
                                "type": {"type": "string"},
                                "priority": {"type": "string"},
                            },
                        },
                    },
                    "tech_stack_inference": {
                        "type": "object",
                        "properties": {
                            "languages": {"type": "array", "items": {"type": "string"}},
                            "frameworks": {"type": "array", "items": {"type": "string"}},
                            "tools": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "string"},
                        },
                    },
                },
            },
        )

        return analysis_json

    async def _generate_clarification_questions(
        self,
        analysis: dict[str, Any],
    ) -> list[ClarificationQuestion]:
        """Generate structured clarification questions from analysis."""

        questions = []

        # Process missing critical info
        missing_info = analysis.get("missing_critical_info", [])
        for idx, item in enumerate(missing_info):
            question_id = f"missing_{idx}"

            if item["category"] == "employment_type":
                question = ClarificationQuestion(
                    question_id=question_id,
                    question=f"请明确招聘类型：全职、兼职、外包还是实习生？",
                    question_type="choice",
                    options=["全职", "外包", "兼职", "实习生"],
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                    context=f"招聘类型影响候选人筛选标准和薪资范围",
                )
            elif item["category"] == "experience":
                question = ClarificationQuestion(
                    question_id=question_id,
                    question=f"请明确工作经验要求：应届、1-3年、3-5年、5-10年还是10年以上？",
                    question_type="choice",
                    options=["应届/1年以下", "1-3年", "3-5年", "5-10年", "10年以上"],
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                    context="工作经验直接影响技术深度要求和薪资范围",
                )
            elif item["category"] == "education":
                question = ClarificationQuestion(
                    question_id=question_id,
                    question="请明确学历要求：高中、大专、本科、硕士还是博士？",
                    question_type="choice",
                    options=["高中", "大专", "本科", "硕士", "博士"],
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                    context="学历要求影响候选人池大小和质量",
                )
            elif item["category"] == "salary":
                question = ClarificationQuestion(
                    question_id=question_id,
                    question='请提供薪资范围（月薪）或选择"薪资面议"',
                    question_type="choice",
                    options=["薪资面议", "5-10K", "10-15K", "15-20K", "20-30K", "30K+"],
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                    context="明确的薪资范围可以提高招聘效率和匹配度",
                )
            elif item["category"] == "location":
                question = ClarificationQuestion(
                    question_id=question_id,
                    question="请提供工作地点，是否支持远程办公？",
                    question_type="text",
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                    context="工作地点是候选人考虑的重要因素",
                )
            else:
                # Generic question
                question = ClarificationQuestion(
                    question_id=question_id,
                    question=item["description"],
                    question_type="text",
                    is_required=item["importance"] == "critical",
                    priority=item["importance"],
                )

            questions.append(question)

        # Process ambiguities
        ambiguities = analysis.get("ambiguities", [])
        for idx, item in enumerate(ambiguities):
            question_id = f"ambiguity_{idx}"
            question = ClarificationQuestion(
                question_id=question_id,
                question=f"关于'{item['aspect']}'，{item['clarification_needed']}",
                question_type="text",
                is_required=False,
                priority="medium",
            )
            questions.append(question)

        # Add suggested questions from LLM
        suggested = analysis.get("suggested_questions", [])
        for idx, item in enumerate(suggested):
            question_id = f"suggested_{idx}"
            question = ClarificationQuestion(
                question_id=question_id,
                question=item["question"],
                question_type=item.get("type", "text"),
                options=item.get("options"),
                is_required=False,
                priority=item.get("priority", "medium"),
            )
            questions.append(question)

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        questions.sort(key=lambda q: priority_order.get(q.priority, 3))

        return questions

    async def submit_clarification_answers(
        self,
        request_id: str,
        answers: dict[str, str],
    ) -> JDRequestResponse:
        """
        Submit answers to clarification questions.

        Args:
            request_id: Request ID
            answers: Dictionary of question_id to answer

        Returns:
            Updated request response
        """
        request = self.active_requests.get(request_id)
        if not request:
            raise ValueError(f"Request not found: {request_id}")

        if request.status != JDRequestStatus.CLARIFYING:
            raise ValueError(f"Request not in clarifying state: {request.status}")

        request.user_answers.update(answers)
        request.updated_at = datetime.utcnow()

        # Check if all required questions are answered
        required_answered = all(
            q.question_id in answers
            for q in request.clarification_questions
            if q.is_required
        )

        if required_answered:
            # Move to generation phase
            request.status = JDRequestStatus.GENERATING
            logger.info(f"All required questions answered for request: {request_id}")
        else:
            logger.info(f"Partial answers received for request: {request_id}")

        return JDRequestResponse(
            request_id=request.request_id,
            status=request.status.value,
            clarification_questions=[q.model_dump() for q in request.clarification_questions],
            user_answers=request.user_answers,
            created_at=request.created_at,
        )

    async def generate_jd(
        self,
        request_id: str,
    ) -> JobPosting:
        """
        Generate final JD based on requirement and clarifications.

        Args:
            request_id: Request ID

        Returns:
            Generated JobPosting instance
        """
        request = self.active_requests.get(request_id)
        if not request:
            raise ValueError(f"Request not found: {request_id}")

        request.status = JDRequestStatus.GENERATING
        request.updated_at = datetime.utcnow()

        try:
            # Build enhanced requirement
            enhanced_requirement = await self._build_enhanced_requirement(request)
            request.enhanced_requirement = enhanced_requirement

            # Generate JD content
            jd_content = await self._generate_jd_content(request)

            # Create JobPosting record
            async with get_db_context() as session:
                # Get client
                client_result = await session.execute(
                    select(Client).where(Client.id == request.client_id)
                )
                client = client_result.scalar_one()

                # Generate job code
                job_code = await self._generate_job_code(session, client.company_code)

                # Map values to enums
                employment_type = self._map_employment_type(jd_content.get("employment_type", "全职"))
                work_experience = self._map_work_experience(jd_content.get("work_experience", "3-5年"))
                education_level = self._map_education_level(jd_content.get("education_level", "本科"))

                job_posting = JobPosting(
                    job_title=jd_content["job_title"],
                    job_code=job_code,
                    client_id=request.client_id,
                    created_by=request.created_by,
                    project_id=request.project_id,

                    # Enum fields
                    employment_type=employment_type,
                    work_experience=work_experience,
                    education_level=education_level,

                    # Job details
                    work_location=jd_content.get("work_location", "待定"),
                    salary_min=jd_content.get("salary_min"),
                    salary_max=jd_content.get("salary_max"),
                    is_salary_negotiable=jd_content.get("is_salary_negotiable", True),

                    # JD content
                    responsibilities=jd_content["responsibilities"],
                    requirements=jd_content["requirements"],
                    preferred_qualifications=jd_content.get("preferred_qualifications", []),
                    benefits=jd_content.get("benefits", []),

                    # AI fields
                    keywords=jd_content["keywords"],
                    skills_required=jd_content["skills_required"],
                    summary=jd_content["summary"],
                    full_jd_text=jd_content["full_jd_text"],

                    # Metadata
                    source="ai_generated",
                    priority=request.additional_context.get("priority", "normal"),
                    remote_work=jd_content.get("remote_work", False),
                    travel_required=jd_content.get("travel_required", False),
                    overtime_expected=jd_content.get("overtime_expected", False),
                )

                session.add(job_posting)
                await session.commit()
                await session.refresh(job_posting)

                request.generated_jd_id = job_posting.id
                request.status = JDRequestStatus.COMPLETED
                request.updated_at = datetime.utcnow()

                logger.info(f"Generated JD {job_posting.id} for request: {request_id}")

                return job_posting

        except Exception as e:
            logger.error(f"Error generating JD for request {request_id}: {e}")
            request.status = JDRequestStatus.FAILED
            raise

    async def _build_enhanced_requirement(
        self,
        request: JDGenerationRequest,
    ) -> str:
        """Build enhanced requirement with clarifications."""

        enhanced_parts = [f"原始需求:\n{request.raw_requirement}"]

        if request.user_answers:
            enhanced_parts.append("\n澄清信息:")
            for q_id, answer in request.user_answers.items():
                question = next(
                    (q for q in request.clarification_questions if q.question_id == q_id),
                    None,
                )
                if question:
                    enhanced_parts.append(f"- {question.question}: {answer}")

        if request.rag_context:
            if request.rag_context.get("project_context"):
                project = request.rag_context["project_context"]["project"]
                enhanced_parts.append(f"""
项目上下文:
- 项目名称: {project['name']}
- 业务领域: {project['business_domain']}
- 技术栈: {json.dumps(project['tech_stack'], ensure_ascii=False)}
- 复杂度: {project['complexity_level']}
                """.strip())

        return "\n\n".join(enhanced_parts)

    async def _generate_jd_content(
        self,
        request: JDGenerationRequest,
    ) -> dict[str, Any]:
        """Generate JD content using LLM."""

        system_prompt = """You are an expert technical recruiter and JD writer.
Create professional, comprehensive job descriptions that attract qualified candidates."""

        prompt = f"""Based on the following requirement information, generate a comprehensive job description.

{request.enhanced_requirement}

Please provide the JD in the following JSON format:
{{
    "job_title": "Professional job title",
    "employment_type": "全职|外包|兼职|实习生",
    "work_experience": "应届/1年以下|1-3年|3-5年|5-10年|10年以上",
    "education_level": "高中|大专|本科|硕士|博士",
    "work_location": "Work location",
    "salary_min": 10000,
    "salary_max": 15000,
    "is_salary_negotiable": true,
    "remote_work": false,
    "travel_required": false,
    "overtime_expected": false,
    "responsibilities": [
        "Clear, action-oriented responsibility 1",
        "Clear, action-oriented responsibility 2"
    ],
    "requirements": [
        "Specific requirement 1",
        "Specific requirement 2"
    ],
    "preferred_qualifications": [
        "Nice-to-have qualification 1",
        "Nice-to-have qualification 2"
    ],
    "benefits": [
        "Benefit 1",
        "Benefit 2"
    ],
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "skills_required": [
        {{"name": "Java", "level": "required", "years": 3}},
        {{"name": "Spring", "level": "required", "years": 2}}
    ],
    "summary": "2-3 sentence overview of the role",
    "full_jd_text": "Complete, formatted JD text ready for posting"
}}

Requirements:
- Job title should be professional and specific
- Responsibilities should be clear and action-oriented
- Requirements should be specific and measurable
- Include both technical and soft skills
- Salary range should be realistic for the role and location
- Summary should be compelling to qualified candidates
- Full JD text should be well-formatted and ready to post
"""

        jd_json = await llm_service.generate_structured(
            prompt=prompt,
            system_prompt=system_prompt,
            schema={
                "type": "object",
                "properties": {
                    "job_title": {"type": "string"},
                    "employment_type": {"type": "string"},
                    "work_experience": {"type": "string"},
                    "education_level": {"type": "string"},
                    "work_location": {"type": "string"},
                    "salary_min": {"type": "integer"},
                    "salary_max": {"type": "integer"},
                    "is_salary_negotiable": {"type": "boolean"},
                    "remote_work": {"type": "boolean"},
                    "travel_required": {"type": "boolean"},
                    "overtime_expected": {"type": "boolean"},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "preferred_qualifications": {"type": "array", "items": {"type": "string"}},
                    "benefits": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "skills_required": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "level": {"type": "string"},
                                "years": {"type": "number"},
                            },
                        },
                    },
                    "summary": {"type": "string"},
                    "full_jd_text": {"type": "string"},
                },
                "required": [
                    "job_title",
                    "responsibilities",
                    "requirements",
                    "keywords",
                    "skills_required",
                    "summary",
                    "full_jd_text",
                ],
            },
        )

        return jd_json

    def _map_employment_type(self, value: str) -> EmploymentType:
        """Map employment type string to enum."""
        mapping = {
            "全职": EmploymentType.FULL_TIME,
            "外包": EmploymentType.OUTSOURCING,
            "兼职": EmploymentType.PART_TIME,
            "实习生": EmploymentType.INTERN,
            "合同": EmploymentType.CONTRACT,
        }
        return mapping.get(value, EmploymentType.FULL_TIME)

    def _map_work_experience(self, value: str) -> WorkExperience:
        """Map work experience string to enum."""
        mapping = {
            "应届/1年以下": WorkExperience.ENTRY,
            "1-3年": WorkExperience.JUNIOR,
            "3-5年": WorkExperience.MIDDLE,
            "5-10年": WorkExperience.SENIOR,
            "10年以上": WorkExperience.EXPERT,
        }
        return mapping.get(value, WorkExperience.MIDDLE)

    def _map_education_level(self, value: str) -> EducationLevel:
        """Map education level string to enum."""
        mapping = {
            "高中": EducationLevel.HIGH_SCHOOL,
            "大专": EducationLevel.ASSOCIATE,
            "本科": EducationLevel.BACHELOR,
            "硕士": EducationLevel.MASTER,
            "博士": EducationLevel.PHD,
        }
        return mapping.get(value, EducationLevel.BACHELOR)

    async def _generate_job_code(
        self,
        session: AsyncSession,
        company_code: str,
    ) -> str:
        """Generate unique job code."""
        # Get today's date in YYMMDD format
        today = datetime.utcnow().strftime("%y%m%d")

        # Count existing jobs for today
        from sqlalchemy import func
        result = await session.execute(
            select(func.count(JobPosting.id))
            .where(JobPosting.job_code.like(f"JD-{company_code}-{today}%"))
        )
        count = result.scalar() or 0

        # Generate code: JD-{COMPANY}-{YYMMDD}-{SEQ}
        sequence = str(count + 1).zfill(3)
        return f"JD-{company_code}-{today}-{sequence}"

    def get_request(self, request_id: str) -> Optional[JDGenerationRequest]:
        """Get request by ID."""
        return self.active_requests.get(request_id)


# Global service instance
jd_generation_service = JDGenerationService()


# Import at end to avoid circular dependency
from pydantic import BaseModel
from sqlalchemy import select
