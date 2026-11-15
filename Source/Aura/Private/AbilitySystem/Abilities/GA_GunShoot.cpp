// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_GunShoot.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "NiagaraDataChannel.h"
#include "TimerManager.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyCharBase.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Kismet/KismetSystemLibrary.h"
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "PlayerInput/MyPlayerController2.h"

DEFINE_LOG_CATEGORY_STATIC(LogGunShoot, Log, All);

namespace MechSwarm::GunShootPrivate
{
	/**
	 * Farthest the aim trace may start from the shooter (cm). The aim comes from the client's target data: an origin
	 * beyond any camera distance (a modified client, or a broken trace) shoots from the pawn's own view instead.
	 */
	constexpr double MaxAimOriginDistance = 5000.0;
}

void UGA_GunShoot::OnServerMouseCursorData(const FGameplayAbilityTargetDataHandle& Data)
{
	Super::OnServerMouseCursorData(Data);

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
	Spec.Data->SetSetByCallerMagnitude(MyTags::SetDamageByCaller, SentinelDamage.GetValueAtLevel(Level));

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

bool UGA_GunShoot::GetSentinelShotSegment(const FHitResult& AimHit, const AActor& Avatar, FVector& OutStart, FVector& OutEnd) const
{
	// Along the aim trace: from the camera through the crosshair. MyPlayerController2's trace ends FLT_MAX away, so the
	// vector is scaled into a sane range before it is normalized.
	FVector Origin = AimHit.TraceStart;
	FVector Direction = (AimHit.bBlockingHit ? FVector(AimHit.Location) : FVector(AimHit.TraceEnd)) - Origin;
	const double Largest = Direction.GetAbsMax();
	Direction = (!Direction.ContainsNaN() && FMath::IsFinite(Largest) && Largest > UE_KINDA_SMALL_NUMBER)
		? (Direction / Largest).GetSafeNormal()
		: FVector::ZeroVector;

	const bool bOriginNearShooter = !Origin.ContainsNaN()
		&& FVector::DistSquared(Origin, Avatar.GetActorLocation()) <= FMath::Square(MechSwarm::GunShootPrivate::MaxAimOriginDistance);
	const bool bUseAimTrace = bOriginNearShooter && !Direction.IsNearlyZero();
	if (!bUseAimTrace)
	{
		// No usable aim trace: shoot where the pawn looks.
		const APawn* Pawn = Cast<APawn>(&Avatar);
		if (!Pawn)
		{
			return false;
		}
		Origin = Pawn->GetPawnViewLocation();
		Direction = Pawn->GetBaseAimRotation().Vector();
	}

	// From the shooter rather than from the camera behind it: nothing between the camera and the character is hit.
	const double AvatarAlongShot = FVector::DotProduct(Avatar.GetActorLocation() - Origin, Direction);
	OutStart = Origin + Direction * FMath::Max(0.0, AvatarAlongShot);

	// Walls and characters stop the shot: end at the aim trace's blocking hit when it lies ahead of the shooter.
	double Range = SentinelShotRange;
	if (bUseAimTrace && AimHit.bBlockingHit)
	{
		const double BlockAlongShot = FVector::DotProduct(FVector(AimHit.Location) - OutStart, Direction);
		if (BlockAlongShot > 0.0)
		{
			Range = FMath::Min(Range, BlockAlongShot);
		}
	}
	OutEnd = OutStart + Direction * Range;
	return true;
}

void UGA_GunShoot::MyFunc(FVector InImpactPoint,AActor* InTargetActor)
{
		if (AMyCharBase* TargetActor=Cast<AMyCharBase>(InTargetActor))
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
				UMyAttributeSet* TargetAttributeSet=Cast<AMyCharBase>(InTargetActor)->GetMyAttributeSet();
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
