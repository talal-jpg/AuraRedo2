

#pragma once

#include "CoreMinimal.h"
#include "MyPlayerController.generated.h"

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
	virtual void SetupInputComponent() override;
	
	UPROPERTY(EditAnywhere)
	UInputMappingContext* IMC_PlayerInputMappingContext;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Move;
	
	void Move(const FInputActionValue& Value);

	/**
	 * AutoMove
	 */
	void AutoMove(const FInputActionValue& Value);
	
	FHitResult HitResult;
	FVector CachedLocation;
	float DistThreshold=200.f;
	float MovementSpeed=1000.f;
	
	UPROPERTY()
	USplineComponent* SplineComp;
	
	
	
	void CursorTrace();
	
	IMyHighlightInterface* ThisActor;
	
	IMyHighlightInterface* LastActor;
	
	
	UPROPERTY(EditAnywhere)
	UMyInputConfig* InputConfig;
	
	void PressedFunc(FGameplayTag InputTag);
	void HeldFunc(FGameplayTag InputTag);
	void ReleasedFunc(FGameplayTag InputTag);
	
};
