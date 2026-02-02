// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyEnemyChar.h"

#include "AbilitySystem/MyAbilitySystemComponent.h"


// Sets default values
AMyEnemyChar::AMyEnemyChar()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	AbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet=CreateDefaultSubobject<UAttributeSet>(TEXT("AttributeSet"));
	
}

// Called when the game starts or when spawned
void AMyEnemyChar::BeginPlay()
{
	Super::BeginPlay();
	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->InitAbilityActorInfo(this, this);
	}
}

// Called every frame
void AMyEnemyChar::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
}

// Called to bind functionality to input
void AMyEnemyChar::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
}

