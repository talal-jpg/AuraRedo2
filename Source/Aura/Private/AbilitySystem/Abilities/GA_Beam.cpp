// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_Beam.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "GameplayCueManager.h"
#include "TimerManager.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Camera/CameraShakeBase.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "PlayerInput/MyPlayerController2.h"

DEFINE_LOG_CATEGORY_STATIC(LogBeam, Log, All);

namespace
{
	// Impacts sent by the server arrive with network jitter and frame rounding, so the client gate is this much shorter than the server's.
	// It still drops the server's copy of an impact this machine already played itself (that copy arrives about one round trip later)
	constexpr float ServerImpactGateSlack=0.25f;
	
	float ImpactGate(float MinInterval,float Duration,bool bFromServer)
	{
		const float Gate=FMath::Max(MinInterval,Duration);
		return bFromServer?FMath::Max(Gate-ServerImpactGateSlack,0.f):Gate;
	}
	
	/**
	 * How far (cm) the crosshair's hit on a character may lie from the server's beam line, and from that character's
	 * collision on the server, and still count, plus CharacterMoveSlackSeconds of the hit point's movement: the crosshair
	 * sweep's radius and the gap between where the client and the server see a character. The hit point must also be
	 * in the open from the beam's start, so no character is hit through a wall, and none more than this behind where
	 * the server's beam stops. Pawns (the airship's hull too) are no walls for these checks: the shooting client sees
	 * them at their lagged positions.
	 */
	constexpr double CharacterHitSlack=100.0;
	
	/**
	 * Seconds of the hit point's movement (the character's own, the base it stands on, a turning hull's) added to
	 * CharacterHitSlack: the server's copy of a moving character trails or leads the shooting client's.
	 */
	constexpr double CharacterMoveSlackSeconds=0.25;
	
	/**
	 * Point lies within Slack of Actor's collision as the server sees it: the nearest of its colliding components'
	 * simple collision, else (no simple collision) its colliding components' bounds.
	 */
	bool IsNearActorCollision(const AActor& Actor,const FVector& Point,const double Slack)
	{
		bool bMeasured=false;
		TInlineComponentArray<UPrimitiveComponent*> Primitives(&Actor);
		for (const UPrimitiveComponent* Primitive : Primitives)
		{
			if (!Primitive || !Primitive->IsRegistered() || !Primitive->IsQueryCollisionEnabled()) continue;
			// A character's skeletal mesh whose bones the server does not refresh (not rendered on this machine, the
			// default for characters) keeps its bodies in an old pose, e.g. the Burrower's body straight while it curves
			// on the client: here only its bounds sphere counts. Other meshes (the airship's) move rigidly with their
			// actor, so their bodies stay right
			const USkeletalMeshComponent* SkeletalMesh=Cast<USkeletalMeshComponent>(Primitive);
			if (SkeletalMesh && Actor.IsA<ACharacter>()
				&& SkeletalMesh->VisibilityBasedAnimTickOption!=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones
				&& !SkeletalMesh->WasRecentlyRendered(0.2f))
			{
				if (FVector::Dist(Point,SkeletalMesh->Bounds.Origin)<=SkeletalMesh->Bounds.SphereRadius+Slack) return true;
				bMeasured=true;
				continue;
			}
			FVector OnCollision;
			const float Distance=Primitive->GetDistanceToCollision(Point,OnCollision);
			if (Distance<0.f) continue;
			if (Distance<=Slack) return true;
			bMeasured=true;
		}
		if (bMeasured) return false;
		
		FVector Origin;
		FVector Extent;
		Actor.GetActorBounds(/*bOnlyCollidingComponents*/true,Origin,Extent);
		return !Extent.IsNearlyZero() && FBox(Origin-Extent,Origin+Extent).ComputeSquaredDistanceToPoint(Point)<=FMath::Square(Slack);
	}
}

void UGA_Beam::OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& Data)
{
	Super::OnServerMouseCursorData(Data);
	
	if (bApplyDamageOnRelease)
	{
		ApplyBeamDamage(Data);
	}
}

bool UGA_Beam::ApplyBeamDamage(const FGameplayAbilityTargetDataHandle& TargetData)
{
	TSharedPtr<FGameplayAbilityTargetData> Aim;
	if (TargetData.Num()>0)
	{
		Aim=TargetData.Data[0];
	}
	const FHitResult* AimHitPtr=Aim.IsValid()?Aim->GetHitResult():nullptr;
	// AT_SendMouseCursorData replays target data that arrived before it listened, and the graph may call this too: damage each aim once
	if (!AimHitPtr || Aim==LastDamagedTargetData) return false;
	
	AActor* Avatar=GetAvatarActorFromActorInfo();
	UAbilitySystemComponent* SourceASC=GetAbilitySystemComponentFromActorInfo();
	UWorld* World=Avatar?Avatar->GetWorld():nullptr;
	if (!World || !SourceASC || !Avatar->HasAuthority()) return false;
	LastDamagedTargetData=Aim;
	const FHitResult AimHit=*AimHitPtr;
	
	// Specs now, while the ability is active (its level, tags and source); they touch no Mass data
	const float Level=float(GetAbilityLevel());
	UMechSentinelSwarmSubsystem* Swarm=UMechSentinelSwarmSubsystem::Get(Avatar);
	const TSubclassOf<UGameplayEffect> CharacterEffect=Splash.CharacterDamageEffect
		?Splash.CharacterDamageEffect:TSubclassOf<UGameplayEffect>(UMySetByCallerDamageEffect::StaticClass());
	TSubclassOf<UGameplayEffect> SentinelEffect=Splash.SentinelDamageEffect;
	if (!SentinelEffect && Swarm)
	{
		SentinelEffect=Swarm->GetRules()->DefaultSentinelDamageEffect;
	}
	if (!SentinelEffect && Swarm && Swarm->HasAuthority())
	{
		UE_LOG(LogBeam,Warning,TEXT("%s: no sentinel damage effect, the beam won't hurt sentinels. Set Splash.SentinelDamageEffect, or DefaultSentinelDamageEffect in the GameMode's Sentinel Swarm Rules."),*GetName());
	}
	const auto MakeDamageSpec=[this,Level](const TSubclassOf<UGameplayEffect> Effect,const float Amount)
	{
		FGameplayEffectSpecHandle Spec=Effect?MakeOutgoingGameplayEffectSpec(Effect,Level):FGameplayEffectSpecHandle();
		if (Spec.IsValid())
		{
			Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller,Amount);
		}
		return Spec;
	};
	const float HitAmount=HitDamage.GetValueAtLevel(Level);
	const float SplashAmount=SplashDamage.GetValueAtLevel(Level);
	const FGameplayEffectSpecHandle HitCharacterSpec=bDamageHitEnemy?MakeDamageSpec(CharacterEffect,HitAmount):FGameplayEffectSpecHandle();
	const FGameplayEffectSpecHandle HitSentinelSpec=bDamageHitEnemy?MakeDamageSpec(SentinelEffect,HitAmount):FGameplayEffectSpecHandle();
	const FGameplayEffectSpecHandle SplashCharacterSpec=Splash.bDamageCharacters?MakeDamageSpec(CharacterEffect,SplashAmount):FGameplayEffectSpecHandle();
	const FGameplayEffectSpecHandle SplashSentinelSpec=Splash.bDamageSentinels?MakeDamageSpec(SentinelEffect,SplashAmount):FGameplayEffectSpecHandle();
	
	// The beam's line as the server sees it: along the aim, stopped by the first wall, the crosshair's hit or BeamRange
	FVector Start=FVector::ZeroVector;
	FVector End=FVector::ZeroVector;
	const bool bHasLine=UMechSentinelCombatLibrary::GetAimShotSegment(AimHit,*Avatar,BeamRange,Start,End);
	const FVector BeamDirection=bHasLine?(End-Start).GetSafeNormal():FVector::ZeroVector;
	
	// The character the crosshair hit, when it is an enemy the server's beam reaches. The client names both the actor and
	// the point, so the server checks them: the point must lie on the server's beam line (which stops at the first wall
	// the server finds, and after BeamRange), on that actor's collision where the server has it, and in the open from
	// the beam's start (no wall in between, the hit actor itself aside)
	AActor* const AimActor=AimHit.GetActor();
	const FVector HitPoint=AimHit.ImpactPoint;
	AActor* HitCharacter=bHasLine?UMySplashDamageLibrary::FindDamageableActor(AimActor):nullptr;
	if (HitCharacter && !UMySplashDamageLibrary::IsDamageableEnemy(HitCharacter,Avatar,bHitDamagesPlayers))
	{
		HitCharacter=nullptr;
	}
	if (HitCharacter)
	{
		const double Slack=CharacterHitSlack+UMechSentinelCombatLibrary::GetMoveVelocityAt(*HitCharacter,HitPoint).Size()*CharacterMoveSlackSeconds;
		const bool bOnBeam=FMath::PointDistToSegment(HitPoint,Start,End)<=Slack;
		const bool bOnCharacter=IsNearActorCollision(*AimActor,HitPoint,Slack)
			|| (HitCharacter!=AimActor && IsNearActorCollision(*HitCharacter,HitPoint,Slack));
		const TArray<const AActor*> HitActors={AimActor,HitCharacter};
		if (!bOnBeam || !bOnCharacter || !UMechSentinelCombatLibrary::IsAimPathClear(*Avatar,Start,HitPoint,HitActors))
		{
			HitCharacter=nullptr;
		}
	}
	
	// The hit and the splash land later this frame: hitting sentinels reads and writes Mass entities, which must not
	// happen while a Mass phase runs, and the host's release comes from input, in the middle of one. Timers run after
	// TG_PostPhysics, when every phase of the frame but FrameEnd is done (as GA_GunShoot)
	const TWeakObjectPtr<UWorld> WeakWorld(World);
	const TWeakObjectPtr<AActor> WeakAvatar(Avatar);
	const TWeakObjectPtr<UAbilitySystemComponent> WeakSourceASC(SourceASC);
	const TWeakObjectPtr<AActor> WeakHitCharacter(HitCharacter);
	const FMySplashDamageSettings SplashSettings=Splash;
	const bool bSplashOnlyOnEnemy=bSplashOnlyOnEnemyHit;
	const FGameplayTag CueTag=SplashGameplayCue;
	const float SentinelRadius=BeamSentinelRadius;
	const double Range=BeamRange;
	const FString AbilityName=GetName();
	
	World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateLambda([=]()
	{
		UWorld* WorldNow=WeakWorld.Get();
		AActor* AvatarNow=WeakAvatar.Get();
		if (!WorldNow || !AvatarNow) return;
		UMechSentinelSwarmSubsystem* SwarmNow=UMechSentinelSwarmSubsystem::Get(WorldNow);
		const bool bSentinels=SwarmNow && SwarmNow->HasAuthority();
		
		// First sentinel along the beam (the sweep is sorted along it). The query's round end cap also reaches sentinels
		// behind the beam's start, beside or behind the caster: those are not in the beam
		const auto AlongBeam=[&](const FVector& Point){ return FVector::DotProduct(Point-Start,BeamDirection); };
		FMechSentinelHit FirstSentinel;
		bool bHitSentinel=false;
		if (bHasLine && bSentinels)
		{
			TArray<FMechSentinelHit> LineHits;
			SwarmNow->QueryCapsule(Start,End,SentinelRadius,LineHits);
			for (const FMechSentinelHit& LineHit : LineHits)
			{
				if (AlongBeam(LineHit.ImpactPoint)>=0.0 && UMechSentinelCombatLibrary::IsSentinelAlive(WorldNow,LineHit.Sentinel))
				{
					FirstSentinel=LineHit;
					bHitSentinel=true;
					break;
				}
			}
		}
		
		AActor* HitCharacterNow=WeakHitCharacter.Get();
		UAbilitySystemComponent* HitCharacterASC=nullptr;
		if (HitCharacterNow)
		{
			HitCharacterASC=UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(HitCharacterNow);
			// Died since the release (another hit this frame)
			if (!HitCharacterASC || !UMySplashDamageLibrary::IsDamageableEnemy(HitCharacterNow,AvatarNow,true))
			{
				HitCharacterNow=nullptr;
				HitCharacterASC=nullptr;
			}
		}
		
		// The hit enemy is the first one along the beam
		if (bHitSentinel && HitCharacterNow && AlongBeam(HitPoint)<AlongBeam(FirstSentinel.ImpactPoint))
		{
			bHitSentinel=false;
		}
		else if (bHitSentinel)
		{
			HitCharacterNow=nullptr;
			HitCharacterASC=nullptr;
		}
		
		bool bHasCenter=true;
		FVector Center=FVector::ZeroVector;
		TArray<const AActor*> IgnoreActors;
		FMechSentinelHandle IgnoreSentinel;
		float HitDealt=0.f;
		if (bHitSentinel)
		{
			Center=FirstSentinel.ImpactPoint;
			IgnoreSentinel=FirstSentinel.Sentinel;
			if (HitSentinelSpec.IsValid())
			{
				HitDealt=SwarmNow->ApplyGameplayEffectSpecToSentinel(FirstSentinel.Sentinel.ToEntity(),*HitSentinelSpec.Data.Get(),&FirstSentinel.ImpactPoint);
			}
		}
		else if (HitCharacterNow)
		{
			Center=HitPoint;
			IgnoreActors.Add(HitCharacterNow);
			if (HitCharacterSpec.IsValid())
			{
				UMySplashDamageLibrary::ApplyScaledSpecToCharacter(*HitCharacterSpec.Data.Get(),*HitCharacterASC,1.f);
			}
		}
		else if (!bSplashOnlyOnEnemy)
		{
			// No enemy: splash where the server's beam stopped, if something stopped it (not at the end of its range in
			// the air). No beam line (it starts in a wall): no splash
			bHasCenter=bHasLine && FVector::Dist(Start,End)<Range-1.0;
			Center=End;
		}
		else
		{
			bHasCenter=false;
		}
		if (!bHasCenter) return;
		
		const FMySplashDamageResult Result=UMySplashDamageLibrary::ApplySplashDamageWithSpecs(*WorldNow,AvatarNow,Center,SplashSettings,
			SplashCharacterSpec,SplashSentinelSpec,IgnoreActors,IgnoreSentinel);
		
		UAbilitySystemComponent* SourceASCNow=WeakSourceASC.Get();
		if (CueTag.IsValid() && SourceASCNow)
		{
			FGameplayCueParameters CueParameters;
			CueParameters.Location=Center;
			CueParameters.RawMagnitude=SplashSettings.Radius;
			CueParameters.Instigator=AvatarNow;
			CueParameters.EffectCauser=AvatarNow;
			SourceASCNow->ExecuteGameplayCue(CueTag,CueParameters);
		}
		
		UE_LOG(LogBeam,Verbose,TEXT("%s: hit %s (%.1f sentinel damage), splash %d character(s) and %d sentinel(s) (%.1f sentinel damage)."),*AbilityName,
			bHitSentinel?TEXT("a sentinel"):(HitCharacterNow?*HitCharacterNow->GetName():TEXT("nothing")),HitDealt,Result.Characters.Num(),Result.Sentinels.Num(),Result.SentinelDamageDealt);
	}));
	return true;
}

void UGA_Beam::PlayBeamHitImpact(ACharacter* HitCharacter)
{
	if (!HitCharacter) return;
	APlayerController* HitPC=Cast<APlayerController>(HitCharacter->GetController());
	if (!HitPC) return;
	
	// Hit player on this machine (listen server host, or a client calling it for itself): play it here, no RPC needed
	if (HitPC->IsLocalController())
	{
		PlayBeamHitImpactLocal(HitPC);
		return;
	}
	
	// Remote hit player: same route as damage numbers, the server tells their own controller, which plays the effect on that machine
	if (!HitCharacter->HasAuthority()) return;
	if (AMyPlayerController2* MyHitPC=Cast<AMyPlayerController2>(HitPC))
	{
		// A continuous beam calls this every frame: only send the reliable RPC once the last impact is over
		const float Now=HitCharacter->GetWorld()->GetTimeSeconds();
		if (Now-MyHitPC->LastHitImpactSentTime<FMath::Max(HitImpactMinInterval,HitImpactDuration)) return;
		MyHitPC->LastHitImpactSentTime=Now;
		MyHitPC->Client_PlayBeamImpact(GetClass(),false);
	}
	else if (HitCameraShake)
	{
		// Not the mech controller, only the shake has a built in client RPC
		HitPC->ClientStartCameraShake(HitCameraShake,HitCameraShakeScale);
	}
}

void UGA_Beam::PlayBeamHitImpactLocal(APlayerController* HitPC,bool bFromServer) const
{
	AMyPlayerController2* MyPC=Cast<AMyPlayerController2>(HitPC);
	if (!MyPC || !MyPC->IsLocalController()) return;
	
	// A continuous beam hits every frame, only start a new impact once the last one is over
	const float Now=MyPC->GetWorld()->GetTimeSeconds();
	if (Now-MyPC->LastHitImpactStartTime<ImpactGate(HitImpactMinInterval,HitImpactDuration,bFromServer)) return;
	MyPC->LastHitImpactStartTime=Now;
	
	MyPC->StartHitImpact(HitPostProcessMaterial,HitImpactDuration,HitFOVOffset);
	
	if (HitCameraShake && MyPC->PlayerCameraManager)
	{
		MyPC->PlayerCameraManager->StartCameraShake(HitCameraShake,HitCameraShakeScale);
	}
}

void UGA_Beam::PlayBeamCastImpact(ACharacter* CasterCharacter)
{
	if (!CasterCharacter) return;
	AMyPlayerController2* CasterPC=Cast<AMyPlayerController2>(CasterCharacter->GetController());
	if (!CasterPC) return;
	
	// Caster on this machine (client, or the listen server host): play it here, no RPC needed
	if (CasterPC->IsLocalController())
	{
		PlayBeamCastImpactLocal(CasterPC);
		return;
	}
	
	// Remote caster: only the server can reach their screen
	if (!CasterCharacter->HasAuthority()) return;
	const float Now=CasterCharacter->GetWorld()->GetTimeSeconds();
	if (Now-CasterPC->LastCastImpactSentTime<FMath::Max(CastImpactMinInterval,CastImpactDuration)) return;
	CasterPC->LastCastImpactSentTime=Now;
	CasterPC->Client_PlayBeamImpact(GetClass(),true);
}

void UGA_Beam::PlayBeamCastImpactLocal(APlayerController* CasterPC,bool bFromServer) const
{
	AMyPlayerController2* MyPC=Cast<AMyPlayerController2>(CasterPC);
	if (!MyPC || !MyPC->IsLocalController()) return;
	
	const float Now=MyPC->GetWorld()->GetTimeSeconds();
	if (Now-MyPC->LastCastImpactStartTime<ImpactGate(CastImpactMinInterval,CastImpactDuration,bFromServer)) return;
	MyPC->LastCastImpactStartTime=Now;
	
	MyPC->StartHitImpact(CastPostProcessMaterial,CastImpactDuration,CastFOVOffset);
	
	if (CastCameraShake && MyPC->PlayerCameraManager)
	{
		MyPC->PlayerCameraManager->StartCameraShake(CastCameraShake,CastCameraShakeScale);
	}
}

// // Fill out your copyright notice in the Description page of Project Settings.
//
//
// #include "AbilitySystem/Abilities/GA_Beam.h"
//
// #include "AudioMixerBlueprintLibrary.h"
// #include "MyAnimInstance.h"
// #include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
// #include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
// #include "Character/MyCharPlayer.h"
// #include "Engine/World.h"
// #include "GameFramework/GameStateBase.h"
//
// void UGA_Beam::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo,
//                                const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
// {
// 	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
// 	
// 	UAbilityTask_PlayMontageAndWait* AT_PlayMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("foo"),BeamAbilityMontageCharge,1,FName("Default"));
// 	AT_PlayMontageAndWait->Activate();
// 	UAbilityTask_WaitInputRelease* WaitReleaseTask=UAbilityTask_WaitInputRelease::WaitInputRelease(this,false);
// 	WaitReleaseTask->OnRelease.AddDynamic(this,&ThisClass::OnInputReleasedCallback);
// 	WaitReleaseTask->ReadyForActivation();
// }
//
// void UGA_Beam::OnInputReleasedCallback(float TimeHeld)
// {
// 	UAbilityTask_PlayMontageAndWait* AT_PlayMontageAndWait=UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this,FName("foo"),BeamAbilityMontageRelease,1,FName("Release"));
// 	if (GetOwningActorFromActorInfo()->HasAuthority())
// 	{
// 		float TimeStamp= GetWorld()->GetGameState()->GetServerWorldTimeSeconds();
// 		float Duration=TimeHeld;
// 		Cast<AMyCharPlayer>(GetAvatarActorFromActorInfo())->Multicast_SetPhysicsState(TimeStamp,Duration);
// 	}
// 	AT_PlayMontageAndWait->OnCompleted.AddDynamic(this,&ThisClass::OnReleaseMontageCompleteCallback);
// 	AT_PlayMontageAndWait->ReadyForActivation();
// }
//
// void UGA_Beam::OnReleaseMontageCompleteCallback()
// {
// 	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,false,false);
// }
