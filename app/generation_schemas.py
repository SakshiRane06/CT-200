"""Validate the structured QA cases returned by an LLM."""

from pydantic import BaseModel, ConfigDict, Field


class TestCaseIdea(BaseModel):
    """One concrete QA check for a behavior described in the manual."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=160)
    preconditions: list[str]
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=3)
    source_node_ids: list[str] = Field(min_length=1)


class TestCaseIdeas(BaseModel):
    """The full response must contain three to five test cases."""

    model_config = ConfigDict(extra="forbid")

    test_cases: list[TestCaseIdea] = Field(min_length=3, max_length=5)
