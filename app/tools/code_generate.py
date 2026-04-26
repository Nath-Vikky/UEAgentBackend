from __future__ import annotations

import re
from textwrap import dedent
from typing import Any


def _ue_class_name(requirement_description: str, fallback: str = "GeneratedFeature") -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", requirement_description.replace("-", " ").replace("_", " "))
    if not words:
        return fallback
    ignored = {
        "ue",
        "unreal",
        "engine",
        "cpp",
        "cxx",
        "class",
        "actor",
        "component",
        "generate",
        "create",
        "enhanced",
        "input",
        "mapping",
        "context",
        "action",
        "overlap",
        "line",
        "trace",
        "raycast",
        "subsystem",
        "manager",
        "game",
        "instance",
        "global",
    }
    useful_words = [word for word in words if word.lower() not in ignored]
    if not useful_words:
        return fallback
    return "".join(word[:1].upper() + word[1:] for word in useful_words[:4])


def _normalize_target_type(raw_target_type: str) -> str:
    normalized = raw_target_type.strip().lower().replace("-", "_").replace(" ", "_")
    actor_aliases = {
        "",
        "actor",
        "class",
        "code",
        "cpp",
        "cpp_actor",
        "cpp_class",
        "default",
        "general",
        "ue",
        "ue_actor",
        "ue_class",
        "ue_cpp",
        "ue_cpp_class",
        "unreal",
        "unreal_actor",
        "unreal_cpp",
        "unreal_cpp_class",
    }
    if normalized in actor_aliases:
        return "ue_cpp_class"
    character_aliases = {
        "character",
        "cpp_character",
        "player_character",
        "ue_character",
        "ue_cpp_character",
        "unreal_character",
    }
    if normalized in character_aliases:
        return "ue_character"
    return normalized


def _module_name(payload: dict[str, Any]) -> str:
    raw = str(
        payload.get("target_module")
        or payload.get("module_name")
        or payload.get("current_module")
        or "YourModule"
    ).strip()
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", raw)
    return cleaned or "YourModule"


def _module_api_macro(module_name: str) -> str:
    return f"{module_name.upper()}_API"


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _is_enhanced_input_character_request(requirement: str, target_type: str) -> bool:
    lowered = f"{requirement} {target_type}".lower()
    enhanced_terms = (
        "enhanced input",
        "enhancedinput",
        "input action",
        "input mapping",
        "mapping context",
        "uinputaction",
        "uinputmappingcontext",
        "uenhancedinputcomponent",
        "增强输入",
        "输入动作",
        "映射上下文",
    )
    character_terms = ("character", "player", "pawn", "角色", "玩家")
    return any(term in lowered for term in enhanced_terms) and (
        target_type == "ue_character" or any(term in lowered for term in character_terms)
    )


def _is_interaction_component_request(requirement: str, target_type: str) -> bool:
    text = f"{requirement} {target_type}"
    return _contains_any(
        text,
        (
            "actor component",
            "interaction component",
            "interact component",
            "overlap component",
            "component",
            "overlap",
            "oncomponentbeginoverlap",
            "交互组件",
            "组件交互",
            "重叠",
            "碰撞触发",
        ),
    )


def _is_subsystem_request(requirement: str, target_type: str) -> bool:
    text = f"{requirement} {target_type}"
    return _contains_any(
        text,
        (
            "game instance subsystem",
            "gameinstancesubsystem",
            "world subsystem",
            "worldsubsystem",
            "subsystem",
            "manager",
            "全局管理器",
            "子系统",
            "管理器",
        ),
    )


def _is_line_trace_request(requirement: str, target_type: str) -> bool:
    text = f"{requirement} {target_type}"
    return _contains_any(
        text,
        (
            "line trace",
            "linetrace",
            "line_trace",
            "raycast",
            "trace interaction",
            "linetracesinglebychannel",
            "射线交互",
            "射线检测",
            "射线",
            "交互射线",
        ),
    )


def _template_fallback_name(
    *,
    is_enhanced_input_character: bool,
    is_interaction_component: bool,
    is_subsystem: bool,
    is_line_trace: bool,
) -> str:
    if is_enhanced_input_character:
        return "EnhancedInputCharacter"
    if is_line_trace:
        return "LineTraceInteractionComponent"
    if is_interaction_component:
        return "InteractionComponent"
    if is_subsystem:
        return "GameFeatureSubsystem"
    return "GeneratedFeature"


def _language_from_file_path(file_path: str) -> str:
    lowered = file_path.lower()
    if lowered.endswith((".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cpp", ".cxx")):
        return "cpp"
    if lowered.endswith(".cs"):
        return "csharp"
    if lowered.endswith(".py"):
        return "python"
    return "text"


def _generated_items(code_draft: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": f"generated_{index}",
            "label": file_path.split("/")[-1],
            "file_path": file_path,
            "language": _language_from_file_path(file_path),
            "code": content,
            "write_status": "not_written",
            "is_virtual": True,
        }
        for index, (file_path, content) in enumerate(code_draft.items(), start=1)
    ]


def generate_code_draft(payload: dict[str, Any]) -> dict[str, Any]:
    requirement = str(payload.get("requirement_description") or payload.get("user_query") or "").strip()
    target_type = _normalize_target_type(str(payload.get("target_type") or "ue_cpp_class"))
    module_name = _module_name(payload)
    api_macro = _module_api_macro(module_name)
    is_enhanced_input_character = _is_enhanced_input_character_request(requirement, target_type)
    is_interaction_component = _is_interaction_component_request(requirement, target_type)
    is_subsystem = _is_subsystem_request(requirement, target_type)
    is_line_trace = _is_line_trace_request(requirement, target_type)
    class_name = _ue_class_name(
        requirement or target_type,
        fallback=_template_fallback_name(
            is_enhanced_input_character=is_enhanced_input_character,
            is_interaction_component=is_interaction_component,
            is_subsystem=is_subsystem,
            is_line_trace=is_line_trace,
        ),
    )
    reference_items = list(payload.get("reference_items") or [])
    reference_count = len(reference_items)
    extra_assumptions: list[str] = []
    extra_patch_steps: list[str] = []

    if is_enhanced_input_character:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "GameFramework/Character.h"
            #include "InputActionValue.h"
            #include "{class_name}.generated.h"

            class UInputAction;
            class UInputMappingContext;

            UCLASS()
            class {api_macro} A{class_name} : public ACharacter
            {{
                GENERATED_BODY()

            public:
                A{class_name}();

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
            }};
            """
        ).strip()
        source = dedent(
            f"""
            #include "{class_name}.h"

            #include "EnhancedInputComponent.h"
            #include "EnhancedInputSubsystems.h"
            #include "GameFramework/PlayerController.h"

            A{class_name}::A{class_name}()
            {{
                PrimaryActorTick.bCanEverTick = false;
            }}

            void A{class_name}::BeginPlay()
            {{
                Super::BeginPlay();

                if (APlayerController* PlayerController = Cast<APlayerController>(GetController()))
                {{
                    if (ULocalPlayer* LocalPlayer = PlayerController->GetLocalPlayer())
                    {{
                        if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
                            ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(LocalPlayer))
                        {{
                            Subsystem->AddMappingContext(DefaultMappingContext, 0);
                        }}
                    }}
                }}
            }}

            void A{class_name}::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
            {{
                Super::SetupPlayerInputComponent(PlayerInputComponent);

                UEnhancedInputComponent* EnhancedInputComponent = Cast<UEnhancedInputComponent>(PlayerInputComponent);
                if (!EnhancedInputComponent)
                {{
                    return;
                }}

                EnhancedInputComponent->BindAction(MoveAction, ETriggerEvent::Triggered, this, &A{class_name}::Move);
                EnhancedInputComponent->BindAction(LookAction, ETriggerEvent::Triggered, this, &A{class_name}::Look);
                EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
                EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
            }}

            void A{class_name}::Move(const FInputActionValue& Value)
            {{
                const FVector2D MovementVector = Value.Get<FVector2D>();

                if (Controller)
                {{
                    AddMovementInput(GetActorForwardVector(), MovementVector.Y);
                    AddMovementInput(GetActorRightVector(), MovementVector.X);
                }}
            }}

            void A{class_name}::Look(const FInputActionValue& Value)
            {{
                const FVector2D LookAxisVector = Value.Get<FVector2D>();

                AddControllerYawInput(LookAxisVector.X);
                AddControllerPitchInput(LookAxisVector.Y);
            }}
            """
        ).strip()
        code_draft = {
            f"Source/{module_name}/Public/{class_name}.h": header,
            f"Source/{module_name}/Private/{class_name}.cpp": source,
        }
        extra_assumptions.extend(
            [
                "Create Input Action assets for Move, Look, and Jump, then assign them on the Character class or Blueprint subclass.",
                "Create an Input Mapping Context asset and map movement/look/jump keys or axes in the editor.",
                f"Add `EnhancedInput` to the `{module_name}.Build.cs` dependency list before compiling.",
            ]
        )
        extra_patch_steps.extend(
            [
                f"Place the header under Source/{module_name}/Public and the source file under Source/{module_name}/Private.",
                f"Add `EnhancedInput` to PublicDependencyModuleNames or PrivateDependencyModuleNames in Source/{module_name}/{module_name}.Build.cs.",
                "Assign DefaultMappingContext, MoveAction, LookAction, and JumpAction in the Blueprint defaults.",
            ]
        )
    elif is_line_trace:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "Components/ActorComponent.h"
            #include "Engine/HitResult.h"
            #include "{class_name}.generated.h"

            UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
            class {api_macro} U{class_name} : public UActorComponent
            {{
                GENERATED_BODY()

            public:
                U{class_name}();

                UFUNCTION(BlueprintCallable, Category = "Interaction")
                AActor* TraceForInteractable() const;

            protected:
                UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
                float TraceDistance = 500.0f;

                UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
                TEnumAsByte<ECollisionChannel> TraceChannel = ECC_Visibility;

                UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
                bool bDrawDebug = false;
            }};
            """
        ).strip()
        source = dedent(
            f"""
            #include "{class_name}.h"

            #include "DrawDebugHelpers.h"
            #include "GameFramework/Actor.h"
            #include "GameFramework/Pawn.h"
            #include "GameFramework/PlayerController.h"

            U{class_name}::U{class_name}()
            {{
                PrimaryComponentTick.bCanEverTick = false;
            }}

            AActor* U{class_name}::TraceForInteractable() const
            {{
                const AActor* Owner = GetOwner();
                if (!Owner)
                {{
                    return nullptr;
                }}

                FVector ViewLocation = Owner->GetActorLocation();
                FRotator ViewRotation = Owner->GetActorRotation();

                if (const APawn* PawnOwner = Cast<APawn>(Owner))
                {{
                    if (const AController* Controller = PawnOwner->GetController())
                    {{
                        Controller->GetPlayerViewPoint(ViewLocation, ViewRotation);
                    }}
                }}

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
                {{
                    DrawDebugLine(GetWorld(), ViewLocation, End, bHit ? FColor::Green : FColor::Red, false, 1.0f);
                }}

                return bHit ? Hit.GetActor() : nullptr;
            }}
            """
        ).strip()
        code_draft = {
            f"Source/{module_name}/Public/{class_name}.h": header,
            f"Source/{module_name}/Private/{class_name}.cpp": source,
        }
        extra_assumptions.extend(
            [
                "This draft only finds an Actor; project-specific interaction usually calls an interface or component method on the hit Actor.",
                "Choose a trace channel that matches the project's collision setup.",
            ]
        )
        extra_patch_steps.extend(
            [
                f"Place the component under Source/{module_name}/Public and Source/{module_name}/Private.",
                "Add the component to the player character or controller-facing actor.",
                "Replace the returned Actor handling with your project interaction interface or gameplay event.",
            ]
        )
    elif is_interaction_component:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "Components/ActorComponent.h"
            #include "{class_name}.generated.h"

            class UPrimitiveComponent;

            UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
            class {api_macro} U{class_name} : public UActorComponent
            {{
                GENERATED_BODY()

            public:
                U{class_name}();

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
            }};
            """
        ).strip()
        source = dedent(
            f"""
            #include "{class_name}.h"

            #include "Components/PrimitiveComponent.h"
            #include "GameFramework/Actor.h"

            U{class_name}::U{class_name}()
            {{
                PrimaryComponentTick.bCanEverTick = false;
            }}

            void U{class_name}::BeginPlay()
            {{
                Super::BeginPlay();

                AActor* Owner = GetOwner();
                UPrimitiveComponent* Primitive = Owner ? Owner->FindComponentByClass<UPrimitiveComponent>() : nullptr;
                if (Primitive)
                {{
                    Primitive->OnComponentBeginOverlap.AddDynamic(this, &U{class_name}::HandleOwnerBeginOverlap);
                }}
            }}

            void U{class_name}::HandleOwnerBeginOverlap(
                UPrimitiveComponent* OverlappedComponent,
                AActor* OtherActor,
                UPrimitiveComponent* OtherComp,
                int32 OtherBodyIndex,
                bool bFromSweep,
                const FHitResult& SweepResult
            )
            {{
                if (!OtherActor || OtherActor == GetOwner())
                {{
                    return;
                }}

                // TODO: Replace with a project-specific interface call or gameplay event.
                UE_LOG(LogTemp, Verbose, TEXT("Interaction overlap with %s"), *OtherActor->GetName());
            }}
            """
        ).strip()
        code_draft = {
            f"Source/{module_name}/Public/{class_name}.h": header,
            f"Source/{module_name}/Private/{class_name}.cpp": source,
        }
        extra_assumptions.extend(
            [
                "The owner needs a UPrimitiveComponent with collision and Generate Overlap Events enabled.",
                "Project-specific interaction should usually call an interface instead of hard-coding target classes.",
            ]
        )
        extra_patch_steps.extend(
            [
                f"Place the component under Source/{module_name}/Public and Source/{module_name}/Private.",
                "Attach the component to an Actor that already owns a collision primitive.",
                "Replace the TODO with a project interaction interface call.",
            ]
        )
    elif is_subsystem:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "Subsystems/GameInstanceSubsystem.h"
            #include "{class_name}.generated.h"

            UCLASS()
            class {api_macro} U{class_name} : public UGameInstanceSubsystem
            {{
                GENERATED_BODY()

            public:
                virtual void Initialize(FSubsystemCollectionBase& Collection) override;
                virtual void Deinitialize() override;

                UFUNCTION(BlueprintCallable, Category = "Subsystem")
                void RegisterRuntimeObject(UObject* Object);

            private:
                UPROPERTY()
                TArray<TObjectPtr<UObject>> RuntimeObjects;
            }};
            """
        ).strip()
        source = dedent(
            f"""
            #include "{class_name}.h"

            void U{class_name}::Initialize(FSubsystemCollectionBase& Collection)
            {{
                Super::Initialize(Collection);
            }}

            void U{class_name}::Deinitialize()
            {{
                RuntimeObjects.Reset();
                Super::Deinitialize();
            }}

            void U{class_name}::RegisterRuntimeObject(UObject* Object)
            {{
                if (IsValid(Object))
                {{
                    RuntimeObjects.AddUnique(Object);
                }}
            }}
            """
        ).strip()
        code_draft = {
            f"Source/{module_name}/Public/{class_name}.h": header,
            f"Source/{module_name}/Private/{class_name}.cpp": source,
        }
        extra_assumptions.extend(
            [
                "GameInstanceSubsystem lives across map loads inside one game instance, so avoid storing level-only strong references unless they are cleaned up.",
                "Use a WorldSubsystem instead if the state should be world-specific.",
            ]
        )
        extra_patch_steps.extend(
            [
                f"Place the subsystem under Source/{module_name}/Public and Source/{module_name}/Private.",
                "Access it with GetGameInstance()->GetSubsystem<UYourSubsystem>() or a Blueprint callable helper.",
                "Decide whether this should be GameInstanceSubsystem or WorldSubsystem based on lifetime.",
            ]
        )
    elif target_type in {"actor", "ue_actor", "ue_cpp_class", "cpp_class"}:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "GameFramework/Actor.h"
            #include "{class_name}.generated.h"

            UCLASS()
            class {api_macro} A{class_name} : public AActor
            {{
                GENERATED_BODY()

            public:
                A{class_name}();

            protected:
                virtual void BeginPlay() override;

            public:
                virtual void Tick(float DeltaTime) override;
            }};
            """
        ).strip()
        source = dedent(
            f"""
            #include "{class_name}.h"

            A{class_name}::A{class_name}()
            {{
                PrimaryActorTick.bCanEverTick = true;
            }}

            void A{class_name}::BeginPlay()
            {{
                Super::BeginPlay();
            }}

            void A{class_name}::Tick(float DeltaTime)
            {{
                Super::Tick(DeltaTime);
            }}
            """
        ).strip()
        code_draft = {
            f"Source/{module_name}/Public/{class_name}.h": header,
            f"Source/{module_name}/Private/{class_name}.cpp": source,
        }
        extra_patch_steps.extend(
            [
                f"Place the header under Source/{module_name}/Public and the source file under Source/{module_name}/Private.",
                f"Confirm that `{api_macro}` matches the target module API macro.",
            ]
        )
    else:
        code_draft = {
            "GeneratedDraft.md": dedent(
                f"""
                Target Type: {target_type}
                Requirement:
                {requirement or "No detailed requirement was provided."}

                Suggested next step:
                - Define the target API surface.
                - Confirm the owning module and file placement.
                - Generate a concrete implementation draft after the schema/template is chosen.
                """
            ).strip()
        }

    generated_items = _generated_items(code_draft)
    generation_mode = "template_reference_augmented_fallback" if reference_count else "template_direct_fallback"
    return {
        "code_draft": code_draft,
        "file_structure_suggestions": list(code_draft.keys()),
        "generated_items": generated_items,
        "generation_mode": generation_mode,
        "write_policy": {
            "mode": "non_destructive",
            "written_to_disk": False,
            "message": "Generated items are virtual drafts returned in the API response; the backend does not create files.",
        },
        "explanation": (
            "Generated a non-destructive code draft."
            if not reference_count
            else "Generated a non-destructive code draft using retrieved code references as soft guidance."
        ),
        "assumptions": [
            "The generated draft is a starting point and still needs human review.",
            "Module names, API macros, and include paths may need project-specific adjustment.",
            *extra_assumptions,
        ],
        "known_risks": [
            "The class skeleton does not guarantee compile success in the target project.",
            "Behavioral logic is intentionally conservative because Phase 3 does not write directly into the workspace.",
        ],
        "patch_plan": [
            "Confirm module/API macro naming.",
            "Drop the generated files into the target module.",
            "Compile and iterate on warnings or missing includes.",
            *extra_patch_steps,
        ],
        "reference_summary": {
            "reference_count": reference_count,
            "reference_titles": [str(item.get("title") or "") for item in reference_items[:5] if item.get("title")],
        },
    }
