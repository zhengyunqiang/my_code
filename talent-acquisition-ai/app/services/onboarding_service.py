"""
Onboarding and Talent Pool Management Service - Phase 4 Core Module.
Handles onboarding workflows, talent profiling, and talent pool operations.
"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import (
    BackgroundCheck,
    Candidate,
    Onboarding,
    TalentProfile,
    EducationLevel,
)
from app.services.llm_service import llm_service

settings = get_settings()
logger = get_logger(__name__)


class OnboardingStatus(str, Enum):
    """Onboarding process status."""

    NOT_STARTED = "not_started"
    DOCUMENTATION = "documentation"
    BACKGROUND_CHECK = "background_check"
    MEDICAL_CHECK = "medical_check"
    IT_SETUP = "it_setup"
    ORIENTATION = "orientation"
    READY_TO_START = "ready_to_start"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OnboardingChecklistItem(str, Enum):
    """Onboarding checklist items."""

    CONTRACT_SIGNED = "contract_signed"
    BACKGROUND_CHECK = "background_check"
    MEDICAL_CHECK = "medical_check"
    IT_SETUP = "it_setup"
    EQUIPMENT_ASSIGNED = "equipment_assigned"
    EMAIL_CREATED = "email_created"
    ORIENTATION_COMPLETED = "orientation_completed"


class OnboardingService:
    """Service for managing onboarding processes."""

    def __init__(self):
        self.notification_templates = {
            "medical_check_reminder": """您好，{candidate_name}！

温馨提醒：您的体检报告需要在{deadline}前提交哦。

如有问题请及时联系HR。谢谢！""",

            "document_reminder": """{candidate_name}您好，

还有以下文档需要提交：
{missing_documents}

请尽快完成，以便我们为您办理入职手续。谢谢！""",

            "onboarding_progress": """
入职进度更新：

已完成步骤：{completed_steps}/{total_steps}

待完成事项：
{pending_items}

如有疑问请联系HR。""",
        }

    async def create_onboarding(
        self,
        candidate_id: int,
        job_posting_id: int,
        offer_accepted_date: datetime,
        expected_start_date: datetime,
        session: Optional[AsyncSession] = None,
    ) -> Onboarding:
        """
        Create onboarding record for hired candidate.

        Args:
            candidate_id: Candidate ID
            job_posting_id: Job posting ID
            offer_accepted_date: Date offer was accepted
            expected_start_date: Expected first day of work
            session: Optional database session

        Returns:
            Created Onboarding record
        """
        if not session:
            async with get_db_context() as session:
                return await self._create_onboarding(
                    candidate_id, job_posting_id, offer_accepted_date, expected_start_date, session
                )

        return await self._create_onboarding(
            candidate_id, job_posting_id, offer_accepted_date, expected_start_date, session
        )

    async def _create_onboarding(
        self,
        candidate_id: int,
        job_posting_id: int,
        offer_accepted_date: datetime,
        expected_start_date: datetime,
        session: AsyncSession,
    ) -> Onboarding:
        """Internal onboarding creation implementation."""

        onboarding = Onboarding(
            candidate_id=candidate_id,
            job_posting_id=job_posting_id,
            offer_accepted_date=offer_accepted_date,
            expected_start_date=expected_start_date,
            status="in_progress",
            progress_percentage=0,
            # Set deadlines
            medical_check_deadline=expected_start_date - timedelta(days=7),
            background_check_deadline=expected_start_date - timedelta(days=5),
        )

        session.add(onboarding)
        await session.commit()
        await session.refresh(onboarding)

        logger.info(f"Created onboarding for candidate {candidate_id}")

        # Initialize background check
        await self._initialize_background_check(candidate_id, session)

        return onboarding

    async def _initialize_background_check(
        self,
        candidate_id: int,
        session: AsyncSession,
    ) -> None:
        """Initialize background check record."""
        background_check = BackgroundCheck(
            candidate_id=candidate_id,
            status="pending",
            completion_percentage=0,
        )
        session.add(background_check)
        await session.commit()

    async def update_onboarding_progress(
        self,
        onboarding_id: int,
        checklist_item: OnboardingChecklistItem,
        completed: bool = True,
        file_path: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Onboarding:
        """
        Update onboarding progress.

        Args:
            onboarding_id: Onboarding record ID
            checklist_item: Checklist item to update
            completed: Whether item is completed
            file_path: Optional file path for uploaded document
            session: Optional database session

        Returns:
            Updated Onboarding record
        """
        if not session:
            async with get_db_context() as session:
                return await self._update_onboarding_progress(
                    onboarding_id, checklist_item, completed, file_path, session
                )

        return await self._update_onboarding_progress(
            onboarding_id, checklist_item, completed, file_path, session
        )

    async def _update_onboarding_progress(
        self,
        onboarding_id: int,
        checklist_item: OnboardingChecklistItem,
        completed: bool,
        file_path: Optional[str],
        session: AsyncSession,
    ) -> Onboarding:
        """Internal progress update implementation."""

        onboarding = await session.get(Onboarding, onboarding_id)
        if not onboarding:
            raise ValueError(f"Onboarding not found: {onboarding_id}")

        # Update specific field based on checklist item
        if checklist_item == OnboardingChecklistItem.CONTRACT_SIGNED:
            onboarding.contract_signed = completed
            if file_path:
                onboarding.contract_file_path = file_path

        elif checklist_item == OnboardingChecklistItem.BACKGROUND_CHECK:
            onboarding.background_check = completed

            # Also update background check record
            bg_check_result = await session.execute(
                select(BackgroundCheck).where(BackgroundCheck.candidate_id == onboarding.candidate_id)
            )
            bg_check = bg_check_result.scalar_one_or_none()
            if bg_check:
                bg_check.status = "completed" if completed else "in_progress"
                bg_check.completion_percentage = 100 if completed else 50

        elif checklist_item == OnboardingChecklistItem.MEDICAL_CHECK:
            onboarding.medical_check = completed
            if file_path:
                onboarding.medical_report_file_path = file_path

        elif checklist_item == OnboardingChecklistItem.IT_SETUP:
            onboarding.it_setup = completed

        elif checklist_item == OnboardingChecklistItem.EQUIPMENT_ASSIGNED:
            onboarding.equipment_assigned = completed

        elif checklist_item == OnboardingChecklistItem.EMAIL_CREATED:
            onboarding.email_created = completed

        elif checklist_item == OnboardingChecklistItem.ORIENTATION_COMPLETED:
            onboarding.orientation_completed = completed
            if completed:
                onboarding.orientation_date = datetime.utcnow()

        # Recalculate progress percentage
        total_items = 7
        completed_items = sum([
            onboarding.contract_signed,
            onboarding.background_check,
            onboarding.medical_check,
            onboarding.it_setup,
            onboarding.equipment_assigned,
            onboarding.email_created,
            onboarding.orientation_completed,
        ])
        onboarding.progress_percentage = int((completed_items / total_items) * 100)

        # Update status if all completed
        if onboarding.progress_percentage == 100:
            onboarding.status = "completed"
        elif onboarding.progress_percentage > 0:
            onboarding.status = "in_progress"

        await session.commit()
        await session.refresh(onboarding)

        logger.info(f"Updated onboarding {onboarding_id} progress to {onboarding.progress_percentage}%")

        return onboarding

    async def send_reminders(
        self,
        session: Optional[AsyncSession] = None,
    ) -> list[dict[str, Any]]:
        """
        Send reminders for pending onboarding tasks.

        Args:
            session: Optional database session

        Returns:
            List of sent reminders
        """
        if not session:
            async with get_db_context() as session:
                return await self._send_reminders(session)

        return await self._send_reminders(session)

    async def _send_reminders(self, session: AsyncSession) -> list[dict[str, Any]]:
        """Internal reminder sending implementation."""

        reminders_sent = []

        # Get pending onboardings with approaching deadlines
        tomorrow = datetime.utcnow() + timedelta(days=1)
        result = await session.execute(
            select(Onboarding).where(
                and_(
                    Onboarding.status == "in_progress",
                    or_(
                        Onboarding.medical_check_deadline < tomorrow,
                        Onboarding.background_check_deadline < tomorrow,
                    ),
                )
            )
        )
        pending_onboardings = result.scalars().all()

        for onboarding in pending_onboardings:
            # Get candidate info
            candidate = await session.get(Candidate, onboarding.candidate_id)

            # Check medical check
            if not onboarding.medical_check and onboarding.medical_check_deadline:
                days_until = (onboarding.medical_check_deadline - datetime.utcnow()).days
                if days_until <= 2:
                    message = self.notification_templates["medical_check_reminder"].format(
                        candidate_name=candidate.name if candidate else "候选人",
                        deadline=onboarding.medical_check_deadline.strftime("%Y-%m-%d"),
                    )
                    # Send notification (integrate with your notification system)
                    logger.info(f"Medical check reminder for candidate {onboarding.candidate_id}")
                    logger.debug(f"Message: {message}")
                    reminders_sent.append({
                        "onboarding_id": onboarding.id,
                        "type": "medical_check_reminder",
                        "candidate_id": onboarding.candidate_id,
                    })

        return reminders_sent

    async def get_onboarding_dashboard(
        self,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Get onboarding dashboard data.

        Args:
            session: Optional database session

        Returns:
            Dashboard data
        """
        if not session:
            async with get_db_context() as session:
                return await self._get_onboarding_dashboard(session)

        return await self._get_onboarding_dashboard(session)

    async def _get_onboarding_dashboard(self, session: AsyncSession) -> dict[str, Any]:
        """Internal dashboard data retrieval."""

        # Get statistics
        result = await session.execute(
            select(func.count(Onboarding.id))
        )
        total = result.scalar() or 0

        result = await session.execute(
            select(func.count(Onboarding.id)).where(Onboarding.status == "in_progress")
        )
        in_progress = result.scalar() or 0

        result = await session.execute(
            select(func.count(Onboarding.id)).where(Onboarding.status == "completed")
        )
        completed = result.scalar() or 0

        # Get average completion time
        result = await session.execute(
            select(func.avg(Onboarding.actual_start_date - Onboarding.offer_accepted_date))
            .where(Onboarding.actual_start_date.isnot(None))
        )
        avg_completion_days = result.scalar()
        if avg_completion_days:
            avg_completion_days = avg_completion_days.days

        return {
            "total_onboardings": total,
            "in_progress": in_progress,
            "completed": completed,
            "avg_completion_days": avg_completion_days,
            "timestamp": datetime.utcnow().isoformat(),
        }


class TalentPoolService:
    """Service for managing talent pool and talent profiling."""

    async def create_talent_profile(
        self,
        candidate_id: int,
        session: Optional[AsyncSession] = None,
    ) -> TalentProfile:
        """
        Create or update talent profile for candidate.

        Args:
            candidate_id: Candidate ID
            session: Optional database session

        Returns:
            Created or updated TalentProfile
        """
        if not session:
            async with get_db_context() as session:
                return await self._create_talent_profile(candidate_id, session)

        return await self._create_talent_profile(candidate_id, session)

    async def _create_talent_profile(
        self,
        candidate_id: int,
        session: AsyncSession,
    ) -> TalentProfile:
        """Internal talent profile creation implementation."""

        # Check if profile exists
        result = await session.execute(
            select(TalentProfile).where(TalentProfile.candidate_id == candidate_id)
        )
        profile = result.scalar_one_or_none()

        # Get candidate data
        candidate = await session.get(Candidate, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate not found: {candidate_id}")

        # Generate tags and profile data
        profile_data = await self._generate_profile_data(candidate, session)

        if profile:
            # Update existing profile
            profile.tags = profile_data["tags"]
            profile.skill_tags = profile_data["skill_tags"]
            profile.accepts_outsourcing = candidate.accepts_outsourcing or False
            profile.status = "active"
            profile.profile_quality_score = profile_data["quality_score"]
        else:
            # Create new profile
            profile = TalentProfile(
                candidate_id=candidate_id,
                tags=profile_data["tags"],
                skill_tags=profile_data["skill_tags"],
                accepts_outsourcing=candidate.accepts_outsourcing or False,
                status="active",
                profile_quality_score=profile_data["quality_score"],
            )
            session.add(profile)

        await session.commit()
        await session.refresh(profile)

        logger.info(f"Updated talent profile for candidate {candidate_id}")

        return profile

    async def _generate_profile_data(
        self,
        candidate: Candidate,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Generate profile data using LLM and candidate info."""

        # Build profile from candidate data
        tags = set()

        # Add status tag
        tags.add(f"#{candidate.status.value}")

        # Add skill tags
        if candidate.resume_skills:
            for skill in candidate.resume_skills[:10]:  # Top 10 skills
                tags.add(f"#{skill}")

        # Add outsourcing acceptance
        if candidate.accepts_outsourcing:
            tags.add("#接受外包")

        # Add availability
        if candidate.available_immediately:
            tags.add("#随时到岗")

        # Generate profile summary using LLM
        summary_prompt = f"""
Based on the following candidate information, generate a talent profile summary:

Candidate: {candidate.name}
Skills: {', '.join(candidate.resume_skills or [])}
Status: {candidate.status.value}
Notes: {candidate.notes or 'N/A'}

Please provide:
1. A 2-3 sentence professional summary
2. Key strengths (top 3)
3. Suggested job categories (up to 5)
4. Quality score (0-1) based on profile completeness

Respond in JSON format:
{{
    "summary": "...",
    "key_strengths": ["strength1", "strength2", "strength3"],
    "job_categories": ["category1", "category2", ...],
    "quality_score": 0.85
}}
"""

        try:
            llm_result = await llm_service.generate_structured(
                prompt=summary_prompt,
                system_prompt="You are an expert talent profiler. Create concise, accurate talent summaries.",
            )

            return {
                "tags": list(tags),
                "skill_tags": candidate.resume_skills or [],
                "summary": llm_result.get("summary", ""),
                "key_strengths": llm_result.get("key_strengths", []),
                "job_categories": llm_result.get("job_categories", []),
                "quality_score": llm_result.get("quality_score", 0.5),
            }

        except Exception as e:
            logger.error(f"Error generating profile data: {e}")
            return {
                "tags": list(tags),
                "skill_tags": candidate.resume_skills or [],
                "quality_score": 0.5,
            }

    async def search_talent_pool(
        self,
        keywords: Optional[list[str]] = None,
        skills: Optional[list[str]] = None,
        experience_level: Optional[str] = None,
        education_level: Optional[EducationLevel] = None,
        accepts_outsourcing: Optional[bool] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        status: str = "active",
        limit: int = 20,
        session: Optional[AsyncSession] = None,
    ) -> list[TalentProfile]:
        """
        Search talent pool with filters.

        Args:
            keywords: Optional keyword tags
            skills: Optional skill tags
            experience_level: Optional experience level filter
            education_level: Optional education level filter
            accepts_outsourcing: Optional outsourcing acceptance filter
            salary_min: Optional minimum salary
            salary_max: Optional maximum salary
            status: Profile status filter
            limit: Maximum results
            session: Optional database session

        Returns:
            List of matching talent profiles
        """
        if not session:
            async with get_db_context() as session:
                return await self._search_talent_pool(
                    keywords, skills, experience_level, education_level,
                    accepts_outsourcing, salary_min, salary_max, status, limit, session
                )

        return await self._search_talent_pool(
            keywords, skills, experience_level, education_level,
            accepts_outsourcing, salary_min, salary_max, status, limit, session
        )

    async def _search_talent_pool(
        self,
        keywords: list[str],
        skills: list[str],
        experience_level: str,
        education_level: EducationLevel,
        accepts_outsourcing: bool,
        salary_min: int,
        salary_max: int,
        status: str,
        limit: int,
        session: AsyncSession,
    ) -> list[TalentProfile]:
        """Internal talent pool search implementation."""

        # Build query
        from app.models.database import Candidate

        query = (
            select(TalentProfile)
            .join(Candidate, TalentProfile.candidate_id == Candidate.id)
            .where(TalentProfile.status == status)
        )

        # Apply filters
        if keywords:
            for keyword in keywords:
                query = query.where(TalentProfile.tags.contains([keyword]))

        if skills:
            for skill in skills:
                query = query.where(TalentProfile.skill_tags.contains([skill]))

        if accepts_outsourcing is not None:
            query = query.where(TalentProfile.accepts_outsourcing == accepts_outsourcing)

        if salary_min is not None:
            query = query.where(
                or_(
                    Candidate.expected_salary_min.is_(None),
                    Candidate.expected_salary_min >= salary_min,
                )
            )

        if salary_max is not None:
            query = query.where(
                or_(
                    Candidate.expected_salary_max.is_(None),
                    Candidate.expected_salary_max <= salary_max,
                )
            )

        # Order by quality score and limit
        query = query.order_by(TalentProfile.profile_quality_score.desc()).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def recommend_talent_for_job(
        self,
        job_posting_id: int,
        limit: int = 10,
        session: Optional[AsyncSession] = None,
    ) -> list[dict[str, Any]]:
        """
        Recommend candidates from talent pool for a job posting.

        Args:
            job_posting_id: Job posting ID
            limit: Maximum recommendations
            session: Optional database session

        Returns:
            List of recommended candidates with match scores
        """
        if not session:
            async with get_db_context() as session:
                return await self._recommend_talent_for_job(job_posting_id, limit, session)

        return await self._recommend_talent_for_job(job_posting_id, limit, session)

    async def _recommend_talent_for_job(
        self,
        job_posting_id: int,
        limit: int,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Internal talent recommendation implementation."""

        # Get job posting
        from app.models.database import JobPosting

        job_posting = await session.get(JobPosting, job_posting_id)
        if not job_posting:
            raise ValueError(f"Job posting not found: {job_posting_id}")

        # Get matching talent profiles
        profiles = await self._search_talent_pool(
            skills=job_posting.skills_required[:5],
            accepts_outsourcing=(job_posting.employment_type.value == "outsourcing"),
            status="active",
            limit=limit * 2,  # Get more to rank
            session=session,
        )

        # Calculate match scores and rank
        recommendations = []
        for profile in profiles:
            # Get candidate
            candidate = await session.get(Candidate, profile.candidate_id)

            # Calculate skill match
            job_skills = set(job_posting.skills_required)
            candidate_skills = set(candidate.resume_skills or [])
            skill_match = len(job_skills & candidate_skills) / len(job_skills) if job_skills else 0

            # Calculate overall match
            overall_match = (
                skill_match * 0.6 +
                profile.profile_quality_score * 0.4
            )

            recommendations.append({
                "candidate_id": candidate.id,
                "candidate_name": candidate.name,
                "talent_profile_id": profile.id,
                "skill_match_score": skill_match,
                "quality_score": profile.profile_quality_score,
                "overall_match_score": overall_match,
                "key_skills": candidate.resume_skills[:5] if candidate.resume_skills else [],
                "last_contacted": profile.last_contacted.isoformat() if profile.last_contacted else None,
            })

        # Sort by overall match and return top results
        recommendations.sort(key=lambda x: x["overall_match_score"], reverse=True)

        return recommendations[:limit]


# Global service instances
onboarding_service = OnboardingService()
talent_pool_service = TalentPoolService()
