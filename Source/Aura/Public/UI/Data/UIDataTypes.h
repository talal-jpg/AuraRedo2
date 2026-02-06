#pragma once
#include "GameDelegates.h"
#include "GameplayTagContainer.h"
#include "UIDataTypes.generated.h"

class UMyUserWidget;

USTRUCT(BlueprintType,Blueprintable)
struct FPopupWidgetInfo : public FTableRowBase
{
	GENERATED_BODY()
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FGameplayTag MessageTag;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	UTexture2D* MessageImage;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	FText Message;
	
	UPROPERTY(EditAnywhere,BlueprintReadWrite)
	TSubclassOf<UMyUserWidget> PopupWidgetClass;
	
};