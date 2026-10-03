// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "MultiplayerSessionTypes.generated.h"

//
// FName keys used with FOnlineSessionSettings::Set/Get and FOnlineSessionSearch's
// QuerySettings::Set. GameName and MatchType already existed as raw FName("...")
// literals in MultiplayerSessionsSubsystem.cpp; the rest are new for MainMenu2.
//
namespace AuraSessionKeys
{
	inline const FName GameName(TEXT("GameName"));
	inline const FName MatchType(TEXT("MatchType"));
	inline const FName JoinCode(TEXT("JoinCode"));
	inline const FName Difficulty(TEXT("Difficulty"));
	inline const FName Rules(TEXT("Rules"));
	inline const FName Listed(TEXT("Listed"));
}

UENUM(BlueprintType)
enum class EAuraSessionPrivacy : uint8
{
	Public UMETA(DisplayName = "Public"),
	FriendsOnly UMETA(DisplayName = "Friends Only"),
	CodeOnly UMETA(DisplayName = "Code Only")
};

UENUM(BlueprintType)
enum class EAuraSearchDistance : uint8
{
	Close UMETA(DisplayName = "Close"),
	Medium UMETA(DisplayName = "Medium"),
	Far UMETA(DisplayName = "Far"),
	Worldwide UMETA(DisplayName = "Worldwide")
};

USTRUCT(BlueprintType)
struct FAuraHostSettings
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	int32 NumPublicConnections = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	FString MatchType = TEXT("FreeForAll");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	EAuraSessionPrivacy Privacy = EAuraSessionPrivacy::Public;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	int32 Difficulty = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	FString Rules = TEXT("Default");

	// Leave empty to have the subsystem generate one with GenerateJoinCode().
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	FString JoinCode;
};

USTRUCT(BlueprintType)
struct FAuraSessionFilter
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	EAuraSearchDistance Distance = EAuraSearchDistance::Worldwide;

	// -1 = any difficulty
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	int32 Difficulty = -1;

	// Empty = any ruleset
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	FString Rules;

	// Non-empty triggers a server-side code lookup instead of a normal browse.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	FString JoinCode;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	int32 MaxSearchResults = 10000;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Aura|Session")
	bool bOnlyJoinable = true;
};

USTRUCT(BlueprintType)
struct FAuraSessionInfo
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	FString SessionId;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	FString HostName;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	FString MatchType;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	FString Rules;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	FString JoinCode;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	int32 Difficulty = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	int32 PingInMs = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	int32 OpenSlots = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	int32 MaxSlots = 0;

	// Index into the subsystem's cached FOnlineSessionSearchResult array; pass to JoinCachedSession().
	UPROPERTY(BlueprintReadOnly, Category = "Aura|Session")
	int32 ResultIndex = INDEX_NONE;
};
