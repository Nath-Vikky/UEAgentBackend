// domain: code_reference
// topic: Actor component creation pattern
// use_for: Code Generate, Code Review

#include "ExampleInteractionActor.h"
#include "Components/StaticMeshComponent.h"

AExampleInteractionActor::AExampleInteractionActor()
{
    PrimaryActorTick.bCanEverTick = false;

    RootMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RootMesh"));
    SetRootComponent(RootMesh);
}

void AExampleInteractionActor::BeginPlay()
{
    Super::BeginPlay();

    // Runtime initialization belongs here rather than in the constructor.
    RefreshInteractionState();
}

void AExampleInteractionActor::RefreshInteractionState()
{
    bCanInteract = IsValid(RootMesh);
}
