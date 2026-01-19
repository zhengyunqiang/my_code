"""
Resume Screening and Matching Service - Phase 2 Core Module.
Handles semantic matching, intelligent screening, and candidate ranking.
"""
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import (
    Candidate,
    CandidateStatus,
    EducationLevel,
    JobPosting,
)
from app.models.schemas import ResumeProcessingResult
from app.services.llm_service import llm_service

logger = get_logger(__name__)


class ResumeParser:
    """Parse and extract information from resume text."""

    # Patterns for extracting information
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'(?:(?:\+|00)86)?1[3-9]\d{9}',
        "wechat": r'(?:微信|WeChat|wechat)[:：\s]*([A-Za-z0-9_-]+)',
        "age": r'(?:年龄|age|Age)[:：\s]*(\d{2})',
        "experience_years": r'(?:工作经验|工作年限|经验)[:：\s]*(\d+(?:\.\d+)?)\s*[年years]*',
        "education_keywords": [
            r'博士',
            r'硕士',
            r'研究生',
            r'本科',
            r'大专',
            r'专科',
            r'高中',
            r'PhD',
            r'Master',
            r'Bachelor',
        ],
    }

    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """Extract email from text."""
        matches = re.findall(ResumeParser.PATTERNS["email"], text)
        return matches[0] if matches else None

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """Extract phone number from text."""
        matches = re.findall(ResumeParser.PATTERNS["phone"], text)
        return matches[0] if matches else None

    @staticmethod
    def extract_age(text: str) -> Optional[int]:
        """Extract age from text."""
        match = re.search(ResumeParser.PATTERNS["age"], text)
        return int(match.group(1)) if match else None

    @staticmethod
    def extract_experience_years(text: str) -> Optional[float]:
        """Extract years of experience from text."""
        match = re.search(ResumeParser.PATTERNS["experience_years"], text)
        return float(match.group(1)) if match else None

    @staticmethod
    def extract_education_level(text: str) -> Optional[EducationLevel]:
        """Extract education level from text."""
        text_lower = text.lower()

        if any(keyword in text for keyword in ["博士", "PhD"]):
            return EducationLevel.PHD
        elif any(keyword in text for keyword in ["硕士", "研究生", "Master"]):
            return EducationLevel.MASTER
        elif any(keyword in text for keyword in ["本科", "Bachelor"]):
            return EducationLevel.BACHELOR
        elif any(keyword in text for keyword in ["大专", "专科"]):
            return EducationLevel.ASSOCIATE
        elif any(keyword in text for keyword in ["高中"]):
            return EducationLevel.HIGH_SCHOOL

        return None

    @staticmethod
    def extract_skills(text: str) -> list[str]:
        """Extract skills from resume text using keyword matching."""
        # Common tech skills dictionary
        TECH_SKILLS = {
            "programming": [
                "Java", "Python", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust",
                "PHP", "Ruby", "Swift", "Kotlin", "Scala", "R", "MATLAB", "Shell"
            ],
            "frameworks": [
                "Spring", "Spring Boot", "Spring Cloud", "Django", "Flask", "FastAPI",
                "Express", "React", "Vue", "Angular", "Next.js", "Nuxt.js",
                "MyBatis", "Hibernate", "Entity Framework", "Laravel"
            ],
            "databases": [
                "MySQL", "PostgreSQL", "Oracle", "SQL Server", "MongoDB", "Redis",
                "Elasticsearch", "Cassandra", "DynamoDB", "Neo4j"
            ],
            "tools": [
                "Git", "Docker", "Kubernetes", "Jenkins", "Jira", "Confluence",
                "Maven", "Gradle", "npm", "yarn", "Webpack", "Linux", "Nginx"
            ],
            "concepts": [
                "微服务", "Microservices", "分布式", "Distributed", "高并发", "High Concurrency",
                "RESTful", "GraphQL", "RPC", "消息队列", "Message Queue", "缓存",
                "Cache", "负载均衡", "Load Balancing", "容器化", "Containerization"
            ]
        }

        found_skills = set()
        text_lower = text.lower()

        for category, skills in TECH_SKILLS.items():
            for skill in skills:
                if skill.lower() in text_lower or skill in text:
                    found_skills.add(skill)

        return sorted(list(found_skills))

    @staticmethod
    def extract_work_history(text: str) -> list[dict[str, Any]]:
        """Extract work history from resume text."""
        work_history = []

        # Pattern for company and position sections
        # This is a simplified version - production would use more sophisticated NLP
        section_pattern = r'(?:工作经验|工作经历|项目经历|Work Experience|Project Experience)[\s\S]+?(?=\n\s*\n|教育|Education|$)'

        match = re.search(section_pattern, text, re.IGNORECASE)
        if match:
            section_text = match.group(0)

            # Try to extract individual entries
            entry_pattern = r'(.+?)(?:公司|有限公司|集团|Co\.|Ltd\.|Inc\.)[\s\S]+?(?=\n|$)'
            entries = re.findall(entry_pattern, section_text)

            for entry in entries:
                work_history.append({
                    "company": entry.strip()[:100],
                    "position": "Unknown",
                    "duration": "Unknown",
                })

        return work_history


class SemanticMatcher:
    """Calculate semantic similarity between JD and resume."""

    def __init__(self):
        self.weight_config = {
            "keyword_match": 0.3,
            "semantic_similarity": 0.4,
            "experience_match": 0.2,
            "education_match": 0.1,
        }

    async def calculate_similarity(
        self,
        jd_text: str,
        resume_text: str,
        jd_skills: list[str],
        resume_skills: list[str],
    ) -> dict[str, float]:
        """
        Calculate comprehensive similarity scores.

        Args:
            jd_text: Job description text
            resume_text: Resume text
            jd_skills: Skills from JD
            resume_skills: Skills from resume

        Returns:
            Dictionary with different similarity scores
        """
        # Keyword matching score
        keyword_score = self._calculate_keyword_score(jd_skills, resume_skills)

        # Semantic similarity using embeddings
        semantic_score = await self._calculate_semantic_similarity(jd_text, resume_text)

        # Combined scores
        overall_score = (
            keyword_score * self.weight_config["keyword_match"] +
            semantic_score * self.weight_config["semantic_similarity"]
        )

        return {
            "keyword_score": keyword_score,
            "semantic_score": semantic_score,
            "overall_score": overall_score,
        }

    def _calculate_keyword_score(
        self,
        jd_skills: list[str],
        resume_skills: list[str],
    ) -> float:
        """Calculate keyword matching score."""
        if not jd_skills:
            return 0.0

        jd_skills_lower = [skill.lower() for skill in jd_skills]
        resume_skills_lower = [skill.lower() for skill in resume_skills]

        matches = sum(1 for skill in jd_skills_lower if skill in resume_skills_lower)
        return matches / len(jd_skills_lower)

    async def _calculate_semantic_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """Calculate semantic similarity using embeddings."""
        try:
            # Generate embeddings for both texts
            embedding1 = await llm_service.embed(text1[:2000])  # Limit length
            embedding2 = await llm_service.embed(text2[:2000])

            # Calculate cosine similarity
            return self._cosine_similarity(embedding1, embedding2)
        except Exception as e:
            logger.error(f"Error calculating semantic similarity: {e}")
            return 0.0

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)


class ResumeScreeningService:
    """Service for resume screening and intelligent matching."""

    def __init__(self):
        self.parser = ResumeParser()
        self.matcher = SemanticMatcher()

    async def process_resume(
        self,
        resume_text: str,
        job_posting_id: int,
        source: str = "upload",
        file_path: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> ResumeProcessingResult:
        """
        Process and screen a resume against a job posting.

        Args:
            resume_text: Extracted resume text
            job_posting_id: Target job posting ID
            source: Resume source
            file_path: Optional file path
            session: Optional database session

        Returns:
            Processing result with extracted data and scores
        """
        if not session:
            async with get_db_context() as session:
                return await self._process_resume(
                    resume_text, job_posting_id, source, file_path, session
                )

        return await self._process_resume(
            resume_text, job_posting_id, source, file_path, session
        )

    async def _process_resume(
        self,
        resume_text: str,
        job_posting_id: int,
        source: str,
        file_path: Optional[str],
        session: AsyncSession,
    ) -> ResumeProcessingResult:
        """Internal resume processing implementation."""

        # Get job posting
        job_posting = await session.get(JobPosting, job_posting_id)
        if not job_posting:
            raise ValueError(f"Job posting not found: {job_posting_id}")

        # Parse resume
        extracted_data = {
            "name": self._extract_name(resume_text),
            "email": self.parser.extract_email(resume_text),
            "phone": self.parser.extract_phone(resume_text),
            "age": self.parser.extract_age(resume_text),
            "education_level": self.parser.extract_education_level(resume_text),
            "years_of_experience": self.parser.extract_experience_years(resume_text),
            "skills": self.parser.extract_skills(resume_text),
            "work_history": self.parser.extract_work_history(resume_text),
        }

        # Calculate match scores
        scores = await self.matcher.calculate_similarity(
            jd_text=job_posting.full_jd_text,
            resume_text=resume_text,
            jd_skills=job_posting.skills_required,
            resume_skills=extracted_data["skills"],
        )

        # Determine status and recommendation
        status, recommended_action = self._determine_status(
            scores, extracted_data, job_posting
        )

        # Generate candidate code
        candidate_code = await self._generate_candidate_code(session)

        # Create candidate record
        candidate = Candidate(
            candidate_code=candidate_code,
            job_posting_id=job_posting_id,
            name=extracted_data["name"] or "Unknown",
            phone=extracted_data["email"],
            email=extracted_data["email"],
            age=extracted_data["age"],
            years_of_experience=extracted_data["years_of_experience"],
            education_level=extracted_data["education_level"],
            resume_file_path=file_path,
            resume_text=resume_text,
            resume_skills=extracted_data["skills"],
            resume_embedding=await llm_service.embed(resume_text[:2000]),
            semantic_score=scores["semantic_score"],
            keyword_score=scores["keyword_score"],
            overall_score=scores["overall_score"],
            status=status,
            source=source,
        )

        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)

        # Get ranking
        ranking = await self._get_candidate_ranking(session, job_posting_id, candidate.id)

        return ResumeProcessingResult(
            candidate_id=candidate.id,
            processing_status="completed",
            extracted_data=extracted_data,
            match_scores=scores,
            ranking_position=ranking,
            recommended_action=recommended_action,
        )

    def _extract_name(self, text: str) -> Optional[str]:
        """Extract candidate name from resume."""
        # Simple heuristic: first line often contains name
        lines = text.strip().split('\n')
        if lines:
            first_line = lines[0].strip()
            # Remove common non-name prefixes
            for prefix in ["简历", "个人简历", "RESUME", "CV", "个人简历"]:
                if first_line.startswith(prefix):
                    first_line = first_line[len(prefix):].strip()
            # Return first 1-3 characters as potential name
            if len(first_line) <= 10:
                return first_line
        return None

    def _determine_status(
        self,
        scores: dict[str, float],
        extracted_data: dict[str, Any],
        job_posting: JobPosting,
    ) -> tuple[CandidateStatus, str]:
        """Determine candidate status and recommended action."""

        overall_score = scores["overall_score"]

        # Score thresholds
        if overall_score >= 0.8:
            return CandidateStatus.CONTACTED, "high_match"
        elif overall_score >= 0.6:
            return CandidateStatus.SCREENING, "medium_match"
        elif overall_score >= 0.4:
            return CandidateStatus.NEW, "low_match"
        else:
            return CandidateStatus.REJECTED, "no_match"

    async def _generate_candidate_code(self, session: AsyncSession) -> str:
        """Generate unique candidate code."""
        from sqlalchemy import func

        # Get today's date in YYMMDD format
        today = datetime.utcnow().strftime("%y%m%d")

        # Count existing candidates for today
        result = await session.execute(
            select(func.count(Candidate.id))
            .where(Candidate.candidate_code.like(f"CAN-{today}%"))
        )
        count = result.scalar() or 0

        # Generate code: CAN-YYMMDD-SEQ
        sequence = str(count + 1).zfill(4)
        return f"CAN-{today}-{sequence}"

    async def _get_candidate_ranking(
        self,
        session: AsyncSession,
        job_posting_id: int,
        candidate_id: int,
    ) -> Optional[int]:
        """Get ranking position for candidate among job applicants."""
        from sqlalchemy import desc

        result = await session.execute(
            select(Candidate.id)
            .where(Candidate.job_posting_id == job_posting_id)
            .where(Candidate.overall_score.isnot(None))
            .order_by(desc(Candidate.overall_score))
        )
        ranked_ids = [row[0] for row in result.all()]

        try:
            return ranked_ids.index(candidate_id) + 1
        except ValueError:
            return None

    async def rank_candidates(
        self,
        job_posting_id: int,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> list[Candidate]:
        """
        Get ranked candidates for a job posting.

        Args:
            job_posting_id: Job posting ID
            limit: Maximum number of candidates to return
            session: Optional database session

        Returns:
            List of candidates ranked by match score
        """
        if not session:
            async with get_db_context() as session:
                return await self._rank_candidates(job_posting_id, limit, session)

        return await self._rank_candidates(job_posting_id, limit, session)

    async def _rank_candidates(
        self,
        session: AsyncSession,
        job_posting_id: int,
        limit: int,
    ) -> list[Candidate]:
        """Internal ranking implementation."""
        from sqlalchemy import desc

        result = await session.execute(
            select(Candidate)
            .where(
                and_(
                    Candidate.job_posting_id == job_posting_id,
                    Candidate.status != CandidateStatus.REJECTED,
                )
            )
            .order_by(desc(Candidate.overall_score))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def batch_screen_resumes(
        self,
        resume_data_list: list[dict[str, Any]],
        job_posting_id: int,
        session: AsyncSession,
    ) -> list[ResumeProcessingResult]:
        """
        Batch screen multiple resumes.

        Args:
            resume_data_list: List of resume data dictionaries
            job_posting_id: Target job posting ID
            session: Database session

        Returns:
            List of processing results
        """
        results = []

        for resume_data in resume_data_list:
            try:
                result = await self._process_resume(
                    resume_text=resume_data["text"],
                    job_posting_id=job_posting_id,
                    source=resume_data.get("source", "batch"),
                    file_path=resume_data.get("file_path"),
                    session=session,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing resume: {e}")
                results.append(
                    ResumeProcessingResult(
                        candidate_id=0,
                        processing_status="failed",
                        extracted_data={},
                        match_scores={},
                        recommended_action="error",
                    )
                )

        return results


# Global service instance
resume_screening_service = ResumeScreeningService()
