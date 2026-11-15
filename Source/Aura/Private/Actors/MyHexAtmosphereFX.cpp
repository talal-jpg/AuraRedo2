// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexAtmosphereFX.h"

#include "Actors/MyHexPathSpawner.h"
#include "Actors/MyHexPlatform.h"
#include "Camera/PlayerCameraManager.h"
#include "Kismet/GameplayStatics.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "TimerManager.h"


// =============================================================================
// AMyHexAtmosphereFX
// =============================================================================

AMyHexAtmosphereFX::AMyHexAtmosphereFX()
{
	// Ticks only while gliding to a move target or following the camera (after the camera has moved)
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;

	bReplicates = false;

	Niagara = CreateDefaultSubobject<UNiagaraComponent>(TEXT("Niagara"));
	SetRootComponent(Niagara);

	// Started in BeginPlay once System is known
	Niagara->SetAutoActivate(false);
	Niagara->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Niagara->SetCanEverAffectNavigation(false);
	Niagara->SetCastShadow(false);
}

void AMyHexAtmosphereFX::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION(AMyHexAtmosphereFX, System, COND_InitialOnly);
	DOREPLIFETIME_CONDITION(AMyHexAtmosphereFX, MoveSpeed, COND_InitialOnly);
	DOREPLIFETIME(AMyHexAtmosphereFX, MoveTargetLocation);
	DOREPLIFETIME(AMyHexAtmosphereFX, MoveTargetYaw);
	DOREPLIFETIME(AMyHexAtmosphereFX, MoveTargetCount);
}

void AMyHexAtmosphereFX::BeginPlay()
{
	Super::BeginPlay();

	if (MaxDrawDistance > 0.f)
	{
		Niagara->SetCullDistance(MaxDrawDistance);
	}

	if (bFollowLocalCamera)
	{
		SetActorTickEnabled(true);
	}

	// PCG attaches the actors it spawns after their BeginPlay: fit and start next tick
	if (bFitToPlatform || bAlignToWind)
	{
		GetWorldTimerManager().SetTimerForNextTick(this, &ThisClass::StartEffect);
	}
	else
	{
		StartEffect();
	}
}

void AMyHexAtmosphereFX::StartEffect()
{
	if (!IsValid(this) || IsActorBeingDestroyed())
	{
		return;
	}

	if (bAlignToWind)
	{
		SetActorRotation(FRotator(0.f, AMyHexPathSpawner::FindWindYaw(this) + WindYawOffset, 0.f));
	}

	if (bFitToPlatform)
	{
		FitToPlatform();
	}

	bEffectStarted = true;
	ApplySystem();
}

void AMyHexAtmosphereFX::FitToPlatform()
{
	AMyHexPlatform* Platform = Cast<AMyHexPlatform>(GetAttachParentActor());

	if (!Platform)
	{
		Platform = Cast<AMyHexPlatform>(GetOwner());
	}

	if (!Platform)
	{
		return;
	}

	if (Platform->TileFootprintCount == 0)
	{
		Platform->UpdateTileFootprint();
	}

	if (Platform->TileFootprintCount == 0)
	{
		return;
	}

	const float Radius = (Platform->TileFootprintRadius + FitMargin) * FitRadiusScale;
	const float ScaleXY = FMath::Clamp(Radius / FMath::Max(FitBaseRadius, 1.f), FitScaleRange.X, FitScaleRange.Y);
	const float ScaleZ = FitScaleZ > 0.f ? FitScaleZ : GetActorScale3D().Z;

	SetActorScale3D(FVector(ScaleXY, ScaleXY, ScaleZ));

	if (bFitCenter)
	{
		SetActorLocation(Platform->TileFootprintCenter + FVector(0.f, 0.f, FitZOffset));
	}
}

void AMyHexAtmosphereFX::ApplyParameters()
{
	for (const TPair<FName, float>& Pair : FloatParameters)
	{
		Niagara->SetVariableFloat(Pair.Key, Pair.Value);
	}

	for (const TPair<FName, FVector>& Pair : VectorParameters)
	{
		Niagara->SetVariableVec3(Pair.Key, Pair.Value);
	}

	BaseSpawnRate = 0.f;

	if (!SpawnRateParameter.IsNone() && SpawnRateAtScale1 > 0.f)
	{
		const FVector Scale = GetActorScale3D().GetAbs();
		float Rate = SpawnRateAtScale1 * Scale.X * Scale.Y * Scale.Z * DensityScale;

		if (MaxSpawnRate > 0.f)
		{
			Rate = FMath::Min(Rate, MaxSpawnRate);
		}

		BaseSpawnRate = Rate;
		Niagara->SetVariableFloat(SpawnRateParameter, Rate);
	}

	if (BaseSpawnRate > 0.f && GustAmount > 0.f)
	{
		GustPhase = FMath::FRandRange(0.f, 1000.f);
		UpdateGust();
		SetActorTickEnabled(true);
	}
}

void AMyHexAtmosphereFX::SetSpawnRate(FName Parameter, float Rate, float InGustAmount, float InGustPeriod)
{
	if (Rate > 0.f)
	{
		SpawnRateParameter = Parameter;
		SpawnRateAtScale1 = Rate;
		DensityScale = 1.f;
		MaxSpawnRate = 0.f;
	}

	GustAmount = InGustAmount;
	GustPeriod = InGustPeriod;
}

void AMyHexAtmosphereFX::UpdateGust()
{
	const UWorld* World = GetWorld();

	if (!World || BaseSpawnRate <= 0.f || GustAmount <= 0.f)
	{
		return;
	}

	// Two octaves of slow noise in 0..1: long gusts with smaller flurries on top
	const float T = World->GetTimeSeconds() / FMath::Max(GustPeriod, 0.5f) + GustPhase;
	const float Noise = 0.7f * FMath::PerlinNoise1D(T) + 0.3f * FMath::PerlinNoise1D(T * 2.7f + 31.f);
	const float Gust = FMath::Clamp(0.5f + Noise * 1.6f, 0.f, 1.f);

	Niagara->SetVariableFloat(SpawnRateParameter, BaseSpawnRate * (1.f - GustAmount * (1.f - Gust)));
}

void AMyHexAtmosphereFX::SetFollowLocalCamera(bool bFollow, const FVector& Offset)
{
	bFollowLocalCamera = bFollow;
	FollowOffset = Offset;

	if (HasActorBegunPlay())
	{
		SetActorTickEnabled(bFollow);
	}
}

void AMyHexAtmosphereFX::SetSystem(const TSoftObjectPtr<UNiagaraSystem>& InSystem)
{
	System = InSystem;

	if (HasActorBegunPlay() && bEffectStarted)
	{
		ApplySystem();
	}
}

void AMyHexAtmosphereFX::OnRep_System()
{
	if (HasActorBegunPlay() && bEffectStarted)
	{
		ApplySystem();
	}
}

void AMyHexAtmosphereFX::ApplySystem()
{
	UNiagaraSystem* Loaded = System.LoadSynchronous();

	if (!Loaded)
	{
		Niagara->Deactivate();
		return;
	}

	if (Niagara->GetAsset() != Loaded)
	{
		Niagara->SetAsset(Loaded);
	}

	ApplyParameters();
	Niagara->Activate(/*bReset=*/true);
}

void AMyHexAtmosphereFX::SetMoveTarget(const FVector& Location, float Yaw)
{
	MoveTargetLocation = Location;
	MoveTargetYaw = Yaw;
	++MoveTargetCount;

	OnRep_MoveTarget();
}

void AMyHexAtmosphereFX::DestroyAttachedTo(AActor* Parent)
{
	if (!Parent)
	{
		return;
	}

	TArray<AActor*> Attached;
	Parent->GetAttachedActors(Attached);

	for (AActor* Child : Attached)
	{
		AMyHexAtmosphereFX* FX = Cast<AMyHexAtmosphereFX>(Child);

		// A client can't destroy a replicated one: the server's destroy reaches it
		if (IsValid(FX) && (!FX->GetIsReplicated() || FX->HasAuthority()))
		{
			FX->Destroy();
		}
	}
}

void AMyHexAtmosphereFX::OnRep_MoveTarget()
{
	if (MoveTargetCount == AppliedMoveTargetCount)
	{
		return;
	}

	// The first target on this machine (or MoveSpeed 0) is a jump, later ones glide in Tick
	const bool bJump = AppliedMoveTargetCount == 0 || MoveSpeed <= 0.f;
	AppliedMoveTargetCount = MoveTargetCount;

	if (bJump)
	{
		SetActorLocationAndRotation(MoveTargetLocation, FRotator(0.f, MoveTargetYaw, 0.f));
		SetActorTickEnabled(false);
	}
	else
	{
		SetActorTickEnabled(true);
	}
}

void AMyHexAtmosphereFX::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (GustAmount > 0.f && BaseSpawnRate > 0.f)
	{
		UpdateGust();
	}

	if (bFollowLocalCamera)
	{
		if (const APlayerCameraManager* Camera = UGameplayStatics::GetPlayerCameraManager(this, 0))
		{
			SetActorLocation(Camera->GetCameraLocation() + FollowOffset);
		}

		return;
	}

	// Ticking only for gusts: no move target to glide to
	if (AppliedMoveTargetCount == 0)
	{
		return;
	}

	const FVector Location = FMath::VInterpConstantTo(GetActorLocation(), MoveTargetLocation, DeltaSeconds, MoveSpeed);

	// Turns at up to 30 degrees per second
	const FRotator Rotation = FMath::RInterpConstantTo(GetActorRotation(), FRotator(0.f, MoveTargetYaw, 0.f), DeltaSeconds, 30.f);

	SetActorLocationAndRotation(Location, Rotation);

	if (Location.Equals(MoveTargetLocation, 1.0) && Rotation.Equals(FRotator(0.f, MoveTargetYaw, 0.f), 0.5f))
	{
		SetActorTickEnabled(false);
	}
}


// =============================================================================
// AMyHexAtmosphereFXNet
// =============================================================================

AMyHexAtmosphereFXNet::AMyHexAtmosphereFXNet()
{
	bReplicates = true;

	// Like the platforms: every machine keeps the whole path's atmosphere
	bAlwaysRelevant = true;

	// Movement is replicated as a target that every machine glides to
	SetReplicatingMovement(false);
}
