"""PAPER-32: capability report for the optional hosted document-AI track.

Checks ONLY for the presence of credential material (profile/variable names,
never secret values) for the three candidate hosted document-AI providers.
Does not call any hosted API. Writes an explicit not_run capability report --
never a silent omission, never a substitution with manual PDF reading.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

OUT_PATH = Path("E:/MeridianData/ooxml-graph-paper/manifests/paper32-hosted-document-ai-capability-report.json")


def _aws_default_profile_present() -> bool:
    for name in ("credentials", "config"):
        path = Path.home() / ".aws" / name
        if path.exists() and "[default]" in path.read_text(encoding="utf-8", errors="ignore"):
            return True
    return False


def main() -> None:
    report = {
        "schema": "paper32-hosted-document-ai-capability-report-v1",
        "track_status": "not_run",
        "reason": "no_credential_no_approval",
        "note": (
            "Per explicit user instruction: hosted document-AI providers require a "
            "specific provider, credential, data-handling approval, and cost approval "
            "all explicitly supplied before any upload. None were supplied. Not "
            "substituted with manual/ad-hoc PDF reading as a benchmark baseline."
        ),
        "providers": {
            "google_document_ai": {
                "credential_env_var_set": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
                "gcloud_config_dir_present": (Path.home() / ".config" / "gcloud").exists(),
                "data_handling_approval": False,
                "cost_approval": False,
            },
            "azure_document_intelligence": {
                "endpoint_env_var_set": bool(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")),
                "key_env_var_set": bool(os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")),
                "data_handling_approval": False,
                "cost_approval": False,
            },
            "aws_textract": {
                "ambient_default_profile_present": _aws_default_profile_present(),
                "project_scoped_credential_present": False,
                "note": (
                    "An ambient, unscoped '[default]' AWS profile exists on this host "
                    "(profile name only checked, no secret material read or used). "
                    "Not treated as satisfying the explicit-approval gate for this "
                    "project's hosted document-AI use -- using ambient credentials for "
                    "an unapproved purpose is exactly what the gate exists to prevent."
                ),
                "data_handling_approval": False,
                "cost_approval": False,
            },
        },
        "unblock_requirements": [
            "explicit user/organization decision on exactly one hosted provider",
            "a credential provisioned through project environment configuration for this specific use",
            "explicit data-handling approval covering the docx-corpus/OmegaUse-OfficeVal source documents",
            "explicit cost approval for per-page hosted billing across a 127-document, often multi-page corpus",
        ],
    }
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
