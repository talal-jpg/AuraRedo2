// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyEnemyChar.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "Components/WidgetComponent.h"
#include "Kismet/KismetSystemLibrary.h"
#include "StaticLib/MyBPFuncLib.h"
#include "UI/UserWidgets/MyUserWidget.h"


// Sets default values
AMyEnemyChar::AMyEnemyChar()
{
	// Set this character to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	MyAbilitySystemComponent=CreateDefaultSubobject<UMyAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	MyAttributeSet=CreateDefaultSubobject<UMyAttributeSet>(TEXT("AttributeSet"));
	HealthBarWidgetComponent=CreateDefaultSubobject<UWidgetComponent>(TEXT("HealthBar"));
	HealthBarWidgetComponent->SetupAttachment(GetRootComponent());
}

// Called when the game starts or when spawned
void AMyEnemyChar::BeginPlay()
{
	Super::BeginPlay();
	if (MyAbilitySystemComponent)
	{
		MyAbilitySystemComponent->InitAbilityActorInfo(this, this);
		GiveStartupAbilities();
		//InitAttrToBeCalledInBPCharClassToBeDifferentForEachEnemy
	}
	HealthBar=Cast<UMyUserWidget>(HealthBarWidgetComponent->GetUserWidgetObject());
	HealthBar->SetWidgetController(this);
	
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetHealthAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
		{
			OnHealthChangeDelegate.Broadcast(Data.NewValue);
		}
	);
	MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(MyAttributeSet->GetMaxHealthAttribute()).AddLambda(
		[this](const FOnAttributeChangeData& Data)
			{
				OnMaxHealthChangeDelegate.Broadcast(Data.NewValue);
			}
	);
	
	OnHealthChangeDelegate.Broadcast(MyAttributeSet->GetHealth());
	OnMaxHealthChangeDelegate.Broadcast(MyAttributeSet->GetMaxHealth());
}

// Called every frame
void AMyEnemyChar::Tick(float DeltaTime)
{
	// for (auto Ability:MyAbilitySystemComponent->GetActivatableAbilities())
	// {
	// 	UKismetSystemLibrary::PrintString(this,Ability.GetDebugString());
	// }
}

void AMyEnemyChar::Highlight()
{
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Highlighted"));
	GetMesh()->SetCustomDepthStencilValue(100);
 }

void AMyEnemyChar::UnHighlight()
{
	GetMesh()->SetCustomDepthStencilValue(0);
	
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("UnHighlighted"));
}

