// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MyHexBridge.generated.h"

class AMyHexPlatform;
class UPCGComponent;
class USplineComponent;

/** One end of a bridge: the edge tile it starts from and the point on that tile's open side. */
USTRUCT(BlueprintType)
struct FMyHexBridgeEnd
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<AMyHexPlatform> Platform = nullptr;

	/** Hex coordinate (Q, R, S) of the edge tile on that platform. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FIntVector Tile = FIntVector::ZeroValue;

	/** World-space middle of the tile's open side, at walking-surface height. */
	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FVector Location = FVector::ZeroVector;
};

/** Both ends, replicated together so a client always gets a matching pair. */
USTRUCT(BlueprintType)
struct FMyHexBridgeEnds
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FMyHexBridgeEnd Start;

	UPROPERTY(BlueprintReadOnly, Category = "Hex Bridge")
	FMyHexBridgeEnd End;

	/**
	 * World-space spline tangents at Start and End (UE convention: the derivative with respect to the
	 * input key between the two points). Both zero = a straight bridge.
	 */
	UPROPERTY()
	FVector StartTangent = FVector::ZeroVector;

	UPROPERTY()
	FVector EndTangent = FVector::ZeroVector;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(
	FOnHexBridgeEndTileCollapsedSignature,
	AMyHexBridge*, Bridge,
	AMyHexPlatform*, Platform,
	FIntVector, Tile
);

/**
 * A bridge between two edge tiles of two AMyHexPlatforms.
 *
 * Spawned by UMyHexBridgeSubsystem on the server and replicated. Its spline runs from one tile's
 * open side to the other's, and its PCG component builds the bridge from that spline on every
 * machine (PCG output is not replicated).
 *
 * The bridge listens to both platforms. When either end tile collapses (activates), on any machine,
 * HandleEndTileCollapsed runs and OnEndTileCollapsed broadcasts.
 */
UCLASS(Blueprintable)
class AURA_API AMyHexBridge : public AActor
{
	GENERATED_BODY()

public:

	AMyHexBridge();

	/** Server only, between SpawnActorDeferred and FinishSpawning. Zero tangents = straight. */
	void InitBridge(const FMyHexBridgeEnd& InStart, const FMyHexBridgeEnd& InEnd, const FVector& InStartTangent = FVector::ZeroVector, const FVector& InEndTangent = FVector::ZeroVector);

	UFUNCTION(BlueprintPure, Category = "Hex Bridge")
	const FMyHexBridgeEnds& GetEnds() const { return Ends; }

	/** True once either end tile has collapsed. */
	UFUNCTION(BlueprintPure, Category = "Hex Bridge")
	bool HasEndTileCollapsed() const { return bEndTileCollapsed; }

	/** Fires once, on every machine, when the first of the two end tiles collapses. */
	UPROPERTY(BlueprintAssignable, Category = "Hex Bridge")
	FOnHexBridgeEndTileCollapsedSignature OnEndTileCollapsed;

protected:

	virtual void BeginPlay() override;

	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/**
	 * Runs once, on every machine, when the first end tile collapses. The default destroys the
	 * bridge on the server after DestroyDelay (when bDestroyWhenEndTileCollapses is set).
	 * Override in Blueprint to play an effect; call the parent to keep the destroy.
	 */
	UFUNCTION(BlueprintNativeEvent, Category = "Hex Bridge")
	void HandleEndTileCollapsed(AMyHexPlatform* Platform, FIntVector Tile);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<USplineComponent> BridgeSpline;

	/** Set its graph in a Blueprint child. Generation is started from BeginPlay, not on load. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Hex Bridge")
	TObjectPtr<UPCGComponent> PCGComponent;

	/** Run the PCG graph in BeginPlay, once the spline has its points. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge")
	bool bGenerateOnBeginPlay = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge")
	bool bDestroyWhenEndTileCollapses = true;

	/** Seconds between the end tile collapsing and the server destroying the bridge. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hex Bridge", meta = (ClampMin = "0.0", EditCondition = "bDestroyWhenEndTileCollapses"))
	float DestroyDelay = 0.f;

private:

	UPROPERTY(ReplicatedUsing = OnRep_Ends)
	FMyHexBridgeEnds Ends;

	UFUNCTION()
	void OnRep_Ends();

	/** Puts the spline on the two end points, with the custom tangents when there are any. */
	void ApplyEnds();

	/**
	 * (Re)binds to both platforms' tile-activated delegates. Safe to call more than once: on a client
	 * a platform reference can arrive after the bridge, and OnRep_Ends runs again when it resolves.
	 */
	void BindToPlatforms();

	void OnPlatformTileActivated(AMyHexPlatform* Platform, const FIntVector& Tile);

	/** Server. An end platform was destroyed (culled) or streamed out: the bridge goes with it. */
	UFUNCTION()
	void HandleEndPlatformEndPlay(AActor* Actor, EEndPlayReason::Type EndPlayReason);

	void NotifyEndTileCollapsed(AMyHexPlatform* Platform, const FIntVector& Tile);

	bool bEndTileCollapsed = false;
};
