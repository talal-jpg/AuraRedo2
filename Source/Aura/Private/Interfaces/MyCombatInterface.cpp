// Fill out your copyright notice in the Description page of Project Settings.


#include "Interfaces/MyCombatInterface.h"


// Add default functionality here for any IMyCombatInterface functions that are not pure virtual.
int32 IMyCombatInterface::GetLevel()
{
	return 0;
}


void IMyCombatInterface::HandleDeath()
{
}

int32 IMyCombatInterface::GetPlayerLevel()
{
	return 1;
}

ECharacterClass IMyCombatInterface::GetCharacterClass()
{
	return ECharacterClass::Warrior;
}
