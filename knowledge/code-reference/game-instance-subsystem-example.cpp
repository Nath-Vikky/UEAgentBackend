#include "GameFeatureSubsystemExample.h"

void UGameFeatureSubsystemExample::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
}

void UGameFeatureSubsystemExample::Deinitialize()
{
    RuntimeObjects.Reset();
    Super::Deinitialize();
}

void UGameFeatureSubsystemExample::RegisterRuntimeObject(UObject* Object)
{
    if (IsValid(Object))
    {
        RuntimeObjects.AddUnique(Object);
    }
}

