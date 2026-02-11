// Fill out your copyright notice in the Description page of Project Settings.


#include "UI/UserWidgets/MyUserWidget.h"

void UMyUserWidget::SetWidgetController(UObject* InWidgetController)
{
	MyWidgetController=InWidgetController;
	WidgetControllerSet();
}

void UMyUserWidget::WidgetControllerSet_Implementation()
{
}

