#include "PCG/PCGHexPlatformTiles.h"

#include "Actors/MyHexPlatform.h"
#include "PCGComponent.h"
#include "PCGContext.h"
#include "PCGPin.h"
#include "PCGPoint.h"
#include "Data/PCGBasePointData.h"
#include "Helpers/PCGHelpers.h"
#include "Metadata/PCGMetadata.h"
#include "Metadata/PCGMetadataAttributeTpl.h"

#define LOCTEXT_NAMESPACE "PCGHexPlatformTiles"


TArray<FPCGPinProperties> UPCGHexPlatformTilesSettings::InputPinProperties() const
{
	// Reads the owning platform, no inputs
	return {};
}

FPCGElementPtr UPCGHexPlatformTilesSettings::CreateElement() const
{
	return MakeShared<FPCGHexPlatformTilesElement>();
}


bool FPCGHexPlatformTilesElement::ExecuteInternal(FPCGContext* Context) const
{
	TRACE_CPUPROFILER_EVENT_SCOPE(FPCGHexPlatformTilesElement::Execute);
	check(Context);

	const UPCGHexPlatformTilesSettings* Settings = Context->GetInputSettings<UPCGHexPlatformTilesSettings>();
	check(Settings);

	const UPCGComponent* PCGComponent = Cast<UPCGComponent>(Context->ExecutionSource.Get());
	const AMyHexPlatform* Platform = PCGComponent ? Cast<AMyHexPlatform>(PCGComponent->GetOwner()) : nullptr;

	if (!Platform)
	{
		PCGE_LOG(Warning, GraphAndLog, LOCTEXT("NoPlatform", "Hex Platform Tile Scatter only works on a PCG component owned by an AMyHexPlatform."));
		return true;
	}

	const TMap<FIntVector, FHexTileInfo>& Tiles = Platform->GetTileInfos();
	const FTransform ActorTransform = Platform->GetActorTransform();
	const float SizeScale = Platform->GetHexRadius() / 100.f;
	const int32 BaseSeed = Context->GetSeed();

	// Sorted so the output (and the per-tile seeds) don't depend on TMap order
	TArray<const FHexTileInfo*> SortedTiles;
	SortedTiles.Reserve(Tiles.Num());
	for (const TPair<FIntVector, FHexTileInfo>& Pair : Tiles)
	{
		SortedTiles.Add(&Pair.Value);
	}
	SortedTiles.Sort([](const FHexTileInfo& A, const FHexTileInfo& B) { return A.TileIndex < B.TileIndex; });

	struct FScatterPoint
	{
		FTransform Transform;
		int32 TileIndex;
		int32 EdgeDepth;
		bool bIsEdge;
		int32 Seed;
	};

	TArray<FScatterPoint> Points;

	for (const FHexTileInfo* Tile : SortedTiles)
	{
		const int32 TileSeed = PCGHelpers::ComputeSeed(BaseSeed, Tile->TileIndex);
		FRandomStream Stream(TileSeed);

		// Open sides of this tile (only edge tiles have any)
		TArray<int32, TInlineAllocator<6>> OpenSides;
		for (int32 Side = 0; Side < 6; ++Side)
		{
			if (Tile->OpenSideBits & (1 << Side))
			{
				OpenSides.Add(Side);
			}
		}

		const bool bIsEdge = OpenSides.Num() > 0;

		const float Falloff01 = FMath::Clamp(static_cast<float>(Tile->EdgeDepth) / static_cast<float>(FMath::Max(1, Settings->EdgeFalloffRings)), 0.f, 1.f);
		const float Chance = FMath::Lerp(Settings->EdgeChance, Settings->InnerChance, Falloff01);
		const int32 Attempts = bIsEdge ? Settings->EdgeAttemptsPerTile : Settings->InnerAttemptsPerTile;

		// Sides already used on this tile, so two edge props don't stack on the same side
		TArray<int32, TInlineAllocator<6>> FreeSides = OpenSides;

		for (int32 Attempt = 0; Attempt < Attempts; ++Attempt)
		{
			if (Stream.FRand() >= Chance)
			{
				continue;
			}

			FVector2D Offset2D;
			float BaseYaw;

			if (bIsEdge && FreeSides.Num() > 0)
			{
				// Towards an open side, jittered along it
				const int32 Pick = Stream.RandRange(0, FreeSides.Num() - 1);
				const FVector2D Out = AMyHexPlatform::GetHexSideDirection(FreeSides[Pick]);
				FreeSides.RemoveAtSwap(Pick);

				const FVector2D Along(-Out.Y, Out.X);
				const float Inset = Stream.FRandRange(Settings->EdgeInsetRange.X, Settings->EdgeInsetRange.Y);
				const float Side = Stream.FRandRange(-Settings->EdgeSideJitter, Settings->EdgeSideJitter);

				Offset2D = (Out * Inset + Along * Side) * Tile->Apothem;
				BaseYaw = Settings->bFaceOutward ? FMath::RadiansToDegrees(FMath::Atan2(Out.Y, Out.X)) : 0.f;
			}
			else
			{
				// Anywhere around the middle (sqrt for an even spread over the disc)
				const float Angle = Stream.FRandRange(0.f, 2.f * PI);
				const float Radius = FMath::Sqrt(Stream.FRand()) * Settings->InnerSpread * Tile->Apothem;

				Offset2D = FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * Radius;
				BaseYaw = 0.f;
			}

			const float Yaw = BaseYaw + Stream.FRandRange(-Settings->YawJitter, Settings->YawJitter);
			const float Pitch = Stream.FRandRange(-Settings->TiltJitter, Settings->TiltJitter);
			const float Roll = Stream.FRandRange(-Settings->TiltJitter, Settings->TiltJitter);
			const float Scale = Stream.FRandRange(Settings->ScaleRange.X, Settings->ScaleRange.Y) * SizeScale;

			const FVector LocalLocation(
				Tile->LocalTopCenter.X + Offset2D.X,
				Tile->LocalTopCenter.Y + Offset2D.Y,
				Tile->LocalTopCenter.Z + Settings->ZOffset * Scale
			);

			const FTransform LocalTransform(FRotator(Pitch, Yaw, Roll), LocalLocation, FVector(Scale));

			FScatterPoint& Point = Points.AddDefaulted_GetRef();
			Point.Transform = LocalTransform * ActorTransform;
			Point.TileIndex = Tile->TileIndex;
			Point.EdgeDepth = Tile->EdgeDepth;
			Point.bIsEdge = bIsEdge;
			Point.Seed = PCGHelpers::ComputeSeed(TileSeed, Attempt);
		}
	}

	// -------------------------------------------------------------------------
	// Output
	// -------------------------------------------------------------------------

	UPCGBasePointData* PointData = FPCGContext::NewPointData_AnyThread(Context);
	check(PointData);

	FPCGTaggedData& Output = Context->OutputData.TaggedData.Emplace_GetRef();
	Output.Data = PointData;

	UPCGMetadata* Metadata = PointData->MutableMetadata();
	FPCGMetadataAttribute<int32>* TileIndexAttr = Metadata->CreateAttribute<int32>(AMyHexPlatform::TileIndexAttributeName, INDEX_NONE, false, true);
	FPCGMetadataAttribute<int32>* EdgeDepthAttr = Metadata->CreateAttribute<int32>(TEXT("EdgeDepth"), 0, false, true);
	FPCGMetadataAttribute<bool>* IsEdgeAttr = Metadata->CreateAttribute<bool>(TEXT("IsEdge"), false, false, true);

	PointData->SetNumPoints(Points.Num(), /*bInitializeValues=*/false);
	PointData->AllocateProperties(EPCGPointNativeProperties::All);

	FPCGPointValueRanges OutRanges(PointData, /*bAllocate=*/false);

	const FVector Extent(Settings->PointExtent);

	for (int32 Index = 0; Index < Points.Num(); ++Index)
	{
		const FScatterPoint& Src = Points[Index];

		FPCGPoint Point;
		Point.Transform = Src.Transform;
		Point.BoundsMin = -Extent;
		Point.BoundsMax = Extent;
		Point.Density = 1.f;
		Point.Steepness = 0.5f;
		Point.Seed = Src.Seed;
		Point.MetadataEntry = Metadata->AddEntry();

		TileIndexAttr->SetValue(Point.MetadataEntry, Src.TileIndex);
		EdgeDepthAttr->SetValue(Point.MetadataEntry, Src.EdgeDepth);
		IsEdgeAttr->SetValue(Point.MetadataEntry, Src.bIsEdge);

		OutRanges.SetFromPoint(Index, Point);
	}

	return true;
}

#undef LOCTEXT_NAMESPACE
