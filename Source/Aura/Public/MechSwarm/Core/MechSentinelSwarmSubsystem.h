// Mech Sentinel Swarm - the swarm subsystem: global runtime data, the GAS bridge and the hit query service.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Actor.h"
#include "GameplayEffectTypes.h"
#include "Subsystems/WorldSubsystem.h"
#include "Mass/EntityHandle.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"
#include "MechSentinelSwarmSubsystem.generated.h"

class AMechSentinelGASProxy;
class AMechSentinelBulletRelay;
class UAbilitySystemComponent;
class UMassEntityConfigAsset;
class UMechSentinelSwarmRules;
struct FGameplayEffectSpec;
struct FMassEntityManager;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FOnMechSentinelDamaged, FMechSentinelHandle, Sentinel, float, Damage, FVector, Location, AActor*, Instigator);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnMechSentinelKilled, FMechSentinelHandle, Sentinel, FVector, Location, AActor*, Instigator);

/** One damaging hit on a sentinel (server), with more detail than OnSentinelDamaged. C++ only; used for damage numbers. */
struct FMechSentinelDamageEvent
{
	FMechSentinelHandle Sentinel;

	/** Health removed, clipped at the sentinel's remaining health (the value OnSentinelDamaged sends). */
	float Damage = 0.f;

	/** Damage after armor and shield, before Health was clamped: what a character's damage number shows. */
	float IncomingDamage = 0.f;

	/** The hit point (FMechSentinelHit::ImpactPoint for traces), else the sentinel's location. */
	FVector Location = FVector::ZeroVector;

	/** The effect context's instigator (a player's AMyPlayerState for player hits). */
	AActor* Instigator = nullptr;

	/** The spec's effect context; the project's crit / blocked flags live in its hit result (UMyBPFuncLib::IsCrit / IsBlocked). */
	FGameplayEffectContextHandle EffectContext;

	/** The sentinel had State.Sentinel.Shielded after the hit (its damage was scaled by ShieldedDamageMultiplier). */
	bool bShielded = false;
};

DECLARE_MULTICAST_DELEGATE_OneParam(FOnMechSentinelDamagedNative, const FMechSentinelDamageEvent&);

/** How one sentinel bullet flies (FMechSentinelParameters' bullet settings). */
struct FMechSentinelBulletSettings
{
	float Speed = 7500.f;
	float Range = 5000.f;
	float SpreadDegrees = 0.f;
	float Radius = 30.f;
};

/** A fallback location sentinels go to when every player is already crowded. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelFallbackPoint
{
	GENERATED_BODY()

	/** Optional actor to follow; when null, Location is used. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sentinel")
	TObjectPtr<AActor> Actor = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sentinel")
	FVector Location = FVector::ZeroVector;

	/** Max sentinels gathering here, 0 = unlimited. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sentinel", meta = (ClampMin = "0"))
	int32 Capacity = 0;

	FVector GetLocation() const { return Actor ? Actor->GetActorLocation() : Location; }
};

/**
 * Runtime copy of a registered fallback point. The actor is held weakly: designers may destroy it at any time,
 * and the subsystem's registration storage is not visible to GC.
 */
struct FMechSentinelFallbackTarget
{
	TWeakObjectPtr<AActor> Actor;
	FVector Location = FVector::ZeroVector;
	int32 Capacity = 0;
	/** True when the point follows an actor (and becomes invalid once that actor is gone). */
	bool bFollowsActor = false;

	explicit FMechSentinelFallbackTarget(const FMechSentinelFallbackPoint& Point)
		: Actor(Point.Actor.Get()), Location(Point.Location), Capacity(Point.Capacity), bFollowsActor(Point.Actor != nullptr)
	{
	}

	bool IsValid() const { return !bFollowsActor || Actor.IsValid(); }

	FVector GetLocation() const
	{
		const AActor* FollowedActor = Actor.Get();
		return FollowedActor ? FollowedActor->GetActorLocation() : Location;
	}
};

/** Result of a capsule query against the sentinels' simple collision capsules. */
USTRUCT(BlueprintType)
struct AURA_API FMechSentinelHit
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	FMechSentinelHandle Sentinel;

	/** Closest point on the sentinel capsule axis to the query shape. */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	FVector ImpactPoint = FVector::ZeroVector;

	/** Distance along a sweep (0 for overlaps). Hits are sorted by it. */
	UPROPERTY(BlueprintReadOnly, Category = "Sentinel")
	float Distance = 0.f;
};

/**
 * World subsystem that glues Mass, GAS and the rest of the game together.
 *
 *  - Global runtime data: the rules (read from AMyGameMode on the server), player targets, fallback points.
 *  - Template bootstrap: registers the replication bubble class and pre-builds entity templates so
 *    clients can spawn replicated sentinels.
 *  - GAS bridge (server): ApplyGameplayEffectSpecToSentinel / RecomputeSentinel through AMechSentinelGASProxy.
 *  - Hit queries: a spatial hash of sentinel capsules rebuilt each frame by UMechSentinelCollisionHashProcessor.
 */
UCLASS()
class AURA_API UMechSentinelSwarmSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UMechSentinelSwarmSubsystem* Get(const UObject* WorldContextObject);

	//~ USubsystem
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	bool HasAuthority() const;
	FMassEntityManager* GetEntityManager() const;

	//----------------------------------------------------------------------//
	// Global data
	//----------------------------------------------------------------------//

	/** Never null: GameMode rules > override > class defaults. */
	const UMechSentinelSwarmRules* GetRules() const;

	/** Use different rules at runtime (e.g. a difficulty change). Server only. */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels")
	void SetRulesOverride(UMechSentinelSwarmRules* NewRules);

	/**
	 * Changes the swarm-wide movement speed shared fragment of a swarm group. Server only (replicated movement follows).
	 * Steering reads it on worker threads during the Mass phases: call it from a timer (Set Timer for Next Tick) or a
	 * tick in Post Update Work; from input, a few sentinels may move at the old speed for one frame.
	 */
	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels")
	void SetSwarmMovementSpeed(FName SwarmGroup, float NewMovementSpeed);

	//----------------------------------------------------------------------//
	// Templates
	//----------------------------------------------------------------------//

	/**
	 * Validates (once) and builds the entity template of Config on this machine. Safe to call often.
	 * Returns false when the config cannot be used (e.g. its Replication trait does not point to the sentinel classes).
	 */
	bool RegisterEntityConfig(const UMassEntityConfigAsset* Config);

	/** Builds the templates of every registered config and of every wave spawner found in the world. */
	void EnsureTemplatesBuilt();

	//----------------------------------------------------------------------//
	// Targets
	//----------------------------------------------------------------------//

	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels", meta = (DefaultToSelf = "Owner"))
	void RegisterFallbackTargets(FName SwarmGroup, const TArray<FMechSentinelFallbackPoint>& Points, UObject* Owner);

	UFUNCTION(BlueprintCallable, Category = "Mech Sentinels", meta = (DefaultToSelf = "Owner"))
	void UnregisterFallbackTargets(UObject* Owner);

	/** Valid, alive player pawns. */
	void GatherPlayerTargets(TArray<TPair<AActor*, FVector>>& OutTargets) const;

	/** Fallback points of a group (empty view when none). Check IsValid(): a followed actor may have been destroyed. */
	TConstArrayView<FMechSentinelFallbackTarget> GetFallbackTargets(FName SwarmGroup) const;

	//----------------------------------------------------------------------//
	// GAS bridge (server)
	//----------------------------------------------------------------------//

	/**
	 * Runs Spec against one sentinel through the GAS proxy and writes the result to Mass.
	 * Instant effects change base values (damage, heals); duration / infinite effects are stored on the
	 * sentinel as active effects (buffs / debuffs / stun / shield). Returns the health removed.
	 */
	float ApplyGameplayEffectSpecToSentinel(FMassEntityHandle Entity, const FGameplayEffectSpec& Spec, const FVector* HitLocation = nullptr);

	/** Re-evaluates current attributes and tags from the stored active effects (after one expired). */
	void RecomputeSentinel(FMassEntityHandle Entity);

	/** Kills a sentinel without damage math (e.g. despawn with death animation). */
	void KillSentinel(FMassEntityHandle Entity, AActor* Instigator = nullptr);

	/** The ASC used as source when sentinels attack players. */
	UAbilitySystemComponent* GetSentinelSourceASC();

	/**
	 * A sentinel's attack lands on TargetActor: the rules' SentinelAttackEffect from the GAS proxy's ASC, with SetByCaller
	 * MyTags::SetDamageByCaller = Damage and a hit result From -> To in the context. Server, game thread.
	 */
	void ApplySentinelAttack(AActor* TargetActor, const FVector& From, const FVector& To, float Damage);

	/**
	 * Fires a sentinel bullet from Muzzle toward AimPoint (with the settings' spread). It flies at Settings.Speed to the
	 * first thing that blocks Visibility on its line (or Settings.Range); every bullet tick sweeps the stretch it covered
	 * since the last one, and the first player pawn within Settings.Radius takes Damage through ApplySentinelAttack and
	 * stops it. Every machine sees it through AMechSentinelBulletRelay. Server, game thread.
	 */
	void FireSentinelBullet(const FVector& Muzzle, const FVector& AimPoint, float Damage, const FMechSentinelBulletSettings& Settings);

	/** Bullets in flight (server). */
	int32 GetNumFlyingBullets() const { return FlyingBullets.Num(); }

	/**
	 * Queues self-buff BuffIndex (EMechSentinelSelfBuff) on a sentinel; UMechSentinelSelfBuffProcessor calls it. It is
	 * applied by a next-tick timer, after this frame's Mass phases, at most the rules' MaxSelfBuffsPerFrame per frame (the
	 * rest waits for the next frames), and skipped when by then the sentinel is gone, dead, stunned or already has it.
	 * Returns false, queueing nothing, when the queue already holds MaxSelfBuffsPerFrame x 30 casts (a second at 30 fps):
	 * the caller keeps the buff ready and decides again later. Game thread, server only.
	 */
	bool QueueSelfBuff(FMassEntityHandle Entity, int32 BuffIndex);

	//----------------------------------------------------------------------//
	// Collision hash (filled by UMechSentinelCollisionHashProcessor)
	//----------------------------------------------------------------------//

	void BeginCollisionFrame(float CellSize);
	void AddCollisionCapsule(FMassEntityHandle Entity, const FVector& Center, const FVector& Axis, float Radius, float HalfHeight);
	void EndCollisionFrame();

	/**
	 * Every sentinel whose capsule touches the query capsule (segment SegmentStart-SegmentEnd inflated by Radius).
	 * A sweep of a sphere is the same query, so projectiles pass their previous and current location.
	 */
	int32 QueryCapsule(const FVector& SegmentStart, const FVector& SegmentEnd, float Radius, TArray<FMechSentinelHit>& OutHits) const;

	/**
	 * Alive (not dead) sentinels this frame, from the collision hash. Authority only (standalone / server): the hash is
	 * built by the server-side collision processor, so this is 0 on clients. Clients read the wave spawner's replicated
	 * counts instead.
	 */
	UFUNCTION(BlueprintPure, Category = "Mech Sentinels")
	int32 GetNumAliveSentinels() const { return CollisionEntries.Num(); }

	//----------------------------------------------------------------------//
	// Events (server)
	//----------------------------------------------------------------------//

	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels")
	FOnMechSentinelDamaged OnSentinelDamaged;

	/** C++ twin of OnSentinelDamaged with the unclipped damage, the effect context and the shield state. */
	FOnMechSentinelDamagedNative OnSentinelDamagedNative;

	UPROPERTY(BlueprintAssignable, Category = "Mech Sentinels")
	FOnMechSentinelKilled OnSentinelKilled;

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	AMechSentinelGASProxy* GetOrCreateProxy();

	/** Mirrors gameplay tags / health / self-buffs into Mass tags and the state fragment. */
	void SyncStateFromGAS(FMassEntityManager& EntityManager, FMassEntityHandle Entity, AActor* Instigator);

	/** Server, on a kill: sends the rules' KillXP to the killer's player avatar as the Attribute.Meta.XP gameplay event. */
	void GrantKillXP(AActor* Instigator) const;

	/** Applies the queued self-buffs, up to the rules' MaxSelfBuffsPerFrame (next-tick timer, outside the Mass phases). */
	void FlushSelfBuffs();

	/** Arms the flush timer once (next tick). */
	void ScheduleSelfBuffFlush();

	/** Makes the buff's spec (the rules' effect, Magnitude, locked Duration) and applies it. False when skipped. */
	bool ApplySelfBuff(FMassEntityManager& EntityManager, UAbilitySystemComponent& SourceASC, const UMechSentinelSwarmRules& Rules, FMassEntityHandle Entity, int32 BuffIndex);

	UPROPERTY(Transient)
	TObjectPtr<UMechSentinelSwarmRules> RulesOverride;

	UPROPERTY(Transient)
	TObjectPtr<UMechSentinelSwarmRules> GameModeRules;

	UPROPERTY(Transient)
	TObjectPtr<AMechSentinelGASProxy> GASProxy;

	UPROPERTY(Transient)
	TArray<TObjectPtr<const UMassEntityConfigAsset>> RegisteredConfigs;

	/** Configs that failed validation (logged once). */
	UPROPERTY(Transient)
	TArray<TObjectPtr<const UMassEntityConfigAsset>> RejectedConfigs;

	bool ValidateEntityConfig(const UMassEntityConfigAsset& Config) const;

	struct FFallbackRegistration
	{
		TWeakObjectPtr<UObject> Owner;
		FName SwarmGroup;
		TArray<FMechSentinelFallbackTarget> Points;
	};
	TArray<FFallbackRegistration> FallbackRegistrations;

	/** Flattened per group, rebuilt on (un)registration. */
	TMap<FName, TArray<FMechSentinelFallbackTarget>> FallbacksByGroup;

	struct FCollisionEntry
	{
		FMassEntityHandle Entity;
		FVector SegmentA;
		FVector SegmentB;
		float Radius = 0.f;
	};
	TArray<FCollisionEntry> CollisionEntries;
	TMap<FIntVector, TArray<int32>> CollisionCells;
	float CollisionCellSize = 500.f;
	float MaxCollisionExtent = 0.f;

	void RebuildFallbackMap();

	/** A self-buff cast waiting for the flush (in cast order). */
	struct FPendingSelfBuff
	{
		FMassEntityHandle Entity;
		int32 BuffIndex = 0;
	};
	TArray<FPendingSelfBuff> PendingSelfBuffs;
	FTimerHandle SelfBuffFlushTimer;
	bool bSelfBuffFlushScheduled = false;

	/** A sentinel bullet on its way (server); each bullet tick sweeps the stretch it flew since the last one. */
	struct FFlyingBullet
	{
		FVector Start = FVector::ZeroVector;
		FVector Direction = FVector::ForwardVector;
		double FireTime = 0.0;
		float Length = 0.f;
		float Travelled = 0.f;
		float Speed = 7500.f;
		float Damage = 0.f;
		float Radius = 0.f;
	};
	TArray<FFlyingBullet> FlyingBullets;

	/** New bullets to show (Start, End), sent by the next bullet tick. */
	TArray<TPair<FVector, FVector>> PendingBulletFx;
	FTimerHandle BulletTimer;

	UPROPERTY(Transient)
	TObjectPtr<AMechSentinelBulletRelay> BulletRelay;

	/** The rules' bullet assets failed to load once (warned, not retried every frame). */
	bool bBulletFxLoadFailed = false;

	/** Next-tick timer, re-armed while bullets fly or wait to be shown: sends the new bullets and resolves the arrived ones. */
	void TickBullets();
	void ArmBulletTimer();
	AMechSentinelBulletRelay* GetOrCreateBulletRelay();
};
