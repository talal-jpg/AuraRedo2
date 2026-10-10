// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/UserWidgets/MyHexMinimapWidget.h"

#include "Actors/MyHexMinimapSubsystem.h"
#include "Blueprint/WidgetTree.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/Image.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "Materials/MaterialInstanceDynamic.h"


namespace HexMinimapParams
{
	static const FName MapTexture(TEXT("MapTexture"));
	static const FName MapWindow(TEXT("MapWindow"));
	static const FName View(TEXT("View"));
	static const FName Height(TEXT("Height"));
	static const FName Players[] = { TEXT("Player0"), TEXT("Player1"), TEXT("Player2"), TEXT("Player3") };
}


UMyHexMinimapWidget::UMyHexMinimapWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	MinimapMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/UI/Minimap/M_HexMinimap.M_HexMinimap")));
}

void UMyHexMinimapWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();

	// Plain C++ widget: build the image ourselves
	if (!MinimapImage && WidgetTree && !WidgetTree->RootWidget)
	{
		MinimapImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("MinimapImage"));
		WidgetTree->RootWidget = MinimapImage;
	}

	if (!MinimapImage)
	{
		return;
	}

	MinimapImage->SetVisibility(ESlateVisibility::Hidden);

	if (UMaterialInterface* Material = MinimapMaterial.LoadSynchronous())
	{
		MaterialInstance = UMaterialInstanceDynamic::Create(Material, this);
		MinimapImage->SetBrushFromMaterial(MaterialInstance);
		MinimapImage->SetDesiredSizeOverride(FVector2D(MinimapSize));
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("MyHexMinimapWidget: MinimapMaterial %s could not be loaded"), *MinimapMaterial.ToString());
	}
}

void UMyHexMinimapWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	if (!MinimapImage || !MaterialInstance)
	{
		return;
	}

	const UWorld* World = GetWorld();
	const UMyHexMinimapSubsystem* Minimap = World ? World->GetSubsystem<UMyHexMinimapSubsystem>() : nullptr;
	const APlayerController* PlayerController = GetOwningPlayer();

	if (!Minimap || !Minimap->IsMinimapReady() || !PlayerController)
	{
		// Only the image hides: a hidden user widget would stop ticking
		MinimapImage->SetVisibility(ESlateVisibility::Hidden);
		return;
	}

	MinimapImage->SetVisibility(ESlateVisibility::HitTestInvisible);

	const APawn* LocalPawn = PlayerController->GetPawn();
	const APlayerCameraManager* Camera = PlayerController->PlayerCameraManager;

	const FVector Centre = LocalPawn ? LocalPawn->GetActorLocation() : (Camera ? Camera->GetCameraLocation() : FVector::ZeroVector);

	const double UpYaw = (bRotateWithCamera && Camera) ? Camera->GetCameraRotation().Yaw : 0.0;
	const double PawnYaw = LocalPawn ? LocalPawn->GetActorRotation().Yaw : UpYaw;

	MaterialInstance->SetTextureParameterValue(HexMinimapParams::MapTexture, Minimap->GetMinimapTexture());
	MaterialInstance->SetVectorParameterValue(HexMinimapParams::MapWindow, Minimap->GetWindowParam());

	MaterialInstance->SetVectorParameterValue(HexMinimapParams::View, FLinearColor(
		static_cast<float>(Centre.X),
		static_cast<float>(Centre.Y),
		ViewRadius * Minimap->GetLengthScale(),
		static_cast<float>(FMath::DegreesToRadians(UpYaw))
	));

	FLinearColor Height = Minimap->GetHeightParam();
	Height.B = static_cast<float>(Centre.Z);
	Height.A = static_cast<float>(FMath::DegreesToRadians(FRotator::NormalizeAxis(PawnYaw - UpYaw)));
	MaterialInstance->SetVectorParameterValue(HexMinimapParams::Height, Height);

	// Other players
	int32 Shown = 0;

	if (const AGameStateBase* GameState = World->GetGameState())
	{
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (Shown >= MaxOtherPlayers)
			{
				break;
			}

			const APawn* Pawn = PlayerState ? PlayerState->GetPawn() : nullptr;

			if (!Pawn || Pawn == LocalPawn)
			{
				continue;
			}

			const FVector Location = Pawn->GetActorLocation();

			MaterialInstance->SetVectorParameterValue(
				HexMinimapParams::Players[Shown++],
				FLinearColor(static_cast<float>(Location.X), static_cast<float>(Location.Y), 1.f, 0.f)
			);
		}
	}

	for (; Shown < MaxOtherPlayers; ++Shown)
	{
		MaterialInstance->SetVectorParameterValue(HexMinimapParams::Players[Shown], FLinearColor(0.f, 0.f, 0.f, 0.f));
	}
}
