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
#include "MechSwarm/Combat/MechSentinelCombatLibrary.h"
#include "MechSwarm/Core/MechSentinelSwarmRules.h"
#include "MechSwarm/Core/MechSentinelSwarmSubsystem.h"
#include "PlayerInput/MyPlayerController2.h"

DEFINE_LOG_CATEGORY_STATIC(LogGunShoot, Log, All);

namespace MechSwarm::GunShootPrivate
{
	/**
	 * The aim comes from the client's target data, so the server bounds it. Farthest the aim trace may start from the
	 * shooter (cm), a sanity bound on the camera position.
	 */
	constexpr double MaxAimOriginDistance = 5000.0;

	/**
	 * Farthest the shot's line may pass from the shooter (cm), plus how far the shooter moves in MoveSlackSeconds. A
	 * crosshair ray passes the character within the camera's offset (arm height, socket offset, camera lag), and the
	 * server's character trails the client's. Beyond that (a modified client, or a broken trace) the shot follows the
	 * pawn's own view instead.
	 */
	constexpr double MaxShotLineOffset = 300.0;
	constexpr double MoveSlackSeconds = 0.25;

	/** Characters in a row the wall trace looks past; the next one counts as a wall. */
	constexpr int32 MaxCharactersSkipped = 8;

	/** The point of the line closest to Location, but never behind Origin. */
	FVector StartOnLine(const FVector& Origin, const FVector& Direction, const FVector& Location)
	{
		return Origin + Direction * FMath::Max(0.0, FVector::DotProduct(Location - Origin, Direction));
	}

	/** The pawn that Actor is, or is attached to (a character's weapon, for example). */
	const APawn* GetCharacterOf(const AActor* Actor)
	{
		for (; Actor; Actor = Actor->GetAttachParentActor())
		{
			if (const APawn* Pawn = Cast<APawn>(Actor))
			{
				return Pawn;
			}
		}
		return nullptr;
	}

	/**
	 * The first wall from From to To: the first blocking hit on the crosshair trace's channel that is not part of a
	 * character. Characters (pawns, their components and attached actors, whatever their collision profiles) are looked
	 * past, because their positions on the server differ from what the shooting client saw. A character stops the shot
	 * only when it is the client's own crosshair hit (see GetSentinelShotSegment). The characters looked past are added
	 * to Params.
	 */
	bool TraceWall(const UWorld& World, const FVector& From, const FVector& To, FCollisionQueryParams& Params,
		const FCollisionResponseParams& Responses, FHitResult& OutWall)
	{
		for (int32 Skipped = 0; ; ++Skipped)
		{
			if (!World.LineTraceSingleByChannel(OutWall, From, To, ECC_Visibility, Params, Responses))
			{
				return false;
			}
			const APawn* Character = GetCharacterOf(OutWall.GetActor());
			if (!Character || Skipped >= MaxCharactersSkipped)
			{
				return true;
			}
			TArray<AActor*> Attached;
			Character->GetAttachedActors(Attached, /*bResetArray*/ true, /*bRecursivelyIncludeAttachedActors*/ true);
			Params.AddIgnoredActor(Character);
			Params.AddIgnoredActors(Attached);
			Params.AddIgnoredActor(OutWall.GetActor());
		}
	}

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
	using namespace MechSwarm::GunShootPrivate;
	const UWorld* World = Avatar.GetWorld();
	if (!World)
	{
		return false;
	}
	const FVector AvatarLocation = Avatar.GetActorLocation();

	// The server traces the walls itself, whatever the client reports: the crosshair trace's channel with complex
	// collision, without the shooter and its attachments. The Pawn object type is skipped here, and TraceWall looks past
	// the rest of every character.
	FCollisionQueryParams Params(SCENE_QUERY_STAT(GunShootSentinelWalls), /*bTraceComplex*/ true, &Avatar);
	TArray<AActor*> Attached;
	Avatar.GetAttachedActors(Attached, /*bResetArray*/ true, /*bRecursivelyIncludeAttachedActors*/ true);
	Params.AddIgnoredActors(Attached);
	FCollisionResponseParams Responses;
	Responses.CollisionResponse.SetResponse(ECC_Pawn, ECR_Ignore);
	FHitResult Wall;

	// The shot starts at the point of its line nearest the shooter, so nothing between the camera and the character is
	// hit. No wall may lie between the shooter's capsule centre (which movement keeps out of walls) and that point.
	const auto IsStartInTheOpen = [&]()
	{
		return FVector::DistSquared(AvatarLocation, OutStart) <= 1.0
			|| !TraceWall(*World, AvatarLocation, OutStart, Params, Responses, Wall);
	};

	// Along the aim trace: from the camera through the crosshair. The direction comes from the trace's own end, which is
	// right even when the sweep started inside something (its hit is then at its start). MyPlayerController2's trace ends
	// FLT_MAX away, so the vector is scaled into a sane range before it is normalized.
	FVector Origin = AimHit.TraceStart;
	FVector Direction = FVector(AimHit.TraceEnd) - Origin;
	const double Largest = Direction.GetAbsMax();
	Direction = (!Direction.ContainsNaN() && FMath::IsFinite(Largest) && Largest > UE_KINDA_SMALL_NUMBER)
		? (Direction / Largest).GetSafeNormal()
		: FVector::ZeroVector;

	// The client sends the aim. It is used when the camera is near the shooter, its line passes close to the shooter,
	// and the shot's start is in the open.
	bool bUseAimTrace = !Origin.ContainsNaN() && !Direction.IsNearlyZero()
		&& FVector::DistSquared(Origin, AvatarLocation) <= FMath::Square(MaxAimOriginDistance);
	if (bUseAimTrace)
	{
		OutStart = StartOnLine(Origin, Direction, AvatarLocation);
		const double MaxOffset = MaxShotLineOffset + Avatar.GetVelocity().Size() * MoveSlackSeconds;
		bUseAimTrace = FVector::DistSquared(OutStart, AvatarLocation) <= FMath::Square(MaxOffset) && IsStartInTheOpen();
	}
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
		OutStart = StartOnLine(Origin, Direction, AvatarLocation);
		if (!IsStartInTheOpen())
		{
			return false;
		}
	}

	// The crosshair trace's first hit stops the shot, when it lies ahead of the shooter: the only stop at characters.
	double Range = SentinelShotRange;
	if (bUseAimTrace && AimHit.bBlockingHit)
	{
		const double BlockAlongShot = FVector::DotProduct(FVector(AimHit.Location) - OutStart, Direction);
		if (BlockAlongShot > 0.0)
		{
			Range = FMath::Min(Range, BlockAlongShot);
		}
	}

	// Walls stop it at the first one the server finds.
	if (TraceWall(*World, OutStart, OutStart + Direction * Range, Params, Responses, Wall))
	{
		Range = Wall.bStartPenetrating ? 0.0 : FMath::Min(Range, double(Wall.Distance));
	}
	if (Range <= UE_KINDA_SMALL_NUMBER)
	{
		// The line starts in a wall.
		return false;
	}
	OutEnd = OutStart + Direction * Range;
	return true;
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
				// ship's own turrets; the ball still took the shot
				const AAirshipPawn* BallShip = Ball->GetSourceShip();
				const bool bOwnShip = BallShip && Shooter && BallShip->IsRiderForDamage(Shooter);
				if (!bOwnShip)
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
