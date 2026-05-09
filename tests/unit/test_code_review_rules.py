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
