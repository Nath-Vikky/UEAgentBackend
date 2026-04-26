#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/HitResult.h"
#include "InteractionComponentExample.generated.h"

class UPrimitiveComponent;

// 交互组件示例：绑定拥有者的 PrimitiveComponent overlap，并把项目逻辑留给接口或事件。
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class YOURMODULE_API UInteractionComponentExample : public UActorComponent
{
    GENERATED_BODY()

public:
    UInteractionComponentExample();

protected:
    virtual void BeginPlay() override;

    UFUNCTION()
    void HandleOwnerBeginOverlap(
        UPrimitiveComponent* OverlappedComponent,
        AActor* OtherActor,
        UPrimitiveComponent* OtherComp,
        int32 OtherBodyIndex,
        bool bFromSweep,
        const FHitResult& SweepResult
    );
};

