// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "GameFramework/RootMotionSource.h"
#include "GA_GrappleSwing.generated.h"

class ACharacter;
class UCharacterMovementComponent;

/**
 * Root motion source that drives the swing. It lives inside the CharacterMovementComponent's move loop,
 * so it is replayed with saved moves on the owning client, corrected by the server and replicated to
 * simulated proxies. Only the ability creates and removes it.
 *
 * Each move: keep the current velocity (momentum), add gravity, a pull towards the hook and a bit of
 * steering from movement input, then the rope removes any velocity that would stretch it. Removing the
 * outward part is the rope tension that balances the centrifugal force, which is what bends the path
 * into an arc and swings the character around the hook.
 */
USTRUCT()
struct AURA_API FRootMotionSource_GrappleSwing : public FRootMotionSource
{
	GENERATED_BODY()

	FRootMotionSource_GrappleSwing();

	virtual ~FRootMotionSource_GrappleSwing() override = default;

	UPROPERTY()
	FVector Anchor=FVector::ZeroVector;

	// Current rope length, only ever gets shorter (reel in and slack pick-up)
	UPROPERTY()
	float RopeLength=1000.f;

	UPROPERTY()
	float MinRopeLength=300.f;

	UPROPERTY()
	float ReelInSpeed=150.f;

	UPROPERTY()
	float PullAcceleration=900.f;

	UPROPERTY()
	float SteerAcceleration=1200.f;

	UPROPERTY()
	float RopeStiffness=8.f;

	UPROPERTY()
	float AirDrag=0.05f;

	UPROPERTY()
	float MaxSwingSpeed=3500.f;

	UPROPERTY()
	float GroundLiftoffSpeed=450.f;

	virtual FRootMotionSource* Clone() const override;
	virtual bool Matches(const FRootMotionSource* Other) const override;
	virtual bool MatchesAndHasSameState(const FRootMotionSource* Other) const override;
	virtual bool UpdateStateFrom(const FRootMotionSource* SourceToTakeStateFrom, bool bMarkForSimulatedCatchup = false) override;
	virtual void PrepareRootMotion(float SimulationTime, float MovementTickTime, const ACharacter& Character, const UCharacterMovementComponent& MoveComponent) override;
	virtual bool NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess) override;
	virtual UScriptStruct* GetScriptStruct() const override;
	virtual FString ToSimpleString() const override;
};

template<>
struct TStructOpsTypeTraits<FRootMotionSource_GrappleSwing> : public TStructOpsTypeTraitsBase2<FRootMotionSource_GrappleSwing>
{
	enum
	{
		WithNetSerializer = true,
		WithCopy = true
	};
};

/**
 * Spider-Man style grapple swing. Fires a hook where the crosshair aims, swings while the input is held,
 * and lets go with the momentum it built up on release.
 *
 * Multiplayer: Local Predicted. The owning client traces from its camera and sends the hook point to the
 * server as target data, both sides apply the same root motion source, and the rope cue replicates to everyone.
 */
UCLASS()
class AURA_API UGA_GrappleSwing : public UMyGameplayAbility
{
	GENERATED_BODY()

public:
	UGA_GrappleSwing();

	// Hook

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float MaxGrappleDistance=4000.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	TEnumAsByte<ECollisionChannel> GrappleTraceChannel=ECC_Visibility;

	// Hook point has to be at least this high above the character, negative allows hooking below
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float MinAnchorHeight=0.f;

	// Swing

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float MinRopeLength=300.f;

	// How fast the hook reels the rope in while swinging (cm/s)
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float ReelInSpeed=150.f;

	// Constant pull of the hook towards itself (cm/s^2)
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float PullAcceleration=900.f;

	// How much movement input can push the swing sideways/forward (cm/s^2), only the part across the rope counts
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float SteerAcceleration=1200.f;

	// How hard the rope pulls the character back when it got stretched (1/s)
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float RopeStiffness=8.f;

	// Fraction of speed lost per second
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float AirDrag=0.05f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float MaxSwingSpeed=3500.f;

	// Upward speed given when the swing starts from the ground so the character lifts off
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float GroundLiftoffSpeed=450.f;

	// Landing earlier than this after the hook attaches does not end the swing
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	float LandingGraceTime=0.3f;

	// Release

	// Extra upward kick when letting go of the input
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Release")
	float ReleaseUpBoost=350.f;

	// Visuals

	// Added while swinging, Location = hook point, EffectCauser = swinging character. Make a looping GC notify actor to draw the rope.
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Visuals")
	FGameplayTag RopeCueTag;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Visuals")
	bool bDrawDebugRope=true;

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

private:
	bool TraceForAnchor(FVector& OutAnchor) const;

	void OnServerTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag);

	void StartSwing(const FVector& InAnchor, const FVector& StartLocation);

	void StopSwing();

	UFUNCTION()
	void OnInputReleased(float TimeHeld);

	UFUNCTION()
	void OnMovementModeChanged(ACharacter* Character, EMovementMode PrevMovementMode, uint8 PreviousCustomMode);

	void DrawDebugRope() const;

	ACharacter* GetSwingCharacter() const;

	UCharacterMovementComponent* GetSwingMovement() const;

	FVector Anchor=FVector::ZeroVector;

	uint16 RootMotionSourceID=(uint16)ERootMotionSourceID::Invalid;

	float SwingStartTime=0.f;

	FDelegateHandle TargetDataDelegateHandle;

	FTimerHandle DebugRopeTimerHandle;
};
