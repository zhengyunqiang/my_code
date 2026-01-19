"""
LangGraph Workflow Orchestration - Core Coordination Layer.
Defines and manages the complete recruitment pipeline using stateful workflows.
"""
from typing import Any, Dict, List, Optional, TypedDict, Literal

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.core.logger import get_logger
from app.services.jd_generation_service import jd_generation_service, JDRequestStatus
from app.services.resume_screening_service import resume_screening_service
from app.services.rpa_communication_service import rpa_communication_service
from app.services.feedback_optimization_service import (
    feedback_collection_service,
    jd_optimization_service,
)
from app.services.onboarding_service import onboarding_service, talent_pool_service

logger = get_logger(__name__)


# State definitions for LangGraph


class RecruitmentState(TypedDict):
    """Main state for the recruitment workflow."""

    # Request identification
    request_id: str
    phase: str  # current phase

    # Phase 1: JD Generation
    jd_request_data: Optional[Dict[str, Any]]
    jd_analysis_result: Optional[Dict[str, Any]]
    clarification_questions: Optional[List[Dict[str, Any]]]
    user_answers: Optional[Dict[str, str]]
    generated_jd_id: Optional[int]

    # Phase 2: Candidate Screening
    job_posting_id: Optional[int]
    resumes_to_process: Optional[List[Dict[str, Any]]]
    screened_candidates: Optional[List[Dict[str, Any]]]
    rpa_communication_results: Optional[Dict[str, Any]]

    # Phase 3: Interview & Feedback
    interview_ids: Optional[List[int]]
    feedback_collected: Optional[Dict[str, Any]]
    optimization_suggestions: Optional[List[Dict[str, Any]]]

    # Phase 4: Onboarding
    hired_candidates: Optional[List[Dict[str, Any]]]
    onboarding_status: Optional[Dict[str, Any]]
    talent_profile_updates: Optional[List[Dict[str, Any]]]

    # Metadata
    errors: List[str]
    messages: List[str]
    current_step: str
    completed_steps: List[str]


class JDGenerationState(TypedDict):
    """State for JD generation workflow."""

    request_id: str
    raw_requirement: str
    client_id: int
    project_id: Optional[int]
    user_answers: Dict[str, str]
    analysis_complete: bool
    clarifications_complete: bool
    generation_complete: bool
    job_posting_id: Optional[int]
    errors: List[str]


class CandidateScreeningState(TypedDict):
    """State for candidate screening workflow."""

    job_posting_id: int
    resumes_data: List[Dict[str, Any]]
    candidates_processed: int
    candidates_qualified: List[Dict[str, Any]]
    screening_complete: bool
    rpa_complete: bool
    errors: List[str]


# Workflow nodes


async def jd_analysis_node(state: RecruitmentState) -> RecruitmentState:
    """Analyze job requirement and generate clarification questions."""
    logger.info(f"JD Analysis node for request {state['request_id']}")

    try:
        # Analyze requirement
        analysis_result = await jd_generation_service.analyze_requirement(state["request_id"])

        state["jd_analysis_result"] = analysis_result
        state["clarification_questions"] = analysis_result.get("clarification_questions", [])
        state["current_step"] = "jd_analysis_complete"
        state["completed_steps"].append("jd_analysis")

    except Exception as e:
        logger.error(f"Error in JD analysis: {e}")
        state["errors"].append(f"JD analysis failed: {str(e)}")

    return state


async def jd_clarification_node(state: RecruitmentState) -> RecruitmentState:
    """Wait for user clarification answers."""
    logger.info(f"JD Clarification node for request {state['request_id']}")

    # Check if we have all required answers
    request = jd_generation_service.get_request(state["request_id"])
    if not request:
        state["errors"].append("Request not found")
        return state

    # Check if all required questions are answered
    required_answered = all(
        q.question_id in (state.get("user_answers", {}))
        for q in request.clarification_questions
        if q.is_required
    )

    if required_answered:
        state["current_step"] = "clarifications_complete"
        state["completed_steps"].append("clarifications")
    else:
        state["current_step"] = "waiting_for_clarifications"
        state["messages"].append("Waiting for user to answer clarification questions")

    return state


async def jd_generation_node(state: RecruitmentState) -> RecruitmentState:
    """Generate final JD after clarifications."""
    logger.info(f"JD Generation node for request {state['request_id']}")

    try:
        # Submit answers if provided
        if state.get("user_answers"):
            await jd_generation_service.submit_clarification_answers(
                state["request_id"],
                state["user_answers"],
            )

        # Generate JD
        job_posting = await jd_generation_service.generate_jd(state["request_id"])

        state["generated_jd_id"] = job_posting.id
        state["job_posting_id"] = job_posting.id
        state["current_step"] = "jd_generation_complete"
        state["completed_steps"].append("jd_generation")
        state["messages"].append(f"JD generated successfully: {job_posting.job_title}")

    except Exception as e:
        logger.error(f"Error in JD generation: {e}")
        state["errors"].append(f"JD generation failed: {str(e)}")

    return state


async def resume_screening_node(state: RecruitmentState) -> RecruitmentState:
    """Screen and rank candidates."""
    logger.info(f"Resume Screening node for job posting {state.get('job_posting_id')}")

    try:
        job_posting_id = state.get("job_posting_id")
        if not job_posting_id:
            state["errors"].append("No job posting ID available")
            return state

        # Process resumes
        results = []
        for resume_data in state.get("resumes_to_process", []):
            try:
                result = await resume_screening_service.process_resume(
                    resume_text=resume_data["text"],
                    job_posting_id=job_posting_id,
                    source=resume_data.get("source", "upload"),
                )
                results.append({
                    "candidate_id": result.candidate_id,
                    "match_score": result.match_scores.get("overall_score", 0),
                    "recommended_action": result.recommended_action,
                })
            except Exception as e:
                logger.error(f"Error processing resume: {e}")
                state["errors"].append(f"Resume processing error: {str(e)}")

        state["screened_candidates"] = results
        state["current_step"] = "screening_complete"
        state["completed_steps"].append("resume_screening")
        state["messages"].append(f"Screened {len(results)} candidates")

    except Exception as e:
        logger.error(f"Error in resume screening: {e}")
        state["errors"].append(f"Resume screening failed: {str(e)}")

    return state


async def rpa_communication_node(state: RecruitmentState) -> RecruitmentState:
    """Execute RPA communication with qualified candidates."""
    logger.info("RPA Communication node")

    try:
        # Get qualified candidate IDs
        qualified_ids = [
            c["candidate_id"]
            for c in state.get("screened_candidates", [])
            if c.get("recommended_action") in ["high_match", "medium_match"]
        ]

        if not qualified_ids:
            state["messages"].append("No qualified candidates for RPA outreach")
            state["current_step"] = "rpa_complete"
            return state

        job_posting_id = state.get("job_posting_id")
        if not job_posting_id:
            state["errors"].append("No job posting ID available")
            return state

        # Execute automated campaign
        results = await rpa_communication_service.automated_screening_campaign(
            candidate_ids=qualified_ids,
            job_posting_id=job_posting_id,
            message_template="您好，我们是XX公司，看到了您的简历...",
        )

        state["rpa_communication_results"] = results
        state["current_step"] = "rpa_complete"
        state["completed_steps"].append("rpa_communication")
        state["messages"].append(
            f"RPA campaign completed: {results.get('completed', 0)} contacted"
        )

    except Exception as e:
        logger.error(f"Error in RPA communication: {e}")
        state["errors"].append(f"RPA communication failed: {str(e)}")

    return state


async def feedback_collection_node(state: RecruitmentState) -> RecruitmentState:
    """Collect interview feedback."""
    logger.info("Feedback Collection node")

    try:
        # Check for pending feedbacks
        pending = await feedback_collection_service.check_pending_feedbacks(hours_threshold=2)

        reminders_sent = []
        for interview in pending:
            result = await feedback_collection_service.send_feedback_reminder(interview)
            if result.get("status") == "sent":
                reminders_sent.append(result)

        state["feedback_collected"] = {
            "pending_count": len(pending),
            "reminders_sent": len(reminders_sent),
        }

        state["current_step"] = "feedback_complete"
        state["completed_steps"].append("feedback_collection")
        state["messages"].append(f"Sent {len(reminders_sent)} feedback reminders")

    except Exception as e:
        logger.error(f"Error in feedback collection: {e}")
        state["errors"].append(f"Feedback collection failed: {str(e)}")

    return state


async def jd_optimization_node(state: RecruitmentState) -> RecruitmentState:
    """Analyze feedback and optimize JD if needed."""
    logger.info("JD Optimization node")

    try:
        job_posting_id = state.get("job_posting_id")
        if not job_posting_id:
            state["errors"].append("No job posting ID available")
            return state

        # Analyze job posting performance
        analysis = await jd_optimization_service.analyze_job_posting_performance(
            job_posting_id
        )

        state["optimization_suggestions"] = analysis.get("suggestions", [])

        # Auto-apply if trigger is critical
        if "low_success_rate" in analysis.get("triggers", []):
            state["messages"].append("Low success rate detected - JD optimization recommended")

        state["current_step"] = "optimization_complete"
        state["completed_steps"].append("jd_optimization")

    except Exception as e:
        logger.error(f"Error in JD optimization: {e}")
        state["errors"].append(f"JD optimization failed: {str(e)}")

    return state


async def onboarding_node(state: RecruitmentState) -> RecruitmentState:
    """Handle onboarding for hired candidates."""
    logger.info("Onboarding node")

    try:
        # Update onboarding progress for hired candidates
        for hired in state.get("hired_candidates", []):
            candidate_id = hired.get("candidate_id")
            job_posting_id = state.get("job_posting_id")

            if candidate_id and job_posting_id:
                # Create talent profile
                await talent_pool_service.create_talent_profile(candidate_id)

        state["current_step"] = "onboarding_complete"
        state["completed_steps"].append("onboarding")
        state["messages"].append("Onboarding workflows initiated")

    except Exception as e:
        logger.error(f"Error in onboarding: {e}")
        state["errors"].append(f"Onboarding failed: {str(e)}")

    return state


# Workflow builders


def build_jd_generation_workflow() -> StateGraph:
    """Build the JD generation workflow graph."""

    workflow = StateGraph(RecruitmentState)

    # Add nodes
    workflow.add_node("analyze_requirement", jd_analysis_node)
    workflow.add_node("collect_clarifications", jd_clarification_node)
    workflow.add_node("generate_jd", jd_generation_node)

    # Define edges
    workflow.set_entry_point("analyze_requirement")
    workflow.add_edge("analyze_requirement", "collect_clarifications")

    # Conditional edge for clarifications
    def should_generate_jd(state: RecruitmentState) -> Literal["generate_jd", "collect_clarifications"]:
        if state.get("current_step") == "clarifications_complete":
            return "generate_jd"
        return "collect_clarifications"

    workflow.add_conditional_edges(
        "collect_clarifications",
        should_generate_jd,
        {
            "generate_jd": "generate_jd",
            "collect_clarifications": "collect_clarifications",
        },
    )

    workflow.add_edge("generate_jd", END)

    return workflow.compile()


def build_candidate_screening_workflow() -> StateGraph:
    """Build the candidate screening workflow graph."""

    workflow = StateGraph(RecruitmentState)

    # Add nodes
    workflow.add_node("screen_resumes", resume_screening_node)
    workflow.add_node("rpa_communication", rpa_communication_node)

    # Define edges
    workflow.set_entry_point("screen_resumes")
    workflow.add_edge("screen_resumes", "rpa_communication")
    workflow.add_edge("rpa_communication", END)

    return workflow.compile()


def build_interview_feedback_workflow() -> StateGraph:
    """Build the interview feedback and optimization workflow graph."""

    workflow = StateGraph(RecruitmentState)

    # Add nodes
    workflow.add_node("collect_feedback", feedback_collection_node)
    workflow.add_node("optimize_jd", jd_optimization_node)

    # Define edges
    workflow.set_entry_point("collect_feedback")
    workflow.add_edge("collect_feedback", "optimize_jd")
    workflow.add_edge("optimize_jd", END)

    return workflow.compile()


def build_onboarding_workflow() -> StateGraph:
    """Build the onboarding workflow graph."""

    workflow = StateGraph(RecruitmentState)

    # Add nodes
    workflow.add_node("process_onboarding", onboarding_node)

    # Define edges
    workflow.set_entry_point("process_onboarding")
    workflow.add_edge("process_onboarding", END)

    return workflow.compile()


def build_complete_recruitment_workflow() -> StateGraph:
    """Build the complete end-to-end recruitment workflow."""

    workflow = StateGraph(RecruitmentState)

    # Add all nodes
    workflow.add_node("jd_generation", jd_generation_node)
    workflow.add_node("resume_screening", resume_screening_node)
    workflow.add_node("rpa_communication", rpa_communication_node)
    workflow.add_node("feedback_collection", feedback_collection_node)
    workflow.add_node("jd_optimization", jd_optimization_node)
    workflow.add_node("onboarding", onboarding_node)

    # Define sequential edges
    workflow.set_entry_point("jd_generation")
    workflow.add_edge("jd_generation", "resume_screening")
    workflow.add_edge("resume_screening", "rpa_communication")
    workflow.add_edge("rpa_communication", "feedback_collection")
    workflow.add_edge("feedback_collection", "jd_optimization")
    workflow.add_edge("jd_optimization", "onboarding")
    workflow.add_edge("onboarding", END)

    return workflow.compile()


# Workflow executor


class RecruitmentWorkflowExecutor:
    """Execute and manage recruitment workflows."""

    def __init__(self):
        self.jd_workflow = build_jd_generation_workflow()
        self.screening_workflow = build_candidate_screening_workflow()
        self.feedback_workflow = build_interview_feedback_workflow()
        self.onboarding_workflow = build_onboarding_workflow()
        self.complete_workflow = build_complete_recruitment_workflow()

    async def execute_jd_generation(
        self,
        initial_state: RecruitmentState,
    ) -> RecruitmentState:
        """Execute JD generation workflow."""
        logger.info(f"Starting JD generation workflow for request {initial_state['request_id']}")

        try:
            final_state = await self.jd_workflow.ainvoke(initial_state)
            logger.info(f"JD generation workflow completed: {final_state.get('current_step')}")
            return final_state

        except Exception as e:
            logger.error(f"Error executing JD generation workflow: {e}")
            initial_state["errors"].append(f"Workflow execution error: {str(e)}")
            return initial_state

    async def execute_candidate_screening(
        self,
        initial_state: RecruitmentState,
    ) -> RecruitmentState:
        """Execute candidate screening workflow."""
        logger.info("Starting candidate screening workflow")

        try:
            final_state = await self.screening_workflow.ainvoke(initial_state)
            logger.info(f"Candidate screening workflow completed: {final_state.get('current_step')}")
            return final_state

        except Exception as e:
            logger.error(f"Error executing candidate screening workflow: {e}")
            initial_state["errors"].append(f"Workflow execution error: {str(e)}")
            return initial_state

    async def execute_feedback_optimization(
        self,
        initial_state: RecruitmentState,
    ) -> RecruitmentState:
        """Execute feedback collection and JD optimization workflow."""
        logger.info("Starting feedback and optimization workflow")

        try:
            final_state = await self.feedback_workflow.ainvoke(initial_state)
            logger.info(f"Feedback workflow completed: {final_state.get('current_step')}")
            return final_state

        except Exception as e:
            logger.error(f"Error executing feedback workflow: {e}")
            initial_state["errors"].append(f"Workflow execution error: {str(e)}")
            return initial_state

    async def execute_onboarding(
        self,
        initial_state: RecruitmentState,
    ) -> RecruitmentState:
        """Execute onboarding workflow."""
        logger.info("Starting onboarding workflow")

        try:
            final_state = await self.onboarding_workflow.ainvoke(initial_state)
            logger.info(f"Onboarding workflow completed: {final_state.get('current_step')}")
            return final_state

        except Exception as e:
            logger.error(f"Error executing onboarding workflow: {e}")
            initial_state["errors"].append(f"Workflow execution error: {str(e)}")
            return initial_state

    async def execute_complete_workflow(
        self,
        initial_state: RecruitmentState,
    ) -> RecruitmentState:
        """Execute complete recruitment workflow."""
        logger.info("Starting complete recruitment workflow")

        try:
            final_state = await self.complete_workflow.ainvoke(initial_state)
            logger.info(f"Complete workflow finished: {final_state.get('current_step')}")
            return final_state

        except Exception as e:
            logger.error(f"Error executing complete workflow: {e}")
            initial_state["errors"].append(f"Workflow execution error: {str(e)}")
            return initial_state


# Global workflow executor instance
workflow_executor = RecruitmentWorkflowExecutor()
