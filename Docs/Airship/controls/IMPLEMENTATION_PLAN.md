# Airship controls: implementation plan (Classic + Galleon + Sky Racer + Point & Fly)

The C++ and PIE-harness plan for the four control schemes in one build. It follows the three reviewed specs
(`SCHEME_GALLEON.md`, `SCHEME_SKYRACER.md`, `SCHEME_POINTFLY.md`, each ending in a "Review changes" section),
`BASELINE.md` (v1 code reference and base fixes) and the bench in `sims/`. **Where a spec's own C++ list and this plan
differ, this plan wins.** Units: cm, cm/s, cm/s², s, deg, rad/s² in code; m, m/s, deg, g in prose.

File shorthand (under `Source/Aura/`): `Types.h` = `Public/Airship/AirshipTypes.h`; `FC.h` / `FC.cpp` =
`Public/Airship/AirshipFlightComponent.h` / `Private/Airship/AirshipFlightComponent.cpp`; `Pawn.h` / `Pawn.cpp` =
`Public/Airship/AirshipPawn.h` / `Private/Airship/AirshipPawn.cpp`; `HUD.h` / `HUD.cpp` = `AirshipHUDWidget`;
`Sub.cpp` = `Private/Airship/AirshipSubsystem.cpp`. Line numbers are at commit 8f01bca.

## 0. Summary

| | |
|---|---|
| Files touched | 8: `Types.h`, `FC.h`, `FC.cpp`, `Pawn.h`, `Pawn.cpp`, `HUD.h`, `HUD.cpp`, `Sub.cpp`. New harness `Docs/Airship/scripts/ue/as_50_pie_controls.py`. No asset, input action, mapping context or rig change |
| New types | `EAirshipControlScheme` (UENUM, contract), `FAirshipFeedbackEvent` (USTRUCT), `FPointFlyLoopState` (plain struct), namespace `AirshipGalleon` |
| New UPROPERTYs | 155 tunables (flight component 91: base fixes 10, shared mechanisms 13, Galleon 7, Sky Racer 52, Point & Fly 9; pawn 62: contract 1, shared 27, Galleon 9, Sky Racer 7, Point & Fly 18; HUD widget 2), 12 telemetry fields (contract 6, extras 6) and 1 wire field (`FAirshipPilotInput::HeadingTarget`, uint16) |
| Wire | +2 bytes per input packet (`HeadingTarget`), Buttons bit 4 (`Button_Stations`) |
| Build order | Phase A shared framework with Classic only (must be exact v1, section 7), then B Galleon, C Sky Racer, D Point & Fly, E harness. Each phase compiles on its own |

Design rules used everywhere:

1. **One scheme switch, one flag.** The pawn owns the replicated `ControlScheme`; `ApplyControlScheme` copies it into
   `UAirshipFlightComponent::ActiveScheme` on every machine. Scheme-specific code tests `ActiveScheme`. Shared
   mechanisms are gated by their own tunables, whose v1 values turn them off.
2. **Classic = the archetype.** Applying any scheme first copies every scheme-owned property from the component's /
   pawn's archetype (the Blueprint CDO, which overrides none of them: BASELINE 2), then writes that scheme's overrides.
   So Classic is exactly today's defaults by construction, and switching is order-independent.
3. **No client physics.** Every force stays in the server's `ApplyForces`. Pilot-side code only shapes the wire
   controls, the camera, the HUD and the feedback.
4. **Deterministic cosmetics.** Anything every machine must agree on (Galleon's order decode and speed loop, Sky
   Racer's drift state machine) runs in `ShapeControls` from the controls that machine has, like v1's `bDrifting`.

---

## 1. Shared framework

### 1.1 The contract types and the pawn property

`Types.h`, before `FAirshipPilotInput`:

```cpp
UENUM(BlueprintType)
enum class EAirshipControlScheme : uint8
{
	Classic = 0 UMETA(DisplayName = "Classic (v1)"),
	Galleon = 1,
	SkyRacer = 2 UMETA(DisplayName = "Sky Racer"),
	PointFly = 3 UMETA(DisplayName = "Point & Fly")
};
```

`Pawn.h` (public, next to `GetControlScheme`; the property in a `protected` "Airship|Controls" block):

```cpp
UPROPERTY(EditAnywhere, BlueprintReadOnly, ReplicatedUsing = OnRep_ControlScheme, Category = "Airship|Controls")
EAirshipControlScheme ControlScheme = EAirshipControlScheme::Classic;   // the judged winner becomes the default later (done: PointFly, CPP_NOTES 14.12)

UFUNCTION(BlueprintCallable, Category = "Airship|Controls")
void SetControlScheme(EAirshipControlScheme NewScheme);

UFUNCTION(BlueprintPure, Category = "Airship|Controls")
EAirshipControlScheme GetControlScheme() const { return ControlScheme; }

UFUNCTION()
void OnRep_ControlScheme();
```

`Pawn.cpp`:

* `GetLifetimeReplicatedProps` (`:230-237`): `DOREPLIFETIME(AAirshipPawn, ControlScheme);` (every connection: the
  observers' cosmetics need it).
* `SetControlScheme(NewScheme)`: on a client, `UE_LOG(LogAirshipPawn, Warning, ...)` and return. On authority:
  `ControlScheme = NewScheme; ApplyControlScheme(true); ForceNetUpdate();`. Re-applying the same scheme is allowed (it
  resets live tuning on the server; clients get no OnRep then, so their cosmetics keep any client-side tuning).
* `OnRep_ControlScheme()`: `if (HasActorBegunPlay()) { ApplyControlScheme(true); }` (the first bunch arrives before
  BeginPlay, which applies it then).
* `BeginPlay` (`:239-283`): call `ApplyControlScheme(false)` right after `Super::BeginPlay()` (the flight component's
  BeginPlay has set the body by then) and before `OnRep_PilotCharacter()`.

### 1.2 `ApplyControlScheme(bool bSwitch)` (new, private, `Pawn.cpp`)

Idempotent and safe on every machine, before or after possession:

1. `ApplySchemePreset(ControlScheme)` (1.13): the archetype copy, then the scheme's overrides, for the flight
   component, the pawn and the `CameraBoom`.
2. `Flight->SetActiveScheme(ControlScheme)`; it calls `ResetSchemeState(true)` (1.12).
3. `OnTuningChanged()` (`:2238-2248`: actuator positions, body settings, cannon geometry, zoom clamp).
4. `ZoomTarget = CameraArmLength; CameraBoom->TargetArmLength` keeps interpolating (no jump).
5. `ResetSchemePilotState(bSwitch)` (1.12): Galleon notch, Point & Fly heading state, camera offsets, feedback state;
   `Camera->SetRelativeRotation(FRotator::ZeroRotator); Camera->SetRelativeLocation(FVector::ZeroVector)`; stop the
   continuous rumble; `SmoothedFOV = Camera->FieldOfView`.
6. `RefreshShipHUDLayout()` (1.11).

### 1.3 Replication and the switch window

| What | How |
|---|---|
| The scheme | `ControlScheme` replicates to every connection; `OnRep` applies it. Late joiners get it in the first bunch; BeginPlay applies it (OnRep before BeginPlay only stores). |
| Tunables | Never replicated: every machine writes the same compiled-in preset. `Aura.Airship.Set` stays per machine, as today. |
| Pilot intent | `FAirshipPilotInput`: Galleon's order rides `Throttle` (a latched code), stations ride Buttons bit 4, Point & Fly's heading rides the new `HeadingTarget`. Sky Racer adds nothing (brake bit + steer + forward speed). |
| Server-derived values for observers | Point & Fly: the server's heading loop writes `Controls.Steer` before `RepInput = Controls` (`FC.cpp:448`). Everything else observers shape from `RepInput` themselves. |
| Switch window (half a round trip until the client's OnRep) | Galleon: Classic throttle values read as order codes (W = FULL, nothing = STOP, S = ASTERN): at most one notch of lurch. Sky Racer: the same wire meaning. Point & Fly: Classic packets carry no target, so their Steer is used; Point & Fly packets at another scheme's server are read as axes (the local-loop Steer, A/D on Strafe). No scheme id in the packet is needed. |

### 1.4 Console (`Sub.cpp`, inside `#if !UE_BUILD_SHIPPING`, next to `GTelemetryCommand`)

* `Aura.Airship.Scheme <0-3>`: `CheckServer`, then `Ship->SetControlScheme(static_cast<EAirshipControlScheme>(N))`
  on every ship of `Subsystem->GetAirships()`; log each. A value outside 0-3: usage warning.
* `Aura.Airship.Scheme` (no argument): any machine; logs `Ship: <DisplayName> (<N>), active <FC ActiveScheme>`.
* `Aura.Airship.Scheme check`: any machine; logs every scheme-owned property (the X-macro lists of 1.13, plus the
  four `CameraBoom` values) whose value differs from the archetype, and the count. Run after `Aura.Airship.Scheme 0` it
  must print 0 differences (the Classic exactness test of section 7); under another scheme it lists that scheme's
  overrides, a quick way to check a preset.
* `Aura.Airship.Telemetry` (`:806-822`): append `scheme %d order %.2f drift %.2f (dir %d tier %d turbo %.2f chain %d)
  heading %d %.1f freelook %d gundeck %d lock %d`. Also, once per call, the inertia line BASELINE 4f row 0 asks for:
  `Body->GetInertiaTensor()`, `Body->GetBodyInstance()->GetMassSpaceLocal()` (rotation as a rotator, translation) and
  the hull-space COM. **Read it in the first PIE run before judging any pitch or roll numbers.**

### 1.5 Telemetry (`Types.h` `FAirshipFlightTelemetry`, all `UPROPERTY(BlueprintReadOnly, Category = "Airship")`)

| Field | Type | Contract | Filled by | Meaning per machine |
|---|---|---|---|---|
| Scheme | uint8 | yes | FC `FillTelemetry` | `ActiveScheme` everywhere |
| ThrottleOrder | float | yes | FC | Galleon: `AirshipGalleon::NotchToOrderValue(notch decoded from CurrentControls.Throttle)` (-1, 0, 1/3, 2/3, 1) on every machine; else -2 |
| DriftCharge | float | yes | FC | Sky Racer: `SkyCharge` (0..1) on every machine (each runs the state machine); else 0 |
| bHeadingTargetActive | bool | yes | FC, pawn override | Point & Fly: server / observers `CurrentControls.HasHeadingTarget()`; the pilot's machine (pawn, `IsLocallyControlled()`) `bPFValid`; else false |
| HeadingTargetDeg | float | yes | FC, pawn override | Point & Fly: world yaw -180..180: received / replicated target, the pilot's sent target (`PFSentHeading`); else 0 |
| bFreeLook | bool | yes | FC, pawn override | true unless Point & Fly in steering mode: pilot `bPFFree`, others `CurrentControls.IsAiming()`; Classic / Galleon / Sky Racer true |
| DriftDir | int32 | extra | FC | Sky Racer `SkyDriftDir` (-1, 0, +1); Galleon / Classic / Point & Fly: `bDrifting ? sign(ShSteer) : 0` |
| DriftTier | int32 | extra | FC | Sky Racer tier of the charge (no grace); else 0 |
| TurboAlpha | float | extra | FC | Sky Racer burn 1 → 0; else 0 |
| TurboChain | int32 | extra | FC | Sky Racer live chain links 0..3; else 0 |
| bGunDeck | bool | extra | FC | the shaped gun-deck flag `bShGunDeck` (Galleon stations bit, else Aim) |
| bGunLock | bool | extra | pawn | Point & Fly gun lock engaged (pilot's machine only); else false |

`AAirshipPawn::GetFlightTelemetry` (`:2218-2236`) calls `Flight->FillTelemetry`, then on the pilot's machine
(`IsLocallyControlled()`) under Point & Fly overrides `bHeadingTargetActive`, `HeadingTargetDeg`, `bFreeLook`,
`bGunLock`. Python reads them with `get_flight_telemetry().export_text()` as today.

### 1.6 The wire (`Types.h`)

* `namespace Airship`: `constexpr uint8 Button_Stations = 1 << 4;` (Galleon only reads it).
* `FAirshipPilotInput`, after `AimPoint`:
  ```cpp
  /** Point & Fly heading target (world yaw): 1..65534 = 1 + round(yaw mod 360 / 360 * 65534) % 65534; 0 = none.
   *  Not in SameControls (camera driven: it rides the InputSendRate heartbeat like AimPoint). */
  UPROPERTY()
  uint16 HeadingTarget = 0;

  static uint16 EncodeHeading(float YawDeg)
  {
  	float W = FMath::Fmod(YawDeg, 360.f);
  	if (W < 0.f) { W += 360.f; }
  	return static_cast<uint16>(1 + FMath::RoundToInt(W / 360.f * 65534.f) % 65534);
  }
  bool HasHeadingTarget() const { return HeadingTarget != 0; }
  float GetHeadingTargetDeg() const { return FRotator::NormalizeAxis((HeadingTarget - 1) * (360.f / 65534.f)); }
  ```
* `SameControls` (`:100-103`) is unchanged. `DebugSetInput` (`Pawn.cpp:2193`) and `Aura.Airship.Input` leave
  `HeadingTarget` 0 and bit 4 clear, so they stay Classic-style cross-checks in every scheme.
* New plain struct (not a USTRUCT) after `FAirshipPilotInput`: `struct FPointFlyLoopState { bool bDrift = false; };`
* New `namespace AirshipGalleon` after `FAirshipPilotInput` (it uses `AxisToFloat`):
  ```cpp
  namespace AirshipGalleon
  {
  	constexpr int32 Astern = -1, Stop = 0, Slow = 1, Half = 2, Full = 3;
  	inline int8 NotchToThrottle(int32 N) { return N < 0 ? int8(-127) : static_cast<int8>(FMath::RoundToInt(127.f * FMath::Clamp(N, 0, 3) / 3.f)); } // -127 0 42 85 127
  	inline int32 ThrottleToNotch(int8 T) { const float V = FAirshipPilotInput::AxisToFloat(T); return V <= -0.5f ? Astern : FMath::RoundToInt(FMath::Clamp(V, 0.f, 1.f) * 3.f); }
  	inline float NotchToOrderValue(int32 N) { return N < 0 ? -1.f : N / 3.f; }
  	inline const TCHAR* NotchName(int32 N) { static const TCHAR* Names[] = { TEXT("ASTERN"), TEXT("STOP"), TEXT("SLOW"), TEXT("HALF"), TEXT("FULL") }; return Names[FMath::Clamp(N, -1, 3) + 1]; }
  }
  ```
* `FAirshipCosmeticState` (plain struct) gains: `bool bDrifting = false; bool bGunDeck = false; int8 DriftDir = 0;
  float DriftCharge = 0.f; uint8 DriftTier = 0; float TurboAlpha = 0.f; uint8 TurboTier = 0; uint8 TurboChain = 0;
  uint8 TurboEventCount = 0; float FXBoost = 0.f; float FXFanThrust = 0.f;`
* New USTRUCT for the feedback events (1.10):
  ```cpp
  USTRUCT(BlueprintType)
  struct AURA_API FAirshipFeedbackEvent
  {
  	GENERATED_BODY()
  	/** Camera trauma added (0..1), FOV punch (deg, decays), rumble intensity (0..1) and length (s). */
  	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float Trauma = 0.f;
  	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float FOVKickDeg = 0.f;
  	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float Rumble = 0.f;
  	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") float RumbleTime = 0.f;
  	/** Large motors (else small). */
  	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airship") bool bRumbleLarge = true;
  };
  ```

### 1.7 Flight component structure (`FC.h` / `FC.cpp`)

New public API:

```cpp
void SetActiveScheme(EAirshipControlScheme InScheme);   // ActiveScheme = InScheme; ResetSchemeState(true)
EAirshipControlScheme GetActiveScheme() const { return ActiveScheme; }
void ResetSchemeState(bool bSchemeSwitch);              // 1.12
/** Full-steer turn rate (deg/s) of the yaw table at |ForwardSpeed| (cm/s), lerped to YawRateBoost by Boost; YawRateDrift when drifting. */
float GetYawRateMaxDeg(float ForwardSpeed, float Boost, bool bDrift) const;
float GetShapedSteer() const { return ShSteer; }
float GetShapedBoost() const { return ShBoost; }
bool IsDrifting() const { return bDrifting; }
bool IsGunDeck() const { return bShGunDeck; }
```

New private state: `EAirshipControlScheme ActiveScheme = EAirshipControlScheme::Classic; bool bShGunDeck = false;
float ShBrakeAmount = 0.f;` plus the per-scheme state of section 2.

`GetYawRateMaxDeg` is `FC.cpp:787-791` moved into a function (the same lerps); `ApplyForces` calls it, Sky Racer's
camera and Point & Fly's heading loop call it too.

**`ShapeControls` (`:366-389`) becomes:**

```cpp
const float RawSteer = Controls.GetSteer();
bShAiming = Controls.IsAiming();
bShGunDeck = (ActiveScheme == EAirshipControlScheme::Galleon) ? Controls.HasButton(Airship::Button_Stations) : bShAiming;
float ThrottleTarget = Controls.GetThrottle();
ShBrakeAmount = 0.f;
switch (ActiveScheme)
{
case EAirshipControlScheme::Galleon:  ShapeGalleon(Controls, Dt, ForwardSpeed, RawSteer, ThrottleTarget); break;   // 2.1
case EAirshipControlScheme::SkyRacer: ShapeSkyRacer(Controls, Dt, ForwardSpeed, RawSteer, ThrottleTarget); break;  // 2.2
default:                                                                                                         // Classic, Point & Fly
	bShBrake = Controls.IsBrake();
	bDrifting = bShBrake && FMath::Abs(RawSteer) > DriftSteerThreshold && ForwardSpeed > DriftMinSpeed;
	ShBrakeAmount = bShBrake ? 1.f : 0.f;
	if (bShBrake && !bDrifting)
	{
		ThrottleTarget = BrakeFadeSpeed > 0.f                                                         // base fix 4c-2
			? -BrakeReverseThrottle * FMath::Clamp(ForwardSpeed / BrakeFadeSpeed, 0.f, 1.f)
			: (ForwardSpeed > 100.f ? -BrakeReverseThrottle : 0.f);                                   // v1
	}
}
ShThrottle = ApproachUpDown(ShThrottle, ThrottleTarget, Dt, ThrottleTauUp, ThrottleTauDown);
ShBoost = Approach(ShBoost, Controls.IsBoost() ? 1.f : 0.f, Dt, Controls.IsBoost() ? BoostTauUp : BoostTauDown);
const float LiftTarget = Controls.GetLift();
const bool bLiftRelease = LiftTauRelease > 0.f && FMath::Abs(LiftTarget) < FMath::Abs(ShLift) && LiftTarget * ShLift >= 0.f;  // 4b-3
ShLift = Approach(ShLift, LiftTarget, Dt, bLiftRelease ? LiftTauRelease : LiftTau);
const bool bSteerRelease = SteerTauRelease > 0.f && FMath::Abs(RawSteer) < FMath::Abs(ShSteer);                                // meet her
ShSteer = Approach(ShSteer, RawSteer, Dt, bSteerRelease ? SteerTauRelease : SteerTau);
ShStrafe = Approach(ShStrafe, Controls.GetStrafe(), Dt, StrafeTau);
```

With Classic values this is v1 line for line (the two new taus are 0, `BrakeFadeSpeed` is 0).

**`UpdateFlight` (`:421-495`):** after the boost gate (`:445`) and before `RepInput = Controls` (`:448`), under Point &
Fly the server heading loop (2.3). The client boost gate (`:450-462`) gets Sky Racer's burst latch (2.2). The
`!bFlightEnabled` branch (`:487-492`) also calls `ResetSchemeState(false)`.

**`ApplyForces` (`:537-919`), in order.** Each item names the spec section; Classic values make every item a no-op.

| # | Block | Change |
|---|---|---|
| F1 | State (`:557-573`) | If `bHullAxisInertia`: `const FQuat MassRot = Body->GetBodyInstance()->GetMassSpaceLocal().GetRotation(); const FVector Principal = Body->GetInertiaTensor();` and `auto HullTorque = [&](const FVector& A) { return MassRot.RotateVector(Principal * MassRot.UnrotateVector(A)); };` (BASELINE 4a fix 1; `BodyInstance.h:907`). |
| F2 | Forward (`:575-594`) | `AFanCmd` with Sky Racer's horizontal-speed fade in a drift (2.2). `ARev = (bShBrake && !bDrifting) ? AFan : ((ActiveScheme == Galleon && Vf > 0) ? GalleonOrderReverseAccel : AFanRev)`. Point & Fly's S brake (2.3). `ADrag` (Sky Racer drift: 2.2). `ABrake = bShBrake ? -ClampBrake(Kbrake * Vf * (bDrifting ? DriftBrakeScale : 1)) * ShBrakeAmount : 0` with `ClampBrake(x) = BrakeMaxAccel > 0 ? Clamp(x, -BrakeMaxAccel, BrakeMaxAccel) : x`. Then the gun deck: `if (bShGunDeck && !bDrifting) { if (AFanCmd > 0) AFanCmd *= GunDeckThrottleScale; ABrake *= GunDeckBrakeScale; }`. `ACmd` after all of them. `AFanCmd`, `ADrag`, `ABrake` become non-const. |
| F3 | Vertical (`:596-640`) | Base fixes 4b-1, 4b-2, 4c-1 (1.8). Point & Fly's turn-lift term in `FvWorld` (2.3). |
| F4 | Attitude targets (`:642-645`) | `BankMax` / `BankDeg` as v1, Sky Racer's drift bank in a drift (2.2), then `if (bShGunDeck) BankDeg *= GunDeckBankScale` (also while drifting). |
| F5 | Yaw command, **moved above the mixer** (from `:786-796`) | `RmaxDeg = GetYawRateMaxDeg(Vf, Boost, bDrifting)`; `YawRateCmd = Steer * Rad(RmaxDeg)` or Sky Racer's drift law; Sky Racer's exit term; then `if (bShGunDeck && !bDrifting) { YawRateCmd *= GunDeckYawScale; RmaxDeg *= GunDeckYawScale; }`. Loop gain / cap: drifting: `Kr' = DriftKr > 0 ? DriftKr : Kr`, `AYaw' = DriftAlphaYawMax > 0 ? DriftAlphaYawMax : AlphaYawMax`; else if `KrSteady > 0 && |YawRateCmd| < |YawRate| - 1e-3`: `Kr' = KrSteady`, `AYaw' = Max(AlphaYawMax, AlphaYawMaxSteady)`. `AlphaZ = Clamp(Kr' * (YawRateCmd - YawRate) + AngularDamping * YawRateCmd, -AYaw', AYaw')`. Moving it up changes no v1 value (it reads nothing from the mixer). |
| F6 | Torques (`:669-670`, `:796`) | `bHullAxisInertia`: `const FVector TauHull = HullTorque(FVector(AlphaTiltBody.X, AlphaTiltBody.Y, AlphaZ)); TauX = TauHull.X; TauY = TauHull.Y; TauZ = TauHull.Z; Izz = HullTorque(FVector::UpVector).Z;` (the full tensor, as the bench's `ctrl_inertia='hull'` models it). Else v1: `Inertia.X * AlphaTiltBody.X`, `Inertia.Y * ...`, `Inertia.Z * AlphaZ`, `Izz = Inertia.Z`. Replace `Inertia.Z` by `Izz` in `:811-819`. |
| F7 | Mixer (`:672-784`) | Base fix 4a-2 before the attitude solve (1.8). `ComputeGimbals` gets Sky Racer's drift roll (2.2). |
| F8 | Fans + rudder (`:798-819`) | `RudderCap` uses 1 in place of `|Steer|` in a Sky Racer drift. |
| F9 | Lateral (`:821-831`) | Sky Racer: drift path force, grip feed-forward, energy redirect, exit snap (2.2). Shared level grip: `FVector GripDir = Right; if (bLevelGripForce) { GripDir = bLevelGripAlongHeading ? FVector(-Fwd.Y, Fwd.X, 0.0).GetSafeNormal() : FVector(Right.X, Right.Y, 0.0).GetSafeNormal(); }` (fall back to `Right` when the result is zero). Point & Fly stores `LastGripAccelZ` (2.3). |
| F10 | Kicks and extras (`:833-852`) | v1 drift kick unless Sky Racer. Sky Racer turbo kick, fuel, burn, dive (2.2). Base fix 4d station keeping (1.8). |
| F11 | Apply (`:863-888`) | `ACom = GripDir * AGrip + Right * WindLat + Fwd * (ADragFwd + ABrake + ARedirect + ATurbo + ADive + AKeepF) + PathN * APath + HorizVelDir * ADragPath + FVector(0, 0, AVert)`, then the hard cap as v1. All new terms are 0 in Classic and `ADragFwd = ADrag` (0 only in a Sky Racer drift). |

**`UpdateCosmetic` (`:921-957`):** fill the new cosmetic fields (`bDrifting`, `bGunDeck = bShGunDeck`, `FXBoost =
ShBoost`, `FXFanThrust = 0` by default); if `bDrifting && DriftCosmeticSteerScale != 1`, `C.Steer =
Clamp(ShSteer * DriftCosmeticSteerScale, -1.3, 1.3)` (only the wheel and rudder read `C.Steer`: `Anim.cpp:207, 213`;
the fan yaw stays `-FanYawMaxDeg * ShSteer`). Galleon pulses (2.1) and Sky Racer FX (2.2) after that.

**`UpdateFX` (`Pawn.cpp:1520-1549`):** thrusters `Boost = C.FXBoost`; fans `Thrust = Max(Abs(C.FanThrust[f]),
C.FXFanThrust)`, `Boost = C.FXBoost`. With the defaults this is v1.

### 1.8 Base fixes (BASELINE 4f), shared by all three schemes

All in `FC.h` category "Airship|BaseFix" (except 4e), v1 defaults = off. Code exactly as `sims/baseline_sim.py` and
the three plug-ins (they agree line for line):

| # | Property (type, v1 default) | Code |
|---|---|---|
| 4a-1 | `bHullAxisInertia` (bool, false) | F1 / F6 |
| 4a-2 | `bFanTorqueFeedForward` (bool, false) | Before the attitude solve (`:706-713`): `Col0[i]` = the collective solve's share; `TotalEst = Clamp(Mass * AFanCmd - Σ Col0[i] * PodDir[i].X, ±2 * FanMaxForce)`; `TauFan = Σ_f (FanLocal[f] - COMLocal) × (FanDir * 0.5 * TotalEst)`; `BAttitude = {0, TauX - TauFan.X, TauY - TauFan.Y}`. `FanDir` and `FanMaxForce` move above the mixer (same values as `:799-805`). |
| 4b-1 | `VertBrakeAccel` (float cm/s², 0) | After `FvWorld`: `AVert = (VertBrakeAccel > 0 && Vz * (Vz - VzCmd) > 0 && |Vz| > |VzCmd|) ? -Sign(Vz) * Min(VertBrakeAccel, Kvz * |Vz - VzCmd|) : 0`, added to `ACom.Z`. |
| 4b-2 | `HoldBrakeAccel` (float cm/s², 0) | `StopLead(vz) = HoldBrakeAccel > 0 ? vz * |vz| / (2 * HoldBrakeAccel) : vz * HoldCaptureLead`; capture `HoldZ = Z + StopLead(Vz)`; hold `VzCmd = Kz * e`, then if `HoldBrakeAccel > 0`: `VzCmd = Sign(e) * Min(|VzCmd|, Sqrt(2 * HoldBrakeAccel * |e|))` (0 for e = 0); then the v1 clamp. |
| 4b-3 | `LiftTauRelease` (float s, 0) | `ShapeControls` (1.7). |
| 4c-1 | `bBrakeHoldLead` (bool, false) | On a brake press in hold mode: `HoldZ = Z + (bBrakeHoldLead ? StopLead(Vz) : 0)`. |
| 4c-2 | `BrakeFadeSpeed` (float cm/s, 0) | `ShapeControls` (1.7) and Sky Racer's brake (2.2). |
| 4d | `StationKeepGain` (float 1/s, 0), `StationKeepSpeed` (float cm/s, 300), `StationKeepAccelMax` (float cm/s², 150) | If `StationKeepGain > 0 && |Throttle| < 0.05 && |Strafe| < 0.05 && Boost < 0.05`: `Fade = Clamp(2 - Size2D(Vf, Vl) / StationKeepSpeed, 0, 1)`, `AKeepF = Clamp(-StationKeepGain * Vf, ±StationKeepAccelMax) * Fade` along `Fwd`. |
| 4e | Pawn `ImpactEpisodeAccelUp` (float cm/s², 0 = use `ImpactEpisodeAccel`), category "Airship\|Impact" | `LimitImpactResponse` (`Pawn.cpp:1710-1711`): `FreeUp = bIsDead ? 0 : (ImpactEpisodeAccelUp > 0 ? ImpactEpisodeAccelUp : ImpactEpisodeAccel) * StepDt`. Rule: at or above the scheme's largest upward flight acceleration, `(CollectiveMax - 1) g + 0.35 g + VertBrakeAccel`. |

### 1.9 Shared mechanisms (one property each, used by several schemes)

`FC.h`, v1-neutral defaults (Classic leaves them so):

| Property | Type, default | Category | Used by | Meaning |
|---|---|---|---|---|
| bLevelGripForce | bool, false | Lateral | Galleon, Sky Racer | Grip / sidle force level (no turn sink) |
| bLevelGripAlongHeading | bool, false | Lateral | Sky Racer (true) | Level grip perpendicular to the heading; false = the hull's right axis made level (Galleon). The bench showed each scheme's sloppy bot worse by 0.6-1.0 gates on the other formula, so both stay |
| BrakeMaxAccel | float cm/s², 0 = no cap | Forward | all three | Air-brake cap |
| SteerTauRelease | float s, 0 = SteerTau | Shaping | Galleon | Helm return time constant |
| KrSteady / AlphaYawMaxSteady | float 1/s / rad/s², 0 | Yaw | Galleon | "Meet her": firmer yaw loop while a turn is taken off |
| DriftKr / DriftAlphaYawMax | float 1/s / rad/s², 0 = Kr / AlphaYawMax | Yaw | Galleon (4 / 1.5), Sky Racer (- / 2.5) | Yaw loop gain / cap while drifting |
| DriftCosmeticSteerScale | float, 1 | Cosmetic | Galleon | Wheel and rudder swing while drifting |
| GunDeckBankScale / GunDeckYawScale / GunDeckThrottleScale / GunDeckBrakeScale | float, 1 | GunDeck | Galleon (stations bit), Sky Racer and Point & Fly (Aim held) | The steady gun deck: bank always; yaw, throttle, brake when not drifting |

### 1.10 Shared feedback (camera trauma, FOV kick, camera roll, rumble): pilot's machine only

One implementation in the pawn; Classic's values are all off, so its camera is exactly v1 (relative rotation and
location stay zero, the FOV path is numerically v1).

**Pawn properties** (category "Airship|Feedback"; v1 defaults in brackets):

| Property | Type [v1] | Meaning |
|---|---|---|
| ShakeRotDeg / ShakeLocCm | float [0 / 0] | Camera relative rotation / location jitter at trauma 1 |
| ShakeFrequency / ShakeDecay | float [10 Hz / 2 /s] | Perlin frequency; trauma decay per second |
| FOVKickDecay / FOVMaxDeg | float [3 /s / 0 = 170] | FOV punch decay (exponential); FOV clamp |
| CameraRollPerBank / CameraRollPerSteerDeg / CameraRollMaxDeg / CameraRollInterpSpeed | float [0 / 0 / 6 / 0 = none] | Camera roll = PerBank x hull roll + PerSteerDeg x `C.Steer` x (gun deck ? GunDeckBankScale : 1), clamped, interpolated |
| RumbleScale | float [0 = off] | Multiplies every rumble |
| ShakeHitPerMS / ShakeHitMax / RumbleHitPerMS | float [0 / 1 / 0] | Hull hit: trauma / rumble per m/s of impact speed above `ImpactMinSpeed` |
| DriftTraumaBase / DriftTraumaPerCharge / DriftRumbleBase / DriftRumblePerCharge | float [0] | While drifting: trauma floor and a continuous rumble (charge = Sky Racer's `DriftCharge`, 0 elsewhere) |
| FeedbackBoostStart, FeedbackOwnBroadside, FeedbackDriftKick, FeedbackTurbo1, FeedbackTurbo2, FeedbackTurbo3, FeedbackOrderChange, FeedbackLockEngage | `FAirshipFeedbackEvent` [all 0] | Per-event trauma, FOV kick, rumble |

**Private state:** `float CameraTrauma = 0, CameraFOVKick = 0, CameraRollDeg = 0, SmoothedFOV = 0, LastAppliedFOV = 0; uint8
LastTurboEventCount = 0; bool bPrevBoostBit = false, bPrevLocalDrift = false; float LocalDriftTime = 0; uint64
LastFeedbackHitFrame = 0; FDynamicForceFeedbackHandle DriftRumbleHandle = 0; double LastOwnBroadsideTime = -1000;`

**Functions:** `void AddFeedback(const FAirshipFeedbackEvent& E, float FOVSign = 1.f)` (trauma `Min(1, T + E.Trauma)`,
`CameraFOVKick += FOVSign * E.FOVKickDeg`, rumble via `PlayRumble(E.Rumble, E.RumbleTime, E.bRumbleLarge)`);
`void PlayRumble(float Intensity, float Duration, bool bLarge)`: if `RumbleScale > 0 && Intensity > 0`,
`PC->PlayDynamicForceFeedback(Intensity * RumbleScale, Duration, bLarge, !bLarge, bLarge, !bLarge)` (the native
overload, `PlayerController.h:1315`; 6 arguments select it); `void UpdateFeedback(float Dt, const
FAirshipCosmeticState& C)` called at the end of `UpdateCamera`.

**Events (pilot's machine):**

| Event | Detected where | Event property |
|---|---|---|
| Boost start | `UpdateFeedback`: rising edge of `Flight->GetCurrentControls().IsBoost()` (the gated bit on this machine) | FeedbackBoostStart |
| Own broadside | `HandleCannonsFired` (`:1467`) if `IsLocallyControlled()`: also `LastOwnBroadsideTime = Now` | FeedbackOwnBroadside |
| Drift kick (Classic path: Galleon swing, Point & Fly drift) | `UpdateFeedback`: `Flight->IsDrifting()` falls after `LocalDriftTime >= DriftBoostMinTime` with `DriftBoostDV > 0`, not Sky Racer | FeedbackDriftKick |
| Turbo release (Sky Racer) | `C.TurboEventCount != LastTurboEventCount`, tier `C.TurboTier` | FeedbackTurbo1/2/3 |
| Order change (Galleon) | The telegraph `Step` (2.1), FOV sign = the order direction | FeedbackOrderChange |
| Gun lock engages (Point & Fly) | `bPFLock` rises (2.3) | FeedbackLockEngage |
| Hull hit | `OnHullHit` (`:1775`), before the authority return, if `IsLocallyControlled()` and `LastFeedbackHitFrame != GFrameCounter`: the impact speed exactly as `:1816-1837` computes it; `Excess = (ImpactSpeed - ImpactMinSpeed) / 100` m/s; if > 0: trauma `+= Min(ShakeHitMax, ShakeHitPerMS * Excess)`, `PlayRumble(Min(1, RumbleHitPerMS * Excess), 0.25, true)` | ShakeHit*, RumbleHitPerMS |

**`UpdateFeedback` per frame:**

```cpp
CameraTrauma = FMath::Max(0.f, CameraTrauma - ShakeDecay * Dt);
if (C.bDrifting) { CameraTrauma = FMath::Max(CameraTrauma, DriftTraumaBase + DriftTraumaPerCharge * C.DriftCharge); }
CameraFOVKick *= FMath::Exp(-FOVKickDecay * Dt);
const float J = ShakeRotDeg * FMath::Square(CameraTrauma), L = ShakeLocCm * FMath::Square(CameraTrauma);
const float T = static_cast<float>(Now) * ShakeFrequency;
const float RollTarget = FMath::Clamp(CameraRollPerBank * static_cast<float>(GetActorRotation().Roll)
	+ CameraRollPerSteerDeg * C.Steer * (C.bGunDeck ? Flight->GunDeckBankScale : 1.f), -CameraRollMaxDeg, CameraRollMaxDeg);
CameraRollDeg = CameraRollInterpSpeed > 0.f ? FMath::FInterpTo(CameraRollDeg, RollTarget, Dt, CameraRollInterpSpeed) : RollTarget;
Camera->SetRelativeRotation(FRotator(J * FMath::PerlinNoise1D(T + 11.3f), J * FMath::PerlinNoise1D(T + 47.1f), CameraRollDeg + J * FMath::PerlinNoise1D(T + 83.9f)));
Camera->SetRelativeLocation(FVector(L * FMath::PerlinNoise1D(T + 5.1f), L * FMath::PerlinNoise1D(T + 19.7f), L * FMath::PerlinNoise1D(T + 61.3f)));
// continuous drift rumble: Start / Update / Stop on DriftRumbleHandle with DriftRumbleBase + DriftRumblePerCharge * C.DriftCharge
```

**FOV** (`UpdateCamera` `:1607-1616`): keep `TargetFOV` as v1, then
`if (!FMath::IsNearlyEqual(Camera->FieldOfView, LastAppliedFOV, 0.01f)) SmoothedFOV = Camera->FieldOfView - CameraFOVKick;`
(someone else wrote the FOV: follow it, as v1 would), `SmoothedFOV = Clamp(FInterpTo(SmoothedFOV, TargetFOV, Dt,
FOVInterpSpeed), 20, MaxFOV)` and `LastAppliedFOV = Clamp(SmoothedFOV + CameraFOVKick, 20, MaxFOV)` with `MaxFOV =
FOVMaxDeg > 0 ? FOVMaxDeg : 170`, then `Camera->SetFieldOfView(LastAppliedFOV)`. With `CameraFOVKick` 0 and
`FOVMaxDeg` 0 this is exactly v1's `Clamp(FInterpTo(Camera->FieldOfView, TargetFOV), 20, 170)`.

### 1.11 HUD framework (`HUD.h` / `HUD.cpp`, `Pawn.cpp` `:2057-2186`)

* `UAirshipHUDWidget`: new `UPROPERTY(EditAnywhere) float GalleonExtraHeight = 78.f;` and `float SkyRowHeight =
  26.f;`, private `EAirshipControlScheme LayoutScheme`, `bool bOverlayMode = false`, and `void SetOverlayMode(bool)`.
  `RefreshValues` reads `LayoutScheme = Ship->GetControlScheme()` every frame. `GetPanelSize()` returns `PanelSize +
  (0, Galleon ? GalleonExtraHeight : SkyRacer ? SkyRowHeight : 0)`. `NativePaint` keeps v1's layout for Classic and
  Point & Fly and inserts the Galleon rows (spec 8) or the Sky Racer TURBO row (spec 7) by `LayoutScheme`; in overlay
  mode it draws only Point & Fly's overlay (spec 7) and nothing in another scheme.
* `AAirshipPawn::RefreshShipHUDLayout()` (new): if the HUD is shown, rebuild the slot as `ShowShipHUD` does (`:2113-2117`)
  with the new `GetPanelSize()` and call `UGameViewportSubsystem::Get()->SetWidgetSlot(ShipHUDWidget, Slot)`
  (`GameViewportSubsystem.h:93`); then create or remove the Point & Fly overlay (`ShipOverlayWidget`, a second
  `UAirshipHUDWidget` with `SetOverlayMode(true)`, anchors (0,0,1,1), offsets 0, ZOrder 0). `ShowShipHUD` /
  `HideShipHUD` also add / remove the overlay when the scheme is Point & Fly. No hide / re-show on a switch: that would
  flash the on-foot overlay for a frame.
* **Shared arc helper** (pawn, public, used by the Galleon HUD and the Point & Fly overlay):
  `void ComputeCannonAimRaw(int32 Cannon, const FVector& Target, float& OutYawDeg, float& OutElevDeg) const` (`:1206-1234`
  without the two clamps; `ComputeCannonAim` calls it and clamps) and `bool IsAimInCannonArc(EAirshipSide Side, const
  FVector& AimPoint) const`: true if either cannon of `Side` has `|yaw| <= CannonYawLimitDeg` and elevation in
  `[CannonElevMinDeg, CannonElevMaxDeg]`. Plus `const FVector& GetLocalAimPoint() const { return LocalAimPoint; }`.

### 1.12 Reset rules

`UAirshipFlightComponent::ResetSchemeState(bool bSchemeSwitch)`: Galleon (`GalleonLastNotch` = decoded current
throttle, both pulses, `bGalleonPrevBoost`), Sky Racer (every field of 2.2's state, `SkyLastReleaseTime =
SkyBoostStartTime = SkyLocalBoostStartTime = -1000`, `SkyTurboTotal = 1`), Point & Fly (`ServerHeadingLoop`,
`LastGripAccelZ`). With `bSchemeSwitch` also `DriftTime = 0`. It never touches the hold altitude, the pod spool, the
boost latch, the fuel or the shaped controls (no jump in forces or cosmetics).

`AAirshipPawn::ResetSchemePilotState(bool bFromSwitch)`: Galleon (`GalleonNotch` = `NotchForSpeed(forward speed)` when
`bFromSwitch`, else STOP; key edges, repeat timer, camera offset / look-ahead / beam watch / `bGalleonCamInit`),
Point & Fly (`bPFValid = false`, which re-initialises H on the next frame; with `bFromSwitch` the camera eases in),
feedback (`CameraTrauma`, `CameraFOVKick`, `CameraRollDeg`, `LocalDriftTime`, `bPrevLocalDrift`,
`LastTurboEventCount = C.TurboEventCount`, stop `DriftRumbleHandle`).

| Event | Machine | Flight component | Pawn pilot-side | Camera |
|---|---|---|---|---|
| Scheme applied (BeginPlay, `SetControlScheme`, `OnRep_ControlScheme`) | all | `SetActiveScheme` → `ResetSchemeState(true)` | `ResetSchemePilotState(true)` | relative transform zeroed, `ZoomTarget = CameraArmLength`, `SmoothedFOV` re-synced, HUD layout refreshed |
| Pilot changes (`OnRep_PilotCharacter` past its `KnownPilot` check; the server calls it itself at board / unboard `:940`, `:1032`) | all | `ResetSchemeState(false)` | `ResetSchemePilotState(false)` | - |
| Local player boards (`UpdateLocalMappingContext` adds the IMC, `:609-612`) | pilot | - | `ResetSchemePilotState(false)` | `bPendingCameraReset` as v1 |
| Possession change on the server (`PossessedBy` / `UnPossessed` → `ResetInput`) | server | `ResetInput` calls `ResetSchemeState(false)` | - | - |
| Death (`HandleDeath` → `SetFlightEnabled(false)` → `ResetInput`) | all | as above, and every frame while dead | `ResetSchemePilotState(false)` | - |
| Debug input active on the pilot's machine | pilot | - | Point & Fly: `bPFValid = false` each frame | - |
| Input timeout | server | Galleon keeps the last order (2.1); the others neutral (v1) | - | - |

### 1.13 Preset table

**Mechanism** (`Pawn.cpp`, new `ApplySchemePreset(EAirshipControlScheme)`):

```cpp
// The scheme-owned properties: every existing property any scheme changes, every new property of FC.h / Pawn.h.
#define AIRSHIP_FC_SCHEME_PROPS(X) X(ThrottleTauUp) X(ThrottleTauDown) /* ... all rows of the tables below (FC) ... */
#define AIRSHIP_PAWN_SCHEME_PROPS(X) X(CameraArmLength) /* ... all rows (Pawn) ... */
const UAirshipFlightComponent* FA = Cast<UAirshipFlightComponent>(Flight->GetArchetype());
const AAirshipPawn* PA = Cast<AAirshipPawn>(GetArchetype());
const USpringArmComponent* BA = Cast<USpringArmComponent>(CameraBoom->GetArchetype());
if (!FA) { FA = GetDefault<UAirshipFlightComponent>(); }   // also PA, BA
#define X(Name) Flight->Name = FA->Name;
AIRSHIP_FC_SCHEME_PROPS(X)
#undef X
#define X(Name) Name = PA->Name;
AIRSHIP_PAWN_SCHEME_PROPS(X)
#undef X
CameraBoom->TargetOffset = BA->TargetOffset; CameraBoom->CameraLagSpeed = BA->CameraLagSpeed;
CameraBoom->CameraLagMaxDistance = BA->CameraLagMaxDistance; CameraBoom->CameraRotationLagSpeed = BA->CameraRotationLagSpeed;
switch (Scheme) { case EAirshipControlScheme::Galleon: ApplyGalleonPreset(); break; /* SkyRacer, PointFly */ default: break; }
```

`ApplyGalleonPreset()` / `ApplySkyRacerPreset()` / `ApplyPointFlyPreset()` are plain assignments of the non-"=" cells of
their column below. The X-macro list is also what `Aura.Airship.Scheme check` compares. The archetype copy also
discards a level instance's overrides of these properties (BASELINE 2: the test map overrides none).

**Existing and shared properties** (code units; "=" = the Classic value; Classic = today's C++ default, checked
against `FC.h`, `Pawn.h`, the constructor `Pawn.cpp:175-194` and `sims/airship_sim.py` `FLIGHT_DEFAULTS` /
`PAWN_DEFAULTS`; generated from the bench presets by `sims/review_preset_table.py`, with the spec-only values added).
Scheme-only properties are in section 2.

| Owner | Property | Classic (v1) | Galleon | Sky Racer | Point & Fly |
|---|---|---|---|---|---|
| FC | AFan | 1323 | = | 1860 | 1400 |
| FC | AFanBoost | 1960 | = | 2550 | = |
| FC | AlphaYawMax | 1 | = | 1.5 | = |
| FC | AlphaYawMaxSteady (new) | 0 | 1.2 | = | = |
| FC | BankFullSpeed | 2000 | 2400 | 1800 | = |
| FC | BankMaxBoostDeg | 12 | 18 | 15 | = |
| FC | BankMaxDeg | 18 | 26 | 22 | = |
| FC | BankMaxDriftDeg | 22 | 28 | = | = |
| FC | bBrakeHoldLead (new) | false | true | true | true |
| FC | bFanTorqueFeedForward (new) | false | true | true | true |
| FC | bHullAxisInertia (new) | false | true | true | true |
| FC | bLevelGripAlongHeading (new) | false | = | true | = |
| FC | bLevelGripForce (new) | false | true | true | = |
| FC | BoostALatMaxG | 2 | = | 3 | = |
| FC | BoostDrainRate | 25 | 22 | 28 | = |
| FC | BoostKickDV | 400 | 550 | 600 | = |
| FC | BoostKlat | 3 | = | 3.5 | = |
| FC | BoostMinFuelToStart | 20 | = | 18 | = |
| FC | BoostPitchDeg | 3 | 1.5 | 1.5 | 1.5 |
| FC | BoostRegenDelay | 1 | = | 1.2 | = |
| FC | BoostRegenRate | 12 | = | 10 | = |
| FC | BoostTauDown | 0.6 | = | 0.45 | = |
| FC | BoostTauUp | 0.15 | = | 0.08 | = |
| FC | BrakeFadeSpeed (new) | 0 | 1000 | 1000 | 1000 |
| FC | BrakeMaxAccel (new) | 0 | 1400 | 1470 | 1470 |
| FC | BrakeReverseThrottle | 0.5 | = | 0.4 | = |
| FC | ClimbRate | 1200 | 1000 | 1350 | = |
| FC | CollectiveMax | 1.9 | = | 2.1 | = |
| FC | CollectiveMin | 0.25 | = | 0.15 | = |
| FC | DescendRate | 1500 | 1300 | 1650 | = |
| FC | DriftALatMaxG | 1.2 | 1.6 | = | = |
| FC | DriftAlphaYawMax (new) | 0 | 1.5 | 2.5 | = |
| FC | DriftBoostDV | 600 | 250 | = | = |
| FC | DriftBoostMinTime | 1.2 | 0.6 | = | = |
| FC | DriftBrakeScale | 0 | 0.3 | = | = |
| FC | DriftCosmeticSteerScale (new) | 1 | 1.3 | = | = |
| FC | DriftEta | 0.4 | 0.15 | = | = |
| FC | DriftKlat | 1.2 | 1.6 | = | = |
| FC | DriftKr (new) | 0 | 4 | = | = |
| FC | DriftMinSpeed | 800 | 600 | = | = |
| FC | FanMax | 0.68 | = | 0.95 | = |
| FC | FanMaxBoost | 1 | = | 1.3 | = |
| FC | GripALatMaxG | 2.5 | = | 4 | = |
| FC | GripKlat | 4 | = | 4.5 | = |
| FC | GunDeckBankScale (new) | 1 | 0.2 | 0.35 | 0.4 |
| FC | GunDeckBrakeScale (new) | 1 | = | 0.3 | = |
| FC | GunDeckThrottleScale (new) | 1 | = | 0.6 | = |
| FC | GunDeckYawScale (new) | 1 | 0.5 | 0.8 | = |
| FC | GyroTiltMax | 0.8 | 1.5 | = | = |
| FC | GyroYawMax | 0.5 | = | 0.6 | = |
| FC | HoldBrakeAccel (new) | 0 | 1470 | 1960 | 1470 |
| FC | Kbrake | 0.9 | = | 1.5 | 2 |
| FC | KdRoll | 4.5 | 5.4 | 5.4 | = |
| FC | Kfloor | 1.5 | = | 2 | = |
| FC | KpRoll | 6.25 | 18 | 9 | = |
| FC | Kr | 3 | = | 4.5 | 5.5 |
| FC | KrSteady (new) | 0 | 4 | = | = |
| FC | Kvz | 2 | = | 3 | = |
| FC | LiftPitchDeg | 3 | = | 4 | = |
| FC | LiftTau | 0.25 | = | 0.12 | = |
| FC | LiftTauRelease (new) | 0 | 0.08 | 0.06 | 0.08 |
| FC | MinClearance | 400 | = | 500 | = |
| FC | PitchMaxDeg | 6 | 3 | 4 | = |
| FC | PitchMinDeg | -8 | -4 | -5 | -4 |
| FC | PitchPerG | 8 | 4 | 4.5 | 4 |
| FC | PodForceMax | 0.55 | = | 0.62 | = |
| FC | RudderAuthority | 0.6 | = | 0.9 | = |
| FC | RudderMaxAlpha | 1.2 | = | 1.6 | = |
| FC | RudderRefSpeed | 4800 | = | 5000 | = |
| FC | StationKeepAccelMax (new) | 150 | = | = | = |
| FC | StationKeepGain (new) | 0 | 1 | 1 | 1 |
| FC | StationKeepSpeed (new) | 300 | = | = | = |
| FC | SteerTau | 0.15 | = | 0.09 | 0.1 |
| FC | SteerTauRelease (new) | 0 | 0.12 | = | = |
| FC | StrafeBankDeg | 6 | 3 | 5 | 7 |
| FC | StrafeSpeed | 1200 | 1000 | 1400 | 1400 |
| FC | StrafeTau | 0.2 | 0.25 | 0.14 | 0.12 |
| FC | ThrottleTauDown | 0.45 | 0.25 | 0.3 | = |
| FC | ThrottleTauUp | 0.3 | 0.15 | 0.18 | = |
| FC | ThrustFadeExponent | 6 | = | 5 | = |
| FC | VertBrakeAccel (new) | 0 | 784 | 1180 | 784 |
| FC | VTop | 5000 | = | 5900 | = |
| FC | VTopBoost | 9600 | = | 10000 | = |
| FC | YawRateAtMid | 45 | 44 | 50 | = |
| FC | YawRateAtRest | 30 | 26 | 34 | = |
| FC | YawRateAtTop | 35 | 34 | 38 | = |
| FC | YawRateBoost | 25 | 24 | 30 | = |
| FC | YawRateDrift | 50 | 54 | = | = |
| FC | YawRateMidSpeed | 1500 | = | 1600 | = |
| FC | YawRateTopSpeed | 4800 | = | 5600 | = |
| Pawn | AimFOVOffset | -15 | -18 | -14 | = |
| Pawn | BaseFOV | 85 | 80 | 82 | = |
| Pawn | BoostFOVExtra | 12 | 14 | 14 | = |
| Pawn | CameraArmLength | 6500 | 8000 | 5400 | = |
| Pawn | CameraArmMax | 12000 | 14000 | = | = |
| Pawn | CameraArmMin | 4000 | 5000 | = | = |
| Pawn | CameraBoostArmExtra | 1000 | 1400 | 1200 | = |
| Pawn | CameraDefaultPitch | -12 | -16 | -8 | = |
| Pawn | CameraPitchMax | 25 | 20 | = | = |
| Pawn | CameraPitchMin | -60 | -65 | = | = |
| Pawn | FOVInterpSpeed | 4 | = | 6 | = |
| Pawn | ImpactCooldown | 0.4 | = | 0.6 | = |
| Pawn | ImpactDamagePerMS | 6 | = | 4 | = |
| Pawn | ImpactEpisodeAccelUp (new) | 0 (= ImpactEpisodeAccel 2500) | 2050 | 2650 | 2000 |
| Pawn | ImpactMaxDamage | 500 | = | 350 | = |
| Pawn | ImpactMaxReboundSpeed | 250 | 120 | 120 | 120 |
| Pawn | ImpactMaxSpeedGain | 500 | = | 400 | = |
| Pawn | ImpactMaxSpinKickDeg | 20 | = | 12 | = |
| Pawn | ImpactMinSpeed | 400 | = | 700 | = |
| Pawn | RecenterDelay | 1.5 | 2 | 0.6 | = |
| Pawn | RecenterMinSpeed | 800 | = | 500 | = |
| Pawn | RecenterSpeed | 2 | 1.2 | 4 | 0 |
| Pawn | SpeedFOVExtra | 10 | = | 18 | = |
| Pawn | SpeedFOVFull | 4800 | = | 5500 | = |
| Pawn | SpeedFOVStart | 2000 | = | 1500 | = |
| Pawn | ShakeRotDeg (new) | 0 | 1 | 1.2 | 1.2 |
| Pawn | ShakeLocCm (new) | 0 | 20 | = | = |
| Pawn | ShakeFrequency (new) | 10 | 8 | 14 | 13 |
| Pawn | ShakeDecay (new) | 2 | 1.8 | 1.8 | 2.5 |
| Pawn | FOVKickDecay (new) | 3 | = | 2.5 | 5 |
| Pawn | FOVMaxDeg (new) | 0 (= 170) | = | 112 | = |
| Pawn | CameraRollPerBank (new) | 0 | = | 0.25 | 0.15 |
| Pawn | CameraRollPerSteerDeg (new) | 0 | 6.5 | = | = |
| Pawn | CameraRollMaxDeg (new) | 6 | = | = | 3 |
| Pawn | CameraRollInterpSpeed (new) | 0 (none) | 8 | = | 6 |
| Pawn | RumbleScale (new) | 0 | 1 | 1 | 1 |
| Pawn | ShakeHitPerMS (new) | 0 | 0.06 | 0.05 | 0.05 |
| Pawn | ShakeHitMax (new) | 1 | = | 0.8 | = |
| Pawn | RumbleHitPerMS (new) | 0 | 0.06 | = | 0.067 |
| Pawn | DriftTraumaBase / DriftTraumaPerCharge (new) | 0 / 0 | = | 0.08 / 0.12 | = |
| Pawn | DriftRumbleBase / DriftRumblePerCharge (new) | 0 / 0 | 0.2 / 0 | 0.15 / 0.35 | = |
| Pawn | FeedbackBoostStart (new; Trauma, FOVKickDeg, Rumble, RumbleTime) | 0 | 0.3, 6, 0.4, 0.4 | 0.35, 6, 0.6, 0.2 | 0, 5, 0.3, 0.35 (small) |
| Pawn | FeedbackOwnBroadside (new) | 0 | 0.35, -3, 0.6, 0.25 | = | 0.25, -3, 0.5, 0.15 |
| Pawn | FeedbackDriftKick (new) | 0 | 0.25, 4, 0.5, 0.2 | = | 0.2, 4, 0.6, 0.2 |
| Pawn | FeedbackTurbo1 / 2 / 3 (new) | 0 | = | 0.3, 4, 0.5, 0.25 / 0.45, 7, 0.75, 0.25 / 0.65, 10, 1.0, 0.25 | = |
| Pawn | FeedbackOrderChange (new) | 0 | 0.06, 1.5, 0.25, 0.08 | = | = |
| Pawn | FeedbackLockEngage (new) | 0 | = | = | 0, 0, 0.15, 0.06 (small) |
| Boom | CameraBoom->TargetOffset.Z | 900 | 1200 | 650 | = |
| Boom | CameraBoom->CameraLagSpeed | 5 | 3.5 | 6.5 | = |
| Boom | CameraBoom->CameraLagMaxDistance | 2500 | 3000 | = | = |
| Boom | CameraBoom->CameraRotationLagSpeed | 7 | 6 | 10 | = |

The Classic column was checked against the headers (BASELINE 2.1 / 2.2 tables) and `FLIGHT_DEFAULTS` /
`PAWN_DEFAULTS`; Galleon, Sky Racer and Point & Fly are their bench presets (`scheme_*.py`, generated by the review
tool) plus the spec-only rows (feedback, impact, `CameraLagMaxDistance`). Not written by any scheme: the anim instance
(no scheme changes the rig mapping) and the HUD widget.

---

## 2. Per-scheme change lists

Each phase compiles on its own and leaves Classic exact.

### 2.1 Galleon (phase B)

**New properties, scheme-only** (C++ default = Galleon's value; only read while `ActiveScheme == Galleon`):

| Property | File | Type | Default | Meaning |
|---|---|---|---|---|
| GalleonOrderSlowSpeed / GalleonOrderHalfSpeed / GalleonOrderAsternSpeed | FC.h, "Airship\|Galleon" | float cm/s | 1400 / 2800 / 1200 | Notch speeds (FULL = throttle 1) |
| GalleonOrderSpeedGain | FC.h | float per cm/s | 0.001 | Speed loop P gain |
| GalleonOrderReverseAccel | FC.h | float cm/s² | 800 | Engines backing to slow to the order |
| GalleonOrderPulse / GalleonOrderPulseTime | FC.h | float / float s | 0.35 / 0.45 | Pod thrust pulse on an order change or boost start |
| GalleonOrderAxisPress / GalleonOrderAxisRelease | Pawn.h, "Airship\|Galleon" | float | 0.5 / 0.3 | Telegraph thresholds |
| GalleonOrderRepeatDelay / GalleonOrderRepeatInterval | Pawn.h | float s | 0.25 / 0.15 | Auto-step |
| GalleonBeamWatchEnterDeg / GalleonBeamWatchExitDeg | Pawn.h | float deg | 55 / 40 | Beam watch hysteresis |
| GalleonStationsFireHoldTime | Pawn.h | float s | 6 | Beam watch gives stations only this long after an own broadside (review R1; 0 = always) |
| GalleonLookAheadDeg / GalleonLookAheadTau | Pawn.h | float deg / s | 10 / 0.12 | Camera yaw into the turn per unit helm |

**Steps:**

1. `FC.h`: the properties above; private `int32 GalleonLastNotch = 0; float GalleonOrderPulse01 = 0, GalleonBoostPulse01
   = 0; bool bGalleonPrevBoost = false; FAirshipPilotInput LastGoodServerInput;`; public `int32 GetGalleonNotch()
   const` (`AirshipGalleon::ThrottleToNotch(CurrentControls.Throttle)`); private `float GalleonHoldThrottle(float V)
   const` (spec 3.3 `HoldThrottle`, forward and astern) and `void ShapeGalleon(...)`.
2. `FC.cpp` `ServerSetPilotInput_Implementation`: keep `LastGoodServerInput = Input` after it is accepted.
   `SelectControls` (`:307-314`), Galleon and a controller and a stale input: return `LastGoodServerInput` with Steer,
   Lift, Strafe = 0, Boost / Brake / Aim / Stations bits cleared, `HeadingTarget = 0` (the order is kept, spec 3.2).
3. `ShapeGalleon` (spec 3.3): `Notch = ThrottleToNotch(Controls.Throttle)`; on a change `GalleonOrderPulse01 = 1`; on a
   boost press `GalleonBoostPulse01 = 1`; `bShBrake = Controls.IsBrake(); bDrifting = bShBrake && |RawSteer| >
   DriftSteerThreshold && ForwardSpeed > DriftMinSpeed` (the swing); `ShBrakeAmount = bShBrake ? 1 : 0`; `ThrottleTarget
   = Controls.IsBoost() ? 1 : (Notch == Full ? 1 : Clamp(GalleonHoldThrottle(Vord) + GalleonOrderSpeedGain * (Vord -
   ForwardSpeed), -1, 1))`; brake (not swinging) as the default branch with `BrakeFadeSpeed`; the pulses decay by `Dt /
   GalleonOrderPulseTime`.
4. `ApplyForces`: F2's `ARev` rule; the gun deck (bank, yaw scale) and drift loop come from the shared code.
5. `UpdateCosmetic`: `Pulse = GalleonOrderPulse * Max(GalleonOrderPulse01, GalleonBoostPulse01)` added to every
   `PodThrustAlpha`, clamped 0..1.5 (the anim's petal flare and the Niagara `Thrust` follow).
6. `FillTelemetry`: `ThrottleOrder = NotchToOrderValue(GetGalleonNotch())`.
7. `Pawn.h`: the pawn properties above; private `int32 GalleonNotch = 0; bool bGalleonUpHeld = false, bGalleonDownHeld
   = false; int32 GalleonRepeatDir = 0; double GalleonNextRepeatTime = 0; float GalleonCamOffsetYaw = 0,
   GalleonLookAhead = 0, GalleonLastHullYaw = 0, GalleonLastLookAhead = 0; bool bGalleonBeamWatch = false,
   bGalleonStations = false, bGalleonCamInit = false;` public `int32 GetGalleonNotch() const { return GalleonNotch; }`,
   `bool IsGalleonStations() const { return bGalleonStations; }`, `static int32 NotchForSpeed(float ForwardSpeedCms)`
   (FULL >= 3800, HALF >= 2100, SLOW >= 700, STOP > -300, else ASTERN).
8. `GatherLocalInput` (`:658-667`, the non-debug branch), Galleon: (a) beam watch and stations (spec 3.8, evaluated
   here from `PC->GetControlRotation().Yaw`, `GalleonLastHullYaw`, `GalleonLastLookAhead`; `bGalleonStations =
   Aim || (bGalleonBeamWatch && (GalleonStationsFireHoldTime <= 0 || Now - LastOwnBroadsideTime <
   GalleonStationsFireHoldTime))`); (b) the telegraph (spec 3.1; on a step `AddFeedback(FeedbackOrderChange, Dir)`);
   (c) `Controls.Throttle = AirshipGalleon::NotchToThrottle(GalleonNotch)`, `Controls.SetButton(Button_Stations,
   bGalleonStations)`.
9. `UpdateCamera`, Galleon branch in place of the v1 recentre (spec 6): ship-relative offset, recentre outside beam
   watch, look-ahead from `C.Steer`, `SetControlRotation(HullYaw + Offset + LookAhead)`; it consumes
   `bPendingCameraReset` (Offset = LookAhead = 0, `bGalleonCamInit = true`). Roll / shake / FOV / rumble: 1.10.
10. HUD (spec 8): the telegraph row, the speed rule, the helm row (`SWING` when `Telemetry.bDrifting`, `STATIONS` when
    `IsGalleonStations()`), the in-arc / `FIRE` marks via `IsAimInCannonArc(AimSide, GetLocalAimPoint())`.
11. `ApplyGalleonPreset()`: the Galleon column of 1.13.

### 2.2 Sky Racer (phase C)

**New properties, scheme-only** (default = Sky Racer's value; read only while `ActiveScheme == SkyRacer`; `FC.h`
category "Airship|Sky Racer" unless noted; all float except `SkyChainMax` int32 and `bSkyCamYawRateFF` bool):

| Properties | Defaults |
|---|---|
| SkyDriftEnterSteer, SkyDriftEnterSpeed, SkyDriftExitSpeed | 0.5, 1500, 800 |
| SkyDriftPathRateMinDeg, SkyDriftPathRateMaxDeg, SkyDriftSlipMinDeg, SkyDriftSlipMaxDeg | 24, 46, 16, 26 |
| SkyDriftSlipGain, SkyDriftPathLeadDeg, SkyDriftYawRateMaxDeg | 3, 10, 65 |
| SkyDriftALatMaxG, SkyDriftScrub, SkyDriftBankDeg, SkyDriftGimbalRollDeg | 5, 0.08, 24, 4 |
| SkyDriftExitTime, SkyDriftExitKlat, SkyDriftExitALatMaxG, SkyDriftExitYawGain | 0.4, 8, 5, 6 |
| SkyDriftThrottle (review R1) | 1.0 |
| SkyChargeRateMin, SkyChargeRateMax, SkyTier1, SkyTier2, SkyTier3, SkyTierGrace | 0.2, 0.5, 0.25, 0.55, 1.0, 0.03 |
| SkyTurboKickDV1/2/3, SkyTurboTime1/2/3, SkyTurboAccel, SkyTurboVTop, SkyTurboFuel1/2/3 | 300/500/750, 0.5/0.8/1.2, 490, 9000, 4/8/15 |
| SkyChainWindow, SkyChainBonus, SkyChainMax | 2.5, 0.15, 3 |
| SkySBrakeSpeed, SkySBrakeTauUp, SkySBrakeTauDown | 300, 0.3, 0.08 |
| SkyGripCentripetalFF, SkyGripEnergyKeep | 0.5, 0.85 |
| SkyDiveAccelPerSink, SkyDiveMinSpeed | 0.06, 1500 |
| SkyBoostMinBurst | 0.5 |
| SkyFXDriftPulse, SkyFXTurboThrust, SkyFXChargeGlow1/2/3 | 0.25, 0.4, 0.25/0.45/0.65 |
| Pawn.h "Airship\|Sky Racer": SkyLookIntoTurnTime, SkyLookIntoTurnMaxDeg, SkyCamSlipShare, bSkyCamYawRateFF, SkyCamDivePitchPerMS, SkyCamDivePitchMaxDeg, SkyTurboArmExtra | 0.3, 14, 0.35, true, 0.4, 8, 600 |

**Steps:**

1. `FC.h`: the properties; private state `double SkyClock = 0; int8 SkyDriftDir = 0; float SkyCharge = 0,
   SkyDriftTime = 0; uint8 SkyChain = 0; double SkyLastReleaseTime = -1000; uint8 SkyTurboTier = 0; float
   SkyTurboLeft = 0, SkyTurboTotal = 1; uint8 SkyTurboEvent = 0, SkyTurboChain = 0, SkyTurboEventCount = 0; float
   SkyExitLeft = 0, SkySBrake = 0; double SkyBoostStartTime = -1000, SkyLocalBoostStartTime = -1000;`; public `float
   GetPilotYawRateCmdDeg() const` (spec 11.2, with `GetYawRateMaxDeg`); private `int32 SkyTierOf(float Charge) const`
   and `void ShapeSkyRacer(...)`.
2. `ShapeSkyRacer` (spec 3.2 + 3.3): `SkyClock += Dt`; the state machine (entry, release with
   `Grace = (HasAuthority() && !GetShip()->IsLocallyControlled()) ? SkyTierGrace : 0`, charge); the S-brake ramp;
   `ShBrakeAmount = (Brake && !drift) ? 1 : (drift ? 0 : SkySBrake)`; `bShBrake = ShBrakeAmount > 0`; `bDrifting =
   SkyDriftDir != 0`; `ThrottleTarget = Throttle`, then **`if (bDrifting && SkyDriftThrottle > 0 && Throttle >= 0)
   ThrottleTarget = Max(ThrottleTarget, SkyDriftThrottle)`** (R1), then the brake override with `BrakeFadeSpeed` and
   `ShBrakeAmount`.
3. `UpdateBoostServer` (`:319-364`) and the client gate (`:450-462`): the burst latch (spec 3.7) with world time.
4. `ComputeGimbals` (`:391-414`): `if (ActiveScheme == SkyRacer && SkyDriftDir) Roll += SkyDriftGimbalRollDeg *
   SkyDriftDir;` before the cone clamp.
5. `ApplyForces` (spec 3.4-3.8): F2 drift fade / path drag; F4 drift bank; F5 drift yaw law, path limiter, exit term;
   F8 rudder cap; F9 path force (`APhys` from `PodForceWorld[]` and `Q.RotateVector(FanDir * FanForce[f])`), grip
   feed-forward, energy redirect, exit snap; F10 turbo kick (`Body->AddImpulse(KickDV, NAME_None, true);
   GetShip()->NoteFlightKick(KickDV)`), `BoostFuel = Min(BoostFuelMax, BoostFuel + SkyTurboFuel<Tier>)`, burn, dive;
   the v1 drift kick is skipped under Sky Racer.
6. `UpdateCosmetic` (spec 11.3): `DriftDir`, `DriftCharge`, `DriftTier`, `TurboAlpha`, `TurboTier`, `TurboChain`,
   `TurboEventCount`, the pod pulses, `FXBoost`, `FXFanThrust`.
7. `FillTelemetry`: `DriftCharge`, `DriftDir`, `DriftTier`, `TurboAlpha`, `TurboChain`.
8. `UpdateCamera`: the generalised recentre (spec 5): when `ActiveScheme == SkyRacer`, `Rate =
   Flight->GetPilotYawRateCmdDeg()`, look-into-turn, slip share, dive pitch, `bSkyCamYawRateFF`; arm target `+
   SkyTurboArmExtra * C.TurboAlpha`. Classic runs v1's recentre unchanged, Galleon its own camera branch (2.1 step 9),
   Point & Fly none (`RecenterSpeed` 0).
9. HUD: the TURBO row (spec 7, 11.5) when `LayoutScheme == SkyRacer`.
10. `ApplySkyRacerPreset()`: the Sky Racer column of 1.13.

### 2.3 Point & Fly (phase D)

**New properties, scheme-only** (default = Point & Fly's value; read only while `ActiveScheme == PointFly`):

| Property | File | Type | Default |
|---|---|---|---|
| PFHeadingKp, PFHeadingLead, PFHeadingDecelDeg, PFHeadingDeadbandDeg | FC.h "Airship\|PointFly" | float | 6.5, 0.18, 55, 0.25 |
| PFDriftStartDeg, PFDriftEndDeg, PFDriftDecelScale | FC.h | float | 40, 15, 0.8 |
| PFReverseBrakeAccel, PFTurnLiftComp | FC.h | float | 980, 1 |
| PFNudgeRateScale, PFHeadingMaxLeadDeg, PFLookReturnTau | Pawn.h "Airship\|PointFly" | float | 1, 150, 0.22 |
| bPFArcAssist | Pawn.h | bool | true |
| PFArcMarginDeg, PFArcMinBearingDeg, PFArcMaxBearingDeg | Pawn.h | float | 6, 55 (review R1), 150 |
| PFArcApproachRateDeg, PFArcApproachTau (review R2), PFArcLockDelay, PFArcLockDeadbandDeg, PFArcRateDeg | Pawn.h | float | 3, 0.1, 0.25, 3, 45 |
| PFLockLeadTime, PFHeadingLeadRateMax, PFHeadingLeadTau | Pawn.h | float | 0.45, 30, 0.12 |
| bPFPitchClimb, PFPitchClimbDeadbandDeg, PFPitchClimbFullDeg | Pawn.h | bool, float, float | false, 10, 20 |

**Steps:**

1. `Types.h`: `HeadingTarget` and `FPointFlyLoopState` (1.6).
2. `FC.h`: the properties; public `float ComputeHeadingSteer(float TargetYawDeg, float YawDeg, float YawRateDegS, float
   ForwardSpeed, float Boost, bool bBrake, FPointFlyLoopState& State) const` (spec 3.5 verbatim); private
   `FPointFlyLoopState ServerHeadingLoop; float LastGripAccelZ = 0;`.
3. `UpdateFlight`, after `:445`, before `:448`: `if (ActiveScheme == PointFly && bFlightEnabled &&
   Controls.HasHeadingTarget()) Controls.Steer = FAirshipPilotInput::QuantizeAxis(ComputeHeadingSteer(
   Controls.GetHeadingTargetDeg(), Body->GetComponentRotation().Yaw, Body->GetPhysicsAngularVelocityInDegrees().Z,
   ForwardSpeed, ShBoost, Controls.IsBrake(), ServerHeadingLoop)); else ServerHeadingLoop = FPointFlyLoopState();`
   (authority only).
4. `ApplyForces` (spec 3.6), Point & Fly only: F2 `if (PFReverseBrakeAccel > 0 && ShThrottle < 0 && !bShBrake && Vf >
   200) AFanCmd = Min(AFanCmd, PFReverseBrakeAccel * ShThrottle * Clamp(Vf / 600, 0, 1))`; F3 `FvWorld = Clamp(Mass *
   (Gravity + Kvz * (VzCmd - Vz) - PFTurnLiftComp * LastGripAccelZ), ...)`; F9 `LastGripAccelZ = AGrip * Right.Z`. The
   brake cap and the gun-deck bank are the shared code.
5. `FillTelemetry` (Point & Fly): `bHeadingTargetActive = CurrentControls.HasHeadingTarget()`, `HeadingTargetDeg =
   CurrentControls.GetHeadingTargetDeg()`, `bFreeLook = CurrentControls.IsAiming()` (the pawn overrides all three on the
   pilot's machine, 1.5).
6. `Pawn.h`: the pawn properties; private state of spec 12.4 (`bPFValid`, `bPFFree`, `bPFLock`, `PFHeading`,
   `PFLookOffset`, `PFLastSetYaw`, `PFSentHeading`, `PFLockDwell`, `PFPrevOffBeam`, `PFOffBeamRate` (R2),
   `PFHeadingRate`, `PFPrevHeading`, `FPointFlyLoopState PilotHeadingLoop`, `uint64 LastLookInputFrame = 0`); functions
   `UpdatePointFlyCamera(float Dt, APlayerController* PC)`, `float PointFlyGunLock(float H, float CamYaw, float Dt)`;
   getters `IsPointFlyActive()`, `GetPFHeadingTargetDeg()`, `IsPFFreeLook()`, `IsPFGunLocked()`.
7. `OnLookInput` (`:727-730`): beside `LastLookInputTime`, `LastLookInputFrame = GFrameCounter`.
8. `GatherLocalInput`: under Point & Fly in the non-debug branch: `UpdatePointFlyCamera` first (spec 3.2 / 3.3 with
   R1 / R2; the external-set rule `d != 0 && LastLookInputFrame != GFrameCounter`, `d = NormalizeAxis(Control.Yaw -
   PFLastSetYaw)`), then the wire (spec 3.4: Strafe from `SteerAction`, `HeadingTarget = EncodeHeading(H_send)`, Steer
   from `Flight->ComputeHeadingSteer` on this machine's hull). In the debug branch: `bPFValid = false` (R5). On a lock
   rise: `AddFeedback(FeedbackLockEngage)`.
9. `UpdateCamera`: the v1 recentre is off through the preset (`RecenterSpeed` 0); roll / FOV / shake: 1.10.
10. HUD overlay (spec 7, 12.6) in `bOverlayMode`; positions from `UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, P, Out, true)` (`WidgetLayoutLibrary.h:64`) in `NativeTick`, cached for `NativePaint`. Hint text per spec 7 (R1).
11. `ApplyPointFlyPreset()`: the Point & Fly column of 1.13.

---

## 3. New-property index

| Where | Count | Names |
|---|---|---|
| FC base fixes | 10 | bHullAxisInertia, bFanTorqueFeedForward, VertBrakeAccel, HoldBrakeAccel, LiftTauRelease, bBrakeHoldLead, BrakeFadeSpeed, StationKeepGain, StationKeepSpeed, StationKeepAccelMax |
| FC shared | 13 | bLevelGripForce, bLevelGripAlongHeading, BrakeMaxAccel, SteerTauRelease, KrSteady, AlphaYawMaxSteady, DriftKr, DriftAlphaYawMax, DriftCosmeticSteerScale, GunDeckBankScale, GunDeckYawScale, GunDeckThrottleScale, GunDeckBrakeScale |
| FC Galleon / Sky Racer / Point & Fly | 7 / 52 / 9 | 2.1 / 2.2 / 2.3 |
| Pawn contract | 1 | ControlScheme |
| Pawn shared | 27 | ImpactEpisodeAccelUp; ShakeRotDeg, ShakeLocCm, ShakeFrequency, ShakeDecay, FOVKickDecay, FOVMaxDeg, CameraRollPerBank, CameraRollPerSteerDeg, CameraRollMaxDeg, CameraRollInterpSpeed, RumbleScale, ShakeHitPerMS, ShakeHitMax, RumbleHitPerMS, DriftTraumaBase, DriftTraumaPerCharge, DriftRumbleBase, DriftRumblePerCharge; FeedbackBoostStart, FeedbackOwnBroadside, FeedbackDriftKick, FeedbackTurbo1, FeedbackTurbo2, FeedbackTurbo3, FeedbackOrderChange, FeedbackLockEngage |
| Pawn Galleon / Sky Racer / Point & Fly | 9 / 7 / 18 | 2.1 / 2.2 / 2.3 |
| HUD widget | 2 | GalleonExtraHeight, SkyRowHeight |
| Telemetry | 12 | 1.5 |

All UPROPERTYs are `EditAnywhere, BlueprintReadOnly` with `ClampMin` only where v1 uses it (`Aura.Airship.Set` skips
metadata anyway). Defaults per the tables.

---

## 4. Compile and stability notes

* **Engine APIs used, checked in `/mnt/new_partition/5.8`:** `FBodyInstance::GetMassSpaceLocal` (BodyInstance.h:907),
  `UPrimitiveComponent::GetInertiaTensor` (PrimitiveComponent.h:2865), the native `APlayerController::
  PlayDynamicForceFeedback(float, float, bool, bool, bool, bool, Action = Start, Handle = 0)` returning
  `FDynamicForceFeedbackHandle` (PlayerController.h:1315; a 6-argument call cannot bind to the latent 8-argument one),
  `UGameViewportSubsystem::SetWidgetSlot` / `GetWidgetSlot` (GameViewportSubsystem.h:89-93),
  `UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition` (WidgetLayoutLibrary.h:64), `FMath::PerlinNoise1D`
  (UnrealMathUtility.h:2463), `UObject::GetArchetype`. The tick order Point & Fly relies on:
  `AController::AddPawnTickDependency` (Controller.cpp:495) and `PlayerTick` running `TickPlayerInput` before
  `UpdateRotation` (PlayerController.cpp:2326-2365).
* **No exotic templates.** The preset uses an X-macro of plain assignments; `uint16` and `uint8` UPROPERTYs are
  supported in USTRUCTs and RPC parameters; `FAirshipFeedbackEvent` is a plain USTRUCT. The only new include is
  `Blueprint/WidgetLayoutLibrary.h` in `HUD.cpp` (the Point & Fly overlay's projection); the X-macro lists must use the
  exact UPROPERTY names (the flight component's tunables are public, the pawn's are its own members).
* **Unity build:** new free functions go into the existing named namespaces (`AirshipFlightPrivate`,
  `AirshipPawnPrivate`, `AirshipHUDPrivate`), never anonymous ones (`FC.cpp:17`).
* **Stability at 1/30 s and 1/120 s** (`sims/review_fps_check.py`, every scheme flown open loop at both steps): turn rate,
  bank, swing / drift, climb overshoot and brake time agree within 1 deg/s, 0.4 m and 0.06 s; no oscillation (roll
  standard deviation in a held turn under 0.3 deg in every scheme). The largest `gain x dt` at 1/30 s is 0.27 (Sky
  Racer's exit snap). Every filter is the exact exponential `Approach`; every timer is time-based, so a 120 fps client
  and a 30 fps server agree (Sky Racer's charge, Galleon's auto-repeat, Point & Fly's dwell).
* **Bandwidth:** Point & Fly's Steer changes every frame while turning, so a client sends every frame while it turns
  (as a v1 analog stick does): at most 120 small packets/s from a 120 fps client.

---

## 5. PIE harness (`Docs/Airship/scripts/ue/as_50_pie_controls.py`)

Base it on `as_45_pie_mp.py` (Slate post-tick state machine, listen server + one client, fixed 30 fps,
`inject_input_vector_for_action` on the pilot's `EnhancedInputLocalPlayerSubsystem`, telemetry via
`get_flight_telemetry().export_text()`). Per scheme: `Aura.Airship.Scheme N` on the server world (or
`ship.set_control_scheme(unreal.AirshipControlScheme.SKY_RACER)`; Python names CLASSIC, GALLEON, SKY_RACER,
POINT_FLY), wait 0.5 s, `Aura.Airship.Scheme check` once after returning to Classic, then the metric protocols of
`sims/README.md` with the bench's own adapters. Write `<scheme>_metrics.json` with `meta.source = 'pie'` and the same
keys, so `compare.py` reads both.

### 5.1 Raw inputs (one bench `RawInput` per frame → injections on the pilot's local player)

| RawInput field | Injection | Notes |
|---|---|---|
| throttle, steer, lift, strafe | `IA_AirshipThrottle` / `Steer` / `Lift` / `Strafe`, `Vector(x, 0, 0)` every frame while non-zero | an injection lasts one tick |
| boost, brake, aim | `IA_AirshipBoost` / `Brake` / `Aim`, `Vector(1, 0, 0)` every frame while held | |
| fire | `IA_AirshipFire` for one frame, then at least one frame without | `Started` must fire again |
| zoom | `IA_AirshipZoom` one frame | |
| cam_yaw / cam_pitch | `pc.set_control_rotation(unreal.Rotator(0.0, pitch, yaw))` (Python order: roll, pitch, yaw) | absolute, every frame the bench sets it |
| look = True | Classic, Galleon, Sky Racer: also inject `IA_AirshipLook` `Vector(0.01, 0, 0)` so `LastLookInputTime` is stamped (the bench's `raw.look` stamps it; `OnLookInput` needs a non-zero value after the sensitivity, and 0.01 adds at most a few hundredths of a degree before the next absolute set). Point & Fly: never inject `IA_AirshipLook` (the external-set rule then reads the rotation as absolute) | without it, Classic / Sky Racer's recentre pulls a set camera back |

Time zero (M10) = the frame after the first injection that changes the pilot's input (Galleon: the first telegraph
tap; Point & Fly: the first camera set that moves the heading target).

### 5.2 Per-scheme raw-input semantics (what the bench's `command_raw` / `intent_raw` produce)

| Scheme | Open-loop maneuvers (`command_raw`, M1-M10) | Bots (`intent_raw`, M11 course, M12 orbit) |
|---|---|---|
| Classic | Keys held as commanded; drift = brake + steer | Heading PD on A/D, speed loop on W/S with X when 8 m/s too fast (steer clamped under the drift threshold while braking), lift PD; camera on the look point |
| Galleon | `thrust` → telegraph taps toward the notch (>= 0.83 FULL, >= 0.5 HALF, >= 0.17 SLOW, > -0.5 STOP, else ASTERN): one frame +1 / -1, one frame 0; steer / lift / strafe / boost / brake / aim as keys; drift = brake + helm (the swing) | Classic's heading loop for A/D; the notch nearest the planned speed (2 m/s hysteresis on the current one, a higher notch only after 1.5 s); X when 8 m/s too fast, letting go of the helm while braking (or no brake when the helm is past 0.6); camera on the look point (absolute; the Galleon camera turns it into an offset) |
| Sky Racer | Classic keys | Classic loops with Sky Racer's turn table, S as the brake; drift: X + full steer when the line ahead needs more than 0.9 x the grip rate above 22 m/s, steer mapped onto the drift's path-rate range, X let go when the need drops under 0.8 x the slowest drift rate or the course left is under 0.9 x the slip, at least 0.25 s per press and 0.6 s between presses; W held in drifts; broadside: Aim held, Classic's heading gains |
| Point & Fly | `steer` → camera at hull yaw + 90 x steer every frame (absolute, no look injection); when the steer command ends, once at hull yaw + yaw rate x 0.3; `strafe` → `IA_AirshipSteer` (A/D sidestep); drift = brake + the camera swing; thrust → W/S | Camera yaw = planned course + 0.25 x course gain x the line's turn rate (absolute); W/S speed loop with S as the firm brake when 3 m/s too fast; lift PD; broadside (look point more than 30 deg off the bow): Aim held, camera on the target, A/D for range (`range_k` 0.12 /m, `range_damp` 0.25 s) |

### 5.3 The adapter object the bench code needs (`PieSim`)

The bench's `course.Bot`, `CoursePlanner`, `metrics.OrbitPlanner` and the schemes' adapters only read these
attributes. Build one per run:

| Attribute | PIE source |
|---|---|
| `scheme` | `airship_sim.load_scheme(key)` (its `GAINS`, `KEY_AXES`, adapters) |
| `P`, `PP` | `dict(FLIGHT_DEFAULTS, **scheme.flight)`, `dict(PAWN_DEFAULTS, **scheme.pawn)` (the presets, as `Sim` builds them) |
| `time`, `dt` | server world time since the run start; 1/30 |
| `pilot_view()` | the pilot's ship telemetry on the pilot's machine (a client's own copy), mapped to the bench keys: `ForwardSpeedMS`, `LateralSpeedMS`, `VerticalSpeedMS`, `SpeedMS`, `YawDeg`, `YawRateDegS`, `RollDeg`, `PitchDeg`, `AltitudeM`, `BoostFuel`, `ForwardSpeed` (= `ForwardSpeedMS * 100`), `ActorLocCm` (`get_actor_location`), `VelCm` (`get_velocity`), `CourseDeg` (`atan2(vel)`, the yaw below 1 cm/s) |
| `rmax_deg`, `hold_throttle`, `top_speed_estimate` | `airship_sim.Sim.rmax_deg` etc. bound to the object (they only read `self.P`) |
| `camera_location_m(view)` | the pilot PC's `player_camera_manager.get_camera_location() / 100` |
| `cam.control_yaw` | `pc.get_control_rotation().yaw` |
| `pilot_state` | a dict owned by the adapters. Galleon: before each adapter call set `pilot_state['order']` from the pilot's `ThrottleOrder` (-1 → -1, else `round(v * 3)`). Point & Fly: never put `'H'` in it, so `PointFly.mouse_to_heading` returns the wanted heading unchanged (an absolute set) |
| `pilot_fm` | Sky Racer: an object with `sky_drift_dir` = the pilot's `DriftDir`, `sh_boost` = its `Boost`, `sky_s_in()` = `clamp(Steer * DriftDir, -1, 1)` |
| `aim_targets` | M12: `[(target cm, 600)]`; place a Visibility-blocking 6 m sphere actor there (README M12 note) |

Gates (M11) are judged from the server's actor location with `course.GateJudge` fed the same keys. The sloppy bot's
noise is seeded as in the bench (`seed=7` official), so a PIE run and a bench run of one scheme fly the same plan.

### 5.4 Scheme checks worth logging in PIE (beyond M1-M12)

| Scheme | Check | Pass looks like |
|---|---|---|
| all | `Aura.Airship.Scheme check` after `Aura.Airship.Scheme 0` | 0 differences |
| all | The inertia line of `Aura.Airship.Telemetry` | principal moments about (6.86, 1.10, 6.57) e10 kg cm² (`hull_mass.json`); if not, re-tune the roll pairs before judging |
| Galleon | Hold W from STOP; telemetry `ThrottleOrder` 0 → 1/3 → 2/3 → 1 at 0 / 0.27 / 0.43 s; beam watch without firing keeps `bGunDeck` false, a broadside sets it | `galleon_checks.json` telegraph, `beam_glances` |
| Sky Racer | Drift with and without W: the same course and tier; client at 100 ms: the tier the HUD showed against the server's `DriftTier` at release | `skyracer_checks.py` sections 2, 3 |
| Point & Fly | Camera steps 10 / 90 deg at cruise settle in 0.9 / 3.4 s with < 0.1 deg overshoot (host and client); with Aim held, a look 40 deg off the bow never sets `bGunLock` | `pointfly_checks.json` steps, pass |

---

## 6. Bench name → C++ name

The sims keep their names; the C++ uses the shared ones.

| Bench (scheme file) | C++ |
|---|---|
| `bSkyDrift` (Sky Racer) | none: `ActiveScheme == SkyRacer` |
| `bSkyLevelGrip` (Sky Racer) | `bLevelGripForce` = true and `bLevelGripAlongHeading` = true |
| `SkyBrakeAccelMax`, `PFBrakeAccelMax`, Galleon `BrakeMaxAccel` | `BrakeMaxAccel` |
| `SkyDriftAlphaYawMax` | `DriftAlphaYawMax` |
| `GalleonStationsBankScale`, `SkyAimBankScale`, `PFAimBankScale` | `GunDeckBankScale` |
| `GalleonStationsHelmScale`, `SkyAimYawScale` | `GunDeckYawScale` |
| `SkyAimThrottleScale`, `SkyAimBrakeScale` | `GunDeckThrottleScale`, `GunDeckBrakeScale` |
| `PFArcAssist`, `PFPitchClimb` | `bPFArcAssist`, `bPFPitchClimb` |
| `CameraTargetOffsetZ`, `CameraLagSpeed`, `CameraRotationLagSpeed` (pawn dicts) | `CameraBoom->TargetOffset.Z`, `->CameraLagSpeed`, `->CameraRotationLagSpeed` |
| Galleon `GalleonCameraRoll*`, `GalleonShake*`, `GalleonFOVKick*`, `GalleonRumbleScale`; Sky Racer `SkyCamRoll*`, `SkyShake*`, `SkyFOV*`, `SkyRumble*`, `bSkyRumble`; Point & Fly `PFCameraRoll*`, `PFFOVKick*`, `PFShake*`, `PFRumbleScale` | the shared feedback properties of 1.10 (values in 1.13 and in each spec's tables) |
| `IsAimInArc` (Galleon spec), `IsAimInCannonArc` (Point & Fly spec) | `IsAimInCannonArc(Side, AimPoint)` |
| `GripYawRateDeg` (Sky Racer spec), `GetYawRateMaxDeg` (Point & Fly spec) | `GetYawRateMaxDeg(ForwardSpeed, Boost, bDrift)` |

---

## 7. Phase A acceptance (before any scheme is judged)

1. Build; `as_43_pie_validate.py` 25 / 25 PASS and `as_45_pie_mp.py` 5 / 5 PASS with `ControlScheme` Classic.
2. `Aura.Airship.Scheme 1`, `2`, `3`, `0` in a row, then `Aura.Airship.Scheme check`: 0 differences.
3. A Classic M1 / M4 / M7 run in PIE matches `Docs/Airship/reports/pie_validate.md` run 2 within the run-to-run noise
   (speed 0.3 m/s, pitch 0.5 deg): the restructured `ShapeControls` / `ApplyForces` / FOV path must be numerically v1.
4. Only then phases B-D, each with its scheme's PIE metrics against its bench JSON (`compare.py`).

## 8. Open risks for the PIE judging

* All pitch and roll numbers of the three schemes assume base fix 4a-1 and the UCX inertia; check the inertia line
  first (5.4).
* Feedback values (shake, FOV kicks, rumble, Sky Racer FX pulses) are untested guesses in all three specs.
* Deck riders: Galleon heels 26-28 deg, Sky Racer pulls 4-5 g of hidden side force; check a rider in PIE.
* Point & Fly's "looking around steers" is the scheme's nature; judge it with a human mouse, not only the bot.
* Sky Racer's sloppy-bot course at 100 ms is one gate over its designer's band since review R1 (keyboard chord fix);
  `SkyDriftThrottle = 0` gives the designed behaviour back for an A / B test.
