// Fill out your copyright notice in the Description page of Project Settings.


#include "MyPlayerState.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Net/UnrealNetwork.h"

UAbilitySystemComponent* AMyPlayerState::GetAbilitySystemComponent() const
{
	return MyAbilitySystemComponent;
}

void AMyPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AMyPlayerState,Level);
	DOREPLIFETIME(AMyPlayerState,XP);
	DOREPLIFETIME(AMyPlayerState,AttributePoints);
	DOREPLIFETIME(AMyPlayerState,SpellPoints);
	
}

AMyPlayerState::AMyPlayerState()
{
	MyAbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("MyAbilitySystemComponent"));
	MyAttributeSet=CreateDefaultSubobject<UMyAttributeSet>(TEXT("MyAttributeSet"));
	
	MyAbilitySystemComponent->SetIsReplicated(true);
	MyAbilitySystemComponent->SetReplicationMode(EGameplayEffectReplicationMode::Mixed);
	SetNetUpdateFrequency(100.f);
}

void AMyPlayerState::AddToXP(int32 InXP)
{
	XP+=InXP;
}

void AMyPlayerState::AddToLevel(int32 InLevel)
{
	Level+=InLevel;
}

void AMyPlayerState::AddToAttributePoints(int32 InAttributePoints)
{
	AttributePoints+=InAttributePoints;
}

void AMyPlayerState::AddToSpellPoints(int32 InSpellPoints)
{
	SpellPoints+=InSpellPoints;
}

void AMyPlayerState::SetLevel(int32 InLevel)
{
	Level=InLevel;
}

void AMyPlayerState::SetXP(int32 InXP)
{
	XP=InXP;
}

void AMyPlayerState::SetAttributePoints(int32 InAttributePoints)
{
	AttributePoints=InAttributePoints;
}

void AMyPlayerState::SetSpellPoints(int32 InSpellPoints)
{
	SpellPoints=InSpellPoints;
}

void AMyPlayerState::OnRep_Level(int32 OldLevel)
{
}

void AMyPlayerState::OnRep_XP(int32 OldXP)
{
}

void AMyPlayerState::OnRep_AttributePoints(int32 OldAttributePoints)
{
}

void AMyPlayerState::OnRep_SpellPoints(int32 OldSpellPoints)
{
}
