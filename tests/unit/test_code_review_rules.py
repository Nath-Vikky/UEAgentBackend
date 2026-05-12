from __future__ import annotations

from app.schemas.requests import ContextInput
from app.tools.code_review import review_ue_cpp_files


def _rule_hits(code: str) -> list[str]:
    result = review_ue_cpp_files({"code": code}, ContextInput())
    return list(result["rule_hits"])


def test_code_review_ignores_comment_only_rule_words() -> None:
    code = """
// UObject* RawAsset = nullptr;
// LoadObject<UObject>(nullptr, TEXT("/Game/Test/Asset"));
// PrimaryActorTick.bCanEverTick = true;
void UCleanHelper::Run()
{
    const int32 Value = 1;
}
"""

    assert _rule_hits(code) == []


def test_code_review_treats_uproperty_pointer_as_guarded() -> None:
    code = """
UCLASS()
class UInventoryHolder : public UObject
{
    GENERATED_BODY()
private:
    UPROPERTY()
    UObject* CurrentItem = nullptr;
};
"""

    assert "raw_pointer_ownership" not in _rule_hits(code)


def test_code_review_does_not_flag_gamethread_async_task_as_thread_hazard() -> None:
    code = """
void UInventorySubsystem::Notify()
{
    AsyncTask(ENamedThreads::GameThread, []()
    {
        UE_LOG(LogTemp, Log, TEXT("Back on the game thread"));
    });
}
"""

    assert "thread_context" not in _rule_hits(code)


def test_code_review_still_flags_background_thread_uobject_pointer() -> None:
    code = """
void FInventoryWorker::Run()
{
    AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask, []()
    {
        UObject* Item = nullptr;
    });
}
"""

    hits = _rule_hits(code)

    assert "thread_context" in hits
    assert "raw_pointer_ownership" in hits


def test_code_review_flags_raw_pointer_without_uproperty() -> None:
    code = """
UCLASS()
class UInventoryHolder : public UObject
{
    GENERATED_BODY()
private:
    UObject* CurrentItem = nullptr;
};
"""

    assert "raw_pointer_ownership" in _rule_hits(code)


def test_code_review_flags_synchronous_asset_loading() -> None:
    code = """
void ASpawner::LoadMesh()
{
    StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Game/Props/SM_Cube"));
}
"""

    hits = _rule_hits(code)

    assert "sync_load_usage" in hits
    assert "hardcoded_asset_path" in hits


def test_code_review_accepts_files_payload_content_alias() -> None:
    code = 'void ASpawner::LoadMesh(){ StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Game/Props/SM_Cube")); }'
    result = review_ue_cpp_files(
        {"files": [{"path": "Source/Demo/Private/Spawner.cpp", "content": code}]},
        ContextInput(),
    )

    assert result["review_scope"]["source_kind"] == "content"
    assert result["review_scope"]["content_length"] == len(code)
    assert "sync_load_usage" in result["rule_hits"]


def test_code_review_flags_hardcoded_asset_path() -> None:
    code = """
void ASpawner::Configure()
{
    const FString Path = TEXT("/Game/Characters/BP_Hero");
}
"""

    assert "hardcoded_asset_path" in _rule_hits(code)


def test_code_review_flags_tick_hot_path_usage() -> None:
    code = """
void AMyActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
}
"""

    assert "tick_hot_path" in _rule_hits(code)


def test_code_review_flags_include_pollution() -> None:
    includes = "\n".join(f'#include "Header{i}.h"' for i in range(11))

    assert "include_pollution" in _rule_hits(includes)


def test_code_review_flags_blueprint_surface_exposure() -> None:
    code = """
UCLASS()
class AMyActor : public AActor
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    void RunGameplayAction();
};
"""

    assert "blueprint_surface" in _rule_hits(code)
