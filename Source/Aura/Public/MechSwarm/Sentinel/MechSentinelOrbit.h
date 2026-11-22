// Mech Sentinel Swarm - where a sentinel flies around its target: the per-sentinel orbit shared by steering and the
// obstacle avoidance (both must agree on the goal).

#pragma once

#include "CoreMinimal.h"
#include "MechSwarm/Sentinel/MechSentinelFragments.h"

namespace MechSwarm::Orbit
{
	/** Stable pseudo random value in [0, 1) per entity and purpose (Salt), so every sentinel keeps its own orbit. */
	inline float Hash01(const int32 Seed, const uint32 Salt)
	{
		uint32 Hash = uint32(Seed) * 0x9E3779B1u ^ (Salt * 0x85EBCA77u);
		Hash ^= Hash >> 15;
		Hash *= 0x2C1B3C6Du;
		Hash ^= Hash >> 12;
		Hash *= 0x297A2D39u;
		Hash ^= Hash >> 15;
		return float(Hash & 0x00FFFFFFu) / float(0x01000000u);
	}

	/** This sentinel's orbit radius around a player: OrbitRadius +- OrbitRadiusJitter. */
	inline float GetRadius(const FMechSentinelParameters& Params, const int32 Seed)
	{
		return FMath::Max(0.f, Params.OrbitRadius * (1.f + Params.OrbitRadiusJitter * (2.f * Hash01(Seed, 1u) - 1.f)));
	}

	/**
	 * Signed orbit speed (deg/s) of this sentinel: OrbitSpeed +- OrbitSpeedJitter along its own circle, some sentinels
	 * circling the other way.
	 */
	inline float GetAngularSpeed(const FMechSentinelParameters& Params, const int32 Seed)
	{
		const float Scale = 1.f + Params.OrbitSpeedJitter * (2.f * Hash01(Seed, 3u) - 1.f);
		const float Sign = Hash01(Seed, 4u) < Params.OrbitReverseChance ? -1.f : 1.f;
		const float Radius = FMath::Max(100.f, GetRadius(Params, Seed));
		return FMath::RadiansToDegrees(Params.OrbitSpeed * Scale / Radius) * Sign;
	}

	/**
	 * The point the sentinel steers to. Around a player: on a horizontal circle (OrbitDirection's heading, turned every
	 * frame by the steering) of the sentinel's own radius, at its own height above the target with a slow bob. Around a
	 * fallback point: OrbitDirection * FallbackLoiterRadius, no orbit (a fixed gathering spot).
	 */
	inline FVector GetGoal(const FMechSentinelTargetFragment& Target, const FMechSentinelParameters& Params, const int32 Seed, const float Time)
	{
		if (Target.PlayerSlot == INDEX_NONE)
		{
			return Target.TargetLocation + Target.OrbitDirection * Params.FallbackLoiterRadius;
		}

		FVector Heading(Target.OrbitDirection.X, Target.OrbitDirection.Y, 0.f);
		if (!Heading.Normalize())
		{
			// Straight up or down: a heading of its own.
			const float Angle = Hash01(Seed, 5u) * UE_TWO_PI;
			Heading = FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
		}

		const float Radius = GetRadius(Params, Seed);
		const float Height = FMath::Lerp(Params.OrbitHeightMin, Params.OrbitHeightMax, Hash01(Seed, 2u));
		const float Bob = Params.OrbitBobAmplitude * FMath::Sin(UE_TWO_PI * (Params.OrbitBobFrequency * Time + Hash01(Seed, 6u)));
		return Target.TargetLocation + Heading * Radius + FVector(0.f, 0.f, Height + Bob);
	}
}
