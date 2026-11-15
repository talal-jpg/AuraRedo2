#include "PCG/PCGHexPlatformTiles.h"

#include "Actors/MyHexPlatform.h"
#include "Engine/StaticMesh.h"
#include "PCGComponent.h"
#include "PCGContext.h"
#include "PCGPin.h"
#include "PCGPoint.h"
#include "Data/PCGBasePointData.h"
#include "Helpers/PCGHelpers.h"
#include "Metadata/PCGMetadata.h"
#include "Metadata/PCGMetadataAttributeTpl.h"

#define LOCTEXT_NAMESPACE "PCGHexPlatformTiles"

namespace PCGHexPlatformTilesConstants
{
	static const FName PathPinLabel = TEXT("Path");
	static const FName PavingPinLabel = TEXT("Paving");
	static const FName LampPinLabel = TEXT("Lamp");
	static const FName PathDistanceAttributeName = TEXT("PathDistance");
}


TArray<FPCGPinProperties> UPCGHexPlatformTilesSettings::InputPinProperties() const
{
	// Reads the owning platform, no inputs
	return {};
}

TArray<FPCGPinProperties> UPCGHexPlatformTilesSettings::OutputPinProperties() const
{
	TArray<FPCGPinProperties> Properties;
	Properties.Emplace(PCGPinConstants::DefaultOutputLabel, EPCGDataType::Point);
	Properties.Emplace(PCGHexPlatformTilesConstants::PathPinLabel, EPCGDataType::Point);
	Properties.Emplace(PCGHexPlatformTilesConstants::PavingPinLabel, EPCGDataType::Point);
	Properties.Emplace(PCGHexPlatformTilesConstants::LampPinLabel, EPCGDataType::Point);
	return Properties;
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
		int32 PathDistance;
		int32 Seed;
	};

	TArray<FScatterPoint> Points;
	TArray<FScatterPoint> PathPoints;

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

		// One point per path tile: top centre, X along the path
		if (Tile->PathDistance == 0)
		{
			const float PathYaw = FMath::RadiansToDegrees(FMath::Atan2(Tile->PathDirection.Y, Tile->PathDirection.X));

			FScatterPoint& PathPoint = PathPoints.AddDefaulted_GetRef();
			PathPoint.Transform = FTransform(FRotator(0.f, PathYaw, 0.f), Tile->LocalTopCenter, FVector(SizeScale)) * ActorTransform;
			PathPoint.TileIndex = Tile->TileIndex;
			PathPoint.EdgeDepth = Tile->EdgeDepth;
			PathPoint.bIsEdge = bIsEdge;
			PathPoint.PathDistance = 0;
			PathPoint.Seed = PCGHelpers::ComputeSeed(TileSeed, -1);
		}

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
			Point.PathDistance = Tile->PathDistance;
			Point.Seed = PCGHelpers::ComputeSeed(TileSeed, Attempt);
		}
	}

	// -------------------------------------------------------------------------
	// Output
	// -------------------------------------------------------------------------

	const FVector PointExtent(Settings->PointExtent);

	auto WritePoints = [Context](const TArray<FScatterPoint>& Source, FName PinLabel, TFunctionRef<FVector(const FScatterPoint&)> GetExtent)
	{
		UPCGBasePointData* PointData = FPCGContext::NewPointData_AnyThread(Context);
		check(PointData);

		FPCGTaggedData& Output = Context->OutputData.TaggedData.Emplace_GetRef();
		Output.Data = PointData;
		Output.Pin = PinLabel;

		UPCGMetadata* Metadata = PointData->MutableMetadata();
		FPCGMetadataAttribute<int32>* TileIndexAttr = Metadata->CreateAttribute<int32>(AMyHexPlatform::TileIndexAttributeName, INDEX_NONE, false, true);
		FPCGMetadataAttribute<int32>* EdgeDepthAttr = Metadata->CreateAttribute<int32>(TEXT("EdgeDepth"), 0, false, true);
		FPCGMetadataAttribute<bool>* IsEdgeAttr = Metadata->CreateAttribute<bool>(TEXT("IsEdge"), false, false, true);
		FPCGMetadataAttribute<int32>* PathDistanceAttr = Metadata->CreateAttribute<int32>(PCGHexPlatformTilesConstants::PathDistanceAttributeName, MAX_int32, false, true);

		PointData->SetNumPoints(Source.Num(), /*bInitializeValues=*/false);
		PointData->AllocateProperties(EPCGPointNativeProperties::All);

		FPCGPointValueRanges OutRanges(PointData, /*bAllocate=*/false);

		for (int32 Index = 0; Index < Source.Num(); ++Index)
		{
			const FScatterPoint& Src = Source[Index];
			const FVector Extent = GetExtent(Src);

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
			PathDistanceAttr->SetValue(Point.MetadataEntry, Src.PathDistance);

			OutRanges.SetFromPoint(Index, Point);
		}
	};

	WritePoints(Points, PCGPinConstants::DefaultOutputLabel, [&PointExtent](const FScatterPoint&) { return PointExtent; });

	// Path points cover their tile (bounds are before the point's scale)
	const float PathHalfSize = SizeScale > UE_KINDA_SMALL_NUMBER && !Tiles.IsEmpty() ? Tiles.CreateConstIterator()->Value.Apothem / SizeScale : 50.f;
	WritePoints(PathPoints, PCGHexPlatformTilesConstants::PathPinLabel, [PathHalfSize](const FScatterPoint&) { return FVector(PathHalfSize, PathHalfSize, 10.f); });

	// -------------------------------------------------------------------------
	// Paving: the platform's stones on the tiles still standing
	// -------------------------------------------------------------------------

	{
		UPCGBasePointData* PointData = FPCGContext::NewPointData_AnyThread(Context);
		check(PointData);

		FPCGTaggedData& Output = Context->OutputData.TaggedData.Emplace_GetRef();
		Output.Data = PointData;
		Output.Pin = PCGHexPlatformTilesConstants::PavingPinLabel;

		UPCGMetadata* Metadata = PointData->MutableMetadata();
		FPCGMetadataAttribute<int32>* TileIndexAttr = Metadata->CreateAttribute<int32>(AMyHexPlatform::TileIndexAttributeName, INDEX_NONE, false, true);
		FPCGMetadataAttribute<int32>* EdgeDepthAttr = Metadata->CreateAttribute<int32>(TEXT("EdgeDepth"), 0, false, true);
		FPCGMetadataAttribute<bool>* IsEdgeAttr = Metadata->CreateAttribute<bool>(TEXT("IsEdge"), false, false, true);
		FPCGMetadataAttribute<int32>* PathDistanceAttr = Metadata->CreateAttribute<int32>(PCGHexPlatformTilesConstants::PathDistanceAttributeName, 0, false, true);
		FPCGMetadataAttribute<int32>* ShapeAttr = Metadata->CreateAttribute<int32>(TEXT("SlabShape"), 0, false, true);
		FPCGMetadataAttribute<FVector2D>* SizeAttr = Metadata->CreateAttribute<FVector2D>(TEXT("SlabSize"), FVector2D::ZeroVector, false, true);
		FPCGMetadataAttribute<int32>* PatternAttr = Metadata->CreateAttribute<int32>(TEXT("PavingPattern"), 0, false, true);
		FPCGMetadataAttribute<FSoftObjectPath>* MeshAttr = Metadata->CreateAttribute<FSoftObjectPath>(TEXT("Mesh"), FSoftObjectPath(), false, true);
		FPCGMetadataAttribute<float>* BendXAttr = Metadata->CreateAttribute<float>(TEXT("SlabBendX"), 0.f, false, true);
		FPCGMetadataAttribute<float>* BendYAttr = Metadata->CreateAttribute<float>(TEXT("SlabBendY"), 0.f, false, true);

		const TArray<FHexPavingSlab>& Slabs = Platform->GetPavingSlabs();
		const double PlatformCellSize = Platform->GetPavingCellSize();
		const double MeshCellSize = FMath::Max(1.0, static_cast<double>(Settings->PavingMeshCellSize));
		const double SlabScale = PlatformCellSize / MeshCellSize;

		// The slabs' curvature is in actor space; the material bends in world space (a mirrored actor bends the
		// same way, its stones' axes mirror with it)
		const double ActorScale = FMath::Max(FMath::Abs(ActorTransform.GetScale3D().X), 1.e-4);

		// Only stones on tiles that are still standing
		TArray<const FHexPavingSlab*> LiveSlabs;
		LiveSlabs.Reserve(Slabs.Num());

		for (const FHexPavingSlab& Slab : Slabs)
		{
			if (Tiles.Contains(Slab.Tile))
			{
				LiveSlabs.Add(&Slab);
			}
		}

		PointData->SetNumPoints(LiveSlabs.Num(), /*bInitializeValues=*/false);
		PointData->AllocateProperties(EPCGPointNativeProperties::All);

		FPCGPointValueRanges OutRanges(PointData, /*bAllocate=*/false);

		for (int32 Index = 0; Index < LiveSlabs.Num(); ++Index)
		{
			const FHexPavingSlab& Slab = *LiveSlabs[Index];
			const FHexTileInfo& Tile = Tiles.FindChecked(Slab.Tile);
			const int32 Seed = PCGHelpers::ComputeSeed(BaseSeed, Slab.Seed);
			FRandomStream Stream(Seed);

			const float Yaw = Slab.Yaw + Stream.FRandRange(-Settings->PavingYawJitter, Settings->PavingYawJitter);
			const float Pitch = Stream.FRandRange(-Settings->PavingTiltJitter, Settings->PavingTiltJitter);
			const float Roll = Stream.FRandRange(-Settings->PavingTiltJitter, Settings->PavingTiltJitter);
			const double ZOffset = (Settings->PavingZOffset + Stream.FRandRange(-Settings->PavingHeightJitter, Settings->PavingHeightJitter)) * SlabScale;

			// Stretched (or trimmed) stones scale along their own axes; the height stays
			const FTransform LocalTransform(FRotator(Pitch, Yaw, Roll), Slab.Location + FVector(0.0, 0.0, ZOffset), FVector(SlabScale * Slab.Scale.X, SlabScale * Slab.Scale.Y, SlabScale));

			const bool bSmall = Slab.Size == FIntPoint(1, 1);
			const bool bLong = Slab.Size == FIntPoint(2, 1);
			const bool bBig = Slab.Size == FIntPoint(2, 2);
			const int32 Shape = bSmall ? 0 : bLong ? 1 : bBig ? 2 : 3;

			const TArray<TSoftObjectPtr<UStaticMesh>>* Meshes = bSmall ? &Settings->SmallSlabMeshes : bLong ? &Settings->LongSlabMeshes : bBig ? &Settings->BigSlabMeshes : nullptr;
			const FSoftObjectPath MeshPath = Meshes && !Meshes->IsEmpty() ? (*Meshes)[Stream.RandRange(0, Meshes->Num() - 1)].ToSoftObjectPath() : FSoftObjectPath();

			// Bounds = the stone before scale (a 1x1 mesh is PavingMeshCellSize wide)
			const FVector Extent(Slab.Size.X * MeshCellSize * 0.5, Slab.Size.Y * MeshCellSize * 0.5, 5.0);

			FPCGPoint Point;
			Point.Transform = LocalTransform * ActorTransform;
			Point.BoundsMin = -Extent;
			Point.BoundsMax = Extent;
			Point.Density = 1.f;
			Point.Steepness = 0.5f;
			Point.Seed = Seed;
			Point.MetadataEntry = Metadata->AddEntry();

			TileIndexAttr->SetValue(Point.MetadataEntry, Slab.TileIndex);
			EdgeDepthAttr->SetValue(Point.MetadataEntry, Tile.EdgeDepth);
			IsEdgeAttr->SetValue(Point.MetadataEntry, Tile.OpenSideBits != 0);
			PathDistanceAttr->SetValue(Point.MetadataEntry, Tile.PathDistance);
			ShapeAttr->SetValue(Point.MetadataEntry, Shape);
			SizeAttr->SetValue(Point.MetadataEntry, FVector2D(Slab.Size.X * PlatformCellSize * Slab.Scale.X, Slab.Size.Y * PlatformCellSize * Slab.Scale.Y));
			PatternAttr->SetValue(Point.MetadataEntry, Slab.Pattern);
			MeshAttr->SetValue(Point.MetadataEntry, MeshPath);
			BendXAttr->SetValue(Point.MetadataEntry, static_cast<float>(Slab.Bend.X / ActorScale));
			BendYAttr->SetValue(Point.MetadataEntry, static_cast<float>(Slab.Bend.Y / ActorScale));

			OutRanges.SetFromPoint(Index, Point);
		}
	}

	// -------------------------------------------------------------------------
	// Lamp: the middle of the plaza the paths meet in, while its tile stands
	// -------------------------------------------------------------------------

	{
		UPCGBasePointData* PointData = FPCGContext::NewPointData_AnyThread(Context);
		check(PointData);

		FPCGTaggedData& Output = Context->OutputData.TaggedData.Emplace_GetRef();
		Output.Data = PointData;
		Output.Pin = PCGHexPlatformTilesConstants::LampPinLabel;

		UPCGMetadata* Metadata = PointData->MutableMetadata();
		FPCGMetadataAttribute<int32>* TileIndexAttr = Metadata->CreateAttribute<int32>(AMyHexPlatform::TileIndexAttributeName, INDEX_NONE, false, true);
		FPCGMetadataAttribute<int32>* SidesAttr = Metadata->CreateAttribute<int32>(TEXT("PlazaSides"), 0, false, true);
		FPCGMetadataAttribute<float>* SideLengthAttr = Metadata->CreateAttribute<float>(TEXT("PlazaSideLength"), 0.f, false, true);

		const FHexPathPlaza& Plaza = Platform->GetPathPlaza();
		const bool bLamp = Plaza.bValid && Tiles.Contains(Plaza.Tile);

		PointData->SetNumPoints(bLamp ? 1 : 0, /*bInitializeValues=*/false);
		PointData->AllocateProperties(EPCGPointNativeProperties::All);

		if (bLamp)
		{
			FPCGPointValueRanges OutRanges(PointData, /*bAllocate=*/false);

			// X faces out through the plaza's side 0
			const FVector Location = Plaza.Centre + FVector(0.0, 0.0, Settings->LampZOffset * SizeScale);
			const FTransform LocalTransform(FRotator(0.f, Plaza.Yaw, 0.f), Location, Settings->LampScale * SizeScale);

			FPCGPoint Point;
			Point.Transform = LocalTransform * ActorTransform;
			Point.BoundsMin = -Settings->LampExtent;
			Point.BoundsMax = Settings->LampExtent;
			Point.Density = 1.f;
			Point.Steepness = 0.5f;
			Point.Seed = PCGHelpers::ComputeSeed(BaseSeed, Plaza.TileIndex);
			Point.MetadataEntry = Metadata->AddEntry();

			TileIndexAttr->SetValue(Point.MetadataEntry, Plaza.TileIndex);
			SidesAttr->SetValue(Point.MetadataEntry, Plaza.NumSides);
			SideLengthAttr->SetValue(Point.MetadataEntry, Plaza.SideLength);

			OutRanges.SetFromPoint(0, Point);
		}
	}

	return true;
}

#undef LOCTEXT_NAMESPACE
