// Fill out your copyright notice in the Description page of Project Settings.

using UnrealBuildTool;

public class Aura : ModuleRules
{
	public Aura(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore","EnhancedInput", "GameplayAbilities","NavigationSystem","UMG","GameplayTasks","Niagara", "OnlineSubsystem", "OnlineSubsystemUtils", "OnlineSubsystemSteam" });

		PrivateDependencyModuleNames.AddRange(new string[] { "GameplayTags","GameplayTasks","NetCore", "OnlineSubsystemUtils", "PCG","ApplicationCore","DeveloperSettings","GeometryCollectionEngine","Chaos","Slate","SlateCore","EngineSettings","CoreOnline" });

		// Mech Sentinel swarm (Source/Aura/*/MechSwarm). Needs the MassGameplay plugin (enabled in Aura.uproject).
		PublicDependencyModuleNames.AddRange(new string[] { "MassEntity", "MassCore", "MassCommon", "MassSpawner", "MassSimulation", "MassLOD", "MassReplication" });

		// Burrower (Source/Aura/*/Burrower): AAIController possesses it so its movement runs on the server.
		PrivateDependencyModuleNames.AddRange(new string[] { "AIModule" });

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		
		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
