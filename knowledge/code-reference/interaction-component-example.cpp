#include "InteractionComponentExample.h"

#include "Components/PrimitiveComponent.h"
#include "GameFramework/Actor.h"

UInteractionComponentExample::UInteractionComponentExample()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UInteractionComponentExample::BeginPlay()
{
    Super::BeginPlay();

    AActor* Owner = GetOwner();
    UPrimitiveComponent* Primitive = Owner ? Owner->FindComponentByClass<UPrimitiveComponent>() : nullptr;
    if (Primitive)
    {
        Primitive->OnComponentBeginOverlap.AddDynamic(this, &UInteractionComponentExample::HandleOwnerBeginOverlap);
    }
}

void UInteractionComponentExample::HandleOwnerBeginOverlap(
    UPrimitiveComponent* OverlappedComponent,
    AActor* OtherActor,
    UPrimitiveComponent* OtherComp,
    int32 OtherBodyIndex,
    bool bFromSweep,
    const FHitResult& SweepResult
)
{
    if (!OtherActor || OtherActor == GetOwner())
    {
        return;
    }

    // TODO: Replace with a project-specific interface call or event dispatch.
    UE_LOG(LogTemp, Verbose, TEXT("Interaction overlap with %s"), *OtherActor->GetName());
}

