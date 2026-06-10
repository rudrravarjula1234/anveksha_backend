"""
Agent configurations for interview preparation context generation.

Uses a workflow orchestration with two specialist agents:
1. CandidateAnalysisAgent - Analyzes all candidate data (profile, knowledge graph,
   past reviews, transcripts) and produces a structured candidate brief.
2. InterviewStrategyAgent - Takes the candidate brief + interview catalog to produce
   the final preparation guide with focus areas, probing suggestions, and time allocation.

This mirrors the feedback_agents.py pattern but is optimized for pre-interview
preparation rather than post-interview evaluation.

Ported from ``backend/lib/agent_service/context_agents.py``. Port note: config
factories accept an optional ``model_name`` (default unchanged).
"""

from typing import Any, Dict, Optional

from .feedback_agents import DEFAULT_FEEDBACK_MODEL
from .schemas import AgentConfig, OrchestrationConfig


def get_candidate_analysis_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Specialist that digests ALL candidate data into a structured brief.

    Input: Raw candidate data block (profile, knowledge nodes, past reviews,
           transcript summaries, aggregated stats).
    Output: A structured candidate brief summarizing strengths, weaknesses,
            patterns, and risk areas.
    """
    return AgentConfig(
        name="CandidateAnalysisAgent",
        model_name=model_name,
        system_message="""You are a Candidate Analysis Specialist for interview preparation.

You receive a data package about a candidate and must produce a structured CANDIDATE BRIEF.

Your analysis must cover:

1. **Skill Profile Summary**: What skills does this candidate have? What is their experience level?
   Use their profile (skills, experience_years, current_role) and knowledge graph data.

2. **Performance Patterns**: Across past interviews, identify recurring patterns.
   - Consistently strong areas (proficiency = "strong" or "demonstrated" across multiple interviews)
   - Consistently weak areas (proficiency = "weak" or "struggled")
   - Improving areas (weak in early interviews, stronger in later ones)
   - Declining areas (strong before, weak recently)

3. **Evidence-Based Insights**: For the top strengths and weaknesses, cite specific
   evidence from past transcripts, reviews, or knowledge nodes. Use actual quotes or
   summaries when available.

4. **Knowledge Gaps**: Topics from the upcoming interview that the candidate has NEVER
   been tested on. These are blind spots.

5. **Risk Areas**: Concepts where the candidate showed low confidence or struggled,
   that are relevant to the upcoming interview topics.

6. **Reviewer Feedback Trends**: What did past interviewers consistently say?
   Aggregate strengths and areas_for_improvement from reviews.

7. **Overall Readiness Assessment**: Based on all data, how prepared is this candidate
   for the specific interview they are about to take?

Output a structured analysis. Be specific, cite evidence, and prioritize insights
that are actionable for the interviewer.""",
        role="specialist",
        associated_skills=["candidate_analysis", "data_synthesis", "pattern_recognition"],
        can_use_mcp=False,
        human_input_mode="never",
    )


def get_interview_strategy_agent_config(
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> AgentConfig:
    """
    Specialist that creates the final interview strategy and preparation guide.

    Input: The candidate brief from CandidateAnalysisAgent + interview catalog details.
    Output: Structured JSON preparation guide.
    """
    return AgentConfig(
        name="InterviewStrategyAgent",
        model_name=model_name,
        system_message="""You are an Interview Strategy Specialist. You help interviewers
prepare for conducting interviews by creating actionable preparation guides.

You receive:
- A candidate analysis brief (strengths, weaknesses, patterns, evidence, gaps)
- Interview catalog details (topics, evaluation criteria, difficulty, duration)
- Suggested questions from the question bank

Your job is to create a PREPARATION GUIDE that tells the interviewer exactly what to do.

You must output ONLY valid JSON with this exact structure:
{
  "focus_areas": [
    "Specific area to focus on with reasoning (e.g., 'Deep dive into system design - candidate showed moderate proficiency but hasn't been tested on distributed systems')"
  ],
  "probing_suggestions": [
    "Specific follow-up questions or probing directions (e.g., 'If they mention using Redis for caching, ask about cache invalidation strategies - they struggled with this in a previous interview')"
  ],
  "question_strategy": "Overall approach for the interview. Should the interviewer start easy and ramp up? Focus on gaps? Test breadth vs depth? Explain why based on candidate data.",
  "candidate_specific_notes": "Key things the interviewer should know about this specific candidate. Personality patterns, communication style observed in past interviews, areas where they need encouragement vs challenge.",
  "difficulty_calibration": "Should the interviewer adjust difficulty up or down from the standard? Based on candidate's experience level and past performance. Be specific.",
  "time_allocation": {
    "topic_name": minutes_as_integer
  },
  "red_flags_to_watch": [
    "Specific behaviors or answers that should raise concerns based on past patterns"
  ],
  "positive_signals_to_look_for": [
    "Specific indicators that the candidate is performing well in their weak areas"
  ]
}

Guidelines:
- time_allocation values MUST sum to the interview duration
- focus_areas should be ordered by priority (most important first)
- probing_suggestions should reference specific candidate data when available
- If no candidate data is available, provide general best-practice guidance for the interview type
- Be concrete and actionable, not vague

Output ONLY the JSON. No markdown, no explanations.""",
        role="specialist",
        associated_skills=["interview_strategy", "question_design", "assessment_planning"],
        can_use_mcp=False,
        human_input_mode="never",
    )


def create_context_orchestration_config(
    interview_metadata: Optional[Dict[str, Any]] = None,
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> OrchestrationConfig:
    """
    Create a workflow orchestration for interview context generation.

    Step 1: CandidateAnalysisAgent processes raw candidate data into a brief.
    Step 2: InterviewStrategyAgent uses the brief + catalog to create the guide.

    This is a sequential workflow (not hierarchical) because step 2 depends on
    step 1's output.
    """
    agents = [
        get_candidate_analysis_agent_config(model_name),  # Index 0
        get_interview_strategy_agent_config(model_name),  # Index 1
    ]

    workflow_steps = [
        {
            "step_name": "candidate_analysis",
            "agent_index": 0,
            "description": "Analyze all candidate data and produce a structured brief",
            "max_turns": 3,
        },
        {
            "step_name": "interview_strategy",
            "agent_index": 1,
            "description": (
                "Create the interview preparation guide using the candidate brief "
                "and interview details"
            ),
            "max_turns": 3,
        },
    ]

    skills_being_tested = []
    if interview_metadata:
        skills_being_tested = interview_metadata.get("topics", []) + interview_metadata.get(
            "tags", []
        )

    return OrchestrationConfig(
        orchestration_type="workflow",
        agents=agents,
        workflow_steps=workflow_steps,
        max_rounds=10,
        enable_mcp_tools=False,
        human_in_loop=False,
        skills_being_tested=skills_being_tested,
        interview_id=interview_metadata.get("schedule_id") if interview_metadata else None,
        candidate_id=interview_metadata.get("candidate_id") if interview_metadata else None,
    )
