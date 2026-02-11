// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MyCharBase.h"
#include "UI/WidgetControllers/Overlay/MyOverlayWidgetController.h"
#include "MyEnemyChar.generated.h"

class UWidgetComponent;
class UMyUserWidget;
class UAttributeSet;
class UAbilitySystemComponent;


UCLASS()
class AURA_API AMyEnemyChar : public AMyCharBase
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

	
	UPROPERTY(EditAnywhere)
	UMyUserWidget* HealthBar;
	
	UPROPERTY(EditAnywhere)
	UWidgetComponent* HealthBarWidgetComponent;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnHealthChangeDelegate;
	
	UPROPERTY(BlueprintAssignable)
	FOnAttribChangeDelegateSignature OnMaxHealthChangeDelegate;
};
