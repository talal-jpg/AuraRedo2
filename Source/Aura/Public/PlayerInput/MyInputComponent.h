// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EnhancedInputComponent.h"
#include "Data/MyInputConfig.h"
#include "MyInputComponent.generated.h"



UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class AURA_API UMyInputComponent : public UEnhancedInputComponent
{
	GENERATED_BODY()

public:
	// Sets default values for this component's properties
	UMyInputComponent();

protected:
	// Called when the game starts
	virtual void BeginPlay() override;

public:
	// Called every frame
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
	                           FActorComponentTickFunction* ThisTickFunction) override;
	
	template<class UserClass,typename PressedFuncType,typename HeldFuncType,typename ReleasedFuncType>
	void BindAbilityAction(UMyInputConfig* InputConfig, UserClass Class, PressedFuncType PressedFunc, HeldFuncType HeldFunc,ReleasedFuncType ReleasedFunc)
	{
		if (!InputConfig)return;
		for (FInputConfig Input: InputConfig)
		{
			if (PressedFunc)
			{
				BindAction(Input.InputAction, ETriggerEvent::Started,Class,PressedFunc,Input.InputTag);
			}
			if (HeldFunc)
			{
				BindAction(Input.InputAction, ETriggerEvent::Triggered,Class,HeldFunc,Input.InputTag);
			}
			if (ReleasedFunc)
			{
				BindAction(Input.InputAction, ETriggerEvent::Completed,Class,ReleasedFunc,Input.InputTag);
			}
		}
	}
};
