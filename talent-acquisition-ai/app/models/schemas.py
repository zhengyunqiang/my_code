"""
Pydantic schemas for API request/response validation.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


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
    ENTRY = "entry"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    EXPERT = "expert"


class EducationLevel(str, Enum):
    """Education level enumeration."""
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class CandidateStatus(str, Enum):
    """Candidate status enumeration."""
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


# Base schemas
class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = {"from_attributes": True, "use_enum_values": True}


class TimestampSchema(BaseSchema):
    """Schema with timestamp fields."""

    created_at: datetime
    updated_at: datetime


# User schemas
class UserBase(BaseSchema):
    """Base user schema."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    full_name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role: str = Field(default="recruiter", max_length=50)
    department: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseSchema):
    """Schema for updating a user."""

    email: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase, TimestampSchema):
    """Schema for user response."""

    id: int
    is_active: bool
    is_superuser: bool
    last_login: Optional[datetime] = None


class UserLogin(BaseSchema):
    """Schema for user login."""

    username: str
    password: str


class Token(BaseSchema):
    """Schema for JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# Client schemas
class ClientBase(BaseSchema):
    """Base client schema."""

    name: str = Field(..., max_length=255)
    company_code: str = Field(..., max_length=50)
    industry: Optional[str] = Field(None, max_length=100)
    contact_person: str = Field(..., max_length=100)
    contact_phone: str = Field(..., max_length=20)
    contact_email: str = Field(..., max_length=255)
    address: Optional[str] = None
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    """Schema for creating a new client."""

    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None


class ClientUpdate(BaseSchema):
    """Schema for updating a client."""

    name: Optional[str] = None
    industry: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ClientResponse(ClientBase, TimestampSchema):
    """Schema for client response."""

    id: int
    is_active: bool
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None


# Project schemas
class ProjectBase(BaseSchema):
    """Base project schema."""

    name: str = Field(..., max_length=255)
    code: str = Field(..., max_length=50)
    client_id: int
    description: str
    tech_stack: dict[str, Any]
    business_domain: str = Field(..., max_length=100)
    start_date: datetime
    end_date: Optional[datetime] = None
    team_size: int = Field(default=1, ge=1)
    project_type: Optional[str] = Field(None, max_length=50)
    complexity_level: Optional[str] = Field(None, max_length=20)
    key_challenges: Optional[list[str]] = None
    success_metrics: Optional[list[str]] = None


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    pass


class ProjectUpdate(BaseSchema):
    """Schema for updating a project."""

    name: Optional[str] = None
    description: Optional[str] = None
    tech_stack: Optional[dict[str, Any]] = None
    end_date: Optional[datetime] = None
    team_size: Optional[int] = None
    is_active: Optional[bool] = None


class ProjectResponse(ProjectBase, TimestampSchema):
    """Schema for project response."""

    id: int
    is_active: bool


# Job Posting schemas
class JobPostingBase(BaseSchema):
    """Base job posting schema."""

    job_title: str = Field(..., max_length=255)
    client_id: int
    employment_type: EmploymentType
    work_experience: WorkExperience
    education_level: EducationLevel
    work_location: str = Field(..., max_length=255)
    salary_min: Optional[int] = Field(None, ge=0)
    salary_max: Optional[int] = Field(None, ge=0)
    is_salary_negotiable: bool = True
    remote_work: bool = False
    travel_required: bool = False
    overtime_expected: bool = False

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, v: Optional[int], info) -> Optional[int]:
        """Validate that salary_max is greater than salary_min."""
        if v is not None and "salary_min" in info.data:
            salary_min = info.data["salary_min"]
            if salary_min is not None and v <= salary_min:
                raise ValueError("salary_max must be greater than salary_min")
        return v


class JobPostingCreate(JobPostingBase):
    """Schema for creating a new job posting."""

    project_id: Optional[int] = None
    responsibilities: list[str]
    requirements: list[str]
    preferred_qualifications: Optional[list[str]] = None
    benefits: Optional[list[str]] = None
    priority: str = Field(default="normal", max_length=20)
    deadline: Optional[datetime] = None


class JobPostingUpdate(BaseSchema):
    """Schema for updating a job posting."""

    job_title: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    work_experience: Optional[WorkExperience] = None
    education_level: Optional[EducationLevel] = None
    work_location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    is_salary_negotiable: Optional[bool] = None
    responsibilities: Optional[list[str]] = None
    requirements: Optional[list[str]] = None
    preferred_qualifications: Optional[list[str]] = None
    benefits: Optional[list[str]] = None
    remote_work: Optional[bool] = None
    travel_required: Optional[bool] = None
    overtime_expected: Optional[bool] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    deadline: Optional[datetime] = None


class JobPostingResponse(JobPostingBase, TimestampSchema):
    """Schema for job posting response."""

    id: int
    job_code: str
    created_by: int
    project_id: Optional[int] = None
    responsibilities: list[str]
    requirements: list[str]
    preferred_qualifications: Optional[list[str]] = None
    benefits: Optional[list[str]] = None
    keywords: list[str]
    skills_required: list[str]
    summary: str
    full_jd_text: str
    status: str
    published_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    optimization_version: int
    priority: str
    source: str


# Candidate schemas
class CandidateBase(BaseSchema):
    """Base candidate schema."""

    name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    age: Optional[int] = Field(None, ge=18, le=65)
    current_position: Optional[str] = Field(None, max_length=255)
    current_company: Optional[str] = Field(None, max_length=255)
    years_of_experience: Optional[float] = Field(None, ge=0)
    education_level: Optional[EducationLevel] = None
    expected_salary_min: Optional[int] = Field(None, ge=0)
    expected_salary_max: Optional[int] = Field(None, ge=0)
    accepts_outsourcing: Optional[bool] = None
    available_immediately: Optional[bool] = Field(None, alias="available immediately")
    relocation_willing: Optional[bool] = None
    source: str = Field(..., max_length=50)
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class CandidateCreate(CandidateBase):
    """Schema for creating a new candidate."""

    job_posting_id: int
    resume_file_path: Optional[str] = None


class CandidateUpdate(BaseSchema):
    """Schema for updating a candidate."""

    status: Optional[CandidateStatus] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    accepts_outsourcing: Optional[bool] = None
    available_immediately: Optional[bool] = None
    relocation_willing: Optional[bool] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class CandidateResponse(CandidateBase, TimestampSchema):
    """Schema for candidate response."""

    id: int
    candidate_code: str
    job_posting_id: int
    status: CandidateStatus
    resume_file_path: Optional[str] = None
    resume_skills: Optional[list[str]] = None
    semantic_score: Optional[float] = None
    keyword_score: Optional[float] = None
    overall_score: Optional[float] = None
    screening_notes: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    communication_history: Optional[list[dict[str, Any]]] = None


# Interview schemas
class InterviewBase(BaseSchema):
    """Base interview schema."""

    round: str = Field(..., max_length=50)
    scheduled_time: datetime
    duration_minutes: int = Field(default=60, ge=15, le=240)
    location: str = Field(..., max_length=255)


class InterviewCreate(InterviewBase):
    """Schema for creating a new interview."""

    candidate_id: int
    job_posting_id: int
    interviewers: list[dict[str, Any]]
    primary_interviewer_id: int
    interview_guide: Optional[str] = None
    evaluation_criteria: Optional[list[str]] = None


class InterviewUpdate(BaseSchema):
    """Schema for updating an interview."""

    scheduled_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    status: Optional[str] = None
    result: Optional[str] = None


class InterviewResponse(InterviewBase, TimestampSchema):
    """Schema for interview response."""

    id: int
    candidate_id: int
    job_posting_id: int
    interviewers: list[dict[str, Any]]
    primary_interviewer_id: int
    status: str
    result: str
    interview_guide: Optional[str] = None
    evaluation_criteria: Optional[list[str]] = None


# Interview Feedback schemas
class InterviewFeedbackBase(BaseSchema):
    """Base interview feedback schema."""

    overall_rating: int = Field(..., ge=1, le=5)
    recommendation: str = Field(..., max_length=20)
    technical_score: int = Field(..., ge=1, le=5)
    communication_score: int = Field(..., ge=1, le=5)
    culture_score: int = Field(..., ge=1, le=5)


class InterviewFeedbackCreate(InterviewFeedbackBase):
    """Schema for creating interview feedback."""

    interview_id: int
    interviewer_id: int
    strengths: list[str]
    weaknesses: list[str]
    concerns: Optional[list[str]] = None
    technical_feedback: Optional[str] = None
    behavioral_feedback: Optional[str] = None
    additional_notes: Optional[str] = None
    suggested_next_steps: Optional[str] = None
    salary_recommendation: Optional[str] = None


class InterviewFeedbackResponse(InterviewFeedbackBase, TimestampSchema):
    """Schema for interview feedback response."""

    id: int
    interview_id: int
    interviewer_id: int
    strengths: list[str]
    weaknesses: list[str]
    concerns: Optional[list[str]] = None
    technical_feedback: Optional[str] = None
    behavioral_feedback: Optional[str] = None
    additional_notes: Optional[str] = None
    suggested_next_steps: Optional[str] = None
    salary_recommendation: Optional[str] = None
    reminder_sent: bool
    reminder_count: int
    submitted_at: Optional[datetime] = None


# JD Request and Optimization schemas
class JDRequestCreate(BaseSchema):
    """Schema for creating a JD generation request."""

    client_id: int
    project_id: Optional[int] = None
    raw_requirement: str = Field(..., min_length=10)
    input_files: Optional[list[str]] = None  # Paths to uploaded files
    additional_context: Optional[dict[str, Any]] = None
    priority: str = Field(default="normal", max_length=20)
    created_by: int


class JDRequestResponse(BaseSchema):
    """Schema for JD request response."""

    request_id: str
    status: str
    clarification_questions: Optional[list[str]] = None
    user_answers: Optional[dict[str, str]] = None
    generated_jd_id: Optional[int] = None
    created_at: datetime


class JDOptimizationSuggestion(BaseSchema):
    """Schema for JD optimization suggestion."""

    jd_id: int
    current_stats: dict[str, Any]
    suggested_changes: list[dict[str, Any]]
    reason: str
    expected_improvement: str
    auto_apply: bool = False


class JDOptimizationApply(BaseSchema):
    """Schema for applying JD optimization."""

    jd_id: int
    optimization_ids: list[int]
    apply_all: bool = False
    notes: Optional[str] = None


# Resume Processing schemas
class ResumeUpload(BaseSchema):
    """Schema for resume upload."""

    file: bytes  # Will be handled by UploadFile in FastAPI
    candidate_name: Optional[str] = None
    job_posting_id: int
    source: str = Field(default="upload")


class ResumeProcessingResult(BaseSchema):
    """Schema for resume processing result."""

    candidate_id: int
    processing_status: str
    extracted_data: dict[str, Any]
    match_scores: dict[str, float]
    ranking_position: Optional[int] = None
    recommended_action: str


# Talent Pool schemas
class TalentSearchRequest(BaseSchema):
    """Schema for talent pool search."""

    keywords: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    experience_level: Optional[WorkExperience] = None
    education_level: Optional[EducationLevel] = None
    location: Optional[str] = None
    accepts_outsourcing: Optional[bool] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    status: str = Field(default="active")
    limit: int = Field(default=20, ge=1, le=100)


class TalentSearchResponse(BaseSchema):
    """Schema for talent search response."""

    total_results: int
    page: int
    page_size: int
    results: list[CandidateResponse]
    search_time_ms: int


# RPA Communication schemas
class RPACommunicationRequest(BaseSchema):
    """Schema for RPA communication request."""

    candidate_ids: list[int]
    message_template: str
    questions: list[str]
    max_retries: int = Field(default=3, ge=1, le=10)


class RPACommunicationResponse(BaseSchema):
    """Schema for RPA communication response."""

    task_id: str
    status: str
    candidates_contacted: int
    successful_contacts: int
    failed_contacts: int
    results: list[dict[str, Any]]


# Analytics schemas
class DashboardMetrics(BaseSchema):
    """Schema for dashboard metrics."""

    period: str = Field(default="7d")  # 7d, 30d, 90d, all
    total_job_postings: int
    active_job_postings: int
    total_candidates: int
    new_candidates_this_period: int
    interviews_scheduled: int
    interviews_completed: int
    offers_extended: int
    offers_accepted: int
    average_time_to_hire_days: float
    conversion_rate: float


class RecruitmentFunnelMetrics(BaseSchema):
    """Schema for recruitment funnel metrics."""

    job_posting_id: int
    job_title: str
    total_applicants: int
    screened: int
    interviews: int
    offers: int
    hires: int
    conversion_rates: dict[str, float]


class PerformanceMetrics(BaseSchema):
    """Schema for performance metrics."""

    source_efficiency: dict[str, float]  # Source name to conversion rate
    average_screening_time_hours: float
    average_interview_time_hours: float
    jd_optimization_impact: dict[str, float]
    top_performing_sources: list[dict[str, Any]]


# Feedback Collection schemas
class FeedbackRequestCreate(BaseSchema):
    """Schema for creating feedback request."""

    interview_id: int
    interviewer_id: int
    reminder_type: str = Field(default="gentle")  # gentle, firm, urgent
    custom_message: Optional[str] = None


class FeedbackRequestResponse(BaseSchema):
    """Schema for feedback request response."""

    request_id: str
    interview_id: int
    status: str
    sent_at: datetime


# Pagination schemas
class PaginatedResponse(BaseSchema):
    """Schema for paginated response."""

    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


# Error schemas
class ErrorDetail(BaseSchema):
    """Schema for error detail."""

    field: str
    message: str


class ErrorResponse(BaseSchema):
    """Schema for error response."""

    error: str
    message: str
    details: Optional[list[ErrorDetail]] = None
    path: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
