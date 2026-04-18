from __future__ import annotations

from textwrap import dedent
from typing import Any


def _ue_class_name(requirement_description: str, fallback: str = "GeneratedFeature") -> str:
    words = [item for item in requirement_description.replace("-", " ").replace("_", " ").split() if item]
    if not words:
        return fallback
    return "".join(word[:1].upper() + word[1:] for word in words[:4])


def generate_code_draft(payload: dict[str, Any]) -> dict[str, Any]:
    requirement = str(payload.get("requirement_description") or payload.get("user_query") or "").strip()
    target_type = str(payload.get("target_type") or "ue_cpp_class").strip().lower()
    class_name = _ue_class_name(requirement or target_type)

    if target_type in {"actor", "ue_actor", "ue_cpp_class", "cpp_class"}:
        header = dedent(
            f"""
            #pragma once

            #include "CoreMinimal.h"
            #include "GameFramework/Actor.h"
            #include "{class_name}.generated.h"

            UCLASS()
            class A{class_name} : public AActor
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
            f"Source/{class_name}.h": header,
            f"Source/{class_name}.cpp": source,
        }
    else:
        code_draft = {
            "draft.txt": dedent(
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

    return {
        "code_draft": code_draft,
        "file_structure_suggestions": list(code_draft.keys()),
        "explanation": (
            "Generated a non-destructive code draft. The backend is only proposing files and skeletons in Phase 3."
        ),
        "assumptions": [
            "The generated draft is a starting point and still needs human review.",
            "Module names, API macros, and include paths may need project-specific adjustment.",
        ],
        "known_risks": [
            "The class skeleton does not guarantee compile success in the target project.",
            "Behavioral logic is intentionally conservative because Phase 3 does not write directly into the workspace.",
        ],
        "patch_plan": [
            "Confirm module/API macro naming.",
            "Drop the generated files into the target module.",
            "Compile and iterate on warnings or missing includes.",
        ],
    }
