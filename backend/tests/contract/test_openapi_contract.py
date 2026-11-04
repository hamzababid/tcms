"""Contract/fuzz tests: responses conform to the published OpenAPI document (docs/08 §2)."""

from __future__ import annotations

import pytest
import schemathesis

from tcms.core.config import Settings
from tcms.main import create_app

pytestmark = [pytest.mark.contract, pytest.mark.integration]


@pytest.fixture(scope="session")
def api_schema(stack_settings: Settings) -> schemathesis.schemas.BaseSchema:
    return schemathesis.openapi.from_asgi("/api/v1/openapi.json", create_app(stack_settings))


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
def test_api_conforms_to_schema(case: schemathesis.Case) -> None:
    case.call_and_validate()
