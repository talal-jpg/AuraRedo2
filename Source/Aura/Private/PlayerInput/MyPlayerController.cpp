// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController.h"

#include <string>

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "MyPlayerState.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Actors/MyTargetDecalActor.h"
#include "Character/MyCharPlayer.h"
#include "Components/SplineComponent.h"
#include "Engine/SkeletalMeshSocket.h"
#include "GameFramework/Character.h"
#include "Interfaces/MyHighlightInterface.h"
#include "Kismet/GameplayStatics.h"
#include "PlayerInput/MyInputComponent.h"
#include "UI/DamageTextWidgetComponent.h"


class UEnhancedPlayerInput;
class UEnhancedInputLocalPlayerSubsystem;

AMyPlayerController::AMyPlayerController()
{
	SplineComp= CreateDefaultSubobject<USplineComponent>(TEXT("SplineComp"));
	// FInputModeGameOnly InputMode;
}

void AMyPlayerController::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	AutoMove();
	CursorTrace();
	UpdateDamageCircle();
	
	// UKismetSystemLibrary::PrintString(GetWorld(),AimLocation.ToString());
}

void AMyPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	
	UEnhancedInputLocalPlayerSubsystem* EnhancedInputSubsystem=ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer());
	
	EnhancedInputSubsystem->AddMappingContext(IMC_PlayerInputMappingContext,0);
	
	UMyInputComponent* MyInputComp=Cast<UMyInputComponent>(InputComponent);
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Triggered,this,&AMyPlayerController::Move);
	
	MyInputComp->BindAbilityAction(InputConfig,this,&AMyPlayerController::PressedFunc,&AMyPlayerController::HeldFunc,&AMyPlayerController::ReleasedFunc);
}

void AMyPlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI InputMode;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	
	SetInputMode(InputMode);
	bShowMouseCursor=true;
	
	AMyPlayerState* PS=GetPlayerState<AMyPlayerState>();
	
	if (!IsLocalController())return;
	// FString Str= FString::Printf(TEXT("LocalRole: %s, RemoteRole : %s"),*LexToString(GetLocalRole()),*LexToString(GetRemoteRole()));
	// UKismetSystemLibrary::PrintString(GetWorld(),Str,true,true,FLinearColor::Red,30);
	
	//check if ASC inited then Bind
	//can call a delegate when inits an bind in that lambda
	// PS->MyAbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(PS->MyAttributeSet->GetMoveSpeedAttribute()).AddLambda(
	// 	[this](const FOnAttributeChangeData& Data)
	// 	{
	// 		MovementSpeed=Data.NewValue;
	// 	}
	// );
	// MovementSpeed=PS->MyAttributeSet->GetMoveSpeed();
}

void AMyPlayerController::Move(const FInputActionValue& Value)
{
	if (GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent->HasMatchingGameplayTag(MyTags::State_Channeling))return;
	const FVector2d InputVal= Value.Get<FVector2d>();
	FRotationMatrix RotMat=FRotationMatrix(GetControlRotation());
	FVector ForwardDir=RotMat.GetUnitAxis(EAxis::X);
	FVector RightVector=RotMat.GetUnitAxis(EAxis::Y);
	GetCharacter()->AddMovementInput(ForwardDir,InputVal.X);
	GetCharacter()->AddMovementInput(RightVector,InputVal.Y);
}

void AMyPlayerController::AutoMove()
{
	if (!bIsAutoRunning)return;
	float Dist= (GetCharacter()->GetActorLocation()-CachedLocation).Size();
	if (Dist<DistThreshold)
	{
		bIsAutoRunning=false;
	}
	else
	{
		FVector Dir= SplineComp->FindTangentClosestToWorldLocation(GetCharacter()->GetActorLocation(),ESplineCoordinateSpace::World);
		GetCharacter()->AddMovementInput(Dir*MovementSpeed,1);
	}
}

void AMyPlayerController::CursorTrace()
{
	//TODO Fix TraceComplex?
	GetHitResultUnderCursor(ECC_Visibility,true,HitResult);
	
	AimLocation=HitResult.ImpactPoint;
	DrawDebugSphere(GetWorld(),HitResult.ImpactPoint,10,10,FColor::Red,false,0.1f);
	
	AMyCharBase* MyCharBase=Cast<AMyCharBase>(GetPawn());
	
	USkeletalMeshComponent* Skel=MyCharBase->GetMesh();
	if (Skel)
	{
		FVector BoneLoc= Skel->GetBoneLocation(FName("LA_point_3"));
		if (!BoneLoc.ContainsNaN())
		{
			DrawDebugLine(GetWorld(),BoneLoc,HitResult.ImpactPoint,FColor::Red,false,0.1f);
		}
		
	}
	
	LastActor=ThisActor;
	ThisActor=Cast<IMyHighlightInterface>(HitResult.GetActor());
	
	// if (!HitResult.bBlockingHit) return;
	if (ThisActor)
	{
		ThisActor->Highlight();
	}
	if (ThisActor== nullptr && LastActor)
	{
		LastActor->UnHighlight();
	}
	bIsTargeting=ThisActor!=nullptr;
}

void AMyPlayerController::PressedFunc(FGameplayTag InputTag)
{
	PressedTime=0;
	if (!bIsTargeting)return;
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputPressed(InputTag);
}

void AMyPlayerController::HeldFunc(FGameplayTag InputTag)
{
	PressedTime+=GetWorld()->DeltaTimeSeconds;
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputHeld(InputTag);
}

void AMyPlayerController::ReleasedFunc(FGameplayTag InputTag)
{
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputReleased(InputTag);
	
	if (InputTag == MyTags::Input_LMB)
	{
		SplineComp->ClearSplinePoints();
		if (PressedTime>PressedTimeThreshold)return;
		if (!bIsTargeting)
		{
			CachedLocation=HitResult.ImpactPoint;
			FVector PathStart= GetCharacter()->GetActorLocation();
			UNavigationPath* NavigationPath=UNavigationSystemV1::FindPathToLocationSynchronously(this,PathStart,CachedLocation);
			for (auto Point:NavigationPath->PathPoints)
			{
				SplineComp->AddSplinePoint(Point,ESplineCoordinateSpace::World,true);
				DrawDebugSphere(GetWorld(),Point,10,10,FColor::Red,false,0.1f);
			}
			SplineComp->UpdateSpline();
			bIsAutoRunning=true;
		}
	}
}

void AMyPlayerController::ShowDamageCircle()
{
	
	FActorSpawnParameters SpawnParams;
	
	 TargetDecalActor= GetWorld()->SpawnActor<AMyTargetDecalActor>(TargetDecalActorClass,HitResult.ImpactPoint,FRotator(0,0,0),SpawnParams);
}

void AMyPlayerController::HideDamageCircle()
{
	if (IsValid(TargetDecalActor))
	{
		TargetDecalActor->Destroy();
	}
}

void AMyPlayerController::UpdateDamageCircle()
{
	if (IsValid(TargetDecalActor))
	{
		TargetDecalActor->SetActorLocation(HitResult.ImpactPoint);
	}
}

void AMyPlayerController::ShowDamageNumber_Implementation(float InDamage,ACharacter* TargetCharacter,bool bIsCrit,bool bIsBlocked)
{
	if (IsValid(TargetCharacter) && DamageTextWidgetComponentClass)
	{
		UDamageTextWidgetComponent* DamageTextWidgetComponent=NewObject<UDamageTextWidgetComponent>(TargetCharacter,DamageTextWidgetComponentClass);
		DamageTextWidgetComponent->RegisterComponent();
		
		DamageTextWidgetComponent->AttachToComponent(TargetCharacter->GetRootComponent(),FAttachmentTransformRules::KeepRelativeTransform);
		DamageTextWidgetComponent->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
		
		DamageTextWidgetComponent->SetDamageText(InDamage,bIsCrit,bIsBlocked);
	}
	
}


