// Custom node body for M_PP_CastFrames, the beam caster's impact frames (Post Process, Scene Color After Tonemapping, Emissive = this node, output Float3)
// Inputs:
//   Time         Time node (game time, same clock as UWorld::GetTimeSeconds)
//   ImpactTime   scalar param, set by AMyPlayerController2::StartHitImpact to the world time the beam landed
//   Duration     scalar param, length of the whole sequence
//   Center       vector param (rg = viewport UV the radial lines rush out from)
//   LineCount    scalar param, number of radial line slots around the circle
//   InkThreshold scalar param, luminance edge strength that becomes an ink line inside characters
//   BandAngle    scalar param, angle of the diagonal bands in degrees (positive rises to the right)
//   Navy, Blue, Pale  vector params, the three inks of the palette
//   SC, SD, CD   SceneTexture nodes PostProcessInput0, SceneDepth, CustomDepth (wired in so the material binds them)
//   PreviewT     scalar param, -1 in game; 0..1 freezes the sequence at that point for previewing in the editor
//
// t = 0 .. 1 over Duration, matching the caster reference panels:
//   0.00-0.20  navy page with bright blue diagonal bands, characters navy with white highlights and rim
//   0.20-0.40  mid blue page hatched with fine white diagonals, characters navy with white highlights and rim
//   0.40-0.60  inverted: characters white with navy ink, bands behind black radial wedges
//   0.60-0.80  blue page with dense navy radial lines, characters navy with white rim
//   0.80-1.00  pale page with thin radial lines, characters as a hatched ink sketch, fading back to the scene

struct FCastFrames
{
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
	// Anti-aliased parallel stripes: 1 where frac(X) is within Width of 0, PxPerUnit is how many pixels one unit of X spans
	float Stripe(float X, float Width, float PxPerUnit)
	{
		float D = abs(frac(X + 0.5) - 0.5) * PxPerUnit;
		float HalfPx = Width * 0.5 * PxPerUnit;
		return saturate(min(HalfPx, D + 0.5) - max(-HalfPx, D - 0.5));
	}
	// Radial line field around the centre, one random line per slot
	float Rays(float A, float R, float N, float Seed0, float WMin, float WMax, float SMin, float SMax, float TaperLen, float OutH)
	{
		float AAw = N / (3.14159265 * max(R, 0.001) * OutH);
		float Seed = floor(A * N) + Seed0;
		float Width = lerp(WMin, WMax, Hash(Seed));
		float Start = lerp(SMin, SMax, Hash(Seed + 7.1));
		float Jitter = (Hash(Seed + 3.7) - 0.5) * 0.6;
		float InCell = abs(frac(A * N) - 0.5 - Jitter * (1.0 - Width) * 0.5) * 2.0;
		float Taper = saturate((R - Start) / TaperLen);
		return Line(InCell, Width * Taper, AAw);
	}
};
FCastFrames F;

float3 Scene = SC.rgb;
float t = (Time - ImpactTime) / max(Duration, 0.01);
if (PreviewT >= 0.0) t = PreviewT;
if (t < 0.0 || t >= 1.0) return Scene;

float2 UV = GetViewportUV(Parameters);
float2 ViewSize = View.ViewSizeAndInvSize.xy;
float Aspect = ViewSize.x / max(ViewSize.y, 1.0);
// Output height for anti-aliasing (the material is also compiled for debug view shaders, which have no PostProcessOutput)
#if POST_PROCESS_MATERIAL
float OutH = PostProcessOutput_ViewportSize.y;
#else
float OutH = View.ViewSizeAndInvSize.y;
#endif

// Characters: custom depth silhouette, outline, ink detail and a two tone posterise of their shading
float M = (CD.r < 1000000.0 && CD.r <= SD.r + 2.0) ? 1.0 : 0.0;
float OutlinePx = max(1.0, round(3.0 * ViewSize.y / 1080.0));
float Edge = 0;
Edge = max(Edge, abs(M - F.Mask(Parameters, float2( OutlinePx, 0))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(-OutlinePx, 0))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(0,  OutlinePx))));
Edge = max(Edge, abs(M - F.Mask(Parameters, float2(0, -OutlinePx))));
float Lx = F.Lum(Parameters, float2(1.5, 0)) - F.Lum(Parameters, float2(-1.5, 0));
float Ly = F.Lum(Parameters, float2(0, 1.5)) - F.Lum(Parameters, float2(0, -1.5));
float DC = SD.r;
float DLap = abs(F.Depth(Parameters, float2(1, 0)) + F.Depth(Parameters, float2(-1, 0)) + F.Depth(Parameters, float2(0, 1)) + F.Depth(Parameters, float2(0, -1)) - 4.0 * DC);
float Ink = max(step(InkThreshold, sqrt(Lx * Lx + Ly * Ly)), step(0.02 * DC, DLap)) * M;
float L0 = dot(Scene, float3(0.3, 0.59, 0.11));
float Highlight = step(0.68, L0) * M;
float Shadow = step(L0, 0.22) * M;

// Diagonal band space: V runs across the bands, in screen heights
float2 P = (UV - 0.5) * float2(Aspect, 1.0);
float Ang = radians(BandAngle);
float V = dot(P, float2(sin(Ang), cos(Ang)));

// Polar coordinates around Center for the radial lines
float2 D = (UV - Center) * float2(Aspect, 1.0);
float R = length(D);
float A = atan2(D.y, D.x) / 6.2831853 + 0.5;

// Each panel gets a whole number of drawings at about 12 a second, and starts a fresh drawing at its cut
float PhaseIndex = floor(saturate(t) * 5.0);
float PhaseT = frac(saturate(t) * 5.0);
float Drawings = max(1.0, round(0.2 * max(Duration, 0.01) * 12.0));
float Frame = PhaseIndex * 64.0 + min(floor(PhaseT * Drawings), Drawings - 1.0);

// Bands: random width blue bands with thin white edges, re-rolled per drawing
float BandN = 7.0;
float BandCell = floor(V * BandN + Frame * 0.37);
float BandHash = F.Hash(BandCell + Frame * 17.3);
float BandIn = frac(V * BandN + Frame * 0.37);
float IsBand = step(0.45, BandHash);
float BandW = lerp(0.35, 0.9, F.Hash(BandCell + 4.4));
float InBand = IsBand * step(abs(BandIn - 0.5), BandW * 0.5);
float BandEdge = IsBand * F.Stripe(BandIn - 0.5 + BandW * 0.5, 0.04, OutH / BandN) * step(0.6, F.Hash(BandCell + 9.9));
float Thin = F.Stripe(V * 31.0 + F.Hash(Frame) * 3.0, 0.08, OutH / 31.0) * step(0.7, F.Hash(floor(V * 31.0) + Frame * 3.1));

float3 Col;
if (PhaseIndex < 1.0)
{
	float3 Bg = lerp(Navy, Blue, InBand);
	Bg = lerp(Bg, Pale, max(BandEdge, Thin * (1.0 - InBand)));
	float3 Ch = lerp(Navy, Pale, Highlight);
	Col = M > 0.5 ? Ch : Bg;
	Col = lerp(Col, Pale, Edge);
}
else if (PhaseIndex < 2.0)
{
	float Hatch = F.Stripe(V * 140.0, 0.22, OutH / 140.0);
	float3 Mid = lerp(Navy, Blue, 0.55);
	float3 Bg = lerp(Mid, Blue, InBand);
	Bg = lerp(Bg, Pale, max(Hatch * 0.85, BandEdge));
	float3 Ch = lerp(Navy, Pale, Highlight);
	Col = M > 0.5 ? Ch : Bg;
	Col = lerp(Col, Pale, Edge);
}
else if (PhaseIndex < 3.0)
{
	float Wedges = F.Rays(A, R, floor(max(LineCount, 8.0) * 0.6), Frame * 91.7, 0.05, 0.6, 0.15, 0.55, 0.6, OutH);
	float3 Bg = lerp(Navy * 0.6, Blue, InBand);
	Bg = lerp(Bg, Pale, BandEdge);
	Bg = lerp(Bg, float3(0.0, 0.0, 0.02), Wedges);
	float3 Ch = lerp(float3(1, 1, 1), Navy, max(Ink, Shadow));
	Col = M > 0.5 ? Ch : Bg;
	Col = lerp(Col, Navy, Edge);
}
else if (PhaseIndex < 4.0)
{
	float N1 = round(max(LineCount, 8.0) * 2.5);
	float Dense = max(F.Rays(A, R, N1, Frame * 57.3 + 101.0, 0.08, 0.45, 0.05, 0.30, 0.35, OutH),
	                  F.Rays(A, R, round(max(LineCount, 8.0)), Frame * 57.3 + 130.1, 0.05, 0.3, 0.15, 0.45, 0.35, OutH));
	float3 Bg = lerp(Blue, Navy, Dense);
	float3 Ch = lerp(Navy, Pale, Highlight * 0.7);
	Col = M > 0.5 ? Ch : Bg;
	Col = lerp(Col, Pale, Edge);
}
else
{
	float Sparse = F.Rays(A, R, floor(max(LineCount, 8.0)), Frame * 91.7 + 29.9, 0.03, 0.12, 0.35, 0.6, 0.4, OutH)
	             * step(F.Hash(floor(A * floor(max(LineCount, 8.0))) + Frame * 91.7 + 41.2), 0.5) * (1.0 - M);
	float Hatch = F.Stripe((UV.x * Aspect + UV.y) * 160.0, 0.3, OutH / 160.0) * Shadow;
	float InkAll = max(max(Edge, Ink), max(Sparse, Hatch));
	float3 Sketch = lerp(Pale, Navy * 0.4, InkAll);
	Col = lerp(Sketch, Scene, Pow2(saturate((t - 0.9) / 0.1)));
}
return Col;
