// Editor-only console commands that fill two gaps in the Python material API (UE 5.8), for materials and material
// functions built from scripts:
//   Aura.MatAddComment <AssetPath> <X> <Y> <SizeX> <SizeY> <RRGGBB> <Text...>
//   Aura.MatClearComments <AssetPath>
//   Aura.MatLinkReroutes <AssetPath>
//   Aura.MatSetAttributeInput <MaterialPath> <SetMaterialAttributesName> <Attribute> [<SourceExpressionName> [<OutputIndex>]]
//   Aura.MatResizeComment <AssetPath> <X> <Y> <SizeX> <SizeY> <TextPrefix...>
//   Aura.MatSetRootPos <MaterialPath> <X> <Y>
// MaterialEditingLibrary.create_material_expression puts a comment into the expression list instead of the comment list,
// and SizeX/SizeY aren't exposed, so a script can't make a real comment box. NamedRerouteUsage::Declaration isn't exposed
// either, so a script can't point a usage at its declaration. MatLinkReroutes links every usage whose Desc is
// "reroute:<Name>" to the declaration with that Name (and clears the Desc). A SetMaterialAttributes node only adds the
// pin for a new AttributeSetTypes entry while a material editor shows it, so MatSetAttributeInput adds the pin for
// <Attribute> (an EMaterialProperty name without MP_, e.g. BaseColor) and optionally connects an expression (by object
// name) to it. MatResizeComment moves and resizes the comment boxes whose text starts with <TextPrefix> (e.g. to grow a
// section box around new nodes). MatSetRootPos moves the material's root (result) node: UMaterial::EditorX/EditorY are plain
// UPROPERTY()s that Python can't read or write, and the editor refuses the console SET command. Save the asset afterwards.
#if WITH_EDITOR
#include "HAL/IConsoleManager.h"
#include "Materials/Material.h"
#include "Materials/MaterialFunction.h"
#include "Materials/MaterialExpressionComment.h"
#include "Materials/MaterialExpressionNamedReroute.h"
#include "Materials/MaterialExpressionSetMaterialAttributes.h"
#include "SceneTypes.h"

namespace
{
	FMaterialExpressionCollection* LoadCollection(const FString& Path, UObject*& OutAsset)
	{
		OutAsset=LoadObject<UObject>(nullptr,*Path);
		if (UMaterial* Material=Cast<UMaterial>(OutAsset))
		{
			return &Material->GetExpressionCollection();
		}
		if (UMaterialFunction* Function=Cast<UMaterialFunction>(OutAsset))
		{
			return &Function->GetExpressionCollection();
		}
		UE_LOG(LogTemp,Warning,TEXT("Aura.Mat*: no material or material function at %s"),*Path);
		return nullptr;
	}

	void FinishEdit(UObject* Asset)
	{
		Asset->PreEditChange(nullptr);
		Asset->PostEditChange();
		Asset->MarkPackageDirty();
	}

	void MatAddComment(const TArray<FString>& Args)
	{
		if (Args.Num()<7)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatAddComment <AssetPath> <X> <Y> <SizeX> <SizeY> <RRGGBB> <Text...>"));
			return;
		}
		UObject* Asset=nullptr;
		FMaterialExpressionCollection* Collection=LoadCollection(Args[0],Asset);
		if (!Collection)
		{
			return;
		}
		UMaterialExpressionComment* Comment=NewObject<UMaterialExpressionComment>(Asset,NAME_None,RF_Transactional);
		Comment->MaterialExpressionEditorX=FCString::Atoi(*Args[1]);
		Comment->MaterialExpressionEditorY=FCString::Atoi(*Args[2]);
		Comment->SizeX=FCString::Atoi(*Args[3]);
		Comment->SizeY=FCString::Atoi(*Args[4]);
		Comment->CommentColor=FLinearColor(FColor::FromHex(Args[5]));
		TArray<FString> Words(&Args[6],Args.Num()-6);
		Comment->Text=FString::Join(Words,TEXT(" "));
		Comment->FontSize=20;
		Comment->UpdateMaterialExpressionGuid(true,true);
		if (UMaterial* Material=Cast<UMaterial>(Asset))
		{
			Comment->Material=Material;
		}
		Collection->AddComment(Comment);
		FinishEdit(Asset);
		UE_LOG(LogTemp,Log,TEXT("Aura.MatAddComment: %s '%s' at (%d,%d) size (%d,%d)"),*Args[0],*Comment->Text,
			Comment->MaterialExpressionEditorX,Comment->MaterialExpressionEditorY,Comment->SizeX,Comment->SizeY);
	}

	void MatClearComments(const TArray<FString>& Args)
	{
		for (const FString& Path : Args)
		{
			UObject* Asset=nullptr;
			FMaterialExpressionCollection* Collection=LoadCollection(Path,Asset);
			if (!Collection)
			{
				continue;
			}
			const int32 Count=Collection->EditorComments.Num();
			TArray<TObjectPtr<UMaterialExpressionComment>> Comments=Collection->EditorComments;
			for (UMaterialExpressionComment* Comment : Comments)
			{
				Collection->RemoveComment(Comment);
			}
			FinishEdit(Asset);
			UE_LOG(LogTemp,Log,TEXT("Aura.MatClearComments: %s removed %d"),*Path,Count);
		}
	}

	void MatLinkReroutes(const TArray<FString>& Args)
	{
		for (const FString& Path : Args)
		{
			UObject* Asset=nullptr;
			FMaterialExpressionCollection* Collection=LoadCollection(Path,Asset);
			if (!Collection)
			{
				continue;
			}
			TMap<FName,UMaterialExpressionNamedRerouteDeclaration*> Declarations;
			for (UMaterialExpression* Expression : Collection->Expressions)
			{
				if (UMaterialExpressionNamedRerouteDeclaration* Declaration=Cast<UMaterialExpressionNamedRerouteDeclaration>(Expression))
				{
					if (!Declaration->VariableGuid.IsValid())
					{
						Declaration->VariableGuid=FGuid::NewGuid();
					}
					Declarations.Add(Declaration->Name,Declaration);
				}
			}
			int32 Linked=0;
			TArray<FString> Missing;
			for (UMaterialExpression* Expression : Collection->Expressions)
			{
				UMaterialExpressionNamedRerouteUsage* Usage=Cast<UMaterialExpressionNamedRerouteUsage>(Expression);
				if (!Usage || !Usage->Desc.StartsWith(TEXT("reroute:")))
				{
					continue;
				}
				const FName Name(*Usage->Desc.Mid(8));
				if (UMaterialExpressionNamedRerouteDeclaration** Found=Declarations.Find(Name))
				{
					Usage->Declaration=*Found;
					Usage->DeclarationGuid=(*Found)->VariableGuid;
					Usage->Desc.Empty();
					++Linked;
				}
				else
				{
					Missing.Add(Name.ToString());
				}
			}
			FinishEdit(Asset);
			UE_LOG(LogTemp,Log,TEXT("Aura.MatLinkReroutes: %s linked %d, declarations %d, missing [%s]"),*Path,Linked,
				Declarations.Num(),*FString::Join(Missing,TEXT(", ")));
		}
	}

	void MatResizeComment(const TArray<FString>& Args)
	{
		if (Args.Num()<6)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatResizeComment <AssetPath> <X> <Y> <SizeX> <SizeY> <TextPrefix...>"));
			return;
		}
		UObject* Asset=nullptr;
		FMaterialExpressionCollection* Collection=LoadCollection(Args[0],Asset);
		if (!Collection)
		{
			return;
		}
		TArray<FString> Words(&Args[5],Args.Num()-5);
		const FString Prefix=FString::Join(Words,TEXT(" "));
		int32 Count=0;
		for (UMaterialExpressionComment* Comment : Collection->EditorComments)
		{
			if (Comment && Comment->Text.StartsWith(Prefix))
			{
				Comment->Modify();
				Comment->MaterialExpressionEditorX=FCString::Atoi(*Args[1]);
				Comment->MaterialExpressionEditorY=FCString::Atoi(*Args[2]);
				Comment->SizeX=FCString::Atoi(*Args[3]);
				Comment->SizeY=FCString::Atoi(*Args[4]);
				++Count;
			}
		}
		FinishEdit(Asset);
		UE_LOG(LogTemp,Log,TEXT("Aura.MatResizeComment: %s '%s' resized %d"),*Args[0],*Prefix,Count);
	}

	void MatSetRootPos(const TArray<FString>& Args)
	{
		if (Args.Num()<3)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatSetRootPos <MaterialPath> <X> <Y>"));
			return;
		}
		UMaterial* Material=LoadObject<UMaterial>(nullptr,*Args[0]);
		if (!Material)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatSetRootPos: no material at %s"),*Args[0]);
			return;
		}
		// editor layout data only: no PostEditChange, so nothing recompiles
		Material->Modify();
		Material->EditorX=FCString::Atoi(*Args[1]);
		Material->EditorY=FCString::Atoi(*Args[2]);
		Material->MarkPackageDirty();
		UE_LOG(LogTemp,Log,TEXT("Aura.MatSetRootPos: %s root node at (%d,%d)"),*Args[0],Material->EditorX,Material->EditorY);
	}

	void MatSetAttributeInput(const TArray<FString>& Args)
	{
		if (Args.Num()<3)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatSetAttributeInput <MaterialPath> <SetMaterialAttributesName> <Attribute> [<SourceExpressionName> [<OutputIndex>]]"));
			return;
		}
		UMaterial* Material=LoadObject<UMaterial>(nullptr,*Args[0]);
		if (!Material)
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatSetAttributeInput: no material at %s"),*Args[0]);
			return;
		}
		UMaterialExpressionSetMaterialAttributes* SetNode=nullptr;
		UMaterialExpression* Source=nullptr;
		for (UMaterialExpression* Expression : Material->GetExpressions())
		{
			if (!Expression)
			{
				continue;
			}
			if (Expression->GetName()==Args[1])
			{
				SetNode=Cast<UMaterialExpressionSetMaterialAttributes>(Expression);
			}
			if (Args.Num()>3 && Expression->GetName()==Args[3])
			{
				Source=Expression;
			}
		}
		const int64 Value=StaticEnum<EMaterialProperty>()->GetValueByNameString(TEXT("MP_")+Args[2]);
		if (!SetNode || Value==INDEX_NONE || (Args.Num()>3 && !Source))
		{
			UE_LOG(LogTemp,Warning,TEXT("Aura.MatSetAttributeInput: %s: set node %s %s, attribute %s %s, source %s %s"),*Args[0],*Args[1],
				SetNode?TEXT("found"):TEXT("MISSING"),*Args[2],Value==INDEX_NONE?TEXT("UNKNOWN"):TEXT("ok"),
				Args.Num()>3?*Args[3]:TEXT("-"),(Args.Num()>3 && !Source)?TEXT("MISSING"):TEXT("ok"));
			return;
		}
		const EMaterialProperty Property=static_cast<EMaterialProperty>(Value);
		const int32 OutputIndex=Args.Num()>4?FCString::Atoi(*Args[4]):0;
		SetNode->Modify();
		const int32 InputIndex=SetNode->CreateOrGetInputAttribute(Property);
		const bool bConnected=Source && SetNode->ConnectInputAttribute(Property,Source,OutputIndex);
		FinishEdit(Material);
		UE_LOG(LogTemp,Log,TEXT("Aura.MatSetAttributeInput: %s %s pin %d '%s' %s%s"),*Args[0],*Args[1],InputIndex,
			*SetNode->GetInputName(InputIndex).ToString(),Source?TEXT("<- "):TEXT(""),
			Source?*FString::Printf(TEXT("%s:%d %s"),*Source->GetName(),OutputIndex,bConnected?TEXT("connected"):TEXT("NOT CONNECTED")):TEXT("(no source)"));
	}

	FAutoConsoleCommand GMatAddComment(
		TEXT("Aura.MatAddComment"),
		TEXT("Add a comment box to a material or material function: <AssetPath> <X> <Y> <SizeX> <SizeY> <RRGGBB> <Text...>"),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatAddComment));

	FAutoConsoleCommand GMatClearComments(
		TEXT("Aura.MatClearComments"),
		TEXT("Remove every comment box from the given materials or material functions (paths)."),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatClearComments));

	FAutoConsoleCommand GMatLinkReroutes(
		TEXT("Aura.MatLinkReroutes"),
		TEXT("Link each NamedRerouteUsage whose Desc is 'reroute:<Name>' to the declaration called <Name> (paths)."),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatLinkReroutes));

	FAutoConsoleCommand GMatResizeComment(
		TEXT("Aura.MatResizeComment"),
		TEXT("Move and resize the comment boxes whose text starts with a prefix: <AssetPath> <X> <Y> <SizeX> <SizeY> <TextPrefix...>"),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatResizeComment));

	FAutoConsoleCommand GMatSetRootPos(
		TEXT("Aura.MatSetRootPos"),
		TEXT("Move the root (result) node of a material in its graph: <MaterialPath> <X> <Y>"),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatSetRootPos));

	FAutoConsoleCommand GMatSetAttributeInput(
		TEXT("Aura.MatSetAttributeInput"),
		TEXT("Add an attribute pin to a SetMaterialAttributes node, optionally connected: <MaterialPath> <SetNodeName> <Attribute> [<SourceName> [<OutputIndex>]]"),
		FConsoleCommandWithArgsDelegate::CreateStatic(&MatSetAttributeInput));
}
#endif
