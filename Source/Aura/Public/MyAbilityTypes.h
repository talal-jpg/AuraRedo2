#pragma once

#include "GameplayEffectTypes.h"
#include "MyAbilityTypes.generated.h"

USTRUCT(BlueprintType)
struct FMyGameplayEffectContext : public FGameplayEffectContext
{
	GENERATED_BODY()
	
	
	

public:
	/** Returns the actual struct used for serialization, subclasses must override this! */
	virtual UScriptStruct* GetScriptStruct() const 
	{
		return StaticStruct();
	}

	/** Creates a copy of this context, used to duplicate for later modifications */
	virtual FMyGameplayEffectContext* Duplicate() const 
	{
		FMyGameplayEffectContext* NewContext = new FMyGameplayEffectContext();
		*NewContext = *this;
		if (GetHitResult())
		{
			// Does a deep copy of the hit result
			NewContext->AddHitResult(*GetHitResult(), true);
		}
		return NewContext;
	}
	
protected:
	
};
