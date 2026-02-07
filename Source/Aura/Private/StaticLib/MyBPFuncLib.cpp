// Fill out your copyright notice in the Description page of Project Settings.


#include "StaticLib/MyBPFuncLib.h"

#include "GameplayTagsManager.h"
#include "MyPlayerState.h"
#include "UI/WidgetControllers/AttributeMenu/MyAttributeMenuWidgetController.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"

class AMyPlayerState;

void UMyBPFuncLib::GetAttributeMenuWidgetController(UMyOverlayWidgetController* OverlayWidgetController,UObject* WorldContextObject, UMyWidgetController*& OutWidgetController,APlayerController* PlayerController)
{
	if (UMyAttributeMenuWidgetController* MenuWidgetController=OverlayWidgetController->AttributeMenuWidgetController)
	{
		OutWidgetController=MenuWidgetController;
	}
	else
	{
		OutWidgetController=NewObject<UMyAttributeMenuWidgetController>(WorldContextObject);
		AMyPlayerState* MyPlayerState=PlayerController->GetPlayerState<AMyPlayerState>();
		UMyAbilitySystemComponent* ASC= MyPlayerState->MyAbilitySystemComponent;
		UMyAttributeSet* AttributeSet=MyPlayerState->MyAttributeSet;
		
		FWidgetControllerParams WcParams= FWidgetControllerParams(PlayerController,MyPlayerState,ASC,AttributeSet);
		OutWidgetController->SetWidgetControllerParams(WcParams);
	}
}

void UMyBPFuncLib::GetAllGameplayTags(FGameplayTagContainer& OutGameplayTags)
{
	FGameplayTagContainer AllGameplayTags;
	UGameplayTagsManager& TagsManager=UGameplayTagsManager::Get();
	TagsManager.RequestAllGameplayTags(AllGameplayTags,false);
	
	OutGameplayTags=AllGameplayTags;
}
