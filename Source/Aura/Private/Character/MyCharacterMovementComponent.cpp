// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharacterMovementComponent.h"

#include "AbilitySystem/Abilities/GA_GrappleSwing2.h"
#include "Character/MyCharPlayer.h"
#include "GameFramework/Character.h"

/** Saved move with GA_JumpHover's hover wish */
class FSavedMove_MyCharacter : public FSavedMove_Character
{
public:
	typedef FSavedMove_Character Super;

	uint8 bSavedWantsToHover:1;
	uint8 bSavedPrevWantsToHover:1;
	// Character::bWasJumping before this move's CheckJumpInput. The engine saves it after (SetInitialPosition), which
	// makes a replayed jump press look like the held part of a jump: no count, no air jump
	uint8 bSavedWasJumpingBeforeMove:1;

	FSavedMove_MyCharacter()
	{
		bSavedWantsToHover=false;
		bSavedPrevWantsToHover=false;
		bSavedWasJumpingBeforeMove=false;
	}

	virtual void Clear() override
	{
		Super::Clear();
		bSavedWantsToHover=false;
		bSavedPrevWantsToHover=false;
		bSavedWasJumpingBeforeMove=false;
	}

	virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override
	{
		Super::SetMoveFor(C,InDeltaTime,NewAccel,ClientData);
		if (const UMyCharacterMovementComponent* Move=Cast<UMyCharacterMovementComponent>(C->GetCharacterMovement()))
		{
			bSavedWantsToHover=Move->bWantsToHover;
			bSavedPrevWantsToHover=Move->bPrevWantsToHover;
			bSavedWasJumpingBeforeMove=Move->bWasJumpingBeforeMove;
		}
	}

	virtual void PrepMoveFor(ACharacter* C) override
	{
		Super::PrepMoveFor(C);
		// The wish itself comes back through the compressed flags (UpdateFromCompressedFlags in MoveAutonomous)
		if (UMyCharacterMovementComponent* Move=Cast<UMyCharacterMovementComponent>(C->GetCharacterMovement()))
		{
			Move->bPrevWantsToHover=bSavedPrevWantsToHover;
		}
		C->bWasJumping=bSavedWasJumpingBeforeMove;
	}

	virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override
	{
		const FSavedMove_MyCharacter* Other=static_cast<const FSavedMove_MyCharacter*>(NewMove.Get());
		if (bSavedWantsToHover!=Other->bSavedWantsToHover || bSavedPrevWantsToHover!=Other->bSavedPrevWantsToHover
			|| bSavedWasJumpingBeforeMove!=Other->bSavedWasJumpingBeforeMove)
		{
			return false;
		}
		return Super::CanCombineWith(NewMove,InCharacter,MaxDelta);
	}

	virtual uint8 GetCompressedFlags() const override
	{
		uint8 Flags=Super::GetCompressedFlags();
		if (bSavedWantsToHover)
		{
			Flags|=FLAG_Custom_0;
		}
		return Flags;
	}
};

class FNetworkPredictionData_Client_MyCharacter : public FNetworkPredictionData_Client_Character
{
public:
	typedef FNetworkPredictionData_Client_Character Super;

	FNetworkPredictionData_Client_MyCharacter(const UCharacterMovementComponent& ClientMovement)
		: Super(ClientMovement)
	{
	}

	virtual FSavedMovePtr AllocateNewMove() override
	{
		return FSavedMovePtr(new FSavedMove_MyCharacter());
	}
};

UMyCharacterMovementComponent::UMyCharacterMovementComponent()
{
}

FNetworkPredictionData_Client* UMyCharacterMovementComponent::GetPredictionData_Client() const
{
	if (ClientPredictionData==nullptr)
	{
		UMyCharacterMovementComponent* MutableThis=const_cast<UMyCharacterMovementComponent*>(this);
		MutableThis->ClientPredictionData=new FNetworkPredictionData_Client_MyCharacter(*this);
	}
	return ClientPredictionData;
}

void UMyCharacterMovementComponent::UpdateFromCompressedFlags(uint8 Flags)
{
	Super::UpdateFromCompressedFlags(Flags);
	bWantsToHover=(Flags & FSavedMove_Character::FLAG_Custom_0)!=0;
}

void UMyCharacterMovementComponent::ControlledCharacterMove(const FVector& InputVector, float DeltaSeconds)
{
	// A new local move (owning client, listen server host, standalone): it carries the current request
	bWantsToHover=bHoverRequest;
	// Before CheckJumpInput (inside Super), for the saved move: replays restore it (FSavedMove_MyCharacter)
	bWasJumpingBeforeMove=CharacterOwner && CharacterOwner->bWasJumping;
	Super::ControlledCharacterMove(InputVector,DeltaSeconds);
}

bool UMyCharacterMovementComponent::DoJump(bool bReplayingMoves, float DeltaTime)
{
	bPendingAirJumpRedirect=false;
	bPendingAirJumpNotify=false;
	// Root motion owns the velocity (GA_GrappleSwing2's swing, montages): no jump, so the air jump is kept. The jump
	// flag still travels with the move, which is what lets go of the rope
	if (HasAnimRootMotion() || CurrentRootMotion.HasOverrideVelocity())
	{
		return false;
	}

	// An air jump starts on this move: already falling, and not the held part of an earlier jump (JumpMaxHoldTime).
	// Read before Super, which switches to MOVE_Falling. Replays restore bWasJumping as it was before the move
	// (FSavedMove_MyCharacter::PrepMoveFor), so a replayed press is an air jump again
	const bool bAirJump=CharacterOwner && IsFalling() && !CharacterOwner->bWasJumping;

	if (!Super::DoJump(bReplayingMoves,DeltaTime))
	{
		return false;
	}

	bPendingAirJumpRedirect=bAirJump;
	bPendingAirJumpNotify=bAirJump && !bReplayingMoves;
	if (bAirJump)
	{
		// Super only raises the upward speed to JumpZVelocity on the first jump or with bDontFallBelowJumpZVelocityDuringJump
		const float UpSpeed=AirJumpZVelocity>0.f ? AirJumpZVelocity : JumpZVelocity;
		if (HasCustomGravity())
		{
			SetGravitySpaceZ(Velocity,FMath::Max<FVector::FReal>(GetGravitySpaceZ(Velocity),UpSpeed));
		}
		else
		{
			Velocity.Z=FMath::Max<FVector::FReal>(Velocity.Z,UpSpeed);
		}
		if (!bReplayingMoves)
		{
			++AirJumpCount;
		}
	}
	return true;
}

void UMyCharacterMovementComponent::UpdateCharacterStateBeforeMovement(float DeltaSeconds)
{
	Super::UpdateCharacterStateBeforeMovement(DeltaSeconds);

	ApplyHover();
	if (bPendingAirJumpRedirect)
	{
		bPendingAirJumpRedirect=false;
		ApplyAirJumpRedirect();
	}
	if (bPendingAirJumpNotify)
	{
		bPendingAirJumpNotify=false;
		// After the redirect: the montage can't change this move's velocity
		if (AMyCharPlayer* Player=Cast<AMyCharPlayer>(CharacterOwner))
		{
			Player->OnAirJumped();
		}
	}

	// On the rope the air jump comes back (inside the move, so the server and replays do the same). The jump that lets
	// go of the rope doesn't jump (DoJump above), so the air jump is still there after the release
	if (bAirJumpResetsOnSwing && CharacterOwner && IsOnGrappleRope())
	{
		CharacterOwner->JumpCurrentCount=0;
		CharacterOwner->JumpCurrentCountPreJump=0;
	}
}

bool UMyCharacterMovementComponent::IsOnGrappleRope() const
{
	for (const TSharedPtr<FRootMotionSource>& Source:CurrentRootMotion.RootMotionSources)
	{
		if (Source.IsValid() && Source->GetScriptStruct()==FRootMotionSource_GrappleSwing2::StaticStruct()
			&& static_cast<const FRootMotionSource_GrappleSwing2*>(Source.Get())->Phase==EGS2Phase::Swing)
		{
			return true;
		}
	}
	return false;
}

void UMyCharacterMovementComponent::ApplyImpartedMovementBaseVelocity()
{
	// What Super adds to Velocity: the base's velocity at the character (zero for a base that does not move)
	CarriedBaseVelocity=GetImpartedMovementBaseVelocity();
	Super::ApplyImpartedMovementBaseVelocity();
}

void UMyCharacterMovementComponent::OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode)
{
	if (MovementMode==MOVE_Falling)
	{
		// Before Super, which reads it: leaving the deck of a vehicle (a base under a pawn that simulates physics: the
		// airship's physics asset bodies and its turrets under the simulating hull) keeps the base in the air; any other
		// base is dropped and gives its velocity (ApplyImpartedMovementBaseVelocity) as always. UpdateBasedMovement
		// reads it while falling and drops the base once the character is not over it any more
		bool bOnVehicle=false;
		const FMovementBaseInterfaceData* Base=GetMovementBaseInterfaceData();
		if (bStayOnVehicleInAir && MovementBaseUtility::IsSimulatedBase(Base))
		{
			const USceneComponent* Root=Cast<USceneComponent>(Base->GetBodyInstanceOwner()->GetPhysicsOwnerAttachmentRoot());
			bOnVehicle=Root && Cast<APawn>(Root->GetOwner())!=nullptr;
		}
		bStayBasedInAir=bOnVehicle;
	}
	Super::OnMovementModeChanged(PreviousMovementMode,PreviousCustomMode);
	if (MovementMode!=MOVE_Falling)
	{
		// Landed, hovering (its braking takes the speed off), swimming...: nothing carried any more
		CarriedBaseVelocity=FVector::ZeroVector;
	}
}

void UMyCharacterMovementComponent::SetPostLandedPhysics(const FHitResult& Hit)
{
	const bool bWasFalling=IsFalling();
	// Walking again: Super finds the floor and sets the new base (OnMovementModeChanged)
	Super::SetPostLandedPhysics(Hit);
	if (!bWasFalling || !IsMovingOnGround() || HasAnimRootMotion() || CurrentRootMotion.HasOverrideVelocity())
	{
		return;
	}

	// Landed on a moving base. Walking velocity is relative to the base (the base's own movement is added on top by
	// UpdateBasedMovement), but Velocity still holds the world velocity of the fall: after a jump on the deck of an
	// airship at 48 m/s that is the ship's 48 m/s, and the character slid 2.7 m along the deck until the ground friction
	// had taken it off. The same velocity the engine gives on leaving the base (GetImpartedMovementBaseVelocity, now of
	// the base landed on) comes off here, in the floor's plane. Only when that leaves the smaller speed: a character
	// that reaches the deck from outside, slow in the world, keeps the engine's landing (it sticks to the deck)
	const FVector Up=-GetGravityDirection();
	const FVector BaseVelocity=FVector::VectorPlaneProject(GetImpartedMovementBaseVelocity(),Up);
	if (BaseVelocity.IsNearlyZero())
	{
		return;
	}
	const FVector Horizontal=FVector::VectorPlaneProject(Velocity,Up);
	const FVector Relative=Horizontal-BaseVelocity;
	if (Relative.SizeSquared()<Horizontal.SizeSquared())
	{
		Velocity+=Relative-Horizontal;
	}
}

void UMyCharacterMovementComponent::ApplyHover()
{
	if (bWantsToHover)
	{
		// Every move while wished, so a correction that put the character back in falling is re-applied in the replay
		if (IsFalling())
		{
			SetMovementMode(MOVE_Flying);
		}
	}
	else if (bPrevWantsToHover && MovementMode==MOVE_Flying)
	{
		SetMovementMode(MOVE_Falling);
	}
	bPrevWantsToHover=bWantsToHover;
}

void UMyCharacterMovementComponent::ApplyAirJumpRedirect()
{
	if (!bAirJumpRedirectsVelocity)
	{
		return;
	}
	if (HasAnimRootMotion() || CurrentRootMotion.HasOverrideVelocity())
	{
		return;
	}

	const FVector Up=-GetGravityDirection();
	// This move's input: Acceleration is the input scaled to GetMaxAcceleration() (clamped on the server too)
	const FVector Input=FVector::VectorPlaneProject(Acceleration,Up);
	const float MaxAccel=GetMaxAcceleration();
	const float InputStrength=MaxAccel>UE_KINDA_SMALL_NUMBER ? FMath::Clamp(static_cast<float>(Input.Size())/MaxAccel,0.f,1.f) : 0.f;
	if (InputStrength<=UE_KINDA_SMALL_NUMBER || InputStrength<AirJumpMinInput)
	{
		// No direction held: only the upward kick
		return;
	}

	// Relative to the moving base the character left (zero otherwise): after a jump on an airship's deck the horizontal
	// velocity is the ship's 48 m/s plus the character's own. Turning all of it toward the input threw the character
	// off the ship at the ship's speed; only its own part turns, the ship's stays
	const FVector Carried=FVector::VectorPlaneProject(CarriedBaseVelocity,Up);
	const FVector HorizontalWorld=FVector::VectorPlaneProject(Velocity,Up);
	const FVector Vertical=Velocity-HorizontalWorld;
	const FVector Horizontal=HorizontalWorld-Carried;
	const float BaseSpeed=(AirJumpHorizontalSpeed>0.f ? AirJumpHorizontalSpeed : MaxWalkSpeed)*InputStrength;
	const float NewSpeed=FMath::Max(static_cast<float>(Horizontal.Size())*AirJumpKeepSpeed,BaseSpeed);
	Velocity=Vertical+Carried+Input.GetSafeNormal()*NewSpeed;
}
