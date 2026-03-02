// Fill out your copyright notice in the Description page of Project Settings.


#include "Interfaces/MyCombatInterface.h"


// Add default functionality here for any IMyCombatInterface functions that are not pure virtual.


void IMyCombatInterface::HandleDeath()
{
}


ECharacterClass IMyCombatInterface::GetCharacterClass()
{
	return ECharacterClass::Warrior;
}
