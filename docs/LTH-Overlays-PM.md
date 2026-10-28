# LTH Overlays — produkto ir darbų planas (handoff)

Atnaujinta: 2026-10-28 · Dabartinė versija: **v0.6.0** · Toliau: Windows patikra (pit komandos, OBS, chat, telemetrija gyvai), E2 atnaujinimų pranešimas, E3 balsas

---

## 0. SVARBIAUSIA: perskaityk prieš bet ką darydamas (instrukcija Claude'ui)

Šis failas yra darbų planas Claude'ui, dirbančiam **draugo kompiuteryje**, kur yra **LIVE versija**.

1. **Tikroji (live) versija yra ŠIAME kompiuteryje.** Joje jau sutvarkyta daug klaidų, kurių nėra pradiniame v0.1.0 archyve.
   - NEKURK projekto iš naujo ir NEPERRAŠYK jo pagal šį dokumentą.
   - NEIŠARCHYVUOK ant jo `LTH-Overlays-0.1.0-win64.zip` ar `lth-overlays-source.zip`. Tai sena bazė, skirta tik pasižiūrėti.
   - Jei vietinis kodas skiriasi nuo šio aprašymo, **teisus vietinis kodas**. Šis failas aprašo, KĄ pridėti, o ne kaip turi atrodyti esamas kodas.
2. **Prieš pirmą pakeitimą:**
   1. Surask projekto aplanką (ieškok `run.py`, `lth_timing/`, `lth_overlays/`). Jei randi kelias kopijas, paklausk vartotojo, kuri yra live.
   2. Padaryk atsarginę kopiją: `git init` (jei dar nėra) ir commit „live snapshot before v0.2“, arba nukopijuok aplanką su data.
   3. Paleisk testus (`python -m pytest -q`) ir užsirašyk, kas praeina. Jei kas nors jau neveikia, užfiksuok tai, bet netaisyk to, kas nesusiję su užduotimi.
   4. Perskaityk `lth_timing/engine.py`, `lth_overlays/app.py`, `lth_overlays/window.py` ir `lth_overlays/config.py`, nes visos naujos funkcijos remiasi jais.
   5. Trumpai parašyk vartotojui, kuo vietinė versija skiriasi nuo 1 skyriaus aprašymo. Tai ir yra „ką jau sutvarkė“. Šių pataisymų niekada neatšauk.
3. **Darbo tvarka:** viena funkcija vienu metu → testai → demo patikra (`python run.py --demo`) → commit → trumpa žinutė vartotojui. Didelius dalykus (Control Center, naujus valdiklius) pirma aptark su vartotoju, o tik paskui rašyk kodą.
4. **Nepažeidžiamos taisyklės:**
   - Visa programos sąsaja **angliškai** (jokio lietuviško teksto UI). Numatytas overlay stilius live versijoje: **Montserrat + „Modern dark“** (Saira Condensed liko pasirinkimuose). Control Center šriftas - Inter.
   - Overlay langai visada virš iRacing, pelė eina kiaurai, langai niekada nepaima fokuso (žr. `win32.py`).
   - Našumo biudžetas (5 skyrius): kiekviena nauja funkcija turi tilpti.
   - `config.json` suderinamumas: nauji nustatymai pridedami per numatytąsias reikšmes (`DEFAULT_WIDGETS`, `_merge`), seni vartotojų failai turi veikti toliau.
   - Antivirusams draugiškai: jokio PyInstaller one-file, UPX, klaviatūros hook'ų, admin teisių ar kodo atsisiuntimo.

---

## 0.0 v0.6.0 — kas padaryta

Tyrimas: `docs/research-v0.6.md` (RaceLab, irDashies, iOverlay, Kapps, bendruomenės nuomonė).

- **Standings / Relative** (`widgets/table.py`, `relative.py`, `standings.py`):
  - vėliavos (FlairID → ISO, `lth_timing/countries.py`; sprite `data/flags`, flag-icons MIT);
  - licencijos spalva iš `LicColor`, mašinos modelis, statuso ženkliukai (`CarIdxSessionFlags`);
  - header / footer juostos (`INFO_ITEMS`, laukas "items" su tvarka);
  - vėliavos kontūras, tankis, eilučių stilius, stulpelių antraštės (`column_header`);
  - iRating prognozė (`lth_timing/laps.py` `project_irating`, stulpelis `irchange`, header `ir_proj`);
  - tušti stulpeliai susitraukia (`COLLAPSIBLE`).
- **Kontūras** visiems valdikliams: `config["outline"]` + valdiklio `outline_mode`; `window._paint_outline()` (kai `_drew_bg`).
- **Inputs**: greitis, pavara, vairas, %.
- **Pit commands** (`race.PitCommandsWidget`, `INTERACTIVE`): `win32.pit_command` (IRSDK_BROADCASTMSG).
- **Track map**: greitas kelias 30/60 fps + statinis sluoksnis talpykloje. **Flat track map** (`FlatMapWidget`).
- **Šriftai**: +14 (33 iš viso, grupė „Modern“); VF šriftams nustatoma `wght` ašis (`theme.Fonts._font`). Visi turi LT raides ir `tnum`.
- **Lenktynių funkcijos**:
  - Lap timer + PB (`lth_overlays/pb.py`, `pb.json`);
  - Sectors (`laps.SectorTracker`, `snap.my_sectors`);
  - Overtake alert ir Rejoin (`widgets/alerts.py`);
  - incidentų limitas iš `WeekendOptions.IncidentLimit` (`snap.incident_limit`).
- **OBS** (`lth_overlays/obs.py`):
  - `ThreadingHTTPServer` tik 127.0.0.1:8399; kadrai piešiami UI gijoje atskiromis kopijomis (`obs_mode`), tik kol OBS prašo;
  - URL: `/w/<valdiklis>`, `/layout?screen=N`, `?demo=1`; Control Center → Stream.
- **Chat** (`lth_overlays/chat.py`, `widgets/chat.py`):
  - Twitch anoniminis IRC;
  - YouTube per vidinį live_chat API (be rakto, gali lūžti);
  - gijos sustoja po 30 s be skaitymo; moderacijos ištrynimai gerbiami.
- **Drivers** puslapis (`control/drivers_page.py`): žymos (Friend / Teammate / Rival / Careful / Fast) su spalva → `config["friends"]`.
- **Hotkey'ai** kiekvienam valdikliui (`widget:<name>`) ir „Next profile“; `app._hotkey_actions()`.
- **Matomumas pagal sesiją**: laukas `sessions` (checks). Config v7 migruoja `race_only`.
- **Garage cover** (`widgets/cover.py`).
- **Telemetrija** (`lth_timing/telemetry.py`, `control/telemetry_page.py`):
  - `LapRecorder` engine gijoje: tik savo mašina, 30/60 Hz;
  - ratas perskaičiuojamas į atstumo tinklelį (~2 m);
  - `.lthlap` = zip (meta.json + npz be pickle);
  - geriausias ratas automatiškai `%APPDATA%\LTH Overlays\laps`;
  - sesijos ataskaita, A/B palyginimas su delta, importas / eksportas, CSV.
- Testai: 66 (14 naujų `tests/test_v06.py`).
- Našumas:
  - 3 numatyti valdikliai ~6–7 % vieno branduolio (sandbox, programinis piešimas);
  - Track map 60 fps prideda ~9 %, todėl numatyta 30 fps.

**Patikrinti Windows'e:**
- pit komandų mygtukai trasoje;
- OBS Browser Source permatomumas;
- Twitch / YouTube chat su tikru kanalu;
- `.lthlap` importas iš draugo;
- per-widget hotkey'ai;
- vėliavų / licencijų spalvos su tikrais duomenimis.

## 0.1 v0.4.0 — kas padaryta (ant live 0.3.1)

Bazė: draugo live `LTH-Overlays-0_3_1-win64.zip` (visi jo pataisymai palikti). Viskas angliškai UI.

- **Control Center** (`lth_overlays/control/`): modernus SaaS stiliaus langas (Inter šriftas, tamsi tema, LTH auksinė spalva). Puslapiai: Overview, Widgets (katalogas su gyvomis miniatiūromis, paieška, kategorijos), valdiklio puslapis (schema → forma, X/Y/W/H, gyva peržiūra, Reset), **Layout** (visas ekranas sumažintas: tempti, keisti dydį kampu / kraštais, rodyklės, prilipimas, inspektorius), Profiles (naujas / pervadinti / dublikuoti / eksportas / importas / trinti, auto perjungimas, tema lygai / serijai), Appearance (temos, šriftai su pavyzdžiu, spalvų perrašymai, klasių spalvos), Hotkeys (keičiami, rodo ar užregistruota), General, Performance (grafikai), Diagnostics, About. Uždarius lieka tray'uje; paleidus ranka atsidaro; antras paleidimas atidaro jau veikiančios programos langą.
- **Registras** `lth_overlays/registry.py`: vienas tiesos šaltinis (26 valdikliai, laukai, numatytos reikšmės, atnaujinimo dažnis). Naujas valdiklis = klasė + vienas `WidgetSpec`.
- **Dydis**: aukštis keičiamas tempiant viršų / apačią (lentelės rodo tiek eilučių, kiek telpa), kampai - proporcingas mastelis, kraštai - plotis, dvigubas spustelėjimas - automatinis aukštis.
- **Standings**: tavo klasė pagal filtrą (visi / top N + aplink / aplink), kitos klasės - top 3 (`other_classes_n`, 0 = paslėpti). Mažinant aukštį pirma trumpinamos kitos klasės, tavo eilutė lieka visada.
- **Nauji valdikliai (21)**: Battle analysis, Lap history, Delta bar, Session (SOF), Flags, Radar, Pit helper, Pit window (išmatuotas pit loss + kur išvažiuosi), Incidents, Stint, Formation, Radio, Fuel, Dash, Inputs (60 Hz tik kai įjungtas), G-force, Tyres, Car setting changes, Engine warnings, Track map (įrašomas iš pirmo švaraus rato, saugomas `%APPDATA%\LTH Overlays\maps`), Connection. Visi numatytai išjungti.
- **Autostart**: vietoj `.vbs` Startup aplanke dabar standartinis `HKCU\...\Run` įrašas (`--autostart`); senas `.vbs` automatiškai ištrinamas ir perkeliamas.
- **Karštieji klavišai**: Ctrl+Shift+E (redagavimas), Ctrl+Shift+H (paslėpti viską), keičiami.
- **Config v5**: seni failai migruojami, nauji laukai ateina per `_merge`.
- Testai: 34 (15 seni + 19 nauji: registras, migracija, standings klasės / aukštis, žaidėjo duomenys, SOF, track map, visų valdiklių piešimas, Control Center, Layout tempimas pele).
- Našumas: 3 numatyti valdikliai - kaip 0.3.1 (v0.4 priedai variklyje ~0,1 % branduolio); SOF / battle / pit skaičiuojami ~2 Hz kartu su standings.
- Paleidiklis (.exe) nepakeistas (tas pats failas kaip 0.3.1, kad neprarastų SmartScreen reputacijos). Į paketą pridėtas Qt6Svg (ikonoms).

**Dar patikrinti Windows'e (sandbox'e neįmanoma):** karštųjų klavišų perregistravimas, `HKCU Run` įrašas ir `.vbs` migracija, antro paleidimo žinutė, Track map krypties ženklas (jei trasa veidrodinė - Mirror / Rotate valdiklio nustatymuose), Tyres duomenų atnaujinimas trasoje, Radar su tikru `CarLeftRight`, `dc*` pavadinimai skirtingoms mašinoms.

---

## 1. Produktas trumpai

**LTH Overlays** yra vidinis (neparduodamas) iRacing overlay paketas, LTH alternatyva RaceLabs. Svarbiausi dalykai: **tikslūs gap'ai, kurie nešokinėja** (net kai iRacing neperduoda visų mašinų), ir **customization**: filtrai, stulpeliai, profiliai.

### v0.1.0 bazė (kas buvo pradiniame archyve; live versija gali būti toliau)

| Dalis | Būsena v0.1.0 |
| --- | --- |
| Timing variklis (`lth_timing/engine.py`) | Gap'ai pagal tą patį tašką trasoje, 20 Hz, multiklasė, „pasenusių“ mašinų žymėjimas „~“ |
| Standings | Grupuota pagal klases / bendra / tik mano klasė, filtrai top N + aplink mane, 14 stulpelių |
| Relative | 3+3 mašinos, gap'as, delta per ratą (tikslus, lyginant su ta pačia vieta prieš ratą), „laps to catch“ |
| Weather | Šlapumas (7 lygiai), temperatūros, krituliai, vėjas santykinai su mašina, tendencija per 10 min |
| Engineer žinutės | 7 tipai, tik tiesiojoje, ne dažniau kaip kas 20 s |
| Performance langelis | Programos CPU, RAM, variklio µs/kadrą, iRacing FPS |
| Redagavimo režimas | Ctrl+Shift+E: tempimas, plotis kampu, Ctrl+ratukas dydis, dešinys pelės mygtukas nustatymai |
| Nustatymų dialogas | Paprastas, atskiras kiekvienam valdikliui (`settings.py`). **Jį pakeis Control Center (3 skyrius)** |
| Profiliai | Race / Qualifying / Practice, persijungia automatiškai; temos pagal lygos / serijos ID |
| Diagnostika | `tools/diagnose.py` / `LTH Diagnostics.exe`: įrašo telemetriją .npz ir parašo ataskaitą |
| Paketas | Portable Python 3.13 + PySide6-Essentials + numpy, C paleidiklis (`packaging/launcher`), `build_dist.py`, MSIX šablonas |
| Testai | 15 testų su sintetinėmis lenktynėmis (`lth_timing/sim.py`) |

### Kaip veikia gap'ai (nekeisti principo)

- Ratas padalintas į timing taškus kas ~50 m. Kiekvienai mašinai saugomas laikas, kada ji kirto kiekvieną tašką (interpoliuojama tarp kadrų).
- `gap(B už A) = laikas, kai B buvo taške X − laikas, kai A buvo tame pačiame taške X`, kur X yra paskutinė patikimai žinoma B vieta.
- Neperduodama mašina (Max Cars): naudojami tik tikri pozicijos pokyčiai, o rodomas skaičius keičiasi ne greičiau nei 3 s/s. Sustojusiai mašinai (boksai, avarija) gap'as auga realiu laiku.
- **Niekada** nekonvertuoti atstumo į laiką vidutiniu greičiu: būtent tai sukelia „kvėpuojančius“ ir šokinėjančius gap'us.

---

## 2. Kodo žemėlapis (v0.1.0; live versijoje patikrink)

```
run.py                       paleidimas (--demo, --replay f.npz, --edit, --screenshot)
lth_timing/                  be UI, tinka ir LTH Spectate
  frame.py                   kuriuos iRacing kintamuosius skaitom (CAR_VARS, SCALAR_VARS)
  irsdk.py                   Windows shared memory skaitytuvas, laukia iRacing signalo
  sessioninfo.py             YAML -> SessionModel (vairuotojai, klasės, spalvos, gamintojai)
  engine.py                  TimingEngine: update(frame) 20 Hz, snapshot() -> Snapshot(cars, relative, weather)
  weather.py                 orų būsena + tendencija
  engineer.py                engineer žinučių taisyklės ir pristatymas
  recording.py               Recorder / ReplaySource / analizė
  sim.py                     SimRace: sintetinės lenktynės testams ir demo
  data/brands.json           CarPath -> gamintojas (pildomas be kodo)
lth_overlays/                PySide6 UI
  app.py                     EngineThread (skaičiavimai), OverlayApp (UI laikmatis 10 Hz, tray, hotkey)
  window.py                  OverlayWidget bazė: topmost, click-through, redagavimas, draw_text talpykla
  widgets/table.py           lentelės piešimas (Standings, Relative)
  widgets/*.py               standings, relative, weather, engineer (+ perf)
  config.py                  config.json, profiliai, DEFAULT_WIDGETS
  settings.py                senas nustatymų dialogas (keisti Control Center)
  theme.py                   temos, šriftai (data/fonts), formatavimas
  win32.py                   WS_EX_* stiliai, RegisterHotKey, prioritetas, RAM/CPU matavimas
tools/diagnose.py            record / report / simulate
packaging/                   launcher.c (+ zig kompiliavimas), build_dist.py, msix/
tests/test_engine.py         variklio testai
```

**Valdiklio sutartis** (`OverlayWidget`): `content_key(snap)` grąžina hashable reikšmę viskam, kas piešiama; `desired_height()`; `paint_content(painter)`; `wants_visible(snap)`. Perpiešiama TIK jei `content_key` pasikeitė. Tekstas piešiamas per `self.draw_text(...)` (QStaticText talpykla), ne `drawText`.

**Duomenų kelias:** `EngineThread` (atskira gija) → kas 0,1 s `Snapshot` → UI laikmatis išdalina valdikliams pagal `RATES` (`app.py`). UI gija iRacing duomenų tiesiogiai neskaito.

---

## 3. v0.2 — Control Center: viena vieta viskam reguliuoti (PRIORITETAS #1)

Vartotojas nori UI, kuriame galima sureguliuoti **viską**. Dabartinis `settings.py` dialogas yra per mažas ir išmėtytas.

### 3.1 Koncepcija

- Atskiras normalus Windows langas **„LTH Overlays Control Center“** (QMainWindow). Jis NĖRA overlay: turi rėmelį, gali turėti fokusą, rodomas užduočių juostoje.
- Atsidaro paleidus programą ir paspaudus tray ikoną. Uždarius langą programa lieka tray (overlay'ai veikia toliau). Išjungti galima per „Quit“.
- **Visi pakeitimai iš karto matomi overlay'uose** (live preview), išsaugomi automatiškai.
- Kai iRacing neveikia, overlay'ai rodo demo duomenis (`preview_snapshot()` jau yra), kad būtų galima derinti išvaizdą.
- Stilius: tamsus, LTH auksinis akcentas, Saira Condensed, toks pat kaip overlay'ų.

### 3.2 Architektūra: nustatymų schema (būtina)

Kad kiekvienas naujas valdiklis (20 punktų iš 4 skyriaus) automatiškai gautų nustatymų UI, nustatymai aprašomi **schema**, o UI generuojamas iš jos:

```python
# pvz. lth_overlays/schema.py
WidgetSchema("relative", title="Relative", groups=[
    Group("Rows", [Int("ahead", "Cars ahead", 1, 8, default=3), Int("behind", ...)]),
    Group("Columns", [Columns("columns", RELATIVE_COLUMNS, reorder=True)]),
    Group("Look", [Slider("scale", "Size", 0.6, 2.5), Slider("opacity", ...), Choice("name_mode", ...)]),
])
```

- Tipai: `Bool`, `Int`, `Float/Slider`, `Choice`, `Color`, `Columns` (įjungti + tvarka tempiant), `Hotkey`, `Text`, `IdList`.
- Iš schemos generuojamos ir `DEFAULT_WIDGETS` reikšmės (vienas tiesos šaltinis).
- Senas `settings.py` pašalinamas tik tada, kai Control Center padengia viską. Dešinys pelės mygtukas ant overlay'aus atidaro Control Center tame valdiklio puslapyje.

### 3.3 Puslapiai (kairėje šoninis meniu)

| Puslapis | Kas reguliuojama |
| --- | --- |
| **Overlays** | Visų valdiklių sąrašas su įjungimu / išjungimu, mini peržiūra, mygtukas „Edit layout“ (Ctrl+Shift+E) ir „Reset position“ |
| **[Kiekvienas valdiklis]** | Visi jo nustatymai iš schemos: stulpeliai (tvarka tempiant), filtrai, eilučių skaičius, dydis, permatomumas, šriftas, **tiksli pozicija X/Y skaičiais**, monitorius, matomumo taisyklės (on track / garage / replay / only when wet ir pan.) |
| **Layout** | Tinklelis (dydis, prilipimas įjungtas / išjungtas), lygiavimas, visų valdiklių atstatymas, „Copy layout from profile…“ |
| **Profiles** | Race / Qualifying / Practice + vartotojo profiliai; auto switch pagal sesiją; priskyrimas lygai / serijai (iRacing ID); dublikavimas; import / export JSON |
| **Theme** | Paruoštos temos + **savo tema**: spalvų parinkikliai visiems žetonams (bg, header, text, dim, accent, good, bad, purple, blue, red, pit, yellow, me_bg), fono permatomumas, kampų apvalumas, antraštės stilius, šrifto pasirinkimas ir bazinis dydis, klasių spalvų perrašymas |
| **Engineer** | Žinučių tipai, slenksčiai (pvz. „car ahead“ < 3 s, „behind closing“ < 1,5 s), cooldown, rodymo trukmė, „tik tiesiojoje“ jautrumas (throttle %, vairo kampas), balsas (Windows TTS) įjungti / išjungti |
| **Hotkeys** | Persiskiriami klavišai: edit layout, show / hide visų, kiekvieno valdiklio rodymas, perjungti profilį, „push to talk“ inžinieriui (v1.2) |
| **Timing** | Variklio dažnis (15–30 Hz), „stale“ slenkstis, kiek ~ rodyti, gap formatas (dešimtosios / šimtosios), Max Cars patarimas (rodo, kiek mašinų iRacing perduoda) |
| **LTH League** | LTH dalyvių iRacing ID sąrašas (filtras „LTH only“), lygos temos priskyrimas |
| **Performance** | Gyvas grafikas: LTH CPU %, RAM, variklio µs, iRacing FPS; mygtukas „Measure impact“ (30 s su overlay'ais ir 30 s be jų, rezultatas) |
| **Diagnostics** | Mygtukas „Record 10 min“, progreso juosta, ataskaitos peržiūra, „Open folder“ |
| **About / Updates** | Versija, changelog, licencijos (šriftai OFL) |

### 3.4 Priėmimo kriterijai

- [ ] Kiekvieną nustatymą, kurį galima keisti `config.json`, galima pakeisti ir per Control Center.
- [ ] Pakeitimas matomas overlay'uje per < 200 ms, be programos perkrovimo.
- [ ] Control Center uždarytas: CPU nepadidėja (langas nepiešiamas, kai paslėptas).
- [ ] Senas `config.json` iš v0.1.0 atsidaro be klaidų.
- [ ] Naujas valdiklis gauna nustatymų puslapį vien aprašius schemą (be rankinio UI kodo).
- [ ] Veikia su demo duomenimis, kai iRacing išjungtas.

---

## 4. 20 naujų valdiklių (idėjų bankas → darbų sąrašas)

Kiekvienas valdiklis: atskiras failas `lth_overlays/widgets/<name>.py`, schema Control Center'iui, numatytai **išjungtas** (kad nepridėtų CPU tiems, kas nenaudoja), testas su `SimRace` ar įrašu, ekrano nuotrauka per `--screenshot`.

Jei reikia naujų iRacing kintamųjų, pridėk juos į `lth_timing/frame.py`. Skaitomi tik tie kintamieji, kurie ten išvardinti.

Etapai: **v1.1** = pirmiausia, **v1.2** = po to, **vėliau** = kai bus laiko.

| # | Valdiklis | Duomenys | Ką rodo / daro | Etapas |
| --- | --- | --- | --- | --- |
| 1 | **Battle analysis** | Variklio mini sektorių laikai (jau saugomi `hist_t`) | Prieš mašiną priekyje / už: kuriuose sektoriuose tu greitesnis, o kuriuose jis („S1 +0.2 you, S3 −0.3 him“). Sektoriai = trasa padalinta į 3–6 dalis arba iRacing sektoriai iš session info | v1.1 |
| 2 | **Fuel calculator** | `FuelLevel`, sunaudojimas per ratą (skaičiuoti iš `FuelLevel` pokyčio per ratą, ne `FuelUsePerHour`), likęs laikas / ratai | Kuro užtenka X ratų, reikia pilti Y l, ar užteks iki finišo, rekomendacija kitam pit stop'ui | v1.1 |
| 3 | **Delta bar** | `LapDeltaToBestLap`, `..._OptimalLap`, `..._SessionBestLap` ir jų `_OK` | Horizontali juosta + skaičius: ar dabartinis ratas greitesnis už pasirinktą atskaitą | v1.1 |
| 4 | **Radar (spotter)** | `CarLeftRight` (0 off, 1 clear, 2 left, 3 right, 4 left+right, 5 two left, 6 two right) + variklio pozicijos | Mašina kairėje / dešinėje, atstumas metrais; rodoma tik kai šalia kažkas yra | v1.1 |
| 5 | **Flags** | `SessionFlags` (irsdk_Flags bitai) | Didelė geltona / mėlyna / juoda / balta / šachmatinė vėliava, rodoma kelias sekundes | v1.1 |
| 6 | **Pit helper** | `PitSvFlags`, `PitSvFuel`, `PitRepairLeft`, `PitOptRepairLeft`, `FastRepairAvailable`, `dcPitSpeedLimiterToggle`, `OnPitRoad` | Kas pažymėta servisui, remonto laikas, įspėjimas „LIMITER“ prieš boksų liniją | v1.1 |
| 7 | **Pit loss & strategy** | Variklio išmatuoti kitų mašinų sustojimai (įvažiavimas → išvažiavimas) | Kiek kainuoja stotelė šioje trasoje, kur išvažiuosi („P7 behind #14, +1.5 s“), undercut / overcut | v1.2 |
| 8 | **Endurance stints** | `DCDriversSoFar`, `DCLapStatus`, stinto laikas, komandos pilotai iš session info | Ar įvykdyti pilotų keitimo reikalavimai, kiek liko stinto, kas važiuos toliau (Vaikų Svajonės, komandinės lenktynės) | v1.2 |
| 9 | **Tyres** | `LF/RF/LR/RRtempCL/CM/CR`, `..coldPressure`, `..wearL/M/R`, `TireSetsAvailable` | Temperatūros ir nusidėvėjimas; **patikrinti: iRacing gyvai šiuos duomenis gali atnaujinti tik boksuose** | v1.2 |
| 10 | **Input graph** | `Throttle`, `Brake`, `Clutch`, `SteeringWheelAngle`, `BrakeABSactive`, `Gear`, `Speed` | Pedalų kreivės per paskutines ~5 s, ABS įsijungimas | v1.2 |
| 11 | **Lap history** | `CarIdxLastLapTime` (mano), variklio ratų istorija | Paskutiniai 10 ratų, stinto vidurkis, nuoseklumas (standartinis nuokrypis), geriausias | v1.1 |
| 12 | **Track map** | Vienas įrašytas ratas (`YawNorth` + `Speed` integravimas, uždarymo paklaidos korekcija), visų `LapDistPct` | Trasa ir visos mašinos kaip taškai su klasės spalva; kur stovi avarija | v1.2 |
| 13 | **Engine warnings** | `EngineWarnings`, `WaterTemp`, `OilTemp`, `OilPress`, `Voltage` | Rodoma TIK esant problemai (perkaitimas, alyvos slėgis ir pan.) | v1.2 |
| 14 | **Connection warning** | `ChanQuality`, `ChanLatency`, `ChanPartnerQuality` | „Bad connection“, kol dar nepradėjai „warpinti“ | v1.1 |
| 15 | **Incidents** | `PlayerCarMyIncidentCount`, `PlayerCarTeamIncidentCount` | Popup „+2x“ ir bendras skaičius; įspėjimas artėjant prie limito (limitas nustatomas Control Center) | v1.1 |
| 16 | **Setting change popups** | `dcBrakeBias`, `dcTractionControl*`, `dcABS`, kiti `dc*` (priklauso nuo mašinos) | Popup „BB 54.2 → 53.8“, kai keiti ant vairo | v1.1 |
| 17 | **Formation lap** | `PaceMode`, `CarIdxPaceRow`, `CarIdxPaceLine`, `CarIdxPaceFlags` | „You: row 3, left“, kas priekyje, kas šalia | v1.2 |
| 18 | **Radio speaker** | `RadioTransmitCarIdx` | Kas dabar kalba radiju (vardas, numeris) | v1.2 |
| 19 | **Steward decisions** | LTH stewardų sistema (lthracing domenas, web API) | Popup pilotui: „Warning: contact T1“. Reikia API iš stewardų sistemos; be interneto programa veikia toliau | v1.2 |
| 20 | **G-force & speed** | `LatAccel`, `LongAccel`, `Speed` | G taškas apskritime, greitis; labiau stream'ui | vėliau |

### 4.1 Engineer žinutės v1.1 (variklio dalis)

- [ ] „#22 pitted: undercut chance“ — konkurentas ±1 pozicija įvažiavo į boksus.
- [ ] „Box now: exit P7 behind #14, +1.5 s“ — pit exit prognozė (naudoja #7 pit loss).
- [ ] „Last 3 laps 0.6 s slower than stint average“ — tempo kritimas.
- [ ] Faster class iš už nugaros (jau yra v0.1.0, patikrinti tikrose multiklasės lenktynėse).
- [ ] Balsas (Windows TTS, pasirenkamas Control Center).

### 4.2 Žmogus prie mikrofono (v1.2)

Programa patiekia vietinį web puslapį „Engineer“: komandos draugas mato duomenis ir vienu mygtuku siunčia žinutę į piloto overlay'ų (BOX BOX, PUSH, SAVE FUEL, „fast car behind“, savo tekstas). Iš kito miesto — per Tailscale. HTTP serveris turi klausytis tik vietiniame tinkle / Tailscale ir turėti slaptažodį.

### 4.3 Stream'ui iš to paties variklio (vėliau)

Lap chart, kovos analizė komentatoriams, pit stop palyginimas, speed trap visoms mašinoms. Duomenys per vietinį WebSocket, grafika HTML (OBS browser source).

---

## 5. Našumo biudžetas ir taisyklės

| Matas | Tikslas | v0.1.0 matavimas (sintetinės lenktynės, lėtas serveris) |
| --- | --- | --- |
| iRacing FPS kritimas | < 1 % | matuoti Performance puslapyje |
| LTH CPU | < 1–2 % vieno branduolio | ~3 % (40 mašinų, visi valdikliai) |
| RAM | < 150 MB | ~100 MB |
| Variklio kadras | < 150 µs | ~30–90 µs |

Taisyklės kiekvienam naujam valdikliui:
- Skaičiuoja variklio gijoje arba savo `content_key` metu, **ne** `paintEvent` metu.
- Perpiešia tik pasikeitus rodomam tekstui (suapvalinti iki rodomo tikslumo).
- Atnaujinimo dažnis pagal poreikį (`RATES` `app.py`): radar / delta bar 10–20 Hz, lentelės 2–5 Hz, orai 1 Hz.
- Išjungtas valdiklis = nulinė kaina (nei skaičiavimų, nei piešimo).
- Jokių šešėlių, blur, animacijų, Chromium. Tekstas tik per `draw_text`.
- Po kiekvieno valdiklio paleisk `--demo` su Performance langeliu ir palygink CPU su ankstesniu.

---

## 6. Testavimas

- `python -m pytest -q`: visi testai turi praeiti prieš commit.
- `python run.py --demo`: sintetinė multiklasės lenktynė su lietumi, boksais ir „neperduodamomis“ mašinomis.
- `python run.py --screenshot out.png`: visų valdiklių vaizdas 1920x1080 (patogu vizualiai patikrinti).
- `python run.py --replay irasas.npz`: tikros iRacing sesijos įrašas iš `LTH Diagnostics.exe`.
- `python tools/diagnose.py report irasas.npz`: gap'ų šuolių ataskaita (tikslas: 0 šuolių > 1 s).
- Nauji variklio skaičiavimai lyginami su `SimRace` tikra trajektorija (žr. `tests/test_engine.py`).

**Būtina patikrinti tikrame iRacing** (sintetika to neparodo):
- [ ] Kaip dažnai atnaujinamos neperduodamų mašinų pozicijos (diagnostikos ataskaita su Max Cars 10 ir 63).
- [ ] Ar `CarIdxTrackSurface` rodo -1 neperduodamoms mašinoms.
- [ ] `WindDir` kryptis: ar tai „iš kur pučia“ (vėjo rodyklė Weather valdiklyje).
- [ ] Overlay'ai borderless režimu, focus niekada nepereina nuo iRacing, Ctrl+Shift+E veikia.
- [ ] Tyre temps / wear: ar atnaujinami važiuojant.

---

## 7. Paketavimas ir platinimas

- `python packaging/build_dist.py` surenka `dist/LTH Overlays/` + zip (portable Python, wheels, C paleidiklis). Paleidiklį perkompiliuoti: `python -m ziglang cc -target x86_64-windows-gnu ...` (komandos `packaging/launcher`).
- **SmartScreen:** kol programa nepasirašyta, pirmą kartą reikia „More info → Run anyway“.
  - Geriausias kelias: **Microsoft Store (MSIX)**. Individualaus developerio registracija nemokama, Store pasirašo programą pats, įspėjimo nėra. Šablonas: `packaging/msix/` (užpildyti Identity iš Partner Center).
  - Azure Artifact Signing (~$10/mėn.) ES galimas tik įmonėms. EV sertifikatai nuo 2024 m. nebeduoda pasitikėjimo iš karto.
- Versijos numeris: `lth_timing/__init__.py` `VERSION`. Kiekvienam leidimui pildyk `CHANGELOG.md`.

---

## 8. Siūloma darbų eilė

1. [x] **Auditas** (0 skyrius): atsarginė kopija, testai, live versijos skirtumų sąrašas vartotojui.
2. [x] **Nustatymų schema** (3.2) + perkelti esamų 5 valdiklių nustatymus į ją.
3. [x] **Control Center** (3.3): puslapiai Overlays, valdiklių, Profiles, Theme, Hotkeys, Performance, Diagnostics.
4. [x] v1.1 valdikliai: Delta bar, Fuel, Flags, Radar, Lap history, Incidents, Setting popups, Connection warning, Pit helper, Battle analysis.
5. [ ] Engineer v1.1 žinutės.
6. [x] v1.2 valdikliai (be Steward decisions - reikia API): Pit loss & strategy, Endurance stints, Tyres, Input graph, Track map, Engine warnings, Formation, Radio, G-force.
7. [ ] Engineer web puslapis (žmogus prie mikrofono).
8. [ ] Microsoft Store leidimas.

## 9. Atviri klausimai vartotojui

- [ ] Kurios multiklasės serijos įrašus naudojam testams?
- [ ] Ar overlay'us skirtas visiems iracing.lt nariams, ar tik LTH LYGOS dalyviams?
- [ ] Steward decisions: ar stewardų sistema gali turėti API, iš kurios overlay gautų sprendimus?
- [ ] Incidentų limitas pagal LTH reglamentą (įspėjimui)?
- [ ] Ar Control Center turi būti apsaugotas, kad pilotai negalėtų pakeisti LTH lygos privalomų nustatymų (jei tokių bus)?
