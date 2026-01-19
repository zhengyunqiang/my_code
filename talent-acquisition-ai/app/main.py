"""
Main FastAPI application for Talent Acquisition AI System.
Provides REST API endpoints for all recruitment workflows.
"""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, status, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, db_manager
from app.core.logger import get_logger, setup_logging
from app.models.schemas import (
    JDRequestCreate,
    JDRequestResponse,
    JobPostingCreate,
    JobPostingResponse,
    JobPostingUpdate,
    CandidateCreate,
    CandidateResponse,
    CandidateUpdate,
    InterviewCreate,
    InterviewResponse,
    InterviewFeedbackCreate,
    InterviewFeedbackResponse,
    TalentSearchRequest,
    TalentSearchResponse,
    ErrorDetail,
    ErrorResponse,
)
from app.services.jd_generation_service import jd_generation_service
from app.services.resume_screening_service import resume_screening_service
from app.services.resume_formatter_service import resume_formatter_service
from app.services.rpa_communication_service import rpa_communication_service
from app.services.feedback_optimization_service import (
    feedback_collection_service,
    jd_optimization_service,
)
from app.services.onboarding_service import (
    onboarding_service,
    talent_pool_service,
)
from app.workflows.recruitment_graph import workflow_executor, RecruitmentState

settings = get_settings()
logger = get_logger(__name__)

# Setup logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Talent Acquisition AI System...")

    # Initialize database
    try:
        if await db_manager.health_check():
            logger.info("Database connection healthy")
        else:
            logger.warning("Database health check failed")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

    # Initialize RAG service
    try:
        from app.services.rag_service import rag_service
        await rag_service.initialize()
        logger.info("RAG service initialized")
    except Exception as e:
        logger.error(f"RAG service initialization error: {e}")

    yield

    # Cleanup
    logger.info("Shutting down Talent Acquisition AI System...")
    await db_manager.close()
    await rpa_communication_service.close_browser()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-Powered Talent Acquisition System with LangGraph Orchestration",
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "message": str(exc.detail),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# Health check endpoints


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    db_healthy = await db_manager.health_check()

    return {
        "status": "healthy" if db_healthy else "degraded",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": "healthy" if db_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "AI-Powered Talent Acquisition System",
        "documentation": "/api/docs",
        "health": "/health",
    }


# Phase 1: JD Generation endpoints


@app.post("/api/v1/jd/requests", response_model=JDRequestResponse, tags=["JD Generation"])
async def create_jd_request(request_data: JDRequestCreate):
    """Create a new JD generation request."""
    try:
        response = await jd_generation_service.create_request(request_data)
        return response
    except Exception as e:
        logger.error(f"Error creating JD request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create JD request: {str(e)}",
        )


@app.get("/api/v1/jd/requests/{request_id}/analyze", tags=["JD Generation"])
async def analyze_jd_request(request_id: str):
    """Analyze JD requirement and get clarification questions."""
    try:
        analysis = await jd_generation_service.analyze_requirement(request_id)
        return analysis
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing JD request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze requirement: {str(e)}",
        )


@app.post("/api/v1/jd/requests/{request_id}/clarify", response_model=JDRequestResponse, tags=["JD Generation"])
async def submit_clarifications(request_id: str, answers: dict[str, str]):
    """Submit answers to clarification questions."""
    try:
        response = await jd_generation_service.submit_clarification_answers(request_id, answers)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error submitting clarifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit clarifications: {str(e)}",
        )


@app.post("/api/v1/jd/requests/{request_id}/generate", response_model=JobPostingResponse, tags=["JD Generation"])
async def generate_jd(request_id: str):
    """Generate final JD after clarifications."""
    try:
        job_posting = await jd_generation_service.generate_jd(request_id)
        return JobPostingResponse.model_validate(job_posting)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating JD: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate JD: {str(e)}",
        )


# Phase 2: Candidate Screening endpoints


@app.post("/api/v1/resumes/upload", tags=["Candidate Screening"])
async def upload_and_process_resume(
    file: UploadFile = File(...),
    job_posting_id: int = None,
    session: AsyncSession = Depends(get_db),
):
    """Upload and process a resume file."""
    try:
        # Save uploaded file
        import aiofiles
        from pathlib import Path

        upload_path = settings.upload_dir / f"{datetime.utcnow().timestamp()}_{file.filename}"
        upload_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(upload_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        # Extract and process
        result = await resume_formatter_service.process_resume_file(
            str(upload_path),
            protect_privacy=True,
            format_to_word=True,
        )

        # Screen against job posting
        if job_posting_id:
            screening_result = await resume_screening_service.process_resume(
                resume_text=result["redacted_text"],
                job_posting_id=job_posting_id,
                file_path=str(upload_path),
                session=session,
            )
            return {
                "formatting_result": result,
                "screening_result": {
                    "candidate_id": screening_result.candidate_id,
                    "match_scores": screening_result.match_scores,
                    "recommended_action": screening_result.recommended_action,
                },
            }

        return result

    except Exception as e:
        logger.error(f"Error processing resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process resume: {str(e)}",
        )


@app.post("/api/v1/screening/batch", tags=["Candidate Screening"])
async def batch_screen_resumes(
    job_posting_id: int,
    resume_data: list[dict[str, Any]],
    session: AsyncSession = Depends(get_db),
):
    """Batch screen multiple resumes."""
    try:
        results = await resume_screening_service.batch_screen_resumes(
            resume_data_list=resume_data,
            job_posting_id=job_posting_id,
            session=session,
        )
        return {"results": results, "processed": len(results)}
    except Exception as e:
        logger.error(f"Error in batch screening: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch screening failed: {str(e)}",
        )


@app.get("/api/v1/jobs/{job_id}/candidates", tags=["Candidate Screening"])
async def get_ranked_candidates(
    job_id: int,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
):
    """Get ranked candidates for a job posting."""
    try:
        candidates = await resume_screening_service.rank_candidates(
            job_posting_id=job_id,
            limit=limit,
            session=session,
        )
        return {
            "job_posting_id": job_id,
            "candidates": [CandidateResponse.model_validate(c) for c in candidates],
            "count": len(candidates),
        }
    except Exception as e:
        logger.error(f"Error getting ranked candidates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get candidates: {str(e)}",
        )


@app.post("/api/v1/rpa/campaign", tags=["RPA Communication"])
async def start_rpa_campaign(
    candidate_ids: list[int],
    job_posting_id: int,
    message_template: str,
    session: AsyncSession = Depends(get_db),
):
    """Start automated RPA communication campaign."""
    try:
        results = await rpa_communication_service.automated_screening_campaign(
            candidate_ids=candidate_ids,
            job_posting_id=job_posting_id,
            message_template=message_template,
            session=session,
        )
        return results
    except Exception as e:
        logger.error(f"Error in RPA campaign: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RPA campaign failed: {str(e)}",
        )


# Phase 3: Interview Feedback endpoints


@app.get("/api/v1/interviews/pending-feedback", tags=["Interview Feedback"])
async def get_pending_feedbacks(
    hours_threshold: int = 2,
    session: AsyncSession = Depends(get_db),
):
    """Get interviews pending feedback."""
    try:
        pending = await feedback_collection_service.check_pending_feedbacks(
            hours_threshold=hours_threshold,
            session=session,
        )
        return {
            "pending_count": len(pending),
            "interviews": [
                {
                    "id": i.id,
                    "candidate_id": i.candidate_id,
                    "scheduled_time": i.scheduled_time,
                    "round": i.round,
                }
                for i in pending
            ],
        }
    except Exception as e:
        logger.error(f"Error getting pending feedbacks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending feedbacks: {str(e)}",
        )


@app.post("/api/v1/interviews/{interview_id}/feedback", response_model=InterviewFeedbackResponse, tags=["Interview Feedback"])
async def submit_interview_feedback(
    interview_id: int,
    feedback_data: InterviewFeedbackCreate,
    session: AsyncSession = Depends(get_db),
):
    """Submit interview feedback."""
    try:
        feedback = await feedback_collection_service.submit_feedback(feedback_data, session)
        return InterviewFeedbackResponse.model_validate(feedback)
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}",
        )


@app.get("/api/v1/jobs/{job_id}/optimization", tags=["Interview Feedback"])
async def analyze_job_optimization(
    job_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Analyze job posting and get optimization suggestions."""
    try:
        analysis = await jd_optimization_service.analyze_job_posting_performance(
            job_posting_id=job_id,
            session=session,
        )
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing optimization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze optimization: {str(e)}",
        )


@app.post("/api/v1/jobs/{job_id}/optimization/apply", tags=["Interview Feedback"])
async def apply_jd_optimization(
    job_id: int,
    optimization_ids: list[int],
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):
    """Apply selected optimizations to a job posting."""
    try:
        optimization_log = await jd_optimization_service.apply_jd_optimization(
            job_posting_id=job_id,
            optimization_ids=optimization_ids,
            notes=notes,
            session=session,
        )
        return {"optimization_applied": True, "log_id": optimization_log.id}
    except Exception as e:
        logger.error(f"Error applying optimization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply optimization: {str(e)}",
        )


# Phase 4: Onboarding and Talent Pool endpoints


@app.get("/api/v1/onboarding/dashboard", tags=["Onboarding"])
async def get_onboarding_dashboard(session: AsyncSession = Depends(get_db)):
    """Get onboarding dashboard data."""
    try:
        dashboard = await onboarding_service.get_onboarding_dashboard(session)
        return dashboard
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard: {str(e)}",
        )


@app.post("/api/v1/talent/search", response_model=TalentSearchResponse, tags=["Talent Pool"])
async def search_talent_pool(
    search_request: TalentSearchRequest,
    session: AsyncSession = Depends(get_db),
):
    """Search talent pool with filters."""
    try:
        profiles = await talent_pool_service.search_talent_pool(
            keywords=search_request.keywords,
            skills=search_request.skills,
            experience_level=search_request.experience_level,
            education_level=search_request.education_level,
            accepts_outsourcing=search_request.accepts_outsourcing,
            salary_min=search_request.salary_min,
            salary_max=search_request.salary_max,
            status=search_request.status,
            limit=search_request.limit,
            session=session,
        )

        # Get candidate details for profiles
        from app.models.database import Candidate
        candidates = []
        for profile in profiles:
            candidate = await session.get(Candidate, profile.candidate_id)
            if candidate:
                candidates.append(CandidateResponse.model_validate(candidate))

        return TalentSearchResponse(
            total_results=len(candidates),
            page=1,
            page_size=search_request.limit,
            results=candidates,
            search_time_ms=0,  # Would calculate actual time
        )
    except Exception as e:
        logger.error(f"Error searching talent pool: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Talent search failed: {str(e)}",
        )


@app.get("/api/v1/jobs/{job_id}/recommendations", tags=["Talent Pool"])
async def get_talent_recommendations(
    job_id: int,
    limit: int = 10,
    session: AsyncSession = Depends(get_db),
):
    """Get talent recommendations for a job posting."""
    try:
        recommendations = await talent_pool_service.recommend_talent_for_job(
            job_posting_id=job_id,
            limit=limit,
            session=session,
        )
        return recommendations
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}",
        )


# Workflow endpoints


@app.post("/api/v1/workflows/jd-generation", tags=["Workflows"])
async def execute_jd_generation_workflow(request_data: JDRequestCreate):
    """Execute complete JD generation workflow."""
    try:
        # Create request
        request_response = await jd_generation_service.create_request(request_data)
        request_id = request_response.request_id

        # Initialize workflow state
        initial_state: RecruitmentState = {
            "request_id": request_id,
            "phase": "jd_generation",
            "jd_request_data": request_data.model_dump(),
            "jd_analysis_result": None,
            "clarification_questions": None,
            "user_answers": {},
            "generated_jd_id": None,
            "job_posting_id": None,
            "resumes_to_process": None,
            "screened_candidates": None,
            "rpa_communication_results": None,
            "interview_ids": None,
            "feedback_collected": None,
            "optimization_suggestions": None,
            "hired_candidates": None,
            "onboarding_status": None,
            "talent_profile_updates": None,
            "errors": [],
            "messages": [],
            "current_step": "initiated",
            "completed_steps": [],
        }

        # Execute workflow
        final_state = await workflow_executor.execute_jd_generation(initial_state)

        return {
            "request_id": request_id,
            "status": "completed" if not final_state["errors"] else "failed",
            "state": final_state,
        }

    except Exception as e:
        logger.error(f"Error executing JD generation workflow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers if not settings.is_development else 1,
        reload=settings.is_development,
    )
