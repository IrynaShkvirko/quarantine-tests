"""Importing the package registers every table on ``Base.metadata`` (Alembic reads it)."""

from app.db.models.jira import JiraIssue
from app.db.models.quarantine import QuarantineDecision, QuarantineRecord, VerificationRun
from app.db.models.repos import BotPullRequest, ProductArea, RawUpload, Repository, Team
from app.db.models.runs import CiRun, FailureSignature, FlakyEvent, TestExecution
from app.db.models.stats import DailyTestStats
from app.db.models.tests import ManualSkip, Test

__all__ = [
    "BotPullRequest",
    "CiRun",
    "DailyTestStats",
    "FailureSignature",
    "FlakyEvent",
    "JiraIssue",
    "ManualSkip",
    "ProductArea",
    "QuarantineDecision",
    "QuarantineRecord",
    "RawUpload",
    "Repository",
    "Team",
    "Test",
    "TestExecution",
    "VerificationRun",
]
