

#pragma once

#include "CoreMinimal.h"
#include "MyPlayerController.generated.h"

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
	virtual void SetupInputComponent() override;
	
	UPROPERTY(EditAnywhere)
	UInputMappingContext* IMC_PlayerInputMappingContext;
	
	UPROPERTY(EditAnywhere)
	UInputAction* IA_Move;
	
	void Move(const FInputActionValue& Value);
	
	
};
