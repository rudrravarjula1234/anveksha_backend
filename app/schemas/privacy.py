"""Privacy & sharing schemas — mirror of `privacySettings` in
anveksha_ui/src/mocks/data/admin.ts (legacy + mockup-aligned fields)."""

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import AppModel, ReadModel

Discoverability = Literal["anyone", "verified-only", "invite-only", "private"]


class SharedReport(ReadModel):
    id: str
    reportId: str
    sharedWith: str
    sharedAt: str
    expiresAt: str
    status: Literal["active", "expired"]


class PrivacySettings(ReadModel):
    # Legacy toggles (admin views/tests still read these)
    shareProfile: bool = True
    shareDossiers: bool = True
    shareTranscripts: bool = False
    allowGrayFollowups: bool = True
    hideFromCompanies: list[str] = Field(default_factory=list)
    # Mockup-aligned candidate controls
    discoverability: Discoverability = "verified-only"
    shareScore: bool = True
    shareGap: bool = False
    shareGray: bool = False
    shareTranscript: bool = False
    allowFollowup: bool = True
    anonymousMode: bool = False
    shareVerifierPanel: bool = True
    sharedReports: list[SharedReport] = Field(default_factory=list)


class PrivacyPatch(AppModel):
    shareProfile: Optional[bool] = None
    shareDossiers: Optional[bool] = None
    shareTranscripts: Optional[bool] = None
    allowGrayFollowups: Optional[bool] = None
    hideFromCompanies: Optional[list[str]] = None
    discoverability: Optional[Discoverability] = None
    shareScore: Optional[bool] = None
    shareGap: Optional[bool] = None
    shareGray: Optional[bool] = None
    shareTranscript: Optional[bool] = None
    allowFollowup: Optional[bool] = None
    anonymousMode: Optional[bool] = None
    shareVerifierPanel: Optional[bool] = None
