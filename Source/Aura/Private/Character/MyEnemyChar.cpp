// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyEnemyChar.h"

#include "MyAiController.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/DA_MyEnemyCharacterClassInfo.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BehaviorTreeComponent.h"
#include "BehaviorTree/BlackboardComponent.h"
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

void AMyEnemyChar::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (!HasAuthority())return;
	MyAiController=Cast<AMyAiController>(NewController);
	MyAiController->BehaviorTree->GetBlackboardComponent()->InitializeBlackboard(*BehaviorTreeAsset->BlackboardAsset);
	MyAiController->RunBehaviorTree(BehaviorTreeAsset);
	MyAiController->BehaviorTree->GetBlackboardComponent()->SetValueAsObject(FName("SelfActor"),this);
	MyAiController->BehaviorTree->GetBlackboardComponent()->SetValueAsBool(FName("bIsRanged"),CharacterClass==ECharacterClass::Warrior? false:true);
	// UKismetSystemLibrary::PrintString(this,(CharacterClass==ECharacterClass::Warrior?"Melee":"Ranged"),true,true,FLinearColor::Green,30);
	
	MyAiController->BehaviorTree->GetBlackboardComponent()->SetValueAsBool(FName("bIsHitReacting"),MyAbilitySystemComponent->GetOwnedGameplayTags().HasTagExact(MyTags::Event_HitReact));
	
	MyAbilitySystemComponent->RegisterGameplayTagEvent(MyTags::Event_HitReact,EGameplayTagEventType::NewOrRemoved).AddLambda(
		[this](const FGameplayTag Tag, int32 Count)
		{
			MyAiController->GetBlackboardComponent()->SetValueAsBool(FName("bIsHitReacting"),Count>0);
			// UKismetSystemLibrary::PrintString(this,FString::Printf(TEXT("HitReact Count: %d"),Count));
		}
	);
}

void AMyEnemyChar::Highlight()
{
	GetMesh()->SetCustomDepthStencilValue(100);
	// MyAiController->BehaviorTree->GetBlackboardComponent()->SetValueAsVector(FName("GoToLoc"),GetActorLocation()+FVector(200,0,0));
 }

void AMyEnemyChar::UnHighlight()
{
	GetMesh()->SetCustomDepthStencilValue(0);
	
	// UKismetSystemLibrary::PrintString(GetWorld(),TEXT("UnHighlighted"));
}

int32 AMyEnemyChar::GetCharLevel()
{
	return Level;
}

