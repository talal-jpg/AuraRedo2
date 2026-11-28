// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyProjectile.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemInterface.h"
#include "NiagaraFunctionLibrary.h"
#include "Components/SphereComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Match/MyTeamLibrary.h"


// Sets default values
AMyProjectile::AMyProjectile()
{
	// Set this actor to call Tick() every frame.  You can turn this off to improve performance if you don't need it.
	PrimaryActorTick.bCanEverTick = false;
	CollisionSphere=CreateDefaultSubobject<USphereComponent>(TEXT("CollisionSphere"));
	ProjectileMovementComponent=CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("ProjectileMovementComponent"));	
	NiagaraComponent=CreateDefaultSubobject<UNiagaraComponent>(TEXT("NiagaraComponent"));
	
	SetRootComponent(CollisionSphere);
	NiagaraComponent->AttachToComponent(RootComponent,FAttachmentTransformRules::KeepRelativeTransform);
	
	ProjectileMovementComponent->InitialSpeed=1000.f;
	ProjectileMovementComponent->MaxSpeed=1000.;
	ProjectileMovementComponent->ProjectileGravityScale=0.f;
	ProjectileMovementComponent->bIsHomingProjectile=true;
	bReplicates=true;
	AActor::SetReplicateMovement(true);
}

// Called when the game starts or when spawned
void AMyProjectile::BeginPlay()
{
	Super::BeginPlay();
	// GA_Projectile spawns it without an instigator and the spec doesn't replicate: the caster from the spec's context
	// becomes the (replicated) instigator, so clients make the same team decision on overlap as the server
	if (HasAuthority() && !GetInstigator())
	{
		SetInstigator(Cast<APawn>(DamageEffectSpec.GetContext().GetInstigator()));
	}
	CollisionSphere->OnComponentBeginOverlap.AddDynamic(this,&ThisClass::OnSphereBeginOverlapCallback);
}

void AMyProjectile::OnSphereBeginOverlapCallback(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult & SweepResult)
{
	if (IAbilitySystemInterface* AbilityIF= Cast<IAbilitySystemInterface>(OtherActor))
	{
		// Match: a teammate (or his team's ship) is flown through, neither damaged nor stopping the fireball (no burst
		// either). The caster: the instigator (set in BeginPlay), else the spec's context
		const AActor* Caster=GetInstigator()?GetInstigator():DamageEffectSpec.GetContext().GetInstigator();
		if (UMyTeamLibrary::IsFriendlyFireBlocked(Caster,OtherActor))
		{
			return;
		}
		UAbilitySystemComponent* ASC=AbilityIF->GetAbilitySystemComponent();
		ASC->ApplyGameplayEffectSpecToSelf(DamageEffectSpec);
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(),BurstNiagaraSystem,GetActorLocation());
		Destroy();
	}
}



