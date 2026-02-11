// Fill out your copyright notice in the Description page of Project Settings.


#include "StaticLib/MyBPFuncLib.h"

#include "GameplayTagsManager.h"
#include "MyGameMode.h"
#include "MyPlayerState.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"
#include "Kismet/GameplayStatics.h"
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

void UMyBPFuncLib::InitializeEnemyAttributes(ECharacterClass IN_CharacterClass,UMyAbilitySystemComponent* MyAbilitySystemComponent,float IN_CharacterLevel)
{
	AMyGameMode* MyGameMode=Cast<AMyGameMode>(UGameplayStatics::GetGameMode(MyAbilitySystemComponent));
	FEnemyCharClassInfo EnemyCharClassInfo = MyGameMode->DA_MyEnemyCharacterClassInfo->GetInfoForClass(IN_CharacterClass);
	FGameplayEffectContextHandle GEContextHandle = MyAbilitySystemComponent->MakeEffectContext();
	AActor* ASCAvatarActor=MyAbilitySystemComponent->GetAvatarActor();
	GEContextHandle.AddInstigator(ASCAvatarActor,ASCAvatarActor);
	FGameplayEffectSpecHandle GESpecHandlePrimary=MyAbilitySystemComponent->MakeOutgoingSpec(EnemyCharClassInfo.PrimaryAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandlePrimary.Data.Get());
	
	FGameplayEffectSpecHandle GESpecHandleSecondary=MyAbilitySystemComponent->MakeOutgoingSpec(MyGameMode->DA_MyEnemyCharacterClassInfo->SecondaryAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandleSecondary.Data.Get());
	
	FGameplayEffectSpecHandle GESpecHandleVital=MyAbilitySystemComponent->MakeOutgoingSpec(MyGameMode->DA_MyEnemyCharacterClassInfo->VitalAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandleVital.Data.Get());
}
