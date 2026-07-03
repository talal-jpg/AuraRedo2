// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_GunShoot.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "NiagaraDataChannel.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Character/MyCharBase.h"
#include "Kismet/KismetSystemLibrary.h"
#include "PlayerInput/MyPlayerController2.h"

void UGA_GunShoot::MyFunc(FVector InImpactPoint,AActor* InTargetActor)
{
		if (AMyCharBase* TargetActor=Cast<AMyCharBase>(InTargetActor))
		{
			// FVector LaunchVel=(TargetActor->GetActorLocation()- InImpactPoint).GetSafeNormal();
			// UKismetSystemLibrary::DrawDebugArrow(InTargetActor,TargetActor->GetActorLocation(),TargetActor->GetActorLocation()+LaunchVel*500,100,FLinearColor::Black,30);
			// LaunchVel*=100;
			// TargetActor->LaunchCharacter(LaunchVel,false,false);
			if (IAbilitySystemInterface* AscIF=Cast<IAbilitySystemInterface>(TargetActor))
			{
				FString Name=TargetActor->GetName();
				UKismetSystemLibrary::PrintString(this,TEXT("HitActor: ") + Name);
				TargetAsc=AscIF->GetAbilitySystemComponent();
				
				
				
				//Make GESpec With Own ASC
				UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
				// UMyAttributeSet* MyAttributeSet=Cast<AMyCharBase>(GetAvatarActorFromActorInfo())->GetMyAttributeSet();
				UMyAttributeSet* TargetAttributeSet=Cast<AMyCharBase>(InTargetActor)->GetMyAttributeSet();
				if (!TargetAttributeSet)return;
				FGameplayEffectContextHandle GEContext=ASC->MakeEffectContext();
				FGameplayEffectSpecHandle GESpecHandle=ASC->MakeOutgoingSpec(DamageEffectClass,1,GEContext);
				//TODO Replace by AttackDamage When add and figure out attrs
				// float Magnitude=MyAttributeSet->GetStrength();
				float Magnitude=1;
				UAbilitySystemBlueprintLibrary::AssignTagSetByCallerMagnitude(GESpecHandle,MyTags::SetDamageByCaller,Magnitude);
				
				float IncomingDamage= TargetAttributeSet->GetIncomingDamage();
				float PrevHealth=TargetAttributeSet->GetHealth();
				ASC->ApplyGameplayEffectSpecToTarget(*GESpecHandle.Data.Get(),TargetAsc);
				float NewHealth=TargetAttributeSet->GetHealth();
				UKismetSystemLibrary::PrintString(this,TEXT("PrevHealth: ") + FString::FromInt(PrevHealth));
				UKismetSystemLibrary::PrintString(this,TEXT("NewHealth: ") + FString::FromInt(NewHealth));
				UKismetSystemLibrary::PrintString(this,TEXT("IncomingDamage: ") + FString::FromInt(IncomingDamage));
				
				
			}
		}
			//TODO Write to NiagarDC from here remove getting controller in bp
			//UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel()
}
