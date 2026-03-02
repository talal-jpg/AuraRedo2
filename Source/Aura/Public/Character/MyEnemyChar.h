// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyCharBase.h"
#include "Interfaces/MyHighlightInterface.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"
#include "MyEnemyChar.generated.h"

enum class ECharacterClass : uint8;
class UBehaviorTreeComponent;
class UBehaviorTree;
class AMyAiController;
class UWidgetComponent;
class UMyUserWidget;
class UAttributeSet;
class UAbilitySystemComponent;


UCLASS()
class AURA_API AMyEnemyChar : public AMyCharBase , public IMyHighlightInterface
{
	GENERATED_BODY()

public:
	// Sets default values for this character's properties
	AMyEnemyChar();

protected:
	// Called when the game starts or when spawned
	virtual void BeginPlay() override;

public:
	// Called every frame
	virtual void Tick(float DeltaTime) override;

	virtual void PossessedBy(AController* NewController) override;
	
	UPROPERTY(EditAnywhere)
	AMyAiController* MyAiController;
	
	UPROPERTY(EditAnywhere)
	UBehaviorTree* BehaviorTreeAsset;
	
	UPROPERTY(EditAnywhere)
	UMyUserWidget* HealthBar;
	
	UPROPERTY(EditAnywhere)
	UWidgetComponent* HealthBarWidgetComponent;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnHealthChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnMaxHealthChangeDelegate;
	
	
	virtual void Highlight() override;
	
	virtual void UnHighlight() override;
	
	virtual int32 GetCharLevel_Implementation() override;
	
	UPROPERTY(EditAnywhere)
	int32 Level=1;
};
