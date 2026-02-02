// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "MyHighlightInterface.generated.h"

// This class does not need to be modified.
UINTERFACE(MinimalAPI)
class UMyHighlightInterface : public UInterface
{
	GENERATED_BODY()
};

/**
 * 
 */
class AURA_API IMyHighlightInterface
{
	GENERATED_BODY()

	// Add interface functions to this class. This is the class that will be inherited to implement this interface.
public:
	virtual void Highlight()=0;
	virtual void UnHighlight()=0;
};
