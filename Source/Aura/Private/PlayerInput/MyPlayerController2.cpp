// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController2.h"

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

AMyPlayerController2::AMyPlayerController2()
{
	// FInputModeGameOnly InputMode;
}

void AMyPlayerController2::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	// AutoMove();
	// CursorTrace();
	
	GetHitResultUnderCursor(ECC_Visibility,true,HitResult);
	// GetPawn()->AddControllerYawInput(10);
	
	// AimLocation= HitResult.ImpactPoint;
	// AimLocation= GetControlRotation().Vector();
	
	FVector DirFromCam;
	FVector PosInWorld;
	
	int32 ViewportSizeX,ViewportSizeY;
	GetViewportSize(ViewportSizeX,ViewportSizeY);
	
	const float OffsetInScreenY=-200;
	DeprojectScreenPositionToWorld(ViewportSizeX*.5f,ViewportSizeY*.5f+OffsetInScreenY,PosInWorld,DirFromCam);
	
	FCollisionQueryParams CollisionQueryParams;
	CollisionQueryParams.AddIgnoredActor(GetPawn());
	
	FHitResult HitResult;
	
	//1000 in front is too far TODO Fix
	bool bHit=GetWorld()->LineTraceSingleByChannel(HitResult,PosInWorld+DirFromCam*1000,PosInWorld+DirFromCam*FLT_MAX,ECC_Visibility,CollisionQueryParams);
	
	if (bHit)
	{
		TargetLocation= HitResult.ImpactPoint;
	}
	else
	{
		TargetLocation= PosInWorld+DirFromCam*1000;
	}
	
	UKismetSystemLibrary::DrawDebugSphere(GetWorld(),TargetLocation,100,12,FLinearColor::Yellow,false,0.1f);
	
	// ForwardVecRigSpace=Z = 0
	// ForwardVecRigSpace=FRotationMatrix(FRotator(0,GetControlRotation().Yaw,GetControlRotation().Roll)).GetUnitAxis(EAxis::X); or that better ask GPT?
	// Not in rig space still if use control rotation is false
	// ControlRotForwardVec= FVector(GetControlRotation().Vector().X,GetControlRotation().Vector().Y,0);
	
	
	// FVector PLoc=GetPawn()->GetActorLocation();
	// UKismetSystemLibrary::DrawDebugArrow(GetWorld(),PLoc,PLoc+GetControlRotation().Vector()*1000,10,FLinearColor::Yellow,30,10);
	
	// LerpChestRotToRot();
	// LerpFeetRotToRot();
	
	//CharMeshRotation
	// GetPawn()->GetViewRotation()
	
	UpdateDamageCircle();
	
	// UKismetSystemLibrary::PrintString(GetWorld(),AimLocation.ToString());
}

void AMyPlayerController2::SetupInputComponent()
{
	Super::SetupInputComponent();
	UEnhancedInputLocalPlayerSubsystem* EnhancedInputSubsystem=ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer());
	
	EnhancedInputSubsystem->AddMappingContext(IMC_PlayerInputMappingContext,0);
	
	UMyInputComponent* MyInputComp=Cast<UMyInputComponent>(InputComponent);
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Triggered,this,&AMyPlayerController2::Move);
	MyInputComp->BindAction(IA_Rotate,ETriggerEvent::Triggered,this,&AMyPlayerController2::Rotate);
	
	MyInputComp->BindAbilityAction(InputConfig,this,&AMyPlayerController2::PressedFunc,&AMyPlayerController2::HeldFunc,&AMyPlayerController2::ReleasedFunc);
}

void AMyPlayerController2::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI InputMode;
	FInputModeGameOnly InputMode2;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	
	//Important fix
	InputMode2.SetConsumeCaptureMouseDown(false);
	
	SetInputMode(InputMode2);
	// bShowMouseCursor=true;
	
	AMyPlayerState* PS=GetPlayerState<AMyPlayerState>();
	
	
	// FTimerHandle TimerHandleChest;
	// float TickRateChestTimer= .1f;
	// GetWorldTimerManager().SetTimer(TimerHandleChest,this,&AMyPlayerController2::LerpChestRotToRot,TickRateChestTimer,true);
	
	
	FTimerHandle TimerHandleFeet;
	float TickRateFeetTimer= .1f;
	GetWorldTimerManager().SetTimer(TimerHandleFeet,this,&AMyPlayerController2::LerpFeetRotToRot,TickRateFeetTimer,true);
	
	
	
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

void AMyPlayerController2::Move(const FInputActionValue& Value)
{
	if (GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent->HasMatchingGameplayTag(MyTags::State_Channeling))return;
	
	const FVector2d InputVal= Value.Get<FVector2d>();
	
	FRotationMatrix RotMat=FRotationMatrix(FRotator(0,GetControlRotation().Yaw,GetControlRotation().Roll));
	
	FVector ForwardDir=RotMat.GetUnitAxis(EAxis::X);
	FVector RightVector=RotMat.GetUnitAxis(EAxis::Y);
	GetCharacter()->AddMovementInput(ForwardDir,InputVal.X);
	GetCharacter()->AddMovementInput(RightVector,InputVal.Y);
}

void AMyPlayerController2::Rotate(const FInputActionValue& Value)
{
	FVector2d Val=Value.Get<FVector2d>();
	GetPawn()->AddControllerYawInput(Val.X);
	GetPawn()->AddControllerPitchInput(Val.Y);
}

void AMyPlayerController2::CursorTrace()
{
	//TODO Fix TraceComplex?
	//Do only in tick remove from here
	GetHitResultUnderCursor(ECC_Visibility,true,HitResult);
	
	// DrawDebugSphere(GetWorld(),HitResult.ImpactPoint,10,10,FColor::Red,false,0.1f);
	
	AMyCharBase* MyCharBase=Cast<AMyCharBase>(GetPawn());
	
	// USkeletalMeshComponent* Skel=MyCharBase->GetMesh();
	// if (Skel)
	// {
	// 	FVector BoneLoc= Skel->GetBoneLocation(FName("LA_point_3"));
	// 	if (!BoneLoc.ContainsNaN())
	// 	{
	// 		DrawDebugLine(GetWorld(),BoneLoc,HitResult.ImpactPoint,FColor::Red,false,0.1f);
	// 	}
		
	// }
	
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

void AMyPlayerController2::LerpChestRotToRot()
{
	const float AmountToRotateEachTimerTick=.1f;
	// RotChest= FMath::Lerp(RotChest,ForwardVecRigSpace,AmountToRotateEachTimerTick);
	RotChest=FMath::Lerp(GetCharacter()->GetMesh()->GetComponentRotation().Vector(),GetControlRotation().Vector(),AmountToRotateEachTimerTick);
}

void AMyPlayerController2::LerpFeetRotToRot()
{
	const float AmountToRotateEachTimerTick=.05f;
	// RotFeet= FMath::Lerp(RotFeet,GetControlRotation().Vector(),AmountToRotateEachTimerTick);
	
	FRotator ControlRot=GetControlRotation();
	ControlRot.Pitch=0;
	FRotator NewRot=FMath::Lerp(GetCharacter()->GetMesh()->GetComponentRotation(),ControlRot,AmountToRotateEachTimerTick);
	YawDelta = FMath::FindDeltaAngleDegrees(NewRot.Yaw, ControlRot.Yaw);
	UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("YawDelta: %f"),YawDelta),true,true,FLinearColor::Red,1.f);
	FVector PawnLoc=GetPawn()->GetActorLocation();
	// UKismetSystemLibrary::DrawDebugArrow(GetWorld(),PawnLoc,PawnLoc+NewRot.Vetor()*1000,10,FLinearColor::Yellow,.1f,10);
	GetCharacter()->GetMesh()->SetWorldRotation(NewRot);
	// GetPawn()->SetActorRotation(NewRot);
}

void AMyPlayerController2::PressedFunc(FGameplayTag InputTag)
{
	if (!bIsTargeting)return;
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputPressed(InputTag);
}

void AMyPlayerController2::HeldFunc(FGameplayTag InputTag)
{
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputHeld(InputTag);
}

void AMyPlayerController2::ReleasedFunc(FGameplayTag InputTag)
{
	UMyAbilitySystemComponent* MyASC=GetPlayerState<AMyPlayerState>()->MyAbilitySystemComponent;
	MyASC->AbilityInputReleased(InputTag);
	
}

void AMyPlayerController2::ShowDamageCircle()
{
	
	FActorSpawnParameters SpawnParams;
	
	 TargetDecalActor= GetWorld()->SpawnActor<AMyTargetDecalActor>(TargetDecalActorClass,HitResult.ImpactPoint,FRotator(0,0,0),SpawnParams);
}

void AMyPlayerController2::HideDamageCircle()
{
	if (IsValid(TargetDecalActor))
	{
		TargetDecalActor->Destroy();
	}
}

void AMyPlayerController2::UpdateDamageCircle()
{
	if (IsValid(TargetDecalActor))
	{
		TargetDecalActor->SetActorLocation(HitResult.ImpactPoint);
	}
}

void AMyPlayerController2::ShowDamageNumber_Implementation(float InDamage,ACharacter* TargetCharacter,bool bIsCrit,bool bIsBlocked)
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


