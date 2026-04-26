#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LineTraceInteractionComponentExample.generated.h"

// 射线交互示例：从拥有者/控制器视角发射 LineTrace，返回命中的 Actor。
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class YOURMODULE_API ULineTraceInteractionComponentExample : public UActorComponent
{
    GENERATED_BODY()

public:
    ULineTraceInteractionComponentExample();

    UFUNCTION(BlueprintCallable, Category = "Interaction")
    AActor* TraceForInteractable() const;

protected:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
    float TraceDistance = 500.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
    TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
    bool bDrawDebug = false;
};

