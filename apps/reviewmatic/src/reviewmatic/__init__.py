"""Reviewmatic runtime: GitLab and local-WIP review workflows with private artifacts, a portable contract core, and manual runbooks."""

from __future__ import annotations

__version__ = "12.0.0"

# The schema diagnostics walker needs the canonical validator as its oracle;
# register it once at package import for consistent schema diagnostics.
from reviewmatic import schema_issues as _schema_issues
from reviewmatic.portable.portable_gitlab import contract as _contract

_schema_issues.register_schema_validator(_contract.schema_valid)
_contract.register_schema_issue_locator(
    lambda schema, value: [
        {"path": issue["path"], "message": issue["message"]}
        for issue in _schema_issues.schema_issues(schema, value, "$", schema)
    ]
)
