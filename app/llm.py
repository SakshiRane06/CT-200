"""Call an OpenAI-compatible chat API and validate its JSON response."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from app.generation_schemas import TestCaseIdeas


class LLMConfigurationError(Exception):
    """The provider settings are missing."""


class LLMRequestError(Exception):
    """The provider could not return an answer."""


class InvalidLLMResponse(Exception):
    """The provider returned invalid test case data after one retry."""


def _provider_settings() -> tuple[str, str, str]:
    """Read provider settings without storing secrets in the repository."""
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not api_key or not base_url or not model:
        raise LLMConfigurationError(
            "Set LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL before generating cases"
        )
    return api_key, base_url.rstrip("/"), model


def _call_provider(api_key: str, base_url: str, model: str, messages: list[dict]) -> str:
    """Send one chat request and return the assistant's text."""
    request_body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        base_url + "/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise LLMRequestError(f"The LLM request failed: {error}") from error

    try:
        return response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise LLMRequestError("The LLM response did not contain assistant text") from error


def _parse_cases(response_text: str, allowed_node_ids: set[str]) -> TestCaseIdeas:
    """Parse the response as JSON and check its shape and source references."""
    if not isinstance(response_text, str):
        raise ValueError("The LLM response did not contain text JSON")
    cleaned = response_text.strip()
    # Some models add a Markdown code fence even after being asked for JSON.
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    output = TestCaseIdeas.model_validate_json(cleaned)

    for case in output.test_cases:
        unknown_ids = set(case.source_node_ids) - allowed_node_ids
        if unknown_ids:
            raise ValueError(
                "The response used source IDs outside the selection: "
                + ", ".join(sorted(unknown_ids))
            )
    return output


def generate_test_cases(selection: dict) -> list[dict]:
    """Ask the LLM for test cases, retry once if its structure is invalid."""
    api_key, base_url, model = _provider_settings()
    source_text = "\n\n".join(
        f"Section ID: {item['id']}\n"
        f"Manual version: {item['version']}\n"
        f"Content hash: {item['content_hash']}\n"
        f"Text:\n{item['text']}"
        for item in selection["items"]
    )
    allowed_node_ids = {item["id"] for item in selection["items"]}

    messages = [
        {
            "role": "system",
            "content": (
                "You write concrete, repeatable QA test case ideas for a medical device. "
                "Only use facts in the supplied manual text. Return one JSON object with "
                "a test_cases array containing 3 to 5 objects. Each object must have "
                "title, preconditions (array of strings), steps (array of strings), "
                "expected_result, and source_node_ids (array of supplied section IDs). "
                "Do not add any other keys. Each step must be something a tester can perform."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create QA test cases for this named selection: {selection['name']}\n\n"
                f"{source_text}"
            ),
        },
    ]

    last_error = "unknown validation error"
    for attempt in range(2):
        response_text = _call_provider(api_key, base_url, model, messages)
        try:
            validated = _parse_cases(response_text, allowed_node_ids)
            return [case.model_dump() for case in validated.test_cases]
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            last_error = str(error)
            if attempt == 0:
                # Give one clear chance to repair the structure before failing.
                messages.extend(
                    [
                        {"role": "assistant", "content": response_text},
                        {
                            "role": "user",
                            "content": (
                                "Your last response failed validation: " + last_error
                                + ". Return the complete corrected JSON object only."
                            ),
                        },
                    ]
                )

    raise InvalidLLMResponse("The LLM response was invalid after one retry: " + last_error)
