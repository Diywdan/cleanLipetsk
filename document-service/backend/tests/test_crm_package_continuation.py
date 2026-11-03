import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import crm_internal
from app.models import DocumentPackage
from app.models.enums import PackageStatus
from app.schemas.api import CrmCaseSyncRequest, DocumentInfo, PackageDetail
from app.services import crm_events, generation
from app.services import validation
from app.services.validation import Issue, Readiness


ALL_CODES = [
    "assignment",
    "decision",
    "act",
    "inspection_protocol",
    "prescription",
    "direction",
]


def _doc(code):
    return SimpleNamespace(
        id=ALL_CODES.index(code) + 1,
        document_type=SimpleNamespace(code=code, name=code.title())
    )


def _fixture_db(existing_codes):
    case = SimpleNamespace(id=12, crm_case_id="crm-12")
    package_kind = SimpleNamespace(id=4)
    package = SimpleNamespace(
        id=19,
        control_case_id=case.id,
        package_kind=SimpleNamespace(
            id=package_kind.id,
            code=crm_internal.PRIMARY_PACKAGE,
            name="Первичное предписание",
        ),
        status=PackageStatus.GENERATED,
        snapshot_id=81,
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalar.side_effect = [case, package_kind, package]
    db.scalars.return_value = [_doc(code) for code in existing_codes]
    return db, case, package


def _ready():
    return Readiness(
        case_id=12,
        package_kind=crm_internal.PRIMARY_PACKAGE,
        documents=ALL_CODES,
    )


def _package_detail(package, codes, missing=None):
    return PackageDetail(
        id=package.id,
        case_id=package.control_case_id,
        package_kind=package.package_kind.code,
        status="generated",
        snapshot_id=package.snapshot_id,
        created_at=package.created_at,
        documents=[
            DocumentInfo(
                id=index,
                code=code,
                name=code,
                download_url=f"/api/documents/{index}/file",
            )
            for index, code in enumerate(codes, start=1)
        ],
        missing_templates=missing or [],
    )


@pytest.fixture(autouse=True)
def integration_token():
    with patch.object(crm_internal.settings, "crm_integration_token", "test-token"):
        yield


def test_continuation_fills_existing_partial_package_without_recreating_documents():
    existing_codes = ["assignment", "decision", "act"]
    db, case, package = _fixture_db(existing_codes)
    readiness = _ready()
    generated = generation.GenerationResult(
        package_id=package.id,
        created=[
            SimpleNamespace(code=code)
            for code in ("inspection_protocol", "prescription", "direction")
        ],
    )
    with (
        patch.object(crm_internal.validation, "check_readiness", return_value=readiness),
        patch.object(
            crm_internal.generation,
            "generate_package",
            return_value=generated,
        ) as generate,
        patch.object(
            crm_internal.package_details,
            "package_detail",
            return_value=_package_detail(package, ALL_CODES),
        ),
        patch.object(crm_internal.audit, "record") as record,
        patch.object(crm_internal.crm_events, "package_generated") as callback,
    ):
        response = crm_internal.continue_primary_package(
            case.crm_case_id, authorization="Bearer test-token", db=db
        )

    assert response.status == "generated"
    assert [document.code for document in response.package.documents] == ALL_CODES
    assert response.package.documents[-1].download_url == "/api/documents/6/file"
    assert generate.call_args.kwargs["existing_package_id"] == package.id
    assert generate.call_args.kwargs["only_codes"] == [
        "inspection_protocol",
        "prescription",
        "direction",
    ]
    assert generate.call_args.kwargs["commit"] is False
    record.assert_called_once()
    db.commit.assert_called_once()
    callback.assert_called_once_with(
        case, package, len(ALL_CODES), event_suffix="extended"
    )


@pytest.mark.parametrize(
    "missing",
    [
        [Issue(None, "control_object", "объект контроля не указан")],
        [],
    ],
)
def test_continuation_returns_readiness_without_generating_when_not_ready(missing):
    db, case, package = _fixture_db(["assignment", "decision"])
    readiness = _ready()
    readiness.issues = missing
    readiness.missing_templates = ["direction"] if not missing else []
    with (
        patch.object(crm_internal.validation, "check_readiness", return_value=readiness),
        patch.object(crm_internal.generation, "generate_package") as generate,
        patch.object(
            crm_internal.package_details,
            "package_detail",
            side_effect=lambda _db, target, missing: _package_detail(
                target, ["assignment", "decision"], missing
            ),
        ),
    ):
        response = crm_internal.continue_primary_package(
            case.crm_case_id, authorization="Bearer test-token", db=db
        )

    assert response.status == "needs_input"
    assert response.readiness["is_ready"] is False
    assert response.package.missing_templates == readiness.missing_templates
    generate.assert_not_called()
    db.commit.assert_not_called()


def test_repeated_continuation_is_idempotent_for_a_complete_package():
    db, case, package = _fixture_db(ALL_CODES)
    with (
        patch.object(crm_internal.validation, "check_readiness") as check_readiness,
        patch.object(crm_internal.generation, "generate_package") as generate,
        patch.object(
            crm_internal.package_details,
            "package_detail",
            return_value=_package_detail(package, ALL_CODES),
        ),
        patch.object(crm_internal.crm_events, "package_generated") as callback,
    ):
        response = crm_internal.continue_primary_package(
            case.crm_case_id, authorization="Bearer test-token", db=db
        )

    assert response.status == "generated"
    assert response.readiness["is_ready"] is True
    check_readiness.assert_not_called()
    generate.assert_not_called()
    callback.assert_not_called()
    db.commit.assert_not_called()


def test_knm_sync_checks_remaining_documents_without_generating_them():
    case = SimpleNamespace(
        id=12,
        crm_case_id="crm-12",
        case_number="CRM-12",
        subject=None,
        controlled_organization=None,
    )
    package_kind = SimpleNamespace(id=4, code=crm_internal.PRIMARY_PACKAGE)
    package = SimpleNamespace(
        id=19,
        control_case_id=case.id,
        package_kind=package_kind,
        status=PackageStatus.GENERATED,
        snapshot_id=81,
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    primary_action = SimpleNamespace(result_text=None)
    db = MagicMock()
    db.scalar.side_effect = [None, case, primary_action, package_kind, package]
    db.scalars.return_value = [_doc("assignment"), _doc("decision")]
    readiness = _ready()
    response_package = _package_detail(package, ["assignment", "decision"])
    body = CrmCaseSyncRequest(
        crm_case_id=case.crm_case_id,
        case_number=case.case_number,
        check_knm_readiness=True,
    )

    with (
        patch.object(crm_internal.validation, "check_readiness", return_value=readiness) as check,
        patch.object(crm_internal.generation, "generate_package") as generate,
        patch.object(crm_internal.package_details, "package_detail", return_value=response_package),
    ):
        response = crm_internal.sync_case(body, authorization="Bearer test-token", db=db)

    assert response["status"] == "generated"
    assert response["readiness"] == readiness.as_dict()
    assert response["primary_package"]["id"] == package.id
    assert check.call_args.kwargs["only_codes"] == crm_internal.PRIMARY_EXTENSION_DOCUMENTS
    generate.assert_not_called()
    db.commit.assert_called_once()


def test_continuation_requires_existing_primary_package():
    db = MagicMock()
    db.scalar.side_effect = [
        SimpleNamespace(id=12, crm_case_id="crm-12"),
        SimpleNamespace(id=4),
        None,
    ]
    with pytest.raises(HTTPException) as error:
        crm_internal.continue_primary_package(
            "crm-12", authorization="Bearer test-token", db=db
        )
    assert error.value.status_code == 409


def test_continuation_callback_uses_distinct_id_and_existing_payload_shape():
    case = SimpleNamespace(id=12, crm_case_id="crm-12")
    documents = [_doc(code) for code in ALL_CODES]
    package = SimpleNamespace(
        id=19,
        package_kind=SimpleNamespace(
            code=crm_internal.PRIMARY_PACKAGE,
            name="Первичное предписание",
        ),
        documents=documents,
        created_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    with (
        patch.object(
            crm_events.settings,
            "crm_event_url",
            "https://crm.invalid/events",
        ),
        patch.object(crm_events.settings, "crm_integration_token", "test-token"),
        patch.object(crm_events, "urlopen", return_value=response) as urlopen,
    ):
        crm_events.package_generated(
            case, package, len(ALL_CODES), event_suffix="extended"
        )

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data)
    assert request.get_header("Authorization") == "Bearer test-token"
    assert payload["event_id"] == "document-package:19:extended"
    assert payload["crm_case_id"] == "crm-12"
    assert payload["package_id"] == 19
    assert payload["documents_count"] == 6
    assert payload["document_codes"] == ALL_CODES
    assert "document_names" in payload
    assert payload["documents"] == [
        {
            "id": index,
            "code": code,
            "name": code.title(),
            "download_url": f"/api/documents/{index}/file",
        }
        for index, code in enumerate(ALL_CODES, start=1)
    ]
    assert set(payload) == {
        "event_id",
        "crm_case_id",
        "document_case_id",
        "package_id",
        "package_kind",
        "package_name",
        "documents_count",
        "document_codes",
        "document_names",
        "documents",
        "actor_name",
        "occurred_at",
    }


def test_generator_appends_missing_document_to_existing_package():
    case = SimpleNamespace(
        id=12,
        actual_start_at=None,
        planned_start_at=None,
        actual_end_at=None,
        act_number="ACT-12",
        erp_number="ERP-12",
        erp_code="E12",
        assignment_number="A12",
        assignment_date=None,
        prescriptions=[],
        decisions=[],
    )
    package_kind = SimpleNamespace(id=4)
    package = SimpleNamespace(
        id=19,
        control_case_id=case.id,
        package_kind_id=package_kind.id,
        snapshot_id=None,
        status=PackageStatus.GENERATED,
    )
    composition = [
        SimpleNamespace(
            document_type=SimpleNamespace(
                id=index,
                code=code,
                name=code.title(),
                uses_external_number=(code == "act"),
            ),
            document_type_id=index,
        )
        for index, code in enumerate(("assignment", "decision", "act"), start=1)
    ]
    db = MagicMock()
    db.get.return_value = case
    db.scalar.side_effect = [package_kind, package, SimpleNamespace(id=5)]
    db.scalars.side_effect = [
        ["assignment", "decision"],
        composition,
        [item.document_type for item in composition],
    ]
    template = SimpleNamespace(id=11, file=SimpleNamespace(), code="act", version="v1")

    with (
        patch.object(generation, "_inspection_for_package", return_value=None),
        patch.object(generation.snapshots, "build_case_context", return_value={}),
        patch.object(
            generation.snapshots,
            "save_snapshot",
            side_effect=[SimpleNamespace(id=20), SimpleNamespace(id=21)],
        ),
        patch.object(generation, "_document_pages", return_value=None),
        patch.object(generation.ru, "date_short", return_value="02.11.2026"),
        patch.object(generation.ru, "date_words", return_value="2 ноября 2026"),
        patch.object(generation, "_active_template", return_value=template),
        patch.object(generation.storage, "read_bytes", return_value=b"template"),
        patch.object(generation, "build_document_bytes", return_value=b"document"),
        patch.object(generation.pages_service, "count_pages", return_value=1),
        patch.object(
            generation.storage,
            "save_bytes",
            return_value=SimpleNamespace(id=30),
        ),
    ):
        result = generation.generate_package(
            db,
            case.id,
            package_kind_code=crm_internal.PRIMARY_PACKAGE,
            only_codes=["act"],
            existing_package_id=package.id,
            commit=False,
        )

    assert result.package_id == package.id
    assert [document.code for document in result.created] == ["act"]
    assert result.skipped == ["assignment", "decision"]
    assert package.snapshot_id == 20
    assert not any(
        isinstance(call.args[0], DocumentPackage)
        for call in db.add.call_args_list
    )
    db.commit.assert_not_called()


def test_active_template_without_file_is_reported_as_missing():
    case = SimpleNamespace(
        id=12,
        control_kind_id=None,
        control_form_id=None,
        control_body_id=None,
        controlled_organization_id=None,
        control_object_id=None,
        assignment_approved_by_signatory_id=None,
        assignment_date=None,
        planned_start_at=None,
        planned_end_at=None,
        actual_start_at=None,
        actual_end_at=None,
        erp_number=None,
        controlled_organization=None,
        controlled_unit=None,
        control_object=None,
    )
    package_kind = SimpleNamespace(id=4)
    item = SimpleNamespace(
        document_type=SimpleNamespace(code="direction"),
        document_type_id=6,
    )
    template = SimpleNamespace(file=None)
    db = MagicMock()
    db.get.return_value = case
    db.scalar.side_effect = [package_kind, template]
    db.scalars.side_effect = [[item], [], [], [], []]

    readiness = validation.check_readiness(
        db, case.id, crm_internal.PRIMARY_PACKAGE, only_codes=["direction"]
    )

    assert readiness.is_ready is False
    assert readiness.missing_templates == ["direction"]


def test_bad_token_is_rejected():
    db = MagicMock()
    with pytest.raises(HTTPException) as error:
        crm_internal.continue_primary_package(
            "crm-12", authorization="Bearer wrong-token", db=db
        )
    assert error.value.status_code == 401
