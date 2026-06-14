

#pragma once

#include "CoreMinimal.h"
#include "MyPlayerController2.generated.h"

class AMyTargetDecalActor;
class UDamageTextWidgetComponent;
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
class AURA_API AMyPlayerController2 : public APlayerController
{
	GENERATED_BODY()
	
public:
	AMyPlayerController2();
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
	
	void Rotate(const FInputActionValue& Value);
	

	/**
	 * AutoMove
	 */
	
	FHitResult HitResult;
	
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
	
	private:
	
	UPROPERTY(EditAnywhere)
	TSubclassOf<UDamageTextWidgetComponent> DamageTextWidgetComponentClass;
	
	
	UPROPERTY(EditAnywhere)
	AMyTargetDecalActor* TargetDecalActor;
	
	UFUNCTION(BlueprintCallable)
	void ShowDamageCircle();
	
	UFUNCTION(BlueprintCallable)
	void HideDamageCircle();
	
	void UpdateDamageCircle();
	
};
