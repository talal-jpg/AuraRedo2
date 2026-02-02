// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "MyPlayerState.generated.h"

class UAttributeSet;
class UAbilitySystemComponent;
/**
 * 
 */
UCLASS()
class AURA_API AMyPlayerState : public APlayerState
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY()
	UAbilitySystemComponent* AbilitySystemComponent;
	
	UPROPERTY()
	UAttributeSet* AttributeSet;
	
	AMyPlayerState();
	
};
