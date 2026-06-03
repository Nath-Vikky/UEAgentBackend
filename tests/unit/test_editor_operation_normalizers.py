from __future__ import annotations

import pytest

from app.services.editor_operations.catalog import EditorOperationValidationError
from app.services.editor_operations.normalizers import (
    normalize_asset_name,
    normalize_asset_path,
    normalize_class_path,
    normalize_folder,
    normalize_optional_string,
    normalize_redirector_folder,
)


def test_normalize_asset_path_accepts_relative_and_uasset_paths() -> None:
    assert normalize_asset_path("Blueprints\\BP_Player.uasset") == "/Game/Blueprints/BP_Player"
    assert normalize_asset_path("/Game/Blueprints/BP_Player.BP_Player") == "/Game/Blueprints/BP_Player"


def test_normalize_asset_path_blocks_parent_traversal_and_non_game_roots() -> None:
    with pytest.raises(EditorOperationValidationError) as parent_error:
        normalize_asset_path("/Game/../Secret")
    with pytest.raises(EditorOperationValidationError) as root_error:
        normalize_asset_path("/Engine/EditorMeshes/Asset")

    assert parent_error.value.reason == "asset_path_contains_parent_traversal"
    assert root_error.value.reason == "asset_path_must_be_under_game"


def test_normalize_folder_rejects_object_path_and_redirector_root() -> None:
    assert normalize_folder("/Game/UI/") == "/Game/UI"

    with pytest.raises(EditorOperationValidationError) as object_error:
        normalize_folder("/Game/UI/WBP_MainHUD.OtherObject")
    with pytest.raises(EditorOperationValidationError) as broad_error:
        normalize_redirector_folder("/Game")

    assert object_error.value.reason == "target_folder_must_not_be_object_path"
    assert broad_error.value.reason == "redirector_folder_too_broad"


def test_normalize_name_class_and_optional_string_contracts() -> None:
    assert normalize_asset_name("BP_Player") == "BP_Player"
    assert normalize_class_path("/Script/Engine.Actor") == "/Script/Engine.Actor"
    assert normalize_optional_string("  Ready  ", max_length=16) == "Ready"

    with pytest.raises(EditorOperationValidationError) as name_error:
        normalize_asset_name("1Invalid", "new_name")
    with pytest.raises(EditorOperationValidationError) as class_error:
        normalize_class_path("../BadClass")
    with pytest.raises(EditorOperationValidationError) as text_error:
        normalize_optional_string("x" * 17, max_length=16)

    assert name_error.value.reason == "new_name_invalid"
    assert class_error.value.reason == "parent_class_invalid"
    assert text_error.value.reason == "text_field_too_long"
