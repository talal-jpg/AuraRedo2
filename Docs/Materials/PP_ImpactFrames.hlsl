// Custom node body for M_PP_ImpactFrames (Post Process, Scene Color After Tonemapping, Emissive = this node, output Float3)
// Inputs:
//   Time         Time node (game time, same clock as UWorld::GetTimeSeconds)
//   ImpactTime   scalar param, set by AMyPlayerController2::StartHitImpact to the world time of the hit
//   Duration     scalar param, length of the whole sequence
//   Center       vector param (rg = viewport UV the speed lines rush out from)
//   LineCount    scalar param, number of speed line slots around the circle
//   InkThreshold scalar param, luminance edge strength that becomes an ink line inside characters
//   SC, SD, CD   SceneTexture nodes PostProcessInput0, SceneDepth, CustomDepth (wired in so the material binds them)
//   PreviewT     scalar param, -1 in game; 0..1 freezes the sequence at that point for previewing in the editor
//
// t = 0 .. 1 over Duration, matching the reference panels:
//   0.00-0.12  zoom blur on the normal scene
//   0.12-0.37  white background, black speed lines and ink frame, characters white with a black outline
//   0.37-0.60  inverted: black background, dense thin white lines, characters white with a black outline
//   0.60-0.78  white page, sparse thin lines, characters drawn as ink outlines
//   0.78-1.00  white flash fading back to the scene

struct FImpactFrames
{
	// 1 where a custom depth mesh (a character) is the nearest thing on screen
	float Mask(FMaterialPixelParameters Parameters, float2 PixelOffset)
	{
		float CustomD = SceneTextureFetchFunc(Parameters, PPI_CustomDepth, PixelOffset).r;
		float SceneD = SceneTextureFetchFunc(Parameters, PPI_SceneDepth, PixelOffset).r;
		return (CustomD < 1000000.0 && CustomD <= SceneD + 2.0) ? 1.0 : 0.0;
	}
	float Lum(FMaterialPixelParameters Parameters, float2 PixelOffset)
	{
		return dot(SceneTextureFetchFunc(Parameters, PPI_PostProcessInput0, PixelOffset).rgb, float3(0.3, 0.59, 0.11));
	}
	float Depth(FMaterialPixelParameters Parameters, float2 PixelOffset)
	{
		return SceneTextureFetchFunc(Parameters, PPI_SceneDepth, PixelOffset).r;
	}
	float Hash(float N)
	{
		return frac(sin(N * 127.1 + 311.7) * 43758.5453);
	}
	// Anti-aliased radial line: InCell is 0 on the line's centre ray and 1 at its slot edge, AAw is InCell units per pixel
	float Line(float InCell, float HalfWidth, float AAw)
	{
		float HalfPx = HalfWidth / AAw;
		float DistPx = InCell / AAw;
		return saturate(min(HalfPx, DistPx + 0.5) - max(-HalfPx, DistPx - 0.5));
	}
};
FImpactFrames F;

float3 Scene = SC.rgb;
float t = (Time - ImpactTime) / max(Duration, 0.01);
if (PreviewT >= 0.0) t = PreviewT;
if (t < 0.0 || t >= 1.0) return Scene;

float2 UV = GetViewportUV(Parameters);
float2 ViewSize = View.ViewSizeAndInvSize.xy;
float Aspect = ViewSize.x / max(ViewSize.y, 1.0);
// Output height for line anti-aliasing (the material is also compiled for debug view shaders, which have no PostProcessOutput)
#if POST_PROCESS_MATERIAL
float OutH = PostProcessOutput_ViewportSize.y;
#else
float OutH = View.ViewSizeAndInvSize.y;
#endif

// Phase 0: zoom blur toward Center, noise jittered so it reads as one smooth smear
if (t < 0.12)
{
	float2 Dir = (Center - UV) * GetSceneTextureViewSize(PPI_PostProcessInput0).xy * (t / 0.12);
	float IGN = frac(52.9829189 * frac(dot(Parameters.SvPosition.xy, float2(0.06711056, 0.00583715))));
	float3 Acc = 0;
	for (int i = 0; i < 16; i++)
	{
		Acc += SceneTextureFetchFunc(Parameters, PPI_PostProcessInput0, Dir * ((i + IGN) * (0.11 / 16.0))).rgb;
	}
	return Acc / 16.0;
}

// Character silhouette (custom depth) and its outline
float M = (CD.r < 1000000.0 && CD.r <= SD.r + 2.0) ? 1.0 : 0.0;
float OutlinePx = max(1.0, round(3.0 * ViewSize.y / 1080.0));
float Edge = 0;
Edge = max(Edge, abs(M - F.Mask(Parameters, float2( OutlinePx, 0))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(-OutlinePx, 0))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(0,  OutlinePx))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(0, -OutlinePx))));

// Ink detail inside characters: luminance edges plus depth creases
float Lx = F.Lum(Parameters, float2(1.5, 0)) - F.Lum(Parameters, float2(-1.5, 0));
float Ly = F.Lum(Parameters, float2(0, 1.5)) - F.Lum(Parameters, float2(0, -1.5));
float DC = SD.r;
float DLap = abs(F.Depth(Parameters, float2(1, 0)) + F.Depth(Parameters, float2(-1, 0)) + F.Depth(Parameters, float2(0, 1)) + F.Depth(Parameters, float2(0, -1)) - 4.0 * DC);
float Ink = max(step(InkThreshold, sqrt(Lx * Lx + Ly * Ly)), step(0.02 * DC, DLap)) * M;

// Polar coordinates around Center
float2 D = (UV - Center) * float2(Aspect, 1.0);
float R = length(D);
float A = atan2(D.y, D.x) / 6.2831853 + 0.5;

// Every panel gets a whole number of drawings at about 12 a second, and starts a fresh drawing at its cut
float PhaseIndex = t < 0.37 ? 0.0 : (t < 0.60 ? 1.0 : 2.0);
float PhaseStart = t < 0.37 ? 0.12 : (t < 0.60 ? 0.37 : 0.60);
float PhaseLen   = t < 0.37 ? 0.25 : (t < 0.60 ? 0.23 : 0.18);
float Drawings   = max(1.0, round(PhaseLen * max(Duration, 0.01) * 12.0));
float Frame = PhaseIndex * 64.0 + min(floor((t - PhaseStart) / PhaseLen * Drawings), Drawings - 1.0);

// Ink frame: superellipse in viewport UV so it reaches all four edges
float2 Q = abs(UV - 0.5) * 2.0;
float Box = pow(pow(Q.x, 4.0) + pow(Q.y, 4.0), 0.25);
float Vig = saturate((Box - 0.88) / 0.12);

// Thick black wedges (panel 2). Toward the border they widen until they merge into the solid frame
float Lines = 0;
float Border = 0;
for (int L = 0; L < 2; L++)
{
	float N = floor(max(LineCount, 8.0) * (L == 0 ? 1.0 : 0.41));
	float AAw = N / (3.14159265 * max(R, 0.001) * OutH);
	float Seed = floor(A * N) + Frame * 91.7 + L * 13.3;
	float Width = lerp(0.05, 0.6, F.Hash(Seed));
	float Start = lerp(0.25, 0.70, F.Hash(Seed + 7.1));
	float Jitter = (F.Hash(Seed + 3.7) - 0.5) * 0.6;
	float InCell = abs(frac(A * N) - 0.5 - Jitter * (1.0 - Width) * 0.5) * 2.0;
	// wedge: thin where the line starts, widest at the screen edge
	float Taper = saturate((R - Start) / 0.6);
	Lines = max(Lines, F.Line(InCell, Width * Taper, AAw));
	Border = max(Border, F.Line(InCell, Width * Taper * step(Start, R) + 0.35 * Vig * Vig, AAw) * step(0.0001, Vig));
}
Border = max(Border, step(0.985, Box));

float3 Col;
if (t < 0.37)
{
	float Bg = 1.0 - max(Lines, Border);
	float C = M > 0.5 ? 1.0 : Bg;
	Col = C * (1.0 - Edge);
}
else if (t < 0.60)
{
	// Inverted panel: its own dense field of thin white lines that reach every screen edge
	float Rays = 0;
	for (int RL = 0; RL < 2; RL++)
	{
		float RN = round(max(LineCount, 8.0) * (RL == 0 ? 2.5 : 1.0));
		float RAAw = RN / (3.14159265 * max(R, 0.001) * OutH);
		float RSeed = floor(A * RN) + Frame * 57.3 + RL * 29.1 + 101.0;
		float RWidth = RL == 0 ? lerp(0.05, 0.30, F.Hash(RSeed)) : lerp(0.04, 0.20, F.Hash(RSeed));
		float RStart = RL == 0 ? lerp(0.06, 0.35, F.Hash(RSeed + 7.1)) : lerp(0.15, 0.45, F.Hash(RSeed + 7.1));
		float RJitter = (F.Hash(RSeed + 3.7) - 0.5) * 0.6;
		float RInCell = abs(frac(A * RN) - 0.5 - RJitter * (1.0 - RWidth) * 0.5) * 2.0;
		float RTaper = saturate((R - RStart) / 0.35);
		Rays = max(Rays, F.Line(RInCell, RWidth * RTaper, RAAw));
	}
	float C = M > 0.5 ? 1.0 : Rays;
	Col = C * (1.0 - Edge);
}
else if (t < 0.78)
{
	// Sparse thin pointed lines on a white page, kept off the characters
	float NS = floor(max(LineCount, 8.0));
	float SAAw = NS / (3.14159265 * max(R, 0.001) * OutH);
	float SSeed = floor(A * NS) + Frame * 91.7 + 29.9;
	float SWidth = lerp(0.03, 0.12, F.Hash(SSeed));
	float SStart = lerp(0.35, 0.60, F.Hash(SSeed + 7.1));
	float SJitter = (F.Hash(SSeed + 3.7) - 0.5) * 0.6;
	float SInCell = abs(frac(A * NS) - 0.5 - SJitter * (1.0 - SWidth) * 0.5) * 2.0;
	float STaper = saturate((R - SStart) / 0.4);
	float Keep = step(F.Hash(SSeed + 11.3), 0.5);
	float Sparse = F.Line(SInCell, SWidth * STaper, SAAw) * Keep * (1.0 - M);
	Col = 1.0 - max(max(Edge, Ink), Sparse);
}
else
{
	float K = (t - 0.78) / 0.22;
	Col = lerp(float3(1, 1, 1), Scene, K * K);
}
return Col;
