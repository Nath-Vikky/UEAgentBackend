#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "UeAssistantDeveloperSettingsExample.generated.h"

UCLASS(Config=Game, DefaultConfig, meta=(DisplayName="UE Assistant Example Settings"))
class YOURMODULE_API UUeAssistantDeveloperSettingsExample : public UDeveloperSettings
{
    GENERATED_BODY()

public:
    UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category="Network")
    FString ApiBaseUrl = TEXT("https://api.example.com");

    UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category="Feature")
    bool bEnableRuntimeAssistant = true;
};

