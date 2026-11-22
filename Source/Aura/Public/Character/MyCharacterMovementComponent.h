// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "MyCharacterMovementComponent.generated.h"

/**
 * Character movement for the player mech (AMyCharPlayer). GA_JumpHover decides what a press does; this class does
 * the movement side inside the move stream, so the owning client, the server and replays after a correction all
 * simulate it on the same move.
 *
 * Air jump: AMyCharPlayer allows two jumps (JumpMaxCount 2). The second one, or the first one when the character is
 * already falling (walked off a ledge), is an air jump: on top of the normal jump velocity it turns the horizontal
 * velocity toward the movement input of that move.
 *
 * Hover: the hover wish travels with every saved move (FLAG_Custom_0). While it is on, a falling character switches
 * to MOVE_Flying; when it goes off, a flying character drops back to MOVE_Falling (only on that change, so other
 * flying, such as GA_BoostBP's, is left alone).
 */
UCLASS()
class AURA_API UMyCharacterMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()

	friend class FSavedMove_MyCharacter;

public:
	UMyCharacterMovementComponent();

	virtual bool DoJump(bool bReplayingMoves, float DeltaTime) override;
	virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;

	// Owning client / listen server host: GA_JumpHover asks for the hover. Applied from the next move on
	void SetHoverRequest(bool bInHover) { bHoverRequest=bInHover; }
	bool GetHoverRequest() const { return bHoverRequest; }

	// In GA_JumpHover's hover on this machine (the wish of the last simulated move, and MOVE_Flying)
	bool IsHovering() const { return bWantsToHover && MovementMode==MOVE_Flying; }

	// Turn the horizontal velocity toward the movement input when the air jump happens
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump")
	bool bAirJumpRedirectsVelocity=true;

	// Horizontal speed (cm/s) after an air jump at full input. 0 = MaxWalkSpeed.
	// A faster character keeps its speed (scaled by AirJumpKeepSpeed) in the new direction.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump", meta=(ClampMin="0", ForceUnits="cm/s"))
	float AirJumpHorizontalSpeed=0.f;

	// How much of the horizontal speed before the air jump it keeps, in the new direction (0..1)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump", meta=(ClampMin="0", ClampMax="1"))
	float AirJumpKeepSpeed=1.f;

	// Upward speed (cm/s) of the air jump. 0 = JumpZVelocity
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump", meta=(ClampMin="0", ForceUnits="cm/s"))
	float AirJumpZVelocity=0.f;

	// Movement input below this fraction of full input keeps the current direction (only the upward kick)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump", meta=(ClampMin="0", ClampMax="1"))
	float AirJumpMinInput=0.1f;

	// Air jumps so far on this machine (not counting replays), for debugging and tests
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category="Character Movement: Jumping / Falling|Air Jump")
	int32 AirJumpCount=0;

	// Hover wish of the move being simulated (from the saved move's flags on the server and in replays)
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category="Character Movement: Jumping / Falling|Hover")
	bool bWantsToHover=false;

protected:
	virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;
	virtual void ControlledCharacterMove(const FVector& InputVector, float DeltaSeconds) override;

private:
	// GA_JumpHover's request on the owning machine. Copied into bWantsToHover for each new local move, so a replay
	// (which sets bWantsToHover from the saved moves) never loses a request made since
	bool bHoverRequest=false;

	// The wish of the previous move: a true -> false change drops out of MOVE_Flying. Saved and restored with the moves
	bool bPrevWantsToHover=false;

	// Character::bWasJumping at the start of the current local move, for FSavedMove_MyCharacter
	bool bWasJumpingBeforeMove=false;

	/**
	 * Set by DoJump for an air jump and used in UpdateCharacterStateBeforeMovement of the same move. DoJump runs
	 * before the move's acceleration is set (CheckJumpInput comes first in ControlledCharacterMove and MoveAutonomous),
	 * UpdateCharacterStateBeforeMovement runs after it, so the redirect uses the input of the move that jumped.
	 */
	bool bPendingAirJumpRedirect=false;

	void ApplyHover();
	void ApplyAirJumpRedirect();
};
