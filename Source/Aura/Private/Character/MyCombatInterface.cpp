// Fill out your copyright notice in the Description page of Project Settings.


#include "Character/MyCombatInterface.h"


// Add default functionality here for any IMyCombatInterface functions that are not pure virtual.
int32 IMyCombatInterface::GetLevel()
{
	return 0;
}

FVector IMyCombatInterface::GetCombatSocketLocation()
{
	return FVector::ZeroVector;
}

void IMyCombatInterface::HandleDeath()
{
}
