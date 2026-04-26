# Enhanced Input Build.cs Dependency Note

domain: examples
topic: Enhanced Input Build.cs dependency
keywords: EnhancedInput, Build.cs, PublicDependencyModuleNames, PrivateDependencyModuleNames, 角色增强输入, 增强输入模块依赖
use_for: Code Generate, Code Review, Project QA

## Minimal Pattern

For a normal Unreal C++ game module, add `EnhancedInput` to the dependency list before compiling Enhanced Input C++ code.

```csharp
PublicDependencyModuleNames.AddRange(new string[]
{
    "Core",
    "CoreUObject",
    "Engine",
    "InputCore",
    "EnhancedInput"
});
```

If the Enhanced Input code is only used by private implementation files, placing `EnhancedInput` in `PrivateDependencyModuleNames` can also be appropriate. Keep the final placement consistent with the module's existing dependency style.

