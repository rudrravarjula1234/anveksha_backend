"""
Service layer for interview feedback generation.

Orchestrates the agent service to generate structured feedback from interview
transcripts.

Ported from ``backend/services/interview_feedback_service.py``. Differences:

- ``initialize_agent_service`` can return ``None`` (AutoGen not installed);
  both entrypoints raise a clear 503-mapped error in that case.
- The legacy code hardcoded ``model_name="gemini-2.0-flash"``. The port keeps
  that default but resolves against the models registered in the ``ai_models``
  collection: when the preferred model is not registered, the first active
  model in the cache is used instead (see ``_resolve_model_name``).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.agents.autogen_compat import require_autogen
from app.agents.exceptions import (
    AgentFrameworkNotInstalledError,
    ModelConfigNotFoundError,
)
from app.agents.feedback_agents import (
    DEFAULT_FEEDBACK_MODEL,
    create_feedback_orchestration_config,
)
from app.agents.startup import initialize_agent_service

logger = logging.getLogger(__name__)


def _resolve_model_name(service, preferred: str = DEFAULT_FEEDBACK_MODEL) -> str:
    """Pick the model to use: the preferred one when registered, otherwise the
    first active model loaded from the ``ai_models`` collection."""
    if service.config.model_cache.get(preferred):
        return preferred
    available = list(service.config.model_cache.configs.keys())
    if not available:
        raise ModelConfigNotFoundError(
            "No active models registered in the ai_models collection. "
            "Create one via POST /api/admin/models before generating feedback."
        )
    fallback = available[0]
    logger.info(
        "Preferred model '%s' not registered; falling back to '%s'", preferred, fallback
    )
    return fallback


async def generate_feedback_direct(
    transcript: str,
    metadata: Optional[Dict[str, Any]] = None,
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> Dict[str, Any]:
    """
    Generate feedback using single direct API call (no multi-agent orchestration).

    This approach is faster, more reliable, and avoids rate limits.

    Args:
        transcript: Raw interview transcript text
        metadata: Optional interview metadata
        model_name: Preferred model (falls back to first registered active model)

    Returns:
        Dict containing feedback and metadata

    Raises:
        ValueError: If transcript is invalid or JSON parsing fails
        Exception: If feedback generation fails
    """
    start_time = datetime.now(timezone.utc)

    # Validate transcript
    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty")

    logger.info(f"Generating feedback (direct mode) for transcript ({len(transcript)} chars)")
    if metadata:
        logger.info(f"Metadata: {metadata}")

    # Initialize agent service (raises a clear 503 error when AutoGen missing)
    require_autogen()
    service = await initialize_agent_service()
    if service is None:  # defensive — only possible when AutoGen is missing
        raise AgentFrameworkNotInstalledError("Agent service could not be initialized")

    try:
        model_name = _resolve_model_name(service, model_name)

        # Build comprehensive prompt
        context_parts = []
        if metadata:
            if metadata.get("role"):
                context_parts.append(f"Position: {metadata['role']}")
            if metadata.get("experience_level"):
                context_parts.append(f"Experience Level: {metadata['experience_level']}")
            if metadata.get("tech_stack"):
                context_parts.append(f"Tech Stack: {', '.join(metadata['tech_stack'])}")
            if metadata.get("interview_type"):
                context_parts.append(f"Interview Type: {metadata['interview_type']}")

        context_str = "\n".join(context_parts) if context_parts else "No additional context provided"

        prompt = f"""Analyze this technical interview transcript and generate structured feedback.

INTERVIEW CONTEXT:
{context_str}

TRANSCRIPT:
{transcript}

INSTRUCTIONS:
1. Carefully read the entire transcript
2. Evaluate technical skills, communication, and problem-solving
3. Identify specific strengths and weaknesses with examples from the transcript
4. Analyze skill gaps based on the role requirements and expected level
5. Provide ratings on a scale of 1.0-5.0 (use decimals for precision)
6. Output ONLY valid JSON with the exact structure below

REQUIRED JSON OUTPUT:
{{
  "overall_rating": <float 1.0-5.0>,
  "technical_skills": <float 1.0-5.0>,
  "communication_skills": <float 1.0-5.0>,
  "problem_solving": <float 1.0-5.0>,
  "strengths": ["specific strength with example", "another strength", "..."],
  "weaknesses": ["specific weakness with example", "another weakness"],
  "overall_comment": "Comprehensive 3-5 sentence summary of candidate performance",
  "recommendation": "hire|no_hire|maybe",
  "detailed_analysis": {{
    "transcript_summary": "Key points and topics discussed in the interview",
    "technical_evaluation": "Detailed technical assessment with specific examples from transcript",
    "communication_evaluation": "Detailed communication assessment with specific examples",
    "key_topics_discussed": ["topic1", "topic2", "topic3", "..."],
    "gap_analysis": "Analysis of skill gaps based on role requirements. Identify missing skills, areas needing improvement, and provide specific, actionable recommendations."
  }}
}}

RATING SCALE:
- 5.0: Exceptional, far exceeds expectations
- 4.0-4.9: Strong, exceeds expectations
- 3.0-3.9: Good, meets expectations
- 2.0-2.9: Below expectations
- 1.0-1.9: Poor, significant gaps

RECOMMENDATION GUIDELINES:
- "hire": overall_rating >= 4.0 AND no critical weaknesses
- "no_hire": overall_rating <= 2.5 OR critical gaps found
- "maybe": overall_rating 2.6-3.9 OR mixed performance

Output ONLY the JSON object. No markdown code blocks, no explanations, no extra text."""

        # Make direct API call
        logger.info("Making direct API call to generate feedback")
        result = await service.direct_call(
            model_name=model_name,
            user_input=prompt,
            track_usage=True,
        )

        # Parse JSON from response
        response_text = result["response"]
        logger.info(f"Direct call response length: {len(response_text)} chars")
        logger.info(f"Response preview: {response_text[:200]}...")

        # Extract JSON (try multiple strategies)
        feedback_json = None

        # Strategy 1: Look for JSON in code blocks
        code_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response_text)
        if code_block_match:
            try:
                feedback_json = json.loads(code_block_match.group(1))
                logger.info("Extracted JSON from code block")
            except json.JSONDecodeError:
                pass

        # Strategy 2: Find JSON object
        if not feedback_json:
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                try:
                    feedback_json = json.loads(json_match.group(0))
                    logger.info("Extracted JSON from response")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing failed: {e}")
                    logger.error(f"Attempted to parse: {json_match.group(0)[:500]}...")
                    raise ValueError(f"Invalid JSON in model response: {e}")

        if not feedback_json:
            raise ValueError("No valid JSON found in model response")

        # Validate required fields
        required_fields = [
            "overall_rating",
            "technical_skills",
            "communication_skills",
            "problem_solving",
            "strengths",
            "weaknesses",
            "overall_comment",
            "recommendation",
            "detailed_analysis",
        ]
        missing_fields = [f for f in required_fields if f not in feedback_json]
        if missing_fields:
            raise ValueError(f"Missing required fields in feedback: {missing_fields}")

        # Calculate duration
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        # Build response
        response = {
            "feedback": feedback_json,
            "metadata": {
                "interview_type": metadata.get("interview_type") if metadata else None,
                "role": metadata.get("role") if metadata else None,
                "duration_ms": duration_ms,
                "token_usage": result.get("token_usage"),
                "model_used": model_name,
            },
        }

        logger.info("Direct feedback generation completed successfully")
        return response

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from response: {e}")
        raise ValueError(f"Invalid JSON in model response: {e}")
    except Exception as e:
        logger.error(f"Error generating feedback: {str(e)}", exc_info=True)
        raise
    finally:
        await service.shutdown()


async def generate_feedback_from_transcript(
    transcript: str,
    metadata: Optional[Dict[str, Any]] = None,
    model_name: str = DEFAULT_FEEDBACK_MODEL,
) -> Dict[str, Any]:
    """
    Generate structured interview feedback from a transcript.

    Uses the full hierarchical multi-agent orchestration (coordinator + three
    specialists). Slower than :func:`generate_feedback_direct` and more prone
    to rate limits, but exercises the complete agentic pipeline.

    Args:
        transcript: Raw interview transcript text
        metadata: Optional interview metadata (role, experience_level, tech_stack, etc.)
        model_name: Preferred model (falls back to first registered active model)

    Returns:
        Dict containing feedback and metadata

    Raises:
        ValueError: If transcript is invalid
        Exception: If agent orchestration fails
    """
    start_time = datetime.now(timezone.utc)
    # Validate transcript
    if not transcript or not transcript.strip():
        raise ValueError("Transcript cannot be empty")

    logger.info(f"Generating feedback for transcript ({len(transcript)} chars)")
    if metadata:
        logger.info(f"Metadata: {metadata}")

    # Initialize agent service (raises a clear 503 error when AutoGen missing)
    require_autogen()
    service = await initialize_agent_service()
    if service is None:  # defensive — only possible when AutoGen is missing
        raise AgentFrameworkNotInstalledError("Agent service could not be initialized")

    try:
        model_name = _resolve_model_name(service, model_name)

        # Create orchestration config
        orchestration_config = create_feedback_orchestration_config(
            interview_metadata=metadata,
            max_rounds=5,  # Reduced from 15 to avoid rate limits (max_messages = 10 instead of 30)
            model_name=model_name,
        )

        # Prepare user input with metadata context
        user_input = _prepare_user_input(transcript, metadata)

        # Run orchestration
        logger.info("Starting agent orchestration for feedback generation")
        result = await service.orchestrate(
            config=orchestration_config,
            user_input=user_input,
            track_usage=True,
        )

        logger.info(f"Orchestration completed in {result.get('duration_ms', 0)}ms")

        # Log the raw agent response for debugging
        raw_response = result.get("final_response", "")
        logger.info(f"Raw agent response length: {len(raw_response)} chars")
        logger.info(f"Raw agent response preview: {raw_response[:500]}...")

        # Parse agent response to structured feedback
        feedback_data = parse_agent_response_to_feedback(
            raw_response,
            metadata,
        )

        # Validate feedback completeness
        if not validate_feedback_completeness(feedback_data):
            logger.warning("Feedback incomplete, using fallback values")
            feedback_data = _apply_fallback_values(feedback_data)

        # Calculate duration
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        # Build response
        response = {
            "feedback": feedback_data,
            "metadata": {
                "interview_type": metadata.get("interview_type") if metadata else None,
                "role": metadata.get("role") if metadata else None,
                "duration_ms": duration_ms,
                "token_usage": result.get("token_usage"),
                "model_used": model_name,
            },
        }

        logger.info("Feedback generation completed successfully")
        return response

    except Exception as e:
        logger.error(f"Error generating feedback: {str(e)}", exc_info=True)
        raise
    finally:
        await service.shutdown()


def _prepare_user_input(transcript: str, metadata: Optional[Dict[str, Any]]) -> str:
    """
    Prepare user input for agent orchestration with context.

    Args:
        transcript: Raw interview transcript
        metadata: Optional interview metadata

    Returns:
        Formatted user input string
    """
    context_parts = []

    if metadata:
        if metadata.get("role"):
            context_parts.append(f"Position: {metadata['role']}")
        if metadata.get("experience_level"):
            context_parts.append(f"Experience Level: {metadata['experience_level']}")
        if metadata.get("tech_stack"):
            context_parts.append(f"Tech Stack: {', '.join(metadata['tech_stack'])}")
        if metadata.get("interview_type"):
            context_parts.append(f"Interview Type: {metadata['interview_type']}")

    if context_parts:
        context = "\n".join(context_parts)
        user_input = f"""Interview Context:
{context}

Interview Transcript:
{transcript}

Please analyze this interview transcript and generate structured feedback."""
    else:
        user_input = f"""Interview Transcript:
{transcript}

Please analyze this interview transcript and generate structured feedback."""

    return user_input


def parse_agent_response_to_feedback(
    agent_output: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Parse agent response into structured feedback data.

    Attempts to extract JSON from the agent's response. If JSON parsing fails,
    falls back to pattern matching and extraction.

    Args:
        agent_output: Raw output from the coordinator agent
        metadata: Optional metadata for context

    Returns:
        Dict with structured feedback data
    """
    logger.info("Parsing agent response to structured feedback")

    # Try to extract JSON from the response
    json_match = re.search(r"\{[\s\S]*\}", agent_output)
    if json_match:
        try:
            feedback_json = json.loads(json_match.group(0))
            logger.info("Successfully parsed JSON from agent response")
            return feedback_json
        except json.JSONDecodeError:
            logger.warning("JSON parsing failed, attempting pattern extraction")

    # Fallback: Extract structured data using patterns
    feedback = _extract_feedback_from_text(agent_output)

    return feedback


def _extract_feedback_from_text(text: str) -> Dict[str, Any]:
    """
    Extract feedback data from unstructured text using pattern matching.

    Args:
        text: Agent response text

    Returns:
        Dict with extracted feedback data
    """
    feedback = {
        "overall_rating": 3.0,
        "technical_skills": 3.0,
        "communication_skills": 3.0,
        "problem_solving": 3.0,
        "strengths": [],
        "weaknesses": [],
        "overall_comment": "",
        "recommendation": "maybe",
        "detailed_analysis": {
            "transcript_summary": "",
            "technical_evaluation": "",
            "communication_evaluation": "",
            "key_topics_discussed": [],
        },
    }

    # Extract ratings (look for patterns like "rating: 4" or "score: 4/5")
    rating_patterns = [
        r"overall[_\s]rating[:\s]+([\d.]+)",
        r"technical[_\s]skills[:\s]+([\d.]+)",
        r"communication[_\s]skills[:\s]+([\d.]+)",
        r"problem[_\s]solving[:\s]+([\d.]+)",
    ]

    for i, pattern in enumerate(rating_patterns):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                rating = float(match.group(1))
                if 1.0 <= rating <= 5.0:
                    if i == 0:
                        feedback["overall_rating"] = rating
                    elif i == 1:
                        feedback["technical_skills"] = rating
                    elif i == 2:
                        feedback["communication_skills"] = rating
                    elif i == 3:
                        feedback["problem_solving"] = rating
            except ValueError:
                pass

    # Extract recommendation
    if re.search(r"\bhire\b", text, re.IGNORECASE) and not re.search(
        r"\bno[_\s]hire\b", text, re.IGNORECASE
    ):
        feedback["recommendation"] = "hire"
    elif re.search(r"\bno[_\s]hire\b", text, re.IGNORECASE):
        feedback["recommendation"] = "no_hire"

    # Extract strengths and weaknesses
    strengths_match = re.search(
        r"strengths?[:\s]+(.*?)(?:weaknesses?|$)", text, re.IGNORECASE | re.DOTALL
    )
    if strengths_match:
        strengths_text = strengths_match.group(1)
        feedback["strengths"] = [
            s.strip("- ").strip()
            for s in strengths_text.split("\n")
            if s.strip() and len(s.strip()) > 10
        ][:4]

    weaknesses_match = re.search(
        r"weaknesses?[:\s]+(.*?)(?:overall|recommendation|$)", text, re.IGNORECASE | re.DOTALL
    )
    if weaknesses_match:
        weaknesses_text = weaknesses_match.group(1)
        feedback["weaknesses"] = [
            w.strip("- ").strip()
            for w in weaknesses_text.split("\n")
            if w.strip() and len(w.strip()) > 10
        ][:4]

    # Use first substantial paragraph as overall comment if not found
    if not feedback["overall_comment"]:
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        if paragraphs:
            feedback["overall_comment"] = paragraphs[0][:500]

    # Extract detailed analysis sections
    feedback["detailed_analysis"]["transcript_summary"] = text[:300] + "..."
    feedback["detailed_analysis"]["technical_evaluation"] = (
        f"Technical skills rated {feedback['technical_skills']}/5"
    )
    feedback["detailed_analysis"]["communication_evaluation"] = (
        f"Communication skills rated {feedback['communication_skills']}/5"
    )

    return feedback


def validate_feedback_completeness(feedback: Dict[str, Any]) -> bool:
    """
    Validate that feedback contains all required fields.

    Args:
        feedback: Feedback data dict

    Returns:
        True if feedback is complete, False otherwise
    """
    required_fields = [
        "overall_rating",
        "technical_skills",
        "communication_skills",
        "problem_solving",
        "strengths",
        "weaknesses",
        "overall_comment",
        "recommendation",
        "detailed_analysis",
    ]

    for field in required_fields:
        if field not in feedback:
            logger.warning(f"Missing required field: {field}")
            return False

        # Check for empty lists/strings
        if field in ["strengths", "weaknesses"] and not feedback[field]:
            logger.warning(f"Empty list for field: {field}")
            return False

        if field == "overall_comment" and not feedback[field]:
            logger.warning("Empty overall_comment")
            return False

    # Validate detailed_analysis structure
    if "detailed_analysis" in feedback:
        required_analysis_fields = [
            "transcript_summary",
            "technical_evaluation",
            "communication_evaluation",
            "key_topics_discussed",
        ]
        for field in required_analysis_fields:
            if field not in feedback["detailed_analysis"]:
                logger.warning(f"Missing detailed_analysis field: {field}")
                return False

    return True


def _apply_fallback_values(feedback: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply fallback values for missing or incomplete feedback fields.

    Args:
        feedback: Partial feedback data

    Returns:
        Feedback with fallback values applied
    """
    defaults = {
        "overall_rating": 3.0,
        "technical_skills": 3.0,
        "communication_skills": 3.0,
        "problem_solving": 3.0,
        "strengths": ["Unable to extract specific strengths from analysis"],
        "weaknesses": ["Unable to extract specific weaknesses from analysis"],
        "overall_comment": (
            "Feedback generation completed with limited detail. Please review the "
            "transcript manually for comprehensive evaluation."
        ),
        "recommendation": "maybe",
        "detailed_analysis": {
            "transcript_summary": "Analysis summary not available",
            "technical_evaluation": "Technical evaluation not available",
            "communication_evaluation": "Communication evaluation not available",
            "key_topics_discussed": [],
        },
    }

    # Merge defaults with existing feedback
    for key, value in defaults.items():
        if key not in feedback or not feedback[key]:
            feedback[key] = value
        elif key == "detailed_analysis" and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key not in feedback[key] or not feedback[key][sub_key]:
                    feedback[key][sub_key] = sub_value

    return feedback
