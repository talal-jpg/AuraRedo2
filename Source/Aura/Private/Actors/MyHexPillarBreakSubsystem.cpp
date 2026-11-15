// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexPillarBreakSubsystem.h"

#include "Actors/MyHexPlatform.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "GeometryCollection/GeometryCollection.h"
#include "GeometryCollection/GeometryCollectionAlgo.h"
#include "GeometryCollection/GeometryCollectionComponent.h"
#include "GeometryCollection/GeometryCollectionObject.h"
#include "GeometryCollectionProxyData.h"
#include "HAL/IConsoleManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogHexPillarBreak, Log, All);

namespace
{
	TAutoConsoleVariable<int32> CVarPillarBreakLumen(
		TEXT("Aura.PillarBreak.Lumen"),
		-1,
		TEXT("Pillar Geometry Collections in Lumen's scene: -1 = the platform's TopPillarBreak / BottomPillarBreak bAffectLumen, 0 = never, 1 = always (new pieces only)"),
		ECVF_Default
	);
}


// =============================================================================
// Subsystem
// =============================================================================

bool UMyHexPillarBreakSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	// The pieces are cosmetic: a dedicated server never makes them
	return Super::ShouldCreateSubsystem(Outer) && !IsRunningDedicatedServer();
}

bool UMyHexPillarBreakSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyHexPillarBreakSubsystem::Deinitialize()
{
	Queue.Reset();
	Active.Reset();
	PieceCache.Reset();
	FarPools.Reset();
	NumFarActive = 0;

	Super::Deinitialize();
}

TStatId UMyHexPillarBreakSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UMyHexPillarBreakSubsystem, STATGROUP_Tickables);
}

bool UMyHexPillarBreakSubsystem::IsTickable() const
{
	return !Queue.IsEmpty() || !Active.IsEmpty() || NumFarActive > 0;
}


// =============================================================================
// Queue
// =============================================================================

void UMyHexPillarBreakSubsystem::QueueBreak(AMyHexPlatform* Platform, UGeometryCollection* Collection, const FTransform& WorldTransform,
	const TArray<FVector>& OpenSides, const FHexPillarBreakSettings& Settings, float LengthScale, float RemoveAfter,
	const TArray<float>& CustomPrimitiveData)
{
	if (!Platform || !Collection)
	{
		return;
	}

	FPendingBreak& Break = Queue.AddDefaulted_GetRef();
	Break.Platform = Platform;
	Break.Collection = Collection;
	Break.WorldTransform = WorldTransform;
	Break.OpenSides = OpenSides;
	Break.CustomPrimitiveData = CustomPrimitiveData;
	Break.Settings = Settings;
	Break.LengthScale = LengthScale;
	Break.RemoveAfter = RemoveAfter;
	Break.QueuedTime = GetWorld()->GetTimeSeconds();

	// Within this frame's budget the pillar replaces the instance in the same frame
	ProcessQueue();
}

void UMyHexPillarBreakSubsystem::ProcessQueue()
{
	const double Now = GetWorld()->GetTimeSeconds();

	if (SpawnFrame != GFrameCounter)
	{
		SpawnFrame = GFrameCounter;
		SpawnedThisFrame = 0;
	}

	// Too late (the tile vanished a while ago) or the platform is gone
	auto IsStale = [Now](const FPendingBreak& Break)
	{
		return Now - Break.QueuedTime > Break.Settings.MaxQueueTime || !Break.Platform.IsValid();
	};

	while (!Queue.IsEmpty())
	{
		// Oldest first, so after a burst the stale ones are all at the front: drop them in one go
		int32 NumStale = 0;

		while (NumStale < Queue.Num() && IsStale(Queue[NumStale]))
		{
			++NumStale;
		}

		if (NumStale > 0)
		{
			Queue.RemoveAt(0, NumStale, EAllowShrinking::No);
			NumDropped += NumStale;
			continue;
		}

		const FHexPillarBreakSettings& Settings = Queue[0].Settings;

		if (SpawnedThisFrame >= Settings.MaxSpawnsPerFrame)
		{
			break;
		}

		// Over the budget: make room by retiring the oldest pillar that lies still, else the oldest one,
		// once it has had its moment (Active is oldest first)
		if (Active.Num() >= Settings.MaxActive)
		{
			int32 Victim = INDEX_NONE;

			for (int32 Index = 0; Index < Active.Num() && Now - Active[Index].SpawnTime >= Settings.MinAgeToRecycle; ++Index)
			{
				if (IsResting(Active[Index]))
				{
					Victim = Index;
					break;
				}
			}

			const bool bMoving = Victim == INDEX_NONE;

			if (bMoving)
			{
				if (Active.IsEmpty() || Now - Active[0].SpawnTime < Settings.MinAgeToRecycle)
				{
					break;
				}

				Victim = 0;
			}

			Retire(Active[Victim], bMoving ? TEXT("recycled, moving") : TEXT("recycled, resting"));
			Active.RemoveAt(Victim, EAllowShrinking::No);
			++NumRecycled;
			NumRecycledMoving += bMoving ? 1 : 0;
			continue;
		}

		const FPendingBreak Break = MoveTemp(Queue[0]);
		Queue.RemoveAt(0, EAllowShrinking::No);

		UGeometryCollectionComponent* Component = SpawnBreak(Break);

		if (!Component)
		{
			++NumDropped;
			continue;
		}

		FActiveBreak& NewBreak = Active.AddDefaulted_GetRef();
		NewBreak.Component = Component;
		NewBreak.OpenSides = Break.OpenSides;
		NewBreak.Settings = Break.Settings;
		NewBreak.LengthScale = Break.LengthScale;
		NewBreak.RemoveAfter = Break.RemoveAfter;
		NewBreak.SpawnTime = Now;

		++NumSpawned;
		++SpawnedThisFrame;

		if (NewBreak.Settings.CrumbleDelay <= 0.f)
		{
			Crumble(NewBreak);
		}
	}
}


// =============================================================================
// Tick
// =============================================================================

void UMyHexPillarBreakSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	const double Now = GetWorld()->GetTimeSeconds();

	for (int32 Index = 0; Index < Active.Num(); ++Index)
	{
		FActiveBreak& Break = Active[Index];
		UGeometryCollectionComponent* Component = Break.Component.Get();

		// Went with its platform (or was unregistered: don't leave it behind untracked)
		if (!Component || !Component->IsRegistered())
		{
			if (Component)
			{
				Component->DestroyComponent();
			}

			Active.RemoveAt(Index--, EAllowShrinking::No);
			continue;
		}

		const double Age = Now - Break.SpawnTime;

		if (!Break.bCrumbled && Age >= Break.Settings.CrumbleDelay)
		{
			Crumble(Break);
		}

		// Every piece removed (only with bAssetRemoval), or its time is up: it goes at once, like the tile props
		const TCHAR* Reason = Component->IsFullyDecayed() ? TEXT("decayed") : Age >= Break.RemoveAfter ? TEXT("life span") : nullptr;

		if (Reason)
		{
			Retire(Break, Reason);
			Active.RemoveAt(Index--, EAllowShrinking::No);
		}
	}

	ProcessQueue();

	TickFarBreaks(Now);
}


// =============================================================================
// Far breaks (baked animation in world ISMs)
// =============================================================================

bool UMyHexPillarBreakSubsystem::AddFarBreak(const FHexFarBreakMesh& Far, const FTransform& WorldTransform, float Speed, int32 MaxActive)
{
	if (!Far.Mesh || Speed <= 0.f)
	{
		return false;
	}

	// Over budget: the tile or prop just vanishes, as without a far break
	if (MaxActive > 0 && NumFarActive >= MaxActive)
	{
		++NumFarSkipped;
		return false;
	}

	FFarPool* Pool = FindOrAddFarPool(Far);
	UInstancedStaticMeshComponent* ISM = Pool ? Pool->ISM.Get() : nullptr;

	if (!ISM)
	{
		return false;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	const float CustomData[2] = { static_cast<float>(Now), Speed };
	int32 Index;

	// Reuse a hidden slot before growing the ISM. The instance data manager sends the change to the
	// renderer once per frame, so no render state is rebuilt here.
	if (!Pool->FreeSlots.IsEmpty())
	{
		Index = Pool->FreeSlots.Pop(EAllowShrinking::No);
		ISM->UpdateInstanceTransform(Index, WorldTransform, /*bWorldSpace=*/true, /*bMarkRenderStateDirty=*/false, /*bTeleport=*/true);
		++NumFarReused;
	}
	else
	{
		Index = ISM->AddInstance(WorldTransform, /*bWorldSpace=*/true);

		if (Index == INDEX_NONE)
		{
			return false;
		}

		Pool->FreeAt.SetNumZeroed(FMath::Max(Pool->FreeAt.Num(), Index + 1));
	}

	ISM->SetCustomData(Index, MakeArrayView(CustomData, 2), /*bMarkRenderStateDirty=*/false);

	Pool->FreeAt[Index] = Now + Far.Length / Speed;
	++Pool->NumActive;
	++NumFarActive;
	++NumFarAdded;
	return true;
}

void UMyHexPillarBreakSubsystem::PrewarmFarBreak(const FHexFarBreakMesh& Far)
{
	if (Far.Mesh)
	{
		FindOrAddFarPool(Far);
	}
}

UMyHexPillarBreakSubsystem::FFarPool* UMyHexPillarBreakSubsystem::FindOrAddFarPool(const FHexFarBreakMesh& Far)
{
	const TPair<TObjectKey<UStaticMesh>, TObjectKey<UMaterialInterface>> Key(Far.Mesh.Get(), Far.Material.Get());

	if (FFarPool* Found = FarPools.Find(Key))
	{
		if (Found->ISM.IsValid())
		{
			return Found;
		}

		NumFarActive -= Found->NumActive;
		FarPools.Remove(Key);
	}

	UWorld* World = GetWorld();

	if (!World)
	{
		return nullptr;
	}

	// One transient actor at the origin holds every far-break ISM (instances are placed in world space)
	AActor* Owner = FarBreakActor.Get();

	if (!Owner)
	{
		FActorSpawnParameters Params;
		Params.ObjectFlags = RF_Transient;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		Owner = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, Params);

		if (!Owner)
		{
			return nullptr;
		}

		Owner->SetReplicates(false);

		USceneComponent* Root = NewObject<USceneComponent>(Owner, TEXT("Root"), RF_Transient);
		Owner->SetRootComponent(Root);
		Root->RegisterComponent();

		FarBreakActor = Owner;
	}

	// Every render flag is set before the mesh and materials, and the PSOs are precached once all of it is
	// final (SetStaticMesh precaches too, before the material override)
	UInstancedStaticMeshComponent* ISM = NewObject<UInstancedStaticMeshComponent>(Owner, NAME_None, RF_Transient);
	ISM->SetMobility(EComponentMobility::Movable);
	ISM->NumCustomDataFloats = 2;
	ISM->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ISM->SetGenerateOverlapEvents(false);
	ISM->SetCanEverAffectNavigation(false);
	ISM->SetCastShadow(Far.bCastShadow);
	ISM->bWorldPositionOffsetWritesVelocity = Far.bWPOWritesVelocity;

	// Cosmetic and far away: kept out of Lumen, distance fields and ray tracing, so new instances don't
	// trigger surface cache captures
	ISM->bAffectDynamicIndirectLighting = false;
	ISM->bAffectDistanceFieldLighting = false;
	ISM->bVisibleInRayTracing = false;

	ISM->SetStaticMesh(Far.Mesh);

	if (Far.Material)
	{
		for (int32 Slot = 0; Slot < Far.Mesh->GetStaticMaterials().Num(); ++Slot)
		{
			ISM->SetMaterial(Slot, Far.Material);
		}
	}

	ISM->PrecachePSOs();
	ISM->SetupAttachment(Owner->GetRootComponent());
	ISM->RegisterComponent();

	FFarPool& Pool = FarPools.Add(Key);
	Pool.ISM = ISM;
	return &Pool;
}

void UMyHexPillarBreakSubsystem::TickFarBreaks(double Now)
{
	if (NumFarActive <= 0)
	{
		return;
	}

	for (TPair<TPair<TObjectKey<UStaticMesh>, TObjectKey<UMaterialInterface>>, FFarPool>& Pair : FarPools)
	{
		FFarPool& Pool = Pair.Value;

		if (Pool.NumActive <= 0)
		{
			continue;
		}

		UInstancedStaticMeshComponent* ISM = Pool.ISM.Get();

		if (!ISM)
		{
			NumFarActive -= Pool.NumActive;
			Pool.NumActive = 0;
			continue;
		}

		for (int32 Index = 0; Index < Pool.FreeAt.Num(); ++Index)
		{
			if (Pool.FreeAt[Index] <= 0.0 || Now < Pool.FreeAt[Index])
			{
				continue;
			}

			// Hidden in place (zero scale) until the slot is reused
			FTransform Hidden;
			ISM->GetInstanceTransform(Index, Hidden, /*bWorldSpace=*/true);
			Hidden.SetScale3D(FVector::ZeroVector);
			ISM->UpdateInstanceTransform(Index, Hidden, /*bWorldSpace=*/true, /*bMarkRenderStateDirty=*/false, /*bTeleport=*/true);

			Pool.FreeAt[Index] = 0.0;
			Pool.FreeSlots.Add(Index);
			--Pool.NumActive;
			--NumFarActive;
		}

		// All done: empty the ISM, so its bounds don't keep growing along the path with hidden slots
		if (Pool.NumActive <= 0)
		{
			ISM->ClearInstances();
			Pool.FreeAt.Reset();
			Pool.FreeSlots.Reset();
		}
	}
}


// =============================================================================
// Spawn / crumble / retire
// =============================================================================

UGeometryCollectionComponent* UMyHexPillarBreakSubsystem::SpawnBreak(const FPendingBreak& Break)
{
	AMyHexPlatform* Platform = Break.Platform.Get();
	UGeometryCollection* Collection = Break.Collection.Get();

	if (!Platform || !Collection || Platform->IsActorBeingDestroyed())
	{
		return nullptr;
	}

	const FHexPillarBreakSettings& Settings = Break.Settings;

	// Owned by the platform like the skeletal mesh pillars, not attached to its ISM, not replicated
	UGeometryCollectionComponent* Component = NewObject<UGeometryCollectionComponent>(Platform, NAME_None, RF_Transient);

	// Everything the physics proxy reads is set while the component is unregistered: SetRestCollection
	// on a registered component builds the proxy at once, with whatever was set by then.
	Component->SetCanEverAffectNavigation(false);
	Component->SetCastShadow(Settings.bCastShadow);

	const int32 LumenOverride = CVarPillarBreakLumen.GetValueOnGameThread();
	Component->bAffectDynamicIndirectLighting = LumenOverride < 0 ? Settings.bAffectLumen : LumenOverride != 0;

	Component->ObjectType = EObjectStateTypeEnum::Chaos_Object_Dynamic;

	// Pieces stay full size until the pillar goes (unless the asset's removal is wanted)
	Component->bAllowRemovalOnBreak = Settings.bAssetRemoval;
	Component->bAllowRemovalOnSleep = Settings.bAssetRemoval;

	// A user defined initial velocity only reaches the leaf pieces (it is added when they come loose), not
	// the intact pillar, so the pillar's velocity is applied to its root below instead
	Component->InitialVelocityType = EInitialVelocityTypeEnum::Chaos_Initial_Velocity_None;

	if (!Settings.bBlocksPawns)
	{
		// Cosmetic: the world and other debris only, no pawns or traces
		Component->SetCollisionResponseToAllChannels(ECR_Ignore);
		Component->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
		Component->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
		Component->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Block);
		Component->SetCollisionResponseToChannel(ECC_Destructible, ECR_Block);
	}

	// The tile's custom data, for the material. Set while unregistered, so the scene proxy starts with it
	for (int32 Index = 0; Index < Break.CustomPrimitiveData.Num(); ++Index)
	{
		Component->SetCustomPrimitiveDataFloat(Index, Break.CustomPrimitiveData[Index]);
	}

	// Also copies the asset's damage settings
	Component->SetRestCollection(Collection);

	Component->SetWorldTransform(Break.WorldTransform);
	Component->RegisterComponent();

	// Runs on the physics thread after the proxy's bodies are made (same push); the pieces inherit it
	if (!Settings.InitialVelocity.IsNearlyZero())
	{
		Component->ApplyLinearVelocity(Component->GetRootIndex(), Settings.InitialVelocity);
	}

	UE_LOG(LogHexPillarBreak, Verbose, TEXT("%s %s: pillar at %s, scale %s, %s, %d active, %d queued"),
		*GetWorld()->GetName(), *Platform->GetName(), *Break.WorldTransform.GetLocation().ToCompactString(),
		*Break.WorldTransform.GetScale3D().ToCompactString(), *Collection->GetName(), Active.Num() + 1, Queue.Num());

	return Component;
}

void UMyHexPillarBreakSubsystem::Crumble(FActiveBreak& Break)
{
	Break.bCrumbled = true;

	UGeometryCollectionComponent* Component = Break.Component.Get();
	const UGeometryCollection* Collection = Component ? Component->GetRestCollection() : nullptr;

	if (!Collection)
	{
		return;
	}

	Component->CrumbleActiveClusters();

	const FHexPillarBreakSettings& Settings = Break.Settings;
	const float Spread = Settings.PieceSpreadSpeed * Break.LengthScale;
	const float Jitter = Settings.PieceVerticalJitter * Break.LengthScale;
	const float MaxSpin = FMath::DegreesToRadians(Settings.PieceMaxSpin);

	if (Spread <= 0.f && Jitter <= 0.f && MaxSpin <= 0.f)
	{
		return;
	}

	const FTransform& ToWorld = Component->GetComponentTransform();

	// The solver runs these after the crumble (same command queue). The pieces are still in their cluster
	// then; their own velocity is added to the cluster's when they come loose.
	for (const FPiece& Piece : GetPieces(*Collection))
	{
		// Away from the pillar's axis (its local Z through the pivot), as far as that points out of an open side
		const FVector Out = ToWorld.TransformVectorNoScale(FVector(Piece.Center.X, Piece.Center.Y, 0.0)).GetSafeNormal();
		float Openness = 0.f;

		for (const FVector& Side : Break.OpenSides)
		{
			Openness = FMath::Max(Openness, static_cast<float>(FVector::DotProduct(Out, Side)));
		}

		const FVector Velocity = Out * (Spread * Openness * FMath::FRandRange(0.5f, 1.f)) + FVector(0.0, 0.0, FMath::FRandRange(-Jitter, Jitter));

		if (!Velocity.IsNearlyZero())
		{
			Component->ApplyLinearVelocity(Piece.TransformIndex, Velocity);
		}

		if (MaxSpin > 0.f)
		{
			Component->ApplyAngularVelocity(Piece.TransformIndex, FMath::VRand() * (MaxSpin * FMath::FRandRange(0.3f, 1.f)));
		}
	}
}

bool UMyHexPillarBreakSubsystem::IsResting(const FActiveBreak& Break)
{
	UGeometryCollectionComponent* Component = Break.Component.Get();
	const UGeometryCollection* Collection = Component ? Component->GetRestCollection() : nullptr;
	FGeometryDynamicCollection* Dynamic = Component ? Component->GetDynamicCollection() : nullptr;

	if (!Break.bCrumbled || !Collection || !Dynamic)
	{
		return false;
	}

	const FGeometryCollectionDynamicStateFacade DynamicState(*Dynamic);

	if (!DynamicState.IsValid())
	{
		return false;
	}

	for (const FPiece& Piece : GetPieces(*Collection))
	{
		if (!DynamicState.IsSleeping(Piece.TransformIndex))
		{
			return false;
		}
	}

	return true;
}

void UMyHexPillarBreakSubsystem::Retire(FActiveBreak& Break, const TCHAR* Reason)
{
	if (UGeometryCollectionComponent* Component = Break.Component.Get())
	{
		UE_LOG(LogHexPillarBreak, Verbose, TEXT("%s: pillar removed after %.2f s (%s)"), *GetWorld()->GetName(), GetWorld()->GetTimeSeconds() - Break.SpawnTime, Reason);

		Component->DestroyComponent();
	}

	Break.Component.Reset();
}

const TArray<UMyHexPillarBreakSubsystem::FPiece>& UMyHexPillarBreakSubsystem::GetPieces(const UGeometryCollection& Collection)
{
	if (const TArray<FPiece>* Found = PieceCache.Find(&Collection))
	{
		return *Found;
	}

	const TSharedPtr<FGeometryCollection, ESPMode::ThreadSafe> Geometry = Collection.GetGeometryCollection();

	if (!Geometry.IsValid())
	{
		static const TArray<FPiece> NoPieces;
		return NoPieces;
	}

	TArray<FPiece>& Pieces = PieceCache.Add(&Collection);

	const TManagedArray<int32>& Parent = Geometry->Parent;
	const TManagedArray<FTransform3f>& Transform = Geometry->Transform;
	const TManagedArray<int32>& TransformToGeometryIndex = Geometry->TransformToGeometryIndex;
	const TManagedArray<FBox>& BoundingBox = Geometry->BoundingBox;

	for (int32 Index = 0; Index < Parent.Num(); ++Index)
	{
		// The root's children: what CrumbleActiveClusters frees
		const int32 ParentIndex = Parent[Index];

		if (ParentIndex == INDEX_NONE || Parent[ParentIndex] != INDEX_NONE)
		{
			continue;
		}

		const FTransform Global = GeometryCollectionAlgo::GlobalMatrix(Transform, Parent, Index);
		const int32 GeometryIndex = TransformToGeometryIndex[Index];

		FPiece& Piece = Pieces.AddDefaulted_GetRef();
		Piece.TransformIndex = Index;
		Piece.Center = BoundingBox.IsValidIndex(GeometryIndex) ? Global.TransformPosition(BoundingBox[GeometryIndex].GetCenter()) : Global.GetTranslation();
	}

	return Pieces;
}

void UMyHexPillarBreakSubsystem::PrecacheCollection(AMyHexPlatform* Platform, UGeometryCollection* Collection)
{
	if (!Platform || !Collection || PrecachedCollections.Contains(Collection))
	{
		return;
	}

	PrecachedCollections.Add(Collection);

	// SetRestCollection starts the PSO precache for its materials; the component itself is never registered
	UGeometryCollectionComponent* Component = NewObject<UGeometryCollectionComponent>(Platform, NAME_None, RF_Transient);
	Component->SetCanEverAffectNavigation(false);
	Component->SetRestCollection(Collection);
	Component->DestroyComponent();
}

void UMyHexPillarBreakSubsystem::LogStats() const
{
	UE_LOG(LogHexPillarBreak, Display, TEXT("%s: %d active, %d queued | since start: %d spawned, %d dropped, %d recycled (%d while moving)"),
		*GetWorld()->GetName(), Active.Num(), Queue.Num(), NumSpawned, NumDropped, NumRecycled, NumRecycledMoving);

	int32 NumFarInstances = 0;

	for (const TPair<TPair<TObjectKey<UStaticMesh>, TObjectKey<UMaterialInterface>>, FFarPool>& Pair : FarPools)
	{
		if (const UInstancedStaticMeshComponent* ISM = Pair.Value.ISM.Get())
		{
			NumFarInstances += ISM->GetInstanceCount();
		}
	}

	UE_LOG(LogHexPillarBreak, Display, TEXT("%s: far breaks %d playing, %d ISMs, %d instances | since start: %d added (%d into reused slots), %d skipped over budget"),
		*GetWorld()->GetName(), NumFarActive, FarPools.Num(), NumFarInstances, NumFarAdded, NumFarReused, NumFarSkipped);
}


#if !UE_BUILD_SHIPPING
namespace
{
	FAutoConsoleCommandWithWorld GPillarBreakStatsCommand(
		TEXT("Aura.PillarBreakStats"),
		TEXT("Aura.PillarBreakStats - log this world's pillar Geometry Collection counts"),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (const UMyHexPillarBreakSubsystem* PillarBreaks = World ? World->GetSubsystem<UMyHexPillarBreakSubsystem>() : nullptr)
			{
				PillarBreaks->LogStats();
			}
		})
	);
}
#endif
