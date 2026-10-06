

#pragma once

#include "CoreMinimal.h"
#include "MyPlayerController.generated.h"

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
/**
 * 
 */
UCLASS()
class AURA_API AMyPlayerController : public APlayerController
{
	GENERATED_BODY()
	
public:
	AMyPlayerController();
	virtual void Tick(float DeltaTime) override;
	virtual void SetupInputComponent() override;
	virtual void BeginPlay() override;
	
	UPROPERTY(EditAnywhere)
	UInputMappingContext* IMC_PlayerInputMappingContext;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Move;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Rotate;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Q;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_E;
	
	void Move(const FInputActionValue& Value);
	
	void RotateLeft(const FInputActionValue& Value);
	void RotateRight(const FInputActionValue& Value);
	

	/**
	 * AutoMove
	 */
	void AutoMove();
	
	FHitResult HitResult;
	
	FVector CachedLocation;
	
	UPROPERTY(EditAnywhere)
	float DistThreshold=500.f;
	float MovementSpeed=100.f;
	float PressedTime=0.f;
	float PressedTimeThreshold=2.2f;
	bool bIsAutoRunning=false;
	
	UPROPERTY()
	USplineComponent* SplineComp;
	
	void CursorTrace();
	
	IMyHighlightInterface* ThisActor;
	
	IMyHighlightInterface* LastActor;
	
	//AutoMoveEnd
	
	
	// AimLocation
	
	UPROPERTY(BlueprintReadOnly)
	FVector AimLocation=FVector::ZeroVector;
	
	UPROPERTY(BlueprintReadOnly)
	FVector2D TargetLocation=FVector2D::ZeroVector;
	
	bool bIsTargeting=false;
	
	UPROPERTY(EditAnywhere ,Category = "Aim")
	float ViewSpan=270; 
	
	void SetAimLocation();
	
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
	
	private:
	
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
	
	
	UPROPERTY(EditAnywhere)
	AMyTargetDecalActor* TargetDecalActor;
	
	UFUNCTION(BlueprintCallable)
	void ShowDamageCircle();
	
	UFUNCTION(BlueprintCallable)
	void HideDamageCircle();
	
	void UpdateDamageCircle();
	
};
