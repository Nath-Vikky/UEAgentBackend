# Async Asset Loading Example

domain: examples
topic: TSoftObjectPtr, async loading, BeginPlay
use_for: Code Generate, Code Review

## Intent

This is a small reference pattern for generated code. It avoids synchronous asset loading in `Tick` and uses a soft reference that can be assigned in the editor.

## Example

```cpp
UPROPERTY(EditDefaultsOnly, Category = "Content")
TSoftObjectPtr<UObject> OptionalAsset;

void AExampleActor::BeginPlay()
{
    Super::BeginPlay();

    if (OptionalAsset.IsNull())
    {
        return;
    }

    OptionalAsset.LoadAsync(FLoadSoftObjectPathAsyncDelegate::CreateWeakLambda(
        this,
        [this](const FSoftObjectPath& LoadedPath, UObject* LoadedObject)
        {
            if (!IsValid(this) || !LoadedObject)
            {
                return;
            }

            CachedLoadedAsset = LoadedObject;
            UE_LOG(LogTemp, Log, TEXT("Loaded optional asset: %s"), *LoadedPath.ToString());
        }));
}
```

## Notes

- Keep the soft reference editable so designers can set content without hard-loading it.
- Avoid calling blocking load helpers from per-frame paths.
- Store loaded objects safely if they need to remain alive.

