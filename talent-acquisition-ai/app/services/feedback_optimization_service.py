"""
Interview Feedback Collection and JD Optimization Service - Phase 3 Core Module.
Handles automated feedback collection, analysis, and JD dynamic optimization.
"""
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import (
    Interview,
    InterviewFeedback,
    InterviewResult,
    InterviewRound,
    JDOptimizationLog,
    JobPosting,
)
from app.models.schemas import InterviewFeedbackCreate, InterviewFeedbackResponse
from app.services.llm_service import llm_service

settings = get_settings()
logger = get_logger(__name__)


class FeedbackReminderStrategy(str, Enum):
    """Strategy for feedback reminders."""

    GENTLE = "gentle"
    FIRM = "firm"
    URGENT = "urgent"


class JDOptimizationTrigger(str, Enum):
    """Triggers for JD optimization."""

    LOW_SUCCESS_RATE = "low_success_rate"
    REPEATED_REJECTION = "repeated_rejection"
    SKILL_MISMATCH = "skill_mismatch"
    SALARY_ISSUE = "salary_issue"
    MANUAL_REQUEST = "manual_request"


class FeedbackCollectionService:
    """Service for collecting interview feedback from interviewers."""

    def __init__(self):
        self.reminder_templates = {
            FeedbackReminderStrategy.GENTLE: """您好，{interviewer_name}老师！

关于{candidate_name}的{round_name}面试已经结束了，方便的时候麻烦您帮忙填写一下面试反馈，这对我们的招聘工作很重要。

您可以通过以下链接提交反馈：
{feedback_link}

感谢您的时间！""",

            FeedbackReminderStrategy.FIRM: """{interviewer_name}老师您好，

提醒您关于{candidate_name}的{round_name}面试反馈还未提交。

面试已经结束{hours_passed}小时了，为了不影响招聘进度，请您尽快提交反馈。

反馈链接：{feedback_link}

如有问题请直接联系我。谢谢！""",

            FeedbackReminderStrategy.URGENT: """紧急提醒：{interviewer_name}老师

{candidate_name}的面试反馈已逾期{hours_passed}小时，请立即提交！

由于候选人还在等待我们的结果，您的反馈非常紧急。

请点击链接立即提交：{feedback_link}

请务必在今天内完成！""",
        }

    async def check_pending_feedbacks(
        self,
        hours_threshold: int = 2,
        session: Optional[AsyncSession] = None,
    ) -> list[Interview]:
        """
        Check for interviews without feedback after threshold hours.

        Args:
            hours_threshold: Hours after interview to check
            session: Optional database session

        Returns:
            List of interviews pending feedback
        """
        if not session:
            async with get_db_context() as session:
                return await self._check_pending_feedbacks(hours_threshold, session)

        return await self._check_pending_feedbacks(hours_threshold, session)

    async def _check_pending_feedbacks(
        self,
        hours_threshold: int,
        session: AsyncSession,
    ) -> list[Interview]:
        """Internal pending feedback check implementation."""

        threshold_time = datetime.utcnow() - timedelta(hours=hours_threshold)

        result = await session.execute(
            select(Interview)
            .where(
                and_(
                    Interview.scheduled_time < threshold_time,
                    Interview.status == "completed",
                    Interview.result == InterviewResult.PENDING,
                )
            )
            .order_by(Interview.scheduled_time)
        )

        return list(result.scalars().all())

    async def send_feedback_reminder(
        self,
        interview: Interview,
        strategy: FeedbackReminderStrategy = FeedbackReminderStrategy.GENTLE,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Send feedback reminder to interviewer.

        Args:
            interview: Interview object
            strategy: Reminder strategy
            session: Optional database session

        Returns:
            Result dictionary
        """
        if not session:
            async with get_db_context() as session:
                return await self._send_feedback_reminder(interview, strategy, session)

        return await self._send_feedback_reminder(interview, strategy, session)

    async def _send_feedback_reminder(
        self,
        interview: Interview,
        strategy: FeedbackReminderStrategy,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Internal reminder sending implementation."""

        # Get interviewer info
        from app.models.database import User
        interviewer = await session.get(User, interview.primary_interviewer_id)
        if not interviewer:
            return {"status": "error", "message": "Interviewer not found"}

        # Get candidate info
        from app.models.database import Candidate
        candidate = await session.get(Candidate, interview.candidate_id)
        if not candidate:
            return {"status": "error", "message": "Candidate not found"}

        # Calculate hours passed
        hours_passed = int((datetime.utcnow() - interview.scheduled_time).total_seconds() / 3600)

        # Get existing feedback to check reminder count
        result = await session.execute(
            select(InterviewFeedback)
            .where(InterviewFeedback.interview_id == interview.id)
        )
        existing_feedback = result.scalar_one_or_none()

        if existing_feedback and existing_feedback.reminder_count >= 3:
            return {"status": "skipped", "message": "Maximum reminders sent"}

        # Generate reminder message
        message = self.reminder_templates[strategy].format(
            interviewer_name=interviewer.full_name,
            candidate_name=candidate.name,
            round_name=self._get_round_name(interview.round),
            hours_passed=hours_passed,
            feedback_link=f"https://talentai.company/feedback/{interview.id}",
        )

        # Send notification (integrate with your notification system)
        # For now, just log
        logger.info(f"Sending {strategy} reminder to {interviewer.email}")
        logger.debug(f"Reminder message: {message}")

        # Update feedback record
        if not existing_feedback:
            feedback = InterviewFeedback(
                interview_id=interview.id,
                interviewer_id=interview.primary_interviewer_id,
                reminder_sent=True,
                reminder_count=1,
            )
            session.add(feedback)
        else:
            existing_feedback.reminder_sent = True
            existing_feedback.reminder_count += 1

        await session.commit()

        return {
            "status": "sent",
            "strategy": strategy,
            "interview_id": interview.id,
            "interviewer_id": interview.primary_interviewer_id,
            "reminder_count": existing_feedback.reminder_count if existing_feedback else 1,
            "hours_passed": hours_passed,
        }

    def _get_round_name(self, round: InterviewRound) -> str:
        """Get display name for interview round."""
        names = {
            InterviewRound.HR_SCREEN: "初筛面试",
            InterviewRound.TECHNICAL: "技术面试",
            InterviewRound.MANAGERIAL: "经理面试",
            InterviewRound.DIRECTOR: "总监面试",
            InterviewRound.CULTURE: "文化面试",
            InterviewRound.OFFER: "薪资谈判",
        }
        return names.get(round, "面试")

    async def submit_feedback(
        self,
        feedback_data: InterviewFeedbackCreate,
        session: Optional[AsyncSession] = None,
    ) -> InterviewFeedbackResponse:
        """
        Submit interview feedback.

        Args:
            feedback_data: Feedback data
            session: Optional database session

        Returns:
            Created feedback response
        """
        if not session:
            async with get_db_context() as session:
                return await self._submit_feedback(feedback_data, session)

        return await self._submit_feedback(feedback_data, session)

    async def _submit_feedback(
        self,
        feedback_data: InterviewFeedbackCreate,
        session: AsyncSession,
    ) -> InterviewFeedbackResponse:
        """Internal feedback submission implementation."""

        # Create feedback record
        feedback = InterviewFeedback(
            interview_id=feedback_data.interview_id,
            interviewer_id=feedback_data.interviewer_id,
            overall_rating=feedback_data.overall_rating,
            recommendation=feedback_data.recommendation,
            technical_score=feedback_data.technical_score,
            communication_score=feedback_data.communication_score,
            culture_score=feedback_data.culture_score,
            strengths=feedback_data.strengths,
            weaknesses=feedback_data.weaknesses,
            concerns=feedback_data.get("concerns", []),
            technical_feedback=feedback_data.technical_feedback,
            behavioral_feedback=feedback_data.behavioral_feedback,
            additional_notes=feedback_data.additional_notes,
            suggested_next_steps=feedback_data.suggested_next_steps,
            salary_recommendation=feedback_data.salary_recommendation,
            submitted_at=datetime.utcnow(),
        )

        session.add(feedback)
        await session.commit()
        await session.refresh(feedback)

        logger.info(f"Feedback submitted for interview {feedback_data.interview_id}")

        # Trigger JD optimization analysis
        await self._analyze_feedback_for_optimization(feedback, session)

        return InterviewFeedbackResponse.model_validate(feedback)


class JDOptimizationService:
    """Service for analyzing feedback and optimizing JDs."""

    def __init__(self):
        self.optimization_thresholds = {
            "consecutive_rejections": 3,
            "low_success_rate": 0.3,  # 30% pass rate
            "feedback_count_for_analysis": 5,
        }

    async def analyze_job_posting_performance(
        self,
        job_posting_id: int,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Analyze job posting performance based on feedback data.

        Args:
            job_posting_id: Job posting ID to analyze
            session: Optional database session

        Returns:
            Analysis results with optimization suggestions
        """
        if not session:
            async with get_db_context() as session:
                return await self._analyze_job_posting_performance(job_posting_id, session)

        return await self._analyze_job_posting_performance(job_posting_id, session)

    async def _analyze_job_posting_performance(
        self,
        job_posting_id: int,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Internal performance analysis implementation."""

        # Get job posting
        job_posting = await session.get(JobPosting, job_posting_id)
        if not job_posting:
            raise ValueError(f"Job posting not found: {job_posting_id}")

        # Get all interviews for this job
        from app.models.database import Interview, InterviewFeedback, Candidate

        interviews_result = await session.execute(
            select(Interview)
            .where(Interview.job_posting_id == job_posting_id)
            .where(Interview.status == "completed")
        )
        interviews = list(interviews_result.scalars().all())

        if not interviews:
            return {
                "job_posting_id": job_posting_id,
                "status": "insufficient_data",
                "message": "No completed interviews found for analysis",
            }

        # Analyze feedback patterns
        feedback_stats = {
            "total_interviews": len(interviews),
            "passed": 0,
            "failed": 0,
            "pending": 0,
            "avg_overall_rating": 0.0,
            "avg_technical_score": 0.0,
            "common_weaknesses": {},
            "rejection_reasons": {},
        }

        feedback_scores = []
        technical_scores = []

        for interview in interviews:
            # Get feedback
            feedback_result = await session.execute(
                select(InterviewFeedback).where(InterviewFeedback.interview_id == interview.id)
            )
            feedback = feedback_result.scalar_one_or_none()

            if feedback:
                if interview.result == InterviewResult.PASSED:
                    feedback_stats["passed"] += 1
                elif interview.result == InterviewResult.FAILED:
                    feedback_stats["failed"] += 1
                    # Analyze rejection reasons
                    if feedback.weaknesses:
                        for weakness in feedback.weaknesses:
                            feedback_stats["rejection_reasons"][weakness] = \
                                feedback_stats["rejection_reasons"].get(weakness, 0) + 1
                else:
                    feedback_stats["pending"] += 1

                feedback_scores.append(feedback.overall_rating)
                technical_scores.append(feedback.technical_score)

                # Aggregate weaknesses
                if feedback.weaknesses:
                    for weakness in feedback.weaknesses:
                        feedback_stats["common_weaknesses"][weakness] = \
                            feedback_stats["common_weaknesses"].get(weakness, 0) + 1

        # Calculate averages
        if feedback_scores:
            feedback_stats["avg_overall_rating"] = sum(feedback_scores) / len(feedback_scores)
        if technical_scores:
            feedback_stats["avg_technical_score"] = sum(technical_scores) / len(technical_scores)

        # Calculate success rate
        total_decided = feedback_stats["passed"] + feedback_stats["failed"]
        success_rate = feedback_stats["passed"] / total_decided if total_decided > 0 else 0

        feedback_stats["success_rate"] = success_rate

        # Generate optimization suggestions using LLM
        suggestions = await self._generate_optimization_suggestions(
            job_posting,
            feedback_stats,
            session,
        )

        # Check triggers
        triggers = []
        if success_rate < self.optimization_thresholds["low_success_rate"]:
            triggers.append(JDOptimizationTrigger.LOW_SUCCESS_RATE)

        # Check for consecutive rejections with same reason
        if feedback_stats["rejection_reasons"]:
            top_reason = max(feedback_stats["rejection_reasons"].items(), key=lambda x: x[1])
            if top_reason[1] >= self.optimization_thresholds["consecutive_rejections"]:
                triggers.append(JDOptimizationTrigger.REPEATED_REJECTION)

        return {
            "job_posting_id": job_posting_id,
            "status": "analysis_complete",
            "statistics": feedback_stats,
            "triggers": [t.value for t in triggers],
            "suggestions": suggestions,
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }

    async def _generate_optimization_suggestions(
        self,
        job_posting: JobPosting,
        feedback_stats: dict[str, Any],
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Generate optimization suggestions using LLM."""

        # Build analysis prompt
        analysis_prompt = f"""
Based on the following job posting and interview feedback data, provide optimization suggestions:

Job Posting:
- Title: {job_posting.job_title}
- Requirements: {', '.join(job_posting.requirements[:5])}
- Skills Required: {', '.join([s['name'] for s in job_posting.skills_required[:5]])}
- Salary Range: {job_posting.salary_min}-{job_posting.salary_max}K

Interview Feedback Statistics:
- Total Interviews: {feedback_stats['total_interviews']}
- Success Rate: {feedback_stats.get('success_rate', 0):.1%}
- Average Technical Score: {feedback_stats.get('avg_technical_score', 0):.1f}/5
- Common Weaknesses: {json.dumps(feedback_stats.get('common_weaknesses', {}), ensure_ascii=False)}
- Rejection Reasons: {json.dumps(feedback_stats.get('rejection_reasons', {}), ensure_ascii=False)}

Please provide 3-5 specific, actionable optimization suggestions in JSON format:
[
    {{
        "category": "requirements|salary|skills|description|other",
        "priority": "high|medium|low",
        "current_issue": "Description of the problem",
        "suggested_change": "Specific change to make",
        "expected_impact": "Expected outcome",
        "implementation": "How to implement"
    }}
]
"""

        try:
            suggestions = await llm_service.generate_structured(
                prompt=analysis_prompt,
                system_prompt="You are an expert recruitment analyst. Provide actionable, specific optimization suggestions based on data.",
            )

            return suggestions if isinstance(suggestions, list) else []

        except Exception as e:
            logger.error(f"Error generating optimization suggestions: {e}")
            return []

    async def apply_jd_optimization(
        self,
        job_posting_id: int,
        optimization_ids: list[int],
        notes: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> JDOptimizationLog:
        """
        Apply selected optimizations to a job posting.

        Args:
            job_posting_id: Job posting ID
            optimization_ids: List of suggestion IDs to apply
            notes: Optional notes about the optimization
            session: Optional database session

        Returns:
            Optimization log record
        """
        if not session:
            async with get_db_context() as session:
                return await self._apply_jd_optimization(
                    job_posting_id, optimization_ids, notes, session
                )

        return await self._apply_jd_optimization(
            job_posting_id, optimization_ids, notes, session
        )

    async def _apply_jd_optimization(
        self,
        job_posting_id: int,
        optimization_ids: list[int],
        notes: str,
        session: AsyncSession,
    ) -> JDOptimizationLog:
        """Internal optimization application implementation."""

        # Get current job posting
        job_posting = await session.get(JobPosting, job_posting_id)
        if not job_posting:
            raise ValueError(f"Job posting not found: {job_posting_id}")

        # Store previous version
        previous_version = {
            "requirements": job_posting.requirements,
            "skills_required": job_posting.skills_required,
            "salary_min": job_posting.salary_min,
            "salary_max": job_posting.salary_max,
            "summary": job_posting.summary,
        }

        # Apply optimizations (simplified - in production would be more sophisticated)
        changes = []

        # This is where you'd actually apply the specific optimizations
        # For now, we'll just increment the version
        job_posting.optimization_version += 1

        await session.commit()
        await session.refresh(job_posting)

        # Create optimization log
        optimization_log = JDOptimizationLog(
            job_posting_id=job_posting_id,
            optimization_type="feedback_based",
            trigger_reason="Applied based on interview feedback analysis",
            previous_version=previous_version,
            new_version={
                "requirements": job_posting.requirements,
                "skills_required": job_posting.skills_required,
                "salary_min": job_posting.salary_min,
                "salary_max": job_posting.salary_max,
                "summary": job_posting.summary,
            },
            changes_summary=notes or "Applied optimizations based on feedback analysis",
        )

        session.add(optimization_log)
        await session.commit()
        await session.refresh(optimization_log)

        logger.info(f"Applied JD optimization for job posting {job_posting_id}")

        return optimization_log

    async def _analyze_feedback_for_optimization(
        self,
        feedback: InterviewFeedback,
        session: AsyncSession,
    ) -> None:
        """
        Analyze feedback and trigger optimization if needed.

        Args:
            feedback: Interview feedback object
            session: Database session
        """
        # Get interview and job posting
        interview = await session.get(Interview, feedback.interview_id)
        if not interview:
            return

        job_posting = await session.get(JobPosting, interview.job_posting_id)
        if not job_posting:
            return

        # If feedback is negative and mentions specific issues, consider optimization
        if feedback.recommendation in ["no_hire", "strong_no_hire"] and feedback.weaknesses:
            # Check if this is a pattern
            recent_feedbacks = await session.execute(
                select(InterviewFeedback)
                .join(Interview, InterviewFeedback.interview_id == Interview.id)
                .where(
                    and_(
                        Interview.job_posting_id == job_posting.id,
                        InterviewFeedback.recommendation.in_(["no_hire", "strong_no_hire"]),
                    )
                )
                .order_by(InterviewFeedback.created_at.desc())
                .limit(self.optimization_thresholds["consecutive_rejections"])
            )

            if recent_feedbacks.rowcount >= self.optimization_thresholds["consecutive_rejections"]:
                logger.info(f"Triggering JD optimization analysis for job posting {job_posting.id}")

                # This would trigger an async task to analyze and suggest optimizations
                # For now, just log it


# Global service instances
feedback_collection_service = FeedbackCollectionService()
jd_optimization_service = JDOptimizationService()
