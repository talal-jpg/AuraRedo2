// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "Engine/EngineTypes.h"
#include "GameFramework/RootMotionSource.h"
#include "GA_GrappleSwing2.generated.h"

class ACharacter;
class UCharacterMovementComponent;
struct FHitResult;

// Phase of the swing source: hook flying, swinging on the rope, finished (removed next move)
enum class EGS2Phase : uint8
{
	Travel,
	Swing,
	Done
};

// How a release request should end the swing: Release adds the vault, Forced keeps the velocity as is
enum class EGS2EndKind : uint8
{
	Release,
	Forced
};

enum class EGS2EndReason : uint8
{
	None,
	Released,
	Forced,
	JumpReleased,
	AutoReleased,
	Landed,
	Timeout,
	TooClose,
	Snapped
};

// Ability state machine
enum class EGS2AbilityState : uint8
{
	Idle,
	Searching,
	Hooked,
	Releasing,
	Spent,
	Rejected
};

// Per-move context for the swing simulation, only valid inside PrepareRootMotion
struct FGS2MoveCtx
{
	const ACharacter* Character=nullptr;
	const UCharacterMovementComponent* Move=nullptr;
	FVector X0=FVector::ZeroVector;
	FVector Up=FVector::UpVector;
	float G=980.f;
	float HalfHeight=88.f;
	float Dt=0.f;
	float T1=0.f;
	bool bJump=false;
	FVector In=FVector::ZeroVector;
};

struct FGS2AnchorCandidate
{
	FVector Anchor=FVector::ZeroVector;
	FVector Normal=FVector::ZeroVector;
	float FloorHeight=0.f;
	bool bHasFloor=false;
	float Score=-1.e9f;
	bool bValid=false;
};

struct FGS2SearchCtx
{
	FVector ViewLoc=FVector::ZeroVector;
	FVector ViewDir=FVector::ForwardVector;
	FVector Pos=FVector::ZeroVector;
	FVector AttachPos=FVector::ZeroVector;
	FVector MoveDirH=FVector::ForwardVector;
	FVector Up=FVector::UpVector;
	float HalfHeight=88.f;
};

/**
 * Every value the swing simulation reads. The ability hands a shared, read-only copy to each root motion source,
 * so client and server simulate with the same numbers without sending them over the network.
 */
USTRUCT(BlueprintType)
struct AURA_API FGrappleSwing2Tuning
{
	GENERATED_BODY()

	// Integration

	// Largest internal simulation step (s)
	UPROPERTY(EditDefaultsOnly, Category = "Integration")
	float MaxSubstepDt=1.f/120.f;

	UPROPERTY(EditDefaultsOnly, Category = "Integration")
	int32 MaxSubsteps=16;

	// Gravity, drag, speed

	// Gravity multiplier while falling, makes the downswing heavy
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float GravityScaleDescending=2.f;

	// Gravity multiplier while rising, makes the upswing float a little
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float GravityScaleAscending=1.3f;

	// Vertical speed range (cm/s) over which the two gravity scales blend
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float GravityBlendSpeed=100.f;

	// Fraction of speed bled off per second
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float LinearDrag=0.02f;

	// Quadratic drag reaches DragAtSoftMaxSpeed at this speed (soft speed cap)
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float SoftMaxSpeed=3000.f;

	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float DragAtSoftMaxSpeed=500.f;

	// Safety clamp only
	UPROPERTY(EditDefaultsOnly, Category = "Gravity")
	float HardMaxSpeed=5000.f;

	// Rope

	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float MinRopeLength=400.f;

	// The pump reel stops at this fraction of the rope length at attach
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float MinRopeFraction=0.65f;

	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float TautTolerance=0.5f;

	// Rope reel-in through the bottom of the arc (cm/s), the visible "hook pulls you in"
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float PumpReelInSpeed=130.f;

	// Rope pay-out near the top of the arc (cm/s)
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float PumpPayOutSpeed=100.f;

	// Tangential speed at which the pump reel runs at full rate
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float PumpFullSpeed=1500.f;

	// Exponent on OldLength/NewLength when the rope shortens (1 = exact angular momentum)
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float ReelMomentumGain=0.8f;

	// Pull of the hook on a slack rope (cm/s^2), zero while taut
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float SlackHookPull=300.f;

	// Horizontal input acceleration while the rope is slack
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float SlackAirControlAccel=350.f;

	// Slack allowed before the rope takes it up
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float SlackAllowance=120.f;

	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float SlackTakeUpSpeed=700.f;

	// Fraction of the radial kinetic energy redirected into the swing when a slack rope catches
	UPROPERTY(EditDefaultsOnly, Category = "Rope")
	float CatchEnergyRetention=0.55f;

	// Attach

	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AttachOutwardRetention=0.85f;

	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AttachInwardRetention=0.7f;

	// Swing speed floor right after the hook attaches
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AttachMinSwingSpeed=900.f;

	// How much the start direction leans towards the aimed direction (0..1)
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AttachAimBias=0.25f;

	// Web shot while looking against the motion: share of the speed heading away from the view that a taut start keeps, turned along the view (0 stops it, 1 keeps all of it)
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AgainstMotionSpeedScale=0.4f;

	// Web shot while looking against the motion: speed away from the view that the web stops completely, a slower drift is stopped in proportion
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AgainstMotionFullStopSpeed=1000.f;

	// Rising towards the anchor faster than this when the hook attaches starts the rope slack
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float AttachSlackInwardSpeed=700.f;

	// Speed multiplier per chained swing
	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	float ChainSpeedBonus=0.05f;

	UPROPERTY(EditDefaultsOnly, Category = "Attach")
	int32 MaxChainStacks=3;

	// Input

	// Global multiplier on every input effect
	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float InputAuthority=1.f;

	// Swing plane turn rate at full sideways input (deg/s)
	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float SteerTurnRateDeg=75.f;

	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float MaxSteerLateralAccel=1500.f;

	// Forward input pump in the lower arc (cm/s^2)
	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float PumpAccel=380.f;

	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float PumpMaxSpeed=2600.f;

	// Back input braking (cm/s^2)
	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float BrakeAccel=300.f;

	// Below this tangential speed input is a plain nudge
	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float LowSpeedThreshold=250.f;

	UPROPERTY(EditDefaultsOnly, Category = "Input")
	float LowSpeedInputAccel=550.f;

	// Ground

	// Gap between the capsule bottom and the floor at the bottom of the arc
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float GroundClearance=120.f;

	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float GroundReelSpeed=2400.f;

	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float GroundReelTime=0.12f;

	// Per-move diagonal floor probe that shortens the rope over rising terrain
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	bool bGroundProbe=true;

	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float ProbeLookAheadTime=0.3f;

	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float ProbeMargin=50.f;

	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float ProbeMinFloorDot=0.6f;

	// Minimum upward speed when grounded during the swing
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float GroundLiftoffSpeed=450.f;

	// Taut and faster than this on the ground skims instead of landing
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float SkimMinSpeed=700.f;

	// No landing this soon after the hook attaches
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float LandingGraceTime=0.25f;

	// Horizontal speed kept when landing
	UPROPERTY(EditDefaultsOnly, Category = "Ground")
	float LandingMaxCarrySpeed=1100.f;

	// Collision

	UPROPERTY(EditDefaultsOnly, Category = "Collision")
	float BlockTolMin=0.5f;

	UPROPERTY(EditDefaultsOnly, Category = "Collision")
	float BlockTolFull=2.f;

	UPROPERTY(EditDefaultsOnly, Category = "Collision")
	float ContactFriction=0.2f;

	// Release

	// An early release or tap is delayed until this long after the hook attaches
	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float MinSwingTimeAfterAttach=0.12f;

	// Hop when releasing at the bottom or while falling
	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float ReleaseUpBoostMin=120.f;

	// Vault when releasing while rising
	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float ReleaseUpBoostMax=500.f;

	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float ReleaseForwardBoost=300.f;

	// Rising factor reaches 1 at this dot with up (0.7 is about 45 degrees)
	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float ReleaseVaultDot=0.7f;

	UPROPERTY(EditDefaultsOnly, Category = "Release")
	float ReleaseMaxSpeed=4000.f;

	// Jump lets go of the rope
	UPROPERTY(EditDefaultsOnly, Category = "Release")
	bool bJumpReleases=true;

	// Auto-chain

	// Hold to cruise: let go near the end of each forward arc and fire the next web at the apex
	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	bool bAutoReleaseAtArcEnd=true;

	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	float AutoReleaseAngleDeg=50.f;

	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	float AutoReleasePeakFraction=0.55f;

	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	float AutoReleaseStallSpeed=350.f;

	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	float AutoReleaseMinSwingTime=0.35f;

	// Fraction of the manual release vault given on an auto-release
	UPROPERTY(EditDefaultsOnly, Category = "AutoChain")
	float AutoReleaseBonusScale=0.6f;

	// Ending and traces

	// The rope snaps after being blocked this long
	UPROPERTY(EditDefaultsOnly, Category = "Ending")
	float LOSBreakTime=0.12f;

	UPROPERTY(EditDefaultsOnly, Category = "Ending")
	float AnchorLOSInset=20.f;

	// The rope leaves the capsule at this fraction of its half height
	UPROPERTY(EditDefaultsOnly, Category = "Ending")
	float RopeAttachHeightFrac=0.5f;

	UPROPERTY(EditDefaultsOnly, Category = "Ending")
	float MaxSwingDuration=20.f;

	// Object types for anchors and every in-swing trace. WorldDynamic is in because the hex platforms keep the default
	// BlockAllDynamic profile. Keep things that move off these types, or client and server disagree on the rope.
	UPROPERTY(EditDefaultsOnly, Category = "Ending")
	TArray<TEnumAsByte<ECollisionChannel>> RopeObjectTypes={ECC_WorldStatic,ECC_WorldDynamic};
};

/**
 * Hook point and everything else both machines build the swing from. Sent once per swing from the owning client.
 */
USTRUCT()
struct AURA_API FGameplayAbilityTargetData_GrappleSwing2 : public FGameplayAbilityTargetData
{
	GENERATED_BODY()

	UPROPERTY()
	uint16 SwingId=0;

	UPROPERTY()
	FVector Anchor=FVector::ZeroVector;

	UPROPERTY()
	FVector AnchorNormal=FVector::ZeroVector;

	UPROPERTY()
	FVector StartLocation=FVector::ZeroVector;

	UPROPERTY()
	FVector PreferredSwingDir=FVector::ZeroVector;

	// Client move time stamp the source clock starts at, -1 when not an autonomous proxy
	UPROPERTY()
	float ClientStartTime=-1.f;

	UPROPERTY()
	float TravelTime=0.1f;

	UPROPERTY()
	float FloorHeight=0.f;

	UPROPERTY()
	uint8 bHasFloor=0;

	UPROPERTY()
	uint8 ChainCount=0;

	// Horizontal view direction when fired while looking against the horizontal motion, zero otherwise
	UPROPERTY()
	FVector AgainstMotionDir=FVector::ZeroVector;

	virtual UScriptStruct* GetScriptStruct() const override { return FGameplayAbilityTargetData_GrappleSwing2::StaticStruct(); }
	virtual bool HasOrigin() const override { return true; }
	virtual FTransform GetOrigin() const override { return FTransform(StartLocation); }
	virtual bool HasEndPoint() const override { return true; }
	virtual FVector GetEndPoint() const override { return Anchor; }

	bool NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess);
};

template<>
struct TStructOpsTypeTraits<FGameplayAbilityTargetData_GrappleSwing2> : public TStructOpsTypeTraitsBase2<FGameplayAbilityTargetData_GrappleSwing2>
{
	enum
	{
		WithNetSerializer = true
	};
};

/**
 * Swing simulation, run by the CharacterMovementComponent each move so it is predicted, replayed and corrected.
 *
 * Travel: the hook is flying, the source adds nothing and normal walking/falling runs.
 * Swing: the source owns the velocity. Gravity, drag and input act on its own stored velocity, then the rope can
 * only pull: velocity stretching the rope is turned (not removed), which is the tension balancing the centrifugal force.
 * Several substeps per move keep the arc the same at any frame rate.
 * Done: the last move outputs the release/landing velocity and the source is removed with it maintained.
 */
USTRUCT()
struct AURA_API FRootMotionSource_GrappleSwing2 : public FRootMotionSource
{
	GENERATED_BODY()

	FRootMotionSource_GrappleSwing2();

	virtual ~FRootMotionSource_GrappleSwing2() override = default;

	// Identity, immutable

	uint16 SwingId=0;

	FVector Anchor=FVector::ZeroVector;

	// Config, built from the target data and the tuning on each machine, never serialized

	TSharedPtr<const FGrappleSwing2Tuning> Tuning;

	float TravelTime=0.1f;

	float FloorHeight=0.f;

	bool bHasFloorBelowAnchor=false;

	FVector PreferredSwingDir=FVector::ZeroVector;

	uint8 ChainCount=0;

	FVector AgainstMotionDir=FVector::ZeroVector;

	// State, serialized and copied in UpdateStateFrom

	EGS2Phase Phase=EGS2Phase::Travel;

	bool bTaut=true;

	bool bPrevJump=false;

	EGS2EndKind EndKind=EGS2EndKind::Release;

	EGS2EndReason EndReason=EGS2EndReason::None;

	// Source clock time the swing ends at, -1 = no release requested
	float EndTime=-1.f;

	float RopeLength=1000.f;

	float InitialRopeLength=1000.f;

	float AttachTime=0.f;

	float LastDt=0.f;

	float LOSBlockedTime=0.f;

	float PeakTangentSpeed=0.f;

	FVector SwingVelocity=FVector::ZeroVector;

	FVector LastStartLocation=FVector::ZeroVector;

	FVector ExpectedLocation=FVector::ZeroVector;

	virtual FRootMotionSource* Clone() const override;
	virtual bool Matches(const FRootMotionSource* Other) const override;
	virtual bool MatchesAndHasSameState(const FRootMotionSource* Other) const override;
	virtual bool UpdateStateFrom(const FRootMotionSource* SourceToTakeStateFrom, bool bMarkForSimulatedCatchup = false) override;
	virtual void PrepareRootMotion(float SimulationTime, float MovementTickTime, const ACharacter& Character, const UCharacterMovementComponent& MoveComponent) override;
	virtual bool NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess) override;
	virtual UScriptStruct* GetScriptStruct() const override;
	virtual FString ToSimpleString() const override;

private:
	FVector AttachRedirect(const FVector& InVelocity, const FGS2MoveCtx& Ctx);
	void ApplyShortfall(FVector& V, const FGS2MoveCtx& Ctx) const;
	bool EvaluateEnds(FVector& V, float Elapsed, const FGS2MoveCtx& Ctx);
	float GroundRopeLimit(const FVector& V, const FGS2MoveCtx& Ctx) const;
	bool Substep(FVector& X, FVector& V, float& L, float H, float LGround, const FGS2MoveCtx& Ctx);
	FVector InputAccel(const FVector& In, const FVector& N, const FVector& V, const FVector& Up) const;
	FVector SteerRotate(const FVector& V, const FVector& N, const FVector& In, float H) const;
	FVector ReleaseVelocity(const FVector& V, const FVector& Up, float Scale) const;
	FVector FallbackTangent(const FVector& N, const FVector& Up) const;
	bool Finish(const FVector& VOut, EGS2EndReason Reason, const FGS2MoveCtx& Ctx);
	bool TraceStatic(const ACharacter& Character, const FVector& Start, const FVector& End, FHitResult& OutHit) const;
	static FVector DecayComp(const UCharacterMovementComponent& MoveComponent);
};

template<>
struct TStructOpsTypeTraits<FRootMotionSource_GrappleSwing2> : public TStructOpsTypeTraitsBase2<FRootMotionSource_GrappleSwing2>
{
	enum
	{
		WithNetSerializer = true,
		WithCopy = true
	};
};

/**
 * Spider-Man style grapple swing, second version. GA_GrappleSwing (v1) is left as it was.
 *
 * Press: aim-assisted search for an anchor above and ahead, then a short hook flight. Hold: a real pendulum that keeps
 * the momentum you had, reels in through the bottom of the arc, steers with sideways input and pumps with forward input.
 * Let go: a vault that depends on where in the arc you release. Keep holding: it auto-releases at the end of each arc
 * and fires the next web near the apex.
 *
 * Multiplayer: Local Predicted. The owning client sends the anchor once as target data, both machines simulate the swing
 * in a root motion source on the same moves, and the release is sent as a time on the source clock so it lands on the
 * same move on both. Simulated proxies follow the replicated movement; the rope is the looping GameplayCue.
 *
 * Blueprint setup: InputTag, add to StartupAbilities, a looping GameplayCue notify for RopeCueTag (Location = anchor,
 * EffectCauser = character, RawMagnitude = hook flight time). Add a "grappling" tag to ActivationOwnedTags and
 * block/cancel GA_JumpHover while swinging, since it changes the movement mode without prediction.
 */
UCLASS()
class AURA_API UGA_GrappleSwing2 : public UMyGameplayAbility
{
	GENERATED_BODY()

public:
	UGA_GrappleSwing2();

	// Hook search and aim assist

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float MaxGrappleDistance=4000.f;

	// Occlusion channel for the search rays
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	TEnumAsByte<ECollisionChannel> GrappleTraceChannel=ECC_Visibility;

	// The anchor must be at least this far above the predicted attach point
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float MinAnchorHeight=250.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float IdealAnchorHeight=900.f;

	// Above this the height score fades out over 1.6x
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float MaxIdealAnchorHeight=2200.f;

	// Preferred angle above the horizon from the character to the anchor
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float IdealElevationDeg=50.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float IdealRopeLength=1300.f;

	// Anchor is pushed this far off the surface along its normal
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float AnchorSurfaceOffset=8.f;

	// Half angle of the aim assist cone
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float AimAssistConeDeg=14.f;

	// The cone is pitched up by this so anchors above win
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float AimAssistUpBiasDeg=6.f;

	// Rays per ring, two rings
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	int32 AssistRaysPerRing=6;

	// Yaw spread of the fan of rays along the travel direction
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float SwingFanYawDeg=25.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	TArray<float> SwingFanElevationsDeg;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightAim=1.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightHeight=0.6f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightAhead=0.8f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightElevation=0.6f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightLength=0.4f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ScoreWeightUnderside=0.3f;

	// Score bonus for the exact crosshair hit
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float CrosshairBonus=0.5f;

	// The crosshair anchor wins if it scores within this of the best one
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float CrosshairStickiness=0.15f;

	// Re-search period while held with no anchor
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float SearchInterval=0.05f;

	// Keep searching while held, false ends the ability when nothing is found
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	bool bSearchWhileHeld=true;

	// An auto-chained web waits until the rising speed drops below this (the apex)
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ChainAttachMaxRiseSpeed=250.f;

	// Pressing again within this long after a release counts as a chain
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Hook")
	float ChainWindow=0.6f;

	// Hook travel

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Travel")
	float HookSpeed=15000.f;

	// Shortest hook flight, also the network buffer for the hook data
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Travel")
	float MinHookTravelTime=0.06f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Travel")
	float MaxHookTravelTime=0.16f;

	// Flow

	// After landing with the button held, fire a new web once airborne again (walking off a ledge)
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Flow")
	bool bRefireWhenAirborne=true;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Flow")
	float RefireAirborneDelay=0.15f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Flow")
	float GatePollInterval=0.05f;

	// Network validation

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float ServerStartTolBase=200.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float ServerStartTolSpeedTime=0.25f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float ServerRangeTolerance=300.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float ServerFloorTolerance=25.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float ServerLOSAnchorSlack=30.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float MaxStartLead=1.f;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	float MaxReleaseLead=1.f;

	// Must beat other override root motion sources
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Network")
	int32 RootMotionPriority=500;

	// Visuals

	// Looping cue while hooked. Location = anchor, Normal = anchor surface normal, RawMagnitude = hook flight time,
	// EffectCauser/Instigator = swinging character.
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Visuals")
	FGameplayTag RopeCueTag;

	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Visuals")
	bool bDrawDebug=false;

	// Everything the swing simulation reads
	UPROPERTY(EditDefaultsOnly, Category = "Grapple|Swing")
	FGrappleSwing2Tuning Swing;

	// Read-only swing state for animation or UI, works on the owner and the server
	UFUNCTION(BlueprintPure, Category = "Grapple")
	static bool GetGrappleSwing2State(const ACharacter* Character, FVector& OutAnchor, float& OutRopeLength, bool& bOutTaut);

	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags = nullptr, const FGameplayTagContainer* TargetTags = nullptr, FGameplayTagContainer* OptionalRelevantTags = nullptr) const override;

	virtual void InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) override;

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

private:
	// Search and attach (locally controlled)
	bool FindAnchor(FGS2AnchorCandidate& OutBest) const;
	bool EvaluateHit(const FHitResult& Hit, bool bCrosshair, bool bFanRay, const FGS2SearchCtx& Ctx, FGS2AnchorCandidate& Out) const;
	void TrySearchAndAttach();
	void StartSwing(const FGameplayAbilityTargetData_GrappleSwing2& Data, bool bServerForRemote);

	// Server for a remote client
	void OnServerHookData(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag);
	bool ServerValidate(const FGameplayAbilityTargetData_GrappleSwing2& Data) const;
	void ServerReject();
	void OnServerReleasePayload();

	// Owning client
	void OnServerRejected();

	// Every frame while active
	void Poll();
	void GatePoll();

	void RequestEnd(FRootMotionSource_GrappleSwing2& Src, float EndTime, EGS2EndKind Kind);
	void EndLocal();
	void RemoveCuePredicted();

	// Never stores the pointer, the movement component deep-clones sources during replays
	FRootMotionSource_GrappleSwing2* FindSource(TSharedPtr<FRootMotionSource>& OutHolder) const;

	bool TraceStatic(const FVector& Start, const FVector& End, FHitResult& OutHit) const;
	bool TraceFloor(const FVector& Anchor, float& OutFloorHeight) const;
	bool IsRopeObjectType(ECollisionChannel Channel) const;

	ACharacter* GetSwingCharacter() const;
	UCharacterMovementComponent* GetSwingMovement() const;

	EGS2AbilityState State=EGS2AbilityState::Idle;

	uint16 RootMotionSourceID=0;

	uint16 NextSwingId=0;

	uint16 LastAcceptedSwingId=0;

	EGS2EndReason LastSeenEndReason=EGS2EndReason::None;

	float AirborneTime=0.f;

	bool bIntentionalEnd=false;

	bool bBlockUntilRelease=false;

	bool bIsAutoChainActivation=false;

	bool bServerSawAttach=false;

	// The source has shown up in the movement component at least once since StartSwing
	bool bSourceSeen=false;

	// bDrawDebug: log why the first search of each activation found no anchor
	mutable bool bDebugLogSearch=false;

	double SwingStartWorldTime=0.0;

	double LastDetachWorldTime=-1000.0;

	EGS2EndReason LastDetachReason=EGS2EndReason::None;

	uint8 LastChainCount=0;

	bool bLastDetachWasRelease=false;

	// Chain count decided at activation for the swing this activation fires
	uint8 PendingChainCount=0;

	uint8 ActiveChainCount=0;

	FVector ActiveAnchor=FVector::ZeroVector;

	TSharedPtr<const FGrappleSwing2Tuning> SharedTuning;

	FPredictionKey ActiveActivationKey;

	FDelegateHandle TargetDataDelegateHandle;

	FDelegateHandle ReleasePayloadDelegateHandle;

	FDelegateHandle ServerRejectedDelegateHandle;

	FGameplayAbilitySpecHandle GateSpecHandle;

	FTimerHandle PollTimerHandle;

	FTimerHandle SearchTimerHandle;

	FTimerHandle GateTimerHandle;
};
