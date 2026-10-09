// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_GrappleSwing2.h"

#include "AbilitySystemComponent.h"
#include "CollisionQueryParams.h"
#include "DrawDebugHelpers.h"
#include "Engine/Engine.h"
#include "NativeGameplayTags.h"
#include "TimerManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/NetSerialization.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

// Names differ from v1's: a unity build can put both .cpp files in one translation unit
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_GS2_Ability,"Ability.GrappleSwing2")
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_GS2_RopeCue,"GameplayCue.GrappleRope")

DEFINE_LOG_CATEGORY_STATIC(LogGrappleSwing2,Log,All);

// bDrawDebug search diagnostics: to the log and the screen
static void GS2DebugMessage(const FString& Message)
{
	UE_LOG(LogGrappleSwing2,Warning,TEXT("%s"),*Message);
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1,5.f,FColor::Orange,Message);
	}
}

namespace GrappleSwing2
{
	const FName RootMotionInstanceName=FName("GrappleSwing2");
	const uint16 InvalidSourceID=(uint16)ERootMotionSourceID::Invalid;
	// The source is assumed lost if it never shows up in the movement component this long after StartSwing
	const double SourceAppearTimeout=1.0;

	static float Sat(float X)
	{
		return FMath::Clamp(X,0.f,1.f);
	}

	static FVector Proj(const FVector& V, const FVector& N)
	{
		return FVector::VectorPlaneProject(V,N);
	}

	// During a client replay PrepMoveFor runs before MoveAutonomous sets Acceleration, so the live value belongs to
	// the previous move. Read the replayed saved move instead.
	static FVector ReadMoveAccel(const UCharacterMovementComponent& Move)
	{
		if (const FSavedMove_Character* SavedMove=Move.GetCurrentReplayedSavedMove())
		{
			return SavedMove->Acceleration.GetClampedToMaxSize(Move.GetMaxAcceleration());
		}
		return Move.GetCurrentAcceleration();
	}

	static bool ReadMoveJump(const ACharacter& Character, const UCharacterMovementComponent& Move)
	{
		if (const FSavedMove_Character* SavedMove=Move.GetCurrentReplayedSavedMove())
		{
			return SavedMove->bPressedJump;
		}
		return Character.bPressedJump;
	}

	static FCollisionObjectQueryParams MakeObjectParams(const FGrappleSwing2Tuning& Tuning)
	{
		FCollisionObjectQueryParams ObjectParams;
		for (const TEnumAsByte<ECollisionChannel>& Channel:Tuning.RopeObjectTypes)
		{
			ObjectParams.AddObjectTypesToQuery(Channel.GetValue());
		}
		if (!ObjectParams.IsValid())
		{
			ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
		}
		return ObjectParams;
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// FGameplayAbilityTargetData_GrappleSwing2
// ---------------------------------------------------------------------------------------------------------------------

bool FGameplayAbilityTargetData_GrappleSwing2::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	// Full precision: both machines build the swing from these exact values
	Ar << SwingId;
	Ar << Anchor;
	Ar << AnchorNormal;
	Ar << StartLocation;
	Ar << PreferredSwingDir;
	Ar << ClientStartTime;
	Ar << TravelTime;
	Ar << FloorHeight;
	Ar << bHasFloor;
	Ar << ChainCount;
	bOutSuccess=true;
	return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// FRootMotionSource_GrappleSwing2
// ---------------------------------------------------------------------------------------------------------------------

FRootMotionSource_GrappleSwing2::FRootMotionSource_GrappleSwing2()
{
	// Additive with zero output while the hook flies, switched to Override when it attaches
	AccumulateMode=ERootMotionAccumulateMode::Additive;
	Priority=500;
	InstanceName=GrappleSwing2::RootMotionInstanceName;
	// Infinite, the source finishes itself
	Duration=-1.f;
	Settings.SetFlag(ERootMotionSourceSettingsFlags::UseSensitiveLiftoffCheck);
	// Clamp/Set finish velocities aren't applied in replays, so the final move outputs the end velocity itself
	FinishVelocityParams.Mode=ERootMotionFinishVelocityMode::MaintainLastRootMotionVelocity;
}

FRootMotionSource* FRootMotionSource_GrappleSwing2::Clone() const
{
	return new FRootMotionSource_GrappleSwing2(*this);
}

bool FRootMotionSource_GrappleSwing2::Matches(const FRootMotionSource* Other) const
{
	// Not the base version: it compares AccumulateMode, which this source changes at attach
	if (!Other || Other->GetScriptStruct()!=GetScriptStruct())return false;
	const FRootMotionSource_GrappleSwing2* OtherCast=static_cast<const FRootMotionSource_GrappleSwing2*>(Other);
	return Priority==Other->Priority
		&& bInLocalSpace==Other->bInLocalSpace
		&& InstanceName==Other->InstanceName
		&& FMath::IsNearlyEqual(Duration,Other->Duration,UE_SMALL_NUMBER)
		&& SwingId==OtherCast->SwingId
		&& Anchor.Equals(OtherCast->Anchor,1.f);
}

bool FRootMotionSource_GrappleSwing2::MatchesAndHasSameState(const FRootMotionSource* Other) const
{
	// A correction during a swing always replays from the server's state: saved override velocities computed from a
	// diverged path never converge on their own
	return false;
}

bool FRootMotionSource_GrappleSwing2::UpdateStateFrom(const FRootMotionSource* SourceToTakeStateFrom, bool bMarkForSimulatedCatchup)
{
	if (!FRootMotionSource::UpdateStateFrom(SourceToTakeStateFrom,bMarkForSimulatedCatchup))return false;

	const FRootMotionSource_GrappleSwing2* Other=static_cast<const FRootMotionSource_GrappleSwing2*>(SourceToTakeStateFrom);
	Phase=Other->Phase;
	AccumulateMode=Phase==EGS2Phase::Travel ? ERootMotionAccumulateMode::Additive : ERootMotionAccumulateMode::Override;
	if (Phase==EGS2Phase::Travel)
	{
		// A Travel source outputs nothing. If the server dropped the hook after this copy attached, CleanUp would add
		// the swing output left here by the last move back as an additive
		RootMotionParams.Clear();
	}
	bTaut=Other->bTaut;
	bPrevJump=Other->bPrevJump;
	EndReason=Other->EndReason;
	RopeLength=Other->RopeLength;
	InitialRopeLength=Other->InitialRopeLength;
	AttachTime=Other->AttachTime;
	LastDt=Other->LastDt;
	LOSBlockedTime=Other->LOSBlockedTime;
	PeakTangentSpeed=Other->PeakTangentSpeed;
	SwingVelocity=Other->SwingVelocity;
	LastStartLocation=Other->LastStartLocation;
	ExpectedLocation=Other->ExpectedLocation;
	// Earliest valid release wins, so a replay never undoes a release
	if (Other->EndTime>=0.f && (EndTime<0.f || Other->EndTime<EndTime))
	{
		EndTime=Other->EndTime;
		EndKind=Other->EndKind;
	}
	// Config and tuning stay as they are
	return true;
}

FVector FRootMotionSource_GrappleSwing2::DecayComp(const UCharacterMovementComponent& MoveComponent)
{
	// CMC adds this to an override velocity while falling, take it out so the displacement is exactly ours
	return MoveComponent.IsFalling() ? MoveComponent.DecayingFormerBaseVelocity : FVector::ZeroVector;
}

bool FRootMotionSource_GrappleSwing2::TraceStatic(const ACharacter& Character, const FVector& Start, const FVector& End, FHitResult& OutHit) const
{
	UWorld* World=Character.GetWorld();
	if (!World || !Tuning.IsValid())return false;
	const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwing2Rope),false,&Character);
	return World->LineTraceSingleByObjectType(OutHit,Start,End,GrappleSwing2::MakeObjectParams(*Tuning),QueryParams);
}

void FRootMotionSource_GrappleSwing2::PrepareRootMotion(float SimulationTime, float MovementTickTime, const ACharacter& Character, const UCharacterMovementComponent& MoveComponent)
{
	RootMotionParams.Clear();
	const float T0=GetTime();
	const float T1=T0+SimulationTime;
	const float Dt=MovementTickTime;

	if (!Tuning.IsValid())
	{
		if (AccumulateMode==ERootMotionAccumulateMode::Override)
		{
			RootMotionParams.Set(FTransform(SwingVelocity));
		}
		SetTime(T1);
		return;
	}
	if (Dt<=UE_SMALL_NUMBER)
	{
		if (Phase!=EGS2Phase::Travel)
		{
			RootMotionParams.Set(FTransform(SwingVelocity));
		}
		SetTime(T1);
		return;
	}

	const FGrappleSwing2Tuning& P=*Tuning;

	FGS2MoveCtx Ctx;
	Ctx.Character=&Character;
	Ctx.Move=&MoveComponent;
	Ctx.X0=MoveComponent.UpdatedComponent->GetComponentLocation();
	Ctx.Up=-MoveComponent.GetGravityDirection();
	Ctx.G=-MoveComponent.GetGravityZ();
	Ctx.HalfHeight=Character.GetCapsuleComponent() ? Character.GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
	Ctx.Dt=Dt;
	Ctx.T1=T1;
	Ctx.bJump=GrappleSwing2::ReadMoveJump(Character,MoveComponent);
	Ctx.In=(GrappleSwing2::ReadMoveAccel(MoveComponent)/FMath::Max(MoveComponent.GetMaxAcceleration(),1.f)).GetClampedToMaxSize(1.f)*P.InputAuthority;

	// (1) Travel: the hook is in flight, zero additive so normal walking/falling runs
	FVector V;
	if (Phase==EGS2Phase::Travel)
	{
		// Ended before the hook arrived (cancel, death, failed activation): drop the hook and leave the velocity alone.
		// A tap always asks for TravelTime+MinSwingTimeAfterAttach or later, so it still gets its short swing.
		// Phase stays Travel, so corrections keep deriving Additive.
		if (EndTime>=0.f && EndTime<TravelTime-1.e-4f && T0>=EndTime-1.e-4f)
		{
			EndReason=EGS2EndReason::Forced;
			AccumulateMode=ERootMotionAccumulateMode::Additive;
			bPrevJump=Ctx.bJump;
			// Duration<0, so only this flag ends it
			Status.SetFlag(ERootMotionSourceStatusFlags::Finished);
			SetTime(T1);
			return;
		}
		if (SimulationTime<=0.f || T1<TravelTime-1.e-4f)
		{
			AccumulateMode=ERootMotionAccumulateMode::Additive;
			bPrevJump=Ctx.bJump;
			SetTime(T1);
			return;
		}
		Phase=EGS2Phase::Swing;
		AccumulateMode=ERootMotionAccumulateMode::Override;
		AttachTime=T1;
		// The only read of the movement component's velocity: the momentum the character had when the hook attached
		V=AttachRedirect(MoveComponent.Velocity,Ctx);
		bPrevJump=Ctx.bJump;
	}
	else if (Phase==EGS2Phase::Swing)
	{
		// State owned by the source, never the movement component's velocity (corrections only restore its Z)
		V=SwingVelocity;
		ApplyShortfall(V,Ctx);
	}
	else
	{
		RootMotionParams.Set(FTransform(SwingVelocity));
		SetTime(T1);
		return;
	}

	// (2) End decisions, once per move before integrating
	const float Elapsed=FMath::Max(T0-AttachTime,0.f);
	if (EvaluateEnds(V,Elapsed,Ctx))return;
	bPrevJump=Ctx.bJump;

	// (3) Ground limit, once per move
	const float LGround=GroundRopeLimit(V,Ctx);

	// (4) Substeps
	const int32 NumSteps=FMath::Clamp(FMath::CeilToInt(Dt/FMath::Max(P.MaxSubstepDt,1.e-3f)),1,FMath::Max(P.MaxSubsteps,1));
	const float H=Dt/NumSteps;
	FVector X=Ctx.X0;
	float L=RopeLength;
	for (int32 i=0;i<NumSteps;++i)
	{
		if (!Substep(X,V,L,H,LGround,Ctx))break;
	}

	// (5) Output the displacement as a velocity, like MoveToForce, and keep the state
	const FVector Out=(X-Ctx.X0)/Dt;
	RootMotionParams.Set(FTransform(Out-DecayComp(MoveComponent)));
	SwingVelocity=V;
	RopeLength=L;
	LastStartLocation=Ctx.X0;
	ExpectedLocation=X;
	LastDt=Dt;
	SetTime(T1);
}

FVector FRootMotionSource_GrappleSwing2::AttachRedirect(const FVector& InVelocity, const FGS2MoveCtx& Ctx)
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector& Up=Ctx.Up;
	const FVector R=Ctx.X0-Anchor;
	const float D=R.Size();
	const FVector N=D>1.f ? R/D : -Up;

	RopeLength=InitialRopeLength=FMath::Max(P.MinRopeLength,D);

	const float Vr=InVelocity|N;
	const FVector Vt=InVelocity-N*Vr;
	FVector V;
	if (Vr<-P.AttachSlackInwardSpeed && (InVelocity|Up)>0.f)
	{
		// Flying up at the anchor: the rope starts slack and catches later
		V=InVelocity;
		bTaut=false;
	}
	else
	{
		// Keep the tangential speed and a fraction of the radial kinetic energy, redirected along the arc
		const float K=Vr>0.f ? P.AttachOutwardRetention : P.AttachInwardRetention;
		const float Speed=FMath::Sqrt(Vt.SizeSquared()+K*Vr*Vr);
		FVector Aim=GrappleSwing2::Proj(PreferredSwingDir,N).GetSafeNormal();
		if (Aim.IsNearlyZero())
		{
			Aim=GrappleSwing2::Proj(-Up,N).GetSafeNormal();
		}
		const float VtSize=Vt.Size();
		const FVector MDir=VtSize>50.f ? Vt/VtSize : Aim;
		FVector Dir=(MDir*(1.f-P.AttachAimBias)+Aim*P.AttachAimBias).GetSafeNormal();
		if (Dir.IsNearlyZero())
		{
			Dir=MDir;
		}
		V=Dir*FMath::Max(Speed,P.AttachMinSwingSpeed);
		bTaut=true;
	}

	V*=1.f+FMath::Min<int32>(ChainCount,P.MaxChainStacks)*P.ChainSpeedBonus;
	if (Ctx.Move->IsMovingOnGround())
	{
		// Sensitive liftoff turns this into Falling
		V+=Up*FMath::Max(0.f,P.GroundLiftoffSpeed-(float)(V|Up));
	}
	V=V.GetClampedToMaxSize(P.HardMaxSpeed);

	PeakTangentSpeed=GrappleSwing2::Proj(V,N).Size();
	LOSBlockedTime=0.f;
	EndReason=EGS2EndReason::None;
	// No expected location from the travel moves, so no collision response on the attach move
	LastDt=0.f;
	return V;
}

void FRootMotionSource_GrappleSwing2::ApplyShortfall(FVector& V, const FGS2MoveCtx& Ctx) const
{
	const FGrappleSwing2Tuning& P=*Tuning;
	if (LastDt<=0.f)return;

	const FVector Intended=ExpectedLocation-LastStartLocation;
	const FVector Actual=Ctx.X0-LastStartLocation;
	const FVector Short=Intended-Actual;
	const float M=Short.Size();
	if (M<=P.BlockTolMin)return;
	// Got further or went sideways: a teleport, correction or moving base, not a hit
	if (Actual.SizeSquared()>Intended.SizeSquared()+FMath::Square(P.BlockTolMin) || M>Intended.Size()+P.BlockTolMin)return;

	const float W=FMath::SmoothStep(P.BlockTolMin,FMath::Max(P.BlockTolFull,P.BlockTolMin+0.01f),M);
	// Points into the obstacle
	const FVector NB=Short/M;
	const float Vn=V|NB;
	if (Vn>0.f)
	{
		// Remove the into-surface velocity and keep the slide, with a little friction
		V-=NB*Vn*W;
		const FVector Vs=GrappleSwing2::Proj(V,NB);
		V-=Vs*P.ContactFriction*W*GrappleSwing2::Sat(Vn/FMath::Max((float)V.Size(),1.f));
	}
}

FVector FRootMotionSource_GrappleSwing2::ReleaseVelocity(const FVector& V, const FVector& Up, float Scale) const
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const float S=V.Size();
	if (!bTaut || Scale<=0.f || S<=UE_KINDA_SMALL_NUMBER)return V;

	// 0 when level or falling, 1 when rising steeply
	const float F=GrappleSwing2::Sat(((V/S)|Up)/FMath::Max(P.ReleaseVaultDot,0.01f));
	const FVector Vh=GrappleSwing2::Proj(V,Up).GetSafeNormal();
	const FVector VRelease=V+Up*FMath::Lerp(P.ReleaseUpBoostMin,P.ReleaseUpBoostMax,F)*Scale+Vh*P.ReleaseForwardBoost*F*Scale;
	return VRelease.GetClampedToMaxSize(FMath::Max(P.ReleaseMaxSpeed,S));
}

bool FRootMotionSource_GrappleSwing2::Finish(const FVector& VOut, EGS2EndReason Reason, const FGS2MoveCtx& Ctx)
{
	// The final move: its override is still applied this move, then the source is removed with Maintain
	Phase=EGS2Phase::Done;
	EndReason=Reason;
	AccumulateMode=ERootMotionAccumulateMode::Override;
	RootMotionParams.Set(FTransform(VOut-DecayComp(*Ctx.Move)));
	SwingVelocity=VOut;
	LastStartLocation=Ctx.X0;
	ExpectedLocation=Ctx.X0+VOut*Ctx.Dt;
	LastDt=Ctx.Dt;
	bPrevJump=Ctx.bJump;
	// Duration<0, so the time-out check never clears this
	Status.SetFlag(ERootMotionSourceStatusFlags::Finished);
	SetTime(Ctx.T1);
	return true;
}

bool FRootMotionSource_GrappleSwing2::EvaluateEnds(FVector& V, float Elapsed, const FGS2MoveCtx& Ctx)
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector& Up=Ctx.Up;
	const float T0=GetTime();
	const FVector R0=Ctx.X0-Anchor;
	const float D0=R0.Size();
	const FVector N0=D0>1.f ? R0/D0 : -Up;

	// a) Release request (button up or ability end), set by the ability on each machine
	if (EndTime>=0.f && T0>=EndTime-1.e-4f)
	{
		const bool bForced=EndKind==EGS2EndKind::Forced;
		return Finish(bForced ? V : ReleaseVelocity(V,Up,1.f),bForced ? EGS2EndReason::Forced : EGS2EndReason::Released,Ctx);
	}

	// b) Jump lets go. The jump flag travels in the move stream, so this needs no RPC
	if (P.bJumpReleases && Ctx.bJump && !bPrevJump && Elapsed>=P.MinSwingTimeAfterAttach)
	{
		return Finish(ReleaseVelocity(V,Up,1.f),EGS2EndReason::JumpReleased,Ctx);
	}

	// c) Watchdog
	if (Elapsed>=P.MaxSwingDuration)
	{
		return Finish(V,EGS2EndReason::Timeout,Ctx);
	}

	// d) Too close to the anchor
	if (D0<0.5f*P.MinRopeLength)
	{
		return Finish(V,EGS2EndReason::TooClose,Ctx);
	}

	// e) Rope line of sight against static geometry, allowed to be blocked briefly
	const FVector RopePoint=Ctx.X0+Up*Ctx.HalfHeight*P.RopeAttachHeightFrac;
	if (FVector::Dist(Anchor,RopePoint)>P.AnchorLOSInset+1.f)
	{
		FHitResult Hit;
		const bool bBlocked=TraceStatic(*Ctx.Character,RopePoint,Anchor-(Anchor-RopePoint).GetSafeNormal()*P.AnchorLOSInset,Hit);
		LOSBlockedTime=bBlocked ? LOSBlockedTime+Ctx.Dt : 0.f;
		if (LOSBlockedTime>P.LOSBreakTime)
		{
			return Finish(V,EGS2EndReason::Snapped,Ctx);
		}
	}

	// f) Ground contact: skim at speed, land when slow or slack
	if (Ctx.Move->IsMovingOnGround())
	{
		const float Vt=GrappleSwing2::Proj(V,N0).Size();
		if (Elapsed<P.LandingGraceTime || (bTaut && Vt>=P.SkimMinSpeed))
		{
			V+=Up*FMath::Max(0.f,P.GroundLiftoffSpeed-(float)(V|Up));
		}
		else
		{
			return Finish(GrappleSwing2::Proj(V,Up).GetClampedToMaxSize(P.LandingMaxCarrySpeed),EGS2EndReason::Landed,Ctx);
		}
	}

	// g) Hold to cruise: let go near the end of the forward arc (rising and moving away from the anchor axis)
	if (P.bAutoReleaseAtArcEnd && Elapsed>=P.AutoReleaseMinSwingTime && bTaut && (V|Up)>0.f
		&& (GrappleSwing2::Proj(V,Up)|GrappleSwing2::Proj(R0,Up))>0.f)
	{
		// 0 = straight below the anchor
		const float Phi=FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(-(float)(N0|Up),-1.f,1.f)));
		const float Vt=GrappleSwing2::Proj(V,N0).Size();
		if (Phi>=P.AutoReleaseAngleDeg || Vt<=FMath::Max(P.AutoReleaseStallSpeed,P.AutoReleasePeakFraction*PeakTangentSpeed))
		{
			return Finish(ReleaseVelocity(V,Up,P.AutoReleaseBonusScale),EGS2EndReason::AutoReleased,Ctx);
		}
	}
	return false;
}

float FRootMotionSource_GrappleSwing2::GroundRopeLimit(const FVector& V, const FGS2MoveCtx& Ctx) const
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector& Up=Ctx.Up;
	const float AnchorHeight=(float)(Anchor|Up);

	// Keep the bottom of the arc GroundClearance above the floor under the anchor
	float LGround=bHasFloorBelowAnchor ? AnchorHeight-FloorHeight-Ctx.HalfHeight-P.GroundClearance : 1.e9f;

	const FVector R=Ctx.X0-Anchor;
	const float Hang=GrappleSwing2::Sat(-(R.GetSafeNormal()|Up));
	if (P.bGroundProbe && (R|Up)<0.f && ((V|Up)<0.f || Hang>0.82f))
	{
		// One diagonal ray: the floor below and ahead
		const float Depth=Ctx.HalfHeight+P.GroundClearance+FMath::Max(0.f,-(float)(V|Up))*P.ProbeLookAheadTime+P.ProbeMargin;
		const FVector End=Ctx.X0+GrappleSwing2::Proj(V,Up)*P.ProbeLookAheadTime-Up*Depth;
		FHitResult Hit;
		// Walls are ignored
		if (TraceStatic(*Ctx.Character,Ctx.X0,End,Hit) && (Hit.ImpactNormal|Up)>=P.ProbeMinFloorDot)
		{
			LGround=FMath::Min(LGround,AnchorHeight-(float)(Hit.ImpactPoint|Up)-Ctx.HalfHeight-P.GroundClearance);
		}
	}
	return FMath::Max(LGround,P.MinRopeLength);
}

FVector FRootMotionSource_GrappleSwing2::FallbackTangent(const FVector& N, const FVector& Up) const
{
	FVector Dir=GrappleSwing2::Proj(PreferredSwingDir,N).GetSafeNormal();
	if (Dir.IsNearlyZero())
	{
		Dir=GrappleSwing2::Proj(-Up,N).GetSafeNormal();
	}
	return Dir;
}

FVector FRootMotionSource_GrappleSwing2::InputAccel(const FVector& In, const FVector& N, const FVector& V, const FVector& Up) const
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector It=GrappleSwing2::Proj(In,N);
	const FVector Vt=GrappleSwing2::Proj(V,N);
	const float S=Vt.Size();
	// From a dead hang input is a plain nudge to start swinging
	if (S<P.LowSpeedThreshold)return It*P.LowSpeedInputAccel;

	const FVector E=Vt/S;
	const float Along=It|E;
	const float Hang=GrappleSwing2::Sat(-(N|Up));
	// Forward pumps in the lower arc and fades with speed, back input brakes
	const float Pump=Along>0.f
		? P.PumpAccel*Along*Hang*GrappleSwing2::Sat(1.f-S/FMath::Max(P.PumpMaxSpeed,1.f))
		: P.BrakeAccel*Along;
	return E*Pump;
}

FVector FRootMotionSource_GrappleSwing2::SteerRotate(const FVector& V, const FVector& N, const FVector& In, float H) const
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector It=GrappleSwing2::Proj(In,N);
	const FVector Vt=GrappleSwing2::Proj(V,N);
	const float S=Vt.Size();
	if (S<P.LowSpeedThreshold)return V;

	const FVector E=Vt/S;
	const FVector Lateral=It-E*(It|E);
	const float M=Lateral.Size();
	if (M<0.05f)return V;

	// Turn the swing plane around the rope: adds no energy, keeps |V| and the radial part
	const float Omega=FMath::Min(FMath::DegreesToRadians(P.SteerTurnRateDeg)*M,P.MaxSteerLateralAccel/S);
	const float Sign=FMath::Sign((float)((E^Lateral)|N));
	return V.RotateAngleAxisRad(Sign*Omega*H,N);
}

bool FRootMotionSource_GrappleSwing2::Substep(FVector& X, FVector& V, float& L, float H, float LGround, const FGS2MoveCtx& Ctx)
{
	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector& Up=Ctx.Up;

	const FVector R=X-Anchor;
	const float D=R.Size();
	// TooClose is decided next move
	if (D<1.f)return false;
	const FVector N=R/D;
	const float Hang=GrappleSwing2::Sat(-(N|Up));
	const float Vt=GrappleSwing2::Proj(V,N).Size();

	// (a) Rope length this substep: pump reel through the bottom, pay-out near the top, ground reel. Rate > 0 shortens.
	const float LMin=FMath::Max(P.MinRopeLength,InitialRopeLength*P.MinRopeFraction);
	const float LMax=FMath::Max(P.MinRopeLength,FMath::Min(InitialRopeLength,LGround));
	float Rate=0.f;
	if (bTaut)
	{
		if (L>LMin)
		{
			Rate+=P.PumpReelInSpeed*FMath::SmoothStep(0.5f,0.9f,Hang)*GrappleSwing2::Sat(Vt/FMath::Max(P.PumpFullSpeed,1.f));
		}
		if (L<LMax)
		{
			Rate-=P.PumpPayOutSpeed*(1.f-FMath::SmoothStep(0.f,0.5f,Hang));
		}
	}
	// The ground always wins
	if (L>LGround)
	{
		Rate=FMath::Max(Rate,FMath::Min(P.GroundReelSpeed,(L-LGround)/FMath::Max(P.GroundReelTime,1.e-3f)));
	}
	// Reeling never lengthens, paying out never passes LMax
	float LNew=FMath::Clamp(L-Rate*H,P.MinRopeLength,FMath::Max(Rate>=0.f ? L : LMax,P.MinRopeLength));

	// (b) Forces. There is never a constant pull while taut
	const float GravityScale=FMath::Lerp(P.GravityScaleAscending,P.GravityScaleDescending,
		FMath::SmoothStep(-P.GravityBlendSpeed,P.GravityBlendSpeed,-(float)(V|Up)));
	const float QuadDrag=P.DragAtSoftMaxSpeed/FMath::Max(FMath::Square(P.SoftMaxSpeed),1.f);
	FVector A=-Up*Ctx.G*GravityScale;
	// Soft speed cap
	A-=V*(P.LinearDrag+QuadDrag*V.Size());
	if (bTaut)
	{
		A+=InputAccel(Ctx.In,N,V,Up);
	}
	else
	{
		// The hook draws in slack
		A+=GrappleSwing2::Proj(Ctx.In,Up)*P.SlackAirControlAccel-N*P.SlackHookPull;
	}
	V+=A*H;
	if (bTaut)
	{
		V=SteerRotate(V,N,Ctx.In,H);
	}

	// (c) Tension before drift: the rope can only pull
	if (bTaut)
	{
		const float Vr=V|N;
		if (Vr>0.f)
		{
			V-=N*Vr;
		}
	}

	// (d) Drift
	FVector XF=X+V*H;
	const FVector RF=XF-Anchor;
	const float DF=RF.Size();
	const FVector NF=DF>UE_KINDA_SMALL_NUMBER ? RF/DF : N;

	// (e) Constraint
	if (bTaut && DF>=L-P.TautTolerance)
	{
		// Still taut against the old length, so paying out does not flicker slack
		XF=Anchor+NF*LNew;
		const float S=V.Size();
		float Vr=V|NF;
		if (Vr>0.f)
		{
			// Exact centripetal turn: the direction changes, the speed is kept
			V=(V-NF*Vr).GetSafeNormal()*S;
		}
		if (LNew!=L)
		{
			// Angular momentum: shortening the rope speeds the swing up
			Vr=V|NF;
			V=NF*Vr+(V-NF*Vr)*FMath::Pow(L/LNew,P.ReelMomentumGain);
		}
	}
	else if (!bTaut && DF>LNew)
	{
		// A slack rope catches: the radial impact is partly redirected into the swing
		XF=Anchor+NF*LNew;
		const float Vr=V|NF;
		if (Vr>0.f)
		{
			const FVector VtF=V-NF*Vr;
			const float VtSize=VtF.Size();
			FVector Dir=VtSize>50.f ? VtF/VtSize : FallbackTangent(NF,Up);
			if (Dir.IsNearlyZero())
			{
				Dir=VtF.GetSafeNormal();
			}
			V=Dir*FMath::Sqrt(VtF.SizeSquared()+P.CatchEnergyRetention*Vr*Vr);
		}
		bTaut=true;
	}
	else
	{
		// Moving inward faster than the rope: slack, taken up beyond the allowance
		bTaut=false;
		if (LNew-DF>P.SlackAllowance)
		{
			LNew=FMath::Max(DF+P.SlackAllowance,LNew-P.SlackTakeUpSpeed*H);
		}
	}

	V=V.GetClampedToMaxSize(P.HardMaxSpeed);
	X=XF;
	L=LNew;
	PeakTangentSpeed=FMath::Max(PeakTangentSpeed,(float)GrappleSwing2::Proj(V,NF).Size());
	return true;
}

bool FRootMotionSource_GrappleSwing2::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	if (!FRootMotionSource::NetSerialize(Ar,Map,bOutSuccess))return false;

	// Loading can reuse an existing struct, so every field is written and read
	Ar << SwingId;
	SerializePackedVector<100,30>(Anchor,Ar);

	uint8 Flags=0;
	if (Ar.IsSaving())
	{
		Flags=(uint8)Phase&3;
		Flags|=(bTaut ? 1 : 0)<<2;
		Flags|=(bPrevJump ? 1 : 0)<<3;
		Flags|=(EndTime>=0.f ? 1 : 0)<<4;
		Flags|=((uint8)EndKind&1)<<5;
	}
	Ar << Flags;
	if (Ar.IsLoading())
	{
		Phase=(EGS2Phase)(Flags&3);
		bTaut=((Flags>>2)&1)!=0;
		bPrevJump=((Flags>>3)&1)!=0;
		EndKind=(EGS2EndKind)((Flags>>5)&1);
	}

	uint8 Reason=(uint8)EndReason;
	Ar << Reason;
	EndReason=(EGS2EndReason)Reason;

	Ar << RopeLength;
	Ar << InitialRopeLength;
	Ar << AttachTime;
	Ar << LastDt;
	Ar << LOSBlockedTime;
	Ar << PeakTangentSpeed;
	SerializePackedVector<100,30>(SwingVelocity,Ar);
	SerializePackedVector<100,30>(LastStartLocation,Ar);
	SerializePackedVector<100,30>(ExpectedLocation,Ar);

	if (Flags&(1<<4))
	{
		Ar << EndTime;
	}
	else if (Ar.IsLoading())
	{
		EndTime=-1.f;
	}

	if (Ar.IsLoading())
	{
		AccumulateMode=Phase==EGS2Phase::Travel ? ERootMotionAccumulateMode::Additive : ERootMotionAccumulateMode::Override;
	}

	bOutSuccess=true;
	return true;
}

UScriptStruct* FRootMotionSource_GrappleSwing2::GetScriptStruct() const
{
	return FRootMotionSource_GrappleSwing2::StaticStruct();
}

FString FRootMotionSource_GrappleSwing2::ToSimpleString() const
{
	return FString::Printf(TEXT("[ID:%u]FRootMotionSource_GrappleSwing2 %s Swing(%u) Phase(%d) Rope(%.0f) Speed(%.0f) EndTime(%.3f)"),
		LocalID,*InstanceName.GetPlainNameString(),SwingId,(int32)Phase,RopeLength,SwingVelocity.Size(),EndTime);
}

// ---------------------------------------------------------------------------------------------------------------------
// UGA_GrappleSwing2
// ---------------------------------------------------------------------------------------------------------------------

UGA_GrappleSwing2::UGA_GrappleSwing2()
{
	InstancingPolicy=EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy=EGameplayAbilityNetExecutionPolicy::LocalPredicted;
	AbilityTag=TAG_GS2_Ability;
	RopeCueTag=TAG_GS2_RopeCue;
	SwingFanElevationsDeg={35.f,50.f,65.f};
	RootMotionSourceID=GrappleSwing2::InvalidSourceID;
}

ACharacter* UGA_GrappleSwing2::GetSwingCharacter() const
{
	return Cast<ACharacter>(GetAvatarActorFromActorInfo());
}

UCharacterMovementComponent* UGA_GrappleSwing2::GetSwingMovement() const
{
	ACharacter* Character=GetSwingCharacter();
	return Character ? Character->GetCharacterMovement() : nullptr;
}

FRootMotionSource_GrappleSwing2* UGA_GrappleSwing2::FindSource(TSharedPtr<FRootMotionSource>& OutHolder) const
{
	OutHolder.Reset();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!MoveComp || RootMotionSourceID==GrappleSwing2::InvalidSourceID)return nullptr;
	OutHolder=MoveComp->GetRootMotionSourceByID(RootMotionSourceID);
	if (!OutHolder.IsValid() || OutHolder->GetScriptStruct()!=FRootMotionSource_GrappleSwing2::StaticStruct())
	{
		OutHolder.Reset();
		return nullptr;
	}
	return static_cast<FRootMotionSource_GrappleSwing2*>(OutHolder.Get());
}

bool UGA_GrappleSwing2::GetGrappleSwing2State(const ACharacter* Character, FVector& OutAnchor, float& OutRopeLength, bool& bOutTaut)
{
	OutAnchor=FVector::ZeroVector;
	OutRopeLength=0.f;
	bOutTaut=false;
	const UCharacterMovementComponent* MoveComp=Character ? Character->GetCharacterMovement() : nullptr;
	if (!MoveComp)return false;
	for (const TSharedPtr<FRootMotionSource>& Source:MoveComp->CurrentRootMotion.RootMotionSources)
	{
		if (Source.IsValid() && Source->GetScriptStruct()==FRootMotionSource_GrappleSwing2::StaticStruct())
		{
			const FRootMotionSource_GrappleSwing2* Swing=static_cast<const FRootMotionSource_GrappleSwing2*>(Source.Get());
			if (Swing->Phase!=EGS2Phase::Swing)continue;
			OutAnchor=Swing->Anchor;
			OutRopeLength=Swing->RopeLength;
			bOutTaut=Swing->bTaut;
			return true;
		}
	}
	return false;
}

bool UGA_GrappleSwing2::IsRopeObjectType(ECollisionChannel Channel) const
{
	for (const TEnumAsByte<ECollisionChannel>& Type:Swing.RopeObjectTypes)
	{
		if (Type.GetValue()==Channel)return true;
	}
	return Swing.RopeObjectTypes.Num()==0 && Channel==ECC_WorldStatic;
}

bool UGA_GrappleSwing2::TraceStatic(const FVector& Start, const FVector& End, FHitResult& OutHit) const
{
	const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwing2Static),false,GetSwingCharacter());
	return GetWorld()->LineTraceSingleByObjectType(OutHit,Start,End,GrappleSwing2::MakeObjectParams(Swing),QueryParams);
}

bool UGA_GrappleSwing2::TraceFloor(const FVector& Anchor, float& OutFloorHeight) const
{
	const UCharacterMovementComponent* MoveComp=GetSwingMovement();
	const FVector Up=MoveComp ? -MoveComp->GetGravityDirection() : FVector::UpVector;
	FHitResult Hit;
	if (TraceStatic(Anchor-Up*20.f,Anchor-Up*(MaxGrappleDistance+3000.f),Hit))
	{
		OutFloorHeight=Hit.ImpactPoint|Up;
		return true;
	}
	OutFloorHeight=0.f;
	return false;
}

bool UGA_GrappleSwing2::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	// Re-fire gate after an external end while the button was held, cleared when the button goes up
	if (bBlockUntilRelease)return false;
	// Airborne only: Falling means in the air and not hovering (GA_JumpHover uses MOVE_Flying).
	// Owning client only: the server can still be a move behind the client's jump, and failing there would cancel it.
	if (ActorInfo && ActorInfo->IsLocallyControlled())
	{
		const UCharacterMovementComponent* MoveComp=Cast<UCharacterMovementComponent>(ActorInfo->MovementComponent.Get());
		if (!MoveComp || !MoveComp->IsFalling())return false;
	}
	return Super::CanActivateAbility(Handle,ActorInfo,SourceTags,TargetTags,OptionalRelevantTags);
}

void UGA_GrappleSwing2::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle,ActorInfo,ActivationInfo,TriggerEventData);

	ACharacter* Character=GetSwingCharacter();
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (!Character || !GetSwingMovement() || !ASC)
	{
		EndAbility(Handle,ActorInfo,ActivationInfo,true,true);
		return;
	}

	if (!SharedTuning.IsValid())
	{
		SharedTuning=MakeShared<FGrappleSwing2Tuning>(Swing);
	}

	State=EGS2AbilityState::Searching;
	bIntentionalEnd=false;
	bServerSawAttach=false;
	bSourceSeen=false;
	RootMotionSourceID=GrappleSwing2::InvalidSourceID;
	AirborneTime=0.f;
	ActiveActivationKey=ActivationInfo.GetActivationPredictionKey();

	PollTimerHandle=GetWorld()->GetTimerManager().SetTimerForNextTick(this,&ThisClass::Poll);

	const bool bAuthority=HasAuthority(&ActivationInfo);
	const bool bLocal=IsLocallyControlled();

	if (bAuthority && !bLocal)
	{
		// Server for a remote client: wait for the hook data and the release time
		TargetDataDelegateHandle=ASC->AbilityTargetDataSetDelegate(Handle,ActiveActivationKey).AddUObject(this,&ThisClass::OnServerHookData);
		ReleasePayloadDelegateHandle=ASC->AbilityReplicatedEventDelegate(EAbilityGenericReplicatedEvent::GameCustom1,Handle,ActiveActivationKey).AddUObject(this,&ThisClass::OnServerReleasePayload);
		ASC->CallReplicatedTargetDataDelegatesIfSet(Handle,ActiveActivationKey);
		if (IsActive())
		{
			ASC->CallReplicatedEventDelegateIfSet(EAbilityGenericReplicatedEvent::GameCustom1,Handle,ActiveActivationKey);
		}
		return;
	}

	if (bLocal && !bAuthority)
	{
		ServerRejectedDelegateHandle=ASC->AbilityReplicatedEventDelegate(EAbilityGenericReplicatedEvent::GenericSignalFromServer,Handle,ActiveActivationKey).AddUObject(this,&ThisClass::OnServerRejected);
	}

	if (bLocal)
	{
		const double Now=GetWorld()->GetTimeSeconds();
		const bool bInChainWindow=Now-LastDetachWorldTime<=ChainWindow;
		bIsAutoChainActivation=bInChainWindow && LastDetachReason==EGS2EndReason::AutoReleased;
		// Decided at activation, so waiting for the apex before the next web still counts as a chain
		PendingChainCount=bInChainWindow && bLastDetachWasRelease ? (uint8)FMath::Min<int32>(LastChainCount+1,Swing.MaxChainStacks) : 0;

		bDebugLogSearch=bDrawDebug;
		TrySearchAndAttach();
		if (IsActive() && State==EGS2AbilityState::Searching)
		{
			if (bSearchWhileHeld)
			{
				GetWorld()->GetTimerManager().SetTimer(SearchTimerHandle,this,&ThisClass::TrySearchAndAttach,FMath::Max(SearchInterval,0.01f),true);
			}
			else
			{
				// Nothing to hook: end, and the gate stops the held button from re-firing every frame
				bIntentionalEnd=false;
				EndAbility(Handle,ActorInfo,ActivationInfo,true,false);
			}
		}
	}
}

bool UGA_GrappleSwing2::FindAnchor(FGS2AnchorCandidate& OutBest) const
{
	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	APlayerController* PC=Character ? Cast<APlayerController>(Character->GetController()) : nullptr;
	if (!PC || !MoveComp)
	{
		if (bDebugLogSearch)
		{
			GS2DebugMessage(TEXT("GrappleSwing2 search skipped: no PlayerController or movement component"));
		}
		return false;
	}

	FGS2SearchCtx Ctx;
	FRotator ViewRot;
	PC->GetPlayerViewPoint(Ctx.ViewLoc,ViewRot);
	Ctx.ViewDir=ViewRot.Vector();
	Ctx.Pos=Character->GetActorLocation();
	Ctx.Up=-MoveComp->GetGravityDirection();
	Ctx.HalfHeight=Character->GetCapsuleComponent() ? Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
	const FVector V=MoveComp->Velocity;
	const float G=-MoveComp->GetGravityZ();

	// Auto-chain: wait for the apex so the next web does not drag the release vault down
	if (bIsAutoChainActivation && (V|Ctx.Up)>ChainAttachMaxRiseSpeed)
	{
		if (bDebugLogSearch)
		{
			GS2DebugMessage(FString::Printf(TEXT("GrappleSwing2 search waiting for the apex (rising %.0f > %.0f)"),(float)(V|Ctx.Up),ChainAttachMaxRiseSpeed));
		}
		return false;
	}

	// Where the character will be when the hook arrives
	const float TravelGuess=FMath::Clamp(IdealRopeLength/FMath::Max(HookSpeed,1.f),MinHookTravelTime,MaxHookTravelTime);
	Ctx.AttachPos=Ctx.Pos+V*TravelGuess-Ctx.Up*0.5f*G*TravelGuess*TravelGuess;
	const FVector VH=GrappleSwing2::Proj(V,Ctx.Up);
	const FVector ViewH=GrappleSwing2::Proj(Ctx.ViewDir,Ctx.Up).GetSafeNormal();
	Ctx.MoveDirH=VH.Size()>400.f ? VH.GetSafeNormal() : ViewH;
	if (Ctx.MoveDirH.IsNearlyZero())
	{
		Ctx.MoveDirH=Character->GetActorForwardVector();
	}

	const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwing2Search),true,Character);
	UWorld* World=GetWorld();

	FGS2AnchorCandidate Crosshair;
	FGS2AnchorCandidate Best;
	int32 NumMisses=0;

	auto TryRay=[&](const FVector& Start, const FVector& Dir, bool bCrosshair, bool bFanRay)
	{
		FHitResult Hit;
		const bool bHit=World->LineTraceSingleByChannel(Hit,Start,Start+Dir*MaxGrappleDistance,GrappleTraceChannel,QueryParams);
		FGS2AnchorCandidate Candidate;
		const bool bValid=bHit && EvaluateHit(Hit,bCrosshair,bFanRay,Ctx,Candidate);
		if (bDrawDebug)
		{
			DrawDebugLine(World,Start,bHit ? Hit.ImpactPoint : Start+Dir*MaxGrappleDistance,bValid ? FColor::Green : (bHit ? FColor::Red : FColor(128,128,128)),false,0.5f,0,1.f);
		}
		if (!bHit)
		{
			++NumMisses;
			return;
		}
		if (!bValid)return;
		if (bCrosshair)
		{
			Crosshair=Candidate;
		}
		if (Candidate.Score>Best.Score)
		{
			Best=Candidate;
		}
	};

	// (a) Crosshair, starting level with the character so things between the camera and the character don't count
	const FVector RayStart=Ctx.ViewLoc+Ctx.ViewDir*((Ctx.Pos-Ctx.ViewLoc)|Ctx.ViewDir);
	TryRay(RayStart,Ctx.ViewDir,true,false);

	// (b) Aim assist cone, pitched up so anchors above win
	FVector Right=(Ctx.ViewDir^Ctx.Up).GetSafeNormal();
	if (Right.IsNearlyZero())
	{
		Right=Character->GetActorRightVector();
	}
	const FVector ConeAxis=Ctx.ViewDir.RotateAngleAxis(AimAssistUpBiasDeg,Right).GetSafeNormal();
	FVector ConeRight=(ConeAxis^Ctx.Up).GetSafeNormal();
	if (ConeRight.IsNearlyZero())
	{
		ConeRight=Right;
	}
	const FVector ConeUp=(ConeRight^ConeAxis).GetSafeNormal();
	const int32 RaysPerRing=FMath::Max(AssistRaysPerRing,1);
	for (const float RingScale:{0.5f,1.f})
	{
		const float Alpha=FMath::DegreesToRadians(AimAssistConeDeg*RingScale);
		for (int32 i=0;i<RaysPerRing;++i)
		{
			const float Phi=2.f*UE_PI*i/RaysPerRing;
			const FVector Offset=ConeRight*FMath::Cos(Phi)+ConeUp*FMath::Sin(Phi);
			const FVector Dir=(ConeAxis*FMath::Cos(Alpha)+Offset*FMath::Sin(Alpha)).GetSafeNormal();
			TryRay(RayStart,Dir,false,false);
		}
	}

	// (c) Fan along the travel direction from the predicted attach point
	for (const float YawDeg:{-SwingFanYawDeg,0.f,SwingFanYawDeg})
	{
		const FVector YawDir=Ctx.MoveDirH.RotateAngleAxis(YawDeg,Ctx.Up);
		for (const float ElevationDeg:SwingFanElevationsDeg)
		{
			const float E=FMath::DegreesToRadians(ElevationDeg);
			const FVector Dir=(YawDir*FMath::Cos(E)+Ctx.Up*FMath::Sin(E)).GetSafeNormal();
			TryRay(Ctx.AttachPos,Dir,false,true);
		}
	}

	if (bDebugLogSearch)
	{
		GS2DebugMessage(FString::Printf(TEXT("GrappleSwing2 search: %s, %d rays hit nothing within %.0f"),
			Best.bValid ? *FString::Printf(TEXT("anchor at %s"),*Best.Anchor.ToString()) : TEXT("no valid anchor"),NumMisses,MaxGrappleDistance));
		bDebugLogSearch=false;
	}
	if (!Best.bValid)return false;
	OutBest=Crosshair.bValid && Crosshair.Score>=Best.Score-CrosshairStickiness ? Crosshair : Best;
	return true;
}

bool UGA_GrappleSwing2::EvaluateHit(const FHitResult& Hit, bool bCrosshair, bool bFanRay, const FGS2SearchCtx& Ctx, FGS2AnchorCandidate& Out) const
{
	// Only geometry the rope traces can see, so the swing agrees with the search
	const UPrimitiveComponent* HitComponent=Hit.GetComponent();
	auto Reject=[&](const FString& Why)
	{
		if (bDebugLogSearch)
		{
			GS2DebugMessage(FString::Printf(TEXT("GrappleSwing2 reject: %s | hit %s (%s, object type %s)"),*Why,*GetNameSafe(Hit.GetActor()),
				*GetNameSafe(HitComponent),HitComponent ? *UEnum::GetValueAsString(HitComponent->GetCollisionObjectType()) : TEXT("none")));
		}
		return false;
	};
	if (!HitComponent || !IsRopeObjectType(HitComponent->GetCollisionObjectType()))return Reject(TEXT("object type not in RopeObjectTypes"));
	if (Hit.GetActor() && Hit.GetActor()->IsA<APawn>())return Reject(TEXT("hit a pawn"));

	const FVector& Up=Ctx.Up;
	const FVector N=Hit.ImpactNormal.GetSafeNormal();
	const FVector A=Hit.ImpactPoint+N*AnchorSurfaceOffset;

	const float Dist=FVector::Dist(Ctx.AttachPos,A);
	if (Dist<Swing.MinRopeLength+100.f || Dist>MaxGrappleDistance)return Reject(FString::Printf(TEXT("distance %.0f outside [%.0f, %.0f]"),Dist,Swing.MinRopeLength+100.f,MaxGrappleDistance));

	const float Height=(A-Ctx.AttachPos)|Up;
	if (Height<MinAnchorHeight)return Reject(FString::Printf(TEXT("height %.0f above the attach point, below MinAnchorHeight %.0f"),Height,MinAnchorHeight));

	// Rope line of sight from where it leaves the capsule
	const FVector RopeStart=Ctx.Pos+Up*Ctx.HalfHeight*Swing.RopeAttachHeightFrac;
	const FVector RopeDir=(A-RopeStart).GetSafeNormal();
	FHitResult LOSHit;
	if (TraceStatic(RopeStart,A-RopeDir*Swing.AnchorLOSInset,LOSHit))return Reject(FString::Printf(TEXT("rope line of sight blocked by %s"),*GetNameSafe(LOSHit.GetActor())));

	// The server's check: the anchor sits on geometry the static traces can see
	if (N.IsNearlyZero())return Reject(TEXT("no surface normal"));
	FHitResult SurfaceHit;
	if (!TraceStatic(A,A-N*(AnchorSurfaceOffset+ServerLOSAnchorSlack),SurfaceHit))return Reject(TEXT("no simple collision under the anchor (the server would reject it)"));

	// The bottom of the arc has to fit above the floor under the anchor
	float FloorHeight=0.f;
	const bool bHasFloor=TraceFloor(A,FloorHeight);
	if (bHasFloor && (A|Up)-FloorHeight-Ctx.HalfHeight-Swing.GroundClearance<Swing.MinRopeLength)
	{
		return Reject(FString::Printf(TEXT("anchor %.0f above the floor under it, needs %.0f (MinRopeLength+HalfHeight+GroundClearance)"),
			(float)(A|Up)-FloorHeight,Swing.MinRopeLength+Ctx.HalfHeight+Swing.GroundClearance));
	}

	// Scores
	const FVector ToAnchorFromView=(A-Ctx.ViewLoc).GetSafeNormal();
	const float AimAngle=FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp((float)(ToAnchorFromView|Ctx.ViewDir),-1.f,1.f)));
	const float AimScore=bFanRay ? 0.f : GrappleSwing2::Sat(1.f-AimAngle/FMath::Max(AimAssistConeDeg,1.f));
	const float HeightScore=FMath::SmoothStep(MinAnchorHeight,FMath::Max(IdealAnchorHeight,MinAnchorHeight+1.f),Height)
		*(1.f-FMath::SmoothStep(MaxIdealAnchorHeight,1.6f*MaxIdealAnchorHeight,Height));
	const FVector ToAnchor=A-Ctx.AttachPos;
	const float AheadScore=GrappleSwing2::Sat(GrappleSwing2::Proj(ToAnchor,Up).GetSafeNormal()|Ctx.MoveDirH);
	const float ElevationDeg=FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp((float)(ToAnchor.GetSafeNormal()|Up),-1.f,1.f)));
	const float ElevationScore=GrappleSwing2::Sat(1.f-FMath::Abs(ElevationDeg-IdealElevationDeg)/45.f);
	const float LengthScore=GrappleSwing2::Sat(1.f-FMath::Abs(Dist-IdealRopeLength)/FMath::Max(IdealRopeLength,1.f));
	const float NormalUp=N|Up;
	const float UndersideScore=NormalUp<-0.3f ? 1.f : (NormalUp>0.7f ? -1.f : 0.5f);

	Out.Anchor=A;
	Out.Normal=N;
	Out.FloorHeight=FloorHeight;
	Out.bHasFloor=bHasFloor;
	Out.Score=ScoreWeightAim*AimScore+ScoreWeightHeight*HeightScore+ScoreWeightAhead*AheadScore
		+ScoreWeightElevation*ElevationScore+ScoreWeightLength*LengthScore+ScoreWeightUnderside*UndersideScore
		+(bCrosshair ? CrosshairBonus : 0.f);
	Out.bValid=true;
	return true;
}

void UGA_GrappleSwing2::TrySearchAndAttach()
{
	if (!IsActive() || State!=EGS2AbilityState::Searching)return;

	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (!Character || !MoveComp || !ASC)return;

	FGS2AnchorCandidate Candidate;
	if (!FindAnchor(Candidate))return;
	if (!CommitCheck(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo))
	{
		if (bDrawDebug)
		{
			GS2DebugMessage(TEXT("GrappleSwing2: anchor found but CommitCheck failed (cost or cooldown)"));
		}
		return;
	}

	GetWorld()->GetTimerManager().ClearTimer(SearchTimerHandle);

	const FVector Up=-MoveComp->GetGravityDirection();
	FGameplayAbilityTargetData_GrappleSwing2 Data;
	Data.SwingId=++NextSwingId;
	if (Data.SwingId==0)
	{
		Data.SwingId=++NextSwingId;
	}
	Data.Anchor=Candidate.Anchor;
	Data.AnchorNormal=Candidate.Normal;
	Data.StartLocation=Character->GetActorLocation();
	Data.PreferredSwingDir=GrappleSwing2::Proj(Data.Anchor-Data.StartLocation,Up).GetSafeNormal();
	if (Data.PreferredSwingDir.IsNearlyZero())
	{
		if (APlayerController* PC=Cast<APlayerController>(Character->GetController()))
		{
			FVector ViewLoc;
			FRotator ViewRot;
			PC->GetPlayerViewPoint(ViewLoc,ViewRot);
			Data.PreferredSwingDir=GrappleSwing2::Proj(ViewRot.Vector(),Up).GetSafeNormal();
		}
	}
	Data.TravelTime=FMath::Clamp((float)FVector::Dist(Data.Anchor,Data.StartLocation)/FMath::Max(HookSpeed,1.f),MinHookTravelTime,MaxHookTravelTime);
	Data.FloorHeight=Candidate.FloorHeight;
	Data.bHasFloor=Candidate.bHasFloor ? 1 : 0;
	Data.ChainCount=PendingChainCount;
	Data.ClientStartTime=-1.f;
	if (Character->GetLocalRole()==ROLE_AutonomousProxy)
	{
		if (const FNetworkPredictionData_Client_Character* ClientData=MoveComp->GetPredictionData_Client_Character())
		{
			Data.ClientStartTime=ClientData->CurrentTimeStamp;
		}
	}

	{
		// One dependent key for the data, the commit and the cue
		FScopedPredictionWindow ScopedPrediction(ASC,true);
		if (!HasAuthority(&CurrentActivationInfo))
		{
			ASC->CallServerSetReplicatedTargetData(CurrentSpecHandle,ActiveActivationKey,
				FGameplayAbilityTargetDataHandle(new FGameplayAbilityTargetData_GrappleSwing2(Data)),FGameplayTag(),ASC->ScopedPredictionKey);
		}
		if (!CommitAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo))
		{
			// The server rejects too; the ability stays until the button goes up
			State=EGS2AbilityState::Rejected;
			return;
		}
		StartSwing(Data,false);
	}
}

void UGA_GrappleSwing2::StartSwing(const FGameplayAbilityTargetData_GrappleSwing2& Data, bool bServerForRemote)
{
	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!Character || !MoveComp)return;
	if (!SharedTuning.IsValid())
	{
		SharedTuning=MakeShared<FGrappleSwing2Tuning>(Swing);
	}

	// Both machines build the source only from the target data and the tuning
	TSharedPtr<FRootMotionSource_GrappleSwing2> Src=MakeShared<FRootMotionSource_GrappleSwing2>();
	Src->Priority=(uint16)FMath::Clamp(RootMotionPriority,0,65535);
	Src->Tuning=SharedTuning;
	Src->SwingId=Data.SwingId;
	Src->Anchor=Data.Anchor;
	Src->PreferredSwingDir=Data.PreferredSwingDir;
	Src->TravelTime=Data.TravelTime;
	Src->FloorHeight=Data.FloorHeight;
	Src->bHasFloorBelowAnchor=Data.bHasFloor!=0;
	Src->ChainCount=Data.ChainCount;
	Src->Phase=EGS2Phase::Travel;
	Src->AccumulateMode=ERootMotionAccumulateMode::Additive;

	if (bServerForRemote)
	{
		// Start the server's source clock at the client's move time stamp, so both attach and release on the same move
		const FNetworkPredictionData_Server_Character* ServerData=MoveComp->GetPredictionData_Server_Character();
		if (ServerData && Data.ClientStartTime>=0.f)
		{
			const float ResetPeriod=MoveComp->MinTimeBetweenTimeStampResets;
			const float Now=ServerData->CurrentClientTimeStamp;
			float Start=Data.ClientStartTime;
			// A time stamp reset straddled the RPC
			if (Start-Now>ResetPeriod*0.5f)
			{
				Start-=ResetPeriod;
			}
			else if (Now-Start>ResetPeriod*0.5f)
			{
				Start+=ResetPeriod;
			}
			Start=FMath::Min(Start,Now+MaxStartLead);
			Src->StartTime=Start;
			if (Now>Start)
			{
				// Late data: align the clock with the client's, still within the (no-op) hook flight
				Src->SetTime(FMath::Min(Now-Start,Src->TravelTime));
			}
		}
	}
	else if (Data.ClientStartTime>=0.f)
	{
		Src->StartTime=Data.ClientStartTime;
	}

	RootMotionSourceID=MoveComp->ApplyRootMotionSource(Src);
	State=EGS2AbilityState::Hooked;
	bSourceSeen=false;
	SwingStartWorldTime=GetWorld()->GetTimeSeconds();
	ActiveChainCount=Data.ChainCount;
	ActiveAnchor=Data.Anchor;

	if (RopeCueTag.IsValid())
	{
		// Inside the caller's prediction window, so a predicted add on the owning client
		FGameplayCueParameters CueParams;
		CueParams.Location=Data.Anchor;
		CueParams.Normal=Data.AnchorNormal;
		CueParams.RawMagnitude=Data.TravelTime;
		CueParams.EffectCauser=Character;
		CueParams.Instigator=Character;
		K2_AddGameplayCueWithParams(RopeCueTag,CueParams,true);
		// The cue replicates with the ASC's owner (the PlayerState, which updates rarely by default), not the Character
		if (HasAuthority(&CurrentActivationInfo))
		{
			if (AActor* AscOwner=GetOwningActorFromActorInfo())
			{
				AscOwner->ForceNetUpdate();
			}
		}
	}
}

void UGA_GrappleSwing2::OnServerHookData(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag)
{
	// Copy first: consuming clears the cached handle this reference may point at
	const FGameplayAbilityTargetDataHandle LocalHandle=DataHandle;
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (!ASC)return;
	ASC->ConsumeClientReplicatedTargetData(CurrentSpecHandle,ActiveActivationKey);

	if (!IsActive() || State!=EGS2AbilityState::Searching)return;

	const FGameplayAbilityTargetData* RawData=LocalHandle.Get(0);
	if (!RawData || RawData->GetScriptStruct()!=FGameplayAbilityTargetData_GrappleSwing2::StaticStruct())
	{
		ServerReject();
		return;
	}
	FGameplayAbilityTargetData_GrappleSwing2 Data=*static_cast<const FGameplayAbilityTargetData_GrappleSwing2*>(RawData);

	// Runs inside the client's prediction window, so the commit shares its key
	if (!ServerValidate(Data) || !CommitAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo))
	{
		ServerReject();
		return;
	}

	Data.TravelTime=FMath::Clamp(Data.TravelTime,MinHookTravelTime,MaxHookTravelTime);
	Data.ChainCount=(uint8)FMath::Clamp<int32>(Data.ChainCount,0,Swing.MaxChainStacks);
	LastAcceptedSwingId=Data.SwingId;
	StartSwing(Data,true);
}

bool UGA_GrappleSwing2::ServerValidate(const FGameplayAbilityTargetData_GrappleSwing2& Data) const
{
	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!Character || !MoveComp)return false;
	if (Data.SwingId==LastAcceptedSwingId)return false;
	if (Data.Anchor.ContainsNaN() || Data.StartLocation.ContainsNaN() || Data.AnchorNormal.ContainsNaN() || Data.PreferredSwingDir.ContainsNaN())return false;

	const FVector Up=-MoveComp->GetGravityDirection();
	const float HalfHeight=Character->GetCapsuleComponent() ? Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;

	// Start location near where the server has the character
	const float StartTolerance=ServerStartTolBase+MoveComp->Velocity.Size()*ServerStartTolSpeedTime;
	if (FVector::Dist(Data.StartLocation,Character->GetActorLocation())>StartTolerance)return false;

	// Range and height. The client measured from where it predicted the character would be when the hook arrives,
	// so allow for the distance covered during the longest hook flight.
	const float G=-MoveComp->GetGravityZ();
	const float FlightSlack=(float)MoveComp->Velocity.Size()*MaxHookTravelTime+0.5f*FMath::Abs(G)*MaxHookTravelTime*MaxHookTravelTime;
	if (FVector::Dist(Data.Anchor,Data.StartLocation)>MaxGrappleDistance+ServerRangeTolerance+FlightSlack)return false;
	if (((Data.Anchor-Data.StartLocation)|Up)<MinAnchorHeight-100.f-FlightSlack)return false;

	// Rope line of sight
	const FVector RopeStart=Data.StartLocation+Up*HalfHeight*Swing.RopeAttachHeightFrac;
	const FVector RopeDir=(Data.Anchor-RopeStart).GetSafeNormal();
	FHitResult Hit;
	if (TraceStatic(RopeStart,Data.Anchor-RopeDir*Swing.AnchorLOSInset,Hit))return false;

	// The anchor sits on real geometry
	const FVector Normal=Data.AnchorNormal.GetSafeNormal();
	if (Normal.IsNearlyZero())return false;
	if (!TraceStatic(Data.Anchor,Data.Anchor-Normal*(AnchorSurfaceOffset+ServerLOSAnchorSlack),Hit))return false;

	// The floor under the anchor agrees, the ground rope limit depends on it
	float ServerFloorHeight=0.f;
	const bool bServerHasFloor=TraceFloor(Data.Anchor,ServerFloorHeight);
	if (bServerHasFloor!=(Data.bHasFloor!=0))return false;
	if (bServerHasFloor && FMath::Abs(ServerFloorHeight-Data.FloorHeight)>ServerFloorTolerance)return false;

	return true;
}

void UGA_GrappleSwing2::ServerReject()
{
	// Keep the ability active with no swing: ending it from here would make the held button re-fire every frame
	State=EGS2AbilityState::Rejected;
	if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
	{
		ASC->ClientSetReplicatedEvent(EAbilityGenericReplicatedEvent::GenericSignalFromServer,CurrentSpecHandle,ActiveActivationKey);
	}
}

void UGA_GrappleSwing2::OnServerRejected()
{
	if (!IsActive())return;
	// A tap: InputReleased already ran for this activation. Any other release while active ends the ability or moves it
	// to Releasing, so the state alone says the button went up (not every controller sets the spec's InputPressed).
	const bool bButtonUp=State==EGS2AbilityState::Releasing;
	if (UCharacterMovementComponent* MoveComp=GetSwingMovement())
	{
		if (RootMotionSourceID!=GrappleSwing2::InvalidSourceID)
		{
			// The only place a source is removed instead of finishing on its own
			MoveComp->RemoveRootMotionSourceByID(RootMotionSourceID);
		}
	}
	RootMotionSourceID=GrappleSwing2::InvalidSourceID;
	RemoveCuePredicted();
	// Stays active until the button goes up; the predicted cooldown rolls back with its key
	State=EGS2AbilityState::Rejected;
	if (bButtonUp)
	{
		// No InputReleased will come to end it
		EndLocal();
	}
}

void UGA_GrappleSwing2::OnServerReleasePayload()
{
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (!ASC)return;
	const FVector Payload=ASC->GetReplicatedDataOfGenericReplicatedEvent(EAbilityGenericReplicatedEvent::GameCustom1,CurrentSpecHandle,ActiveActivationKey).VectorPayload;
	ASC->ConsumeGenericReplicatedEvent(EAbilityGenericReplicatedEvent::GameCustom1,CurrentSpecHandle,ActiveActivationKey);

	TSharedPtr<FRootMotionSource> Holder;
	FRootMotionSource_GrappleSwing2* Src=FindSource(Holder);
	if (!Src || Src->SwingId!=(uint16)FMath::RoundToInt(Payload.Y))return;

	const float ClientEndTime=Payload.X/1000.f;
	float EndTime=FMath::Clamp(ClientEndTime,Src->GetTime(),Src->GetTime()+MaxReleaseLead);
	if (Src->Phase==EGS2Phase::Travel && ClientEndTime<Src->TravelTime-1.e-4f)
	{
		// The client dropped the hook before it arrived. Late hook data can start this clock at TravelTime, where the
		// clamp would turn the drop into an attach and an immediate finish.
		EndTime=FMath::Min(EndTime,Src->TravelTime-2.e-4f);
	}
	const EGS2EndKind Kind=FMath::RoundToInt(Payload.Z)==(int32)EGS2EndKind::Forced ? EGS2EndKind::Forced : EGS2EndKind::Release;
	// Earliest valid request wins
	if (Src->EndTime>=0.f && Src->EndTime<=EndTime)return;
	Src->EndTime=EndTime;
	Src->EndKind=Kind;
}

void UGA_GrappleSwing2::RequestEnd(FRootMotionSource_GrappleSwing2& Src, float EndTime, EGS2EndKind Kind)
{
	if (Src.EndTime>=0.f && Src.EndTime<=EndTime)return;
	Src.EndTime=EndTime;
	Src.EndKind=Kind;

	if (IsLocallyControlled() && !HasAuthority(&CurrentActivationInfo))
	{
		// Reliable on the ASC channel and sent before the next ServerMove, so the server ends on the same move.
		// Time in ms for precision in the quantized payload.
		if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
		{
			ASC->ServerSetReplicatedEventWithPayload(EAbilityGenericReplicatedEvent::GameCustom1,CurrentSpecHandle,ActiveActivationKey,
				ASC->ScopedPredictionKey,FVector_NetQuantize100(EndTime*1000.f,(float)Src.SwingId,(float)(uint8)Kind));
		}
	}
}

void UGA_GrappleSwing2::InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo)
{
	Super::InputReleased(Handle,ActorInfo,ActivationInfo);
	// Called on the local machine only (AbilitySpecInputReleased)
	if (!IsActive())return;

	switch (State)
	{
	case EGS2AbilityState::Hooked:
		{
			TSharedPtr<FRootMotionSource> Holder;
			FRootMotionSource_GrappleSwing2* Src=FindSource(Holder);
			if (!Src)
			{
				EndLocal();
				break;
			}
			// A tap still gives a short swing
			const float MinEnd=(Src->Phase==EGS2Phase::Travel ? Src->TravelTime : Src->AttachTime)+Swing.MinSwingTimeAfterAttach;
			RequestEnd(*Src,FMath::Max(Src->GetTime(),MinEnd),EGS2EndKind::Release);
			// Keep the ability (and the rope cue) until the source finishes
			State=EGS2AbilityState::Releasing;
			break;
		}
	case EGS2AbilityState::Releasing:
		break;
	default:
		EndLocal();
		break;
	}
}

void UGA_GrappleSwing2::EndLocal()
{
	bIntentionalEnd=true;
	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,true,false);
}

void UGA_GrappleSwing2::RemoveCuePredicted()
{
	if (!RopeCueTag.IsValid())return;
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	if (IsLocallyControlled() && ASC && !HasAuthority(&CurrentActivationInfo))
	{
		FScopedPredictionWindow ScopedPrediction(ASC,true);
		K2_RemoveGameplayCue(RopeCueTag);
	}
	else
	{
		K2_RemoveGameplayCue(RopeCueTag);
	}
}

void UGA_GrappleSwing2::Poll()
{
	if (!IsActive())return;

	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!Character || !MoveComp)
	{
		EndLocal();
		return;
	}

	const UWorld* World=GetWorld();
	const double Now=World->GetTimeSeconds();
	const bool bLocal=IsLocallyControlled();
	const bool bAuthority=HasAuthority(&CurrentActivationInfo);

	TSharedPtr<FRootMotionSource> Holder;
	FRootMotionSource_GrappleSwing2* Src=FindSource(Holder);
	if (Src)
	{
		bSourceSeen=true;
		LastSeenEndReason=Src->EndReason;
	}

	if (bAuthority && !bLocal && Src && Src->Phase==EGS2Phase::Swing && !bServerSawAttach)
	{
		bServerSawAttach=true;
		Character->ForceNetUpdate();
	}

	const bool bSwinging=State==EGS2AbilityState::Hooked || State==EGS2AbilityState::Releasing;
	// A source that never showed up (still pending, or lost) only counts as gone after a grace period
	const bool bMissing=!Src && (bSourceSeen || Now-SwingStartWorldTime>GrappleSwing2::SourceAppearTimeout);
	const bool bOver=bSwinging && (bMissing || (Src && (Src->Phase==EGS2Phase::Done || Src->Status.HasFlag(ERootMotionSourceStatusFlags::Finished))));

	if (bOver)
	{
		// Vanished unseen: infer the reason
		const EGS2EndReason Reason=Src ? Src->EndReason
			: (LastSeenEndReason!=EGS2EndReason::None ? LastSeenEndReason : (MoveComp->IsMovingOnGround() ? EGS2EndReason::Landed : EGS2EndReason::Snapped));
		RootMotionSourceID=GrappleSwing2::InvalidSourceID;
		Holder.Reset();
		Src=nullptr;
		if (bAuthority)
		{
			Character->ForceNetUpdate();
			// The rope cue is removed below or in EndAbility this frame, and replicates with the ASC's owner
			if (AActor* AscOwner=GetOwningActorFromActorInfo())
			{
				AscOwner->ForceNetUpdate();
			}
		}

		if (!bLocal)
		{
			// Server for a remote client: wait for the client's end
			K2_RemoveGameplayCue(RopeCueTag);
			State=EGS2AbilityState::Spent;
		}
		else
		{
			LastDetachWorldTime=Now;
			LastDetachReason=Reason;
			bLastDetachWasRelease=Reason==EGS2EndReason::Released || Reason==EGS2EndReason::AutoReleased || Reason==EGS2EndReason::JumpReleased;
			LastChainCount=bLastDetachWasRelease ? ActiveChainCount : 0;

			switch (Reason)
			{
			case EGS2EndReason::Landed:
			case EGS2EndReason::JumpReleased:
			case EGS2EndReason::Timeout:
				if (State==EGS2AbilityState::Releasing)
				{
					// The button is already up, and InputReleased won't run again for this activation
					EndLocal();
					return;
				}
				// No re-fire until the button goes up (or the character walks off a ledge after landing)
				RemoveCuePredicted();
				State=EGS2AbilityState::Spent;
				AirborneTime=0.f;
				break;
			default:
				// Released/Forced: the button is already up. AutoReleased/Snapped/TooClose: the held button re-fires
				// next frame, and that's intended (hold to cruise)
				EndLocal();
				return;
			}
		}
	}

	if (bLocal && State==EGS2AbilityState::Spent && LastDetachReason==EGS2EndReason::Landed && bRefireWhenAirborne)
	{
		AirborneTime=MoveComp->IsMovingOnGround() ? 0.f : AirborneTime+World->GetDeltaSeconds();
		const FGameplayAbilitySpec* Spec=GetCurrentAbilitySpec();
		if (AirborneTime>=RefireAirborneDelay && Spec && Spec->InputPressed)
		{
			// Walked off a ledge while holding
			EndLocal();
			return;
		}
	}

	if (bDrawDebug && bLocal)
	{
		FVector DebugAnchor;
		float DebugRope;
		bool bDebugTaut;
		if (GetGrappleSwing2State(Character,DebugAnchor,DebugRope,bDebugTaut))
		{
			const FVector Loc=Character->GetActorLocation();
			DrawDebugLine(World,Loc,DebugAnchor,bDebugTaut ? FColor::White : FColor::Yellow,false,-1.f,0,2.f);
			DrawDebugSphere(World,DebugAnchor,15.f,8,FColor::Red,false,-1.f);
			DrawDebugString(World,Loc+FVector(0.f,0.f,120.f),FString::Printf(TEXT("Rope %.0f  Speed %.0f"),DebugRope,MoveComp->Velocity.Size()),nullptr,FColor::White,0.f);
		}
	}

	if (IsActive())
	{
		PollTimerHandle=GetWorld()->GetTimerManager().SetTimerForNextTick(this,&ThisClass::Poll);
	}
}

void UGA_GrappleSwing2::GatePoll()
{
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	const FGameplayAbilitySpec* Spec=ASC ? ASC->FindAbilitySpecFromHandle(GateSpecHandle) : nullptr;
	if (!Spec || !Spec->InputPressed)
	{
		bBlockUntilRelease=false;
		GetWorld()->GetTimerManager().ClearTimer(GateTimerHandle);
	}
}

void UGA_GrappleSwing2::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (!IsActive())return;

	// Graceful finish on the next move. The release payload goes out before ServerEndAbility/ServerCancelAbility.
	// Never remove the source here: client and server would remove it on different moves.
	{
		TSharedPtr<FRootMotionSource> Holder;
		FRootMotionSource_GrappleSwing2* Src=FindSource(Holder);
		if (Src && Src->Phase!=EGS2Phase::Done && !Src->Status.HasFlag(ERootMotionSourceStatusFlags::Finished))
		{
			// During the hook flight, end before the attach move (late hook data can start the clock at TravelTime)
			const float EndTime=Src->Phase==EGS2Phase::Travel ? FMath::Min(Src->GetTime(),Src->TravelTime-2.e-4f) : Src->GetTime();
			RequestEnd(*Src,EndTime,bWasCancelled ? EGS2EndKind::Forced : EGS2EndKind::Release);
		}
	}

	if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
	{
		if (TargetDataDelegateHandle.IsValid())
		{
			ASC->AbilityTargetDataSetDelegate(Handle,ActiveActivationKey).Remove(TargetDataDelegateHandle);
			TargetDataDelegateHandle.Reset();
		}
		if (ReleasePayloadDelegateHandle.IsValid())
		{
			ASC->AbilityReplicatedEventDelegate(EAbilityGenericReplicatedEvent::GameCustom1,Handle,ActiveActivationKey).Remove(ReleasePayloadDelegateHandle);
			ReleasePayloadDelegateHandle.Reset();
		}
		if (ServerRejectedDelegateHandle.IsValid())
		{
			ASC->AbilityReplicatedEventDelegate(EAbilityGenericReplicatedEvent::GenericSignalFromServer,Handle,ActiveActivationKey).Remove(ServerRejectedDelegateHandle);
			ServerRejectedDelegateHandle.Reset();
		}
	}

	// Gate only external ends (server cancel, failed activation, cancel by tag, death) while the button is held.
	// Never read InputPressed on the server: it is set at activation and never cleared there.
	const bool bLocal=IsLocallyControlled();
	const FGameplayAbilitySpec* Spec=GetCurrentAbilitySpec();
	const bool bGate=bLocal && !bIntentionalEnd && Spec && Spec->InputPressed;
	GateSpecHandle=Handle;

	if (bLocal && !HasAuthority(&ActivationInfo) && RopeCueTag.IsValid())
	{
		// The tracked-cue cleanup in Super does nothing on a client without a prediction key
		if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
		{
			FScopedPredictionWindow ScopedPrediction(ASC,true);
			K2_RemoveGameplayCue(RopeCueTag);
		}
	}

	if (RopeCueTag.IsValid() && HasAuthority(&ActivationInfo))
	{
		// Super removes the rope cue, which replicates with the ASC's owner. A remote client's end usually arrives with
		// the finishing move, before Poll can flush the removal.
		if (AActor* AscOwner=ActorInfo ? ActorInfo->OwnerActor.Get() : nullptr)
		{
			AscOwner->ForceNetUpdate();
		}
	}

	State=EGS2AbilityState::Idle;
	RootMotionSourceID=GrappleSwing2::InvalidSourceID;
	bServerSawAttach=false;
	bSourceSeen=false;

	// Clears every timer this object owns, so the gate is armed after it
	Super::EndAbility(Handle,ActorInfo,ActivationInfo,bReplicateEndAbility,bWasCancelled);

	if (bGate)
	{
		bBlockUntilRelease=true;
		GetWorld()->GetTimerManager().SetTimer(GateTimerHandle,this,&ThisClass::GatePoll,FMath::Max(GatePollInterval,0.01f),true);
	}
	bIntentionalEnd=false;
}
