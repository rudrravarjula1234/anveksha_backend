"""Custom exceptions for the Agent Service.

Ported from ``backend/lib/agent_service/exceptions.py``. The hierarchy now
roots at :class:`app.core.exceptions.AppError` so the global FastAPI handler
translates agent failures into clean JSON responses (legacy rooted at plain
``Exception``); the class names and semantics are unchanged.
"""

from app.core.exceptions import AppError


class AgentServiceException(AppError):
    """Base exception for all agent service errors"""

    status_code = 500
    error_code = "agent_service_error"


class ModelProviderNotFoundError(AgentServiceException):
    """Raised when a model provider cannot be found or instantiated"""

    error_code = "model_provider_not_found"


class ConfigurationError(AgentServiceException):
    """Raised when there's an error in service configuration"""

    error_code = "agent_configuration_error"


class OrchestrationError(AgentServiceException):
    """Raised when agent orchestration fails"""

    error_code = "orchestration_error"


class MCPError(AgentServiceException):
    """Raised when MCP server operations fail"""

    error_code = "mcp_error"


class TokenUsageError(AgentServiceException):
    """Raised when token counting or usage tracking fails"""

    error_code = "token_usage_error"


class ModelConfigNotFoundError(ConfigurationError):
    """Raised when a model configuration is not found"""

    status_code = 404
    error_code = "model_config_not_found"


class CredentialNotFoundError(ConfigurationError):
    """Raised when API credentials are not found for a provider"""

    status_code = 404
    error_code = "credential_not_found"


class AgentNotFoundError(AgentServiceException):
    """Raised when an agent is not found in the database"""

    status_code = 404
    error_code = "agent_not_found"


class AgentFrameworkNotInstalledError(AgentServiceException):
    """Raised when an agentic endpoint is invoked without the optional
    AutoGen dependencies installed. New in the port (maps to HTTP 503)."""

    status_code = 503
    error_code = "agent_framework_not_installed"
