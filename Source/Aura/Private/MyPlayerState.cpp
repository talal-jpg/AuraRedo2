// Fill out your copyright notice in the Description page of Project Settings.


#include "MyPlayerState.h"

#include <string>

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Net/UnrealNetwork.h"

void AMyPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,XP,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,Level,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,AttributePoints,COND_None,REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(AMyPlayerState,SpellPoints,COND_None,REPNOTIFY_Always);
}

void AMyPlayerState::AddToXP(int32 InXP)
{
	XP+=InXP;
	OnXPChangedDelegate.Broadcast(XP);
}

void AMyPlayerState::AddToLevel(int32 InLevels)
{
	Level+=InLevels;
	OnLevelChangedDelegate.Broadcast(Level);
}

void AMyPlayerState::AddToAttributePoints(int32 InAttributePoints)
{
	AttributePoints+=InAttributePoints;
	OnAttribPointsChangedDelegate.Broadcast(AttributePoints);
}

void AMyPlayerState::AddToSpellPoints(int32 InSpellPoints)
{
	SpellPoints+=InSpellPoints;
	OnSpellPointsChangedDelegate.Broadcast(SpellPoints);
}

void AMyPlayerState::OnRep_XP(int32 OldXP)
{
	OnXPChangedDelegate.Broadcast(XP);
}

void AMyPlayerState::OnRep_Level(int32 OldLevel)
{
	OnLevelChangedDelegate.Broadcast(Level);
}

void AMyPlayerState::OnRep_AttributePoints(int32 OldAttributePoints)
{
	OnAttribPointsChangedDelegate.Broadcast(AttributePoints);
}

void AMyPlayerState::OnRep_SpellPoints(int32 OldSpellPoints)
{
	OnSpellPointsChangedDelegate.Broadcast(SpellPoints);
}

AMyPlayerState::AMyPlayerState()
{
	MyAbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("MyAbilitySystemComponent"));
	MyAttributeSet=CreateDefaultSubobject<UMyAttributeSet>(TEXT("MyAttributeSet"));
}

