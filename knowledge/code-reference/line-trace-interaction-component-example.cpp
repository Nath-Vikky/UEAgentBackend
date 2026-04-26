#include "LineTraceInteractionComponentExample.h"

#include "DrawDebugHelpers.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

ULineTraceInteractionComponentExample::ULineTraceInteractionComponentExample()
{
    PrimaryComponentTick.bCanEverTick = false;
}

AActor* ULineTraceInteractionComponentExample::TraceForInteractable() const
{
    const AActor* Owner = GetOwner();
    if (!Owner)
    {
        return nullptr;
    }

    FVector ViewLocation = Owner->GetActorLocation();
    FRotator ViewRotation = Owner->GetActorRotation();

    if (const APawn* PawnOwner = Cast<APawn>(Owner))
    {
        if (const AController* Controller = PawnOwner->GetController())
        {
            Controller->GetPlayerViewPoint(ViewLocation, ViewRotation);
        }
    }

    const FVector End = ViewLocation + ViewRotation.Vector() * TraceDistance;
    FHitResult Hit;
    FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(InteractionTrace), false, Owner);

    const bool bHit = GetWorld() && GetWorld()->LineTraceSingleByChannel(
        Hit,
        ViewLocation,
        End,
        TraceChannel,
        QueryParams
    );

    if (bDrawDebug && GetWorld())
    {
        DrawDebugLine(GetWorld(), ViewLocation, End, bHit ? FColor::Green : FColor::Red, false, 1.0f);
    }

    return bHit ? Hit.GetActor() : nullptr;
}

