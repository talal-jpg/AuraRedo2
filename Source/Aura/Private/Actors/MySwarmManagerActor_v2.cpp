// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MySwarmManagerActor_v2.h"

#include "Actors/MySwarmManagerActor.h"


#include "Actors/MySwarmActor.h"
#include "Character/MyCharPlayer.h"
#include "Components/SplineComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Net/UnrealNetwork.h"

// Sets default values
AMySwarmManagerActor_v2::AMySwarmManagerActor_v2()
{
 	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = true;
	
	bReplicates=true;
}

void AMySwarmManagerActor_v2::GetLifetimeReplicatedProps(TArray<class FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	// DOREPLIFETIME_CONDITION(AMySwarmManagerActor,StartLocation,COND_InitialOnly);
	// DOREPLIFETIME_CONDITION(AMySwarmManagerActor,EndLocation,COND_InitialOnly);
	// DOREPLIFETIME_CONDITION(AMySwarmManagerActor,ActorToFollow,COND_InitialOnly);
	// DOREPLIFETIME_CONDITION(AMySwarmManagerActor,RotateNoiseOffsetSpeed,COND_InitialOnly);
	// DOREPLIFETIME_CONDITION(AMySwarmManagerActor,NoiseOffsetSpeed,COND_InitialOnly);
}

void AMySwarmManagerActor_v2::BeginPlay()
{
	Super::BeginPlay();
	
	//SplineComponentsBuild
	for (int32 i = 0; i < TotalNumOfSplinesToConstruct; i++)
	{
		USplineComponent* Spline = NewObject<USplineComponent>(this);
		Spline->RegisterComponent();
		// Spline->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepRelativeTransform);
		SplineComponents.Add(Spline);
	}
	
	if (HasAuthority())
	{
		TArray<AActor*> Characters;
		UGameplayStatics::GetAllActorsOfClass(this,AMyCharPlayer::StaticClass(),Characters);
		if (Characters.Num()==0)return;
		StartLocation=StartLocation+FVector(0,0,1);
		
		ActorToFollow=Characters[0];
		
		EndLocation=ActorToFollow->GetActorLocation();
		ConstructSplines(TotalNumOfSplinesToConstruct);
		// DebugDrawSpline();
		
		SpawnSwarmActors(1000);
	}
}


// Called every frame
void AMySwarmManagerActor_v2::Tick(float DeltaTime)
{
	if (!ActorToFollow)return;
	// {
	// 	UKismetSystemLibrary::PrintString(this,"No ActorToFollow Found on");
	// 	ENetRole NetRole=GetLocalRole();
	// 	FString Str=StaticEnum<ENetRole>()->GetNameStringByValue(NetRole);
	// 	UKismetSystemLibrary::PrintString(this,Str);
	// 	return;
	// }
	EndLocation=ActorToFollow->GetActorLocation();
	InterpedEndLocation= FMath::Lerp(InterpedEndLocation,EndLocation,.2);
	ConstructSplines(TotalNumOfSplinesToConstruct);
}

USplineComponent* AMySwarmManagerActor_v2::ConstructSpline(int32 Id)
{
	USplineComponent* SplineComponent= SplineComponents[Id];
	float RotateIdOffset=(static_cast<float>(Id))*RotateIdOffsetMult;
	float SpiralIdOffset=Id*SpiralIdOffsetMult;
	SplineComponent->ClearSplinePoints();
	SplineComponent->AddSplinePoint(StartLocation,ESplineCoordinateSpace::World,false);
	SplineComponent->AddSplinePoint(InterpedEndLocation,ESplineCoordinateSpace::World,true);
	int32 NumPoints=100;
	
	// make PointsArray
	TArray<FVector> Points;
	for (int i=0;i<=NumPoints;i++)
	{
		// const float YOffset=10000.f;
		float Length=SplineComponent->GetSplineLength();
		float CurrentPointDist=Length/NumPoints*i;
		float NormalizedPointDist=(float)i/float(NumPoints);
		
		//GetPosAndVecsAtCertainDist
		// FVector Right=SplineComponent->GetRightVectorAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		// FVector Up=SplineComponent->GetUpVectorAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		FVector Forward= SplineComponent->GetTangentAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		FVector PntPos=SplineComponent->GetLocationAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		
		//Will REdo
		//Noise
		float NoiseOffset= GetWorld()->GetTimeSeconds()*RotateNoiseOffsetSpeed;
		float NoiseX=FMath::PerlinNoise1D(CurrentPointDist*RotateNoiseFrequency+ NoiseOffset);
		NoiseX*=RotateNoiseAmplitude;
		
		float RotateRampedVal=RotateRamp.GetValueAtLevel(NormalizedPointDist);
		
		// Calculate rotation angle for Rotation
		NormalizedPointDist+=GetWorld()->GetTimeSeconds()*RotateOffsetSpeed+RotateIdOffset;
		float RotateAngle = NormalizedPointDist * RotateTurns * 2.f * PI; // full rotations
		float RotateRadius = RotateRadiusBase * RotateRampedVal;
		float RotateNoise= FMath::GetMappedRangeValueClamped(FVector2D(-1,1),FVector2D(.4,1),NoiseX);
		RotateRadius*=RotateNoise;
		
		// FVector RightFromStraightUp=FVector::CrossProduct(Forward,FVector(0,1,0));
		FVector ForwardWith0DeviationInZ= FVector(Forward.X,Forward.Y,0).GetSafeNormal();
		// Offset using forward/up vectors
		FVector RotateOffset = FMath::Cos(RotateAngle) * ForwardWith0DeviationInZ * RotateRadius+ FMath::Sin(RotateAngle) * FVector(0,1,0) * RotateRadius;
		
		// RotateOffset*=
		PntPos+=RotateOffset;
		
		Points.Add(PntPos);
		
		// DrawDebugSphere(GetWorld(),PntPos,30,10,FColor::Green,true,100.f);
	}
	
	SplineComponent->ClearSplinePoints();
	
	// Make New Spline with Points
	for (int i=0;i<Points.Num()-1;i++)
	{
		SplineComponent->AddSplinePoint(Points[i],ESplineCoordinateSpace::World,false);
	}
	
	Points.Empty();
	SplineComponent->UpdateSpline();
	
	NumPoints=1000;
	
	for (int i=0;i<NumPoints-1;i++)
	{
		// const float YOffset=10000.f;
		float Length=SplineComponent->GetSplineLength();
		float CurrentPointDist=Length/NumPoints*i;
		float NormalizedPointDist=(float)i/float(NumPoints);
		
		//GetPosAndVecsAtCertainDist
		FVector Right=SplineComponent->GetRightVectorAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		FVector Up=SplineComponent->GetUpVectorAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		FVector PntPos=SplineComponent->GetLocationAtDistanceAlongSpline(CurrentPointDist,ESplineCoordinateSpace::World);
		// float SplineKey=SplineComponent->GetInputKeyAtDistanceAlongSpline(CurrentPointDist);
		
		//Noise
		float NoiseOffset= GetWorld()->GetTimeSeconds()*SpiralNoiseOffsetSpeed;
		float NoiseX=FMath::PerlinNoise1D(CurrentPointDist*SpiralNoiseFrequency+ NoiseOffset);
		NoiseX*=SpiralNoiseAmplitude;
		
		float SpiralRampedVal=SpiralRamp.GetValueAtLevel(NormalizedPointDist);
		float EndsSnapRampedVal=EndsSnapRamp.GetValueAtLevel(NormalizedPointDist);
		// UKismetSystemLibrary::PrintString(this,std::to_string(MultRampedVal).c_str(),true,true,FLinearColor::Green,3);
		
		// Calculate rotation angle for Spiral
		NormalizedPointDist+=GetWorld()->GetTimeSeconds()*SpiralOffsetSpeed+SpiralIdOffset;
		float Angle2 = NormalizedPointDist * SpiralTurns * 2.f * PI; // full rotations
		float SpiralRadius = SpiralRadiusBase * SpiralRampedVal;
		float SpiralNoise= FMath::GetMappedRangeValueClamped(FVector2D(-1,1),FVector2D(.4,1),NoiseX);
		SpiralRadius*=SpiralNoise;
		
		// Offset using right/up vectors
		FVector SpiralOffset = FMath::Cos(Angle2) * Right * SpiralRadius+ FMath::Sin(Angle2) * Up * SpiralRadius;
		
		// FVector OrigPos=PntPos;
		
		PntPos+=SpiralOffset;
		PntPos=FMath::Lerp(PntPos,InterpedEndLocation,EndsSnapRampedVal);
		
		Points.Add(PntPos);
		
		// DrawDebugSphere(GetWorld(),PntPos,30,10,FColor::Green,true,100.f);
	}
	
	SplineComponent->ClearSplinePoints();
	
	// Make New Spline with Points
	for (int i=0;i<Points.Num()-1;i++)
	{
		SplineComponent->AddSplinePoint(Points[i],ESplineCoordinateSpace::World,false);
	}
	
	SplineComponent->UpdateSpline();
	
	
	bSplineConstructed=true;
	return SplineComponent;
}

void AMySwarmManagerActor_v2::ConstructSplines(int32 InNumSplines)
{
	for (int i=0;i<InNumSplines;i++)
	{
		USplineComponent* SplineComponent=ConstructSpline(i);
		SplineCount++;
		SplineComponents.Add(SplineComponent);
	}
}

void AMySwarmManagerActor_v2::SpawnSwarmActor(float InSpeed,int32 Id,int32 SplineToChoose)
{
	FTransform SpawnTransform;
	SpawnTransform.SetLocation(StartLocation);
	AMySwarmActor* MySwarmActor=GetWorld()->SpawnActorDeferred<AMySwarmActor>(SwarmActorClass,SpawnTransform);
	MySwarmActor->SplineToFollow=SplineComponents[SplineToChoose];
	MySwarmActor->Id=Id;
	MySwarmActor->Speed=InSpeed;
	MySwarmActor->FinishSpawning(SpawnTransform);
}

void AMySwarmManagerActor_v2::SpawnSwarmActors(int32 InCount)
{
	for (int i=0;i<InCount;i++)
	{
		int32 Id=SwarmCount;
		FRandomStream RandStream(Id);
		float Speed=RandStream.FRandRange(2000,4000);
		int32 SplineToChoose=RandStream.RandRange(0,SplineCount-1);
		// UKismetSystemLibrary::PrintString(GetWorld(),std::to_string(Speed).c_str(),true,true,FLinearColor::Green,3);
		// UKismetSystemLibrary::PrintString(GetWorld(),std::to_string(SplineToChoose).c_str(),true,true,FLinearColor::Green,3);
		
		SpawnSwarmActor(Speed,Id,SplineToChoose);
		SwarmCount++;
	}
}

void AMySwarmManagerActor_v2::OnRep_UpdateLocation()
{
	// UKismetSystemLibrary::PrintString(GetWorld(),StartLocation.ToString(),true,true,FLinearColor::Red,30);
	// UKismetSystemLibrary::PrintString(GetWorld(),EndLocation.ToString(),true,true,FLinearColor::Blue,30);
	ConstructSplines(TotalNumOfSplinesToConstruct);
	// for (int i=0;i<=10;i++)
	// {
	// 	SpawnSwarm();
	// }
}

