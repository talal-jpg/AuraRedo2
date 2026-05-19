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
#include "UI/WidgetControllers/SpellMenu/MySpellMenuWidgetController.h"

class UMySpellMenuWidgetController;
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

void UMyBPFuncLib::GetSpellMenuWidgetController(UMyOverlayWidgetController* OverlayWidgetController,
	UObject* WorldContextObject, UMyWidgetController*& OutWidgetController, APlayerController* PlayerController)
{
	if (UMySpellMenuWidgetController* MenuWidgetController=OverlayWidgetController->SpellMenuWidgetController)
	{
		OutWidgetController=MenuWidgetController;
	}
	else
	{
		AMyPlayerState* MyPlayerState=PlayerController->GetPlayerState<AMyPlayerState>();
		TSubclassOf<UMySpellMenuWidgetController> MySpellMenuWCClass=MyPlayerState->MySpellMenuWidgetControllerClass;
		checkf(MySpellMenuWCClass,TEXT("PleaseSetSpellMenuWidgetControllerClassOnPlayerState"));
		UMySpellMenuWidgetController* MySpellMenuWidgetController=NewObject<UMySpellMenuWidgetController>(WorldContextObject,MySpellMenuWCClass);
		UMyAbilitySystemComponent* ASC= MyPlayerState->MyAbilitySystemComponent;
		UMyAttributeSet* AttributeSet=MyPlayerState->MyAttributeSet;
		
		FWidgetControllerParams WcParams= FWidgetControllerParams(PlayerController,MyPlayerState,ASC,AttributeSet);
		MySpellMenuWidgetController->SetWidgetControllerParams(WcParams);
		OutWidgetController=MySpellMenuWidgetController;
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
	
	checkf(EnemyCharClassInfo.PrimaryAttributesEffect != nullptr,TEXT("PleaseFillOutCharacterClassInfo"));
	
	FGameplayEffectSpecHandle GESpecHandlePrimary=MyAbilitySystemComponent->MakeOutgoingSpec(EnemyCharClassInfo.PrimaryAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandlePrimary.Data.Get());
	
	FGameplayEffectSpecHandle GESpecHandleSecondary=MyAbilitySystemComponent->MakeOutgoingSpec(MyGameMode->DA_MyEnemyCharacterClassInfo->SecondaryAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandleSecondary.Data.Get());
	
	FGameplayEffectSpecHandle GESpecHandleVital=MyAbilitySystemComponent->MakeOutgoingSpec(MyGameMode->DA_MyEnemyCharacterClassInfo->VitalAttributesEffect,IN_CharacterLevel,GEContextHandle);
	MyAbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*GESpecHandleVital.Data.Get());
}

void UMyBPFuncLib::SetIsCrit(FGameplayEffectContextHandle& GEContextHandle, bool bIsCrit)
{
	FHitResult NewHit = FHitResult();
	NewHit.bStartPenetrating = true;
	
	GEContextHandle.AddHitResult(NewHit, true);
}

void UMyBPFuncLib::SetIsBlocked(FGameplayEffectContextHandle& GEContextHandle, bool bIsBlocked)
{
		FHitResult NewHit = FHitResult();
		NewHit.bStartPenetrating = true;
	
		GEContextHandle.AddHitResult(NewHit, true);
}

bool UMyBPFuncLib::IsCrit(FGameplayEffectContextHandle& GEContextHandle,UObject* WorldContextObj)
{
	if (GEContextHandle.GetHitResult()==nullptr)return false;
	return GEContextHandle.GetHitResult()->bBlockingHit;
}

bool UMyBPFuncLib::IsBlocked(FGameplayEffectContextHandle& GEContextHandle)
{
	if (GEContextHandle.GetHitResult()==nullptr)return false;
	return GEContextHandle.GetHitResult()->bStartPenetrating;
}

int32 UMyBPFuncLib::GetXPRewardForCharacterClass(ECharacterClass IN_CharacterClass, int32 InLevel, UObject* InWorldContextObject)
{
	AMyGameMode* MyGameMode=Cast<AMyGameMode>(UGameplayStatics::GetGameMode(InWorldContextObject));
	FEnemyCharClassInfo EnemyCharClassInfo = MyGameMode->DA_MyEnemyCharacterClassInfo->GetInfoForClass(IN_CharacterClass);
	
	checkf(EnemyCharClassInfo.XPReward.IsValid(),TEXT("PleaseFillOutCharacterClassInfo"));
	
	return EnemyCharClassInfo.XPReward.GetValueAtLevel(InLevel);
}
