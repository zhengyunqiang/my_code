"""
RPA Communication Service - Phase 2 Module.
Automates communication with candidates on Boss Zhipin (Boss直聘) platform.
"""
import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from playwright.async_api import async_playwright, Page, Browser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.database import get_db_context
from app.models.database import Candidate, CandidateStatus

settings = get_settings()
logger = get_logger(__name__)


class CommunicationStatus(str, Enum):
    """Status of automated communication."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class MessageTemplate(str, Enum):
    """Predefined message templates for automated communication."""

    INITIAL_CONTACT = """您好，我是{company_name}的招聘专员{recruiter_name}。

我们正在招聘{position}职位，看到您的背景很匹配，想和您了解一下情况。

请问：
1. 您目前是在职状态吗？
2. 您能接受外包性质的工作吗？
3. 您的期望薪资范围是多少？
4. 您的最高学历是什么？

期待您的回复！"""

    SCREENING_FOLLOW_UP = """感谢您的回复！

关于{position}职位，我们这边的基本情况是：
- 工作地点：{location}
- 薪资范围：{salary_range}
- 工作性质：{employment_type}

请问您对这个职位还有其他问题吗？"""

    INTERVIEW_INVITATION = """您好！经过初步沟通，我们对您的背景很感兴趣。

想邀请您参加{round}面试，时间安排在{date_time}。

面试形式：{interview_type}
面试地点：{location}

请问这个时间方便吗？"""

    REJECTION = """感谢您关注{company_name}的{position}职位。

经过综合考虑，我们认为当前阶段您的背景与岗位要求不太匹配。

我们会将您的简历存入人才库，有更合适的职位会第一时间联系您。

祝您求职顺利！"""


class RPACommunicationService:
    """Service for RPA automation on Boss Zhipin."""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        self.communication_tasks: dict[str, dict[str, Any]] = {}

    async def initialize_browser(self) -> None:
        """Initialize browser for automation."""
        if self.browser:
            return

        logger.info("Initializing RPA browser...")

        playwright = await async_playwright().start()

        self.browser = await playwright.chromium.launch(
            headless=settings.boss_headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        self.page = await context.new_page()

        # Set download behavior
        await self.page.route("**/*", lambda route: route.continue_())

        logger.info("RPA browser initialized successfully")

    async def login_boss_zhipin(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """
        Login to Boss Zhipin platform.

        Args:
            username: Platform username (default from settings)
            password: Platform password (default from settings)

        Returns:
            True if login successful, False otherwise
        """
        username = username or settings.boss_username
        password = password or settings.boss_password

        if not username or not password:
            logger.error("Boss Zhipin credentials not configured")
            return False

        if not self.page:
            await self.initialize_browser()

        try:
            logger.info(f"Logging in to Boss Zhipin as {username}...")

            await self.page.goto(settings.boss_base_url, wait_until="networkidle")
            await asyncio.sleep(2)

            # Check if already logged in
            if await self._check_login_status():
                logger.info("Already logged in")
                self.is_logged_in = True
                return True

            # Find and fill login form
            # Note: These selectors are examples and may need adjustment
            await self.page.fill('input[placeholder*="手机号"]', username)
            await self.page.fill('input[placeholder*="密码"]', password)

            # Click login button
            await self.page.click('button:has-text("登录")')

            # Wait for navigation
            await self.page.wait_for_url("**/chat/**", timeout=10000)

            self.is_logged_in = True
            logger.info("Successfully logged in to Boss Zhipin")
            return True

        except Exception as e:
            logger.error(f"Failed to login to Boss Zhipin: {e}")
            self.is_logged_in = False
            return False

    async def _check_login_status(self) -> bool:
        """Check if already logged in."""
        try:
            # Look for logged-in user indicators
            user_element = await self.page.query_selector('.user-nav')
            return user_element is not None
        except:
            return False

    async def send_message(
        self,
        candidate_chat_id: str,
        message: str,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        Send message to candidate on Boss Zhipin.

        Args:
            candidate_chat_id: Boss platform chat ID for candidate
            message: Message content
            max_retries: Maximum retry attempts

        Returns:
            Result dictionary with status and details
        """
        if not self.is_logged_in:
            if not await self.login_boss_zhipin():
                return {"status": "failed", "error": "Not logged in"}

        for attempt in range(max_retries):
            try:
                logger.info(f"Sending message to {candidate_chat_id}, attempt {attempt + 1}")

                # Navigate to chat
                chat_url = f"{settings.boss_base_url}/web/user/chat/{candidate_chat_id}"
                await self.page.goto(chat_url, wait_until="networkidle")
                await asyncio.sleep(1)

                # Find message input and send
                await self.page.fill('textarea[placeholder*="请输入消息"]', message)
                await self.page.click('button:has-text("发送")')

                # Wait for send confirmation
                await asyncio.sleep(1)

                logger.info(f"Message sent successfully to {candidate_chat_id}")
                return {
                    "status": "success",
                    "chat_id": candidate_chat_id,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(f"Error sending message (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {
                        "status": "failed",
                        "chat_id": candidate_chat_id,
                        "error": str(e),
                        "attempts": max_retries,
                    }
                await asyncio.sleep(2)

    async def get_candidate_response(
        self,
        candidate_chat_id: str,
        wait_time: int = 60,
    ) -> Optional[str]:
        """
        Wait for and get candidate response.

        Args:
            candidate_chat_id: Boss platform chat ID
            wait_time: Maximum wait time in seconds

        Returns:
            Candidate response text or None if timeout
        """
        if not self.page:
            return None

        try:
            # Navigate to chat
            chat_url = f"{settings.boss_base_url}/web/user/chat/{candidate_chat_id}"
            await self.page.goto(chat_url, wait_until="networkidle")

            # Wait for new message
            start_time = datetime.utcnow()
            last_message_count = await self._get_message_count()

            while (datetime.utcnow() - start_time).seconds < wait_time:
                await asyncio.sleep(5)

                current_count = await self._get_message_count()
                if current_count > last_message_count:
                    # Get last message
                    messages = await self.page.query_selector_all('.chat-message')
                    if messages:
                        last_message = await messages[-1].inner_text()
                        return last_message

            logger.warning(f"Timeout waiting for response from {candidate_chat_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting candidate response: {e}")
            return None

    async def _get_message_count(self) -> int:
        """Get current message count in chat."""
        try:
            messages = await self.page.query_selector_all('.chat-message')
            return len(messages)
        except:
            return 0

    async def automated_screening_campaign(
        self,
        candidate_ids: list[int],
        job_posting_id: int,
        message_template: str,
        session: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """
        Run automated screening campaign for multiple candidates.

        Args:
            candidate_ids: List of candidate IDs to contact
            job_posting_id: Job posting ID
            message_template: Message template to use
            session: Optional database session

        Returns:
            Campaign results summary
        """
        if not session:
            async with get_db_context() as session:
                return await self._run_automated_campaign(
                    candidate_ids, job_posting_id, message_template, session
                )

        return await self._run_automated_campaign(
            candidate_ids, job_posting_id, message_template, session
        )

    async def _run_automated_campaign(
        self,
        candidate_ids: list[int],
        job_posting_id: int,
        message_template: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Internal campaign implementation."""

        # Get job posting details
        from sqlalchemy import select
        from app.models.database import JobPosting

        job_result = await session.execute(
            select(JobPosting).where(JobPosting.id == job_posting_id)
        )
        job_posting = job_result.scalar_one_or_none()

        if not job_posting:
            raise ValueError(f"Job posting not found: {job_posting_id}")

        # Get candidates
        candidates_result = await session.execute(
            select(Candidate).where(Candidate.id.in_(candidate_ids))
        )
        candidates = list(candidates_result.scalars().all())

        # Initialize campaign
        campaign_id = f"CAM-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.communication_tasks[campaign_id] = {
            "status": CommunicationStatus.IN_PROGRESS,
            "total": len(candidates),
            "completed": 0,
            "failed": 0,
            "results": [],
        }

        # Process each candidate
        for candidate in candidates:
            if not candidate.boss_chat_id:
                logger.warning(f"Candidate {candidate.id} has no Boss chat ID, skipping")
                continue

            try:
                # Personalize message
                message = message_template.format(
                    company_name="公司名称",
                    recruiter_name="招聘专员",
                    position=job_posting.job_title,
                    location=job_posting.work_location,
                    salary_range=f"{job_posting.salary_min}-{job_posting.salary_max}K",
                    employment_type=job_posting.employment_type.value,
                )

                # Send message
                result = await self.send_message(candidate.boss_chat_id, message)

                if result["status"] == "success":
                    self.communication_tasks[campaign_id]["completed"] += 1

                    # Update candidate status
                    candidate.status = CandidateStatus.CONTACTED
                    candidate.last_contacted_at = datetime.utcnow()

                    # Add to communication history
                    if not candidate.communication_history:
                        candidate.communication_history = []

                    candidate.communication_history.append({
                        "timestamp": datetime.utcnow().isoformat(),
                        "type": "outbound",
                        "message": message,
                        "status": "sent",
                    })

                else:
                    self.communication_tasks[campaign_id]["failed"] += 1

                self.communication_tasks[campaign_id]["results"].append({
                    "candidate_id": candidate.id,
                    "chat_id": candidate.boss_chat_id,
                    "result": result,
                })

                # Rate limiting - avoid spam detection
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error contacting candidate {candidate.id}: {e}")
                self.communication_tasks[campaign_id]["failed"] += 1

        await session.commit()

        self.communication_tasks[campaign_id]["status"] = CommunicationStatus.COMPLETED

        logger.info(f"Campaign {campaign_id} completed: "
                   f"{self.communication_tasks[campaign_id]['completed']} sent, "
                   f"{self.communication_tasks[campaign_id]['failed']} failed")

        return self.communication_tasks[campaign_id]

    async def parse_candidate_response(
        self,
        response_text: str,
        required_questions: list[str],
    ) -> dict[str, Any]:
        """
        Parse candidate's response using LLM.

        Args:
            response_text: Candidate's response text
            required_questions: List of questions that were asked

        Returns:
            Parsed response with structured answers
        """
        from app.services.llm_service import llm_service

        prompt = f"""Please analyze the following candidate response and extract structured information.

Response: {response_text}

Questions asked:
{json.dumps(required_questions, ensure_ascii=False)}

Please extract and return in JSON format:
{{
    "is_employed": true/false,
    "accepts_outsourcing": true/false/null,
    "expected_salary_min": 10000,
    "expected_salary_max": 15000,
    "education_level": "本科",
    "available_immediately": true/false,
    "relocation_willing": true/false,
    "confidence_score": 0.95,
    "missing_info": ["question1", "question2"],
    "notes": "Additional observations"
}}"""

        try:
            parsed = await llm_service.generate_structured(
                prompt=prompt,
                system_prompt="You are an expert at parsing candidate responses. Extract information accurately and indicate when information is missing or ambiguous.",
            )

            return parsed

        except Exception as e:
            logger.error(f"Error parsing candidate response: {e}")
            return {
                "error": str(e),
                "confidence_score": 0.0,
            }

    async def close_browser(self) -> None:
        """Close browser and cleanup resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
            self.is_logged_in = False
            logger.info("RPA browser closed")


# Global service instance
rpa_communication_service = RPACommunicationService()
