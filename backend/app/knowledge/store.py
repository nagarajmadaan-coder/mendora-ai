"""
Loads and validates the knowledge entries in data/entries.json.

Validation happens at startup, so a bad entry stops the server instead of reaching a user:
  * required fields, allowed trades and values
  * unique IDs
  * NO step or restriction may contain a dangerous DIY instruction (checked with the safety engine's screen)
  * the source/verification status must be stated honestly ("unverified" unless there is a documented basis)
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..safety.engine import find_unsafe_instruction

DATA_FILE = Path(__file__).parent / "data" / "entries.json"


class Source(BaseModel):
    type: Literal["mendora_draft", "manufacturer_guidance", "professional_review"]
    verification_status: Literal["unverified", "professionally_reviewed"]
    note: str = Field(min_length=10)
    reviewed_by: str | None = None  # required when professionally_reviewed

    @model_validator(mode="after")
    def _basis_required(self) -> "Source":
        if self.verification_status == "professionally_reviewed" and not self.reviewed_by:
            raise ValueError("professionally_reviewed entries must name who reviewed them (reviewed_by)")
        return self


class Cause(BaseModel):
    title: str = Field(min_length=3)
    explanation: str = Field(min_length=10)


class KnowledgeEntry(BaseModel):
    id: str = Field(pattern=r"^[a-z]{3}-[a-z0-9-]+$")
    trade: Literal["plumbing", "electrical", "carpentry"]
    category: str
    title: str
    symptoms: list[str] = Field(min_length=1)
    keywords: list[str] = Field(min_length=3)
    clarifying_questions: list[str] = Field(default_factory=list)
    possible_causes: list[Cause] = Field(min_length=1)
    next_steps: list[str] = Field(min_length=1)
    diy_level: Literal["simple", "none"]  # "none" = only safe checks; the fix itself is for a professional
    professional_recommended: bool
    professional_reason: str | None = None
    safety_restrictions: list[str] = Field(default_factory=list)
    hazard_categories: list[Literal["electrical", "gas", "structural", "plumbing", "carpentry", "general"]]
    source: Source | None = None

    @field_validator("next_steps", "safety_restrictions")
    @classmethod
    def _no_unsafe_instructions(cls, items: list[str]) -> list[str]:
        for text in items:
            hit = find_unsafe_instruction(text)
            if hit:
                raise ValueError(f"unsafe instruction in knowledge entry: '{hit}' in '{text}'")
        return items

    @model_validator(mode="after")
    def _consistent(self) -> "KnowledgeEntry":
        if self.diy_level == "none" and not self.professional_recommended:
            raise ValueError(f"{self.id}: diy_level 'none' requires professional_recommended = true")
        if self.professional_recommended and not self.professional_reason:
            raise ValueError(f"{self.id}: professional_reason is required when a professional is recommended")
        return self


class KnowledgeFile(BaseModel):
    version: str
    default_source: Source
    entries: list[KnowledgeEntry]

    @model_validator(mode="after")
    def _apply_defaults_and_check_ids(self) -> "KnowledgeFile":
        ids = [e.id for e in self.entries]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate knowledge entry ids: {sorted(duplicates)}")
        for entry in self.entries:
            if entry.source is None:
                entry.source = self.default_source
        return self


def load_knowledge(path: Path = DATA_FILE) -> KnowledgeFile:
    return KnowledgeFile.model_validate(json.loads(path.read_text(encoding="utf-8")))


@lru_cache
def get_knowledge() -> KnowledgeFile:
    return load_knowledge()
