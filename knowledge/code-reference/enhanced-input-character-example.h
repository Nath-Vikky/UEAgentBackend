#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "EnhancedInputCharacterExample.generated.h"

class UInputAction;
class UInputMappingContext;

// 角色增强输入示例：Character + Input Mapping Context + Input Actions.
UCLASS()
class YOURMODULE_API AEnhancedInputCharacterExample : public ACharacter
{
    GENERATED_BODY()

public:
    AEnhancedInputCharacterExample();

protected:
    virtual void BeginPlay() override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Input")
    TObjectPtr<UInputMappingContext> DefaultMappingContext;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Input")
    TObjectPtr<UInputAction> MoveAction;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Input")
    TObjectPtr<UInputAction> LookAction;

    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Input")
    TObjectPtr<UInputAction> JumpAction;

private:
    void Move(const FInputActionValue& Value);
    void Look(const FInputActionValue& Value);
};

