"""
Database models for Talent Acquisition AI System.
Defines all tables and relationships for a production-ready system.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class TimestampMixin:
    """Mixin for adding timestamp fields to models."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


# Enums
class EmploymentType(str, Enum):
    """Employment type enumeration."""
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    OUTSOURCING = "outsourcing"
    INTERN = "intern"


class WorkExperience(str, Enum):
    """Work experience level enumeration."""
    ENTRY = "entry"  # 应届/1年以下
    JUNIOR = "junior"  # 1-3年
    MIDDLE = "middle"  # 3-5年
    SENIOR = "senior"  # 5-10年
    EXPERT = "expert"  # 10年以上


class EducationLevel(str, Enum):
    """Education level enumeration."""
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class CandidateStatus(str, Enum):
    """Candidate status in recruitment pipeline."""
    NEW = "new"
    CONTACTED = "contacted"
    SCREENING = "screening"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_COMPLETED = "interview_completed"
    OFFER_EXTENDED = "offer_extended"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InterviewRound(str, Enum):
    """Interview round types."""
    HR_SCREEN = "hr_screen"
    TECHNICAL = "technical"
    MANAGERIAL = "managerial"
    DIRECTOR = "director"
    CULTURE = "culture"
    OFFER = "offer"


class InterviewResult(str, Enum):
    """Interview result enumeration."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Models


class User(Base, TimestampMixin):
    """System users (recruiters, hiring managers, admins)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="recruiter")
    department: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    job_postings: Mapped[list["JobPosting"]] = relationship(
        "JobPosting", back_populates="created_by_user", cascade="all, delete-orphan"
    )
    interview_feedbacks: Mapped[list["InterviewFeedback"]] = relationship(
        "InterviewFeedback", back_populates="interviewer", cascade="all, delete-orphan"
    )
    activities: Mapped[list["ActivityLog"]] = relationship(
        "ActivityLog", back_populates="user", cascade="all, delete-orphan"
    )


class Client(Base, TimestampMixin):
    """Client companies or departments that request talent."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    contact_person: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    billing_info: Mapped[Optional[dict]] = mapped_column(JSON)
    contract_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    contract_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    job_postings: Mapped[list["JobPosting"]] = relationship(
        "JobPosting", back_populates="client", cascade="all, delete-orphan"
    )


class Project(Base, TimestampMixin):
    """Historical and ongoing projects for RAG context."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tech_stack: Mapped[dict] = mapped_column(JSON, nullable=False)  # {"languages": ["Java"], "frameworks": ["Spring"], "tools": ["Redis", "MySQL"]}
    business_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    team_size: Mapped[int] = mapped_column(Integer, default=1)
    project_type: Mapped[str] = mapped_column(String(50))  # web, mobile, desktop, system, etc.
    complexity_level: Mapped[str] = mapped_column(String(20))  # low, medium, high, critical
    key_challenges: Mapped[Optional[list]] = mapped_column(JSON)
    success_metrics: Mapped[Optional[list]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    client: Mapped["Client"] = relationship("Client")
    project_documents: Mapped[list["ProjectDocument"]] = relationship(
        "ProjectDocument", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectDocument(Base, TimestampMixin):
    """Documents associated with projects for RAG knowledge base."""

    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50))  # requirement, design, technical, report
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)  # in bytes
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    content_text: Mapped[Optional[str]] = mapped_column(Text)  # Extracted text for RAG
    embedding_vector: Mapped[Optional[list]] = mapped_column(JSON)  # Vector embedding
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="project_documents")

    __table_args__ = (
        Index("ix_project_documents_project_type", "project_id", "document_type"),
    )


class JobPosting(Base, TimestampMixin):
    """Job postings/Job Descriptions generated by the system."""

    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    job_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))

    # Job Details
    employment_type: Mapped[EmploymentType] = mapped_column(
        SQLEnum(EmploymentType), nullable=False, default=EmploymentType.FULL_TIME
    )
    work_experience: Mapped[WorkExperience] = mapped_column(
        SQLEnum(WorkExperience), nullable=False
    )
    education_level: Mapped[EducationLevel] = mapped_column(
        SQLEnum(EducationLevel), nullable=False
    )

    # Location & Salary
    work_location: Mapped[str] = mapped_column(String(255), nullable=False)
    salary_min: Mapped[int] = mapped_column(Integer)  # Monthly salary in CNY
    salary_max: Mapped[int] = mapped_column(Integer)
    is_salary_negotiable: Mapped[bool] = mapped_column(Boolean, default=True)

    # JD Content
    responsibilities: Mapped[list] = mapped_column(JSON, nullable=False)
    requirements: Mapped[list] = mapped_column(JSON, nullable=False)
    preferred_qualifications: Mapped[Optional[list]] = mapped_column(JSON)
    benefits: Mapped[Optional[list]] = mapped_column(JSON)

    # AI Generated Fields
    keywords: Mapped[list] = mapped_column(JSON)  # Extracted keywords for matching
    skills_required: Mapped[list] = mapped_column(JSON)  # Structured skills
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_jd_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Workflow Status
    status: Mapped[str] = mapped_column(
        String(50), default="draft"
    )  # draft, published, paused, closed, filled
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Optimization Tracking
    optimization_version: Mapped[int] = mapped_column(Integer, default=1)
    optimization_history: Mapped[Optional[list]] = mapped_column(JSON)
    optimization_suggestions: Mapped[Optional[list]] = mapped_column(JSON)

    # Metadata
    source: Mapped[str] = mapped_column(String(50), default="ai_generated")  # ai_generated, manual
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low, normal, high, urgent
    remote_work: Mapped[bool] = mapped_column(Boolean, default=False)
    travel_required: Mapped[bool] = mapped_column(Boolean, default=False)
    overtime_expected: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="job_postings")
    created_by_user: Mapped["User"] = relationship("User", back_populates="job_postings")
    project: Mapped[Optional["Project"]] = relationship("Project")
    candidates: Mapped[list["Candidate"]] = relationship(
        "Candidate", back_populates="job_posting", cascade="all, delete-orphan"
    )
    jd_optimization_logs: Mapped[list["JDOptimizationLog"]] = relationship(
        "JDOptimizationLog", back_populates="job_posting", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_job_postings_status", "status"),
        Index("ix_job_postings_client", "client_id"),
        Index("ix_job_postings_created", "created_at"),
    )


class JDOptimizationLog(Base, TimestampMixin):
    """Track JD optimization history and feedback."""

    __tablename__ = "jd_optimization_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)

    # Optimization Details
    optimization_type: Mapped[str] = mapped_column(String(50))  # auto, manual, feedback_based
    trigger_reason: Mapped[str] = mapped_column(Text)  # Why was this optimization triggered?

    # Changes Made
    previous_version: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_version: Mapped[dict] = mapped_column(JSON, nullable=False)
    changes_summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Results
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[Optional[float]] = mapped_column(Float)  # Improved match rate

    # Relationships
    job_posting: Mapped["JobPosting"] = relationship(
        "JobPosting", back_populates="jd_optimization_logs"
    )


class Candidate(Base, TimestampMixin):
    """Candidate profiles and resumes."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)

    # Personal Information (Privacy-protected)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    gender: Mapped[Optional[str]] = mapped_column(String(10))

    # Professional Information
    current_position: Mapped[Optional[str]] = mapped_column(String(255))
    current_company: Mapped[Optional[str]] = mapped_column(String(255))
    years_of_experience: Mapped[Optional[float]] = mapped_column(Float)
    education_level: Mapped[Optional[EducationLevel]] = mapped_column(SQLEnum(EducationLevel))
    expected_salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    expected_salary_max: Mapped[Optional[int]] = mapped_column(Integer)

    # Resume & Screening
    resume_file_path: Mapped[Optional[str]] = mapped_column(String(500))
    resume_text: Mapped[Optional[str]] = mapped_column(Text)
    resume_skills: Mapped[Optional[list]] = mapped_column(JSON)  # Extracted skills
    resume_embedding: Mapped[Optional[list]] = mapped_column(JSON)  # Vector embedding

    # Matching Scores
    semantic_score: Mapped[Optional[float]] = mapped_column(Float)  # Semantic similarity
    keyword_score: Mapped[Optional[float]] = mapped_column(Float)  # Keyword match
    overall_score: Mapped[Optional[float]] = mapped_column(Float)  # Combined score
    screening_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Status & Workflow
    status: Mapped[CandidateStatus] = mapped_column(
        SQLEnum(CandidateStatus), default=CandidateStatus.NEW, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50))  # boss_zhipin, liepin, linkedin, referral

    # Communication Tracking
    last_contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    communication_history: Mapped[Optional[list]] = mapped_column(JSON)
    boss_chat_id: Mapped[Optional[str]] = mapped_column(String(100))  # Boss platform chat ID

    # Additional Info
    accepts_outsourcing: Mapped[Optional[bool]] = mapped_column(Boolean)
    available_immediately: Mapped[Optional[bool]] = mapped_column(Boolean)
    relocation_willing: Mapped[Optional[bool]] = mapped_column(Boolean)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[list]] = mapped_column(JSON)  # #Java #接受外包 #移动端

    # Relationships
    job_posting: Mapped["JobPosting"] = relationship("JobPosting", back_populates="candidates")
    interviews: Mapped[list["Interview"]] = relationship(
        "Interview", back_populates="candidate", cascade="all, delete-orphan"
    )
    background_check: Mapped[Optional["BackgroundCheck"]] = relationship(
        "BackgroundCheck", back_populates="candidate", uselist=False
    )
    talent_profile: Mapped[Optional["TalentProfile"]] = relationship(
        "TalentProfile", back_populates="candidate", uselist=False
    )

    __table_args__ = (
        Index("ix_candidates_score", "overall_score"),
        Index("ix_candidates_job", "job_posting_id"),
    )


class Interview(Base, TimestampMixin):
    """Interview schedules and details."""

    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)

    # Interview Details
    round: Mapped[InterviewRound] = mapped_column(SQLEnum(InterviewRound), nullable=False)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str] = mapped_column(String(255))  # Physical address or video link

    # Interviewers
    interviewers: Mapped[list] = mapped_column(JSON)  # List of user IDs and names
    primary_interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Status
    status: Mapped[str] = mapped_column(
        String(50), default="scheduled"
    )  # scheduled, completed, cancelled, rescheduled
    result: Mapped[InterviewResult] = mapped_column(
        SQLEnum(InterviewResult), default=InterviewResult.PENDING
    )

    # Interview Materials
    interview_guide: Mapped[Optional[str]] = mapped_column(Text)
    evaluation_criteria: Mapped[Optional[list]] = mapped_column(JSON)

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="interviews")
    job_posting: Mapped["JobPosting"] = relationship("JobPosting")
    primary_interviewer: Mapped["User"] = relationship("User")
    feedbacks: Mapped[list["InterviewFeedback"]] = relationship(
        "InterviewFeedback", back_populates="interview", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_interviews_candidate", "candidate_id"),
        Index("ix_interviews_status", "status"),
        Index("ix_interviews_scheduled", "scheduled_time"),
    )


class InterviewFeedback(Base, TimestampMixin):
    """Detailed feedback from interviewers."""

    __tablename__ = "interview_feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Overall Assessment
    overall_rating: Mapped[int] = mapped_column(Integer)  # 1-5 scale
    recommendation: Mapped[str] = mapped_column(String(20))  # strong_hire, hire, no_hire, strong_no_hire

    # Detailed Feedback
    technical_score: Mapped[int] = mapped_column(Integer)  # 1-5 scale
    communication_score: Mapped[int] = mapped_column(Integer)  # 1-5 scale
    culture_score: Mapped[int] = mapped_column(Integer)  # 1-5 scale

    # Strengths & Weaknesses
    strengths: Mapped[list] = mapped_column(JSON)
    weaknesses: Mapped[list] = mapped_column(JSON)
    concerns: Mapped[Optional[list]] = mapped_column(JSON)

    # Detailed Comments
    technical_feedback: Mapped[Optional[str]] = mapped_column(Text)
    behavioral_feedback: Mapped[Optional[str]] = mapped_column(Text)
    additional_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Follow-up Actions
    suggested_next_steps: Mapped[Optional[str]] = mapped_column(Text)
    salary_recommendation: Mapped[Optional[str]] = mapped_column(String(100))

    # Feedback Collection Status
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    interview: Mapped["Interview"] = relationship("Interview", back_populates="feedbacks")
    interviewer: Mapped["User"] = relationship("User", back_populates="interview_feedbacks")


class BackgroundCheck(Base, TimestampMixin):
    """Background check and verification information."""

    __tablename__ = "background_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)

    # Education Verification
    education_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    education_verification_method: Mapped[Optional[str]] = mapped_column(String(50))  # chsi, manual, pending
    education_documents: Mapped[Optional[list]] = mapped_column(JSON)

    # Employment Verification
    employment_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    employment_verification_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Criminal Record
    criminal_check_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    criminal_check_result: Mapped[Optional[str]] = mapped_column(String(50))

    # Other Checks
    credit_check: Mapped[Optional[bool]] = mapped_column(Boolean)
    reference_check: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_contacts: Mapped[Optional[list]] = mapped_column(JSON)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, in_progress, completed, failed
    completion_percentage: Mapped[int] = mapped_column(Integer, default=0)
    verified_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="background_check")


class Onboarding(Base, TimestampMixin):
    """Onboarding process tracking."""

    __tablename__ = "onboarding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False)

    # Important Dates
    offer_accepted_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expected_start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actual_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Onboarding Checklist
    contract_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_file_path: Mapped[Optional[str]] = mapped_column(String(500))

    medical_check: Mapped[bool] = mapped_column(Boolean, default=False)
    medical_report_file_path: Mapped[Optional[str]] = mapped_column(String(500))
    medical_check_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)

    background_check: Mapped[bool] = mapped_column(Boolean, default=False)
    background_check_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)

    it_setup: Mapped[bool] = mapped_column(Boolean, default=False)
    equipment_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    email_created: Mapped[bool] = mapped_column(Boolean, default=False)

    # Orientation
    orientation_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    orientation_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="in_progress")  # in_progress, completed, cancelled
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)

    # Notes
    special_requirements: Mapped[Optional[str]] = mapped_column(Text)
    onboarding_notes: Mapped[Optional[str]] = mapped_column(Text)


class TalentProfile(Base, TimestampMixin):
    """Talent profiles for the talent pool/knowledge base."""

    __tablename__ = "talent_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False)

    # Profile Tags & Categories
    tags: Mapped[list] = mapped_column(JSON)  # #Java #Senior #接受外包
    skill_tags: Mapped[list] = mapped_column(JSON)  # ["Spring", "Microservices", "MySQL"]
    industry_tags: Mapped[Optional[list]] = mapped_column(JSON)
    location_tags: Mapped[Optional[list]] = mapped_column(JSON)

    # Availability & Preferences
    accepts_outsourcing: Mapped[bool] = mapped_column(Boolean)
    accepts_remote: Mapped[Optional[bool]] = mapped_column(Boolean)
    salary_range_min: Mapped[Optional[int]] = mapped_column(Integer)
    salary_range_max: Mapped[Optional[int]] = mapped_column(Integer)
    notice_period_days: Mapped[Optional[int]] = mapped_column(Integer)

    # Quality Metrics
    interview_success_rate: Mapped[Optional[float]] = mapped_column(Float)
    average_rating: Mapped[Optional[float]] = mapped_column(Float)
    placement_count: Mapped[int] = mapped_column(Integer, default=0)

    # Interaction History
    last_contacted: Mapped[Optional[datetime]] = mapped_column(DateTime)
    contact_count: Mapped[int] = mapped_column(Integer, default=0)
    response_rate: Mapped[Optional[float]] = mapped_column(Float)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, inactive, blacklisted
    profile_quality_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 score

    # Relationships
    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="talent_profile")

    __table_args__ = (
        Index("ix_talent_profiles_status", "status"),
    )


class ActivityLog(Base, TimestampMixin):
    """Audit log for all system activities."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    # Activity Details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # candidate, job, interview, etc.
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Change Tracking
    changes: Mapped[Optional[dict]] = mapped_column(JSON)  # Before/after values
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="activities")

    __table_args__ = (
        Index("ix_activity_logs_entity", "entity_type", "entity_id"),
    )


class SystemMetrics(Base, TimestampMixin):
    """System performance metrics for monitoring."""

    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(50))
    dimensions: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context
