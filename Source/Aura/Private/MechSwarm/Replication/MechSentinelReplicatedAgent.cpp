// Mech Sentinel Swarm - replicated sentinel snapshot.

#include "MechSwarm/Replication/MechSentinelReplicatedAgent.h"

#include "MechSwarm/Sentinel/MechSentinelFragments.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MechSentinelReplicatedAgent)

namespace MechSwarm::ReplicationPrivate
{
	constexpr float PositionTolerance = 1.f;
	constexpr float VelocityTolerance = 5.f;
}

FMechSentinelReplicatedData FMechSentinelReplicatedData::FromEntity(const FTransform& Transform, const FVector& InVelocity, const FMechSentinelStateFragment& StateFragment,
	const FMechSentinelAttributesFragment& Attributes, const FMechSentinelAttackFragment& Attack)
{
	FMechSentinelReplicatedData Data;
	Data.Position = Transform.GetLocation();
	Data.Velocity = InVelocity;
	Data.SetRotation(Transform.GetRotation());
	Data.State = uint8(StateFragment.State);
	Data.HealthByte = uint8(FMath::RoundToInt32(Attributes.GetHealthFraction() * 255.f));
	// A living sentinel never shows an empty bar because of rounding.
	if (Data.HealthByte == 0 && Attributes.Health > 0.f)
	{
		Data.HealthByte = 1;
	}
	Data.HitSerial = StateFragment.HitSerial;
	Data.AttackSerial = Attack.AttackSerial;
	Data.BuffMask = StateFragment.BuffMask;
	return Data;
}

void FMechSentinelReplicatedData::SetRotation(const FQuat& Rotation)
{
	const FRotator Rotator = Rotation.Rotator();
	Yaw = FRotator::CompressAxisToShort(Rotator.Yaw);
	Pitch = FRotator::CompressAxisToShort(Rotator.Pitch);
	Roll = FRotator::CompressAxisToShort(Rotator.Roll);
}

FQuat FMechSentinelReplicatedData::GetRotation() const
{
	return FRotator(FRotator::DecompressAxisFromShort(Pitch), FRotator::DecompressAxisFromShort(Yaw), FRotator::DecompressAxisFromShort(Roll)).Quaternion();
}

bool FMechSentinelReplicatedData::DiffersFrom(const FMechSentinelReplicatedData& Other) const
{
	using namespace MechSwarm::ReplicationPrivate;

	return HasDiscreteChange(Other)
		|| !Position.Equals(Other.Position, PositionTolerance)
		|| !Velocity.Equals(Other.Velocity, VelocityTolerance)
		|| Yaw != Other.Yaw
		|| Pitch != Other.Pitch
		|| Roll != Other.Roll;
}

bool FMechSentinelReplicatedData::HasDiscreteChange(const FMechSentinelReplicatedData& Other) const
{
	return State != Other.State
		|| HealthByte != Other.HealthByte
		|| HitSerial != Other.HitSerial
		|| AttackSerial != Other.AttackSerial
		|| BuffMask != Other.BuffMask;
}
