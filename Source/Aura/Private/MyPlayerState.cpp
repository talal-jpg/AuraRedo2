// Fill out your copyright notice in the Description page of Project Settings.


#include "MyPlayerState.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"

AMyPlayerState::AMyPlayerState()
{
	MyAbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("MyAbilitySystemComponent"));
	MyAttributeSet=CreateDefaultSubobject<UMyAttributeSet>(TEXT("MyAttributeSet"));
}
