// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyEffectActor.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "Kismet/KismetSystemLibrary.h"


// Sets default values
AMyEffectActor::AMyEffectActor()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	bReplicates=true;
}

void AMyEffectActor::OnOverlap(AActor* OverlappingActor)
{
	if (!HasAuthority())return;
	if (ApplicationPolicy==EApplicationPolicy::ApplyOnOverlap)
	{
		if (IAbilitySystemInterface* AbilitySystemIF=Cast<IAbilitySystemInterface>(OverlappingActor))
		{
			UAbilitySystemComponent* ActorAsASC=AbilitySystemIF->GetAbilitySystemComponent();
			if (!ActorAsASC )
			{
				UKismetSystemLibrary::PrintString(GetWorld(),TEXT("Actor does not have AbilitySystemComponent"));
				return;
			}
			FGameplayEffectContextHandle EffectContextHandle=ActorAsASC->MakeEffectContext();

			FGameplayEffectSpecHandle GESpecHandle=ActorAsASC->MakeOutgoingSpec(GameplayEffectClass,ActorLevel,EffectContextHandle);
			FActiveGameplayEffectHandle ActiveGEHandle=ActorAsASC->ApplyGameplayEffectSpecToSelf(*GESpecHandle.Data.Get());

			EGameplayEffectDurationType GEDurationType=GESpecHandle.Data.Get()->Def->DurationPolicy;
		 	
			if (GEDurationType==EGameplayEffectDurationType::Infinite)
			{
			    ActiveGEHandles.Add(ActorAsASC,ActiveGEHandle);
			}
		}
	}
}

void AMyEffectActor::OnEndOverlap(AActor* OverlappingActor)
{
	if (!HasAuthority())return;
	if (RemovalPolicy==ERemovalPolicy::RemoveOnEndOverlap)
	{
		if (IAbilitySystemInterface* AbilitySystemIF=Cast<IAbilitySystemInterface>(OverlappingActor))
		{
			UAbilitySystemComponent* ActorAsASC=AbilitySystemIF->GetAbilitySystemComponent();
			FActiveGameplayEffectHandle* GEHandle=ActiveGEHandles.Find(ActorAsASC);
			ActorAsASC->RemoveActiveGameplayEffect(*GEHandle);
			// check if need to loop over all TMap and remove all effects
		}
	}
}

// Called when the game starts or when spawned
void AMyEffectActor::BeginPlay()
{
	Super::BeginPlay();
}


