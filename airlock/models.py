"""Validated request, policy, provenance, and internal decision contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserProvenance(StrictModel):
    user_id: str = Field(default="unknown", max_length=200)
    name: str = Field(default="Unknown user", max_length=200)
    roles: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=10
    )
    team: str = Field(default="unknown", max_length=200)
    purpose: str = Field(default="", max_length=2000)


class ContextRequest(StrictModel):
    object_id: str = Field(pattern=r"^obj_[a-f0-9]{16}$")
    question: str = Field(min_length=1, max_length=6000)
    user_provenance: UserProvenance = Field(default_factory=UserProvenance)
    purpose: str = Field(default="", max_length=2000)


class PolicyInput(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=12000)
    scope: Literal["organization", "object"] = "organization"
    object_id: str | None = None
    enabled: bool = True


class Decision(StrictModel):
    mode: Literal["query", "summary", "scoped", "full", "deny"]
    response: str
    explanation: str
    applied_policy_ids: list[str]
    disclosed_fields: list[str]
