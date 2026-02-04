// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "MyPlayerState.generated.h"

class UMyAttributeSet;
class UMyAbilitySystemComponent;
/**
 * 
 */
UCLASS()
class AURA_API AMyPlayerState : public APlayerState
{
	GENERATED_BODY()
	
public:
	
	UPROPERTY()
	UMyAbilitySystemComponent* AbilitySystemComponent;
	
	UPROPERTY()
	UMyAttributeSet* AttributeSet;
	
	AMyPlayerState();
	
};
