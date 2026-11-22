// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCharacterMovementComponent.h"

#include "GameFramework/Character.h"

/** Saved move with GA_JumpHover's hover wish */
class FSavedMove_MyCharacter : public FSavedMove_Character
{
public:
	typedef FSavedMove_Character Super;

	uint8 bSavedWantsToHover:1;
	uint8 bSavedPrevWantsToHover:1;

	FSavedMove_MyCharacter()
	{
		bSavedWantsToHover=false;
		bSavedPrevWantsToHover=false;
	}

	virtual void Clear() override
	{
		Super::Clear();
		bSavedWantsToHover=false;
		bSavedPrevWantsToHover=false;
	}

	virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override
	{
		Super::SetMoveFor(C,InDeltaTime,NewAccel,ClientData);
		if (const UMyCharacterMovementComponent* Move=Cast<UMyCharacterMovementComponent>(C->GetCharacterMovement()))
		{
			bSavedWantsToHover=Move->bWantsToHover;
			bSavedPrevWantsToHover=Move->bPrevWantsToHover;
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
	}

	virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override
	{
		const FSavedMove_MyCharacter* Other=static_cast<const FSavedMove_MyCharacter*>(NewMove.Get());
		if (bSavedWantsToHover!=Other->bSavedWantsToHover || bSavedPrevWantsToHover!=Other->bSavedPrevWantsToHover)
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
	Super::ControlledCharacterMove(InputVector,DeltaSeconds);
}

bool UMyCharacterMovementComponent::DoJump(bool bReplayingMoves, float DeltaTime)
{
	bPendingAirJumpRedirect=false;
	// Root motion owns the velocity (GA_GrappleSwing2's swing, montages): no jump, so the air jump is kept. The jump
	// flag still travels with the move, which is what lets go of the rope
	if (HasAnimRootMotion() || CurrentRootMotion.HasOverrideVelocity())
	{
		return false;
	}

	// An air jump starts on this move: already falling, and not the held part of an earlier jump (JumpMaxHoldTime).
	// Read before Super, which switches to MOVE_Falling. AMyCharPlayer::CheckJumpInput keeps bWasJumping right in replays
	const bool bAirJump=CharacterOwner && IsFalling() && !CharacterOwner->bWasJumping;

	if (!Super::DoJump(bReplayingMoves,DeltaTime))
	{
		return false;
	}

	bPendingAirJumpRedirect=bAirJump;
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

	const FVector Horizontal=FVector::VectorPlaneProject(Velocity,Up);
	const FVector Vertical=Velocity-Horizontal;
	const float BaseSpeed=(AirJumpHorizontalSpeed>0.f ? AirJumpHorizontalSpeed : MaxWalkSpeed)*InputStrength;
	const float NewSpeed=FMath::Max(static_cast<float>(Horizontal.Size())*AirJumpKeepSpeed,BaseSpeed);
	Velocity=Vertical+Input.GetSafeNormal()*NewSpeed;
}
