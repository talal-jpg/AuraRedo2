// Fill out your copyright notice in the Description page of Project Settings.


#include "AbilitySystem/Abilities/GA_GrappleSwing.h"

#include "AbilitySystemComponent.h"
#include "DrawDebugHelpers.h"
#include "NativeGameplayTags.h"
#include "TimerManager.h"
#include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"

UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_Ability_GrappleSwing,"Ability.GrappleSwing")
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_GameplayCue_GrappleRope,"GameplayCue.GrappleRope")

namespace GrappleSwing
{
	const FName RootMotionInstanceName=FName("GrappleSwing");
	const uint16 RootMotionPriority=500;
	// Server accepts a client hook point this much further than MaxGrappleDistance, and a client start location this far from its own
	const float ServerRangeTolerance=300.f;
	const float ServerStartLocationTolerance=250.f;
	const float DebugRopeInterval=1.f/60.f;
}

// ---------------------------------------------------------------------------------------------------------------------
// FRootMotionSource_GrappleSwing
// ---------------------------------------------------------------------------------------------------------------------

FRootMotionSource_GrappleSwing::FRootMotionSource_GrappleSwing()
{
	// Override: this source owns the whole velocity while swinging, so CMC skips its own gravity and air control
	AccumulateMode=ERootMotionAccumulateMode::Override;
	Priority=GrappleSwing::RootMotionPriority;
	InstanceName=GrappleSwing::RootMotionInstanceName;
	// Infinite, the ability removes it
	Duration=-1.f;
	Settings.SetFlag(ERootMotionSourceSettingsFlags::UseSensitiveLiftoffCheck);
	// Let go with whatever speed the swing had
	FinishVelocityParams.Mode=ERootMotionFinishVelocityMode::MaintainLastRootMotionVelocity;
}

FRootMotionSource* FRootMotionSource_GrappleSwing::Clone() const
{
	return new FRootMotionSource_GrappleSwing(*this);
}

bool FRootMotionSource_GrappleSwing::Matches(const FRootMotionSource* Other) const
{
	if (!FRootMotionSource::Matches(Other))return false;
	// Safe, FRootMotionSource::Matches checked the script struct
	const FRootMotionSource_GrappleSwing* OtherCast=static_cast<const FRootMotionSource_GrappleSwing*>(Other);
	return FVector::PointsAreNear(Anchor,OtherCast->Anchor,1.f);
}

bool FRootMotionSource_GrappleSwing::MatchesAndHasSameState(const FRootMotionSource* Other) const
{
	if (!FRootMotionSource::MatchesAndHasSameState(Other))return false;
	const FRootMotionSource_GrappleSwing* OtherCast=static_cast<const FRootMotionSource_GrappleSwing*>(Other);
	return FMath::IsNearlyEqual(RopeLength,OtherCast->RopeLength,1.f);
}

bool FRootMotionSource_GrappleSwing::UpdateStateFrom(const FRootMotionSource* SourceToTakeStateFrom, bool bMarkForSimulatedCatchup)
{
	if (!FRootMotionSource::UpdateStateFrom(SourceToTakeStateFrom,bMarkForSimulatedCatchup))return false;
	// Server is authoritative over how much rope is left
	RopeLength=static_cast<const FRootMotionSource_GrappleSwing*>(SourceToTakeStateFrom)->RopeLength;
	return true;
}

void FRootMotionSource_GrappleSwing::PrepareRootMotion(float SimulationTime, float MovementTickTime, const ACharacter& Character, const UCharacterMovementComponent& MoveComponent)
{
	RootMotionParams.Clear();

	const float DeltaTime=MovementTickTime;
	if (DeltaTime<=UE_SMALL_NUMBER)
	{
		RootMotionParams.Set(FTransform(MoveComponent.Velocity));
		SetTime(GetTime()+SimulationTime);
		return;
	}

	const FVector Up=-MoveComponent.GetGravityDirection();
	const FVector Gravity=Up*MoveComponent.GetGravityZ();
	const FVector Location=MoveComponent.UpdatedComponent->GetComponentLocation();

	// Momentum: start from the velocity the character already has
	FVector Velocity=MoveComponent.Velocity;

	const FVector ToAnchor=Anchor-Location;
	const float Distance=ToAnchor.Size();
	const FVector RopeDir=Distance>UE_KINDA_SMALL_NUMBER ? ToAnchor/Distance : Up;

	// Gravity, CMC does not apply it while an override source is active
	Velocity+=Gravity*DeltaTime;

	// Hook pulls the character towards itself, fading out near the min rope length so it never yanks into the hook
	const float PullScale=MinRopeLength>UE_KINDA_SMALL_NUMBER ? FMath::Clamp((Distance-MinRopeLength)/MinRopeLength,0.f,1.f) : 1.f;
	Velocity+=RopeDir*PullAcceleration*PullScale*DeltaTime;

	// Steering: only the part of the movement input across the rope, so input bends the swing but never fights the rope
	const float MaxAccel=MoveComponent.GetMaxAcceleration();
	if (MaxAccel>UE_KINDA_SMALL_NUMBER)
	{
		const FVector InputDir=(MoveComponent.GetCurrentAcceleration()/MaxAccel).GetClampedToMaxSize(1.f);
		const FVector SteerDir=FVector::VectorPlaneProject(InputDir,RopeDir);
		Velocity+=SteerDir*SteerAcceleration*DeltaTime;
	}

	Velocity*=FMath::Max(0.f,1.f-AirDrag*DeltaTime);

	// Rope reels in over time, and picks up slack when the character gets closer than the rope
	RopeLength=FMath::Max(MinRopeLength,FMath::Min(RopeLength,Distance)-ReelInSpeed*DeltaTime);

	// Rope constraint: when taut, cancel the velocity that would stretch it. This is the tension that balances
	// the centrifugal force, it keeps the tangential speed and turns it around the hook.
	if (Distance>=RopeLength)
	{
		const float OutwardSpeed=-(Velocity|RopeDir);
		if (OutwardSpeed>0.f)
		{
			Velocity+=RopeDir*OutwardSpeed;
		}
		// Moving along a tangent drifts outward a bit every move, pull that stretch back in
		const float Stretch=Distance-RopeLength;
		Velocity+=RopeDir*FMath::Min(Stretch*RopeStiffness,MaxSwingSpeed);
	}

	// Lift off when the swing starts on the ground, walking would otherwise eat the vertical speed
	if (MoveComponent.IsMovingOnGround())
	{
		const float UpSpeed=Velocity|Up;
		if (UpSpeed<GroundLiftoffSpeed)
		{
			Velocity+=Up*(GroundLiftoffSpeed-UpSpeed);
		}
	}

	Velocity=Velocity.GetClampedToMaxSize(MaxSwingSpeed);

	// For override sources the translation is the velocity to use for this move
	RootMotionParams.Set(FTransform(Velocity));

	SetTime(GetTime()+SimulationTime);
}

bool FRootMotionSource_GrappleSwing::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	if (!FRootMotionSource::NetSerialize(Ar,Map,bOutSuccess))return false;

	Ar << Anchor;
	Ar << RopeLength;
	Ar << MinRopeLength;
	Ar << ReelInSpeed;
	Ar << PullAcceleration;
	Ar << SteerAcceleration;
	Ar << RopeStiffness;
	Ar << AirDrag;
	Ar << MaxSwingSpeed;
	Ar << GroundLiftoffSpeed;

	bOutSuccess=true;
	return true;
}

UScriptStruct* FRootMotionSource_GrappleSwing::GetScriptStruct() const
{
	return FRootMotionSource_GrappleSwing::StaticStruct();
}

FString FRootMotionSource_GrappleSwing::ToSimpleString() const
{
	return FString::Printf(TEXT("[ID:%u]FRootMotionSource_GrappleSwing %s Anchor(%s) Rope(%.0f)"),LocalID,*InstanceName.GetPlainNameString(),*Anchor.ToCompactString(),RopeLength);
}

// ---------------------------------------------------------------------------------------------------------------------
// UGA_GrappleSwing
// ---------------------------------------------------------------------------------------------------------------------

UGA_GrappleSwing::UGA_GrappleSwing()
{
	InstancingPolicy=EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy=EGameplayAbilityNetExecutionPolicy::LocalPredicted;
	AbilityTag=TAG_Ability_GrappleSwing;
	RopeCueTag=TAG_GameplayCue_GrappleRope;
}

void UGA_GrappleSwing::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle,ActorInfo,ActivationInfo,TriggerEventData);

	if (!GetSwingCharacter() || !GetSwingMovement())
	{
		EndAbility(Handle,ActorInfo,ActivationInfo,true,true);
		return;
	}

	UAbilityTask_WaitInputRelease* WaitReleaseTask=UAbilityTask_WaitInputRelease::WaitInputRelease(this,true);
	WaitReleaseTask->OnRelease.AddDynamic(this,&ThisClass::OnInputReleased);
	WaitReleaseTask->ReadyForActivation();

	if (IsLocallyControlled())
	{
		// Owning client (or listen server host): the crosshair is only known here
		FVector HookPoint;
		if (!TraceForAnchor(HookPoint))
		{
			CancelAbility(Handle,ActorInfo,ActivationInfo,true);
			return;
		}
		const FVector StartLocation=GetSwingCharacter()->GetActorLocation();

		if (!HasAuthority(&ActivationInfo))
		{
			// Send exact hook point and start location, the server builds the same rope from them
			FGameplayAbilityTargetData_LocationInfo* LocationData=new FGameplayAbilityTargetData_LocationInfo();
			LocationData->SourceLocation.LocationType=EGameplayAbilityTargetingLocationType::LiteralTransform;
			LocationData->SourceLocation.LiteralTransform=FTransform(StartLocation);
			LocationData->TargetLocation.LocationType=EGameplayAbilityTargetingLocationType::LiteralTransform;
			LocationData->TargetLocation.LiteralTransform=FTransform(HookPoint);
			FGameplayAbilityTargetDataHandle DataHandle(LocationData);

			UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
			FScopedPredictionWindow ScopedPrediction(ASC,true);
			ASC->CallServerSetReplicatedTargetData(Handle,ActivationInfo.GetActivationPredictionKey(),DataHandle,FGameplayTag(),ASC->ScopedPredictionKey);
		}

		if (!CommitAbility(Handle,ActorInfo,ActivationInfo))
		{
			CancelAbility(Handle,ActorInfo,ActivationInfo,true);
			return;
		}
		StartSwing(HookPoint,StartLocation);
	}
	else
	{
		// Server for a remote client: wait for the client's hook point
		UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
		const FPredictionKey ActivationKey=ActivationInfo.GetActivationPredictionKey();
		TargetDataDelegateHandle=ASC->AbilityTargetDataSetDelegate(Handle,ActivationKey).AddUObject(this,&ThisClass::OnServerTargetDataReceived);
		ASC->CallReplicatedTargetDataDelegatesIfSet(Handle,ActivationKey);
	}
}

void UGA_GrappleSwing::OnServerTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag)
{
	UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo();
	ASC->ConsumeClientReplicatedTargetData(CurrentSpecHandle,CurrentActivationInfo.GetActivationPredictionKey());

	const FGameplayAbilityTargetData* Data=DataHandle.Get(0);
	ACharacter* Character=GetSwingCharacter();
	if (!Data || !Data->HasOrigin() || !Data->HasEndPoint() || !Character)
	{
		CancelAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,true);
		return;
	}

	const FVector StartLocation=Data->GetOrigin().GetLocation();
	const FVector HookPoint=Data->GetEndPoint();

	// Don't trust the client blindly: the hook has to be in range of where the server has the character
	const FVector ServerLocation=Character->GetActorLocation();
	const bool bStartValid=FVector::Dist(StartLocation,ServerLocation)<=GrappleSwing::ServerStartLocationTolerance;
	const bool bRangeValid=FVector::Dist(HookPoint,ServerLocation)<=MaxGrappleDistance+GrappleSwing::ServerRangeTolerance;
	if (!bStartValid || !bRangeValid || !CommitAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo))
	{
		CancelAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,true);
		return;
	}

	StartSwing(HookPoint,StartLocation);
}

bool UGA_GrappleSwing::TraceForAnchor(FVector& OutAnchor) const
{
	ACharacter* Character=GetSwingCharacter();
	APlayerController* PC=Character ? Cast<APlayerController>(Character->GetController()) : nullptr;
	if (!PC)return false;

	// Camera view point, the crosshair sits in the middle of the screen
	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation,ViewRotation);

	// Start the trace level with the character so things between the camera and the character don't count
	const FVector ViewDir=ViewRotation.Vector();
	const FVector CharLocation=Character->GetActorLocation();
	const FVector TraceStart=ViewLocation+ViewDir*((CharLocation-ViewLocation)|ViewDir);
	const FVector TraceEnd=TraceStart+ViewDir*MaxGrappleDistance;

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(GrappleSwingTrace),true,Character);
	FHitResult Hit;
	if (!GetWorld()->LineTraceSingleByChannel(Hit,TraceStart,TraceEnd,GrappleTraceChannel,QueryParams))return false;

	const FVector Up=-GetSwingMovement()->GetGravityDirection();
	if (((Hit.ImpactPoint-CharLocation)|Up)<MinAnchorHeight)return false;
	if (FVector::Dist(Hit.ImpactPoint,CharLocation)>MaxGrappleDistance)return false;

	OutAnchor=Hit.ImpactPoint;
	return true;
}

void UGA_GrappleSwing::StartSwing(const FVector& InAnchor, const FVector& StartLocation)
{
	ACharacter* Character=GetSwingCharacter();
	UCharacterMovementComponent* MoveComp=GetSwingMovement();
	Anchor=InAnchor;
	SwingStartTime=GetWorld()->GetTimeSeconds();

	// Rope length comes from the client's start location so the client and server ropes are identical
	TSharedPtr<FRootMotionSource_GrappleSwing> Swing=MakeShared<FRootMotionSource_GrappleSwing>();
	Swing->Anchor=Anchor;
	Swing->RopeLength=FMath::Max(MinRopeLength,FVector::Dist(Anchor,StartLocation));
	Swing->MinRopeLength=MinRopeLength;
	Swing->ReelInSpeed=ReelInSpeed;
	Swing->PullAcceleration=PullAcceleration;
	Swing->SteerAcceleration=SteerAcceleration;
	Swing->RopeStiffness=RopeStiffness;
	Swing->AirDrag=AirDrag;
	Swing->MaxSwingSpeed=MaxSwingSpeed;
	Swing->GroundLiftoffSpeed=GroundLiftoffSpeed;
	RootMotionSourceID=MoveComp->ApplyRootMotionSource(Swing);

	Character->MovementModeChangedDelegate.AddUniqueDynamic(this,&ThisClass::OnMovementModeChanged);

	if (RopeCueTag.IsValid())
	{
		FGameplayCueParameters CueParams;
		CueParams.Location=Anchor;
		CueParams.EffectCauser=Character;
		CueParams.Instigator=Character;
		K2_AddGameplayCueWithParams(RopeCueTag,CueParams,true);
	}

	if (bDrawDebugRope && IsLocallyControlled())
	{
		GetWorld()->GetTimerManager().SetTimer(DebugRopeTimerHandle,this,&ThisClass::DrawDebugRope,GrappleSwing::DebugRopeInterval,true);
	}
}

void UGA_GrappleSwing::StopSwing()
{
	if (UCharacterMovementComponent* MoveComp=GetSwingMovement())
	{
		if (RootMotionSourceID!=(uint16)ERootMotionSourceID::Invalid)
		{
			MoveComp->RemoveRootMotionSourceByID(RootMotionSourceID);
		}
	}
	RootMotionSourceID=(uint16)ERootMotionSourceID::Invalid;

	if (ACharacter* Character=GetSwingCharacter())
	{
		Character->MovementModeChangedDelegate.RemoveDynamic(this,&ThisClass::OnMovementModeChanged);
	}
	GetWorld()->GetTimerManager().ClearTimer(DebugRopeTimerHandle);
}

void UGA_GrappleSwing::OnInputReleased(float TimeHeld)
{
	const bool bWasSwinging=RootMotionSourceID!=(uint16)ERootMotionSourceID::Invalid;
	StopSwing();

	// Let go: keep the swing momentum and add a little hop, runs on both client and server
	ACharacter* Character=GetSwingCharacter();
	if (bWasSwinging && Character && ReleaseUpBoost>0.f)
	{
		Character->LaunchCharacter(-GetSwingMovement()->GetGravityDirection()*ReleaseUpBoost,false,false);
	}
	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,true,false);
}

void UGA_GrappleSwing::OnMovementModeChanged(ACharacter* Character, EMovementMode PrevMovementMode, uint8 PreviousCustomMode)
{
	// Landed, the swing is over
	if (!Character || !Character->GetCharacterMovement()->IsMovingOnGround())return;
	if (GetWorld()->GetTimeSeconds()-SwingStartTime<LandingGraceTime)return;
	EndAbility(CurrentSpecHandle,CurrentActorInfo,CurrentActivationInfo,true,false);
}

void UGA_GrappleSwing::DrawDebugRope() const
{
	if (ACharacter* Character=GetSwingCharacter())
	{
		DrawDebugLine(GetWorld(),Character->GetActorLocation(),Anchor,FColor::White,false,GrappleSwing::DebugRopeInterval*1.5f,0,2.f);
		DrawDebugSphere(GetWorld(),Anchor,15.f,8,FColor::Red,false,GrappleSwing::DebugRopeInterval*1.5f);
	}
}

void UGA_GrappleSwing::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (!IsActive())return;

	StopSwing();

	if (TargetDataDelegateHandle.IsValid())
	{
		if (UAbilitySystemComponent* ASC=GetAbilitySystemComponentFromActorInfo())
		{
			ASC->AbilityTargetDataSetDelegate(Handle,ActivationInfo.GetActivationPredictionKey()).Remove(TargetDataDelegateHandle);
		}
		TargetDataDelegateHandle.Reset();
	}

	Super::EndAbility(Handle,ActorInfo,ActivationInfo,bReplicateEndAbility,bWasCancelled);
}

ACharacter* UGA_GrappleSwing::GetSwingCharacter() const
{
	return Cast<ACharacter>(GetAvatarActorFromActorInfo());
}

UCharacterMovementComponent* UGA_GrappleSwing::GetSwingMovement() const
{
	ACharacter* Character=GetSwingCharacter();
	return Character ? Character->GetCharacterMovement() : nullptr;
}
