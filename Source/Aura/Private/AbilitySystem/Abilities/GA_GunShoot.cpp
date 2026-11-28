// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_GunShoot.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "NiagaraDataChannel.h"
#include "TimerManager.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Airship/AirshipCannonball.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipTurret.h"
#include "Character/MyCharBase.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "PlayerInput/MyPlayerController2.h"

DEFINE_LOG_CATEGORY_STATIC(LogGunShoot, Log, All);

namespace MechSwarm::GunShootPrivate
{
	/** The airship Actor rides attached to (a turret, a gunner, something a gunner carries), or null. */
	const AAirshipPawn* GetShipCarrying(const AActor* Actor)
	{
		for (const AActor* Parent = Actor ? Actor->GetAttachParentActor() : nullptr; Parent; Parent = Parent->GetAttachParentActor())
		{
			if (const AAirshipPawn* Ship = Cast<AAirshipPawn>(Parent))
			{
				return Ship;
			}
		}
		return nullptr;
	}

	/** How far MyFunc's impact point may be from the last crosshair hit for that line to count as this shot's (cm). */
	constexpr double SameShotTolerance = 100.0;
}

void UGA_GunShoot::OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& Data)
{
	Super::OnServerMouseCursorData(Data);

	// The shot's line for MyFunc (it gets only the impact point and the actor), whatever the sentinel setting
	if (const FGameplayAbilityTargetData* First = Data.Get(0))
	{
		if (const FHitResult* Hit = First->GetHitResult())
		{
			LastAimTraceStart = Hit->TraceStart;
			LastAimImpact = Hit->ImpactPoint;
			bHasLastAim = !LastAimTraceStart.ContainsNaN() && !LastAimImpact.ContainsNaN();
		}
	}

	if (!bDamageSentinels)
	{
		return;
	}

	TSharedPtr<FGameplayAbilityTargetData> Shot;
	if (Data.Num() > 0)
	{
		Shot = Data.Data[0];
	}
	const FHitResult* AimHit = Shot.IsValid() ? Shot->GetHitResult() : nullptr;
	// AT_SendMouseCursorData replays target data that arrived before it listened, and every one of its tasks waiting
	// when a shot arrives gets that shot: damage each shot once.
	if (!AimHit || Shot == LastSentinelShot)
	{
		return;
	}
	LastSentinelShot = Shot;

	AActor* Avatar = GetAvatarActorFromActorInfo();
	UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	UMechSentinelSwarmSubsystem* Swarm = World ? UMechSentinelSwarmSubsystem::Get(Avatar) : nullptr;
	if (!Swarm || !Swarm->HasAuthority())
	{
		return;
	}

	FVector Start, End;
	if (!GetSentinelShotSegment(*AimHit, *Avatar, Start, End))
	{
		return;
	}

	const TSubclassOf<UGameplayEffect> EffectClass = SentinelDamageEffect ? SentinelDamageEffect : Swarm->GetRules()->DefaultSentinelDamageEffect;
	if (!EffectClass)
	{
		UE_LOG(LogGunShoot, Warning, TEXT("%s: no sentinel damage effect. Set SentinelDamageEffect, or DefaultSentinelDamageEffect in the GameMode's Sentinel Swarm Rules."), *GetName());
		return;
	}

	// The spec is made now, while the ability is active (its level, tags and source); it touches no Mass data.
	const float Level = float(GetAbilityLevel());
	const FGameplayEffectSpecHandle Spec = MakeOutgoingGameplayEffectSpec(EffectClass, Level);
	if (!Spec.IsValid())
	{
		return;
	}
	const float BaseDamage = GetSentinelBaseDamage(Level);
	Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, BaseDamage);
	UE_LOG(LogGunShoot, Verbose, TEXT("%s: sentinel base damage %.1f (%s)."), *GetName(), BaseDamage,
		bSentinelDamageFromDamageEffect && DamageEffectClass ? *GetNameSafe(DamageEffectClass) : TEXT("SentinelDamage"));

	// Hitting sentinels reads and writes Mass entities, which must not happen while a Mass phase runs, and this can be
	// called in the middle of one (the host's shot comes from input, in TG_PrePhysics). Timers run after TG_PostPhysics,
	// when every phase of the frame but FrameEnd is done, so the hit lands later this same frame.
	const TWeakObjectPtr<UMechSentinelSwarmSubsystem> WeakSwarm(Swarm);
	const float Radius = SentinelShotRadius;
	const int32 MaxTargets = SentinelMaxTargets;
	World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateLambda([WeakSwarm, Spec, Start, End, Radius, MaxTargets]()
	{
		UMechSentinelSwarmSubsystem* SwarmNow = WeakSwarm.Get();
		TArray<FMechSentinelHit> Hits;
		if (SwarmNow && SwarmNow->QueryCapsule(Start, End, Radius, Hits) > 0)
		{
			float TotalDamage = 0.f;
			const int32 Applied = UMechSentinelCombatLibrary::ApplySpecToHits(*SwarmNow, *Spec.Data.Get(), Hits, MaxTargets, &TotalDamage);
			UE_LOG(LogGunShoot, Verbose, TEXT("Shot hit %d sentinel(s) for %.1f damage."), Applied, TotalDamage);
		}
	}));
}

float UGA_GunShoot::GetSentinelBaseDamage(const float Level) const
{
	const float Fallback = SentinelDamage.GetValueAtLevel(Level);
	if (!bSentinelDamageFromDamageEffect || !DamageEffectClass)
	{
		return Fallback;
	}

	// A spec like the one the character path applies (MyFunc sets SetDamageByCaller to 1), so source captures and
	// SetByCaller magnitudes read the same. Needs the ability's actor info: outside an activation this is the fallback.
	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(DamageEffectClass, Level);
	if (!SpecHandle.IsValid() || !SpecHandle.Data->Def)
	{
		return Fallback;
	}
	SpecHandle.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, 1.f);

	float Damage = 0.f;
	bool bFoundDamage = false;
	for (const FGameplayModifierInfo& Modifier : SpecHandle.Data->Def->Modifiers)
	{
		if (Modifier.Attribute != UMyAttributeSet::GetIncomingDamageAttribute() || Modifier.ModifierOp != EGameplayModOp::Additive)
		{
			continue;
		}
		float Magnitude = 0.f;
		if (!Modifier.ModifierMagnitude.AttemptCalculateMagnitude(*SpecHandle.Data.Get(), Magnitude, /*WarnIfSetByCallerFail*/ false))
		{
			// A magnitude that needs the target (or a custom calculation that failed): don't guess a partial value.
			return Fallback;
		}
		Damage += Magnitude;
		bFoundDamage = true;
	}
	// No IncomingDamage modifier (e.g. an execution calculation does the damage): SentinelDamage.
	return bFoundDamage ? FMath::Max(0.f, Damage) : Fallback;
}

bool UGA_GunShoot::GetSentinelShotSegment(const FHitResult& AimHit, const AActor& Avatar, FVector& OutStart, FVector& OutEnd) const
{
	return UMechSentinelCombatLibrary::GetAimShotSegment(AimHit, Avatar, SentinelShotRange, OutStart, OutEnd);
}

FVector UGA_GunShoot::GetShotDirection(const FVector& ImpactPoint) const
{
	using namespace MechSwarm::GunShootPrivate;

	// This shot's crosshair line (the camera's), when the last target data is this hit's; else from the pawn's view
	FVector Origin = FVector::ZeroVector;
	if (bHasLastAim && FVector::DistSquared(LastAimImpact, ImpactPoint) <= FMath::Square(SameShotTolerance))
	{
		Origin = LastAimTraceStart;
	}
	else if (const APawn* Pawn = Cast<APawn>(GetAvatarActorFromActorInfo()))
	{
		Origin = Pawn->GetPawnViewLocation();
	}
	else
	{
		return FVector::ZeroVector;
	}
	return (ImpactPoint - Origin).GetSafeNormal();
}

void UGA_GunShoot::MyFunc(FVector InImpactPoint,AActor* InTargetActor)
{
		using namespace MechSwarm::GunShootPrivate;
		AActor* Avatar = GetAvatarActorFromActorInfo();
		const ACharacter* Shooter = Cast<ACharacter>(Avatar);

		// Airship cannonballs block Visibility and have health in gun units (no ASC): the server counts the hit
		if (AAirshipCannonball* Ball = Cast<AAirshipCannonball>(InTargetActor))
		{
			if (Avatar && Avatar->HasAuthority())
			{
				// No friendly fire on the balls of the ship the shooter rides (deck, helm or gun station), like the
				// ship's own turrets, nor in a match on the balls of a teammate's ship (the ball's team is stored at
				// launch, so it holds after its ship is gone); the ball still took the shot
				const AAirshipPawn* BallShip = Ball->GetSourceShip();
				const bool bOwnShip = BallShip && Shooter && BallShip->IsRiderForDamage(Shooter);
				if (!bOwnShip && !UMyTeamLibrary::IsFriendlyFireBlocked(Avatar, Ball))
				{
					Ball->ApplyShotDamage(CannonballShotUnits, Avatar);
				}
			}
			return;
		}

		// A ship's turrets sit inside its hull's forward-deck collision, so the crosshair stops on the hull in front of
		// them: a hull hit over that deck goes on to the turret behind it (AAirshipPawn::FindTurretBehindHullHit)
		if (const AAirshipPawn* HitShip = Cast<AAirshipPawn>(InTargetActor))
		{
			FHitResult TurretHit;
			if (AAirshipTurret* Turret = HitShip->FindTurretBehindHullHit(InImpactPoint, GetShotDirection(InImpactPoint), TurretHit))
			{
				InTargetActor = Turret;
				InImpactPoint = TurretHit.ImpactPoint;
			}
		}

		// No friendly fire on what rides attached to the shooter's own ship (its turrets, its gunners): a deck rider or
		// a gunner shooting over the forward deck would otherwise wreck its own turrets. The same rule as the balls above.
		if (const AAirshipPawn* CarrierShip = GetShipCarrying(InTargetActor))
		{
			if (Shooter && CarrierShip->IsRiderForDamage(Shooter))
			{
				return;
			}
		}

		// Match: no damage to teammates, their ship or its turrets unless the rules allow friendly fire. Both machines
		// decide the same from replicated team ids; only the server's damage counts
		if (UMyTeamLibrary::IsFriendlyFireBlocked(Avatar, InTargetActor))
		{
			return;
		}

		// Match: a team ship or its turret takes a fixed amount per hit instead of DamageEffectClass's value, which differs
		// by 1000x between trees and would decide ship lives on its own. Through the ship's (turret's) own damage path, with
		// the shooter in the effect context; 0 = the effect's value below
		const float FixedShipDamage = UMyMatchSettings::Get()->ShipDamageGunHit;
		if (FixedShipDamage > 0.f && UMyTeamLibrary::IsTeamShipTarget(InTargetActor))
		{
			if (Avatar && Avatar->HasAuthority())
			{
				if (AAirshipPawn* TargetShip = Cast<AAirshipPawn>(InTargetActor))
				{
					TargetShip->ApplyShipDamage(FixedShipDamage, Avatar);
				}
				else if (AAirshipTurret* TargetTurret = Cast<AAirshipTurret>(InTargetActor))
				{
					TargetTurret->ApplyTurretDamage(FixedShipDamage, Avatar);
				}
			}
			return;
		}

		// Characters and any other GAS actor whose ASC has UMyAttributeSet (AAirshipPawn)
		if (AActor* TargetActor=InTargetActor)
		{
			// FVector LaunchVel=(TargetActor->GetActorLocation()- InImpactPoint).GetSafeNormal();
			// UKismetSystemLibrary::DrawDebugArrow(InTargetActor,TargetActor->GetActorLocation(),TargetActor->GetActorLocation()+LaunchVel*500,100,FLinearColor::Black,30);
			// LaunchVel*=100;
			// TargetActor->LaunchCharacter(LaunchVel,false,false);
			if (IAbilitySystemInterface* AscIF=Cast<IAbilitySystemInterface>(TargetActor))
			{
				FString Name=TargetActor->GetName();
				UKismetSystemLibrary::PrintString(this,TEXT("HitActor: ") + Name);
				TargetAsc=AscIF->GetAbilitySystemComponent();
				
				
				
				//Make GESpec With Own ASC
				UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
				// UMyAttributeSet* MyAttributeSet=Cast<AMyCharBase>(GetAvatarActorFromActorInfo())->GetMyAttributeSet();
				const UMyAttributeSet* TargetAttributeSet=TargetAsc?TargetAsc->GetSet<UMyAttributeSet>():nullptr;
				if (!TargetAttributeSet)return;
				FGameplayEffectContextHandle GEContext=ASC->MakeEffectContext();
				FGameplayEffectSpecHandle GESpecHandle=ASC->MakeOutgoingSpec(DamageEffectClass,1,GEContext);
				//TODO Replace by AttackDamage When add and figure out attrs
				// float Magnitude=MyAttributeSet->GetStrength();
				float Magnitude=1;
				UAbilitySystemBlueprintLibrary::AssignTagSetByCallerMagnitude(GESpecHandle,MyTags::SetDamageByCaller,Magnitude);
				
				float IncomingDamage= TargetAttributeSet->GetIncomingDamage();
				float PrevHealth=TargetAttributeSet->GetHealth();
				ASC->ApplyGameplayEffectSpecToTarget(*GESpecHandle.Data.Get(),TargetAsc);
				float NewHealth=TargetAttributeSet->GetHealth();
				UKismetSystemLibrary::PrintString(this,TEXT("PrevHealth: ") + FString::FromInt(PrevHealth));
				UKismetSystemLibrary::PrintString(this,TEXT("NewHealth: ") + FString::FromInt(NewHealth));
				UKismetSystemLibrary::PrintString(this,TEXT("IncomingDamage: ") + FString::FromInt(IncomingDamage));
				
				
			}
		}
			//TODO Write to NiagarDC from here remove getting controller in bp
			//UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel()
}
