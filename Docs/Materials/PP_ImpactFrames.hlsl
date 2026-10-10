// Custom node body for M_PP_ImpactFrames (post process, After Tonemapping, Emissive = this, output float3)
// Inputs: UV (ScreenPosition ViewportUV), Time, ImpactTime, Duration, Center (float2, screen point the lines rush from), LineCount, ViewSize
// The graph also needs any SceneTexture node (unconnected is fine) so SceneTextureLookup compiles.
//
// t = 0 .. 1 over Duration:
//   0.00-0.12  zoom blur on the normal scene
//   0.12-0.37  white background, black speed lines, characters white with black outline
//   0.37-0.60  inverted: black background, white speed lines
//   0.60-0.78  white with sparse thin lines, characters as ink outlines
//   0.78-1.00  white flash fading back to the scene

float t = saturate((Time - ImpactTime) / max(Duration, 0.01));
float3 Scene = SceneTextureLookup(GetDefaultSceneTextureUV(Parameters, 14), 14, false).rgb;
if (t <= 0.0 || t >= 1.0) return Scene;

float2 Texel = 1.0 / max(ViewSize, 1.0);
float Aspect = ViewSize.x / max(ViewSize.y, 1.0);

// Character mask from custom depth: on screen where the character is nearest
struct F
{
	static float Mask(FMaterialPixelParameters Parameters, float2 Offset)
	{
		float2 SUV = GetDefaultSceneTextureUV(Parameters, 13) + Offset;
		float CD = SceneTextureLookup(SUV, 13, false).r;
		float SD = SceneTextureLookup(GetDefaultSceneTextureUV(Parameters, 1) + Offset, 1, false).r;
		return (CD < 1e6 && CD <= SD + 2.0) ? 1.0 : 0.0;
	}
	static float Lum(FMaterialPixelParameters Parameters, float2 Offset)
	{
		return dot(SceneTextureLookup(GetDefaultSceneTextureUV(Parameters, 14) + Offset, 14, false).rgb, float3(0.3, 0.59, 0.11));
	}
	static float Hash(float n) { return frac(sin(n * 127.1) * 43758.5453); }
};

// Phase 0: zoom blur toward Center
if (t < 0.12)
{
	float3 Acc = 0;
	float2 Dir = (Center - UV);
	for (int i = 0; i < 8; i++)
	{
		Acc += SceneTextureLookup(GetDefaultSceneTextureUV(Parameters, 14) + Dir * (i * 0.012), 14, false).rgb;
	}
	return Acc / 8.0;
}

// Character silhouette and outline
float M = F::Mask(Parameters, 0);
float Th = 2.5;
float Edge = 0;
Edge = max(Edge, abs(M - F::Mask(Parameters, float2( Th, 0) * Texel)));
Edge = max(Edge, abs(M - F::Mask(Parameters, float2(-Th, 0) * Texel)));
Edge = max(Edge, abs(M - F::Mask(Parameters, float2(0,  Th) * Texel)));
Edge = max(Edge, abs(M - F::Mask(Parameters, float2(0, -Th) * Texel)));

// Ink detail inside the character from scene luminance edges
float Lx = F::Lum(Parameters, float2(1.5, 0) * Texel) - F::Lum(Parameters, float2(-1.5, 0) * Texel);
float Ly = F::Lum(Parameters, float2(0, 1.5) * Texel) - F::Lum(Parameters, float2(0, -1.5) * Texel);
float Ink = step(0.18, sqrt(Lx * Lx + Ly * Ly)) * M;

// Radial speed lines, re-rolled every 1/16 of the duration so they boil like hand drawn frames
float2 D = (UV - Center) * float2(Aspect, 1);
float R = length(D);
float A = atan2(D.y, D.x) / 6.2831853 + 0.5;
float Frame = floor(t * 16.0);
float Lines = 0;
for (int L = 0; L < 2; L++)
{
	float N = LineCount * (L == 0 ? 1.0 : 0.37);
	float Cell = floor(A * N);
	float Seed = Cell + Frame * 91.7 + L * 13.3;
	float Width = lerp(0.08, 0.7, F::Hash(Seed));
	float Start = lerp(0.12, 0.55, F::Hash(Seed + 7.1));
	float InCell = abs(frac(A * N) - 0.5) * 2.0;
	// taper: thin near the start radius, full width at the screen edge
	float Taper = saturate((R - Start) / 0.5);
	Lines = max(Lines, step(InCell, Width * Taper) * step(Start, R));
}
float Vignette = smoothstep(0.75, 1.05, R);

float3 Col;
if (t < 0.37)
{
	float Bg = 1.0 - max(Lines, Vignette);
	Col = M > 0.5 ? 1.0 : Bg;
	Col *= 1.0 - Edge;
}
else if (t < 0.60)
{
	float Bg = Lines * (1.0 - Vignette);
	Col = M > 0.5 ? 1.0 : Bg;
	Col *= 1.0 - Edge;
}
else if (t < 0.78)
{
	float Sparse = Lines * step(0.6, F::Hash(floor(A * LineCount) + 3.3)) * step(0.45, R);
	Col = 1.0 - max(max(Edge, Ink), Sparse);
}
else
{
	float k = (t - 0.78) / 0.22;
	Col = lerp(float3(1, 1, 1), Scene, k * k);
}
return Col;
