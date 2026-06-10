"""
MCP Server for Interview Feedback Generation.

Provides MCP-compliant endpoint for generating structured interview feedback
from transcripts using the existing agentic framework.

Ported from ``backend/lib/agent_service/mcp/mcp_interview_feedback.py``;
``services.interview_feedback_service`` is now :mod:`app.agents.feedback_service`.
"""

import logging
from typing import Any, Dict, Optional

from app.agents.feedback_service import generate_feedback_direct

logger = logging.getLogger(__name__)


async def generate_interview_feedback(
    transcript: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    MCP endpoint for generating interview feedback.

    This is the main entry point for the MCP server. It validates inputs,
    orchestrates the agent service, and returns structured feedback.

    Args:
        transcript: Raw interview transcript text
        metadata: Optional interview metadata dict with keys:
            - role: str (job role)
            - experience_level: str (junior|mid-level|senior|staff|principal)
            - tech_stack: List[str] (technologies being evaluated)
            - interview_type: str (coding|system_design|behavioral|mixed)
            - interview_id: str (for tracking)
            - candidate_id: str (for tracking)

    Returns:
        Dict with structure:
        {
            "feedback": {
                "overall_rating": int (1-5),
                "technical_skills": int (1-5),
                "communication_skills": int (1-5),
                "problem_solving": int (1-5),
                "strengths": List[str],
                "weaknesses": List[str],
                "overall_comment": str,
                "recommendation": str (hire|no_hire|maybe),
                "detailed_analysis": {
                    "transcript_summary": str,
                    "technical_evaluation": str,
                    "communication_evaluation": str,
                    "key_topics_discussed": List[str]
                }
            },
            "metadata": {
                "interview_type": str,
                "role": str,
                "duration_ms": int,
                "token_usage": dict,
                "model_used": str
            }
        }

    Raises:
        ValueError: If transcript is invalid
        Exception: If feedback generation fails
    """
    logger.info("MCP endpoint: generate_interview_feedback called")
    # Validate transcript input
    if not validate_transcript_input(transcript):
        raise ValueError("Invalid transcript: must be non-empty string")

    # Validate and normalize metadata
    validated_metadata = validate_metadata(metadata or {})

    # Generate feedback using direct API call (faster, avoids rate limits)
    result = await generate_feedback_direct(
        transcript=transcript,
        metadata=validated_metadata,
    )
    # Format output
    formatted_result = format_feedback_output(result)

    logger.info("MCP endpoint: feedback generation completed successfully")
    return formatted_result


def validate_transcript_input(transcript: str) -> bool:
    """
    Validate transcript input.

    Args:
        transcript: Raw transcript text

    Returns:
        True if valid, False otherwise
    """
    if not transcript:
        logger.warning("Transcript validation failed: empty transcript")
        return False

    if not isinstance(transcript, str):
        logger.warning(f"Transcript validation failed: invalid type {type(transcript)}")
        return False

    if not transcript.strip():
        logger.warning("Transcript validation failed: whitespace only")
        return False

    if len(transcript.strip()) < 10:
        logger.warning(f"Transcript validation failed: too short ({len(transcript)} chars)")
        return False

    return True


def validate_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize interview metadata.

    Applies defaults for missing fields and validates field values.

    Args:
        metadata: Raw metadata dict

    Returns:
        Validated and normalized metadata dict
    """
    validated = {}

    # Role (optional, no default)
    if "role" in metadata and metadata["role"]:
        validated["role"] = str(metadata["role"])

    # Experience level (optional, with validation)
    if "experience_level" in metadata and metadata["experience_level"]:
        level = metadata["experience_level"].lower()
        valid_levels = ["junior", "mid-level", "senior", "staff", "principal"]
        if level in valid_levels:
            validated["experience_level"] = level
        else:
            logger.warning(f"Invalid experience_level '{level}', ignoring")

    # Tech stack (optional, defaults to empty list)
    if "tech_stack" in metadata:
        if isinstance(metadata["tech_stack"], list):
            validated["tech_stack"] = [str(t) for t in metadata["tech_stack"] if t]
        else:
            logger.warning("tech_stack must be a list, ignoring")
            validated["tech_stack"] = []
    else:
        validated["tech_stack"] = []

    # Interview type (optional, with validation)
    if "interview_type" in metadata and metadata["interview_type"]:
        itype = metadata["interview_type"].lower()
        valid_types = ["coding", "system_design", "behavioral", "mixed"]
        if itype in valid_types:
            validated["interview_type"] = itype
        else:
            logger.warning(f"Invalid interview_type '{itype}', defaulting to 'mixed'")
            validated["interview_type"] = "mixed"
    else:
        validated["interview_type"] = "mixed"

    # Interview ID (optional, for tracking)
    if "interview_id" in metadata and metadata["interview_id"]:
        validated["interview_id"] = str(metadata["interview_id"])

    # Candidate ID (optional, for tracking)
    if "candidate_id" in metadata and metadata["candidate_id"]:
        validated["candidate_id"] = str(metadata["candidate_id"])

    logger.info(f"Metadata validated: {validated}")
    return validated


def format_feedback_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format feedback output to ensure consistent structure.

    Args:
        result: Raw result from service layer

    Returns:
        Formatted result dict
    """
    # Ensure all required fields are present
    if "feedback" not in result:
        raise ValueError("Missing 'feedback' in result")

    if "metadata" not in result:
        result["metadata"] = {}

    # Ensure feedback has all required fields
    feedback = result["feedback"]
    required_feedback_fields = [
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

    for field in required_feedback_fields:
        if field not in feedback:
            logger.error(f"Missing required feedback field: {field}")
            raise ValueError(f"Incomplete feedback: missing {field}")

    # Ensure metadata has required fields
    metadata = result["metadata"]
    if "duration_ms" not in metadata:
        metadata["duration_ms"] = 0
    if "model_used" not in metadata:
        metadata["model_used"] = "gemini-2.0-flash"

    return result
