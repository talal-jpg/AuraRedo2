// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController.h"

#include <string>

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "MyPlayerState.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"
#include "VectorUtil.h"
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
#include "Kismet/KismetMathLibrary.h"
#include "PlayerInput/MyInputComponent.h"
#include "Tests/AutomationTestSettings.h"
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
	// AutoMove();
	// CursorTrace();
	
	GetHitResultUnderCursor(ECC_Visibility,true,HitResult);
	
	UpdateDamageCircle();
	SetAimLocation();
	
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

void AMyPlayerController::SetAimLocation()
{
	
	{
		// FRotator RootRot=GetPawn()->GetActorRotation();
		// FRotationMatrix RootRotationMatrixMat=FRotationMatrix(RootRot);
		//
		// FVector LeftSpan= RootRot.RotateVector(LeftEnd);
		// FVector RightSpan= RootRot.RotateVector(RightEnd);
		//
		// FVector PawnLoc=GetPawn()->GetActorLocation();
		//
		// DrawDebugLine(GetWorld(),PawnLoc,PawnLoc+LeftSpan*1000,FColor::Blue,false,.1f);
		// DrawDebugLine(GetWorld(),PawnLoc,PawnLoc+RightSpan*1000,FColor::Blue,false,.1f);
		//
		// FVector FromActorToHitLocation=HitResult.ImpactPoint-GetPawn()->GetActorLocation();
		// FVector FromActorToHitLocationOrig=FromActorToHitLocation;
		// FromActorToHitLocationOrig.Y= FMath::Clamp(FromActorToHitLocationOrig.Y,0,100000000);
		// FromActorToHitLocation.Z=0.f;
		//
		// DrawDebugLine(GetWorld(),PawnLoc,PawnLoc+FromActorToHitLocation,FColor::Blue,false,.1f);
		//
		// //if span is more than 90 it breaks
		// AimLocation=FromActorToHitLocationOrig;
		// UKismetSystemLibrary::DrawDebugSphere(this,AimLocation,100,12,FLinearColor::Yellow,false,0.1f);
		//
		// if (FromActorToHitLocation.Dot(LeftSpan) >0 && FromActorToHitLocation.Dot(RightSpan) >0)
		// {
		// 	// AimLocation=HitResult.ImpactPoint;
		// }
		// else
		// {
		// 	// AimLocation=GetPawn()->GetActorLocation()+RootRotationMatrixMat.GetUnitAxis(EAxis::X)*1000;
		// }
	}
	
	{
		//Xform Clamping in Local Space
		// FTransform PawnTransform=GetPawn()->GetActorTransform();
		// FVector ImpactPoint=HitResult.ImpactPoint;
		//
		// ImpactPoint= PawnTransform.InverseTransformPosition(ImpactPoint);
		// ImpactPoint.Y=FMath::Clamp(ImpactPoint.Y,-400,400);
		// ImpactPoint.X=FMath::Clamp(ImpactPoint.X,0,FLT_MAX);
		// ImpactPoint= PawnTransform.TransformPosition(ImpactPoint);
		//
		// AimLocation=ImpactPoint;
		// ProjectWorldLocationToScreenWithDistance(ImpactPoint,TargetLocation);
		//
		// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("AimLocation: %s"),*ImpactPoint.ToString()));
		// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("TargetLocation: %s"),*TargetLocation.ToString()));
	}
	
	if ( !HitResult.bBlockingHit)
	{
		float MouseX;
		float MouseY;
		GetMousePosition(MouseX,MouseY);
		
	}
	if (HitResult.bBlockingHit)
	{
		FVector ImpactPoint= HitResult.ImpactPoint;
		
		FVector PawnLoc = GetPawn()->GetActorLocation();

		float Distance = (ImpactPoint - PawnLoc).Size();
		
		FVector FromPawnDir = (ImpactPoint - PawnLoc)/Distance;
		
		FVector Forward = GetPawn()->GetActorForwardVector();

		float PawnYaw = Forward.Rotation().Yaw;
		float TargetYaw = FromPawnDir.Rotation().Yaw;

		float DeltaYaw = FMath::FindDeltaAngleDegrees(PawnYaw, TargetYaw);
		
		float ClampedYaw = FMath::Clamp(DeltaYaw, -ViewSpan*.5, ViewSpan*.5);
		
		FRotator NewRot(FromPawnDir.Rotation().Pitch, PawnYaw + ClampedYaw, FromPawnDir.Rotation().Roll);
		
		FVector ClampedDir = NewRot.Vector();
		
		UKismetSystemLibrary::DrawDebugArrow(this,PawnLoc,PawnLoc+ClampedDir*1000,10,FLinearColor::Yellow,.1f,10);
		
		FVector ClampedImpact = PawnLoc + ClampedDir * Distance;
		
		AimLocation=ClampedImpact;
		ProjectWorldLocationToScreenWithDistance(ClampedImpact,TargetLocation);
	}
	
}

void AMyPlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI InputMode;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::LockAlways);
	
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
	//Do only in tick remove from here
	GetHitResultUnderCursor(ECC_Visibility,true,HitResult);
	
	// DrawDebugSphere(GetWorld(),HitResult.ImpactPoint,10,10,FColor::Red,false,0.1f);
	
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


