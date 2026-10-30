# Aura Menu3 style spec: Persona 5's menu style with yellow in place of red

**Revision 2 (critic pass).** This revision fixes the following:
- material sizes that depended on the DPI scale
- premultiplied material output
- button brushes drawn outside their widget
- outline and shadow bloat on hovered labels
- places where the spec's own materials put Paper against Yellow
- text inside rotated cards
- gaps in gamepad focus (spawned rows and filters)
- overlays that left the screen behind them focusable
- wrong timing numbers
- missing font fallback and licence staging
- anchors for screens that are not 16:9

**For:** the Unreal developer building `WBP_MainMenu3`, `WBP_SettingsMenu3`, `WBP_PauseMenu3` and their row widgets in UE 5.8.
**Goal:** Persona 5's menu style (one key colour plus black and white, slanted cut-paper shapes, ransom-note headings, fast bursty motion), with **yellow in place of red**. Every asset is original.
**C++:** sections 1 to 11 work with the C++ as it stands at commit `14ed4e1`, with no new C++. Section 12 lists small optional C++ changes that would make it better.
**Units:**
- Design canvas 1920×1080. DPI scale is 1.0 at 1080p with the default Shortest Side curve.
- Sizes are in Slate units, which are px at 1080p with UI Scale 1.0.
- Animation times are in frames at 60 fps (1 f = 16.7 ms).
- Material `*Px` parameters use the same design px and are multiplied by `MPC_UI.PxScale` (§5.0), because materials measure real screen pixels.

---

## 0. Originality rules

- **Copy the design rules, not the assets.** Do not use any of these:
  - Persona logos, characters or Joker poses
  - calling-card art, or star or skull motifs
  - screenshots, textures or sounds
  - Atlus fonts. P5's logo uses Arial Bold Italic and Markin LT Ultra Bold, and its dialogue uses Fontworks Slump DB; all three are commercial ([designbeep](https://designbeep.com/2026/01/09/persona-5-font/), [Megaten Wiki](https://www.megatenwiki.com/wiki/Persona_5)).

  Do not trace screenshots.
- **Do not rebuild any P5 screen 1:1.** In particular:
  - **No calling-card analogue.** P5's calling card is a card carrying a ransom-lettered message and an emblem. Here, ransom lettering is only for headings of 1 to 3 words. No card ever carries a ransom-lettered sentence, a signature, or an emblem or logo stamp.
  - **Home is not P5's main menu.** P5 shows the hero in the background, and he "switches poses depending on the menu you select" ([Mechanics of Magic](https://mechanicsofmagic.com/2022/04/23/visual-design-of-games-persona-5/)). Aura is different in two ways:
    - Its words ride the edge of a hex-platform band.
    - The mech reacts in mech-specific ways: a hex floor segment lights, a visor or reticle callout appears, or an arm rises. These come from Aura's own mech renders, not from a series of full-body hero poses.
- **Aura's own motifs replace P5's:** hexagons (from the hex platforms), the mech silhouette, fog, and hazard stripes. The burst is an irregular 16-point comic burst, never a 5-point star.
- **Check where the art comes from.** Before using `GraffitiUI/minimalSplashScreenMech_1` as the silhouette, confirm it is Aura's own art, or Fab content whose licence allows use in a game.
- **Fonts:** every font below is SIL OFL 1.1. This was checked against each family's `METADATA.pb` and `OFL.txt` in google/fonts.
  - Two fonts have **Reserved Font Names**: Alfa Slab One ("Alfa Slab") and Abril Fatface ("Abril", "Abril Fatface").
  - The OFL FAQ counts a format change or a subset as a modification, and a modified font with an RFN must be renamed ([OFL FAQ](https://openfontlicense.org/ofl-faq/)).
  - UE's Font Face asset keeps the original file bytes. So import the TTFs as they are, and never subset or convert them.
  - Ship the copyright statement, the licence notice and the licence text, which is the OFL FAQ minimum. Also name the fonts in Credits.
- **Yellow-and-black risk:** yellow and black alone can read as Persona 4 or as generic hazard tape. The P5 feel has to come from the **slanted shapes, mixed lettering and burst motion**, not from the colours.

## 1. The look in eight rules (with sources)

1. **Three colours, flat fills, no gradients.** At CEDEC+KYUSHU 2017, P5's UI lead Sudo said the UI uses one main colour plus black and white, and that he "prefer[s] filling in each and every graphic" over gradations ([Famitsu CEDEC report](https://www.famitsu.com/news/201711/13145540.html), [Siliconera](https://www.siliconera.com/atlus-reveals-design-secrets-behind-persona-5s-distinctive-ui/), [Wikipedia](https://en.wikipedia.org/wiki/Persona_5)). Where a fade is needed, use halftone dots instead of a gradient ([TCRF prototype graphics](https://tcrf.net/Proto:Persona_5/December_4th,_2015/Graphics)).
2. **The brightest area holds the important information** ([Siliconera](https://www.siliconera.com/atlus-reveals-design-secrets-behind-persona-5s-distinctive-ui/), [Famitsu](https://www.famitsu.com/news/201711/13145540.html)). In our version yellow is the bright colour, so **text on yellow is always black**.
3. **No plain rectangles.** Use slanted, cut-paper polygons with thick outlines, long pointing wedges, and boxes shaped like manga panels ([Jiaxin Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/), [inside-games](https://www.inside-games.jp/arti/T9kRGPl_2/)).
4. **Big words along a slanted line, on a lopsided screen with a figure on one side** ([Liu, Medium](https://medium.com/game-design-fundamentals/visual-design-of-games-practice-analysis-of-persona-5-royal-61a5c18ba9c1), [Mechanics of Magic](https://mechanicsofmagic.com/2022/04/23/visual-design-of-games-persona-5/)).
5. **The selected item gets bigger and gets a jagged shape behind it in a contrasting accent colour.** P5 uses a "splash of blue" ([Mechanics of Magic](https://mechanicsofmagic.com/2022/04/23/visual-design-of-games-persona-5/), [Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/)). Our accent is **white (Paper)**. Cyan `#00E5FF` is an optional extra and is off by default.
6. **Ransom-note lettering only for words that never change. Anything that changes uses a plain condensed sans** ([Olszewska](https://medium.com/@kinga.olszewska/interface-so-good-that-people-make-cosplay-of-it-persona-5-ui-controversial-yet-brilliant-ac1ec4b95229), [Inverse](https://inverse.com/gaming/persona-5-tactica-user-interface)). Director Hashino said early P5 menus were "impossible to read at first" ([PC Gamer](https://www.pcgamer.com/games/rpg/persona-series-director-says-atluss-flashy-menus-are-actually-really-annoying-to-design)).
7. **Fast, bursty motion, with transitions instead of cuts.** Each deeper menu level changes the angle and the layout. Sources:
   - the "pop punk", "bursting feel" quote ([Famitsu 2023](https://www.famitsu.com/news/202311/29325647.html))
   - the depth rule ([Famitsu CEDEC](https://www.famitsu.com/news/201711/13145540.html))
   - press descriptions ([Kotaku](https://kotaku.com/persona-5-menus-make-everything-better-1794216056), [Kotaku Strikers](https://kotaku.com/persona-5-strikers-menus-are-as-vibrantly-alive-as-its-1846340592))
8. **One shared kit, plus one signature move per screen.** Atlus designed every menu separately ([PC Gamer](https://www.pcgamer.com/games/rpg/persona-series-director-says-atluss-flashy-menus-are-actually-really-annoying-to-design)). We get the same feel more cheaply by reusing one kit.

The sources give **no exact angles, colour values or timings**. Every number in this spec is an Aura design value.

---

## 2. Palette

The UMG colour picker has two hex fields:
- **Hex sRGB:** type the hex values below here.
- **Hex Linear:** uses linear values, as do `Make Linear Color` and C++. The linear column below is for those.

| Token | sRGB hex | Linear RGB | Use |
|---|---|---|---|
| **Yellow** | `#FFD400` | 1.0, 0.6584, 0.0 | Key colour, used everywhere P5 uses red: starbursts, focus slabs, selected plates, header bands, headings on black, card outlines |
| Yellow Hot | `#FFE433` | 1.0, 0.7758, 0.0331 | Mouse-hovered chip plate, active-and-hovered list row |
| Yellow Press | `#E6B800` | 0.7913, 0.4793, 0.0 | Pressed plates |
| Yellow Dim | `#8A7300` | 0.2542, 0.1714, 0.0 | Unselected tags, resting field outlines, inactive headings on black, hovered combo rows |
| **Ink** | `#0B0B0B` | 0.0033, 0.0033, 0.0033 | Background, all text on yellow, outlines, cards. Also set as `HoverTextColor` |
| Coal | `#161616` | 0.008, 0.008, 0.008 | List-row plates, control column, second surface level |
| Coal 2 | `#222222` | 0.016, 0.016, 0.016 | Slider track, scroll track, dividers on black |
| **Paper** | `#FFFFFF` | 1, 1, 1 | Focus accent (burst teeth, misprint copy), stamp plates, join-code plate, the primary word at rest |
| Grey | `#6E6E6E` | 0.1559 (all) | Truly disabled text and outlines, hint text on Paper |
| Grey Light | `#B4B4B4` | 0.4564 (all) | Secondary text: host names, roles, help, privacy explanation, version |
| Error | `#FF4D3A` | 1.0, 0.0742, 0.0423 | **Function only:** errors, offline, bad ping. Always on Ink, always with a word |
| Good | `#38E07B` | 0.0395, 0.7454, 0.1981 | **Function only:** online, good ping. Always on Ink |

**Contrast (WCAG ratio, computed from the linear values):**

| Pair | Ratio | Verdict |
|---|---|---|
| Ink on Yellow | 13.8 | All text on yellow |
| Ink on Yellow Hot / Yellow Press | 15.4 / 10.5 | Chip labels when hovered or pressed |
| Yellow on Ink / Coal | 13.8 / 12.6 | Headings and words on black |
| Paper on Ink | 19.7 | Body text |
| Grey Light on Ink | 9.5 | Secondary text and version string |
| Ink on Yellow Dim | 4.25 | Unselected tag labels (≥ size 30 only, which counts as large text) |
| Paper on Yellow Dim | 4.6 | Hovered combo rows |
| Grey on Paper | 5.1 | Hint text on the code slots |
| Grey on Ink | 3.9 | Disabled text only |
| Error on Ink | 6.0 | OK |
| Yellow on the Pause slab, worst case (94% Ink over a white game frame) | 6.5 | OK |
| **Paper on Yellow** | **1.43** | **Never.** Separate them with an Ink line at least 4 px wide |
| **Error on Yellow** | **2.3** | **Never** |
| C++ ping colours on Yellow | 1.1 to 1.5 | **Never.** Ping always sits on an Ink badge |

**Colour rules**
- Use flat fills only. Fades are halftone dots (`M_UI_Dots`), never gradients.
- Use **only one accent colour on screen at a time** (Paper by default), and only on the focused item.
- Colours already set in C++: the offline status is `#F36C59` sRGB (linear 0.9/0.15/0.1), and the ping colours are green `#95F395`, yellow `#F9E77C` and red `#F9957C`. All of them read fine on Ink (6.7 to 15.7), so give each one an Ink background.

**Colour vision**
- Every state difference is carried by brightness or shape, never by hue alone.
  - Yellow and Yellow Dim differ in brightness (relative luminance 0.68 against 0.18).
  - Focused and selected differ by teeth, motion and the notch.
- Error and Good are a red/green pair that protanopes and deuteranopes confuse, so they always come with a word ("Offline", "Online as …").
- Ping: C++ colours the ping text. Also add `Img_PingBars`, a 1 to 3 bar glyph set in `OnSessionInfoSet` from `Info.PingInMs`:
  - 3 bars at 60 ms or less
  - 2 bars at 120 ms or less
  - 1 bar above that

  These are the same thresholds as the C++ defaults `GoodPingMs` and `OkPingMs`.
- Aura's own colour-blind option calls `SetColorVisionDeficiencyType(..., bCorrectDeficiency = true)`, which re-colours the **whole frame, UI included**.
  - Test the menus with each mode at strength 10. Ink/Yellow must stay at least 7:1, and focus must still read.
  - Tritan correction pushes Yellow toward Paper, which is one more reason Paper and Yellow never touch.
  - The editor's colour vision deficiency preview helps while building.

---

## 3. Type

### 3.1 Fonts (all SIL OFL 1.1, static TTFs from google/fonts, imported unmodified)

| Font asset | Faces to import | Role |
|---|---|---|
| `F_Anton` (Anton) | Regular | Big words: Home and Pause items, action words, confirm titles. Ransom letter pool |
| `F_ArchivoBlack` | Regular | Ransom letters (wide grotesk), stamp initials |
| `F_AlfaSlab` (Alfa Slab One, RFN "Alfa Slab") | Regular | Ransom letters (slab), stamp initials |
| `F_Abril` (Abril Fatface, RFN "Abril") | Regular | Ransom letters (high-contrast serif), at most 1 per word |
| `F_Bebas` (Bebas Neue) | Regular | Tags, tabs, chips, column headers, busy text. Bebas Neue is caps-only |
| `F_Barlow` (Barlow Condensed) | Medium, SemiBold, Bold | **Everything that changes:** names, values, messages, hints, version, status |
| `F_RubikMono` (Rubik Mono One) | Regular | Join code entry and display |
| Fallback typeface of `F_Barlow` | Noto Sans Regular/Bold, plus the Noto Sans SC / JP / KR faces you need | Lobby, host and player names from Steam/EOS can be in any script. The other six families above cover Latin only (google/fonts METADATA subsets). Each CJK face adds several MB, so add only the ones you need |

**Import settings**
- **Distance field rendering (UE 5.5+):**
  - Turn on Project Settings > Engine > User Interface > UMG Fonts > **Enable Distance Field Font Rasterization**.
  - On the Font Face of Anton, Archivo Black, Alfa Slab One, Abril Fatface, Bebas Neue and Rubik Mono One, set **Distance Field Mode > Enable Distance Field Rendering**.
  - Set `UI.SlateSDFText.RasterizationMode=Msdf` (sharp mitered corners) and `UI.SlateSDFText.ResolutionLevel=2`. These are device-profile CVars, so put them in `[ConsoleVariables]` or in DefaultDeviceProfiles ([Epic SDF text](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-signed-distance-field-text-rendering-in-unreal-engine)).
  - Epic notes that thin features are the weak spot of SDF. Check Abril Fatface's hairlines; if they break up, override that one face to Bitmap.
- **Leave Barlow and the Noto fallbacks as bitmap.** SDF has no hinting, and these faces are used at small sizes.
- Loading policy: *Lazy Load*.
- Do not change the project Font DPI, because that rescales every existing HUD font. Sizes below are UMG `Size` values. At the default 96 DPI, px em ≈ Size × 1.33.

### 3.2 Type scale

"Outline" means the mitered Ink font outline. **FX labels always have Outline 0** (§6.2, rule 8).

| Token | Font | UMG Size | ≈ px em | Outline | Skew | Use |
|---|---|---|---|---|---|---|
| D0 | Ransom pool | 150 base | 200 | 6 (loose letters) | per letter | `AURA` logo on Title |
| D1 | Anton | 64 | 85 | 0 (FX label) | 0.21 | Primary word: CREATE SESSION, RESUME |
| D2 | Anton | 52–58 | 69–77 | 0 (FX label) | 0.21 | Other Home and Pause words |
| D3 | Ransom pool | 56 base (×0.88–1.2) | 75 | 4 on loose letters | per letter | Screen titles |
| H1 | Anton | 48–60 | 64–80 | 0 on FX labels, 3 otherwise | 0.21 (0 on ConfirmTitleText) | START LOBBY (60), QUICK JOIN (52), Confirm title (56), CONFIRM (48) |
| H2 | Anton | 36–44 | 48–59 | 0 (FX label) | 0.21 | REFRESH, PLAY SOLO, JOIN WITH CODE |
| T1 | Bebas Neue | 30 (chips 26) | 40 | 0 | 0.21 (0 on BusyText) | Tags, tabs, privacy, chips, busy text (48) |
| T2 | Bebas Neue | 22 | 29 | 0 | 0 | Column headers, form labels, glyph hints |
| B1 | Barlow SemiBold (Bold for names) | 26 | 35 | 0 | 0 | Option labels, lobby and player names |
| B2 | Barlow SemiBold | 22 | 29 | 0 | 0 | Row data, messages, values (values in Bold, Yellow) |
| B3 | Barlow Medium | 20 | 27 | 0 | 0 | Hints, status, privacy explanation |
| M1 | Barlow Medium | 18 | 24 | 0 | 0 | Version string only (smallest size allowed) |
| C1 | Rubik Mono One | 60 | 80 | 0 | 0 | Join code entry |
| C2 | Rubik Mono One | 48–60 | 64–80 | 0 | 0 | Session code display |

**Text settings**
- **Letter spacing:** Anton +20, Bebas +40, Barlow 0, Rubik Mono 0 (it uses `MonospacedWidth`, §7.6).
- **Skew:** `SkewAmount 0.21` equals tan 12°, the house slant. Use it on display faces only, **never** on Barlow or Rubik, and never on `ConfirmTitleText` or `BusyText`.
- **Shadows:**
  - The FX overwrites `ShadowColorAndOpacity` on its labels every frame: opaque black at rest, lerping to white on hover. Any non-zero `ShadowOffset` therefore always shows.
  - **Word labels:** `ShadowOffset (3,3)`. At rest the black shadow is invisible on Ink. On hover the white offset is the one allowed "misprint" detail next to yellow.
  - **Tag labels:** `ShadowOffset (0,0)`, which draws no shadow.
  - **Non-FX display text:** `(4,4)` Ink.
- **Line height:** messages use `LineHeightPercentage 1.05` and wrap at 760 px.

**Text that C++ writes:**
- **Rule:** Barlow or Rubik Mono, upright, no skew.
- **Exceptions:** three short strings drawn from a fixed list:
  - `ConfirmYesText` ("OK" / "Yes"): an FX Word label in Anton
  - `ConfirmTitleText` ("Quit", "Join lobby?", "Kick player", message titles): Anton H1, upright, Skew 0
  - `BusyText` ("Joining lobby…"): Bebas T1 size 48, upright, Skew 0

### 3.3 Ransom headings: `WBP_RansomWord` (Blueprint only)

Build the letters once, in **Event PreConstruct**, so they are stable and also show in the Designer.

**Inputs:**
- `Text`, `Seed` (int; default = sum of the character codes), `BaseSize`, `Mode` (OnInk / OnYellow)
- `InvertEvery` = 4
- `FontPool` = Anton, Archivo Black, Alfa Slab One, Bebas Neue, plus Abril Fatface (at most once per word)
- **`bPlain`** (default false): renders the whole word in Anton, in one colour, with no plates. This is the non-stylised alternative that [XAG 101](https://devdocs.xbox.com/gaming/accessibility/xbox-accessibility-guidelines/101) asks for. C++ #10 connects it to a setting.

**Per letter:**
- Create `WBP_RansomLetter`: an Overlay holding `Img_Plate` (`MI_UI_Plate_Letter`) and a TextBlock.
- Use a Random Stream seeded from `Seed` for:
  - Angle: ±3 to 8°
  - Scale: 0.88 to 1.2
  - Baseline shift: ±6% of size
  - Font: picked from the pool
- Letters overlap by −0.06 × size, using negative HBox slot padding.
- A space becomes a 0.35 × size spacer.

**Colour rules:**

| Mode | Normal letter | Every `InvertEvery`-th letter | One letter per word |
|---|---|---|---|
| OnInk | Yellow, no plate, 4 px Ink outline | Ink on a Paper plate (Ink 3 px outline) | Ink on a Yellow plate |
| OnYellow | Ink, no plate | Yellow on an Ink plate | Ink on a Paper plate with an Ink outline at least 4 px wide (it touches the yellow band) |

**Where to use it:**
- Only for fixed words of 1 to 3 words: screen titles, PAUSE, the logo.
- Keep these words English in every language, as P5 does ([Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/)).
- Never use it for anything C++ writes, and never for a sentence.

**Home and Pause stamp initials:** store the initial and the rest of the word as **two localisable texts**, for example "C" + "REATE SESSION", or keep these words English as well.

---

## 4. Shape kit

### 4.1 Angles

| Element | Value |
|---|---|
| **House slant** (plates, slabs, chips, text skew) | **12°**, leaning forward (`/`) |
| Menu staircase / guide line | 16–20° `/`. Each row steps left by `pitch × tan(angle)`: 38 px per 112 px row on Home, 34 px per 100 px on Pause, 24 px per 84 px on the Browse rail |
| Home band edge | 20° |
| Pause slab edge | 18° |
| Header bands | Rotation −4° |
| Card **images** | −2.5° (Confirm), −3° (Code), −4° (Busy), −5° (action cards), −2° (session card) |
| Tags / tabs (FX rest tilt comes on top) | Alternating −3, +2, −2, +3, −1° |
| Ransom letters | Own ±3–8°, plus the rotation of the plate they sit on. Total at most 12° |
| Display words (fixed text, size ≥ 30, at most 3 words) | At most ±6°, including the FX tilt |
| Wipe slabs | 20° slant |
| Hazard stripes, halftone grid | 45° |
| **Text that C++ writes, all Barlow, all controls** | **0° always**: no rotation, shear or skew |

**Rotate plates, not panels.**
- A tilted card is an Image (or a stack of Images) inside a `Wrap_<Card>` overlay.
- Everything readable or interactive sits in an **upright sibling layer** on top of the card image.
- Never put a ScrollBox, ListView, EditableTextBox, ComboBox, InputKeySelector or any Barlow text inside a rotated, sheared or scaled container. Two reasons:
  - Bitmap Barlow blurs when transformed.
  - Clipping widgets fall back to stencil clipping and stop batching ([Slate clipping](https://dev.epicgames.com/documentation/unreal-engine/using-the-slate-clipping-system-in-unreal-engine)).
- The FX containers (Word, Tag, Chip) are the only interactive containers that tilt.

How depth shows in the composition (the P5 rule that a deeper level changes the angle and layout, [Famitsu](https://www.famitsu.com/news/201711/13145540.html)):
- **Home (level 1):** the menu leans `/` at 20° on the left, and the burst and mech are on the right.
- **Sub-screens (level 2):** a yellow header band at −4° along the top, the content upright, and the burst moved to the bottom right.
- **Modals (level 3):** a centred, tilted card image over a dimmed, dotted backdrop, with the content upright.

### 4.2 Proportions

| Item | Value |
|---|---|
| Outlines | Cards 6 px Yellow on Ink. Yellow plates 5 px Ink. Fields and chips 3 px. Inner lines: Paper 3 px on Ink plates, **Ink 2 px on Yellow plates**, set 8 px inside the outline |
| Cut-paper shadow copy | Offset (10–16, 10–16) px. Yellow under Ink cards, Ink under Yellow plates |
| Corner cut | 24–32 px on cards (top-right corner only), 10 px on chips, none on tags |
| Selected notch | A 14 px wedge in a **reserved 14 px strip at the bottom of the tag**. Button brushes cannot draw outside their widget, so tags are 66 px of plate plus a 14 px strip |
| Label padding inside plates | L 24 / R 32 (extra room for the slant) / T–B 6–10. Tags add 14 px at the bottom for the notch strip |
| Heights | Home/Pause words 100–104 · action words 72–84 · tags 80 (66 + 14) · chips 52–56 · fields 52–60 · option rows 64 · list rows 76–80 |
| Grid and safe area | 8 px grid. 72–96 px side margins, 48 px top and bottom. A `SafeZone` widget at each root |

### 4.3 Pieces

All of these are procedural UI materials (§5), so there are no textures to draw.
- **Plate:** a parallelogram slanted 12°. It can have one corner cut, an outline, an inner line, a shadow copy and a notch. Used for cards, tags, chips, fields, rows, header bands and wipe slabs.
- **Focus slab:** the `Graffiti_*` image (§6). A yellow slab wipes in from the left with jagged Paper teeth and an Ink gap ring around it. It wobbles at 12 fps.
- **Starburst:** 16 irregular points, inner radius 0.62. The same material draws hexagons (`Points 6, InnerR 0.866`) and triangles (`Points 3, InnerR 0.5`).
- **Wedge / tail:** a long triangle (the triangle burst stretched) pointing from a card or menu toward what it refers to.
- **Dividers:** never grey hairlines. Use either of these:
  - a tri-line (Yellow 4 px, a 2 px Ink gap, Paper 2 px) tilted −4° across 60–80% of the column
  - a hazard strip (Yellow/Ink stripes, 14 px, 45°) 12–18 px tall
- **Backgrounds:**
  - Ink base (a plain Image tint, no material), with one starburst per screen.
  - Halftone dots on a **hex lattice** (Aura's own texture) for fades.
  - The mech silhouette as Ink with a Yellow rim and halftone shading.
  - An 18 px hazard strip along the bottom edge.
  - Background layers drift slowly (burst rotation 0.6°/s, dots scroll 12 px/s) while the menu itself moves fast, as P5's background stars do ([Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/)).
- **Text never sits on dots, stripes or burst edges.** It always has a solid plate.

---

## 5. Materials (build recipe)

All of these use **Domain = User Interface, Blend = Translucent**.
- **Output:** Final Color = rgb, Opacity = a, in **straight (un-premultiplied) alpha**.
- **Folder:** `/Game/Level/UI/UserWidgets/MainMenu/Menu3/Materials/`.
- **Images:** on every Image using these materials, set *Draw As = Image* and *Image Size = 1×1*, so the image never drives layout.

**Key technique, no C++ needed:** a material can work out its widget's size in screen pixels from UV derivatives, so shapes can be specified in pixels:
`SizePx = 1 / float2(length(float2(ddx(UV.x), ddy(UV.x))), length(float2(ddx(UV.y), ddy(UV.y))))`, then `P = UV * SizePx`.
- The result is in **physical** pixels, and it works under rotation, scale and shear.
- Anti-alias with `saturate(0.5 - sdf_px)`.
- Every `*Px` parameter is multiplied by `MPC_UI.PxScale` so that it matches Slate units.

### 5.0 `MPC_UI` (Material Parameter Collection)

MPCs work in UI materials (fixed since 4.15).

| Param | Default | Set by |
|---|---|---|
| `Motion` | 1 | Every time-driven term in every material is multiplied by this. Set from `Get Aura Game User Settings → GetScreenShakeEnabled` |
| `Flashes` | 1 | Multiplies flash effects. Set from `GetScreenFlashesEnabled` |
| **`PxScale`** | 1 | `Get Viewport Scale` (Widget Layout Library) |

**Why `PxScale` is needed:**
- Material sizes come out in physical pixels, but slot paddings are Slate units, so they are multiplied by the DPI scale.
- That scale varies: 0.74 on Steam Deck, 1.33 at 1440p, 2.0 at 4K.
- It also includes Aura's UI Scale setting (0.75 to 1.5), which writes `ApplicationScale`. Confirm this once by printing `Get Viewport Scale` at UI Scale 1.5.
- Without the multiplier, a 34 px inset is off by 34 px on each side at 4K.

**When to update:**
- Set all three in **Event Construct** of `WBP_MainMenu3` and `WBP_PauseMenu3`.
- In **Event Tick**, re-read `Get Viewport Scale` and write `PxScale` only when it changed (window resize, resolution change, UI Scale slider).
- In `WBP_SettingsMenu3`, bind **On Check State Changed** of `ScreenShakeCheckBox` and `ScreenFlashesCheckBox` in Blueprint (this works alongside the C++ handler) to update `Motion` and `Flashes` live.
- A dedicated "Reduce UI motion" setting is C++ change #10.

### 5.1 `M_UI_Slab`: the new material for `Graffiti_*` images

This **replaces M_UI_Button for Menu3 only**. Leave `M_UI_Button` and `MI_GraffitiBtn_*` alone, because `WBP_MainMenu2` still uses them.

The C++ FX sets the scalar **`Hovered`** each frame, so that exact name must exist.

| Param | Default | Notes |
|---|---|---|
| `Hovered` | 0 | Set by C++ (FInterpTo speed 12) |
| `RevealGain` | 3 | The slab is complete when Hovered ≥ 0.33, which is frame 2 |
| **`HideBelow`** | 0.12 | Below this nothing is drawn. Without it the Ink ring stayed about 26 frames after unfocus |
| `Mode` | 0 | 0 = Word (nothing at rest). 1 = Tag (dim plate at rest). 2 = Ring (only teeth and ring; the chip button draws its own plate) |
| `SlantDeg` | 12 | |
| **`Inset` (L,T,R,B)** | 34, 22, 34, 22 | In design px. **Must equal the image's negative slot padding**, plus any reserved strip (tags) |
| `GapPx` | 4 | Ink separation ring |
| `BurstPx` | 14 | Maximum tooth length |
| `TeethPx` | 22 | Spacing between teeth |
| `JitterFPS` / `JitterPx` | 12 / 2.5 | Stepped wobble, "animated on twos" |
| `Seed` | 0–1 | Use different MIs (A/B/C) on alternate rows |
| `EdgeOffset` (xy) | 0, 0 | (0,0) = off. Set (10,10) for a Paper misprint copy; it is drawn **under** the Ink ring |
| `RestColor` / `FillColor` / `BackColor` / `GapColor` / `EdgeColor` | Yellow Dim / Yellow / Paper / Ink / Paper | |

**Custom node:**
- Output Type Float4. It feeds Final Color = rgb and Opacity = a.
- Declare these inputs:
  - `UV`: TexCoord 0
  - `Time`: the Time node
  - `Motion` and `PxScale`: from `MPC_UI`
  - the parameters above
- Put the early return after the derivatives so `ddx`/`ddy` stay in uniform control flow.

```hlsl
struct S { float Slab(float2 p, float2 sz, float4 ins, float k) {
  float2 q = p - ins.xy; float2 s = sz - ins.xy - ins.zw;
  float u = q.x - (s.y - q.y)*k;                    // un-shear: the top edge sits k*height to the right, so it leans "/"
  float w = max(s.x - s.y*k, 1);
  float2 d = abs(float2(u - 0.5*w, q.y - 0.5*s.y)) - 0.5*float2(w, s.y);
  return length(max(d,0)) + min(max(d.x,d.y),0); } };
S f;
float2 sz = 1 / max(float2(length(float2(ddx(UV.x),ddy(UV.x))), length(float2(ddx(UV.y),ddy(UV.y)))), 1e-5);
if (abs(Mode-1) > 0.5 && Hovered < HideBelow) return float4(0,0,0,0);    // Word / Ring at rest: draw nothing, skip the rest
float  ps  = PxScale;
float2 P   = UV*sz;
float  h   = (Hovered < HideBelow) ? 0 : saturate(Hovered*RevealGain);
float  on  = step(0.01, h);
float  st  = floor(Time*JitterFPS)*Motion;
float2 j   = (frac(sin(float2(st*12.99+Seed*78.2, st*39.35+Seed*11.1))*43758.55)-0.5)*2*JitterPx*ps*h*Motion;
float  k   = tan(radians(SlantDeg));
float4 ins = Inset*ps;
float  gap = GapPx*ps;
float  sd  = f.Slab(P+j, sz, ins, k);
float  sE  = f.Slab(P+j-EdgeOffset*ps, sz, ins, k);
float2 c   = P - 0.5*sz;
float  t   = atan2(c.y*sz.x/sz.y, c.x)/6.28318 + 0.5;
float  n   = max(8, floor(2*(sz.x+sz.y)/(TeethPx*ps)));
float  r   = frac(sin(floor(t*n)*12.9898 + st*78.233 + Seed*37.719)*43758.5453);
float  sB  = sd - gap - h*BurstPx*ps*(0.35+0.65*r)*(1-abs(frac(t*n)*2-1)) - 2*ps*h;
float  wipe = saturate(0.5 - ((P.x - (sz.y-P.y)*k) - ins.x - h*1.2*sz.x));   // wipes in from the left; the wipe edge is slanted too
float  useEdge = step(0.001, dot(EdgeOffset, EdgeOffset));
// o is premultiplied; lerp(o, float4(c,1), a) is the premultiplied "over" operator
float4 o = float4(BackColor,1) * saturate(0.5-sB) * on;                    // jagged teeth
o = lerp(o, float4(EdgeColor,1), saturate(0.5-sE) * wipe * on * useEdge);   // misprint copy, under the ring
o = lerp(o, float4(GapColor,1),  saturate(0.5-(sd-gap)) * on);              // Ink separation ring
float aS = saturate(0.5-sd);
if (Mode < 0.5)      o = lerp(o, float4(FillColor,1), aS*wipe);             // Word
else if (Mode < 1.5) o = lerp(o, float4(on > 0 ? FillColor : RestColor,1), aS); // Tag
return float4(o.rgb / max(o.a, 1e-4), o.a);                                // straight alpha out
```

Note: in Ring mode the chip button's own plate covers the centre.

| MI | Mode | Colours (Back / Gap / Fill / Edge) | Inset (L,T,R,B) | For |
|---|---|---|---|---|
| `MI_UI_Slab_Word_A/B/C` | 0 | Paper / Ink / Yellow / off | 34, 22, 34, 22 | Home and Pause words, action words on Ink (Seed 0.1 / 0.5 / 0.9) |
| `MI_UI_Slab_Word_OnYellow` | 0 | Ink / Ink / Yellow / Paper (10,10) | 34, 22, 34, 22 | Words sitting on a yellow area. The Ink ring separates the Paper copy from the fill |
| `MI_UI_Slab_Tag` | 1 | Paper / Ink / Yellow / off; Rest = Yellow Dim | **16, 10, 16, 24** | Privacy tags, Options tabs (14 px notch strip reserved) |
| `MI_UI_Slab_Ring` | 2 | Yellow teeth / Ink ring / – / **off** | 16, 10, 16, 10 | Chips (Back, Cancel, No, Copy…), Paste |

### 5.2 `M_UI_Plate`: static shapes

It uses the same `Slab` SDF, the pixel-size trick, `PxScale`, the straight-alpha output and a float4 `Inset`.

Shape modifiers:
- **Corner cut** (top-right): `sd = max(sd, ((P.x-P.y) - (sz.x-ins.z-CornerCutPx*ps-ins.y)) * 0.7071)`.
- **Notch:** union with a triangle (iq `sdTriangle`). It starts at the plate's bottom-left corner and points down into the reserved bottom strip, so the `Inset.w` must hold it.
- **Outline:** where `-OutlinePx < sd < 0`.
- **Inner line:** a band at `-(OutlinePx+InnerGapPx)`.
- **Shadow:** a second copy of the shape at `P - ShadowOffset`, drawn first.
- **Dots:** optional halftone inside the fill.

| Param | Default |
|---|---|
| `FillColor`, `OutlineColor`, `InnerColor`, `ShadowColor` | Ink, Yellow, Paper, Yellow |
| `OutlinePx`, `InnerPx`, `InnerGapPx` | 6, 0, 8 |
| `ShadowOffset` (xy) | 0, 0 |
| `SlantDeg`, `CornerCutPx`, `NotchPx` | 12, 0, 0 |
| `Inset` (L,T,R,B) | As an Image: must cover the outline, shadow and notch, matched with negative padding. **As a Button brush: the brush cannot draw outside the button**, so the shadow and notch must fit inside it |
| `DotsAmount`, `DotsCellPx` | 0, 8 |
| `Opacity` | 1 |

| MI | Settings | Use |
|---|---|---|
| `MI_UI_Plate_Card` | Ink fill, Yellow 6 outline, Paper 3 inner line, cut 28, shadow Yellow (14,14) | Card **images** for Confirm, Busy, Code, action and session cards |
| `MI_UI_Plate_Header` | Yellow fill, Ink 6 outline | Header bands, title tags, the press-any-key plate |
| `MI_UI_Plate_Band` | Ink fill, Yellow 12 outline, Paper 3 inner line, slant 20 | Home band; Pause slab (slant 18, Opacity 0.94) |
| `MI_UI_Plate_Selected` | Yellow fill, Ink 5 outline, **Ink 2 inner line**, notch 14, Inset (0,0,0,14) | Button Disabled brush on tags (selected) |
| `MI_UI_Plate_Field` / `_FieldHover` / `_FieldFocus` / **`_FieldOff`** | Ink fill with outline Yellow Dim 3 / Yellow 3 / Paper 4 + 6 px Yellow left notch / **Coal fill, Grey 2 outline** | Combo, text box and key selector backgrounds |
| `MI_UI_Plate_Chip` / `_ChipHover` / `_ChipPress` / `_ChipOff` | Ink fill with Yellow Dim 3 outline / Yellow Hot fill / Yellow Press fill / Coal fill with Grey 2 outline | Chip button states |
| **`MI_UI_Plate_ChipHazard`** | Ink fill, Yellow 3 outline, a 12 px Yellow/Ink 45° hazard band at the left end only | Hovered brush of Kick and Ban; the label stays on solid Ink |
| `MI_UI_Plate_Veil` | Ink at 70% plus a Grey 3 px diagonal strike (dots off) | Disabled brush on Word buttons |
| `MI_UI_Plate_Flash` | Paper at 35%, no outline | Pressed brush on Word buttons |
| `MI_UI_Plate_Row` / `_RowFill` | Coal fill, Yellow 6 px left notch / Yellow fill with a 12° slanted right end, **580 px wide (label column only)** | List-row plate and its focus fill |
| **`MI_UI_Plate_Menu`** | Ink fill, Yellow 3 outline, **slant 0** | Combo dropdown border (rectangular rows must fit) |
| **`MI_UI_Plate_Lock`** | Coal 90% fill, Grey 2 outline, 45° Grey hatch at 20% | Client "HOST ONLY" lock over the privacy tags |
| `MI_UI_Plate_Letter` | Slant ±8 (random in the Blueprint), outline 3, padding 6/2 | Ransom letters |
| `MI_UI_Plate_FocusRing` | Fill alpha 0, Paper 4 outline, Inset 0 | Focused background of the join-code box; focus rings in spawned rows |
| `MI_UI_Plate_Wipe_Ink` / `_Yellow` | Slant 20, no outline | Wipe slabs |
| `MI_UI_Plate_Thumb` / `_ThumbHover` | Yellow / Paper fill, Ink 3 outline, slant 12, size 20×40 | Slider thumb |
| `MI_UI_Plate_Box` / `_BoxOn` | Ink + Yellow Dim 3 outline / Yellow + Ink diamond mark, slant 8, size 40×40 | Check box |

### 5.3 `M_UI_Burst`

A star SDF; use iq's `sdStar` for exact edges.

| Param | Default |
|---|---|
| Points | 16 |
| InnerR / OuterR | 0.62 / 0.98 |
| Irregularity | 0.2 (random per point from Seed) |
| Color | Yellow |
| RotDegPerSec | 0.6 × Motion |
| BreathAmp / BreathPeriod | 0.02 / 1.6 s |
| StepFPS | 0 = smooth, 12 = stepped |
| DotsEdge | 0–1: halftone fade toward the tips |

MIs:
- `MI_UI_Burst_Main`
- `MI_UI_Hex` (Points 6, InnerR 0.866, Irr 0): spinner, hex floor
- `MI_UI_Tri` (Points 3, InnerR 0.5): tails, combo arrow, chevrons

### 5.4 `M_UI_Dots`: halftone

- **Grid:** `CellPx 9 × PxScale`, `AngleDeg 45`, `HexLattice` switch (on by default; this is Aura's own texture).
- **Coverage:** from `CoverageA` to `CoverageB` (0 → 0.35) along `FadeMode` (linear with `FadeAngle`, or radial).
- **Dot radius:** `sqrt(coverage/π)` in cell units, anti-aliased with `fwidth`.
- **Other inputs:** `ScrollPx (12,12)/s × Motion`, `DotColor`, `ScreenLocked` switch.
- **Reuse first.** The project already has two `M_UI_Halftone` materials (`GraffitiUI/` and `Materials/6_Patterns/4_Halftone/`) and `UIMaterialLab/.../MF_UI_Halftone`. Reuse one if it has these controls.

### 5.5 `M_UI_Stripes`

- `StripePx 14 × PxScale`, `AngleDeg 45`, `ColorA` Yellow, `ColorB` Ink, `Duty 0.5`, `ScrollPxPerSec 20 × Motion`.
- Used for hazard strips, the FULL badge ends and dividers. **Never put text on it.**

### 5.6 `M_UI_Silhouette`

- **Input:** `Tex`. Try the existing `GraffitiUI/minimalSplashScreenMech_1` first, after the provenance check in §0, and check it has alpha. Later, add pose renders of the Aura mech.
- **Fill:** alpha above `Threshold 0.5` becomes Ink.
- **Rim:** an 8-tap alpha dilation of `RimPx 6 × PxScale` becomes the Yellow rim.
- **Optional `ShadeDots`:** the texture's luminance drives `M_UI_Dots` coverage, so the shading becomes halftone.
- **Performance:** for release, bake the rim and the halftone into the texture. The runtime version costs 9 samples a pixel over about 0.5 Mpx.

### 5.7 `M_UI_CodeSlots`

- `Slots 6`, `SlotPx (112,136)`, `GapPx 16` (pitch 128), `TiltDeg 3` (alternating ±). Each slot is tilted inside the material; the Image itself stays upright.
- Paper fill, Ink 4 outline, Yellow shadow (6,6). The Ink outline separates the Paper from the Yellow.

### 5.8 Performance budget

**Pixel cost**
- At 1080p, the full-screen translucent layers come to about 6–8 Mpx a frame: burst 2.3 Mpx, dots 2 Mpx, band 1.6 Mpx, mech, hex floor.
- At 4K the cost is ×4.
- This is fine on PC. Profile with `stat slate` and the GPU Visualizer.

**Draw calls**
- Each `Graffiti_*` image gets its own MID from the FX (`GetDynamicMaterial`), so each is its own draw call. About 40 per menu is fine.
- Images at rest early-out in the shader.

**Hidden layers**
- `FlashLayer` and `WipeLayer` are **Collapsed** outside their animations. Use a Visibility track; an Image at opacity 0 still draws.

**Things to avoid**
- **No Retainer Box anywhere in Menu3.** Rotated hit testing inside retainers was wrong in 5.6–5.7 ([UE-361595](https://issues.unrealengine.com/issue/UE-361595), fixed in 5.8), and the disabled-effect CVar is not honoured inside them ([forum](https://forums.unrealengine.com/t/the-slate-applydisabledeffectonwidgets-not-works-for-retainerbox-children/2437491)).
- Never rotate or shear clipping widgets (§4.1).

---

## 6. The existing C++ hover FX (`FAuraMenuButtonFX`)

### 6.1 How it works (checked against `MenuButtonFX.cpp`)

**Registration (in NativeConstruct):**
- Every `UButton` in the widget's own tree is registered **if its parent panel also holds an Image named `Graffiti_*`**.
- Named-slot content counts. Child user widgets (spawned rows) do not.
- The label is the **last TextBlock child** of that parent.
- Its rest colour is read once, at Setup.
- The rest tilt is `sin(Index·2.3+0.7)·RestTilt`, where Index counts every registered button in the widget.

**Every tick, the FX does three things:**
1. Sets the parent container's **whole render transform**: rest tilt, plus hover scale (a spring), a sine wobble, a Perlin jitter of 2.5 px, a +10,−4 px nudge, and **Shear X −8°**.
2. Sets the `Hovered` material parameter.
3. Sets the label colour to `lerp(RestColour, HoverTextColor, Hover)`, and **its shadow colour from opaque black to opaque white**.

**What counts as hovered:** mouse hover **or keyboard/gamepad focus**, and **only while the button is enabled**.

**Hit testing follows the render transform.** A hovered word's click area grows and tilts with it. Expect this and don't fight it.

### 6.2 Hierarchy rules

1. **Backing image:** name it `Graffiti_<Name>` and use `MI_UI_Slab_*`. Set it HitTestInvisible, and give its Overlay slot alignment Fill with **negative padding equal to the MI's Inset** (minus any reserved strip).
2. **Never animate or bind the transform of the FX container** (the button's parent), because the FX overwrites it every frame. Put open/close animation on a **wrapper** around it (`Wrap_<Name>`). Changing the container's **visibility** is allowed.
3. **Never animate or bind the colour or shadow colour of an FX label.** Set its rest colour in the Designer, as a specified colour, not Inherit.
4. **Render Transform Pivot of the container:**
   - Word: **(0.15, 0.5)**, so a scaled word grows to the right and keeps the staircase aligned.
   - Tag and Chip: **(0.5, 0.5)**.
5. A button's label must be a **direct sibling** TextBlock for the FX to invert it. Labels inside the button are not touched.
6. **If C++ collapses a button, only the button disappears.** That applies to:
   - `TutorialButton` when `TutorialMapPath` is empty
   - `CancelBusyButton`
   - `ConfirmNoButton`
   - `OpenLobbyButton`
   - the row buttons Profile, Kick and Ban

   Any sibling label would stay visible, so those buttons use **archetype C** (label inside the button).

   The exception is **Tutorial**, which stays a Word button. In `OnPanelChanged(HomePanel)`, set `Item_Tutorial`'s visibility to match `TutorialButton`; this is Blueprint only.
7. **Spawned rows get no FX.** `WBP_SessionEntry3`, `WBP_SessionPlayerRow3` and `WBP_KeyBindingRow3` have their own trees and are created after Setup. They use the row-focus pattern (§7.8), or C++ #1b.
8. **FX labels have Outline 0.** The FX recolours only the fill: a 4 px Ink outline on Ink text over yellow fills Anton's narrow counters.
9. **FX label shadows:** Word `ShadowOffset (3,3)`, Tag `(0,0)`. The FX forces the shadow opaque, so a non-zero offset always shows.

### 6.3 Settings to type into each widget's Class Defaults (`ButtonFX` struct, no C++)

| Field | WBP_MainMenu3 | WBP_PauseMenu3 | WBP_SettingsMenu3 |
|---|---|---|---|
| HoverScale | **1.14** | 1.12 | 1.05 |
| HoverKick | **5.0** | 4.0 | 1.5 |
| RestTilt | **1.5** | **1.5** | 1.0 |
| Wobble | 0.6 | 0.6 | 0.4 |
| HoverTextColor | Ink (linear 0.0033, 0.0033, 0.0033, 1) | same | same |

**Why RestTilt is 1.5:** with a pivot of 0.15, a tilt of 2.5° moves the right end of a 600 px word by up to 22 px, and neighbouring Home rows tilted in opposite directions close their gap by about 40 px. A tilt of 1.5° keeps them clear.

**Spring check:** I simulated the C++ spring (k 260, c 14, follow speed 12, 60 fps):
- Main menu settings: the scale peaks at **1.185 at frame 6 (100 ms)** and is within 0.005 of 1.14 by frame 23 (383 ms).
- Pause settings: peak 1.151 at 100 ms.
- Settings menu: peak 1.059.

### 6.4 Known limits with the current C++ (each has a C++ change in §12)

- **Label contrast during the transition.** The label colour follows `Hover` (0.20, 0.36, 0.49, 0.59, 0.67, 0.74, 0.79, 0.83 on frames 1–8).
  - On entry, Ink-on-slab contrast passes 3:1 at about frame 6 and 4.5:1 at frame 8 (about 130 ms). Frames 2–5 show a dark-yellow word on yellow.
  - On exit, frames 3–5 look much the same.
  - Fix: C++ #3.
- **Exit timing.** With `HideBelow 0.12`, the slab starts retracting at about frame 6 and is gone at frame 10 (about 170 ms).
- **Wobble ignores the motion setting.** The sine wobble and Perlin jitter are smooth and ignore `MPC_UI.Motion`, which is why Wobble stays at 0.6 or less. Fix: C++ #3 / #10.
- **Shear sign.** The hover shear also tilts the label, which is fine with MSDF fonts. **Check the sign once:** the hover lean should match the slab's `/`.
- **Disabled buttons.** Truly disabled buttons get no greying from the FX; the Word archetype handles this with the veil drawn on top.
- **Slab overhang.** The FX scale enlarges the image, but the slab's pixel features stay in screen pixels. At the peak scale of 1.185 the slab overhangs the button by about 6 px. This is harmless.

---

## 7. Control styling

**Required config.** Add the following to `Config/DefaultEngine.ini` and check it in the console:
```
[ConsoleVariables]
Slate.ApplyDisabledEffectOnWidgets=0
UI.SlateSDFText.RasterizationMode=Msdf
UI.SlateSDFText.ResolutionLevel=2
```
- **Why:** with the default value of 1, every disabled widget is drawn desaturated and at reduced alpha, which would turn the "selected" yellow plate into a muddy dim plate.
- **Scope:** it is **global**, so check `WBP_MainMenu2` and the HUD too. It acts only on the game layer, so the UMG Designer still shows disabled widgets greyed. It is ignored inside Retainer Boxes.

**Every control C++ can disable needs its own disabled look**, because nothing greys out any more:

| Control | When C++ disables it | Disabled look |
|---|---|---|
| Word buttons | Browse and Start Lobby offline, Refresh while searching, Confirm until 6 characters, full session rows | `_Veil` |
| Chips | Copy/Invite outside a session, Open Lobby while creating | `_ChipOff` + DisabledForeground Grey |
| Tags | Selected | `_Selected` |
| Combos | `ResolutionComboBox` in borderless, `LanguageComboBox` with one culture | ButtonStyle.Disabled `_FieldOff` |
| Sliders | `ColorBlindStrengthSlider` when the mode is Off | Disabled bar and thumb brushes |
| Check boxes | `HDRCheckBox` when unsupported | There are **no disabled images**, so the row shows it (§7.8 `bWatchEnabled`) |

**Focus rendering.** Once every focusable control has its own focus look (§7.8), set **Project Settings > User Interface > Render Focus Rule = Never**. Until then, use `NavigationOnly`.

### 7.1 Archetype A, "Word" button (big menu words and action words)
```
Wrap_Create            SizeBox (H 104) – UMG animations go here
└ Item_Create          Overlay – FX owns this transform; pivot (0.15,0.5)
  ├ Graffiti_Create    Image  MI_UI_Slab_Word_A  padding (-34,-22,-34,-22)  HitTestInvisible
  ├ Stamp_Create       WBP_RansomLetter "C" (Home/Pause only), HAlign Left, angle -8°
  ├ Label_Create       TextBlock "REATE SESSION"  D1, Outline 0, ShadowOffset (3,3), padding L 52  HitTestInvisible
  └ CreateSessionButton Button (LAST = on top), Fill, no content
```

| State | Graffiti_ | Label | Button brush |
|---|---|---|---|
| Normal | Nothing | Yellow (the primary word Paper); the black shadow is invisible on Ink | Normal and Hovered brushes: *Draw As None* |
| Hovered / **focused** | Yellow slab wipes in by frame 2, Paper teeth, Ink ring, 12 fps wobble; scale 1.14 | Ink (FX), with a white (3,3) misprint shadow | None |
| Pressed | Same; the FX squashes it 7% | Ink | `MI_UI_Plate_Flash`, a white flash while held. `PressedSlateSound` = SFX_UI_Confirm |
| Disabled (truly) | Nothing | Unchanged, but covered | `MI_UI_Plate_Veil`, drawn **over** the label because the button is the top layer (the label stays readable at about 4.8:1 under the veil) |

Used for:
- Home items
- Pause home items
- StartLobby, PlaySolo
- QuickJoin, Refresh, JoinWithCode, Friends
- ConfirmJoinCode
- ConfirmYes (label = `ConfirmYesText`)
- KeepDisplay

### 7.2 Archetype B, "Tag" (privacy choices and Options tabs: disabled means selected)
```
Item_PrivPublic        Overlay (SizeBox 240×80 = 66 plate + 14 notch strip), pivot (0.5,0.5)
├ Graffiti_PrivPublic  Image MI_UI_Slab_Tag (Inset 16,10,16,24), padding (-16,-10,-16,-10)
├ PrivacyPublicButton  Button: Normal/Hovered None, Pressed MI_UI_Plate_ChipPress (Inset 0,0,0,14), Disabled MI_UI_Plate_Selected
└ Label_PrivPublic     TextBlock "PUBLIC" T1, Ink, ShadowOffset (0,0), centred, padding B 14, HitTestInvisible (on top)
```

| State | Look |
|---|---|
| Unselected | Yellow Dim plate, Ink label (4.25:1) |
| Focused | Bright yellow plate, jagged Paper teeth, wobble, scale 1.14 on Main / 1.05 on Settings (it moves) |
| **Selected** (disabled) | Bright yellow plate, Ink outline, Ink inner line, **notch** in the bottom strip. **Still**: no scale, no teeth, no wobble |

**Rules for tags:**
- Focused and selected must never look the same: selected is still with a notch, focused moves and is jagged.
- Gamepad navigation skips the selected tag, because disabled widgets can't take focus. That is expected behaviour.
- **Test:** press a privacy tag with A. It becomes disabled while it holds focus. Check that the d-pad still moves. If focus is lost, bind that button's **On Clicked** in Blueprint (this works alongside the C++ handler) to focus the nearest enabled tag on the next tick.
- **Z-order:** UMG cannot raise a focused widget above its later siblings. A focused tag's right side is drawn under the next tag, so keep 20 px gaps between the privacy tags. The Options tabs keep their −12 px overlap for the cut-paper look.

**Client lock (Pause, Blueprint only).**
- In `WBP_PauseMenu3`'s Event Tick, only while `SessionPanel` is the active panel: if all three privacy buttons are disabled (the client case), show `Img_PrivacyLock` over the tags.
  - `Img_PrivacyLock` uses `MI_UI_Plate_Lock` and is **Visible**, so it blocks the mouse.
  - It carries "HOST ONLY" in T2 Grey Light.
- Otherwise collapse it.
- Remove this once C++ #4 lands.

### 7.3 Archetype C, "Chip" (small actions; also every button that C++ collapses)
```
Item_ConfirmNo         Overlay, pivot (0.5,0.5)
├ Graffiti_ConfirmNo   Image MI_UI_Slab_Ring, padding (-16,-10,-16,-10)
└ ConfirmNoButton      Button, padding (20,8,26,8)
   └ TextBlock "NO"    T1 size 26, Color and Opacity = Use Foreground
```

| State | Brush | Foreground |
|---|---|---|
| Normal | `MI_UI_Plate_Chip` (Ink, Yellow Dim outline) | Yellow |
| Hovered (mouse) | `_ChipHover` (Yellow Hot) | Ink |
| Focused (gamepad) | Normal brush, plus a yellow jagged ring from the Graffiti_ image and the FX scale | Yellow |
| Pressed | `_ChipPress` | Ink |
| Disabled | `_ChipOff` | Grey |

**Details:**
- Put a glyph chip (an Ink square with a Paper letter, e.g. "B") at the left of the BACK chips.
- Used for: Back buttons, CancelBusy, ConfirmNo, Paste, Copy, Invite, OpenLobby (large: T1 size 30, H 64), ResetTab, AutoDetect, Revert, ResetKeyBindings, and in rows Profile/Kick/Ban.
- **Kick and Ban:** the hovered brush is `MI_UI_Plate_ChipHazard` with Yellow foreground. The hazard band reads as a destructive action while the label stays on solid Ink.
- **Chips in spawned rows:** they get no FX, so they need the per-control focus ring (§7.8).

### 7.4 Combo box (`ComboBoxString`)

**ComboButtonStyle.ButtonStyle:**
- Brushes: Normal `_Field`, Hovered `_FieldHover`, Pressed `MI_UI_Plate_Header`, **Disabled `_FieldOff`**.
- Foregrounds: Normal/Hovered Paper, Pressed Ink, **DisabledForeground Grey**.

**Arrow:** `DownArrowImage` = `MI_UI_Tri` in Yellow, 16 px, rotated 180°.

**Size and font:** 560×52 (filter bar 260×52). ContentPadding (24,8,16,8). Font B2 Paper.

**Dropdown:**
- `MenuBorderBrush` = `MI_UI_Plate_Menu` (slant 0, so rectangular rows fit). `MenuBorderPadding` 6.
- `MaxListHeight` 420. `EnableGamepadNavigationMode` on.

**ItemStyle (TableRowStyle):**
- `EvenRowBackgroundBrush` Ink, `OddRowBackgroundBrush` Coal.
- **`EvenRowBackgroundHoveredBrush` / `OddRowBackgroundHoveredBrush` Yellow Dim** (Paper text on it is 4.6:1).
- `ActiveBrush` Yellow, `ActiveHoveredBrush` Yellow Hot, `InactiveBrush` Yellow Dim.
- `SelectorFocusedBrush` = a Paper 3 px outline, which shows gamepad focus inside the list.
- `TextColor` Paper, `SelectedTextColor` Ink.
- Row padding (14,8).

**Focus on the closed box:** comes from the option row or the focus cell (§7.8).

### 7.5 Slider

- **Size:** 440×40, `BarThickness 6`.
- **Bar:** Normal Coal 2, Hovered Yellow Dim, Disabled Coal.
- **Thumb:** `MI_UI_Plate_Thumb` 20×40; Hovered `_ThumbHover`; Disabled Grey.
- **Colours:** set `SliderBarColor` and `SliderHandleColor` to white, so the colour comes from the brushes.
- **Gamepad:** `RequiresControllerLock` **off**, so the d-pad left/right changes the value and up/down moves between rows.
- **StepSize:** 0.05 for volume, 0.01 for gamma and scale.
- **Value text:** the value TextBlock sits to the right, in the control column, on Coal: B2 Bold, Yellow, 100 px, upright. It never sits under the row fill.

### 7.6 Check box and text boxes

**CheckBox (40×40):**
- Unchecked `MI_UI_Plate_Box`; UncheckedHovered with a Yellow outline.
- Checked `_BoxOn`; CheckedHovered Yellow Hot.
- Pressed Yellow Press. Undetermined Yellow Dim.
- Focus and the disabled look come from the row.

**LobbyNameTextBox:**
- Backgrounds: Normal `_Field`, Hovered `_FieldHover`, **Focused `_FieldFocus`** (Paper 4 outline plus a 6 px Yellow left notch), ReadOnly Coal.
- Padding (24,10,16,10). Font B1 Paper, `FocusedForegroundColor` Paper. Selection background Yellow Dim.
- Hint text: check its contrast in PIE. If it is under 4.5:1, clear `HintText` and use a separate Grey Light TextBlock that a Blueprint `OnTextChanged` binding hides.

**JoinCodeTextBox:**
- Sits exactly over `Img_CodeSlots` (752×136), in the **upright** layer of the code card.
- Backgrounds: Normal, Hovered and ReadOnly *None*; Focused `MI_UI_Plate_FocusRing`.
- Font C1 Ink with **`ForceMonospaced` on and `MonospacedWidth`** set so each character's advance equals the 128 px slot pitch. Start near 1.6 and check against the slots. These are FSlateFontInfo fields.
- `LetterSpacing` 0. Left-pad the box so the first character centres in slot 1.
- Hint "A1B2C3" in Grey on Paper (5.1:1).
- Never rotate the characters; only the slot shapes inside `M_UI_CodeSlots` tilt.

### 7.7 Key selector and scroll bar

**InputKeySelector (200×52):**
- WidgetStyle: Normal `_Field`, Hovered `_FieldHover`, Pressed Yellow Dim (only while the mouse button is held), Disabled `_FieldOff`.
- TextStyle B2 Bold Paper. `KeySelectionText` "PRESS A KEY".
- There is no separate "capturing" brush. The capture state shows as the `KeySelectionText` plus the selector's focus ring (§7.8).

**ScrollBar** (ScrollBox `WidgetBarStyle`):
- Thickness 8. Thumb: Normal Yellow, Hovered Yellow Hot, Dragged Paper. Track Coal 2. No arrow or slot images.
- `ScrollbarPadding` 8 on the left.

**ScrollBox focus:**
- Set `Scroll When Focus Changes = Animated Scroll` and `NavigationScrollPadding 96` on the Browse list, every Options tab and the key-binding list, so gamepad focus stays in view.
- Credits: scroll bar Collapsed.

**Never rotate or shear a ScrollBox, ListView, combo box, text box or key selector** (§4.1).

### 7.8 Rows, focus cells and focus without C++

**How rows track focus:**
- **Focus events:** each row is a user widget that uses the Blueprint events **On Added To Focus Path** and **On Removed From Focus Path**. These fire when any control inside the row gains or loses focus.
- **Mouse events:** **On Mouse Enter / Leave** cover the mouse.
- **What they play:** `Anim_RowFocus` forward or in reverse, plus `SFX_UI_Move`.

**`WBP_OptionRow`** (new, Settings and the Host form)
- **Layout:** a SizeBox, H 64, containing:
  - `Img_RowPlate` (`_Row`, full width, Coal)
  - `Img_RowFill` (`_RowFill`, **label column only**: 0–580 px, slanted right end; ScaleX 0 at rest, pivot (0,0.5))
  - `Img_Chevron` (`MI_UI_Tri`, opacity 0)
  - `Txt_Label` (B1 Paper; a variable set by the instance)
  - `Img_Strike` (Grey 3 px diagonal, Hidden)
  - a **NamedSlot `Control`** at x 600
- **The control column (600+) always stays on Coal.** Yellow values and the yellow slider thumb never sit on the fill.
- **Binding:** put each bound control (e.g. `MasterVolumeSlider` and its `MasterVolumeText` in an HBox) **into the named slot inside `WBP_SettingsMenu3`**. It stays in the outer widget tree, so BindWidget and the FX still find it.
- **`bWatchEnabled`** (instance-editable). Set it on the HDR, Resolution, Language and Colour-blind Strength rows.
  - While it is true, Event Tick reads `Get Content For Slot(Control) → Get Is Enabled`.
  - On a change: `Txt_Label` goes Grey, `Img_Strike` becomes visible, and the focus animation is skipped.

**`WBP_FocusCell`** (new: compact focus for bound controls outside option rows)
- **Layout:** a NamedSlot `Control`, plus `Img_FocusUnder` (a 6 px slanted yellow wedge under the control, ScaleX 0 at rest) and `Img_Chevron` on its left.
- **Behaviour:** the same focus-path and mouse events, with `Anim_CellFocus` (wedge ScaleX 0 → 1 over 3 f, chevron on at frame 1).
- **Used for:** the Browse filter combos (`DistanceComboBox`, `DifficultyFilterComboBox`, `RulesFilterComboBox`) and `ShowFullLobbiesCheckBox`.

**Per-control focus in spawned rows**
- **The gap:** a row with several focusable children cannot tell from the focus-path events which child has focus. This covers:
  - the player row (Profile / Kick / Ban)
  - the key row (three selectors + RESET)
- **The fix:**
  - Give each such child a `Wrap_<Name>` and an `Img_Ring_<Name>` (`MI_UI_Plate_FocusRing`, Hidden, HitTestInvisible, 4 px outside the control).
  - Keep a flag `bOnFocusPath`, set in On Added To Focus Path and cleared in On Removed From Focus Path.
  - While the flag is set, Event Tick sets each ring's visibility from `<Name>.HasKeyboardFocus`.
  - On the rising edge, play `Anim_ChipFocus_<Name>` (Wrap scale 1.0 → 1.08 over 3 f, ease-out, plus `SFX_UI_Move`).
- C++ #1b replaces this.

**`WBP_SessionEntry3`**
- **Layout:** SizeBox H 80, **24 px narrower than the list** (room for the nudge), holding `RowRoot` (Overlay):
  - `Img_RowPlate`, `Img_RowFill` (full width here; every text track in this row is recoloured by the animation)
  - An HBox:
    - `Img_Chevron`
    - `LobbyNameText` (B1 Bold Paper, 400), `HostNameText` (B2 Grey Light, 200), `PlayersText` (T1 Yellow, 100)
    - `DifficultyText` (a T2 tag), `RulesText` (B2, 160)
    - a `PingBadge` (Ink plate) holding `PingText` and `Img_PingBars`
    - `FullBadge`: a solid Yellow plate with short hazard-striped ends, "FULL" in T2 Ink on the solid part
  - **`JoinEntryButton` last, Fill**, with all brushes None except Disabled = `_Veil` and Pressed = `_Flash`. The whole row is clickable.
- **On focus:**
  - The fill goes yellow.
  - Text tracks switch to Ink on frame 1, using constant keys. Exclude `PingText`, whose colour C++ sets on its Ink badge.
  - The row nudges +16 px.
- **In `OnSessionInfoSet`:**
  - Read `Info.Privacy` to show a small stamp.
  - Read `Info.ResultIndex` for the stagger and the alternating 0/24 px offset.
  - Read `Info.PingInMs` for the ping bars.

**`WBP_SessionPlayerRow3`** (a "wanted card" row)
- H 76, Coal plate.
- **Badges:** `HostBadge` = a Yellow hex stamp reading "HOST" (T2 Ink). `LocalPlayerBadge` = a Paper tag reading "YOU", with an Ink outline.
- **Text:** `PlayerNameText` B1 Bold (Noto fallback), `PingText` on an Ink badge.
- **Buttons:** Profile, Kick and Ban as archetype-C chips, each with its own ring (above).

**`WBP_KeyBindingRow3`**
- H 64.
- `ActionNameText` B1 (420) and `CategoryText` T2 Grey Light (130), with the fill on the label column only.
- Three selectors at x 600/812/1024, each with a ring.
- A `ResetRowButton` chip labelled "RESET", with a ring.

---

## 8. Motion kit

### 8.1 Timing tokens (my design values; Atlus has published no timings)

| Token | Value | Notes |
|---|---|---|
| Focus visible | Frame 1; slab complete by frame 2 | `RevealGain 3` on top of the C++ follow |
| Focus pop | Peak 1.185 at 6 f, settled at about 23 f | FX spring (§6.3) |
| Unfocus | Slab retracts from about 6 f, gone by about 10 f | `HideBelow 0.12` |
| Material boil | 12 fps steps | Paused when `MPC_UI.Motion = 0` |
| Press flash | While held | The Pressed brush |
| Wipe | Hold 2 f, then reveal 12 f (≈233 ms). Back: 2 + 9 f | |
| Screen open | 23–25 f (≈0.40 s), items stagger 2 f, 9 f each | First item readable by about 6 f |
| Screen close | Instant | C++ swaps immediately; the wipe hides it |
| Overlay in | Card 8 f, dim 7 f | Overlay out: instant (C++ collapses it) |
| Tab switch | 6 f | |
| Row focus | In 4 f, out 3 f | |
| Chip focus in spawned rows | 3 f | |
| Flash | 3 f | Gated by `Flashes` |
| Shake | 4 f, 2–3 px, constant keys | Gated by ScreenShake |
| Idle | Burst 0.6°/s, breathing 1.6 s, dots 12 px/s, mech bob ±3 px over 1.6 s | |
| Fixed in C++ | Press-any-key **render opacity `0.55 + 0.45·sin(3t)`, so 0.10–1.0** with a 2.1 s period; credits scroll 40 px/s | The plate behind the prompt stays solid |

Text never moves once it has landed. The one exception is the focused item's FX wobble (at most Wobble° and 2.5 px). Plates, slabs and the figure keep moving.

### 8.2 Easing in UMG Sequencer

Use a 60 fps display rate and snap keys to whole frames. End every translation on a whole pixel, so bitmap text lands sharp.

| Curve | How to key it (Auto tangents) |
|---|---|
| Ease-out | 3 keys: start; at 30% of the time, 85% of the travel; end |
| Ease-in | Mirror of ease-out: at 70% of the time, 15% of the travel |
| Overshoot | Add a key at 75% of the time at 106–108% of the travel |
| Stepped | Key interpolation = **Constant** |
| Flash / scroll | Linear |

Arriving things ease out; leaving things ease in.

### 8.3 Animation catalogue

**`WBP_MainMenu3`**

- **`Anim_Wipe_Fwd`:**
  - `WipeLayer` is a root-level Canvas, HitTestInvisible, with a Visibility track (Collapsed at rest).
  - It holds `Wipe_Group`, an HBox of `[Wipe_Body Ink 2400w][Wipe_Stripe Yellow 120w][Wipe_Lead Ink 200w]`, all `MI_UI_Plate_Wipe_*`, 1300 high, slanted 20°.
  - `Wipe_Group.Translation.X` keys: 0: X0, 2: X0, 6: X0−1500, 14: X0−2720.
  - X0 = the position where the slanted trailing edge just clears the right edge of the screen at the bottom.
  - Play `SFX_UI_Wipe` at the same time.
- **`Anim_Wipe_Back`:** the same keys, plus `WipeLayer.RenderScale.X = −1` (pivot at the centre) so it reveals from left to right. It finishes 3 f sooner.
- **`Anim_Open_Home`:**

  | Track | Keys (f: value) |
  |---|---|
  | `Img_GuideSlash` ScaleY (pivot 0.5,0) | 0: 0, 2: 0.8, 5: 1 |
  | `Img_MenuBand` Translation.X | 1: −1400, 6: −60, 8: +14, 10: 0 |
  | `Img_Burst` Scale / Angle | 2: 0.6 / −25°, 8: 1.04, 12: 1.0 / 0° |
  | `Img_Mech` Translation.X / Opacity | 3: +260 / 0, 5: – / 1, 12: −8, 14: 0 |
  | `Wrap_<item i>` (i = 0..5, s = 4+2i) | X: s: −140, s+3: −20, s+6: +8, s+9: 0 · Opacity: s: 0, s+2: 1 · Scale: s: 1.25, s+6: 0.97, s+9: 1.0 · Angle: s: −6°, s+9: 0° |
  | `Wrap_BottomBar` Opacity | 14: 0, 18: 1 |

- **`Anim_Open_Host`, `_Browse`, `_Credits`, `_Code`:**
  - Backdrop to its level pose: from frame 1, under the wipe; band out to −1400, mech out +900, burst to its corner.
  - `Wrap_Header`: X −900 → +10 → 0 over 2–10 f; Angle −10 → −4°. The band holds only the ransom title, which is a display word.
  - `Wrap_Title` (ransom): Scale 1.4 → 1.0 over 6–12 f.
  - Content wrappers: Y +24 → 0 and Opacity 0 → 1, staggered 2 f, 8 f each, from 6 f.
  - Right action card wrapper: X +420 → 0 over 4–14 f. The card image keeps its fixed angle; the wrapper does not rotate.
- **`Anim_Busy_In`, `Anim_Confirm_In`:**
  - `Img_Dim` opacity 0 → 0.6 over 0–7 f.
  - `Wrap_Card` (card image and upright content): Scale 1.25 → 0.98 → 1.0 (0/5/8 f); **Angle −6° → 0°**; Opacity 0 → 1 over 2 f.
  - The card image inside keeps its static angle (−2.5° / −4°), so the text lands upright.
  - Content layer opacity 3 → 6 f.
  - Button wrappers: Y +20 → 0 over 6–11 f.
  - Play `SFX_UI_Slam`.
- **`Anim_Shake`:** on `Wrap_Card`, constant keys: 5: (3,0), 6: (−3,1), 7: (2,−1), 8: (0,0). Play it only if ScreenShake is on.
- **`Anim_Busy_Spin`** (looping): `Img_HexSpin` angle 0, 30, 60 … 330° on constant keys, every 5 f.
- **`Anim_Title_Loop`** (looping): `Img_PressChevron` X 0 / +8 on constant keys every 10 f. Do not animate `PressAnyKeyText`'s opacity, because C++ drives it.
- **`Anim_Title_ToHome`:**
  - `Wrap_Logo` (root level, outside the switcher) moves from the title pose (D0, centre-left) to the Home pose (64 size, top-left at 72,56) over 0–12 f, ease-in then overshoot.
  - It plays alongside `Anim_Flash`: `FlashLayer` Visibility on at frame 0, opacity 0.8 → 0 over 3 f (linear), Collapsed at frame 3. Gated by Flashes.
- **`Anim_Logo_Home` / `Anim_Logo_Hide`:** logo opacity 0 → 1 over 8–12 f in the Home pose, or 1 → 0 over 0–3 f. Sub-screen open animations play `Hide`.
- **`Anim_Home_Idle`** (looping): `Img_Mech` Translation.Y ±3 px over 1.6 s, sinusoidal.

**`WBP_SettingsMenu3`**
- **`Anim_Settings_Open`:** header and tab strip as in the sub-screen opens. **Trigger:** this widget is constructed only once, with its parent. So the parent's `OnPanelChanged` calls a custom event `PlayOpen` on `OptionsMenu`, and that event plays the animation.
- **`Anim_Tab_Switch`** (on `OnTabChanged`): `Wrap_TabContent` X +80 → 0 and Opacity 0 → 1 over 0–6 f, ease-out. Play `SFX_UI_Tab`.
- **`Anim_DisplayConfirm_In`:** the same as `Anim_Confirm_In`. **Trigger:** Event Tick edge-detects `DisplayConfirmPanel.IsVisible`.

**`WBP_PauseMenu3`**
- **`Anim_Pause_Open`:**
  - `Img_PauseVeil` opacity 0 → 0.45 over 0–6 f.
  - `Img_PauseSlab` X −1000 → +16 → 0 over 0/9/11 f.
  - `Img_SlabEdge` ScaleY 0 → 1 over 3–7 f.
  - `Wrap_PauseTitle` pops over 8–14 f.
  - Items as in Home, s = 6 + 2i.
- **`Anim_Open_Session`:**
  - The session card wrapper slides X +300 → 0 and Angle +6° → 0° over 0–11 f. The card image inside stays at −2°.
  - The code plate wrapper slams 1.3 → 1.0 over 4–10 f.
  - Player rows: each row plays its own `Anim_Row_In` with a delay of `0.033 × index`.
- **`Anim_Wipe_Fwd` / `Anim_Wipe_Back` / `Anim_Confirm_In`:** the same as the main menu.

**Rows**
- **`Anim_RowFocus`:**
  - `Img_RowFill` ScaleX 0 → 1 (linear, 0–3 f).
  - Text colours to Ink at frame 1 (constant keys).
  - `Img_Chevron` opacity 1 at frame 1.
  - `RowRoot` X 0 → 16 over 4 f, ease-out.
- **`Anim_Row_In`:** X −60 → 0 and Opacity 0 → 1 over 8 f.
- **`Anim_ChipFocus_<Name>` / `Anim_CellFocus`:** see §7.8.

### 8.4 Blueprint wiring (no C++)

**`WBP_MainMenu3`, Event `OnPanelChanged(NewPanel)`** (C++ has already swapped the panel when this fires):
1. `Name = Get Object Name(NewPanel)`.
2. If Name is `BusyPanel` or `ConfirmPanel`:
   - Set `MenuSwitcher` Visibility to **HitTestInvisible**. Hit-test-invisible widgets are not navigation targets, so focus cannot leave the modal.
   - Play `Anim_Busy_In` or `Anim_Confirm_In` (and `Anim_Shake` if enabled).
   - Set `Prev = Name` and stop.
3. Otherwise, set `MenuSwitcher` Visibility back to its Designer value (`SelfHitTestInvisible`).
4. If `Prev` is an overlay and `Name == LastScreen`:
   - The overlay just closed, so play nothing.
   - Set `Prev = Name` and stop.
5. Look up the depth:

   | Panel | Depth |
   |---|---|
   | TitlePanel | 0 |
   | HomePanel | 1 |
   | HostPanel, BrowsePanel, CreditsPanel, OptionsPanel/OptionsMenu | 2 |
   | CodePanel | 3 |

6. Choose the wipe:
   - If `Prev == TitlePanel`: play `Anim_Title_ToHome`, `Anim_Flash` and `Anim_Wipe_Fwd`.
   - Otherwise, if depth went down: play `Anim_Wipe_Back` and `SFX_UI_Back`.
   - Otherwise: play `Anim_Wipe_Fwd`.
7. Play `Anim_Open_<Name>`, then the logo show or hide animation.
   - For the Options panel, call `OptionsMenu → PlayOpen`.
   - For `HomePanel`, also mirror `TutorialButton`'s visibility onto `Item_Tutorial`.
8. Set `LastScreen = Name` and `Prev = Name`.

**`WBP_PauseMenu3`:**
- **Event Construct:** set `Prev = None`. The menu is removed from the viewport on close, so Construct runs on every open.
- **`OnPanelChanged`:**
  - `PauseHomePanel` with `Prev == None`: play `Anim_Pause_Open`.
  - `ConfirmPanel` (a switcher page here, so nothing behind it is focusable): play `Anim_Confirm_In`.
  - The Options panel: call `OptionsMenu → PlayOpen` and play the wipe.
  - Anything else: play a wipe chosen by depth, as above.
- **Event Tick:** run the privacy lock check (§7.2).
- **Close:** instant (C++ calls `RemoveFromParent`).

**`WBP_SettingsMenu3`:**
- **`OnTabChanged(Index)`:**
  - Play `Anim_Tab_Switch`.
  - Show `Wrap_AutoDetect` only when Index = 0, and `Wrap_ResetKeys` only when Index = 2. Otherwise collapse them; these are wrappers, which is allowed.
- **Event Tick:** watch `DisplayConfirmPanel.IsVisible`.
  - On the rising edge: play `Anim_DisplayConfirm_In`, and set `Wrap_SettingsBody` (the tabs, content and bottom bar) to HitTestInvisible.
  - On the falling edge: restore it.
- **Check-box bindings:** bind **On Check State Changed** of `ScreenShakeCheckBox` and `ScreenFlashesCheckBox` to update `MPC_UI` (§5.0).

**Navigation sound:**
- Only in **`WBP_MainMenu3` and `WBP_PauseMenu3`**, never in `WBP_SettingsMenu3`. The Settings widget is nested inside both, so its handler would double every sound.
- In **On Preview Key Down**, if the key is a d-pad, left-stick or arrow key or Tab, play `SFX_UI_Move` with pitch 0.97–1.03, and **return Unhandled**.

**`StatusText`:**
- Wrap it in `Border_Status` (an Ink brush with a Yellow 3 px outline, padding 16/8).
- Bind the border's Visibility to "StatusText's text is not empty". A property binding on a non-FX widget is fine.

**Optional per-item mech reaction on Home:**
- In Tick, poll `Item_<x>.HasFocusedDescendants` or `IsHovered`.
- On change, switch the mech's reaction: light the matching hex floor segment, move the visor reticle callout, or swap to one of Aura's own mech renders. Use a 2-frame crossfade and an 8 px jolt.
- Do not build a series of full-body hero poses (§0).

**MPC update:** see §5.0 (Construct, PxScale in Tick, the check-box bindings).

### 8.5 Sound map

Use only original or licensed sounds; no Persona audio. The rule follows P5's sound lead: "if it moves, it'll make a sound" ([The Sound Architect](https://www.thesoundarchitect.co.uk/persona-5-audio-review/)).

| Cue | Trigger | Character |
|---|---|---|
| `SFX_UI_Move` | `HoveredSlateSound` (mouse) + Preview Key Down in the outer menus + chip-focus edges in rows | Air whoosh, 60–120 ms, ±3% pitch, −6 dB on repeats |
| `SFX_UI_Confirm` | `PressedSlateSound` | Hard stamp with a low thump |
| `SFX_UI_Back` | Depth decreases | Reversed whoosh plus a click |
| `SFX_UI_Tab` | `OnTabChanged`, tag pressed | Paper snap |
| `SFX_UI_Wipe` | The wipe animations | Cloth or air rip, about 150 ms |
| `SFX_UI_Slam` | Overlay in, Home band landing | Metal plate hit (it's a mech game) |
| `SFX_UI_Tick` | Slider step (Blueprint `On Value Changed`) | Short tick |
| `SFX_UI_Error` | Wrong code, errors | Dull double thud |

---

## 9. Screens

**Anchors.** Coordinates below are at 1920×1080. With the Shortest Side DPI curve, a 16:10 screen (including Steam Deck at 1280×800) is 1728 units wide, and 21:9 is about 2520 wide.

| Item | Anchor | Offset |
|---|---|---|
| Left-column items | Top-left or bottom-left | As given |
| Burst, mech, action card, Browse rail, help card, session card, glyph hints | Top-right or bottom-right | x' = x − 1920 |
| Modal cards | Centre | |
| Bottom bars | Bottom | |

Wrap each root in a `SafeZone`.

**`WBP_MainMenu3` root overlay, back to front:**
1. Backdrop canvas: `Img_Base` Ink, `Img_Burst`, `Img_BurstDots`, `Img_Mech`, `Img_HexFloor`, `Img_MenuBand`, `Img_GuideSlash`, `Img_Hazard`.
2. `Wrap_Logo`.
3. `MenuSwitcher`: one Canvas per panel. Its Designer Visibility is `SelfHitTestInvisible`.
4. `BusyPanel` and `ConfirmPanel`, **outside the switcher**, so the current screen stays visible behind the dim.
5. `Border_Status` holding `StatusText` (bottom centre, x 660–1260, y 1000, B2 Yellow on the Ink plate).
6. `WipeLayer` (Collapsed at rest).
7. `FlashLayer` (a Paper Image, Collapsed at rest, HitTestInvisible).

**Title (`TitlePanel`).** Signature: the logo bursts into the corner.
- **Backdrop:** a burst 1500 px across, centred at (1240, 520) and anchored right; hex floor silhouettes along the bottom right; hazard strip.
- **Logo:** `AURA` with `WBP_RansomWord`, D0, OnInk, in `Wrap_Logo` at (140, 280) rotated −8°. The 6 px Ink outlines separate the yellow letters from the burst.
- **Prompt:**
  - A 560×72 `MI_UI_Plate_Header` plate rotated −4° at (180, 860), holding `PressAnyKeyText` (T1 size 40, Ink, −4°), plus `Img_PressChevron`.
  - C++ pulses the text's opacity from 0.10 to 1.0, while the plate stays solid.

**Home (`HomePanel`).** Signature: a staircase of big words riding the hex-platform band, with the mech in the burst.
- **Band:** `Img_MenuBand` (`MI_UI_Plate_Band`, slant 20) at (−200, −60), size 1300×1240.
  - Its right edge runs from x ≈ 1100 at the top to ≈ 650 at the bottom.
  - Its yellow edge is the guide line. A separate Paper `Img_GuideSlash` (6 px) runs parallel to it, 40 px further right. The Ink band separates the slash from the yellow edge.
- **Burst:** 1500×1500, centred at (1380, 540), anchored right.
- **Mech:** silhouette 860 tall, anchored bottom-right at x 1180–1760. Its hex floor segments light per focused item.
- **Stack:** `VerticalBox` at y 236.
  - Left padding per row: CREATE SESSION 300 (D1 Paper), BROWSE SESSIONS 262 (D2 size 58), TUTORIAL 224 (56), OPTIONS 186 (56), CREDITS 148 (52), QUIT 110 (52).
  - Row SizeBox H 104, gap 8.
  - Each row has a stamp initial (Archivo Black or Alfa Slab, on a Paper plate with an Ink outline).
  - Set the stack's Navigation Up/Down to **Wrap**.
- **Bottom bar:**
  - `VersionText`: M1 **Grey Light** at (72, 1036).
  - `OnlineStatusText`: B3 Paper on an Ink tag with a Yellow notch, at x 1240–1856 (anchored right), y 1000. C++ writes the Error colour when offline, and the text always includes the words.
  - Glyph hints "A SELECT · B BACK" (T2 Grey Light) at the top right (1600, 48).
- **Offline:** `BrowseSessionsButton` is disabled, so its veil shows a struck-through, dimmed word.

**Create Session (`HostPanel`).** Signature: privacy as three stamp tags.
- **Header:** `MI_UI_Plate_Header` at (−60, 44), 1180×150, rotated −4°, with "CREATE SESSION" ransom (OnYellow, base 56).
- **Privacy:**
  - Label "PRIVACY" (T2 Grey Light) at (96, 262).
  - Tags at x 300, 560 and 820, y 236: 240×80 each, **20 px gaps**, angles −3/+2/−2.
  - `PrivacyLabelText` B3 Grey Light at (300, 330), wrapping at 760.
- **Form:** `WBP_OptionRow`s at (96, 400), width 1000: LOBBY NAME (text box 560×60), MAX PLAYERS, DIFFICULTY, RULES (combos 560×52).
- **Action card** (anchored right):
  - `Wrap_ActionCard` at (1180, 420), holding `Img_ActionCard` (`MI_UI_Plate_Card` 640×420, image rotated −5°).
  - **Upright layer on top:**
    - START LOBBY (H1 60, Paper, veil when offline)
    - PLAY SOLO (H2 44, Yellow), 40 px to the left
    - the note "Offline. Open it to others later from the pause menu." (B3 Grey Light)
  - The burst sits behind the card, centred at (1640, 900), scale 0.6.
- **Back:** `HostBackButton` chip at (96, 990).

**Browse Sessions (`BrowsePanel`).** Signature: list rows as offset slanted strips, and a staircase action rail.
- **Header:** "BROWSE SESSIONS".
- **Filter strip:** at (96, 220), 1250×64, on a Coal plate.
  - Distance (260), Difficulty (260) and Rules (240) combos, 52 high, then the `ShowFullLobbiesCheckBox` with "SHOW FULL" (T2).
  - **Each sits in a `WBP_FocusCell`.**
- **Column headers:** T2 Grey Light at y 300: LOBBY 140, HOST 560, PLAYERS 760, DIFFICULTY 880, RULES 1040, PING 1200.
- **List:**
  - An upright `ScrollBox` (96, 330, 1250×640) with Animated focus scrolling, containing `SessionListPanel` (VerticalBox).
  - Rows are 80 high, 1226 wide, with an 8 px gap.
  - `SessionListHintText` is centred, T1 size 44, Yellow Dim.
- **Right rail** (anchored right):
  - `Img_RailCard`: a 470×460 card image rotated −5°, at (1420, 300).
  - On top, upright: QUICK JOIN (H1 52 Paper), then REFRESH, JOIN WITH CODE, FRIENDS (H2 40 Yellow), stepping 24 px per 84 px row.
  - The rail's Word buttons tilt only through the FX.
- **Back:** chip at (96, 990).

**Join with Code (`CodePanel`).** Signature: six tilted code slots.
- **Backdrop:** the level-3 pose, with the burst centred at scale 1.1 and heavy dots.
- **Card:** `Wrap_CodeCard` centred, holding `Img_CodeCard` (1000×520, image rotated −3°) and a yellow tail wedge at its top-left.
- **Upright layer:**
  - Title: "JOIN WITH CODE" ransom on a yellow tag that overhangs the card's top-left, at −6°.
  - Code: `Img_CodeSlots` plus `JoinCodeTextBox`, 752×136, centred 170 px below the card's top.
  - Buttons: PASTE chip, CONFIRM (H1 48, veil until the code has 6 characters), BACK chip, 360 px below the card's top.

**Busy overlay (`BusyPanel`, Visible):**
- `Img_Dim`: Ink at 60%, **Visible** (blocks the mouse). Plus `Img_DimDots` at 18%, screen-locked, HitTestInvisible.
- `Wrap_Card` (centred), holding `Img_BusyCard`: a card image at least 820×240, rotated −4°.
- **Upright layer:**
  - The hex spinner (88 px).
  - `BusyText`: T1 size 48, Yellow, Skew 0, wrapping at 640.
  - The `CancelBusyButton` chip, overhanging the bottom-right.

**Confirm overlay (`ConfirmPanel`, Visible):**
- Dim at 60%, **Visible**.
- `Wrap_Card`, holding `Img_ConfirmCard`: 940×420, image rotated −2.5°, with a Yellow (16,16) shadow and a tail wedge.
- **Upright content layer:**
  - `ConfirmTitleText`: H1 56 Yellow, Skew 0, Outline 3.
  - `ConfirmMessageText`: B2 Paper, wrapping at 760.
  - YES (Word, label `ConfirmYesText`) and NO (chip; C++ collapses it for OK-only messages).

**Credits (`CreditsPanel`).** Signature: a slanted yellow band behind an upright scrolling column.
- **Header:** "CREDITS".
- **Background:** `Img_CreditsBand` (Yellow, slant 20) behind an Ink column card 900 wide at x 510. The card's Ink border at least 4 px wide separates any Paper text from the band.
- **`CreditsScrollBox`:** C++ scrolls it at 40 px/s. Its scroll bar is Collapsed.
- **Content:**
  - Section headers on Yellow tags (T1 size 40, Ink), alternating ±3° and ±60 px. Rotated children inside an axis-aligned ScrollBox are fine.
  - Names B1 Paper; roles B3 Grey Light.
  - A **FONTS** section listing each font with "SIL Open Font License 1.1" and its copyright line, copied exactly from each `OFL.txt`. That includes Noto, if shipped, and "Copyright © 2010 by Dharma Type" for Bebas Neue.
- **Back:** chip.

**Options (`WBP_SettingsMenu3`; used as `OptionsPanel` in both menus).** Signature: tabs as overlapping cut-paper tags.
- **Background:** its own full-bleed Ink background at 94%, so it also works over the live game in Pause.
- **Header:** "OPTIONS".
- **Tab strip:**
  - At (96, 214): five archetype-B tags, 236×80 each (ACCESSIBILITY 260), with −12 px overlap and angles −3/+2/−2/+3/−1.
  - LB/RB glyph chips at both ends; these are images, since C++ already handles `CycleTab`.
- **`Wrap_SettingsBody`:** holds the content and the bottom bar.
- **Content:**
  - In `Wrap_TabContent`, from (96, 310) to (1440, 960).
  - Each tab is an upright `ScrollBox` of option rows (Animated focus scrolling): label column 0–580, control column 600–1180, value text at 1200.
  - No FX buttons inside the ScrollBoxes, because their teeth would be clipped.
- **Help card** (anchored right): `SettingsHintText`, B3 Grey Light on a Coal card with a Yellow Dim outline, at (1490, 310), 350×420.
- **Bottom bar:**
  - At y 990: RESET TAB, `Wrap_AutoDetect` (AUTO DETECT, Video tab only), `Wrap_ResetKeys` (RESET KEY BINDINGS, Controls tab only) and BACK.
  - All are chips.
- **Controls tab:** a header row reading ACTION / KEYBOARD / ALT / GAMEPAD (T2 Grey Light) above `KeyBindingList`.
- **`DisplayConfirmPanel`:**
  - Confirm-overlay style: a Visible dim, a card image, and an upright layer.
  - `DisplayConfirmText` (the countdown) is B2 Paper.
  - KEEP is a Word button; REVERT is a chip.
- **Navigation:**
  - **Stop** at the ends of each tab's list.
  - Leave Up from the first row on **Escape** (the default). An explicit link to the tab strip would fail whenever its target is the current, disabled tab.

**Pause (`WBP_PauseMenu3`).** Signature: a black slab over the live game.
- **Root:**
  - `Img_PauseVeil`: Ink at 45%, full screen.
  - `Img_PauseSlab`: `MI_UI_Plate_Band` with slant 18 and opacity 0.94, at (−300, −80), size 1260×1240.
  - The right side shows the live game. Nothing pauses in co-op.
  - "PAUSE" ransom at (72, 60), −6°.
- **`PauseHomePanel`:**
  - A staircase at y 250. Left padding: RESUME 260 (D1 Paper), CURRENT SESSION 226, OPTIONS 192, LEAVE SESSION 158, QUIT GAME 124 (D2 48–52, Yellow).
  - Pitch 100; navigation Wrap.
- **`SessionPanel`, on the slab:**
  - "JOIN CODE" (T2 Yellow).
  - `Wrap_CodePlate` holding `Img_CodePlate`: Paper fill, Ink 5 outline, Yellow (10,10) shadow, 460×110, image rotated −4°.
  - `SessionCodeText`: C2 Ink, upright, centred on the plate.
  - COPY and INVITE chips; OPEN LOBBY as a large chip.
  - `SessionInfoText`: B2 Paper, wrapping at 480.
  - `SessionBackButton` chip at (96, 990).
- **`SessionPanel`, on the right (anchored right):**
  - `Wrap_SessionCard` holding `Img_SessionCard`: (900, 150), 940×800, image rotated −2°.
  - **Upright layer:**
    - a "CURRENT SESSION" ransom tag
    - the privacy tags with `Img_PrivacyLock` and `PrivacyLabelText`
    - "PLAYERS" (T1 Yellow)
    - `PlayerListPanel`, holding the wanted-card rows
    - `SessionStatusText` (B3 Yellow on Ink)
- **`ConfirmPanel`:** a switcher page in Pause, because the C++ requires it. Give it its own Visible `Img_Dim`, card image and upright layer.
- **Pause Options:** the shared `WBP_SettingsMenu3`.

---

## 10. Readability and accessibility rules

1. **Text on yellow is always Ink.** Never put Paper or Error text on yellow.
2. **Paper never touches Yellow directly.** Keep an Ink line of at least 4 px between them, in materials as well. The one exception is the 3 px white misprint shadow of a focused Word label (§3.2).
3. **Anything C++ writes** uses Barlow or Rubik Mono, upright, with no skew or shear, at UMG size 20 or more (version string 18).
   - That covers names, codes, numbers, status, hints, values and messages.
   - The only exceptions are the three short fixed strings in §3.2, which stay upright.
4. **Display faces and ransom lettering are only for fixed words.**
   - Each ransom word is generated once in PreConstruct and never reshuffles at runtime.
   - `bPlain` offers a non-stylised version ([XAG 101](https://devdocs.xbox.com/gaming/accessibility/xbox-accessibility-guidelines/101)).
5. **Every text block sits on a solid fill.** Never place text directly on dots, stripes or burst edges.
6. **Rotate plates, not text** (§4.1).
   - Display words may tilt up to ±6°, including the FX tilt.
   - Ransom letters may tilt ±8°, plus their plate's rotation.
   - Nothing interactive or C++-written sits in a rotated card.
7. **Contrast:** at least 4.5:1 for body text and at least 3:1 for display words of size 30 and up. Ping and status colours always sit on Ink badges.
8. **Text size:** [XAG 101](https://devdocs.xbox.com/gaming/accessibility/xbox-accessibility-guidelines/101) asks for at least 26 px body height (descender to ascender) at 1080p on TV and 18 px on PC.
   - B3 (size 20) meets the TV figure at UI Scale 1.0.
   - At UI Scale 0.75 or on Steam Deck (scale 0.74), check B3 and M1 in PIE.
   - Never add information text below B3.
9. **At rest, at most two things move:** the focused item's wobble and the slow background drift.
10. **Gamepad focus check:** every focusable control is in one of these:
    - an FX container (Word, Tag, Chip)
    - an option row or focus cell
    - a per-control ring in a spawned row

    Focus is always shown at least two ways out of shape (teeth, slab, ring, wedge), scale and motion or a chevron; never by colour alone. Only then switch Render Focus Rule to Never.
11. **Selected and focused never look alike.** Selected is still, with a notch; focused moves and is jagged. Truly disabled controls are greyed or veiled with a strike and have no notch.
12. **Motion and flash settings:**
    - `MPC_UI.Motion = 0` stops the material wobble, drift, breathing and shakes. `Flashes = 0` stops the white flashes.
    - Both follow the existing ScreenShake and ScreenFlashes settings live.
    - The C++ FX wobble still runs until C++ #10.
13. **Modals hold focus.** While Busy, Confirm or Display Confirm is open, nothing behind it is clickable or reachable with the d-pad.
14. **Colour vision:** Aura's own colour-blind correction recolours the UI; test with it on (§2).
15. **Calm screens:** Options, Browse and key bindings are the "calm" screens. They use plain type, 0° content and no rotated rows, as P5 keeps its shops simple ([Olszewska](https://medium.com/@kinga.olszewska/interface-so-good-that-people-make-cosplay-of-it-persona-5-ui-controversial-yet-brilliant-ac1ec4b95229)).

---

## 11. Build order (no C++)

1. **Config:**
   - Add the `[ConsoleVariables]` block from §7.
   - Turn on distance-field fonts (UMG Fonts).
   - Set Render Focus Rule = NavigationOnly for now.
   - Check `WBP_MainMenu2` and the HUD with the disabled effect off.
2. **Fonts:**
   - Download the 7 families (plus the Noto fallbacks) from `github.com/google/fonts/tree/main/ofl/<family>`, unmodified.
   - Create the Font Face and Font assets (§3.1) and the `F_Barlow` fallback typeface.
   - Copy each `OFL.txt` to `Content/Licenses/Fonts/<Family>-OFL.txt`.
   - Add `+DirectoriesToAlwaysStageAsNonUFS=(Path="Licenses")` under `[/Script/UnrealEd.ProjectPackagingSettings]` in `DefaultGame.ini`, so the files ship in packaged builds.
3. **Materials and MIs:**
   - Build `MPC_UI` (Motion, Flashes, PxScale), `M_UI_Slab`, `M_UI_Plate`, `M_UI_Burst`, `M_UI_Dots`, `M_UI_Stripes`, `M_UI_Silhouette`, `M_UI_CodeSlots`, and the MIs in §5.
   - Test each on a scratch widget at three widths, in both PIE and the Designer, and **at UI Scale 0.75 and 1.5**: the slab must stay on the button bounds.
4. **Helper widgets:** `WBP_RansomLetter`, `WBP_RansomWord`, `WBP_OptionRow`, `WBP_FocusCell`, `WBP_GlyphChip`.
5. **One button of each archetype**, styled per §7. After that, copy and paste the containers; the FX finds buttons by naming only.
6. **Row widgets:**
   - Build `WBP_SessionEntry3`, `WBP_SessionPlayerRow3` and `WBP_KeyBindingRow3` (their parents are the C++ classes), with the per-control rings.
   - Assign them in `SessionEntryClass`, `PlayerRowClass` and `KeyBindingRowClass`.
7. **Menus:**
   - Build **`WBP_SettingsMenu3`**, then **`WBP_MainMenu3`**, then **`WBP_PauseMenu3`**. Use the exact C++ widget names.
   - Set anchors (§9) and the `ButtonFX` values (§6.3).
8. **Animations** (§8.3), **Blueprint wiring** (§8.4), then sounds.
9. **Test pass:**
   - **Input:** gamepad only through every screen, including inside combo dropdowns, the key-binding rows (rings) and the player rows. Press a privacy tag with A and keep navigating. Make sure the d-pad cannot reach anything behind Busy, Confirm or Display Confirm.
   - **States:** offline mode (veils). Pause as a client (the HOST ONLY lock appears). HDR unsupported and borderless (the disabled rows read as disabled).
   - **Settings:** motion and flash settings off, toggled live inside Options. Each colour-blind mode at strength 10.
   - **Scale:** UI Scale 0.75 and 1.5. Resolutions 1280×800, 1920×1080, 2560×1080 and 3840×2160 (anchors, SafeZone, slab alignment).
   - **Names:** a lobby or player name in Cyrillic and in CJK (no tofu boxes).

---

## 12. Optional small C++ changes (in priority order)

| # | Change | Why | Size |
|---|---|---|---|
| 1 | In `FAuraMenuButtonFX`, also handle **non-button controls** (CheckBox, Slider, ComboBoxString, EditableTextBox, InputKeySelector) that have a `Graffiti_*` sibling. Drive the material only (no transform), using `Container->HasFocusedDescendants()` | Focus visuals on sliders and combo boxes without the row and cell wrappers | ~25 lines |
| 1b | Give `USessionEntry3`, `USessionPlayerRow3` and `UKeyBindingRow3` their own `FAuraMenuButtonFX` (Setup in NativeConstruct, Tick in NativeTick) | Chips and selectors in spawned rows get the same focus look; this replaces the Tick-polled rings | ~10 lines each |
| 2 | When C++ hides a button, **collapse its FX container** (`Button->GetParent()` when it holds a `Graffiti_*`) instead of only the button. One helper, `AuraMenu::SetButtonShown`, used at the 5 call sites | Lets Cancel, No, OpenLobby and the row buttons use the Word archetype with sibling labels, and removes the Tutorial mirror | ~15 lines |
| 3 | Add `HoverShadowColor`, `HoverShear` and `bSnapLabelColour` (step the colour when Hover > 0.35) to `FAuraMenuButtonFXSettings`. Add `Stiffness 900`, `Damping 30`, `HoverFollowSpeed 28`, Kick 6–8, and two Dt substeps at 1/60. Swap the sine wobble and Perlin jitter for **stepped 12 fps jitter** | A harder P5 snap: peak at about 80 ms, settled by about 120 ms. No muddy label frames on entry or exit | ~30 lines |
| 4 | In the Pause menu, **collapse the privacy tags** when `!bCanChoosePrivacy`, instead of disabling all three | Clients otherwise see three "selected" tags; this replaces the Blueprint lock | ~5 lines |
| 5 | Add `FocusSound` and `ConfirmSound` to the FX settings and play them on the rising edge of hover or press | Navigation sound without the Preview Key Down workaround | ~10 lines |
| 6 | Make the offline status colour and ping colours `EditAnywhere` `FLinearColor`s. Also reset the `OnlineStatusText` colour when the service comes back; today it stays red | Palette control; fixes a stale colour | ~10 lines |
| 7 | Bind face buttons directly: Y = Refresh and X = Join Code in Browse; X = Profile and Y = Kick on player rows | P5 maps actions straight to face buttons ([ANN](https://www.animenewsnetwork.com/feature/2017-03-06/first-look-persona-5/.113058)) | ~20 lines |
| 8 | Expose a `PressAnyKeyBlink` mode (stepped instead of a sine) and a minimum opacity (0.4 instead of 0.10) | Matches the stepped motion language; the prompt never vanishes | ~5 lines |
| 9 | Add a `bDeferPanelUntilWipe` flag. **Not recommended:** screens should never wait on an animation, which matches P5's "only limited by your dexterity" feel ([ANN](https://www.animenewsnetwork.com/feature/2017-03-06/first-look-persona-5/.113058)) | Listed only so nobody adds it by accident | – |
| 10 | Add `bReduceUIMotion` and `bPlainHeadings` settings in `UMyGameUserSettings`, with check boxes in Accessibility. Drive `MPC_UI.Motion`, the FX wobble and jitter, and `WBP_RansomWord.bPlain` from them | A proper accessibility switch, which Atlus's lead UI designer also called something players need ([PC Gamer](https://pcgamer.com/games/rpg/persona-and-metaphor-refantazios-ui-designer-is-open-to-accessibility-options-for-players-who-find-the-stylish-menus-overstimulating-that-is-something-we-understand-well-need-to-work-on-and-provide-in-the-future)); XAG 101's stylised-font alternative | ~35 lines |

---

## 13. Reference notes (claims and their sources)

- **One key colour plus black and white, flat fills, colour chosen first:** [Famitsu CEDEC 2017](https://www.famitsu.com/news/201711/13145540.html), [Siliconera](https://www.siliconera.com/atlus-reveals-design-secrets-behind-persona-5s-distinctive-ui/), [Wikipedia](https://en.wikipedia.org/wiki/Persona_5), [SegaBits](https://segabits.com/?p=54918).
- **Brightness follows priority; a white guide line on open; deeper levels change layout and angle; a 3D model spins into a pose; tuned "one dot, one frame":** [Famitsu CEDEC](https://www.famitsu.com/news/201711/13145540.html), [Siliconera](https://www.siliconera.com/?p=668266), [PlayStation LifeStyle](https://www.playstationlifestyle.net/?p=615973), [Game Watch](https://game.watch.impress.co.jp/docs/news/1083476.html).
- **Slanted cut-paper shapes, pointing wedges, manga-panel boxes, thick borders:** [Jiaxin Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/), [inside-games](https://www.inside-games.jp/arti/T9kRGPl_2/), [Redbrick](https://www.redbrick.me/behind-the-mask-producing-a-games-visual-identity/), [Kotaku](https://kotaku.com/metaphor-refantazio-persona-5-menu-ui-hashino-1851667088).
- **Selected item bigger with a contrasting splash; transforming shapes under the chosen button; the hero switches poses per menu item (which is why ours is different):** [Mechanics of Magic](https://mechanicsofmagic.com/2022/04/23/visual-design-of-games-persona-5/), [Liu](https://medium.com/game-design-fundamentals/visual-design-of-games-practice-analysis-of-persona-5-royal-61a5c18ba9c1), [Olszewska](https://medium.com/@kinga.olszewska/interface-so-good-that-people-make-cosplay-of-it-persona-5-ui-controversial-yet-brilliant-ac1ec4b95229), [p5ui](https://p5ui.tumblr.com/).
- **Ransom-note lettering; plain sans for changing information; readability problems:** [inside-games](https://www.inside-games.jp/arti/T9kRGPl_2/), [Robin Rendle](https://robinrendle.com/adventures/video-games-and-wiggletech/), [Inverse](https://inverse.com/gaming/persona-5-tactica-user-interface), [PC Gamer, Hashino](https://www.pcgamer.com/games/rpg/persona-series-director-says-atluss-flashy-menus-are-actually-really-annoying-to-design), [Divagatra 2024](https://ojs.unikom.ac.id/index.php/divagatra/article/download/12339/4353), [Sakurai](https://sourcegaming.info/2016/11/24/the-aims-of-ui-sakurais-famitsu-column-vol-515/), [TV Tropes: Cut-and-Paste Note](https://www.tvtropes.org/pmwiki/pmwiki.php/Main/CutAndPasteNote).
- **Backgrounds (flat colour with silhouettes, halftone, star stripes, slow-moving stars):** [New Frame Plus transcript](https://amara.org/subtitles/wIZbgZ3Jyy5D/en/1/download/The%20Overwhelming%20Style%20of%20Persona%205s%20All-Out%20Attacks.en.srt), [TCRF](https://tcrf.net/Proto:Persona_5/December_4th,_2015/Graphics), [Wen](https://jiaxinwen.wordpress.com/2017/04/27/the-ui-design-of-persona-5/), [p5ui](https://p5ui.tumblr.com/).
- **Motion ("pop punk", speed and burst; menus pulse and react; transitions instead of cuts; fast cursor):** [Famitsu 2023 (Kumagai)](https://www.famitsu.com/news/202311/29325647.html), [Kotaku](https://kotaku.com/persona-5-menus-make-everything-better-1794216056), [Kotaku Strikers](https://kotaku.com/persona-5-strikers-menus-are-as-vibrantly-alive-as-its-1846340592), [ANN](https://www.animenewsnetwork.com/feature/2017-03-06/first-look-persona-5/.113058), [Endless Mode](https://www.endlessmode.com/video-games/persona-5/persona-5-is-the-most-stylish-jrpg-ever), [TheGamer](https://www.thegamer.com/best-jrpg-start-screens/), [Val Head (motion ranges)](https://valhead.com/?p=2978).
- **Sound ("if it moves, it'll make a sound"):** [The Sound Architect](https://www.thesoundarchitect.co.uk/persona-5-audio-review/).
- **Fonts and licences:**
  - google/fonts `METADATA.pb` and `OFL.txt` for [Anton](https://raw.githubusercontent.com/google/fonts/main/ofl/anton/METADATA.pb), [Archivo Black](https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/METADATA.pb), [Alfa Slab One](https://raw.githubusercontent.com/google/fonts/main/ofl/alfaslabone/METADATA.pb) (RFN "Alfa Slab"), [Abril Fatface](https://raw.githubusercontent.com/google/fonts/main/ofl/abrilfatface/METADATA.pb) (RFN "Abril", "Abril Fatface"), [Bebas Neue](https://raw.githubusercontent.com/google/fonts/main/ofl/bebasneue/METADATA.pb), [Barlow Condensed](https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/METADATA.pb), [Rubik Mono One](https://raw.githubusercontent.com/google/fonts/main/ofl/rubikmonoone/METADATA.pb), and the Noto Sans, SC, JP and KR families (all `license: "OFL"`).
  - [OFL FAQ](https://openfontlicense.org/ofl-faq/): bundling in games is allowed; a format change or subset is a modification; the minimum to ship is the copyright, notice and licence text.
- **UE specifics:**
  - SDF text (UE 5.5+, setting names, CVars, thin-feature caveat): [Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-signed-distance-field-text-rendering-in-unreal-engine).
  - FSlateFontInfo (`SkewAmount`, `ForceMonospaced`, `MonospacedWidth`, `LetterSpacing`): [Epic Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SlateFontInfo).
  - FFontOutlineSettings (`bMiteredCorners`, outline colour lives in the font info): [Epic](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/SlateCore/FFontOutlineSettings).
  - Rotated hit testing in Retainer Boxes ([UE-361595](https://issues.unrealengine.com/issue/UE-361595)) and the disabled-effect CVar in retainers ([forum](https://forums.unrealengine.com/t/the-slate-applydisabledeffectonwidgets-not-works-for-retainerbox-children/2437491)).
  - MPC in UMG materials ([forum](https://forums.unrealengine.com/t/umg-material-not-reflecting-parameter-collection-change/382732)).
  - FWidgetTransform shear and angle, Slate clipping, style classes, focus rule, Rich Text and Retainer cost: see the Epic links in the sources list.
- **Accessibility:** [XAG 101 text display](https://devdocs.xbox.com/gaming/accessibility/xbox-accessibility-guidelines/101) (26 px TV / 18 px PC at 1080p; a non-stylised alternative to stylised fonts); [PC Gamer on Atlus and overstimulating menus](https://pcgamer.com/games/rpg/persona-and-metaphor-refantazios-ui-designer-is-open-to-accessibility-options-for-players-who-find-the-stylish-menus-overstimulating-that-is-something-we-understand-well-need-to-work-on-and-provide-in-the-future).
- **Aura C++ facts used here** (commit `14ed4e1`):
  - `MenuButtonFX.cpp`: the label is the last sibling TextBlock; the shadow colour is overwritten every tick; spring k 260 / c 14; follow speed 12.
  - `MainMenu3.cpp`: the press-any-key opacity is `0.55 + 0.45·sin(3t)`; overlays outside the switcher are toggled with `SetVisibility`.
  - `SettingsMenu3.cpp` / `MyGameUserSettings.cpp`: the UI Scale slider writes `ApplicationScale` (0.75–1.5); colour-blind modes call `SetColorVisionDeficiencyType` with correction on; Resolution, Language, HDR and Colour-blind Strength can be disabled.
  - `SessionEntry3.cpp`: ping colours and thresholds 60/120 ms.
