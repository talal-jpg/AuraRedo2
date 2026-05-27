// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyPointCollectionActor.h"

#include "Components/BillboardComponent.h"
#include "Kismet/KismetSystemLibrary.h"


// Sets default values
AMyPointCollectionActor::AMyPointCollectionActor()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = false;
	Point1=CreateDefaultSubobject<USceneComponent>(TEXT("Point1"));
	Points.Add(Point1);
	SetRootComponent(Point1);
	
	Point2=CreateDefaultSubobject<USceneComponent>(TEXT("Point2"));
	Points.Add(Point2);
	Point2->SetupAttachment(Point1);
	
	Point3=CreateDefaultSubobject<USceneComponent>(TEXT("Point3"));
	Points.Add(Point3);
	Point3->SetupAttachment(Point1);
	
	Point4=CreateDefaultSubobject<USceneComponent>(TEXT("Point4"));
	Points.Add(Point4);
	Point4->SetupAttachment(Point1);
	
	Point5=CreateDefaultSubobject<USceneComponent>(TEXT("Point5"));
	Points.Add(Point5);
	Point5->SetupAttachment(Point1);
	
	Point6=CreateDefaultSubobject<USceneComponent>(TEXT("Point6"));
	Points.Add(Point6);
	Point6->SetupAttachment(Point1);
	
	BillboardPoint1=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard1"));
	BillboardPoint1->SetupAttachment(Point1);
	
	BillboardPoint2=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard2"));
	BillboardPoint2->SetupAttachment(Point2);
	
	BillboardPoint3=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard3"));
	BillboardPoint3->SetupAttachment(Point3);
	
	BillboardPoint4=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard4"));
	BillboardPoint4->SetupAttachment(Point4);
	
	BillboardPoint5=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard5"));
	BillboardPoint5->SetupAttachment(Point5);
	
	BillboardPoint6=CreateDefaultSubobject<UBillboardComponent>(TEXT("Billboard6"));
	BillboardPoint6->SetupAttachment(Point6);
}

TArray<USceneComponent*> AMyPointCollectionActor::GetPoints()
{
	for (auto Point:Points)
	{
		FVector TraceStart=Point->GetComponentLocation();
		FVector TraceEnd=Point->GetComponentLocation()+FVector(0,0,1000);
		TArray<AActor*> IgnoredActors;
		FHitResult HitResult;
		UKismetSystemLibrary::LineTraceSingle(this,TraceStart,TraceEnd,TraceTypeQuery1,false,IgnoredActors,EDrawDebugTrace::None,HitResult,true);
		if (HitResult.bBlockingHit)
		{
			Point->SetWorldLocation(HitResult.ImpactPoint);
		}
	}
	return Points;
}

void AMyPointCollectionActor::RotatePoints(float RandZRot)
{
	Point1->SetWorldRotation(FRotator(0,RandZRot,0));
}



