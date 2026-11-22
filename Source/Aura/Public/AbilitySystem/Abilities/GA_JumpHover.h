// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyGameplayAbility.h"
#include "Engine/TimerHandle.h"
#include "GA_JumpHover.generated.h"

class ACharacter;
class UMyCharacterMovementComponent;

/**
 * Jump, air jump and hover on one button (Input.Space).
 *
 * Each press does what fits the current movement:
 *  - on the ground: jump
 *  - in the air with the air jump left: air jump. UMyCharacterMovementComponent turns the velocity toward the movement
 *    input. It also works once when falling without a first jump (walked off a ledge)
 *  - in the air with the air jump used: hover (MOVE_Flying), paying CostGameplayEffectClass every HoverCostInterval
 *  - while hovering: drop out of the hover (falling). A later press hovers again; the air jump comes back on landing
 * One activation lasts until the character lands (or until the button is released, if it is still held on landing),
 * so holding the button never repeats a jump or starts a hover on its own.
 *
 * Multiplayer: Local Predicted. The owning client decides every press. Both the jumps (Character::Jump, JumpMaxCount 2
 * on AMyCharPlayer) and the hover wish (UMyCharacterMovementComponent, FLAG_Custom_0) travel in the character's move
 * stream, so the server simulates them on the same moves and replays after a correction redo them. The server copy
 * of the activation only charges the mana; when it can't, it tells the owning client to drop out (GameCustom1).
 */
UCLASS()
class AURA_API UGA_JumpHover : public UMyGameplayAbility
{
	GENERATED_BODY()

public:
	UGA_JumpHover();

	// Seconds between two payments of CostGameplayEffectClass while hovering. Jumping costs nothing
	UPROPERTY(EditDefaultsOnly, Category="Hover", meta=(ClampMin="0.01", ForceUnits="s"))
	float HoverCostInterval=0.1f;

	// The hover ends (falling) when CostGameplayEffectClass can't be paid
	UPROPERTY(EditDefaultsOnly, Category="Hover")
	bool bEndHoverWhenOutOfMana=true;

	// After a ground jump: still on the ground this many seconds later (the jump was blocked) ends the activation
	UPROPERTY(EditDefaultsOnly, Category="Jump", meta=(ClampMin="0.05", ForceUnits="s"))
	float GroundJumpCheckDelay=0.3f;

	// Hovering on this machine: the owning client's / host's request, or what the server copy last saw in the moves
	UPROPERTY(Transient, BlueprintReadOnly, Category="JumpHover")
	bool bHovering=false;

	// Presses handled by this activation (owning client)
	UPROPERTY(Transient, BlueprintReadOnly, Category="JumpHover")
	int32 PressCount=0;

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	// Later presses while active (owning client only, from AbilitySpecInputPressed)
	virtual void InputPressed(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) override;

	virtual void InputReleased(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) override;

	// Activating is free: CostGameplayEffectClass is the hover's cost, paid while hovering (CanPayHoverCost, HoverCostTick)
	virtual bool CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, FGameplayTagContainer* OptionalRelevantTags = nullptr) const override;

private:
	enum class EJumpHoverAction : uint8
	{
		None,
		Jump,
		AirJump,
		StartHover,
		StopHover,
	};

	ACharacter* GetCharacter() const;
	UMyCharacterMovementComponent* GetMovement() const;

	// Owning client / listen host: what this press does
	EJumpHoverAction ChooseAction() const;
	void HandlePress();

	// Owning client / listen host: ask the movement component for the hover (applied from the next move on)
	void SetHover(bool bOn);

	bool CanPayHoverCost() const;
	// Server (and listen host): pays the hover while the movement component hovers
	void HoverCostTick();
	// Owning client: the server ran out of mana for the hover
	void OnServerStopHover();

	// Owning client / listen host: landing ends the activation
	void LandingCheckTick();
	// Owning client: end now, or when the button is released if it is still held
	void FinishWhenReleased();

	FTimerHandle HoverCostTimerHandle;
	FTimerHandle LandingCheckTimerHandle;
	FDelegateHandle ServerStopHoverHandle;
	double LastGroundJumpTime=-1.0;
	bool bLeftGround=false;
	bool bEndWhenReleased=false;
	// Server: the stop has been sent for the current hover
	bool bServerStopSent=false;
};
