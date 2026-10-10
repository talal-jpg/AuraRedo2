// Fill out your copyright notice in the Description page of Project Settings.


#include "PlayerInput/MyPlayerController2.h"

#include <string>

#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "MyPlayerState.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"
#include "NetworkMessage.h"
#include "NiagaraComponent.h"
#include "NiagaraDataChannel.h"
#include "NiagaraDataChannelAccessor.h"
#include "NiagaraDataChannelFunctionLibrary.h"
#include "AbilitySystem/MyAbilitySystemComponent.h"
#include "AbilitySystem/MyAttributeSet.h"
#include "AbilitySystem/Data/MyGameplayTags.h"
#include "Actors/MyTargetDecalActor.h"
#include "Character/MyCharPlayer.h"
#include "Camera/PlayerCameraManager.h"
#include "Camera/CameraComponent.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "AbilitySystem/Abilities/GA_Beam.h"
#include "Components/CapsuleComponent.h"
#include "EOS/MainMenu.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GeometryCollection/GeometryCollectionParticlesData.h"
#include "Interfaces/MyHighlightInterface.h"
#include "Kismet/GameplayStatics.h"
#include "PlayerInput/MyInputComponent.h"
#include "UI/DamageTextWidgetComponent.h"
#include "UObject/ConstructorHelpers.h"


class UEnhancedPlayerInput;
class UEnhancedInputLocalPlayerSubsystem;

AMyPlayerController2::AMyPlayerController2()
{
	// FInputModeGameOnly InputMode;
	
	static ConstructorHelpers::FObjectFinder<UNiagaraDataChannelAsset> DamageNumberNDC(TEXT("/Game/Level/UI/FloatingText/NiagaraDamageNumbers/NDC_DamageNumbers.NDC_DamageNumbers"));
	DamageNumberDataChannel=DamageNumberNDC.Object;
}

void AMyPlayerController2::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	TickHitImpact(DeltaTime);
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
	
	// const float OffsetInScreenY=-200;
	const float OffsetInScreenY=0;
	DeprojectScreenPositionToWorld(ViewportSizeX*.5f,ViewportSizeY*.5f+OffsetInScreenY,PosInWorld,DirFromCam);
	
	FCollisionQueryParams CollisionQueryParams;
	CollisionQueryParams.AddIgnoredActor(GetPawn());
	CollisionQueryParams.bTraceComplex=true;
	
	if (!GetPawn())return;
	//1000 in front is too far TODO Fix
	// bool bHit=GetWorld()->LineTraceSingleByChannel(HitResultLineTrace,PosInWorld+DirFromCam*10,PosInWorld+DirFromCam*FLT_MAX,ECC_Visibility,CollisionQueryParams);
	FCollisionShape Sphere = FCollisionShape::MakeSphere(10.f);
	bool bHit = GetWorld()->SweepSingleByChannel(HitResultLineTrace,PosInWorld+ DirFromCam * 10.f,PosInWorld+ DirFromCam * FLT_MAX,FQuat::Identity,ECC_Visibility,Sphere,CollisionQueryParams);
	
	if (bHit)
	{
		TargetLocation= HitResultLineTrace.ImpactPoint;
		// UKismetSystemLibrary::PrintString(this,FString::Printf(TEXT("Hit: %s"),*HitResultLineTrace.GetActor()->GetName()),true,true,FLinearColor::Red,10.f);
	}
	else
	{
		TargetLocation= PosInWorld+DirFromCam*1000;
	}
	
	UKismetSystemLibrary::DrawDebugArrow(GetWorld(),GetPawn()->GetActorLocation(),TargetLocation,10,FLinearColor::Yellow,0,02);
	// UKismetSystemLibrary::DrawDebugSphere(GetWorld(),TargetLocation,100,12,FLinearColor::Yellow,false,0.1f);
	
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
	//TODO Move From Triggered to Started??
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Triggered,this,&AMyPlayerController2::Move);
	MyInputComp->BindAction(IA_Move,ETriggerEvent::Completed,this,&AMyPlayerController2::MoveCompleted);
	MyInputComp->BindAction(IA_Rotate,ETriggerEvent::Triggered,this,&AMyPlayerController2::Rotate);
	MyInputComp->BindAction(IA_Jump,ETriggerEvent::Triggered,this,&AMyPlayerController2::Jump);
	MyInputComp->BindAction(IA_Q,ETriggerEvent::Started,this,&AMyPlayerController2::MenuButtonPressed,true);
	MyInputComp->BindAction(IA_E,ETriggerEvent::Started,this,&AMyPlayerController2::MenuButtonPressed,false);
	
	
	MyInputComp->BindAbilityAction(InputConfig,this,&AMyPlayerController2::PressedFunc,&AMyPlayerController2::HeldFunc,&AMyPlayerController2::ReleasedFunc);
}

void AMyPlayerController2::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI InputMode;
	FInputModeGameOnly InputMode2;
	InputMode.SetHideCursorDuringCapture(false);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	
	// };//Important fix
	InputMode2.SetConsumeCaptureMouseDown(false);
	
	SetInputMode(InputMode2);
	// bShowMouseCursor=true;
	
	AMyPlayerState* PS=GetPlayerState<AMyPlayerState>();
	
	
	// FTimerHandle TimerHandleChest;
	// float TickRateChestTimer= .1f;
	// GetWorldTimerManager().SetTimer(TimerHandleChest,this,&AMyPlayerController2::LerpChestRotToRot,TickRateChestTimer,true);
	
	
	// FTimerHandle TimerHandleFeet;
	// float TickRateFeetTimer= .1f;
	// GetWorldTimerManager().SetTimer(TimerHandleFeet,this,&AMyPlayerController2::LerpFeetRotToRot,TickRateFeetTimer,true);
	
	
	
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

UMyAbilitySystemComponent* AMyPlayerController2::GetMyASC()
{
	if (MyAbilitySystemComponent)return MyAbilitySystemComponent;
	AMyPlayerState* MyPlayerState=GetPlayerState<AMyPlayerState>();
	if (!MyPlayerState)return nullptr;
	UMyAbilitySystemComponent* MyASC=MyPlayerState->MyAbilitySystemComponent;
	return MyASC;
}

void AMyPlayerController2::Move(const FInputActionValue& Value)
{
	if (!GetMyASC() || !GetCharacter())return;
	if (GetMyASC()->HasMatchingGameplayTag(MyTags::State_BlockTranslate))return;
	
	const FVector2d InputVal= Value.Get<FVector2d>();
	
	FRotationMatrix RotMat=FRotationMatrix(GetControlRotation());
	EMovementMode MovementMode=GetCharacter()->GetCharacterMovement()->MovementMode;
	
	//if flying boosting use complete rotator 
	if (MovementMode== EMovementMode::MOVE_Flying && GetMyASC()->HasMatchingGameplayTag(MyTags::State_Boosting) )
	{
		RotMat=FRotationMatrix(FRotator(GetControlRotation()));
		FlyBoostingMoveInput= InputVal;
	}
	else 
	{
		//MightNot need to 0 out here
		FlyBoostingMoveInput= FVector2d(0,0);
		RotMat=FRotationMatrix(FRotator(0,GetControlRotation().Yaw,GetControlRotation().Roll));
		FVector ForwardDir=RotMat.GetUnitAxis(EAxis::X);
		FVector RightVector=RotMat.GetUnitAxis(EAxis::Y);
		GetCharacter()->AddMovementInput(ForwardDir,InputVal.X);
		GetCharacter()->AddMovementInput(RightVector,InputVal.Y);
	}
}

void AMyPlayerController2::MoveCompleted(const FInputActionValue& Value)
{
		FlyBoostingMoveInput= FVector2d(0,0);
}

void AMyPlayerController2::Rotate(const FInputActionValue& Value)
{
	if (!GetPawn())return;
	FVector2d Val=Value.Get<FVector2d>();
	GetPawn()->AddControllerYawInput(Val.X);
	GetPawn()->AddControllerPitchInput(Val.Y);
}

void AMyPlayerController2::Jump(const FInputActionValue& Value)
{
	Cast<AMyCharBase>(GetPawn())->Jump();
	
}

void AMyPlayerController2::MenuButtonPressed(bool bIsAttribMenuButton)
{
	OnMenuButtonPressedDelegate.Broadcast(bIsAttribMenuButton);
}

void AMyPlayerController2::SpellMenuButtonPressed(bool bIsAttribMenuButton)
{
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
	if (GetMyASC()->HasMatchingGameplayTag(MyTags::State_Channeling))return;
	const float AmountToRotateEachTimerTick=.05f;
	// RotFeet= FMath::Lerp(RotFeet,GetControlRotation().Vector(),AmountToRotateEachTimerTick);
	
	FRotator ControlRot=GetControlRotation();
	ControlRot.Pitch=0;
	FRotator NewRot=FMath::Lerp(GetCharacter()->GetMesh()->GetComponentRotation(),ControlRot,AmountToRotateEachTimerTick);
	YawDelta = FMath::FindDeltaAngleDegrees(NewRot.Yaw, ControlRot.Yaw);
	// UKismetSystemLibrary::PrintString(GetWorld(),FString::Printf(TEXT("YawDelta: %f"),YawDelta),true,true,FLinearColor::Red,1.f);
	FVector PawnLoc=GetPawn()->GetActorLocation();
	// UKismetSystemLibrary::DrawDebugArrow(GetWorld(),PawnLoc,PawnLoc+NewRot.Vetor()*1000,10,FLinearColor::Yellow,.1f,10);
	GetCharacter()->GetMesh()->SetWorldRotation(NewRot);
	// GetPawn()->SetActorRotation(NewRot);
}

void AMyPlayerController2::PressedFunc(FGameplayTag InputTag)
{
	// if (!bIsTargeting)return;

	UMyAbilitySystemComponent* MyASC = GetMyASC();
	if (MyASC==nullptr)return;
	MyASC->AbilityInputPressed(InputTag);
}

void AMyPlayerController2::HeldFunc(FGameplayTag InputTag)
{
	UMyAbilitySystemComponent* MyASC=GetMyASC();
	if (MyASC==nullptr)return;
	MyASC->AbilityInputHeld(InputTag);
}

void AMyPlayerController2::ReleasedFunc(FGameplayTag InputTag)
{
	UMyAbilitySystemComponent* MyASC=GetMyASC();
	if (MyASC==nullptr)return;
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

void AMyPlayerController2::JoinSessionButtonWrapper()
{
	UE_LOG(LogTemp,Warning,TEXT("JoinSessionButtonWrapperCalled"));
	if (MainMenu)
	{
		MainMenu->JoinButtonClicked();
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

void AMyPlayerController2::ShowDamageNumber_2_Implementation(float InDamage,ACharacter* TargetCharacter,bool bIsCrit,bool bIsBlocked)
{
	if (!IsValid(TargetCharacter) || !DamageNumberDataChannel) return;
	
	FVector Location=TargetCharacter->GetActorLocation();
	if (const UCapsuleComponent* Capsule=TargetCharacter->GetCapsuleComponent())
	{
		Location.Z+=Capsule->GetScaledCapsuleHalfHeight();
	}
	Location.Z+=DamageNumberHeightOffset;
	
	// Alpha carries the size scale, NS_DamageNumbers splits it back out
	FLinearColor Color= bIsBlocked ? BlockedDamageColor : (bIsCrit ? CritDamageColor : NormalDamageColor);
	Color.A= bIsCrit ? DamageNumberSize*CritDamageScale : DamageNumberSize;
	
	// GameplayBurst channels only accept the access context path, the legacy SearchParams write is rejected
	FNDCAccessContextInst& AccessContext=UNiagaraDataChannelLibrary::GetUsableAccessContextFromNDC(DamageNumberDataChannel);
	if (FNDCAccessContext* Context=AccessContext.Get<FNDCAccessContext>())
	{
		Context->Location=Location;
		Context->bOverrideLocation=true;
	}
	UNiagaraDataChannelWriter* Writer=UNiagaraDataChannelLibrary::WriteToNiagaraDataChannel_WithContext(this,DamageNumberDataChannel,AccessContext,1,false,true,true,TEXT("ShowDamageNumber_2"));
	if (!Writer) return;
	
	// How far the local camera is from the number, NS_DamageNumbers grows the sprites with it
	const FVector ViewLocation= PlayerCameraManager ? PlayerCameraManager->GetCameraLocation() : (GetPawn() ? GetPawn()->GetActorLocation() : Location);
	
	// Variable names must match NDC_DamageNumbers
	Writer->WritePosition(TEXT("Location"),0,Location);
	Writer->WriteFloat(TEXT("DamageAmount"),0,FMath::RoundToFloat(InDamage));
	Writer->WriteBool(TEXT("IsCritical"),0,bIsCrit);
	Writer->WriteBool(TEXT("IsBlocked"),0,bIsBlocked);
	Writer->WriteFloat(TEXT("Distance"),0,FVector::Dist(ViewLocation,Location));
	Writer->WriteLinearColor(TEXT("Color"),0,Color);
}



void AMyPlayerController2::Client_PlayBeamHitImpact_Implementation(TSubclassOf<UGA_Beam> BeamClass)
{
	if (!BeamClass) return;
	BeamClass->GetDefaultObject<UGA_Beam>()->PlayBeamHitImpactLocal(this);
}

void AMyPlayerController2::StartHitImpact(UMaterialInterface* Material,float Duration,float FOVOffset)
{
	UCameraComponent* Camera=GetPawn()?GetPawn()->FindComponentByClass<UCameraComponent>():nullptr;
	if (!Camera) return;
	
	if (bHitImpactActive) StopHitImpact();
	
	HitImpactCamera=Camera;
	HitImpactFOVOffset=FOVOffset;
	HitImpactDuration=FMath::Max(Duration,0.05f);
	HitImpactElapsed=0.f;
	bHitImpactActive=true;
	
	if (Material)
	{
		// The material runs the whole sequence itself from (Time-ImpactTime)/Duration, this side only sets when it started
		HitImpactMID=UMaterialInstanceDynamic::Create(Material,this);
		HitImpactMID->SetScalarParameterValue(TEXT("ImpactTime"),GetWorld()->GetTimeSeconds());
		HitImpactMID->SetScalarParameterValue(TEXT("Duration"),HitImpactDuration);
		Camera->PostProcessSettings.AddBlendable(HitImpactMID,1.f);
		
		// Characters go white in the impact frames, the material finds them through custom depth
		for (TActorIterator<ACharacter> It(GetWorld());It;++It)
		{
			TArray<UMeshComponent*> Meshes;
			It->GetComponents<UMeshComponent>(Meshes);
			for (UMeshComponent* Mesh:Meshes)
			{
				if (Mesh->IsVisible() && !Mesh->bRenderCustomDepth)
				{
					Mesh->SetRenderCustomDepth(true);
					HitImpactCustomDepthMeshes.Add(Mesh);
				}
			}
		}
	}
	TickHitImpact(0.f);
}

void AMyPlayerController2::TickHitImpact(float DeltaTime)
{
	if (!bHitImpactActive) return;
	if (!IsValid(HitImpactCamera))
	{
		StopHitImpact();
		return;
	}
	
	HitImpactElapsed+=DeltaTime;
	if (HitImpactElapsed>=HitImpactDuration)
	{
		StopHitImpact();
		return;
	}
	
	// FOV kick: full on impact, eases out
	const float Alpha=FMath::Square(1.f-HitImpactElapsed/HitImpactDuration);
	const float NewFOV=HitImpactFOVOffset*Alpha;
	HitImpactCamera->SetFieldOfView(HitImpactCamera->FieldOfView-HitImpactAppliedFOV+NewFOV);
	HitImpactAppliedFOV=NewFOV;
}

void AMyPlayerController2::StopHitImpact()
{
	if (IsValid(HitImpactCamera))
	{
		HitImpactCamera->SetFieldOfView(HitImpactCamera->FieldOfView-HitImpactAppliedFOV);
		if (HitImpactMID)
		{
			HitImpactCamera->PostProcessSettings.RemoveBlendable(HitImpactMID);
		}
	}
	for (UPrimitiveComponent* Mesh:HitImpactCustomDepthMeshes)
	{
		if (IsValid(Mesh)) Mesh->SetRenderCustomDepth(false);
	}
	HitImpactCustomDepthMeshes.Reset();
	HitImpactAppliedFOV=0.f;
	HitImpactCamera=nullptr;
	HitImpactMID=nullptr;
	bHitImpactActive=false;
}
