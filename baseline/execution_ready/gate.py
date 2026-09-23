"""Fail-closed release gate v0.3 (data gate remains pending)."""
from __future__ import annotations

import re
import hashlib
from pathlib import Path


REQUIRED = ("data", "code", "environment", "preregistration")
DOOR_FIELDS = {
    "data": ("p4", "frozen_manifest_sha256", "signature_range"),
    "code": ("code_hash", "review"),
    "environment": ("authenticated",),
    "preregistration": ("full_results", "failure_policy"),
}


def check_gate(gates: dict, evidence_root: str | Path | None = None) -> dict:
    """Validate four release gates and refuse a validation flag when data waits."""
    if not isinstance(gates, dict) or any(k not in gates for k in REQUIRED):
        raise ValueError("release gate requires data, code, environment and preregistration")
    statuses = {k: str(gates[k].get("status", "pending")) if isinstance(gates[k], dict) else "pending" for k in REQUIRED}
    missing_reasons = {
        k: (gates[k].get("missing_reason") or "missing_reason_required" if isinstance(gates[k], dict) else "missing_gate_record")
        for k in REQUIRED if statuses[k] != "passed"
    }
    if statuses["data"] != "passed":
        return {"schema": "release-gate-v0.3", "status": "pending", "candidate_ready": False, "validation_flag_allowed": False,
                "gates": statuses, "missing_reasons": missing_reasons}
    if any(statuses[k] != "passed" for k in REQUIRED):
        return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                "gates": statuses, "missing_reasons": missing_reasons}
    if any(not gates[k].get(field) for k, fields in DOOR_FIELDS.items() for field in fields):
        return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                "gates": statuses, "missing_reasons": {k: "required gate evidence field missing" for k in REQUIRED}}
    typed_ok = (
        isinstance(gates["data"].get("p4"), bool) and gates["data"]["p4"] is True
        and isinstance(gates["data"].get("frozen_manifest_sha256"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", gates["data"]["frozen_manifest_sha256"]) is not None
        and isinstance(gates["data"].get("signature_range"), str)
        and isinstance(gates["code"].get("code_hash"), str)
        and re.fullmatch(r"[0-9a-fA-F]{64}", gates["code"]["code_hash"]) is not None
        and gates["code"].get("review") is True
        and gates["environment"].get("authenticated") is True
        and gates["preregistration"].get("full_results") is True
        and isinstance(gates["preregistration"].get("failure_policy"), str)
    )
    if not typed_ok:
        return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                "gates": statuses, "missing_reasons": {k: "typed gate evidence is incomplete" for k in REQUIRED}}
    if any(not isinstance(gates[k].get("evidence_path"), str)
           or not isinstance(gates[k].get("evidence_sha256"), str)
           or not re.fullmatch(r"[0-9a-fA-F]{64}", gates[k]["evidence_sha256"])
           for k in REQUIRED):
        return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                "gates": statuses, "missing_reasons": {k: "evidence_sha256 must be a 64-hex artifact hash" for k in REQUIRED}}
    if evidence_root is not None:
        root = Path(evidence_root).resolve()
        for k in REQUIRED:
            candidate = (root / gates[k]["evidence_path"]).resolve()
            if root not in candidate.parents or not candidate.is_file():
                return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                        "gates": statuses, "missing_reasons": {k: "evidence file missing or outside evidence_root"}}
            if hashlib.sha256(candidate.read_bytes()).hexdigest().lower() != gates[k]["evidence_sha256"].lower():
                return {"schema": "release-gate-v0.3", "status": "blocked", "candidate_ready": False, "validation_flag_allowed": False,
                        "gates": statuses, "missing_reasons": {k: "evidence file SHA256 mismatch"}}
    # This library only emits an auditable candidate-ready result.  Creating a
    # validation flag remains an orchestrator-controlled action outside this
    # package, even after all four doors have evidence.
    return {"schema": "release-gate-v0.3", "status": "passed", "candidate_ready": True,
            "validation_flag_allowed": False, "gates": statuses}
