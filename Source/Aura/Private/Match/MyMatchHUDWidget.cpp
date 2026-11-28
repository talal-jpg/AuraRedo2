// Fill out your copyright notice in the Description page of Project Settings.


#include "Match/MyMatchHUDWidget.h"

#include "MyGameState.h"
#include "MyPlayerState.h"
#include "Airship/AirshipLaneComponent.h"
#include "Airship/AirshipPawn.h"
#include "Airship/AirshipPilotComponent.h"
#include "Airship/AirshipSubsystem.h"
#include "Airship/AirshipTypes.h"
#include "Blueprint/WidgetLayoutLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/World.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Interfaces/MyCombatInterface.h"
#include "Match/MyLobbyPanel.h"
#include "Match/MyMatchSettings.h"
#include "Match/MyTeamLibrary.h"
#include "PlayerInput/MyPlayerController2.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

// Named, not anonymous: the unity build compiles this file together with others
namespace MyMatchHUDPrivate
{
	void MakeRoundedBrush(FSlateBrush& Brush, const FLinearColor& Fill, float Radius, const FLinearColor& Outline, float OutlineWidth)
	{
		Brush = FSlateBrush();
		Brush.DrawAs = ESlateBrushDrawType::RoundedBox;
		Brush.TintColor = FSlateColor(Fill);
		Brush.OutlineSettings = FSlateBrushOutlineSettings(Radius, FSlateColor(Outline), OutlineWidth);
	}

	/** Width (slate units) of Text in Font as drawn at the paint geometry's Scale (glyph advances round at the scaled size). */
	float MeasureWidth(const FString& Text, const FSlateFontInfo& Font, float Scale)
	{
		if (!FSlateApplication::IsInitialized() || Text.IsEmpty())
		{
			return 0.f;
		}
		const float FontScale = FMath::Max(Scale, 0.01f);
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		return static_cast<float>(FVector2f(Measure->Measure(Text, Font, FontScale)).X) / FontScale;
	}

	/** m:ss */
	FString Clock(double Seconds)
	{
		const int32 Total = FMath::Max(0, FMath::CeilToInt(Seconds));
		return FString::Printf(TEXT("%d:%02d"), Total / 60, Total % 60);
	}

	FString TeamName(uint8 TeamId)
	{
		return TeamId < MyMatch::NumTeams ? UMyTeamLibrary::GetTeamName(TeamId).ToString() : FString(TEXT("?"));
	}

	FLinearColor TeamColor(uint8 TeamId)
	{
		return UMyTeamLibrary::GetTeamColor(TeamId);
	}

	/** Darker, same alpha: team colours as text on paper. */
	FLinearColor Darken(const FLinearColor& Color, float Factor)
	{
		return FLinearColor(Color.R * Factor, Color.G * Factor, Color.B * Factor, Color.A);
	}

	bool IsAlive(const AAirshipPawn* Ship)
	{
		return IsValid(Ship) && !Ship->IsAirshipDead();
	}

	/** Point and outward direction on the screen's edge (Inset from it) for a world point the camera doesn't see. */
	FVector2D EdgePoint(const FVector2D& Size, const FVector2D& Direction, float Inset)
	{
		const FVector2D Centre = Size * 0.5;
		const FVector2D Half(FMath::Max(1.0, Centre.X - Inset), FMath::Max(1.0, Centre.Y - Inset));
		const double ScaleX = FMath::Abs(Direction.X) > KINDA_SMALL_NUMBER ? Half.X / FMath::Abs(Direction.X) : UE_BIG_NUMBER;
		const double ScaleY = FMath::Abs(Direction.Y) > KINDA_SMALL_NUMBER ? Half.Y / FMath::Abs(Direction.Y) : UE_BIG_NUMBER;
		return Centre + Direction * FMath::Min(ScaleX, ScaleY);
	}
}

UMyMatchHUDWidget::UMyMatchHUDWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// The ship HUD's comic ink on paper (sRGB)
	PaperColor = FLinearColor(FColor(240, 230, 205));
	InkColor = FLinearColor(FColor(28, 24, 22));
	WarningColor = FLinearColor(FColor(214, 52, 40));

	// Display only: clicks go through to the game
	SetVisibilityInternal(ESlateVisibility::HitTestInvisible);
}

void UMyMatchHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();
	RefreshBrushes();
	BindGameState();

	if (!UseRefusedHandle.IsValid())
	{
		UseRefusedHandle = UAirshipPilotComponent::OnLocalUseRefused.AddUObject(this, &ThisClass::HandleUseRefused);
	}
}

void UMyMatchHUDWidget::NativeDestruct()
{
	UnbindGameState();

	if (UseRefusedHandle.IsValid())
	{
		UAirshipPilotComponent::OnLocalUseRefused.Remove(UseRefusedHandle);
		UseRefusedHandle.Reset();
	}

	Super::NativeDestruct();
}

void UMyMatchHUDWidget::RefreshBrushes()
{
	using namespace MyMatchHUDPrivate;
	const FLinearColor Track = FMath::Lerp(PaperColor, InkColor, 0.08f);

	MakeRoundedBrush(ShadowBrush, InkColor, 8.f, FLinearColor::Transparent, 0.f);
	MakeRoundedBrush(PanelBrush, PaperColor, 8.f, InkColor, 3.f);
	MakeRoundedBrush(TrackBrush, Track, 3.f, InkColor, 2.f);
	MakeRoundedBrush(FillBrush, FLinearColor::White, 2.f, FLinearColor::Transparent, 0.f);
	MakeRoundedBrush(TagBrush, InkColor, 4.f, FLinearColor::Transparent, 0.f);
}

void UMyMatchHUDWidget::BindGameState()
{
	if (GameState.IsValid())
	{
		return;
	}

	const UWorld* World = GetWorld();
	AMyGameState* MyGameState = World ? World->GetGameState<AMyGameState>() : nullptr;

	if (MyGameState)
	{
		GameState = MyGameState;
		MatchEventHandle = MyGameState->OnMatchEvent.AddUObject(this, &ThisClass::HandleMatchEvent);
	}
}

void UMyMatchHUDWidget::UnbindGameState()
{
	if (AMyGameState* MyGameState = GameState.Get())
	{
		MyGameState->OnMatchEvent.Remove(MatchEventHandle);
	}

	MatchEventHandle.Reset();
	GameState.Reset();
}

uint8 UMyMatchHUDWidget::GetLocalTeam() const
{
	const APlayerController* PC = GetOwningPlayer();
	const AMyPlayerState* MyPlayerState = PC ? PC->GetPlayerState<AMyPlayerState>() : nullptr;
	return MyPlayerState ? MyPlayerState->GetTeamId() : MyMatch::NoTeam;
}

bool UMyMatchHUDWidget::IsLocalHost() const
{
	const APlayerController* PC = GetOwningPlayer();
	const AMyPlayerState* MyPlayerState = PC ? PC->GetPlayerState<AMyPlayerState>() : nullptr;

	if (MyPlayerState && MyPlayerState->IsHost())
	{
		return true;
	}

	const UWorld* World = GetWorld();
	return PC && World && PC->IsLocalController() && World->GetNetMode() != NM_Client;
}

bool UMyMatchHUDWidget::HasLobbyPanel() const
{
	const AMyPlayerController2* PC = Cast<AMyPlayerController2>(GetOwningPlayer());
	return PC && PC->GetLobbyPanel() != nullptr;
}

bool UMyMatchHUDWidget::IsSoloPractice(uint8 TeamId) const
{
	// The server's rule (B3.2): one active team with one player doesn't count lives
	return !bVersus && TeamId < MyMatch::NumTeams && Teams[TeamId].NumPlayers <= 1 && UMyMatchSettings::Get()->bSoloPracticeUnlimitedShips;
}

void UMyMatchHUDWidget::AddToast(const FString& Text, const FLinearColor& Color)
{
	if (Text.IsEmpty())
	{
		return;
	}

	FToast& Toast = Toasts.AddDefaulted_GetRef();
	Toast.Text = Text;
	Toast.Color = Color;
	Toast.TimeLeft = ToastSeconds;

	while (Toasts.Num() > FMath::Max(1, MaxToasts))
	{
		Toasts.RemoveAt(0);
	}
}

void UMyMatchHUDWidget::HandleMatchEvent(EMyMatchEvent Event, uint8 TeamId, int32 Value)
{
	using namespace MyMatchHUDPrivate;
	const uint8 Own = GetLocalTeam();
	const bool bOwn = TeamId != MyMatch::NoTeam && TeamId == Own;
	const FString Name = TeamName(TeamId);
	const FLinearColor Color = TeamId < MyMatch::NumTeams ? TeamColor(TeamId) : PaperColor;

	switch (Event)
	{
	case EMyMatchEvent::Started:
		ObjectiveTimeLeft = ObjectiveSeconds;
		FightTimeLeft = Value > 0 ? FightSeconds : 0.f;
		break;

	case EMyMatchEvent::PracticeToVersus:
		AddToast(FString::Printf(TEXT("A new player joined %s: versus starts in %d s"), *Name, FMath::Max(0, Value)), Color);
		break;

	case EMyMatchEvent::ShipDestroyed:
		if (bOwn)
		{
			AddToast(Value < 0 ? FString(TEXT("Your ship was destroyed: a new one is coming"))
				: (Value > 0 ? FString::Printf(TEXT("Your ship was destroyed: %d left"), Value) : FString(TEXT("Your ship was destroyed: none left"))), WarningColor);
		}
		else
		{
			AddToast(FString::Printf(TEXT("%s ship destroyed"), *Name), Color);
		}
		break;

	case EMyMatchEvent::ShipRespawned:
		if (bOwn)
		{
			AddToast(TEXT("Your ship is back"), Color);
		}
		break;

	case EMyMatchEvent::TeamEliminated:
		AddToast(bOwn ? FString(TEXT("Your team is out of ships")) : FString::Printf(TEXT("%s is out of ships"), *Name), bOwn ? WarningColor : Color);
		break;

	case EMyMatchEvent::ForfeitWarning:
		AddToast(FString::Printf(TEXT("%s has no players: they forfeit in %d s"), *Name, FMath::Max(0, Value)), Color);
		break;

	case EMyMatchEvent::ShipUnderAttack:
		if (bOwn)
		{
			AddToast(TEXT("YOUR SHIP IS UNDER ATTACK"), WarningColor);
		}
		if (TeamId < MyMatch::NumTeams)
		{
			AttackFlashTimeLeft[TeamId] = AttackFlashSeconds;
		}
		break;

	case EMyMatchEvent::ShipReturning:
		if (bOwn)
		{
			AddToast(TEXT("Your ship is returning to its lane"), Color);
		}
		break;

	case EMyMatchEvent::TimeWarning:
		AddToast(Value >= 55 ? FString(TEXT("1 minute left")) : FString::Printf(TEXT("%d s left"), FMath::Max(0, Value)), PaperColor);
		break;

	// The lobby (SPEC_B_LOBBY 4.3): value = the cause's EMyLobbyStartBlock (0 = the host)
	case EMyMatchEvent::LobbyCancelled:
	{
		const EMyLobbyStartBlock Cause = static_cast<EMyLobbyStartBlock>(FMath::Clamp(Value, 0, 255));
		const FString Why = Cause == EMyLobbyStartBlock::None ? FString() : UMyTeamLibrary::GetLobbyStartBlockText(this, Cause, 0).ToString();
		AddToast(Why.IsEmpty() ? FString(TEXT("The host cancelled the start")) : FString::Printf(TEXT("Start cancelled: %s"), *Why), WarningColor);
		break;
	}

	// Team = the new team, value = the player's PlayerId (-1 = every team again, a rebalance)
	case EMyMatchEvent::LobbyTeamChanged:
	{
		if (Value < 0)
		{
			AddToast(TEXT("Teams rebalanced for the new team mode"), PaperColor);
			break;
		}

		const APlayerController* PC = GetOwningPlayer();
		const APlayerState* LocalState = PC ? PC->PlayerState : nullptr;
		const AMyGameState* MyGameState = GameState.Get();
		const APlayerState* Mover = nullptr;

		if (MyGameState)
		{
			for (const APlayerState* PlayerState : MyGameState->PlayerArray)
			{
				if (PlayerState && PlayerState->GetPlayerId() == Value)
				{
					Mover = PlayerState;
					break;
				}
			}
		}

		if (Mover && Mover == LocalState)
		{
			AddToast(FString::Printf(TEXT("You are on %s now"), *Name), Color);
		}
		else if (Mover)
		{
			AddToast(FString::Printf(TEXT("%s joined %s"), *Mover->GetPlayerName(), *Name), Color);
		}
		break;
	}

	case EMyMatchEvent::LobbyRulesChanged:
		if (!IsLocalHost())
		{
			AddToast(TEXT("The host changed the rules"), PaperColor);
		}
		break;

	case EMyMatchEvent::LobbyReturn:
		AddToast(TEXT("Back to the lobby"), PaperColor);
		break;

	default:
		break;
	}
}

void UMyMatchHUDWidget::HandleUseRefused(const APlayerController* Player, EAirshipUseRefusal Reason)
{
	// The delegate is process-wide: in single-process PIE another window's player was refused
	if (Phase == EMyMatchPhase::None || (Player && Player != GetOwningPlayer()))
	{
		return;
	}

	// The lobby and its countdown lock every ship (SPEC_B_LOBBY 3.3)
	if (Reason == EAirshipUseRefusal::Locked)
	{
		AddToast(TEXT("Ships unlock when the match starts"), PaperColor);
		return;
	}

	if (Reason != EAirshipUseRefusal::EnemyShip)
	{
		return;
	}

	// The only other team's ship there is
	const uint8 Own = GetLocalTeam();
	const uint8 Enemy = Own < MyMatch::NumTeams ? 1 - Own : MyMatch::NoTeam;

	AddToast(Enemy != MyMatch::NoTeam ? FString::Printf(TEXT("%s ship: you can't use it"), *MyMatchHUDPrivate::TeamName(Enemy))
		: FString(TEXT("That ship isn't yours")), Enemy != MyMatch::NoTeam ? MyMatchHUDPrivate::TeamColor(Enemy) : PaperColor);
}

void UMyMatchHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	BindGameState();
	RefreshValues(MyGeometry, InDeltaTime);
}

void UMyMatchHUDWidget::RefreshValues(const FGeometry& MyGeometry, float DeltaSeconds)
{
	using namespace MyMatchHUDPrivate;
	const AMyGameState* MyGameState = GameState.Get();
	HUDTime += DeltaSeconds;

	for (int32 Index = Toasts.Num() - 1; Index >= 0; --Index)
	{
		Toasts[Index].TimeLeft -= DeltaSeconds;

		if (Toasts[Index].TimeLeft <= 0.f)
		{
			Toasts.RemoveAt(Index);
		}
	}

	ObjectiveTimeLeft = FMath::Max(0.f, ObjectiveTimeLeft - DeltaSeconds);
	FightTimeLeft = FMath::Max(0.f, FightTimeLeft - DeltaSeconds);

	for (float& Flash : AttackFlashTimeLeft)
	{
		Flash = FMath::Max(0.f, Flash - DeltaSeconds);
	}

	Phase = MyGameState ? MyGameState->GetMatchPhase() : EMyMatchPhase::None;
	Markers.Reset();
	NameTags.Reset();
	bTeammateUnderCrosshair = false;

	if (Phase == EMyMatchPhase::None)
	{
		return;
	}

	Rules = MyGameState->GetMatchRules();
	LocalTeam = GetLocalTeam();

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		Teams[Team] = MyGameState->GetTeamState(Team);
		bShipAlive[Team] = IsAlive(Teams[Team].Ship);
	}

	bVersus = Teams[0].bActive && Teams[1].bActive;
	const double Now = MyGameState->GetServerWorldTimeSeconds();
	const double PhaseLeft = FMath::Max(0.0, MyGameState->GetPhaseEndServerTime() - Now);
	const uint8 Enemy = LocalTeam < MyMatch::NumTeams ? 1 - LocalTeam : MyMatch::NoTeam;

	// The centre of the bar: the phase, or the match clock
	CentreSubText.Reset();
	CentreColor = InkColor;

	switch (Phase)
	{
	case EMyMatchPhase::WaitingToStart:
	{
		const int32 NumIn = Teams[0].NumPlayers + Teams[1].NumPlayers;
		CentreText = FString::Printf(TEXT("WAITING FOR PLAYERS %d/%d"), NumIn, FMath::Max(NumIn, MyGameState->GetExpectedPlayers()));
		CentreSubText = TEXT("host: Esc > Start match");
		break;
	}

	case EMyMatchPhase::Countdown:
		CentreText = FString::Printf(TEXT("%s IN %d"), bVersus ? TEXT("FIGHT STARTS") : TEXT("MATCH STARTS"), FMath::CeilToInt(PhaseLeft));
		break;

	case EMyMatchPhase::Lobby:
		// The lobby widget shows its own strip; without it this one-line strip stands in (SPEC_B_LOBBY 6.6)
		CentreText = TEXT("LOBBY");
		break;

	case EMyMatchPhase::InProgress:
	{
		const double MatchEnd = MyGameState->GetMatchEndServerTime();

		if (FightTimeLeft > 0.f)
		{
			CentreText = TEXT("FIGHT");
			CentreColor = WarningColor;
		}
		else if (!bVersus)
		{
			CentreText = TEXT("PRACTICE");
		}
		else if (MatchEnd > 0.0)
		{
			const double Left = MatchEnd - Now;
			CentreText = Clock(Left);
			CentreColor = Left <= 60.0 ? WarningColor : InkColor;
		}
		else
		{
			CentreText = TEXT("VERSUS");
		}
		break;
	}

	case EMyMatchPhase::Ended:
		switch (MyGameState->GetMatchResult())
		{
		case EMyMatchResult::TeamWon:
		{
			const uint8 Winner = MyGameState->GetWinningTeam();
			CentreText = LocalTeam < MyMatch::NumTeams ? (Winner == LocalTeam ? TEXT("VICTORY") : TEXT("DEFEAT")) : FString::Printf(TEXT("%s WINS"), *TeamName(Winner));
			CentreColor = Winner < MyMatch::NumTeams ? Darken(TeamColor(Winner), 0.75f) : InkColor;
			break;
		}
		case EMyMatchResult::Draw: CentreText = TEXT("DRAW"); break;
		case EMyMatchResult::PracticeOver: CentreText = TEXT("PRACTICE OVER"); break;
		default: CentreText = TEXT("MATCH OVER"); break;
		}
		break;

	default:
		CentreText.Reset();
		break;
	}

	StatusText = GetShipStatusText();

	// The lobby without a lobby widget (no LobbyWidgetClass on the HUD): the strip, and one warning
	LobbyStripText.Reset();

	if (Phase == EMyMatchPhase::Lobby && !HasLobbyPanel())
	{
		LobbyStripText = Rules.TeamMode == EMyTeamMode::Practice
			? FString::Printf(TEXT("LOBBY   PRACTICE %d   "), Teams[0].NumPlayers)
			: FString::Printf(TEXT("LOBBY   %s %d - %s %d   "), *TeamName(0), Teams[0].NumPlayers, *TeamName(1), Teams[1].NumPlayers);
		LobbyStripText += IsLocalHost() ? TEXT("host: Esc > Start match") : TEXT("waiting for the host");
		LobbyNoPanelTime += DeltaSeconds;

		if (LobbyNoPanelTime > 2.f && !bWarnedNoLobbyPanel)
		{
			bWarnedNoLobbyPanel = true;
			UE_LOG(LogMatch, Warning, TEXT("Lobby: no lobby widget on %s (AMyHUD LobbyWidgetClass unset or failed): the match HUD's strip and the pause menu's START MATCH stand in"),
				*GetNameSafe(GetOwningPlayer()));
		}
	}
	else
	{
		LobbyNoPanelTime = 0.f;
	}

	// The objective (B8.1): at the start and at a practice -> versus start
	if (bVersus && Enemy != MyMatch::NoTeam)
	{
		ObjectiveText = FString::Printf(TEXT("Sink %s's ship %d %s. Keep yours afloat."), *TeamName(Enemy), Teams[Enemy].LivesLeft,
			Teams[Enemy].LivesLeft == 1 ? TEXT("time") : TEXT("times"));

		if (Rules.TimeLimitMinutes > 0)
		{
			// The server's tie-break (UMyTeamLibrary::GetTimeLimitLives): without the handicap's lives it is the ships lost
			ObjectiveText += UMyMatchSettings::Get()->bTimeLimitCountsHandicap
				? FString::Printf(TEXT(" Most ships left after %d:00 wins."), Rules.TimeLimitMinutes)
				: FString::Printf(TEXT(" Fewest ships lost after %d:00 wins."), Rules.TimeLimitMinutes);
		}
	}
	else
	{
		ObjectiveText = TEXT("Practice: learn to fly. Nobody is against you.");
	}

	// The end panel (B8.5)
	if (Phase == EMyMatchPhase::Ended)
	{
		EndTitle = CentreText;
		EndReason = GetEndReasonText();
		EndShipsLine = bVersus
			? FString::Printf(TEXT("%s %d ships left  -  %s %d"), *TeamName(0), Teams[0].LivesLeft, *TeamName(1), Teams[1].LivesLeft)
			: FString::Printf(TEXT("Ships lost: %d"), Teams[LocalTeam < MyMatch::NumTeams ? LocalTeam : 0].ShipsLost);
		// A match that ends in the lobby says so on every machine (EndMatch writes bLobbyRound, SPEC_B_LOBBY 2.5)
		const bool bToLobby = MyGameState->IsLobbyRound();
		const bool bTimed = MyGameState->GetPhaseEndServerTime() > 0.0;
		const int32 SecondsLeft = FMath::CeilToInt(PhaseLeft);
		EndRestartLine = !bTimed ? FString(bToLobby ? TEXT("Host: Esc > Back to lobby") : TEXT("Host: Esc > Restart match"))
			: (bToLobby ? FString::Printf(TEXT("Back to the lobby in %d s"), SecondsLeft) : FString::Printf(TEXT("Restarting in %d s"), SecondsLeft));
		EndHostLine = bTimed && IsLocalHost()
			? FString(bToLobby ? TEXT("Esc > Back to lobby to go now") : TEXT("Esc > Restart match to go now"))
			: FString();
	}

	const APlayerController* PC = GetOwningPlayer();
	const APawn* LocalPawn = PC ? PC->GetPawn() : nullptr;

	if (PC)
	{
		RefreshMarkers(MyGeometry, PC, LocalPawn);
		RefreshNameTags(PC, LocalPawn, DeltaSeconds);
		RefreshCrosshair(PC, LocalPawn);
	}
}

FString UMyMatchHUDWidget::GetShipStatusText() const
{
	using namespace MyMatchHUDPrivate;

	if (LocalTeam >= MyMatch::NumTeams || !Teams[LocalTeam].bActive)
	{
		return FString();
	}

	const FMyTeamState& Own = Teams[LocalTeam];
	const AAirshipPawn* Ship = Own.Ship;
	const AMyGameState* MyGameState = GameState.Get();
	const double Now = MyGameState ? MyGameState->GetServerWorldTimeSeconds() : 0.0;

	if (!IsAlive(Ship))
	{
		if (Own.ShipRespawnServerTime > 0.0)
		{
			return FString::Printf(TEXT("SHIP: BACK IN %d s"), FMath::Max(0, FMath::CeilToInt(Own.ShipRespawnServerTime - Now)));
		}
		return Own.LivesLeft <= 0 && (Phase == EMyMatchPhase::InProgress || Phase == EMyMatchPhase::Ended) ? FString(TEXT("SHIP: NO SHIPS LEFT")) : FString(TEXT("SHIP: -"));
	}

	const UAirshipLaneComponent* Lane = Ship->GetLane();
	const EMyLaneState LaneState = Lane ? Lane->GetLaneState() : EMyLaneState::NoLane;
	const APlayerState* PilotState = Ship->GetPlayerState();
	const FString Pilot = PilotState ? PilotState->GetPlayerName() : FString(TEXT("a pilot"));
	FString Text;

	switch (LaneState)
	{
	case EMyLaneState::Cruising:
		Text = FString::Printf(TEXT("SHIP: LANE  %d m/s"), FMath::RoundToInt(Ship->GetVelocity().Size2D() / 100.0));
		break;

	case EMyLaneState::Waiting:
		switch (static_cast<EMyLaneClamp>(Lane->GetLaneHint().Clamp))
		{
		case EMyLaneClamp::TeamPace: Text = TEXT("SHIP: WAITING FOR TEAM"); break;
		case EMyLaneClamp::PathEnd: Text = TEXT("SHIP: WAITING AT THE PATH END"); break;
		case EMyLaneClamp::Blocked: Text = TEXT("SHIP: BLOCKED"); break;
		case EMyLaneClamp::NotStarted: Text = TEXT("SHIP: WAITING FOR THE START"); break;
		case EMyLaneClamp::Ended: Text = TEXT("SHIP: STOPPED"); break;
		default: Text = TEXT("SHIP: WAITING"); break;
		}
		break;

	case EMyLaneState::Assist:
		Text = FString::Printf(TEXT("SHIP: LANE AUTO, %s AT THE HELM"), *Pilot);
		break;

	case EMyLaneState::PilotedInLane:
		Text = FString::Printf(TEXT("SHIP: PILOTED BY %s"), *Pilot);
		break;

	case EMyLaneState::OutOfLane:
		Text = FString::Printf(TEXT("SHIP: OUT OF LANE, PILOTED BY %s"), *Pilot);
		break;

	case EMyLaneState::Parked:
	{
		const double RecallAt = Lane->GetRecallServerTime();
		Text = RecallAt > 0.0 ? FString::Printf(TEXT("SHIP: RETURNS TO LANE IN %d s"), FMath::Max(0, FMath::CeilToInt(RecallAt - Now))) : FString(TEXT("SHIP: PARKED"));
		break;
	}

	case EMyLaneState::Returning:
		Text = TEXT("SHIP: RETURNING TO LANE");
		break;

	default:
		Text = (Ship->HasPilot() || Ship->GetController()) ? FString::Printf(TEXT("SHIP: PILOTED BY %s"), *Pilot) : FString(TEXT("SHIP: NO LANE"));
		break;
	}

	if (Ship->IsSpawnProtected())
	{
		Text += TEXT("   (PROTECTED)");
	}

	return Text;
}

FString UMyMatchHUDWidget::GetEndReasonText() const
{
	using namespace MyMatchHUDPrivate;
	const AMyGameState* MyGameState = GameState.Get();

	if (!MyGameState)
	{
		return FString();
	}

	const EMyMatchResult Result = MyGameState->GetMatchResult();
	const uint8 Winner = MyGameState->GetWinningTeam();
	const uint8 Loser = Winner < MyMatch::NumTeams ? 1 - Winner : MyMatch::NoTeam;

	if (Result == EMyMatchResult::PracticeOver)
	{
		return TEXT("Your last ship went down");
	}

	switch (MyGameState->GetEndReason())
	{
	case EMyMatchEndReason::Eliminated:
		return Result == EMyMatchResult::TeamWon ? FString::Printf(TEXT("%s ran out of ships"), *TeamName(Loser)) : FString(TEXT("Both teams ran out of ships"));

	case EMyMatchEndReason::Forfeit:
		return FString::Printf(TEXT("%s forfeited"), *TeamName(Loser));

	case EMyMatchEndReason::TimeLimit:
		if (Result != EMyMatchResult::TeamWon)
		{
			return TEXT("Time up: nothing between the teams");
		}
		// The server's tie-break order: lives (UMyTeamLibrary::GetTimeLimitLives), then hull, then the race
		if (UMyTeamLibrary::GetTimeLimitLives(Teams[0]) != UMyTeamLibrary::GetTimeLimitLives(Teams[1]))
		{
			return UMyMatchSettings::Get()->bTimeLimitCountsHandicap
				? FString::Printf(TEXT("Time up: %s has more ships left"), *TeamName(Winner))
				: FString::Printf(TEXT("Time up: %s lost fewer ships"), *TeamName(Winner));
		}
		if (Teams[0].ShipHealthPct != Teams[1].ShipHealthPct)
		{
			return FString::Printf(TEXT("Time up: %s has more hull left"), *TeamName(Winner));
		}
		return FString::Printf(TEXT("Time up: %s got further in the race"), *TeamName(Winner));

	case EMyMatchEndReason::Host:
		return TEXT("Ended by the host");

	default:
		return FString();
	}
}

void UMyMatchHUDWidget::RefreshMarkers(const FGeometry& MyGeometry, const APlayerController* PC, const APawn* LocalPawn)
{
	using namespace MyMatchHUDPrivate;
	const FVector2D Size(MyGeometry.GetLocalSize());
	const APlayerCameraManager* Camera = PC->PlayerCameraManager;

	if (!Camera || Size.X < 10.0 || Size.Y < 10.0)
	{
		return;
	}

	const FVector CameraLocation = Camera->GetCameraLocation();
	const FRotator CameraRotation = Camera->GetCameraRotation();
	const bool bOnFoot = Cast<ACharacter>(LocalPawn) && !UAirshipSubsystem::IsShipBorne(LocalPawn);

	for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
	{
		const AAirshipPawn* Ship = Teams[Team].Ship;

		// Not the ship this player is at the helm of: he sees it
		if (!Teams[Team].bActive || !IsAlive(Ship) || Ship == LocalPawn)
		{
			continue;
		}

		// Practice shows the own team only
		if (!bVersus && Team != LocalTeam)
		{
			continue;
		}

		FShipMarker Marker;
		Marker.TeamId = Team;
		Marker.bOwn = Team == LocalTeam;
		const FVector WorldPoint = Ship->GetActorLocation() + FVector(0.0, 0.0, MarkerHeight);
		const double Distance = FVector::Dist(CameraLocation, WorldPoint);
		Marker.DistanceM = static_cast<float>(Distance / 100.0);
		Marker.HealthAlpha = Teams[Team].ShipHealthPct / 100.f;
		Marker.bProtected = Ship->IsSpawnProtected();
		Marker.bGrappleHint = Marker.bOwn && bOnFoot && Rules.bGrappleShips && LocalPawn
			&& FVector::Dist(LocalPawn->GetActorLocation(), Ship->GetActorLocation()) <= ShipHookDistance;
		Marker.bFlashOn = AttackFlashTimeLeft[Team] <= 0.f || FMath::Frac(HUDTime * 4.f) < 0.5f;

		FVector2D ScreenPosition;
		const FVector Local = CameraRotation.UnrotateVector(WorldPoint - CameraLocation);
		const bool bProjected = Local.X > 1.0 && UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, WorldPoint, ScreenPosition, true);
		const double Margin = 24.0;
		Marker.bOnScreen = bProjected && ScreenPosition.X >= Margin && ScreenPosition.X <= Size.X - Margin && ScreenPosition.Y >= Margin && ScreenPosition.Y <= Size.Y - Margin;

		if (Marker.bOnScreen)
		{
			Marker.Position = ScreenPosition;
		}
		else
		{
			// The own ship sticks to the edge; the enemy's only within EnemyMarkerRange
			if (!Marker.bOwn && Distance > EnemyMarkerRange)
			{
				continue;
			}

			FVector2D Direction(Local.Y, -Local.Z);
			Direction = Direction.IsNearlyZero() ? FVector2D(0.0, 1.0) : Direction.GetSafeNormal();
			Marker.Direction = Direction;
			Marker.Position = EdgePoint(Size, Direction, 56.f);
		}

		Markers.Add(Marker);
	}
}

void UMyMatchHUDWidget::RefreshNameTags(const APlayerController* PC, const APawn* LocalPawn, float DeltaSeconds)
{
	using namespace MyMatchHUDPrivate;
	const AMyGameState* MyGameState = GameState.Get();
	const APlayerState* LocalState = PC->PlayerState;
	const UWorld* World = GetWorld();

	if (!MyGameState || !World || !PC->PlayerCameraManager)
	{
		return;
	}

	const FVector CameraLocation = PC->PlayerCameraManager->GetCameraLocation();
	EnemyTraceTimer -= DeltaSeconds;
	const bool bTraceNow = EnemyTraceTimer <= 0.f;

	if (bTraceNow)
	{
		EnemyTraceTimer = EnemyTagTraceInterval;

		for (auto It = EnemyInSight.CreateIterator(); It; ++It)
		{
			if (!It.Key().IsValid())
			{
				It.RemoveCurrent();
			}
		}
	}

	for (const APlayerState* PlayerState : MyGameState->PlayerArray)
	{
		const AMyPlayerState* MyPlayerState = Cast<AMyPlayerState>(PlayerState);

		// A seated pilot's pawn is his ship: its marker shows him
		const ACharacter* Character = MyPlayerState && MyPlayerState != LocalState ? Cast<ACharacter>(MyPlayerState->GetPawn()) : nullptr;

		if (!IsValid(Character) || Character == LocalPawn)
		{
			continue;
		}

		if (Character->Implements<UMyCombatInterface>() && IMyCombatInterface::Execute_IsDead(const_cast<ACharacter*>(Character)))
		{
			continue;
		}

		const uint8 Team = MyPlayerState->GetTeamId();

		if (Team >= MyMatch::NumTeams)
		{
			continue;
		}

		// Teammates always (up to the relevancy range); enemies nearby or in sight. Every player is the same mech, so
		// this is the only way to tell friend from foe on foot
		if (Team != LocalTeam)
		{
			const double Distance = FVector::Dist(CameraLocation, Character->GetActorLocation());

			if (Distance > EnemyTagRange)
			{
				bool* bInSight = EnemyInSight.Find(Character);

				if (bTraceNow || !bInSight)
				{
					FHitResult Hit;
					FCollisionQueryParams Params(SCENE_QUERY_STAT(MatchNameTagSight), false);
					Params.AddIgnoredActor(LocalPawn);
					Params.AddIgnoredActor(Character);
					const bool bBlocked = World->LineTraceSingleByChannel(Hit, CameraLocation, Character->GetActorLocation(), ECC_Visibility, Params);
					EnemyInSight.Add(Character, !bBlocked);
					bInSight = EnemyInSight.Find(Character);
				}

				if (!bInSight || !*bInSight)
				{
					continue;
				}
			}
		}

		FVector2D ScreenPosition;
		const FVector WorldPoint = Character->GetActorLocation() + FVector(0.0, 0.0, NameTagHeight);
		const FVector Local = PC->PlayerCameraManager->GetCameraRotation().UnrotateVector(WorldPoint - CameraLocation);

		if (Local.X > 1.0 && UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, WorldPoint, ScreenPosition, true))
		{
			FNameTag& Tag = NameTags.AddDefaulted_GetRef();
			Tag.Position = ScreenPosition;
			Tag.Name = MyPlayerState->GetPlayerName();
			Tag.Color = TeamColor(Team);
		}
	}
}

void UMyMatchHUDWidget::RefreshCrosshair(const APlayerController* PC, const APawn* LocalPawn)
{
	// On foot or at a gun only: a pilot has the ship's own crosshair
	const UWorld* World = GetWorld();

	if (!World || !Cast<ACharacter>(LocalPawn) || LocalTeam >= MyMatch::NumTeams)
	{
		return;
	}

	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(MatchCrosshairTeammate), false);
	Params.AddIgnoredActor(LocalPawn);

	if (World->LineTraceSingleByChannel(Hit, ViewLocation, ViewLocation + ViewRotation.Vector() * CrosshairTraceDistance, ECC_Pawn, Params))
	{
		const AActor* HitActor = Hit.GetActor();
		bTeammateUnderCrosshair = Cast<ACharacter>(HitActor) && UMyTeamLibrary::AreTeammates(PC->PlayerState, HitActor);
	}
}

int32 UMyMatchHUDWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements,
	int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	int32 Layer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);

	if (Phase == EMyMatchPhase::None)
	{
		return Layer;
	}

	using namespace MyMatchHUDPrivate;
	const FLinearColor Opacity = InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const float Scale = AllottedGeometry.Scale;

	const FSlateFontInfo BigFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 20);
	const FSlateFontInfo LabelFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 12);
	const FSlateFontInfo ValueFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 11);
	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 9);
	const FSlateFontInfo TagFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 13);
	const FSlateFontInfo ToastFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 16);
	const FSlateFontInfo EndTitleFont = FCoreStyle::GetDefaultFontStyle(TEXT("Black"), 40);
	const FSlateFontInfo EndFont = FCoreStyle::GetDefaultFontStyle(TEXT("Bold"), 15);

	// MakeBox fills a RoundedBox brush with the element tint alone (UAirshipHUDWidget's note): the colour goes in the tint
	auto Box = [&](const FVector2f& Position, const FVector2f& BoxSize, const FSlateBrush& Brush, const FLinearColor& Tint, int32 InLayer)
	{
		FSlateDrawElement::MakeBox(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(BoxSize, FSlateLayoutTransform(Position)), &Brush,
			ESlateDrawEffect::None, Brush.GetTint(InWidgetStyle) * Tint * Opacity);
	};

	auto Diamond = [&](const FVector2f& Centre, float Half, const FSlateBrush& Brush, const FLinearColor& Tint, int32 InLayer)
	{
		const FVector2f BoxSize(Half * 1.414f, Half * 1.414f);
		FSlateDrawElement::MakeBox(OutDrawElements, InLayer,
			AllottedGeometry.ToPaintGeometry(BoxSize, FSlateLayoutTransform(Centre - BoxSize * 0.5f), FSlateRenderTransform(FQuat2D(FMath::DegreesToRadians(45.f)))),
			&Brush, ESlateDrawEffect::None, Brush.GetTint(InWidgetStyle) * Tint * Opacity);
	};

	auto Text = [&](const FVector2f& Position, const FString& String, const FSlateFontInfo& Font, const FLinearColor& Color, int32 InLayer)
	{
		FSlateDrawElement::MakeText(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(FVector2f(FMath::Max(Size.X, 1.f), Font.Size * 1.6f), FSlateLayoutTransform(Position)),
			String, Font, ESlateDrawEffect::None, Color * Opacity);
	};

	// Text centred on X, with a 1 px ink drop shadow where it sits on the world
	auto CentredText = [&](float CentreX, float Y, const FString& String, const FSlateFontInfo& Font, const FLinearColor& Color, int32 InLayer, bool bShadow)
	{
		const float Width = MeasureWidth(String, Font, Scale);

		if (bShadow)
		{
			Text(FVector2f(CentreX - Width * 0.5f + 1.5f, Y + 1.5f), String, Font, InkColor, InLayer);
		}
		Text(FVector2f(CentreX - Width * 0.5f, Y), String, Font, Color, InLayer + 1);
	};

	// An ink tag with paper (or coloured) text, centred on X
	auto Tag = [&](float CentreX, float Y, const FString& String, const FSlateFontInfo& Font, const FLinearColor& TextColor, float Alpha, int32 InLayer)
	{
		const float Width = MeasureWidth(String, Font, Scale);
		const FVector2f TagSize(Width + 16.f, Font.Size * 1.6f + 4.f);
		Box(FVector2f(CentreX - TagSize.X * 0.5f, Y), TagSize, TagBrush, FLinearColor(1.f, 1.f, 1.f, 0.85f * Alpha), InLayer);
		Text(FVector2f(CentreX - Width * 0.5f, Y + 2.f), String, Font, TextColor * FLinearColor(1.f, 1.f, 1.f, Alpha), InLayer + 1);
	};

	auto Lines = [&](const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 InLayer)
	{
		FSlateDrawElement::MakeLines(OutDrawElements, InLayer, AllottedGeometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color * Opacity, true, Thickness);
	};

	auto Bar = [&](const FVector2f& Position, const FVector2f& TrackSize, float Alpha, const FLinearColor& Color, int32 InLayer)
	{
		Box(Position, TrackSize, TrackBrush, FLinearColor::White, InLayer);
		const float Inset = 2.5f;
		const float FillWidth = (TrackSize.X - 2.f * Inset) * FMath::Clamp(Alpha, 0.f, 1.f);

		if (FillWidth > 0.5f)
		{
			Box(Position + FVector2f(Inset, Inset), FVector2f(FillWidth, TrackSize.Y - 2.f * Inset), FillBrush, Color, InLayer + 1);
		}
	};

	// --- Name tags (under everything else) ---
	for (const FNameTag& NameTag : NameTags)
	{
		CentredText(static_cast<float>(NameTag.Position.X), static_cast<float>(NameTag.Position.Y) - 20.f, NameTag.Name, TagFont, NameTag.Color, Layer + 1, true);
	}

	// --- Ship markers ---
	for (const FShipMarker& Marker : Markers)
	{
		const FLinearColor Color = TeamColor(Marker.TeamId);
		const FVector2f Centre(Marker.Position);
		const float Alpha = Marker.bFlashOn ? 1.f : 0.25f;
		const int32 MarkerLayer = Layer + 4;

		if (Marker.bProtected)
		{
			// The spawn shield: a paper ring round the diamond
			Diamond(Centre, 19.f, PanelBrush, FLinearColor(1.f, 1.f, 1.f, 0.9f * Alpha), MarkerLayer);
		}

		Diamond(Centre, 13.f, ShadowBrush, FLinearColor(1.f, 1.f, 1.f, Alpha), MarkerLayer + 1);
		Diamond(Centre, 10.f, FillBrush, Color * FLinearColor(1.f, 1.f, 1.f, Alpha), MarkerLayer + 2);

		if (!Marker.bOnScreen)
		{
			// An ink arrow pointing out of the screen, toward the ship
			const FVector2f Out(Marker.Direction);
			const FVector2f Side(-Out.Y, Out.X);
			const FVector2f Tip = Centre + Out * 30.f;
			const FVector2f BaseCentre = Centre + Out * 18.f;
			Lines({ BaseCentre + Side * 8.f, Tip, BaseCentre - Side * 8.f }, InkColor * FLinearColor(1.f, 1.f, 1.f, Alpha), 3.f, MarkerLayer + 1);
		}

		float LabelY = Centre.Y + 16.f;

		if (Marker.bOwn)
		{
			CentredText(Centre.X, Centre.Y - 34.f, TEXT("YOU"), LabelFont, Color, MarkerLayer, true);
		}

		CentredText(Centre.X, LabelY, FString::Printf(TEXT("%d m"), FMath::RoundToInt(Marker.DistanceM)), ValueFont, PaperColor, MarkerLayer, true);
		LabelY += 18.f;
		Bar(FVector2f(Centre.X - 22.f, LabelY), FVector2f(44.f, 8.f), Marker.HealthAlpha, Color, MarkerLayer);
		LabelY += 12.f;

		if (Marker.bGrappleHint)
		{
			Tag(Centre.X, LabelY, TEXT("AIM + GRAPPLE"), SmallFont, PaperColor, 1.f, MarkerLayer);
		}
	}

	// --- Crosshair: TEAMMATE (a shot at him does nothing, this says why) ---
	if (bTeammateUnderCrosshair && LocalTeam < MyMatch::NumTeams)
	{
		Tag(Size.X * 0.5f, Size.Y * 0.5f + 28.f, TEXT("TEAMMATE"), LabelFont, TeamColor(LocalTeam), 1.f, Layer + 8);
	}

	// The lobby (SPEC_B_LOBBY 6.6): no match bar; the lobby widget shows its strip, or this one stands in
	if (Phase == EMyMatchPhase::Lobby)
	{
		if (!LobbyStripText.IsEmpty())
		{
			Tag(Size.X * 0.5f, BarTop, LobbyStripText, LabelFont, PaperColor, 1.f, Layer + 10);
		}
	}
	else
	{
		// --- Match bar, top centre ---
		const FVector2f BarSizeF(BarSize);
		const FVector2f BarPos((Size.X - BarSizeF.X) * 0.5f, BarTop);
		const int32 BarLayer = Layer + 10;
		Box(BarPos + FVector2f(4.f, 4.f), BarSizeF, ShadowBrush, FLinearColor::White, BarLayer);
		Box(BarPos, BarSizeF, PanelBrush, FLinearColor::White, BarLayer + 1);

		const float Pad = 14.f;
		const float BoxStep = 14.f;
		const FVector2f LifeBox(11.f, 13.f);
		const float HullWidth = 80.f;

		for (uint8 Team = 0; Team < MyMatch::NumTeams; ++Team)
		{
			const FMyTeamState& State = Teams[Team];

			// Practice shows the own team only; waiting shows both (the player counts)
			if (Phase != EMyMatchPhase::WaitingToStart && !State.bActive)
			{
				continue;
			}
			if (!bVersus && Phase != EMyMatchPhase::WaitingToStart && Team != LocalTeam && LocalTeam < MyMatch::NumTeams)
			{
				continue;
			}

			const bool bLeft = Team == 0;
			const FLinearColor Color = TeamColor(Team);
			const FString Name = TeamName(Team) + (Team == LocalTeam ? TEXT(" (YOU)") : TEXT(""))
				+ (Phase == EMyMatchPhase::WaitingToStart ? FString::Printf(TEXT("  %d"), State.NumPlayers) : FString());
			const float NameWidth = MeasureWidth(Name, LabelFont, Scale);
			const float NameX = bLeft ? BarPos.X + Pad : BarPos.X + BarSizeF.X - Pad - NameWidth;
			Text(FVector2f(NameX, BarPos.Y + 6.f), Name, LabelFont, Darken(Color, 0.8f), BarLayer + 2);

			if (Phase == EMyMatchPhase::WaitingToStart)
			{
				continue;
			}

			const float RowY = BarPos.Y + 30.f;

			// Lives: boxes, filled = left (solo practice: SHIPS LOST n), then the hull bar toward the centre
			float Cursor = bLeft ? BarPos.X + Pad : BarPos.X + BarSizeF.X - Pad;

			if (IsSoloPractice(Team))
			{
				const FString Lost = FString::Printf(TEXT("SHIPS LOST %d"), State.ShipsLost);
				const float LostWidth = MeasureWidth(Lost, ValueFont, Scale);
				Text(FVector2f(bLeft ? Cursor : Cursor - LostWidth, RowY - 2.f), Lost, ValueFont, InkColor, BarLayer + 2);
				Cursor += bLeft ? LostWidth + 8.f : -(LostWidth + 8.f);
			}
			else
			{
				const int32 NumBoxes = FMath::Clamp(FMath::Max(State.LivesLeft, Rules.ShipLives + State.BonusLives), 1, 9);

				for (int32 Index = 0; Index < NumBoxes; ++Index)
				{
					const float X = bLeft ? Cursor + Index * BoxStep : Cursor - (Index + 1) * BoxStep + (BoxStep - LifeBox.X);
					Box(FVector2f(X, RowY), LifeBox, TrackBrush, FLinearColor::White, BarLayer + 2);

					if (Index < State.LivesLeft)
					{
						Box(FVector2f(X + 2.f, RowY + 2.f), LifeBox - FVector2f(4.f, 4.f), FillBrush, Color, BarLayer + 3);
					}
				}

				Cursor += bLeft ? NumBoxes * BoxStep + 6.f : -(NumBoxes * BoxStep + 6.f);
			}

			const float HullX = bLeft ? Cursor : Cursor - HullWidth;
			Bar(FVector2f(HullX, RowY), FVector2f(HullWidth, 13.f), State.ShipHealthPct / 100.f, bShipAlive[Team] ? Color : Darken(PaperColor, 0.6f), BarLayer + 2);
		}

		// The phase or the clock
		CentredText(BarPos.X + BarSizeF.X * 0.5f, BarPos.Y + 14.f, CentreText, Phase == EMyMatchPhase::WaitingToStart ? LabelFont : BigFont, CentreColor, BarLayer + 3, false);

		if (!CentreSubText.IsEmpty())
		{
			CentredText(BarPos.X + BarSizeF.X * 0.5f, BarPos.Y + 34.f, CentreSubText, SmallFont, InkColor * 0.7f, BarLayer + 3, false);
		}

		if (!StatusText.IsEmpty() && Phase != EMyMatchPhase::WaitingToStart)
		{
			CentredText(BarPos.X + BarSizeF.X * 0.5f, BarPos.Y + BarSizeF.Y - 20.f, StatusText, SmallFont, InkColor, BarLayer + 3, false);
		}

		float BelowBar = BarPos.Y + BarSizeF.Y + 10.f;

		// The objective line
		if (ObjectiveTimeLeft > 0.f && Phase == EMyMatchPhase::InProgress)
		{
			const float Alpha = FMath::Clamp(ObjectiveTimeLeft / 0.5f, 0.f, 1.f);
			Tag(BarPos.X + BarSizeF.X * 0.5f, BelowBar, ObjectiveText, ValueFont, PaperColor, Alpha, BarLayer);
			BelowBar += 28.f;
		}
	}

	// --- Toasts, centre, newest at the bottom ---
	float ToastY = Size.Y * 0.28f;

	for (const FToast& Toast : Toasts)
	{
		const float Alpha = FMath::Clamp(Toast.TimeLeft / 0.5f, 0.f, 1.f);
		Tag(Size.X * 0.5f, ToastY, Toast.Text, ToastFont, Toast.Color, Alpha, Layer + 20);
		ToastY += 36.f;
	}

	// --- End panel ---
	if (Phase == EMyMatchPhase::Ended)
	{
		const FVector2f PanelSize(520.f, 260.f);
		const FVector2f PanelPos((Size.X - PanelSize.X) * 0.5f, (Size.Y - PanelSize.Y) * 0.5f);
		const int32 EndLayer = Layer + 30;
		Box(PanelPos + FVector2f(6.f, 6.f), PanelSize, ShadowBrush, FLinearColor::White, EndLayer);
		Box(PanelPos, PanelSize, PanelBrush, FLinearColor::White, EndLayer + 1);

		const float CentreX = PanelPos.X + PanelSize.X * 0.5f;
		CentredText(CentreX, PanelPos.Y + 28.f, EndTitle, EndTitleFont, CentreColor, EndLayer + 2, false);
		CentredText(CentreX, PanelPos.Y + 110.f, EndReason, EndFont, InkColor, EndLayer + 2, false);
		CentredText(CentreX, PanelPos.Y + 150.f, EndShipsLine, EndFont, InkColor, EndLayer + 2, false);
		CentredText(CentreX, PanelPos.Y + 200.f, EndRestartLine, ValueFont, InkColor * 0.7f, EndLayer + 2, false);

		if (!EndHostLine.IsEmpty())
		{
			CentredText(CentreX, PanelPos.Y + 224.f, EndHostLine, SmallFont, InkColor * 0.7f, EndLayer + 2, false);
		}
	}

	return Layer + 40;
}
