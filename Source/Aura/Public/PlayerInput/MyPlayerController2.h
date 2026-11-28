

#pragma once

#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/PlayerController.h"
#include "Match/MyMatchTypes.h"
#include "MyPlayerController2.generated.h"

class UMainMenu;
class UPauseMenu3;
class IMyLobbyPanel;
class UGA_Beam;
class UMaterialInterface;
class UCameraComponent;
class UMaterialInstanceDynamic;
class UMyAbilitySystemComponent;
class AMyTargetDecalActor;
class UDamageTextWidgetComponent;
class UNiagaraDataChannelAsset;
struct FGameplayTag;
class UMyInputConfig;
class USplineComponent;
class IMyHighlightInterface;
struct FInputActionValue;
class UInputMappingContext;
class UInputAction;
struct FHitResult;
struct FMechSentinelDamageEvent;
class UMechSentinelSwarmSubsystem;
/**
 *
 */

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnMenuButtonPressedDelegateSignature, bool, bIsAttribMenuButton);

/** AMyPlayerController2::OnLobbyMessage: a lobby refusal, the zone's "stay in the lobby", a swap notice (SPEC_B_LOBBY 4.8). */
DECLARE_MULTICAST_DELEGATE_OneParam(FOnLobbyMessage, const FText& /*Message*/);

// One damage number for a hit on a Mech Sentinel, sent from the server to the player who dealt it
USTRUCT()
struct FSentinelDamageNumberEntry
{
	GENERATED_BODY()

	// Where the number starts (the hit point plus SentinelDamageNumberHeightOffset)
	UPROPERTY()
	FVector_NetQuantize Location=FVector::ZeroVector;

	// The hit's damage after armor and shield, before the sentinel's health was clamped (like the character numbers)
	UPROPERTY()
	float Damage=0.f;

	// FSentinelDamageNumberEntry::Crit / Blocked bits
	UPROPERTY()
	uint8 Flags=0;

	static constexpr uint8 Crit=1;
	static constexpr uint8 Blocked=2;
};

UCLASS()
class AURA_API AMyPlayerController2 : public APlayerController
{
	GENERATED_BODY()
	
public:
	AMyPlayerController2();
	virtual void Tick(float DeltaTime) override;
	virtual void SetupInputComponent() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UPROPERTY()
	UMyAbilitySystemComponent* MyAbilitySystemComponent;
	
	UMyAbilitySystemComponent* GetMyASC();
	
	UPROPERTY(EditAnywhere)
	UInputMappingContext* IMC_PlayerInputMappingContext;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Move;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Rotate;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Jump;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Q;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_E;
	
	// Opens / closes the Esc menu (UPauseMenu3). Map it to Escape and Gamepad Special Right in the IMC
	UPROPERTY(EditAnywhere, Category="Menu")
	UInputAction* IA_Pause;
	
	// WBP of UPauseMenu3. Empty = no pause menu
	UPROPERTY(EditAnywhere, Category="Menu")
	TSubclassOf<UPauseMenu3> PauseMenuClass;
	
	// Esc. In the lobby (with the pause menu closed) it opens / closes the registered lobby panel instead (SPEC_B_LOBBY 6.1)
	UFUNCTION(BlueprintCallable, Category="Menu")
	void TogglePauseMenu();
	
	// Opens the pause menu (the lobby panel's MENU button). Local controllers only
	UFUNCTION(BlueprintCallable, Category="Menu")
	void OpenPauseMenu();
	
	UFUNCTION(BlueprintPure, Category="Menu")
	bool IsPauseMenuOpen() const;
	
	// Opens the pause menu on its Leave Session confirm (the lobby panel's LEAVE), so the host-left kick stays in one place
	void OpenLeaveSessionConfirm();
	
	// -------------------------------------------------------------------------
	// Lobby (Docs/Airship/round2/SPEC_B_LOBBY.md 4.8): the lobby widget's requests. All Server, Reliable, checked on the
	// server (AMyGameMode); the host-only ones refuse everybody else. A refusal (or a pending swap) answers with
	// ClientLobbyMessage. On a listen server the host's own calls run locally, so his widget takes the same route.
	// -------------------------------------------------------------------------
	
	/** A client's ready flag (the host has none). */
	UFUNCTION(Server, Reliable)
	void ServerLobbySetReady(bool bReady);
	
	/** Ask for a team: a move when the teams stay within one, a swap with a player who asked for the opposite, else pending. 255 (or the own team) cancels a request. */
	UFUNCTION(Server, Reliable)
	void ServerLobbyRequestTeam(uint8 TeamId);
	
	/** Host: the rules and Max Players (AMyGameMode::ApplyLobbyRules). The widget sends one 0.75 s after the last edit. */
	UFUNCTION(Server, Reliable)
	void ServerLobbySetRules(const FMyMatchRules& Rules, int32 MaxPlayers);
	
	/** Host: start the lobby countdown. bForce = the second click (soft blocks ignored). */
	UFUNCTION(Server, Reliable)
	void ServerLobbyStart(bool bForce);
	
	/** Host: cancel the lobby countdown. */
	UFUNCTION(Server, Reliable)
	void ServerLobbyCancelStart();
	
	/** Host: move TargetPlayer to TeamId (a swap with one of that team when it is full). (Not "Player": UHT refuses a name APlayerController has.) */
	UFUNCTION(Server, Reliable)
	void ServerLobbyMovePlayer(APlayerState* TargetPlayer, uint8 TeamId);
	
	/** Server -> this player: a lobby message (logged on the receiving machine, then OnLobbyMessage). Reliable: refusals and
	 *  the pending-swap notice are the only answer a request gets, and they are rare (player actions, the zone's put-back). */
	UFUNCTION(Client, Reliable)
	void ClientLobbyMessage(const FText& Text);
	
	/** Local machine: every ClientLobbyMessage (the lobby widget shows it for 3 s). */
	FOnLobbyMessage OnLobbyMessage;
	
	/** The lobby widget registers itself (an IMyLobbyPanel) in NativeConstruct, null in NativeDestruct. */
	void SetLobbyPanel(UObject* Panel);
	
	/** The registered lobby panel, or null (no lobby widget: Esc opens the pause menu). */
	IMyLobbyPanel* GetLobbyPanel() const;
	
	UPROPERTY(BlueprintReadOnly)
	FVector2D FlyBoostingMoveInput=FVector2D::ZeroVector;
	
	void Move(const FInputActionValue& Value);
	void MoveCompleted(const FInputActionValue& Value);
	
	void Rotate(const FInputActionValue& Value);
	
	void Jump(const FInputActionValue& Value);
	
	UPROPERTY(BlueprintAssignable)
	FOnMenuButtonPressedDelegateSignature OnMenuButtonPressedDelegate;
	
	void MenuButtonPressed(bool bIsAttribMenuButton);
	
	void SpellMenuButtonPressed(bool bIsAttribMenuButton);

	/**
	 * AutoMove
	 */
	
	FHitResult HitResult;
	
	FHitResult HitResultLineTrace;
	
	void CursorTrace();
	
	IMyHighlightInterface* ThisActor;
	
	IMyHighlightInterface* LastActor;
	
	//AutoMoveEnd
	
	
	// AimRot&Location
	UPROPERTY(BlueprintReadOnly)
	FVector ControlRotForwardVec= GetControlRotation().Vector();
	
	UPROPERTY(BlueprintReadOnly)
	float YawDelta=0;
	
	UPROPERTY(BlueprintReadOnly)
	FVector RotChest= GetControlRotation().Vector();
	
	UPROPERTY(BlueprintReadOnly)
	FVector RotFeet= RotChest;
	
	void LerpChestRotToRot();
	
	void LerpFeetRotToRot();
	
	//World location where bullet would hit
	UPROPERTY(BlueprintReadOnly)
	FVector TargetLocation=FVector::ZeroVector;
	
	bool bIsTargeting=false;
	
	UPROPERTY(EditAnywhere ,Category = "Aim")
	float ViewSpan=270; 
	
	bool bShouldRotate=false;
	
	bool bShouldRotateQ=false;
	
	// AimLocation
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<AMyTargetDecalActor> TargetDecalActorClass;
	
	
	UPROPERTY(EditAnywhere)
	UMyInputConfig* InputConfig;
	
	void PressedFunc(FGameplayTag InputTag);
	void HeldFunc(FGameplayTag InputTag);
	void ReleasedFunc(FGameplayTag InputTag);
	
	UFUNCTION(Client,Reliable)
	void ShowDamageNumber(float InDamage,ACharacter* TargetCharacter,bool bIsCrit,bool bIsBlocked);
	
	// Niagara version: writes one entry to DamageNumberDataChannel, NS_DamageNumbers reads it and draws the number
	UFUNCTION(Client,Reliable)
	void ShowDamageNumber_2(float InDamage,ACharacter* TargetCharacter,bool bIsCrit,bool bIsBlocked);
	
	// When true MyAttributeSet calls ShowDamageNumber_2 (Niagara), otherwise the widget based ShowDamageNumber
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	bool bUseNiagaraDamageNumbers=true;

	// Mech Sentinel hits this player dealt, batched by the server once per frame; drawn through DamageNumberDataChannel like ShowDamageNumber_2.
	// Unreliable: the numbers are cosmetic and one shot can hit several sentinels
	UFUNCTION(Client,Unreliable)
	void Client_ShowSentinelDamageNumbers(const TArray<FSentinelDamageNumberEntry>& Numbers);

	// Damage numbers for Mech Sentinel hits (Niagara only, sentinels have no actor for the widget version)
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	bool bShowSentinelDamageNumbers=true;

	// Height above the hit point where a sentinel's number starts (the sentinel hit capsule's half height is 140)
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	float SentinelDamageNumberHeightOffset=100.f;

	// Server side cap per frame and player, extra numbers that frame are dropped
	UPROPERTY(EditAnywhere,Category="DamageNumbers",meta=(ClampMin="1"))
	int32 MaxSentinelDamageNumbersPerFrame=32;

	// Sent by UGA_Beam to the player the beam hit (bCaster false) or to the player who cast it (bCaster true), settings come from BeamClass's defaults
	UFUNCTION(Client,Reliable)
	void Client_PlayBeamImpact(TSubclassOf<UGA_Beam> BeamClass,bool bCaster);
	
	// Puts an instance of Material on the pawn's camera with ImpactTime=now and Duration, and kicks the FOV by FOVOffset easing back over Duration
	void StartHitImpact(UMaterialInterface* Material,float Duration,float FOVOffset);
	
	// Client side: when the last impact started playing. Server side: when the last impact RPC was sent to this player
	float LastHitImpactStartTime=-1000.f;
	float LastHitImpactSentTime=-1000.f;
	float LastCastImpactStartTime=-1000.f;
	float LastCastImpactSentTime=-1000.f;
	
	// Sent by AGameSession::KickPlayer. Keeps the reason for the main menu and goes back to it
	virtual void ClientWasKicked_Implementation(const FText& KickReason) override;
	
	// Server, the controller is going away (logout, disconnect). The engine destroys the possessed pawn: a pilot's pawn is
	// his team's ship, which would cost the team a ship for a disconnect. A team ship is given back unpiloted instead (it
	// cruises or holds) and only the pilot's character goes (SPEC_B B1.4). Free ships: the engine's (PR A)
	virtual void PawnLeavingGame() override;
	
	private:
	
	UPROPERTY()
	TObjectPtr<UPauseMenu3> PauseMenu;
	
	// SetLobbyPanel's widget (an IMyLobbyPanel)
	TWeakObjectPtr<UObject> LobbyPanel;
	
	// Creates PauseMenu on first use; false without PauseMenuClass
	bool EnsurePauseMenu();
	
	// Options > Gameplay > Field of View, added on top of the camera's own FOV like the hit impact kick
	void TickFieldOfViewSetting();
	// Options > Accessibility > Screen Shake turns the camera shake modifier off
	void TickScreenShakeSetting();
	TWeakObjectPtr<APawn> FOVSettingPawn;
	TWeakObjectPtr<UCameraComponent> FOVSettingCamera;
	float AppliedFOVSettingDelta=0.f;
	
	void TickHitImpact(float DeltaTime);
	void StopHitImpact();
	
	UPROPERTY()
	TObjectPtr<UCameraComponent> HitImpactCamera;
	
	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> HitImpactMID;
	
	// Character meshes we turned custom depth on for, so the material can mask characters out. Turned back off in StopHitImpact
	UPROPERTY()
	TArray<TObjectPtr<UPrimitiveComponent>> HitImpactCustomDepthMeshes;
	
	float HitImpactFOVOffset=0.f;
	float HitImpactDuration=0.f;
	// World time of the hit, the same clock as the material's Time node, so pausing holds both
	double HitImpactStartWorldTime=0.0;
	// FOV currently added to the camera, removed again before applying the next frame's offset so other FOV changes are kept
	float HitImpactAppliedFOV=0.f;
	bool bHitImpactActive=false;
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UDamageTextWidgetComponent> DamageTextWidgetComponentClass;
	
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	TObjectPtr<UNiagaraDataChannelAsset> DamageNumberDataChannel;
	
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	FLinearColor NormalDamageColor=FLinearColor(1.f,1.f,1.f,1.f);
	
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	FLinearColor CritDamageColor=FLinearColor(1.f,0.25f,0.05f,1.f);
	
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	FLinearColor BlockedDamageColor=FLinearColor(0.3f,0.6f,1.f,1.f);
	
	// Number size in Niagara, crits get CritDamageScale times this
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	float DamageNumberSize=1.f;
	
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	float CritDamageScale=1.5f;
	
	// Extra height above the capsule top where the number starts
	UPROPERTY(EditAnywhere,Category="DamageNumbers")
	float DamageNumberHeightOffset=20.f;

	// Writes one entry to DamageNumberDataChannel (local only). Used by ShowDamageNumber_2 and Client_ShowSentinelDamageNumbers;
	// DebugSource names the writer in Niagara's data channel debugging
	void WriteDamageNumber(const FVector& Location,float InDamage,bool bIsCrit,bool bIsBlocked,const TCHAR* DebugSource);
	
	// Server: UMechSentinelSwarmSubsystem::OnSentinelDamagedNative, queues the hits this player dealt
	void HandleSentinelDamaged(const FMechSentinelDamageEvent& Event);
	
	// Server, next tick after the first queued hit: sends the queued sentinel numbers in one Client_ShowSentinelDamageNumbers
	void FlushSentinelDamageNumbers();
	
	// True when DamageInstigator is this controller or owned by it (its player state, its pawn, actors they own)
	bool IsSentinelDamageInstigator(const AActor* DamageInstigator) const;
	
	TArray<FSentinelDamageNumberEntry> PendingSentinelDamageNumbers;
	FTimerHandle SentinelDamageNumberFlushTimer;
	FDelegateHandle SentinelDamagedHandle;
	TWeakObjectPtr<UMechSentinelSwarmSubsystem> SentinelDamageSwarm;

	
	UPROPERTY(EditAnywhere)
	AMyTargetDecalActor* TargetDecalActor;
	
	UFUNCTION(BlueprintCallable)
	void ShowDamageCircle();
	
	UFUNCTION(BlueprintCallable)
	void HideDamageCircle();
	
	void UpdateDamageCircle();
	
	UFUNCTION(Exec)
	void JoinSessionButtonWrapper();
	
	UPROPERTY(EditAnywhere)
	UMainMenu* MainMenu;
	
};
