// Editor-only console command: Aura.ClearConnectedRootConstants <MaterialPath> [<MaterialPath> ...]
// The material editor stores an inline constant (UseConstant) on every unconnected output pin when a material is saved.
// If that output is wired up later outside the material editor (MaterialEditingLibrary, MCP tools), UseConstant stays
// set and the compiler keeps using the constant and ignores the wire. That is why M_MasterMechDissolve (a copy of
// M_MasterMech) never clipped its opacity mask or showed the disintegration glow. This clears UseConstant on every
// output that has an expression connected, then recompiles; save the material afterwards.
#if WITH_EDITOR
#include "HAL/IConsoleManager.h"
#include "Materials/Material.h"

namespace
{
	void ClearConnectedRootConstants(const TArray<FString>& Args)
	{
		for (const FString& Path : Args)
		{
			UMaterial* Material=LoadObject<UMaterial>(nullptr,*Path);
			UMaterialEditorOnlyData* Data=Material ? Material->GetEditorOnlyData() : nullptr;
			if (!Data)
			{
				UE_LOG(LogTemp,Warning,TEXT("Aura.ClearConnectedRootConstants: no material at %s"),*Path);
				continue;
			}
			TArray<FString> Cleared;
			auto Fix=[&Cleared](auto& Input, const TCHAR* Name)
			{
				if (Input.Expression && Input.UseConstant)
				{
					Input.UseConstant=false;
					Cleared.Add(Name);
				}
			};
			Fix(Data->BaseColor,TEXT("BaseColor"));
			Fix(Data->Metallic,TEXT("Metallic"));
			Fix(Data->Specular,TEXT("Specular"));
			Fix(Data->Roughness,TEXT("Roughness"));
			Fix(Data->Normal,TEXT("Normal"));
			Fix(Data->EmissiveColor,TEXT("EmissiveColor"));
			Fix(Data->Opacity,TEXT("Opacity"));
			Fix(Data->OpacityMask,TEXT("OpacityMask"));
			Fix(Data->SubsurfaceColor,TEXT("SubsurfaceColor"));
			Fix(Data->AmbientOcclusion,TEXT("AmbientOcclusion"));
			Fix(Data->Refraction,TEXT("Refraction"));
			Material->PreEditChange(nullptr);
			Material->PostEditChange();
			Material->MarkPackageDirty();
			UE_LOG(LogTemp,Warning,TEXT("Aura.ClearConnectedRootConstants: %s cleared [%s]"),*Path,*FString::Join(Cleared,TEXT(", ")));
		}
	}

	FAutoConsoleCommand GClearConnectedRootConstants(
		TEXT("Aura.ClearConnectedRootConstants"),
		TEXT("Clear the inline constant on every connected output pin of the given materials (paths), so the wires are used."),
		FConsoleCommandWithArgsDelegate::CreateStatic(&ClearConnectedRootConstants));
}
#endif
