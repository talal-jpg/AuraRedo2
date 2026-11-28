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
 * The air jump comes back on landing and while hanging on a GA_GrappleSwing2 rope (its root motion source in the
 * Swing phase), so a swing always leaves one air jump for after the release. On a new air jump the owner
 * (AMyCharPlayer::OnAirJumped) plays its air jump montage.
 *
 * Moving bases (the deck of a flying airship): a jump from a pawn that simulates physics stays on that base in the air
 * (bStayOnVehicleInAir), so jumps, air jumps and landings on the deck happen in the ship's frame. Once the
 * character is no longer over the ship the engine gives it the ship's velocity and never takes it off again. Here the
 * landing does: back on a moving base, the velocity becomes the one relative to that base when that is the smaller one
 * (no slide along the deck at the ship's speed; a character that drops onto the deck from outside still sticks as
 * before). The air jump turns only the velocity relative to the base the character left, so it keeps the ship's speed.
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

	// Hanging on a GA_GrappleSwing2 rope gives the air jump back (like landing)
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling|Air Jump")
	bool bAirJumpResetsOnSwing=true;

	// On a GA_GrappleSwing2 rope: its root motion source is in the Swing phase (not the hook flight)
	bool IsOnGrappleRope() const;

	// Air jumps so far on this machine (not counting replays), for debugging and tests
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category="Character Movement: Jumping / Falling|Air Jump")
	int32 AirJumpCount=0;

	// Hover wish of the move being simulated (from the saved move's flags on the server and in replays)
	UPROPERTY(Transient, VisibleInstanceOnly, BlueprintReadOnly, Category="Character Movement: Jumping / Falling|Hover")
	bool bWantsToHover=false;

	/**
	 * A jump from the deck of a vehicle stays on that base in the air (the engine's bStayBasedInAir, set per jump). A
	 * vehicle here is a pawn that simulates physics: the airship (its physics asset bodies and its turrets hang under
	 * the simulating hull). The character keeps moving with the ship and its velocity stays relative to the deck until
	 * it lands or is no longer over the ship (StayBasedInAirHeight, 10 m). Without it the character takes the ship's
	 * velocity and flies beside it in world space: its capsule then sweeps the ship's speed x one frame (1.6 m at
	 * 48 m/s) ahead into the ship, which has not moved yet in that frame, and hits or lands on whatever stands there.
	 * Every other base is left as it was (dropped when the character leaves the ground): the ground, the hex
	 * platforms, and simulating pieces that are not pawns (collapsing bridge parts, which tumble).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Character Movement: Jumping / Falling")
	bool bStayOnVehicleInAir=true;

	/**
	 * The velocity the character got from the moving base it left (the engine adds the base's velocity when a character
	 * jumps or walks off a moving base, such as the deck of a flying airship) and still carries in the air. Zero on the
	 * ground, in the hover, and after leaving a base at rest. The air jump turns only the velocity relative to it.
	 */
	FVector GetCarriedBaseVelocity() const { return CarriedBaseVelocity; }

protected:
	virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;
	virtual void ControlledCharacterMove(const FVector& InputVector, float DeltaSeconds) override;
	// Moving bases (the airship's deck): see CarriedBaseVelocity
	virtual void ApplyImpartedMovementBaseVelocity() override;
	virtual void OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode) override;
	virtual void SetPostLandedPhysics(const FHitResult& Hit) override;

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

	// A new air jump (not a replay) on this move: tell the character once the redirect is done
	bool bPendingAirJumpNotify=false;

	/**
	 * Set when the character leaves a moving base (ApplyImpartedMovementBaseVelocity), cleared when it stops falling.
	 * Not saved with the moves: a replay that starts in the air uses the value of the last simulated move, which is the
	 * same jump unless the character has landed since (then a redirect in that replay is off until the next correction).
	 */
	FVector CarriedBaseVelocity=FVector::ZeroVector;

	void ApplyHover();
	void ApplyAirJumpRedirect();
};
