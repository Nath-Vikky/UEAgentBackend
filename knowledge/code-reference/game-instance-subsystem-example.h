#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameFeatureSubsystemExample.generated.h"

// GameInstanceSubsystem 示例：适合跨地图存在的运行时管理器。
UCLASS()
class YOURMODULE_API UGameFeatureSubsystemExample : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    UFUNCTION(BlueprintCallable, Category = "Subsystem")
    void RegisterRuntimeObject(UObject* Object);

private:
    UPROPERTY()
    TArray<TObjectPtr<UObject>> RuntimeObjects;
};

