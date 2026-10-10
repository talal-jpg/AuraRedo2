// Fill out your copyright notice in the Description page of Project Settings.


#include "Actors/MyHexMinimapSubsystem.h"

#include "Actors/MyHexBridge.h"
#include "Actors/MyHexMinimapSettings.h"
#include "Actors/MyHexPlatform.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"


namespace HexMinimap
{
	constexpr double Sqrt3 = 1.7320508075688772;
	constexpr double HalfSqrt3 = 0.8660254037844386;

	/** Past this many dirty rectangles in one flush they are drawn as their union. */
	constexpr int32 MaxRectsPerFlush = 16;

	/** Rounds fractional cube coordinates (axial Q, R) to the hex that contains them. */
	FIntPoint RoundAxial(double Q, double R)
	{
		const double S = -Q - R;

		double RQ = FMath::RoundToDouble(Q);
		double RR = FMath::RoundToDouble(R);
		const double RS = FMath::RoundToDouble(S);

		const double DQ = FMath::Abs(RQ - Q);
		const double DR = FMath::Abs(RR - R);
		const double DS = FMath::Abs(RS - S);

		if (DQ > DR && DQ > DS)
		{
			RQ = -RR - RS;
		}
		else if (DR > DS)
		{
			RR = -RQ - RS;
		}

		return FIntPoint(static_cast<int32>(RQ), static_cast<int32>(RR));
	}
}


// =============================================================================
// Subsystem
// =============================================================================

bool UMyHexMinimapSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	// A dedicated server never draws a minimap
	return Super::ShouldCreateSubsystem(Outer) && !IsRunningDedicatedServer();
}

bool UMyHexMinimapSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UMyHexMinimapSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
}

void UMyHexMinimapSubsystem::Deinitialize()
{
	for (TPair<TObjectKey<AMyHexPlatform>, FPlatformEntry>& Pair : Platforms)
	{
		if (AMyHexPlatform* Platform = Pair.Value.Platform.Get())
		{
			Platform->OnHexTileActivated.RemoveAll(this);
		}
	}

	Platforms.Empty();
	Bridges.Empty();
	DirtyRects.Empty();
	Pixels.Empty();
	Texture = nullptr;
	bWindowValid = false;

	Super::Deinitialize();
}

TStatId UMyHexMinimapSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UMyHexMinimapSubsystem, STATGROUP_Tickables);
}

bool UMyHexMinimapSubsystem::IsActive() const
{
	// PIE can run a dedicated server world in the same process as the clients
	const UWorld* World = GetWorld();
	return World && World->GetNetMode() != NM_DedicatedServer;
}

void UMyHexMinimapSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (!Texture)
	{
		return;
	}

	UpdateWindow();
	Flush();
}

FLinearColor UMyHexMinimapSubsystem::GetWindowParam() const
{
	return FLinearColor(
		static_cast<float>(WindowMin.X * CmPerPixel),
		static_cast<float>(WindowMin.Y * CmPerPixel),
		static_cast<float>(Size * CmPerPixel),
		0.f
	);
}

FLinearColor UMyHexMinimapSubsystem::GetHeightParam() const
{
	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();
	return FLinearColor(Settings.HeightMin, Settings.HeightMax, 0.f, 0.f);
}


// =============================================================================
// Platforms
// =============================================================================

void UMyHexMinimapSubsystem::RegisterPlatform(AMyHexPlatform* Platform)
{
	if (!IsValid(Platform) || !Platform->HexPillarsISM || !IsActive())
	{
		return;
	}

	// The first platform decides the scale, like the bridge planner
	if (LengthScale <= 0.f)
	{
		LengthScale = FMath::Max(Platform->HexRadius / 100.f, 0.01f);
	}

	if (!Texture)
	{
		FVector Focus;

		if (!GetFocus(Focus))
		{
			Focus = Platform->GetActorLocation();
		}

		InitTexture(Focus);
	}

	FPlatformEntry* Existing = Platforms.Find(Platform);

	if (Existing)
	{
		MarkDirty(Existing->Bounds);
	}

	FPlatformEntry& Entry = Existing ? *Existing : Platforms.Add(Platform);
	Entry = FPlatformEntry();
	Entry.Platform = Platform;

	const FTransform ActorTransform = Platform->GetActorTransform();
	const FVector ActorScale = ActorTransform.GetScale3D();
	const double YawRad = FMath::DegreesToRadians(ActorTransform.Rotator().Yaw);

	Entry.Origin = FVector2D(ActorTransform.GetLocation());
	Entry.YawCos = FMath::Cos(YawRad);
	Entry.YawSin = FMath::Sin(YawRad);
	Entry.Scale = FVector2D(
		FMath::Max(FMath::Abs(ActorScale.X), 1.e-4),
		FMath::Max(FMath::Abs(ActorScale.Y), 1.e-4)
	);
	Entry.InvScale = FVector2D(1.0 / Entry.Scale.X, 1.0 / Entry.Scale.Y);
	Entry.HexRadius = FMath::Max(static_cast<double>(Platform->HexRadius), 1.0);
	Entry.TileReach = Entry.HexRadius * FMath::Max(Entry.Scale.X, Entry.Scale.Y);
	Entry.GridSize = FMath::Max(Platform->GridSize, 0);
	Entry.Dim = Entry.GridSize * 2 + 1;
	Entry.Cells.Init(0, Entry.Dim * Entry.Dim);

	// Tile top = the pillar mesh's top through the instance's world transform
	const UStaticMesh* Mesh = Platform->HexPillarsISM->GetStaticMesh();
	const double MeshTop = Mesh ? Mesh->GetBounds().GetBox().Max.Z : 0.0;

	double MaxCentre = 0.0;

	// HexMap only holds live tiles: on a late-joining client the collapsed ones are already gone
	for (const TPair<FIntVector, int32>& Pair : Platform->HexMap)
	{
		const int32 Q = Pair.Key.X;
		const int32 R = Pair.Key.Y;

		if (FMath::Abs(Q) > Entry.GridSize || FMath::Abs(R) > Entry.GridSize)
		{
			continue;
		}

		double Top = ActorTransform.GetLocation().Z;
		FTransform InstanceTransform;

		if (Platform->HexPillarsISM->GetInstanceTransform(Pair.Value, InstanceTransform, /*bWorldSpace=*/true))
		{
			Top = InstanceTransform.TransformPosition(FVector(0.0, 0.0, MeshTop)).Z;
		}

		Entry.Cells[(Q + Entry.GridSize) + (R + Entry.GridSize) * Entry.Dim] = HeightByte(Top);

		MaxCentre = FMath::Max(MaxCentre, static_cast<double>(Platform->HexToWorld(Q, R, Entry.HexRadius).Size()));
	}

	const double Reach = MaxCentre * FMath::Max(Entry.Scale.X, Entry.Scale.Y) + Entry.TileReach;
	Entry.Bounds = FBox2D(Entry.Origin - FVector2D(Reach), Entry.Origin + FVector2D(Reach));

	Platform->OnHexTileActivated.RemoveAll(this);
	Platform->OnHexTileActivated.AddUObject(this, &ThisClass::OnTileActivated);

	MarkDirty(Entry.Bounds);
}

void UMyHexMinimapSubsystem::UnregisterPlatform(AMyHexPlatform* Platform)
{
	FPlatformEntry Entry;

	if (!Platforms.RemoveAndCopyValue(Platform, Entry))
	{
		return;
	}

	if (Platform)
	{
		Platform->OnHexTileActivated.RemoveAll(this);
	}

	MarkDirty(Entry.Bounds);
}

void UMyHexMinimapSubsystem::OnTileActivated(AMyHexPlatform* Platform, const FIntVector& Coord)
{
	FPlatformEntry* Entry = Platforms.Find(Platform);

	if (!Entry || FMath::Abs(Coord.X) > Entry->GridSize || FMath::Abs(Coord.Y) > Entry->GridSize)
	{
		return;
	}

	Entry->Cells[(Coord.X + Entry->GridSize) + (Coord.Y + Entry->GridSize) * Entry->Dim] = 0;

	// Tile centre, platform local -> world
	const double CX = HexMinimap::Sqrt3 * Entry->HexRadius * (Coord.X + Coord.Y * 0.5) * Entry->Scale.X;
	const double CY = 1.5 * Entry->HexRadius * Coord.Y * Entry->Scale.Y;

	const FVector2D Centre(
		Entry->Origin.X + CX * Entry->YawCos - CY * Entry->YawSin,
		Entry->Origin.Y + CX * Entry->YawSin + CY * Entry->YawCos
	);

	MarkDirty(FBox2D(Centre - FVector2D(Entry->TileReach), Centre + FVector2D(Entry->TileReach)));
}


// =============================================================================
// Bridges
// =============================================================================

void UMyHexMinimapSubsystem::RegisterBridge(AMyHexBridge* Bridge)
{
	if (!IsValid(Bridge) || !IsActive())
	{
		return;
	}

	const FMyHexBridgeEnds& Ends = Bridge->GetEnds();

	// A client can get here before the ends have replicated
	if (Ends.Start.Location.Equals(Ends.End.Location))
	{
		return;
	}

	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();

	FBridgeEntry* Existing = Bridges.Find(Bridge);

	if (Existing)
	{
		MarkDirty(Existing->Bounds);
	}

	FBridgeEntry& Entry = Existing ? *Existing : Bridges.Add(Bridge);
	Entry = FBridgeEntry();
	Entry.Bridge = Bridge;

	// Same curve as AMyHexBridge::ApplyEnds: one cubic Hermite segment, or a straight deck
	if (Ends.StartTangent.IsNearlyZero() && Ends.EndTangent.IsNearlyZero())
	{
		Entry.Points.Add(Ends.Start.Location);
		Entry.Points.Add(Ends.End.Location);
	}
	else
	{
		const int32 Segments = FMath::Clamp(Settings.BridgeSegments, 1, 32);

		for (int32 Index = 0; Index <= Segments; ++Index)
		{
			Entry.Points.Add(FMath::CubicInterp(
				Ends.Start.Location, Ends.StartTangent,
				Ends.End.Location, Ends.EndTangent,
				static_cast<double>(Index) / Segments
			));
		}
	}

	const AMyHexPlatform* EndPlatform = IsValid(Ends.Start.Platform) ? Ends.Start.Platform.Get() : Ends.End.Platform.Get();
	const double HexRadius = IsValid(EndPlatform) ? EndPlatform->HexRadius : 100.0 * GetLengthScale();

	Entry.HalfWidth = FMath::Max(0.5 * Settings.BridgeWidthInHexRadii * HexRadius, 1.0);

	for (const FVector& Point : Entry.Points)
	{
		Entry.Bounds += FVector2D(Point);
	}

	Entry.Bounds = Entry.Bounds.ExpandBy(Entry.HalfWidth);

	MarkDirty(Entry.Bounds);
}

void UMyHexMinimapSubsystem::UnregisterBridge(AMyHexBridge* Bridge)
{
	FBridgeEntry Entry;

	if (Bridges.RemoveAndCopyValue(Bridge, Entry))
	{
		MarkDirty(Entry.Bounds);
	}
}


// =============================================================================
// Window
// =============================================================================

void UMyHexMinimapSubsystem::InitTexture(const FVector& Focus)
{
	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();

	Size = FMath::Clamp(Settings.TextureSize, 64, 4096);
	CmPerPixel = FMath::Max(Settings.CmPerPixel, 1.f) * GetLengthScale();

	Pixels.Init(FColor(0, 0, 0, 0), Size * Size);

	Texture = UTexture2D::CreateTransient(Size, Size, PF_B8G8R8A8, TEXT("HexMinimap"));

	if (!Texture)
	{
		return;
	}

	// Data, not colour; wraps so the window can scroll without moving pixels
	Texture->SRGB = false;
	Texture->CompressionSettings = TC_VectorDisplacementmap;
	Texture->Filter = TF_Bilinear;
	Texture->AddressX = TA_Wrap;
	Texture->AddressY = TA_Wrap;
	Texture->NeverStream = true;
	Texture->UpdateResource();

	WindowMin = FIntPoint(
		FMath::FloorToInt32(Focus.X / CmPerPixel) - Size / 2,
		FMath::FloorToInt32(Focus.Y / CmPerPixel) - Size / 2
	);
	bWindowValid = true;

	// Everything registered so far is in here
	DirtyRects.Reset();
	DirtyRects.Add(FIntRect(WindowMin, WindowMin + FIntPoint(Size)));

	// Draw the first window right away
	LastUploadTime = -1.e9;
}

bool UMyHexMinimapSubsystem::GetFocus(FVector& OutFocus) const
{
	const UWorld* World = GetWorld();
	const APlayerController* PlayerController = World ? World->GetFirstPlayerController() : nullptr;

	if (!PlayerController || !PlayerController->IsLocalController())
	{
		return false;
	}

	if (const APawn* Pawn = PlayerController->GetPawn())
	{
		OutFocus = Pawn->GetActorLocation();
		return true;
	}

	if (PlayerController->PlayerCameraManager)
	{
		OutFocus = PlayerController->PlayerCameraManager->GetCameraLocation();
		return true;
	}

	return false;
}

void UMyHexMinimapSubsystem::UpdateWindow()
{
	FVector Focus;

	if (!GetFocus(Focus))
	{
		return;
	}

	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();

	const FIntPoint FocusTexel(
		FMath::FloorToInt32(Focus.X / CmPerPixel),
		FMath::FloorToInt32(Focus.Y / CmPerPixel)
	);

	const int32 Half = Size / 2;
	const int32 Threshold = FMath::Max(1, FMath::RoundToInt32(Size * Settings.RecenterFraction));

	FIntPoint NewMin = WindowMin;

	if (FMath::Abs(FocusTexel.X - (WindowMin.X + Half)) > Threshold)
	{
		NewMin.X = FocusTexel.X - Half;
	}

	if (FMath::Abs(FocusTexel.Y - (WindowMin.Y + Half)) > Threshold)
	{
		NewMin.Y = FocusTexel.Y - Half;
	}

	if (NewMin == WindowMin)
	{
		return;
	}

	const FIntRect Old(WindowMin, WindowMin + FIntPoint(Size));
	const FIntRect New(NewMin, NewMin + FIntPoint(Size));

	WindowMin = NewMin;

	if (!Old.Intersect(New))
	{
		DirtyRects.Add(New);
		return;
	}

	// The texture wraps, so only the strips that scrolled in need drawing
	if (New.Min.X < Old.Min.X)
	{
		DirtyRects.Add(FIntRect(New.Min.X, New.Min.Y, Old.Min.X, New.Max.Y));
	}
	else if (New.Max.X > Old.Max.X)
	{
		DirtyRects.Add(FIntRect(Old.Max.X, New.Min.Y, New.Max.X, New.Max.Y));
	}

	if (New.Min.Y < Old.Min.Y)
	{
		DirtyRects.Add(FIntRect(New.Min.X, New.Min.Y, New.Max.X, Old.Min.Y));
	}
	else if (New.Max.Y > Old.Max.Y)
	{
		DirtyRects.Add(FIntRect(New.Min.X, Old.Max.Y, New.Max.X, New.Max.Y));
	}
}

FIntRect UMyHexMinimapSubsystem::WorldToTexels(const FVector2D& Min, const FVector2D& Max) const
{
	return FIntRect(
		FMath::FloorToInt32(Min.X / CmPerPixel),
		FMath::FloorToInt32(Min.Y / CmPerPixel),
		FMath::FloorToInt32(Max.X / CmPerPixel) + 1,
		FMath::FloorToInt32(Max.Y / CmPerPixel) + 1
	);
}

void UMyHexMinimapSubsystem::MarkDirty(const FBox2D& WorldBox)
{
	// Before the texture exists the first window redraws everything anyway
	if (!Texture || !WorldBox.bIsValid)
	{
		return;
	}

	DirtyRects.Add(WorldToTexels(WorldBox.Min, WorldBox.Max));
}

uint8 UMyHexMinimapSubsystem::HeightByte(double Z) const
{
	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();
	const double Range = FMath::Max(static_cast<double>(Settings.HeightMax - Settings.HeightMin), 1.0);
	const double Alpha = FMath::Clamp((Z - Settings.HeightMin) / Range, 0.0, 1.0);

	return static_cast<uint8>(1 + FMath::RoundToInt32(Alpha * 254.0));
}


// =============================================================================
// Drawing
// =============================================================================

void UMyHexMinimapSubsystem::Flush()
{
	if (DirtyRects.IsEmpty() || !Texture)
	{
		return;
	}

	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;
	const UMyHexMinimapSettings& Settings = *GetDefault<UMyHexMinimapSettings>();

	if (Now - LastUploadTime < Settings.UpdateInterval)
	{
		return;
	}

	LastUploadTime = Now;

	// Clip to the window: anything outside it is drawn when it scrolls in
	const FIntRect Window(WindowMin, WindowMin + FIntPoint(Size));

	TArray<FIntRect, TInlineAllocator<HexMinimap::MaxRectsPerFlush>> Rects;
	FIntRect Union;
	bool bHasUnion = false;

	for (FIntRect Rect : DirtyRects)
	{
		Rect.Clip(Window);

		if (Rect.Width() <= 0 || Rect.Height() <= 0)
		{
			continue;
		}

		Rects.Add(Rect);

		if (bHasUnion)
		{
			Union.Union(Rect);
		}
		else
		{
			Union = Rect;
			bHasUnion = true;
		}
	}

	DirtyRects.Reset();

	if (Rects.Num() > HexMinimap::MaxRectsPerFlush)
	{
		Rects.Reset();
		Rects.Add(Union);
	}

	for (const FIntRect& Rect : Rects)
	{
		RasterRect(Rect);

		// A rectangle can wrap past the texture edge: up to two pieces per axis
		const int32 X0 = Wrap(Rect.Min.X);
		const int32 Y0 = Wrap(Rect.Min.Y);
		const int32 W0 = FMath::Min(Rect.Width(), Size - X0);
		const int32 H0 = FMath::Min(Rect.Height(), Size - Y0);

		const FIntRect Pieces[4] = {
			FIntRect(X0, Y0, X0 + W0, Y0 + H0),
			FIntRect(0, Y0, Rect.Width() - W0, Y0 + H0),
			FIntRect(X0, 0, X0 + W0, Rect.Height() - H0),
			FIntRect(0, 0, Rect.Width() - W0, Rect.Height() - H0)
		};

		for (const FIntRect& Piece : Pieces)
		{
			const int32 Width = Piece.Width();
			const int32 Height = Piece.Height();

			if (Width <= 0 || Height <= 0)
			{
				continue;
			}

			// The render thread reads the data later, so it gets its own copy of just this piece
			FColor* Data = static_cast<FColor*>(FMemory::Malloc(sizeof(FColor) * Width * Height));

			for (int32 Row = 0; Row < Height; ++Row)
			{
				FMemory::Memcpy(
					Data + Row * Width,
					Pixels.GetData() + (Piece.Min.Y + Row) * Size + Piece.Min.X,
					sizeof(FColor) * Width
				);
			}

			FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(Piece.Min.X, Piece.Min.Y, 0, 0, Width, Height);

			Texture->UpdateTextureRegions(
				0, 1, Region,
				sizeof(FColor) * Width, sizeof(FColor),
				reinterpret_cast<uint8*>(Data),
				[](uint8* SrcData, const FUpdateTextureRegion2D* Regions)
				{
					FMemory::Free(SrcData);
					delete Regions;
				}
			);
		}
	}
}

void UMyHexMinimapSubsystem::RasterRect(const FIntRect& Rect)
{
	// Clear
	for (int32 GY = Rect.Min.Y; GY < Rect.Max.Y; ++GY)
	{
		FColor* Row = Pixels.GetData() + Wrap(GY) * Size;

		for (int32 GX = Rect.Min.X; GX < Rect.Max.X; ++GX)
		{
			Row[Wrap(GX)] = FColor(0, 0, 0, 0);
		}
	}

	const FBox2D RectWorld(
		FVector2D(Rect.Min.X * CmPerPixel, Rect.Min.Y * CmPerPixel),
		FVector2D(Rect.Max.X * CmPerPixel, Rect.Max.Y * CmPerPixel)
	);

	// The part of Rect that Box covers, in global texels
	auto Overlap = [this, &Rect](const FBox2D& Box)
	{
		FIntRect Sub = WorldToTexels(Box.Min, Box.Max);
		Sub.Clip(Rect);
		return Sub;
	};

	// -------------------------------------------------------------------------
	// Tiles: every pixel finds its hex by rounding, so the cost is per pixel, not per tile
	// -------------------------------------------------------------------------

	for (const TPair<TObjectKey<AMyHexPlatform>, FPlatformEntry>& Pair : Platforms)
	{
		const FPlatformEntry& Entry = Pair.Value;

		if (!Entry.Bounds.Intersect(RectWorld))
		{
			continue;
		}

		const FIntRect Sub = Overlap(Entry.Bounds);
		const double R = Entry.HexRadius;
		const double InvRowStep = 1.0 / (1.5 * R);
		const double InvColStep = 1.0 / (HexMinimap::Sqrt3 * R);
		const double InvInner = 1.0 / (HexMinimap::HalfSqrt3 * R);

		for (int32 GY = Sub.Min.Y; GY < Sub.Max.Y; ++GY)
		{
			FColor* Row = Pixels.GetData() + Wrap(GY) * Size;
			const double DY = (GY + 0.5) * CmPerPixel - Entry.Origin.Y;

			for (int32 GX = Sub.Min.X; GX < Sub.Max.X; ++GX)
			{
				const double DX = (GX + 0.5) * CmPerPixel - Entry.Origin.X;

				// World -> platform local
				const double LX = (DX * Entry.YawCos + DY * Entry.YawSin) * Entry.InvScale.X;
				const double LY = (-DX * Entry.YawSin + DY * Entry.YawCos) * Entry.InvScale.Y;

				// Inverse of AMyHexPlatform::HexToWorld
				const double FR = LY * InvRowStep;
				const double FQ = LX * InvColStep - FR * 0.5;
				const FIntPoint Hex = HexMinimap::RoundAxial(FQ, FR);

				if (FMath::Abs(Hex.X) > Entry.GridSize || FMath::Abs(Hex.Y) > Entry.GridSize)
				{
					continue;
				}

				const uint8 Height = Entry.Cells[(Hex.X + Entry.GridSize) + (Hex.Y + Entry.GridSize) * Entry.Dim];

				if (Height == 0)
				{
					continue;
				}

				// Distance to the tile's edge, 0 at its centre, 1 on its sides (sides face +-X, +-60 deg)
				const double TX = LX - HexMinimap::Sqrt3 * R * (Hex.X + Hex.Y * 0.5);
				const double TY = LY - 1.5 * R * Hex.Y;
				const double EdgeDistance = FMath::Max3(
					FMath::Abs(TX),
					FMath::Abs(0.5 * TX + HexMinimap::HalfSqrt3 * TY),
					FMath::Abs(0.5 * TX - HexMinimap::HalfSqrt3 * TY)
				) * InvInner;

				FColor& Pixel = Row[Wrap(GX)];
				Pixel.R = 255;
				Pixel.A = static_cast<uint8>(FMath::RoundToInt32(255.0 * (1.0 - FMath::Clamp(EdgeDistance, 0.0, 1.0))));
				Pixel.B = FMath::Max(Pixel.B, Height);
			}
		}
	}

	// -------------------------------------------------------------------------
	// Bridges: distance to the deck polyline
	// -------------------------------------------------------------------------

	for (const TPair<TObjectKey<AMyHexBridge>, FBridgeEntry>& Pair : Bridges)
	{
		const FBridgeEntry& Entry = Pair.Value;

		if (Entry.Points.Num() < 2 || !Entry.Bounds.Intersect(RectWorld))
		{
			continue;
		}

		const FIntRect Sub = Overlap(Entry.Bounds);
		const double HalfWidthSq = Entry.HalfWidth * Entry.HalfWidth;

		for (int32 GY = Sub.Min.Y; GY < Sub.Max.Y; ++GY)
		{
			FColor* Row = Pixels.GetData() + Wrap(GY) * Size;
			const double PY = (GY + 0.5) * CmPerPixel;

			for (int32 GX = Sub.Min.X; GX < Sub.Max.X; ++GX)
			{
				const FVector2D P((GX + 0.5) * CmPerPixel, PY);

				double BestSq = HalfWidthSq;
				double BestZ = 0.0;
				bool bHit = false;

				for (int32 Index = 1; Index < Entry.Points.Num(); ++Index)
				{
					const FVector& A = Entry.Points[Index - 1];
					const FVector& B = Entry.Points[Index];
					const FVector2D A2(A);
					const FVector2D AB = FVector2D(B) - A2;
					const double LenSq = AB.SizeSquared();
					const double T = LenSq > UE_SMALL_NUMBER ? FMath::Clamp(FVector2D::DotProduct(P - A2, AB) / LenSq, 0.0, 1.0) : 0.0;
					const double DistSq = FVector2D::DistSquared(P, A2 + AB * T);

					if (DistSq < BestSq)
					{
						BestSq = DistSq;
						BestZ = FMath::Lerp(A.Z, B.Z, T);
						bHit = true;
					}
				}

				if (!bHit)
				{
					continue;
				}

				FColor& Pixel = Row[Wrap(GX)];
				const double Centre = 1.0 - FMath::Sqrt(BestSq) / Entry.HalfWidth;
				Pixel.G = FMath::Max<uint8>(Pixel.G, static_cast<uint8>(FMath::Clamp(FMath::RoundToInt32(255.0 * Centre), 1, 255)));
				Pixel.B = FMath::Max(Pixel.B, HeightByte(BestZ));
			}
		}
	}
}
