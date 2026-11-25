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
#include "Airship/AirshipPawn.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"

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

	// A hook closer to straight below than this still takes this much arc to reach the bottom from -1
	const float MinHookArcAngleDeg=10.f;

	// Horizontal direction the arc angle is measured along: the motion, or the hook direction when barely moving sideways
	static FVector ArcForward(const FVector& V, const FVector& HookDir, const FVector& Up)
	{
		const FVector Hook=Proj(HookDir,Up).GetSafeNormal();
		const FVector Forward=(Proj(V,Up)+Hook*50.f).GetSafeNormal();
		return Forward.IsNearlyZero() ? Hook : Forward;
	}

	// Signed angle from straight below the anchor in the vertical plane along Forward: negative while heading toward the
	// bottom, positive once past it. Passes 0 smoothly even when steering moves the arc off the anchor's vertical
	static float ArcAngleDeg(const FVector& R, const FVector& Forward, const FVector& Up)
	{
		return FMath::RadiansToDegrees(FMath::Atan2((float)(R|Forward),(float)-(R|Up)));
	}

	// Angle from straight down where the auto release is expected to let go: the arc end angle, or earlier where the
	// tangential speed falls to the stall speed climbing at the rising gravity. Converges on the real one as it nears
	static float PredictReleaseAngleDeg(const FGrappleSwing2Tuning& P, float PeakTangentSpeed, const FVector& R, const FVector& V, const FVector& Up, float G)
	{
		const float MaxDeg=FMath::Clamp(P.AutoReleaseAngleDeg,1.f,179.f);
		const float D=R.Size();
		if (!P.bAutoReleaseAtArcEnd || D<1.f)return MaxDeg;
		const FVector N=R/D;
		const float CosNow=FMath::Clamp(-(float)(N|Up),-1.f,1.f);
		const float Vt=Proj(V,N).Size();
		const float VStall=FMath::Max(P.AutoReleaseStallSpeed,P.AutoReleasePeakFraction*PeakTangentSpeed);
		if (Vt<=VStall)return FMath::Min(FMath::RadiansToDegrees(FMath::Acos(CosNow)),MaxDeg);
		// Vt^2-VStall^2 = 2*g*D*(cos now - cos release)
		const float CosStall=CosNow-(Vt*Vt-VStall*VStall)/(2.f*FMath::Max(G*P.GravityScaleAscending,1.f)*D);
		if (CosStall<=FMath::Cos(FMath::DegreesToRadians(MaxDeg)))return MaxDeg;
		return FMath::RadiansToDegrees(FMath::Acos(CosStall));
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

	// A client move time stamp brought next to the server's, across a time stamp reset that straddled the RPC
	static float AlignClientTime(float ClientTime, float Now, float ResetPeriod)
	{
		if (ClientTime-Now>ResetPeriod*0.5f)
		{
			return ClientTime-ResetPeriod;
		}
		if (Now-ClientTime>ResetPeriod*0.5f)
		{
			return ClientTime+ResetPeriod;
		}
		return ClientTime;
	}

	// CMC adds this to an override velocity while falling, take it out so the displacement is exactly ours
	static FVector DecayingBaseVelocity(const UCharacterMovementComponent& MoveComponent)
	{
		return MoveComponent.IsFalling() ? MoveComponent.DecayingFormerBaseVelocity : FVector::ZeroVector;
	}

	// Ship hook: the airship a hit belongs to, the hull itself or anything attached to it (the turrets)
	static AAirshipPawn* ResolveShip(AActor* Actor)
	{
		for (int32 Depth=0;Actor && Depth<=4;++Depth,Actor=Actor->GetAttachParentActor())
		{
			if (AAirshipPawn* Ship=Cast<AAirshipPawn>(Actor))return Ship;
		}
		return nullptr;
	}

	static FVector ShipLinearVelocity(const AAirshipPawn& Ship)
	{
		const UPrimitiveComponent* HullComp=Ship.GetHull();
		return HullComp && HullComp->IsSimulatingPhysics() ? HullComp->GetPhysicsLinearVelocity() : Ship.GetVelocity();
	}

	// Linear plus angular x r at a world point
	static FVector ShipVelocityAt(const AAirshipPawn& Ship, const FVector& Point)
	{
		const UPrimitiveComponent* HullComp=Ship.GetHull();
		return HullComp && HullComp->IsSimulatingPhysics() ? HullComp->GetPhysicsLinearVelocityAtPoint(Point) : Ship.GetVelocity();
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
	Ar << AgainstMotionDir;
	Ar << bShipReel;
	if (bShipReel)
	{
		Ar << AnchorActor;
		Ar << TargetHullLocal;
		Ar << AnchorVelocity;
	}
	else if (Ar.IsLoading())
	{
		AnchorActor.Reset();
		TargetHullLocal=FVector::ZeroVector;
		AnchorVelocity=FVector::ZeroVector;
	}
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
	AttachArcAngle=Other->AttachArcAngle;
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
	bool bAttachMove=false;
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
		bAttachMove=true;
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
	if (bAttachMove)
	{
		// Measured where the move ends, which is what the first read after the catch sees, so that read is -1
		AttachArcAngle=GrappleSwing2::ArcAngleDeg(X-Anchor,GrappleSwing2::ArcForward(V,PreferredSwingDir,Ctx.Up),Ctx.Up);
	}
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

	// Keep the tangential speed and a fraction of the radial kinetic energy, redirected along the arc
	auto ArcStart=[&](const FVector& Vel, FVector& OutDir)->float
	{
		const float VelR=Vel|N;
		const FVector VelT=Vel-N*VelR;
		const float K=VelR>0.f ? P.AttachOutwardRetention : P.AttachInwardRetention;
		FVector Aim=GrappleSwing2::Proj(PreferredSwingDir,N).GetSafeNormal();
		if (Aim.IsNearlyZero())
		{
			Aim=GrappleSwing2::Proj(-Up,N).GetSafeNormal();
		}
		const float VtSize=VelT.Size();
		const FVector MDir=VtSize>50.f ? VelT/VtSize : Aim;
		OutDir=(MDir*(1.f-P.AttachAimBias)+Aim*P.AttachAimBias).GetSafeNormal();
		if (OutDir.IsNearlyZero())
		{
			OutDir=MDir;
		}
		return FMath::Sqrt(VelT.SizeSquared()+K*VelR*VelR);
	};

	// Shot while looking against the motion: the web stops the speed heading away from the view (a slow drift only partly)
	FVector In=InVelocity;
	const float Away=-(float)(InVelocity|AgainstMotionDir);
	FVector OldDir=FVector::ZeroVector;
	float OldSpeed=0.f;
	if (Away>0.f)
	{
		In+=AgainstMotionDir*(Away*FMath::Min(Away/FMath::Max(P.AgainstMotionFullStopSpeed,1.f),1.f));
		OldSpeed=ArcStart(InVelocity,OldDir);
	}

	const float Vr=In|N;
	FVector V;
	if (Vr<-P.AttachSlackInwardSpeed && (In|Up)>0.f)
	{
		// Flying up at the anchor: the rope starts slack and catches later
		V=In;
		bTaut=false;
	}
	else
	{
		FVector Dir;
		float Speed;
		if (Away>0.f)
		{
			// A share of the speed away from the view turns along it. A start that already went this way keeps its speed
			Speed=ArcStart(InVelocity+AgainstMotionDir*(Away*(1.f+P.AgainstMotionSpeedScale)),Dir);
			Speed=FMath::Lerp(Speed,FMath::Max(Speed,OldSpeed),FMath::Clamp((float)(Dir|OldDir),0.f,1.f));
		}
		else
		{
			Speed=ArcStart(In,Dir);
		}
		if (Away>10.f && (In|Up)>0.f && Vr<0.f && (Dir|AgainstMotionDir)<-0.2f)
		{
			// Rising at the anchor with the arc still starting clearly away from the view: start slack, the rope catches on the way
			V=In;
			bTaut=false;
		}
		else
		{
			V=Dir*FMath::Max(Speed,P.AttachMinSwingSpeed);
			bTaut=true;
		}
	}
	if (Away>0.f)
	{
		// Never faster than the start without the turn
		const bool bOldSlack=(float)(InVelocity|N)<-P.AttachSlackInwardSpeed && (InVelocity|Up)>0.f;
		V=V.GetClampedToMaxSize(bOldSlack ? (float)InVelocity.Size() : FMath::Max(OldSpeed,P.AttachMinSwingSpeed));
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
	Ar << AttachArcAngle;
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
// FRootMotionSource_GrappleReel2 (ship hook, SPEC_B B7.3)
// ---------------------------------------------------------------------------------------------------------------------

FRootMotionSource_GrappleReel2::FRootMotionSource_GrappleReel2()
{
	// Additive with zero output while the hook flies, switched to Override when it arrives, like the swing
	AccumulateMode=ERootMotionAccumulateMode::Additive;
	Priority=500;
	InstanceName=FName("GrappleReel2");
	// Infinite, the source finishes itself
	Duration=-1.f;
	Settings.SetFlag(ERootMotionSourceSettingsFlags::UseSensitiveLiftoffCheck);
	// The final move outputs the leave velocity itself (Clamp/Set finish velocities aren't applied in replays)
	FinishVelocityParams.Mode=ERootMotionFinishVelocityMode::MaintainLastRootMotionVelocity;
}

FRootMotionSource* FRootMotionSource_GrappleReel2::Clone() const
{
	return new FRootMotionSource_GrappleReel2(*this);
}

bool FRootMotionSource_GrappleReel2::Matches(const FRootMotionSource* Other) const
{
	// Not the base version: it compares AccumulateMode, which this source changes when the hook arrives
	if (!Other || Other->GetScriptStruct()!=GetScriptStruct())return false;
	const FRootMotionSource_GrappleReel2* OtherCast=static_cast<const FRootMotionSource_GrappleReel2*>(Other);
	return Priority==Other->Priority
		&& bInLocalSpace==Other->bInLocalSpace
		&& InstanceName==Other->InstanceName
		&& FMath::IsNearlyEqual(Duration,Other->Duration,UE_SMALL_NUMBER)
		&& SwingId==OtherCast->SwingId
		&& AnchorStart.Equals(OtherCast->AnchorStart,1.f);
}

bool FRootMotionSource_GrappleReel2::MatchesAndHasSameState(const FRootMotionSource* Other) const
{
	// As the swing: a correction during a reel always replays from the server's state
	return false;
}

bool FRootMotionSource_GrappleReel2::UpdateStateFrom(const FRootMotionSource* SourceToTakeStateFrom, bool bMarkForSimulatedCatchup)
{
	if (!FRootMotionSource::UpdateStateFrom(SourceToTakeStateFrom,bMarkForSimulatedCatchup))return false;

	const FRootMotionSource_GrappleReel2* Other=static_cast<const FRootMotionSource_GrappleReel2*>(SourceToTakeStateFrom);
	Phase=Other->Phase;
	AccumulateMode=Phase==EGS2Phase::Travel ? ERootMotionAccumulateMode::Additive : ERootMotionAccumulateMode::Override;
	if (Phase==EGS2Phase::Travel)
	{
		// A Travel source outputs nothing (see the swing's UpdateStateFrom)
		RootMotionParams.Clear();
	}
	bPrevJump=Other->bPrevJump;
	EndReason=Other->EndReason;
	AttachTime=Other->AttachTime;
	ReelVelocity=Other->ReelVelocity;
	// Earliest valid end wins, so a replay never undoes one
	if (Other->EndTime>=0.f && (EndTime<0.f || Other->EndTime<EndTime))
	{
		EndTime=Other->EndTime;
		EndKind=Other->EndKind;
	}
	// Config, tuning and this machine's view of the ship stay as they are
	return true;
}

FVector FRootMotionSource_GrappleReel2::VelocityAt(const FVector& X, float Time, const FVector& Up) const
{
	const FVector A=GetAnchorAt(Time);
	const float D=FVector::Dist(A,X);
	// Close enough: ride along with the ship for the rest of the move, the next move ends the reel
	if (D<=ArriveDistance)return AnchorVelocity;
	const FVector Aim=A+Up*FMath::Min(LiftMax,LiftFraction*D);
	return AnchorVelocity+(Aim-X).GetSafeNormal()*ReelSpeed;
}

bool FRootMotionSource_GrappleReel2::IsOnShip(const ACharacter& Character, const UCharacterMovementComponent& MoveComponent, const FVector& X, float HalfHeight) const
{
	UPrimitiveComponent* HullComp=Hull.Get();
	if (!HullComp)return false;

	// Landed on the ship (the hull, or anything attached to it), the way AAirshipPawn's rider test reads the base
	if (MoveComponent.IsMovingOnGround() && Character.GetMovementBaseObject())
	{
		const AActor* ShipActor=HullComp->GetOwner();
		const AActor* BaseActor=APawn::GetMovementBaseActor(&Character);
		if (ShipActor && BaseActor && (BaseActor==ShipActor || BaseActor->IsAttachedTo(ShipActor)))return true;
	}

	// Over the deck near the target's height, with the hull right below: an arrival that drifted a little still lands.
	// This machine's view of the ship, so client and server may end a move apart (the CMC corrects the last metres)
	if (!DeckBoxLocal.IsValid)return false;
	const FTransform HullTM=HullComp->GetComponentTransform();
	if (!DeckBoxLocal.IsInsideOrOn(HullTM.InverseTransformPosition(X)))return false;
	FHitResult Hit;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(GrappleReel2Deck),false);
	return HullComp->LineTraceComponent(Hit,X,X-HullTM.GetUnitAxis(EAxis::Z)*(HalfHeight+DeckDropTolerance),Params);
}

void FRootMotionSource_GrappleReel2::Finish(const FVector& VOut, EGS2EndReason Reason, const UCharacterMovementComponent& MoveComponent, float T1, bool bJump)
{
	// The final move: its override is still applied this move, then the source is removed with Maintain
	Phase=EGS2Phase::Done;
	EndReason=Reason;
	AccumulateMode=ERootMotionAccumulateMode::Override;
	RootMotionParams.Set(FTransform(VOut-GrappleSwing2::DecayingBaseVelocity(MoveComponent)));
	ReelVelocity=VOut;
	bPrevJump=bJump;
	// Duration<0, so the time-out check never clears this
	Status.SetFlag(ERootMotionSourceStatusFlags::Finished);
	SetTime(T1);
}

void FRootMotionSource_GrappleReel2::PrepareRootMotion(float SimulationTime, float MovementTickTime, const ACharacter& Character, const UCharacterMovementComponent& MoveComponent)
{
	RootMotionParams.Clear();
	const float T0=GetTime();
	const float T1=T0+SimulationTime;
	const float Dt=MovementTickTime;

	if (!Tuning.IsValid() || Dt<=UE_SMALL_NUMBER)
	{
		if (Phase!=EGS2Phase::Travel)
		{
			RootMotionParams.Set(FTransform(ReelVelocity));
		}
		SetTime(T1);
		return;
	}

	const FGrappleSwing2Tuning& P=*Tuning;
	const FVector X0=MoveComponent.UpdatedComponent->GetComponentLocation();
	const FVector Up=-MoveComponent.GetGravityDirection();
	const float HalfHeight=Character.GetCapsuleComponent() ? Character.GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
	const bool bJump=GrappleSwing2::ReadMoveJump(Character,MoveComponent);

	// (1) Travel: the hook is in flight, zero additive so normal falling runs
	if (Phase==EGS2Phase::Travel)
	{
		// Ended before the hook arrived (cancel, death): drop the hook and leave the velocity alone
		if (EndTime>=0.f && EndTime<TravelTime-1.e-4f && T0>=EndTime-1.e-4f)
		{
			EndReason=EGS2EndReason::Forced;
			AccumulateMode=ERootMotionAccumulateMode::Additive;
			bPrevJump=bJump;
			Status.SetFlag(ERootMotionSourceStatusFlags::Finished);
			SetTime(T1);
			return;
		}
		if (SimulationTime<=0.f || T1<TravelTime-1.e-4f)
		{
			AccumulateMode=ERootMotionAccumulateMode::Additive;
			bPrevJump=bJump;
			SetTime(T1);
			return;
		}
		Phase=EGS2Phase::Swing;
		AccumulateMode=ERootMotionAccumulateMode::Override;
		AttachTime=T1;
		EndReason=EGS2EndReason::None;
		// A jump held through the hook flight doesn't let go at once
		bPrevJump=bJump;
	}
	else if (Phase==EGS2Phase::Done)
	{
		RootMotionParams.Set(FTransform(ReelVelocity));
		SetTime(T1);
		return;
	}

	// (2) Ends, once per move before moving
	const FVector VNow=VelocityAt(X0,T0,Up);
	const float Elapsed=FMath::Max(T0-AttachTime,0.f);
	// a) Ability end (the button alone never ends a reel): keep the reel velocity
	if (EndTime>=0.f && T0>=EndTime-1.e-4f)
	{
		Finish(VNow,EndKind==EGS2EndKind::Forced ? EGS2EndReason::Forced : EGS2EndReason::Released,MoveComponent,T1,bJump);
		return;
	}
	// b) Jump lets go, as on the swing
	if (P.bJumpReleases && bJump && !bPrevJump && Elapsed>=P.MinSwingTimeAfterAttach)
	{
		Finish(VNow,EGS2EndReason::JumpReleased,MoveComponent,T1,bJump);
		return;
	}
	bPrevJump=bJump;
	// c) At the deck target, on the ship, or over its deck: leave with the ship's velocity and a hop, landing on the lid
	const FVector Leave=AnchorVelocity+Up*LeaveUpSpeed;
	if (FVector::Dist(GetAnchorAt(T0),X0)<=ArriveDistance || IsOnShip(Character,MoveComponent,X0,HalfHeight))
	{
		Finish(Leave,EGS2EndReason::Arrived,MoveComponent,T1,bJump);
		return;
	}
	// d) Time limit, the same way out wherever it is
	if (Elapsed>=MaxReelTime)
	{
		Finish(Leave,EGS2EndReason::Timeout,MoveComponent,T1,bJump);
		return;
	}

	// (3) Substeps: the direction to the moving aim point turns as the player closes in
	const int32 NumSteps=FMath::Clamp(FMath::CeilToInt(Dt/FMath::Max(P.MaxSubstepDt,1.e-3f)),1,FMath::Max(P.MaxSubsteps,1));
	const float H=Dt/NumSteps;
	FVector X=X0;
	FVector V=VNow;
	for (int32 i=0;i<NumSteps;++i)
	{
		V=VelocityAt(X,T0+SimulationTime*((float)i/NumSteps),Up);
		X+=V*H;
	}

	// (4) Output the displacement as a velocity, like the swing
	RootMotionParams.Set(FTransform((X-X0)/Dt-GrappleSwing2::DecayingBaseVelocity(MoveComponent)));
	ReelVelocity=V;
	SetTime(T1);
}

bool FRootMotionSource_GrappleReel2::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	if (!FRootMotionSource::NetSerialize(Ar,Map,bOutSuccess))return false;

	// Loading can reuse an existing struct, so every field is written and read
	Ar << SwingId;
	SerializePackedVector<100,30>(AnchorStart,Ar);
	SerializePackedVector<100,30>(AnchorVelocity,Ar);

	uint8 Flags=0;
	if (Ar.IsSaving())
	{
		Flags=(uint8)Phase&3;
		Flags|=(bPrevJump ? 1 : 0)<<2;
		Flags|=(EndTime>=0.f ? 1 : 0)<<3;
		Flags|=((uint8)EndKind&1)<<4;
	}
	Ar << Flags;
	if (Ar.IsLoading())
	{
		Phase=(EGS2Phase)(Flags&3);
		bPrevJump=((Flags>>2)&1)!=0;
		EndKind=(EGS2EndKind)((Flags>>4)&1);
	}

	uint8 Reason=(uint8)EndReason;
	Ar << Reason;
	EndReason=(EGS2EndReason)Reason;

	Ar << AttachTime;
	SerializePackedVector<100,30>(ReelVelocity,Ar);

	if (Flags&(1<<3))
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

UScriptStruct* FRootMotionSource_GrappleReel2::GetScriptStruct() const
{
	return FRootMotionSource_GrappleReel2::StaticStruct();
}

FString FRootMotionSource_GrappleReel2::ToSimpleString() const
{
	return FString::Printf(TEXT("[ID:%u]FRootMotionSource_GrappleReel2 %s Swing(%u) Phase(%d) Speed(%.0f) ShipSpeed(%.0f) EndTime(%.3f)"),
		LocalID,*InstanceName.GetPlainNameString(),SwingId,(int32)Phase,ReelVelocity.Size(),AnchorVelocity.Size(),EndTime);
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

FRootMotionSource_GrappleReel2* UGA_GrappleSwing2::FindReelSource(TSharedPtr<FRootMotionSource>& OutHolder) const
{
	OutHolder.Reset();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!MoveComp || RootMotionSourceID==GrappleSwing2::InvalidSourceID)return nullptr;
	OutHolder=MoveComp->GetRootMotionSourceByID(RootMotionSourceID);
	if (!OutHolder.IsValid() || OutHolder->GetScriptStruct()!=FRootMotionSource_GrappleReel2::StaticStruct())
	{
		OutHolder.Reset();
		return nullptr;
	}
	return static_cast<FRootMotionSource_GrappleReel2*>(OutHolder.Get());
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
		if (Source.IsValid() && Source->GetScriptStruct()==FRootMotionSource_GrappleReel2::StaticStruct())
		{
			// Ship reel: the rope end follows the moving deck anchor
			const FRootMotionSource_GrappleReel2* Reel=static_cast<const FRootMotionSource_GrappleReel2*>(Source.Get());
			if (Reel->Phase!=EGS2Phase::Swing)continue;
			OutAnchor=Reel->GetAnchorAt(Reel->GetTime());
			OutRopeLength=MoveComp->UpdatedComponent ? (float)FVector::Dist(MoveComp->UpdatedComponent->GetComponentLocation(),OutAnchor) : 0.f;
			bOutTaut=true;
			return true;
		}
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

bool UGA_GrappleSwing2::GetGrappleSwing2Phase(const ACharacter* Character, float& OutPhase)
{
	OutPhase=0.f;
	const UCharacterMovementComponent* MoveComp=Character ? Character->GetCharacterMovement() : nullptr;
	if (!MoveComp || !MoveComp->UpdatedComponent)return false;
	bool bHookFlying=false;
	for (const TSharedPtr<FRootMotionSource>& Source:MoveComp->CurrentRootMotion.RootMotionSources)
	{
		if (Source.IsValid() && Source->GetScriptStruct()==FRootMotionSource_GrappleReel2::StaticStruct())
		{
			// Ship reel: no arc, the pose where the rope pulls for the whole reel (and the hook flight)
			if (static_cast<const FRootMotionSource_GrappleReel2*>(Source.Get())->Phase!=EGS2Phase::Done)
			{
				bHookFlying=true;
			}
			continue;
		}
		if (!Source.IsValid() || Source->GetScriptStruct()!=FRootMotionSource_GrappleSwing2::StaticStruct())continue;
		const FRootMotionSource_GrappleSwing2* Swing=static_cast<const FRootMotionSource_GrappleSwing2*>(Source.Get());
		if (Swing->Phase==EGS2Phase::Travel)
		{
			bHookFlying=true;
		}
		if (Swing->Phase!=EGS2Phase::Swing)continue;

		// Always set on the owner and the server, the defaults only guard a source without it
		static const FGrappleSwing2Tuning DefaultTuning;
		const FGrappleSwing2Tuning& P=Swing->Tuning.IsValid() ? *Swing->Tuning : DefaultTuning;
		const FVector Up=-MoveComp->GetGravityDirection();
		const FVector R=MoveComp->UpdatedComponent->GetComponentLocation()-Swing->Anchor;
		const FVector& V=Swing->SwingVelocity;
		const FVector Forward=GrappleSwing2::ArcForward(V,Swing->PreferredSwingDir,Up);
		const float Angle=GrappleSwing2::ArcAngleDeg(R,Forward,Up);
		if (Angle<=0.f)
		{
			// Hook side: -1 where the rope caught, 0 straight below
			OutPhase=Angle/FMath::Max(-Swing->AttachArcAngle,GrappleSwing2::MinHookArcAngleDeg);
		}
		else
		{
			// Release side: +1 where the full angle from straight down reaches the release angle. With the arc's sideways
			// offset from the anchor, that point sits this far along the motion
			const float ReleaseRad=FMath::DegreesToRadians(GrappleSwing2::PredictReleaseAngleDeg(P,Swing->PeakTangentSpeed,R,V,Up,-MoveComp->GetGravityZ()));
			const float D=R.Size();
			const float Side=R|(Up^Forward);
			const float AlongRel=FMath::Sqrt(FMath::Max(FMath::Square(D*FMath::Sin(ReleaseRad))-Side*Side,0.f));
			const float ReleaseArcDeg=FMath::RadiansToDegrees(FMath::Atan2(AlongRel,D*FMath::Cos(ReleaseRad)));
			OutPhase=Angle/FMath::Max(ReleaseArcDeg,1.f);
		}
		OutPhase=FMath::Clamp(OutPhase,-1.f,1.f);
		return true;
	}
	if (bHookFlying)
	{
		// The swing starts at -1, so the catch doesn't jump
		OutPhase=-1.f;
		return true;
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
	ReelShip.Reset();
	ReelTargetHullLocal=FVector::ZeroVector;
	bReelDropped=false;

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
	// const FVector V=MoveComp->Velocity;
	const FVector V= Character->GetActorForwardVector();
	
	const float G=-MoveComp->GetGravityZ();

	const FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwing2Search),true,Character);
	UWorld* World=GetWorld();
	// The crosshair rays start level with the character so things between the camera and the character don't count
	const FVector RayStart=Ctx.ViewLoc+Ctx.ViewDir*((Ctx.Pos-Ctx.ViewLoc)|Ctx.ViewDir);

	// Ship hook first: the crosshair on a ship is a deliberate aim and wins over any swing anchor (and over the apex wait).
	// The crosshair ray below still sees the ship as a pawn and rejects it, as before, when this one doesn't take it.
	if (IsShipHookOn())
	{
		const float ShipRayLength=FMath::Max(MaxGrappleDistance,MaxShipHookDistance);
		FHitResult ShipHit;
		if (World->LineTraceSingleByChannel(ShipHit,RayStart,RayStart+Ctx.ViewDir*ShipRayLength,GrappleTraceChannel,QueryParams))
		{
			if (AAirshipPawn* Ship=GrappleSwing2::ResolveShip(ShipHit.GetActor()))
			{
				FGS2AnchorCandidate ShipCandidate;
				const bool bValid=EvaluateShipHit(ShipHit,Ship,Ctx,ShipCandidate);
				if (bDrawDebug)
				{
					DrawDebugLine(World,RayStart,ShipHit.ImpactPoint,bValid ? FColor::Cyan : FColor::Magenta,false,0.5f,0,1.f);
				}
				if (bValid)
				{
					if (bDebugLogSearch)
					{
						GS2DebugMessage(FString::Printf(TEXT("GrappleSwing2 search: ship reel to %s, deck target %.0f m away"),*GetNameSafe(Ship),
							FVector::Dist(Ctx.Pos,ShipCandidate.Anchor)/100.f));
						bDebugLogSearch=false;
					}
					OutBest=ShipCandidate;
					return true;
				}
			}
		}
	}

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
	// Search along the motion when moving fast, along the view when slow or when looking against the motion
	Ctx.MoveDirH=VH.Size()>400.f && (VH|ViewH)>=0.f ? VH.GetSafeNormal() : ViewH;
	if (Ctx.MoveDirH.IsNearlyZero())
	{
		Ctx.MoveDirH=Character->GetActorForwardVector();
	}

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

bool UGA_GrappleSwing2::IsShipHookOn() const
{
	if (MaxShipHookDistance<=0.f)return false;
	// The match's rule (replicated, so the client's search agrees with the server). With no match running the grapple is
	// PR A's (a ship is a pawn, never an anchor, and no extra crosshair trace: SPEC_B B5.5), unless the settings let free
	// ships be hooked outside a match too
	if (UMyTeamLibrary::IsMatchActive(this))return UMyTeamLibrary::GetRules(this).bGrappleShips;
	const UMyMatchSettings* Settings=UMyMatchSettings::Get();
	return Settings->bShipHookOutsideMatch&&Settings->DefaultRules.bGrappleShips;
}

bool UGA_GrappleSwing2::TraceStaticPastShip(const FVector& Start, const FVector& End, const AActor* Ship, FHitResult& OutHit) const
{
	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwing2ShipRope),false,GetSwingCharacter());
	if (Ship)
	{
		QueryParams.AddIgnoredActor(Ship);
		TArray<AActor*> Attached;
		Ship->GetAttachedActors(Attached,true,true);
		QueryParams.AddIgnoredActors(Attached);
	}
	return GetWorld()->LineTraceSingleByObjectType(OutHit,Start,End,GrappleSwing2::MakeObjectParams(Swing),QueryParams);
}

bool UGA_GrappleSwing2::FindShipDeckTarget(UPrimitiveComponent& HullComp, const FVector& AimPoint, FVector& OutTargetLocal) const
{
	// Hull space: the hidden hull body's own bounds, like AAirshipPawn's rider test
	const FBox Local=HullComp.CalcBounds(FTransform::Identity).GetBox();
	if (!Local.IsValid)return false;
	const FTransform HullTM=HullComp.GetComponentTransform();
	const FVector HullUp=HullTM.GetUnitAxis(EAxis::Z);
	const FVector Centre=Local.GetCenter();
	const FVector Aimed=HullTM.InverseTransformPosition(AimPoint);

	// Clamped onto the deck: inside the bow and the stern, near the centre line, so an arrival short of the target (it
	// comes in from the side it was shot from) still lands on the deck
	const double InsetX=FMath::Min((double)ShipReelDeckInset,Local.GetExtent().X*0.5);
	const double X=FMath::Clamp(Aimed.X,Local.Min.X+InsetX,Local.Max.X-InsetX);
	const double HalfWidth=FMath::Min((double)ShipReelDeckHalfWidth,Local.GetExtent().Y);
	const double Y=FMath::Clamp(Aimed.Y,Centre.Y-HalfWidth,Centre.Y+HalfWidth);

	// Straight down onto the hull's top (the walkable lid, CPP_NOTES 3), on the hull only, the way UnboardPilot finds the
	// deck. Where the hull is narrower than its box, try nearer the middle
	const double TopZ=FMath::Max(1500.0,Local.Max.Z+100.0);
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(GrappleSwing2ShipDeck),false);
	const FVector2D Tries[]={FVector2D(X,Y),FVector2D(X,Centre.Y),FVector2D(FMath::Lerp(X,Centre.X,0.5),Centre.Y),FVector2D(Centre.X,Centre.Y)};
	for (const FVector2D& Try:Tries)
	{
		FHitResult Hit;
		const FVector Start=HullTM.TransformPosition(FVector(Try.X,Try.Y,TopZ));
		const FVector End=HullTM.TransformPosition(FVector(Try.X,Try.Y,Local.Min.Z-10.0));
		if (HullComp.LineTraceComponent(Hit,Start,End,Params) && (Hit.ImpactNormal|HullUp)>0.5f)
		{
			OutTargetLocal=HullTM.InverseTransformPosition(Hit.ImpactPoint+HullUp*ShipReelTargetHeight);
			return true;
		}
	}
	return false;
}

bool UGA_GrappleSwing2::EvaluateShipHit(const FHitResult& Hit, AAirshipPawn* Ship, const FGS2SearchCtx& Ctx, FGS2AnchorCandidate& Out) const
{
	auto Reject=[&](const FString& Why)
	{
		if (bDebugLogSearch)
		{
			GS2DebugMessage(FString::Printf(TEXT("GrappleSwing2 ship hook reject: %s | ship %s"),*Why,*GetNameSafe(Ship)));
		}
		return false;
	};
	if (!IsValid(Ship) || Ship->IsAirshipDead())return Reject(TEXT("ship dead"));
	UPrimitiveComponent* HullComp=Ship->GetHull();
	if (!HullComp)return Reject(TEXT("ship has no hull"));
	if (bShipHookOwnTeamOnly && !UMyTeamLibrary::CanUseShip(GetSwingCharacter(),Ship))return Reject(TEXT("the other team's ship"));
	const float ShipSpeed=GrappleSwing2::ShipLinearVelocity(*Ship).Size();
	if (ShipSpeed>ShipHookMaxShipSpeed)return Reject(FString::Printf(TEXT("ship speed %.0f above ShipHookMaxShipSpeed %.0f"),ShipSpeed,ShipHookMaxShipSpeed));

	FVector TargetLocal;
	if (!FindShipDeckTarget(*HullComp,Hit.ImpactPoint,TargetLocal))return Reject(TEXT("no deck found under the aimed point"));
	const FTransform HullTM=HullComp->GetComponentTransform();
	const FVector A=HullTM.TransformPosition(TargetLocal);

	const float Dist=FVector::Dist(Ctx.Pos,A);
	if (Dist>MaxShipHookDistance)return Reject(FString::Printf(TEXT("deck target %.0f away, beyond MaxShipHookDistance %.0f"),Dist,MaxShipHookDistance));
	if (Dist<Swing.MinRopeLength+100.f)return Reject(TEXT("already at the deck"));

	// Not from under the hull: the reel would only push into its bottom until it times out
	FHitResult Above;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(GrappleSwing2ShipAbove),false);
	if (HullComp->LineTraceComponent(Above,Ctx.Pos,Ctx.Pos+HullTM.GetUnitAxis(EAxis::Z)*MaxShipHookDistance,Params))return Reject(TEXT("under the ship"));

	// Rope line of sight against static geometry, past the ship and everything attached to it
	const FVector RopeStart=Ctx.Pos+Ctx.Up*Ctx.HalfHeight*Swing.RopeAttachHeightFrac;
	FHitResult LOSHit;
	if (TraceStaticPastShip(RopeStart,A-(A-RopeStart).GetSafeNormal()*Swing.AnchorLOSInset,Ship,LOSHit))
	{
		return Reject(FString::Printf(TEXT("rope line of sight blocked by %s"),*GetNameSafe(LOSHit.GetActor())));
	}

	Out.Anchor=A;
	Out.Normal=HullTM.GetUnitAxis(EAxis::Z);
	Out.bShipReel=true;
	Out.Ship=Ship;
	Out.TargetHullLocal=TargetLocal;
	Out.AnchorVelocity=GrappleSwing2::ShipVelocityAt(*Ship,A);
	Out.Score=0.f;
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
	if (APlayerController* PC=Cast<APlayerController>(Character->GetController()))
	{
		FVector ViewLoc;
		FRotator ViewRot;
		PC->GetPlayerViewPoint(ViewLoc,ViewRot);
		const FVector ViewH=GrappleSwing2::Proj(ViewRot.Vector(),Up).GetSafeNormal();
		if ((GrappleSwing2::Proj(MoveComp->Velocity,Up)|ViewH)<0.f)
		{
			Data.AgainstMotionDir=ViewH;
		}
	}
	Data.TravelTime=FMath::Clamp((float)FVector::Dist(Data.Anchor,Data.StartLocation)/FMath::Max(HookSpeed,1.f),MinHookTravelTime,MaxHookTravelTime);
	Data.FloorHeight=Candidate.FloorHeight;
	Data.bHasFloor=Candidate.bHasFloor ? 1 : 0;
	Data.ChainCount=PendingChainCount;
	if (Candidate.bShipReel)
	{
		// A reel has no arc: no chain stacks, no look-against-the-motion turn, no floor
		Data.bShipReel=1;
		Data.AnchorActor=Candidate.Ship.Get();
		Data.TargetHullLocal=Candidate.TargetHullLocal;
		Data.AnchorVelocity=Candidate.AnchorVelocity;
		Data.AgainstMotionDir=FVector::ZeroVector;
		Data.ChainCount=0;
	}
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

TSharedPtr<FRootMotionSource> UGA_GrappleSwing2::MakeReelSource(const FGameplayAbilityTargetData_GrappleSwing2& Data) const
{
	TSharedPtr<FRootMotionSource_GrappleReel2> Reel=MakeShared<FRootMotionSource_GrappleReel2>();
	Reel->Priority=(uint16)FMath::Clamp(RootMotionPriority,0,65535);
	Reel->Tuning=SharedTuning;
	Reel->SwingId=Data.SwingId;
	Reel->AnchorStart=Data.Anchor;
	Reel->AnchorVelocity=Data.AnchorVelocity;
	Reel->TravelTime=Data.TravelTime;
	Reel->ReelSpeed=FMath::Max(ShipReelSpeed,1.f);
	Reel->ArriveDistance=FMath::Max(ShipReelArriveDistance,0.f);
	Reel->MaxReelTime=FMath::Max(ShipReelMaxTime,0.f);
	Reel->LiftFraction=FMath::Max(ShipReelLiftFraction,0.f);
	Reel->LiftMax=FMath::Max(ShipReelLiftMax,0.f);
	Reel->LeaveUpSpeed=ShipReelLeaveUpSpeed;
	Reel->DeckDropTolerance=FMath::Max(ShipReelDeckBoxMargin,0.f);
	Reel->Phase=EGS2Phase::Travel;
	Reel->AccumulateMode=ERootMotionAccumulateMode::Additive;

	// The deck finish reads this machine's ship (the motion doesn't): the deck part the target is on, around its height
	const AAirshipPawn* Ship=Cast<AAirshipPawn>(Data.AnchorActor.Get());
	UPrimitiveComponent* HullComp=Ship ? Ship->GetHull() : nullptr;
	if (HullComp)
	{
		const FBox Local=HullComp->CalcBounds(FTransform::Identity).GetBox();
		if (Local.IsValid)
		{
			const double Margin=FMath::Max(ShipReelDeckBoxMargin,0.f);
			const double HalfWidth=FMath::Min((double)ShipReelDeckHalfWidth,Local.GetExtent().Y)+Margin;
			const double CentreY=Local.GetCenter().Y;
			Reel->Hull=HullComp;
			Reel->DeckBoxLocal=FBox(
				FVector(Local.Min.X,CentreY-HalfWidth,Data.TargetHullLocal.Z-Margin),
				FVector(Local.Max.X,CentreY+HalfWidth,Data.TargetHullLocal.Z+Margin));
		}
	}
	return Reel;
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

	// Both machines build the source only from the target data and the tuning (a ship reel: and the ability's ship hook
	// values, plus this machine's view of the ship for the deck finish)
	TSharedPtr<FRootMotionSource> Src;
	if (Data.bShipReel)
	{
		Src=MakeReelSource(Data);
		if (!Src.IsValid())return;
	}
	else
	{
		TSharedPtr<FRootMotionSource_GrappleSwing2> SwingSrc=MakeShared<FRootMotionSource_GrappleSwing2>();
		SwingSrc->Priority=(uint16)FMath::Clamp(RootMotionPriority,0,65535);
		SwingSrc->Tuning=SharedTuning;
		SwingSrc->SwingId=Data.SwingId;
		SwingSrc->Anchor=Data.Anchor;
		SwingSrc->PreferredSwingDir=Data.PreferredSwingDir;
		SwingSrc->TravelTime=Data.TravelTime;
		SwingSrc->FloorHeight=Data.FloorHeight;
		SwingSrc->bHasFloorBelowAnchor=Data.bHasFloor!=0;
		SwingSrc->ChainCount=Data.ChainCount;
		SwingSrc->AgainstMotionDir=GrappleSwing2::Proj(Data.AgainstMotionDir,-MoveComp->GetGravityDirection()).GetSafeNormal();
		SwingSrc->Phase=EGS2Phase::Travel;
		SwingSrc->AccumulateMode=ERootMotionAccumulateMode::Additive;
		Src=SwingSrc;
	}

	if (bServerForRemote)
	{
		// Start the server's source clock at the client's move time stamp, so both attach and release on the same move
		const FNetworkPredictionData_Server_Character* ServerData=MoveComp->GetPredictionData_Server_Character();
		if (ServerData && Data.ClientStartTime>=0.f)
		{
			const float Now=ServerData->CurrentClientTimeStamp;
			const float Start=FMath::Min(GrappleSwing2::AlignClientTime(Data.ClientStartTime,Now,MoveComp->MinTimeBetweenTimeStampResets),Now+MaxStartLead);
			Src->StartTime=Start;
			if (Now>Start)
			{
				// Late data: align the clock with the client's, still within the (no-op) hook flight
				Src->SetTime(FMath::Min(Now-Start,Data.TravelTime));
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
	ReelShip=Data.bShipReel ? Cast<AAirshipPawn>(Data.AnchorActor.Get()) : nullptr;
	ReelTargetHullLocal=Data.TargetHullLocal;
	if (Data.bShipReel && HasAuthority(&CurrentActivationInfo))
	{
		// The lane holds its speed and heading until the reel ends (B7.4)
		SetReelRegistered(true);
	}

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
	if (Data.Anchor.ContainsNaN() || Data.StartLocation.ContainsNaN() || Data.AnchorNormal.ContainsNaN() || Data.PreferredSwingDir.ContainsNaN() || Data.AgainstMotionDir.ContainsNaN())return false;
	if (Data.TargetHullLocal.ContainsNaN() || Data.AnchorVelocity.ContainsNaN())return false;

	const FVector Up=-MoveComp->GetGravityDirection();
	const float HalfHeight=Character->GetCapsuleComponent() ? Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;

	// Start location near where the server has the character
	const float StartTolerance=ServerStartTolBase+MoveComp->Velocity.Size()*ServerStartTolSpeedTime;
	if (FVector::Dist(Data.StartLocation,Character->GetActorLocation())>StartTolerance)return false;

	if (Data.bShipReel)
	{
		return ServerValidateReel(Data);
	}

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

float UGA_GrappleSwing2::GetServerReelTime(float ClientStartTime) const
{
	const UCharacterMovementComponent* MoveComp=GetSwingMovement();
	const FNetworkPredictionData_Server_Character* ServerData=MoveComp ? MoveComp->GetPredictionData_Server_Character() : nullptr;
	if (!ServerData || ClientStartTime<0.f)return 0.f;
	// Where StartSwing will put the source clock
	const float Now=ServerData->CurrentClientTimeStamp;
	const float Start=FMath::Min(GrappleSwing2::AlignClientTime(ClientStartTime,Now,MoveComp->MinTimeBetweenTimeStampResets),Now+MaxStartLead);
	return FMath::Max(Now-Start,0.f);
}

bool UGA_GrappleSwing2::ServerValidateReel(const FGameplayAbilityTargetData_GrappleSwing2& Data) const
{
	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	if (!Character || !MoveComp)return false;
	auto Reject=[&](const FString& Why)
	{
		// Once per hook at most: the T6 / M7 tests read it
		UE_LOG(LogGrappleSwing2,Log,TEXT("GrappleSwing2 ship hook %u rejected by the server: %s"),Data.SwingId,*Why);
		return false;
	};

	// The ship alive and allowed
	AAirshipPawn* Ship=Cast<AAirshipPawn>(Data.AnchorActor.Get());
	if (!IsShipHookOn())return Reject(TEXT("ship hook off"));
	if (!IsValid(Ship) || Ship->IsAirshipDead())return Reject(TEXT("no ship, or it is dead"));
	UPrimitiveComponent* HullComp=Ship->GetHull();
	if (!HullComp)return Reject(TEXT("ship has no hull"));
	if (bShipHookOwnTeamOnly && !UMyTeamLibrary::CanUseShip(Character,Ship))return Reject(TEXT("the other team's ship"));
	const FVector ShipVelocity=GrappleSwing2::ShipLinearVelocity(*Ship);
	// The client checked its own view against ShipHookMaxShipSpeed; the velocity check below covers the difference
	if (ShipVelocity.Size()>ShipHookMaxShipSpeed+ShipHookMaxVelocityError)return Reject(FString::Printf(TEXT("ship speed %.0f"),ShipVelocity.Size()));

	// The target is on this hull (the client traced the same hull-space deck)
	const FBox Local=HullComp->CalcBounds(FTransform::Identity).GetBox();
	if (!Local.IsValid || !Local.ExpandBy(FVector(0.0,0.0,ShipReelTargetHeight+100.0)).IsInsideOrOn(Data.TargetHullLocal))
	{
		return Reject(FString::Printf(TEXT("deck target %s outside the hull"),*Data.TargetHullLocal.ToString()));
	}

	// Client and server see the ship at different times (physics replication lag), so neither can trust its own view of
	// the hull: the server's hull point must be near the client's moving anchor at the server's source time, within the
	// drift allowance, and the anchor's velocity near the ship's there
	const float Tau=GetServerReelTime(Data.ClientStartTime);
	const FVector ServerPoint=HullComp->GetComponentTransform().TransformPosition(Data.TargetHullLocal);
	const FVector ClientPoint=Data.Anchor+Data.AnchorVelocity*Tau;
	const float Drift=FVector::Dist(ServerPoint,ClientPoint);
	const float Allowance=ShipHookMaxDrift+ShipVelocity.Size()*ShipHookLatencyAllowance;
	if (Drift>Allowance)return Reject(FString::Printf(TEXT("hull point %.0f from the client's anchor, allowance %.0f"),Drift,Allowance));
	const float VelocityError=(Data.AnchorVelocity-GrappleSwing2::ShipVelocityAt(*Ship,ServerPoint)).Size();
	if (VelocityError>ShipHookMaxVelocityError)return Reject(FString::Printf(TEXT("anchor velocity %.0f off the ship's"),VelocityError));

	// Range, with the allowance for the longest hook flight
	const float G=-MoveComp->GetGravityZ();
	const float FlightSlack=(float)MoveComp->Velocity.Size()*MaxHookTravelTime+0.5f*FMath::Abs(G)*MaxHookTravelTime*MaxHookTravelTime;
	const float Range=FVector::Dist(Data.Anchor,Data.StartLocation);
	if (Range>MaxShipHookDistance+ServerRangeTolerance+FlightSlack)return Reject(FString::Printf(TEXT("range %.0f"),Range));

	// Rope line of sight against static geometry, past the ship and everything attached to it (its turrets' hit boxes)
	const FVector Up=-MoveComp->GetGravityDirection();
	const float HalfHeight=Character->GetCapsuleComponent() ? Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 88.f;
	const FVector RopeStart=Data.StartLocation+Up*HalfHeight*Swing.RopeAttachHeightFrac;
	const FVector RopeDir=(Data.Anchor-RopeStart).GetSafeNormal();
	FHitResult Hit;
	if (TraceStaticPastShip(RopeStart,Data.Anchor-RopeDir*Swing.AnchorLOSInset,Ship,Hit))
	{
		return Reject(FString::Printf(TEXT("rope line of sight blocked by %s"),*GetNameSafe(Hit.GetActor())));
	}
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

void UGA_GrappleSwing2::SetReelRegistered(bool bRegister)
{
	if (bRegister==bReelRegistered)return;
	AAirshipPawn* Ship=ReelShip.Get();
	UWorld* World=GetWorld();
	if (bRegister)
	{
		if (!Ship || !World)return;
		bReelRegistered=true;
		ReelReeler=GetSwingCharacter();
		Ship->NotifyIncomingReel(ReelReeler.Get(),true);
		// Safety: the ship is told the reel ended at most this long after it started, whatever happens to this ability
		// (the ship also expires the entry by itself)
		const float Safety=MaxHookTravelTime+FMath::Max(ShipReelMaxTime,0.f)+1.f;
		World->GetTimerManager().SetTimer(ReelSafetyTimerHandle,this,&ThisClass::OnReelSafetyTimeout,Safety,false);
		return;
	}
	bReelRegistered=false;
	if (World)
	{
		World->GetTimerManager().ClearTimer(ReelSafetyTimerHandle);
	}
	if (Ship)
	{
		// The same actor as at the start, even while it is being destroyed
		Ship->NotifyIncomingReel(ReelReeler.Get(true),false);
	}
	ReelReeler.Reset();
}

void UGA_GrappleSwing2::OnReelSafetyTimeout()
{
	if (!bReelRegistered)return;
	UE_LOG(LogGrappleSwing2,Warning,TEXT("GrappleSwing2 ship reel still registered with %s after its time limit, ending the registration"),*GetNameSafe(ReelShip.Get()));
	SetReelRegistered(false);
}

bool UGA_GrappleSwing2::CheckReelOnServer(FRootMotionSource_GrappleReel2& Reel)
{
	AAirshipPawn* Ship=ReelShip.Get();
	UPrimitiveComponent* HullComp=Ship ? Ship->GetHull() : nullptr;
	if (!HullComp || Ship->IsActorBeingDestroyed() || Ship->IsAirshipDead())
	{
		DropReel(Reel,TEXT("the ship is gone or dead"));
		return false;
	}
	// The same allowance as the validation: a lane ship holds its speed during the reel and stays within it, a piloted
	// ship that turns or brakes leaves the anchor line and the player falls
	const FVector ShipVelocity=GrappleSwing2::ShipLinearVelocity(*Ship);
	const FVector HullPoint=HullComp->GetComponentTransform().TransformPosition(ReelTargetHullLocal);
	const float Drift=FVector::Dist(HullPoint,Reel.GetAnchorAt(Reel.GetTime()));
	const float Allowance=ShipHookMaxDrift+ShipVelocity.Size()*ShipHookLatencyAllowance;
	if (Drift>Allowance)
	{
		DropReel(Reel,FString::Printf(TEXT("hull point %.0f from the anchor, allowance %.0f (ship %.0f cm/s)"),Drift,Allowance,ShipVelocity.Size()));
		return false;
	}
	return true;
}

void UGA_GrappleSwing2::DropReel(FRootMotionSource_GrappleReel2& Reel, const FString& Why)
{
	UE_LOG(LogGrappleSwing2,Log,TEXT("GrappleSwing2 ship reel %u ended by the server: %s"),Reel.SwingId,*Why);
	SetReelRegistered(false);
	if (IsLocallyControlled())
	{
		// The listen server's own player: a graceful forced end next move, Poll then ends the ability. No re-fire while the
		// button stays held (the crosshair is likely still on the ship)
		bReelDropped=true;
		RequestEnd(Reel,Reel.GetTime(),EGS2EndKind::Forced);
		return;
	}
	// Server for a remote client: the existing reject path. Finish here next move with the velocity kept, and tell the
	// client to drop its own copy (OnServerRejected); the CMC corrects the moves in between. The player falls.
	if (Reel.EndTime<0.f || Reel.EndTime>Reel.GetTime())
	{
		Reel.EndTime=Reel.GetTime();
		Reel.EndKind=EGS2EndKind::Forced;
	}
	K2_RemoveGameplayCue(RopeCueTag);
	if (AActor* AscOwner=GetOwningActorFromActorInfo())
	{
		AscOwner->ForceNetUpdate();
	}
	if (ACharacter* Character=GetSwingCharacter())
	{
		Character->ForceNetUpdate();
	}
	ServerReject();
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
	if (FRootMotionSource_GrappleReel2* Reel=FindReelSource(Holder))
	{
		// Ship reel: the same rules as the swing's below (the client only sends one when the ability ends)
		if (Reel->SwingId!=(uint16)FMath::RoundToInt(Payload.Y))return;
		const float ClientEndTime=Payload.X/1000.f;
		float EndTime=FMath::Clamp(ClientEndTime,Reel->GetTime(),Reel->GetTime()+MaxReleaseLead);
		if (Reel->Phase==EGS2Phase::Travel && ClientEndTime<Reel->TravelTime-1.e-4f)
		{
			EndTime=FMath::Min(EndTime,Reel->TravelTime-2.e-4f);
		}
		if (Reel->EndTime>=0.f && Reel->EndTime<=EndTime)return;
		Reel->EndTime=EndTime;
		Reel->EndKind=FMath::RoundToInt(Payload.Z)==(int32)EGS2EndKind::Forced ? EGS2EndKind::Forced : EGS2EndKind::Release;
		return;
	}
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
	SendEndTime(EndTime,Src.SwingId,Kind);
}

void UGA_GrappleSwing2::RequestEnd(FRootMotionSource_GrappleReel2& Src, float EndTime, EGS2EndKind Kind)
{
	if (Src.EndTime>=0.f && Src.EndTime<=EndTime)return;
	Src.EndTime=EndTime;
	Src.EndKind=Kind;
	SendEndTime(EndTime,Src.SwingId,Kind);
}

void UGA_GrappleSwing2::SendEndTime(float EndTime, uint16 SwingId, EGS2EndKind Kind)
{
	if (IsLocallyControlled() && !HasAuthority(&CurrentActivationInfo))
	{
		// Reliable on the ASC channel and sent before the next ServerMove, so the server ends on the same move.
		// Time in ms for precision in the quantized payload.
		if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
		{
			ASC->ServerSetReplicatedEventWithPayload(EAbilityGenericReplicatedEvent::GameCustom1,CurrentSpecHandle,ActiveActivationKey,
				ASC->ScopedPredictionKey,FVector_NetQuantize100(EndTime*1000.f,(float)SwingId,(float)(uint8)Kind));
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
			if (FindReelSource(Holder))
			{
				// A ship reel runs to the deck on its own (a tap is enough): only remember that the button is up, so the
				// ability ends when the reel does. Jump still lets go
				State=EGS2AbilityState::Releasing;
				break;
			}
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
	// The ship reel's source when this activation reels (the holder then keeps it)
	FRootMotionSource_GrappleReel2* Reel=Src ? nullptr : FindReelSource(Holder);
	if (Src)
	{
		bSourceSeen=true;
		LastSeenEndReason=Src->EndReason;
	}
	else if (Reel)
	{
		bSourceSeen=true;
		LastSeenEndReason=Reel->EndReason;
	}

	if (bAuthority && !bLocal && !bServerSawAttach && ((Src && Src->Phase==EGS2Phase::Swing) || (Reel && Reel->Phase==EGS2Phase::Swing)))
	{
		bServerSawAttach=true;
		Character->ForceNetUpdate();
	}

	const bool bSwinging=State==EGS2AbilityState::Hooked || State==EGS2AbilityState::Releasing;
	const bool bReelRunning=Reel && Reel->Phase!=EGS2Phase::Done && !Reel->Status.HasFlag(ERootMotionSourceStatusFlags::Finished);

	// Ship reel, server: the ship must stay on the anchor line the reel follows, and alive. A drop for a remote client
	// moves the state to Rejected (the client falls), so nothing below treats it as an end
	if (bAuthority && bSwinging && bReelRegistered && bReelRunning)
	{
		CheckReelOnServer(*Reel);
	}

	const bool bStillSwinging=State==EGS2AbilityState::Hooked || State==EGS2AbilityState::Releasing;
	// A source that never showed up (still pending, or lost) only counts as gone after a grace period
	const bool bMissing=!Src && !Reel && (bSourceSeen || Now-SwingStartWorldTime>GrappleSwing2::SourceAppearTimeout);
	const bool bOver=bStillSwinging && (bMissing || (Src && (Src->Phase==EGS2Phase::Done || Src->Status.HasFlag(ERootMotionSourceStatusFlags::Finished)))
		|| (Reel && !bReelRunning));

	if (bOver)
	{
		// Vanished unseen: infer the reason
		const EGS2EndReason Reason=Src ? Src->EndReason : Reel ? Reel->EndReason
			: (LastSeenEndReason!=EGS2EndReason::None ? LastSeenEndReason : (MoveComp->IsMovingOnGround() ? EGS2EndReason::Landed : EGS2EndReason::Snapped));
		RootMotionSourceID=GrappleSwing2::InvalidSourceID;
		Holder.Reset();
		Src=nullptr;
		Reel=nullptr;
		if (bAuthority)
		{
			// The reel is over: the ship may move on
			SetReelRegistered(false);
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

			// Landed, JumpReleased, Timeout, a ship reel's arrival, or the listen server's own reel dropped by its check:
			// no re-fire while the button stays held (on the deck, or with the crosshair still on the ship)
			const bool bHoldStops=Reason==EGS2EndReason::Landed || Reason==EGS2EndReason::JumpReleased || Reason==EGS2EndReason::Timeout
				|| Reason==EGS2EndReason::Arrived || bReelDropped;
			if (bHoldStops)
			{
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
			}
			else
			{
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
		else if (FRootMotionSource_GrappleReel2* Reel=Src ? nullptr : FindReelSource(Holder))
		{
			// The same for a ship reel (both kinds keep the reel velocity)
			if (Reel->Phase!=EGS2Phase::Done && !Reel->Status.HasFlag(ERootMotionSourceStatusFlags::Finished))
			{
				const float EndTime=Reel->Phase==EGS2Phase::Travel ? FMath::Min(Reel->GetTime(),Reel->TravelTime-2.e-4f) : Reel->GetTime();
				RequestEnd(*Reel,EndTime,bWasCancelled ? EGS2EndKind::Forced : EGS2EndKind::Release);
			}
		}
	}

	// The ship may move on (server)
	if (HasAuthority(&ActivationInfo))
	{
		SetReelRegistered(false);
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
	ReelShip.Reset();
	bReelDropped=false;

	// Clears every timer this object owns, so the gate is armed after it
	Super::EndAbility(Handle,ActorInfo,ActivationInfo,bReplicateEndAbility,bWasCancelled);

	if (bGate)
	{
		bBlockUntilRelease=true;
		GetWorld()->GetTimerManager().SetTimer(GateTimerHandle,this,&ThisClass::GatePoll,FMath::Max(GatePollInterval,0.01f),true);
	}
	bIntentionalEnd=false;
}

