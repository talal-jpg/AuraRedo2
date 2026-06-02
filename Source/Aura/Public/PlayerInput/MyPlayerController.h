

#pragma once

#include "CoreMinimal.h"
#include "MyPlayerController.generated.h"

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
	
	void Move(const FInputActionValue& Value);

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
	FVector TargetLocation=FVector::ZeroVector;
	
	bool bIsTargeting=false;
	
	UPROPERTY(EditAnywhere ,Category = "Aim")
	float ViewSpan= 270;
	
	void SetAimLocation();
	
	
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
