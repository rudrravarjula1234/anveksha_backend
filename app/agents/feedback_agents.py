"""
Agent configurations for interview feedback generation.

This module provides reusable agent configurations for analyzing interview
transcripts and generating structured feedback using the existing agentic framework.

Ported from ``backend/lib/agent_service/feedback_agents.py``. Port note: each
config factory now accepts an optional ``model_name`` (default unchanged:
``gemini-2.0-flash``) so the orchestration can run against whatever model is
registered in the ``ai_models`` table.
"""

from typing import Any, Dict, Optional

from .schemas import AgentConfig, OrchestrationConfig

DEFAULT_FEEDBACK_MODEL = "gemini-2.0-flash"


def get_transcript_analysis_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Create agent configuration for transcript analysis.

    Responsibility: Extract structured information from raw interview transcripts
    including questions asked, answers given, technical topics, and problem-solving approach.

    Returns:
        AgentConfig for transcript analysis specialist
    """
    return AgentConfig(
        name="TranscriptAnalysisAgent",
        model_name=model_name,
        system_message="""You are a transcript analysis specialist for technical interviews.

Your role is to analyze interview transcripts and extract structured information:

1. **Questions Asked**: List all questions the interviewer asked
2. **Candidate Responses**: Summarize key points from candidate's answers
3. **Technical Topics**: Identify all technical topics discussed (languages, frameworks, concepts)
4. **Code Snippets**: Extract any code or pseudocode mentioned
5. **Problem-Solving Approach**: Describe how the candidate approached problems

Provide your analysis in a clear, structured format. Focus on factual extraction without evaluation.
""",
        role="specialist",
        associated_skills=["transcript_analysis", "information_extraction"],
        can_use_mcp=False,
        human_input_mode="NEVER",
    )


def get_technical_evaluation_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Create agent configuration for technical evaluation.

    Responsibility: Evaluate technical competency based on transcript analysis,
    rating technical depth, accuracy, problem-solving ability, and code quality.

    Returns:
        AgentConfig for technical evaluation specialist
    """
    return AgentConfig(
        name="TechnicalEvaluationAgent",
        model_name=model_name,
        system_message="""You are a technical evaluation specialist for software engineering interviews.

Your role is to evaluate the candidate's technical competency based on the interview transcript.

Rate the following on a scale of 1-5:
1. **Technical Depth** (1=surface level, 5=expert level understanding)
2. **Accuracy** (1=many errors, 5=completely accurate)
3. **Problem-Solving** (1=struggled significantly, 5=excellent approach)
4. **Code Quality** (1=poor practices, 5=production-ready code)

For each rating, provide:
- The numeric score (1-5)
- Brief justification (2-3 sentences)
- Specific examples from the transcript

Also identify:
- **Technical Strengths**: 2-3 specific strengths with examples
- **Technical Weaknesses**: 2-3 areas for improvement with examples

Be objective and evidence-based. Reference specific parts of the transcript.
""",
        role="specialist",
        associated_skills=["technical_evaluation", "code_review", "problem_solving"],
        can_use_mcp=True,
        human_input_mode="NEVER",
    )


def get_communication_evaluation_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Create agent configuration for communication evaluation.

    Responsibility: Assess communication skills including clarity, articulation,
    confidence, and listening skills.

    Returns:
        AgentConfig for communication evaluation specialist
    """
    return AgentConfig(
        name="CommunicationEvaluationAgent",
        model_name=model_name,
        system_message="""You are a communication evaluation specialist for technical interviews.

Your role is to assess the candidate's communication skills based on the interview transcript.

Rate the following on a scale of 1-5:
1. **Clarity** (1=unclear/confusing, 5=crystal clear)
2. **Articulation** (1=struggled to express ideas, 5=well-articulated)
3. **Confidence** (1=very hesitant, 5=very confident)
4. **Active Listening** (1=missed questions, 5=excellent comprehension)

For each rating, provide:
- The numeric score (1-5)
- Brief justification (2-3 sentences)
- Specific examples from the transcript

Also identify:
- **Communication Strengths**: 2-3 specific strengths
- **Communication Weaknesses**: 2-3 areas for improvement

Consider:
- How well did they explain technical concepts?
- Did they ask clarifying questions when needed?
- Were their responses structured and coherent?
- Did they adapt their communication style appropriately?

Be objective and cite specific examples from the transcript.
""",
        role="specialist",
        associated_skills=["communication_assessment", "soft_skills"],
        can_use_mcp=False,
        human_input_mode="NEVER",
    )


def get_feedback_coordinator_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Create agent configuration for feedback coordination.

    Responsibility: Orchestrate the feedback generation workflow by delegating to
    specialist agents and synthesizing their outputs into structured feedback.

    Returns:
        AgentConfig for feedback coordinator
    """
    return AgentConfig(
        name="FeedbackCoordinator",
        model_name=model_name,
        system_message="""You are the Interview Feedback Coordinator.

Your role is to orchestrate the interview feedback generation process.

Available specialists:
- **TranscriptAnalysisAgent**: Extracts structured information from transcripts
- **TechnicalEvaluationAgent**: Evaluates technical competency
- **CommunicationEvaluationAgent**: Assesses communication skills

Your workflow:
1. Delegate transcript analysis to TranscriptAnalysisAgent
2. Delegate technical evaluation to TechnicalEvaluationAgent
3. Delegate communication evaluation to CommunicationEvaluationAgent
4. Synthesize all specialist feedback into final structured output

Final output must be in JSON format with this structure:
{
  "overall_rating": <1-5>,
  "technical_skills": <1-5>,
  "communication_skills": <1-5>,
  "problem_solving": <1-5>,
  "strengths": ["strength1", "strength2", "strength3"],
  "weaknesses": ["weakness1", "weakness2", "weakness3"],
  "overall_comment": "<comprehensive summary in 3-5 sentences>",
  "recommendation": "<hire|no_hire|maybe>",
  "detailed_analysis": {
    "transcript_summary": "<key points from transcript>",
    "technical_evaluation": "<technical assessment summary>",
    "communication_evaluation": "<communication assessment summary>",
    "key_topics_discussed": ["topic1", "topic2", "topic3"]
  }
}

Guidelines for synthesis:
- **overall_rating**: Average of technical_skills, communication_skills, and problem_solving
- **recommendation**:
  - "hire" if overall_rating >= 4
  - "no_hire" if overall_rating <= 2
  - "maybe" if overall_rating is 3
- **strengths/weaknesses**: Combine and prioritize from specialist feedback (max 3-4 each)
- **overall_comment**: Synthesize a balanced, actionable summary

Be objective, data-driven, and provide actionable insights.
""",
        role="coordinator",
        associated_skills=["orchestration", "synthesis", "decision_making"],
        can_use_mcp=True,
        human_input_mode="NEVER",
    )


def create_feedback_orchestration_config(
    interview_metadata: Optional[Dict[str, Any]] = None,
    max_rounds: int = 15,
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> OrchestrationConfig:
    """
    Create complete orchestration configuration for feedback generation.

    Uses hierarchical orchestration with a coordinator and three specialist agents.

    Args:
        interview_metadata: Optional metadata about the interview (role, experience_level, etc.)
        max_rounds: Maximum conversation rounds (default: 15)
        model_name: Model to run all agents on (default: gemini-2.0-flash)

    Returns:
        OrchestrationConfig ready for AutogenAgentService.orchestrate()
    """
    # Create all agent configurations
    agents = [
        get_feedback_coordinator_agent_config(model_name),  # Index 0: Coordinator
        get_transcript_analysis_agent_config(model_name),  # Index 1: Specialist
        get_technical_evaluation_agent_config(model_name),  # Index 2: Specialist
        get_communication_evaluation_agent_config(model_name),  # Index 3: Specialist
    ]
    # Extract skills from metadata if provided
    skills_being_tested = []
    if interview_metadata:
        tech_stack = interview_metadata.get("tech_stack", [])
        if tech_stack:
            skills_being_tested.extend(tech_stack)

    # Create orchestration config
    config = OrchestrationConfig(
        orchestration_type="hierarchical",
        agents=agents,
        coordinator_agent_index=0,  # FeedbackCoordinator is at index 0
        max_rounds=max_rounds,
        enable_mcp_tools=True,
        skills_being_tested=skills_being_tested,
        human_in_loop=False,
        interview_id=interview_metadata.get("interview_id") if interview_metadata else None,
        candidate_id=interview_metadata.get("candidate_id") if interview_metadata else None,
    )

    return config
