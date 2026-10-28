# LTH Overlays v0.6 — research (2026-10-28)

## Ką turi kiti

**RaceLab** (rinkos lyderis, prenumerata, Electron) — 30 overlay'ų iRacing'ui: Standings, Relative, Fuel, Input Telemetry, Delta Trace, Track Map, Flat Map, Flags, Head to Head, Overtake Alert, Blind Spot, Radar / Radar Bars, Data Blocks, G-force, Laptime Graph / Log / Spread, Minimap, Pitbox Helper, Session Timer, Weather, Digiflag, Leaderboard, Race Schedule.
Naujausi dalykai (2025–2026): nacionalinės vėliavos prie vardų (Standings / Relative, įjungiama stulpeliuose), stulpelių tvarka tempiant, „Lumina“ tema, vairuotojų žymos (tag notes su spalva), „Minimum visible drivers“, Track map V3 (draugų / lyderio žymekliai, post-pit indikatorius, rėmeliai ir spalvos), ABS ant input'ų, G-force kaip input'ų modulis, Overtake Alert (greitesnė klasė iš už nugaros su iRating / licencija), Stream Deck, bendruomenės išdėstymai.

**irDashies** (atviras kodas, MIT, Electron) — labai išsamus:
- Standings / Relative: vėliavos (250+ šalių, pagal iRacing `FlairID`), vardų formatai, komandos pavadinimas po vardu, pit būsenos ženkliukai (DNF, TOW, OUT, PIT, meatball, juoda vėliava, slowdown), licencijos / iRating ženkliukai keliais formatais, gamintojas, padangų mišinys, pozicijų pokytis, iRating pokytis, „Compact / Ultra“ tankis, ofTrack paryškinimas geltonai, vairuotojų žymos (Friend, Dangerous, Twitch...), **header ir footer juostos su pasirenkamais elementais** (sesija, laikas, incidentai, brake bias, šlapumas, krituliai, vėjas, temperatūros, trasa, kuras, geriausias / paskutinis ratas, SOF klasės antraštėje), **vėliavos kontūras** aplink relative, kai sesijoje vėliava.
- Input: trace + juostos + pavara ir greitis + **vairo vizualizacija** (keli stiliai) + išdėstymo redaktorius, shift flash.
- Track map: posūkių pavadinimai, „P“ boksuose, kontūro storis, išvažiavusių paryškinimas; Flat track map.
- Kiti: Rejoin indicator, Faster cars from behind, Slow car ahead, Blind spot, Pitlane helper (atstumas iki boksų, limiteris), Lap timer (prognozė), Sector delta, Garage cover, OBS naršyklės šaltiniai, profiliai pagal sesiją, karštieji klavišai kiekvienam valdikliui.

**iOverlay** (freemium, 2,50–4,95 €/mėn.) — Standings / Relative su ~32 reikšmėmis antraštėse, Fuel, Inputs, Track map, Flat map, Spotter, Multiclass traffic, Pit entry/exit helper, Race control, komandos kuro dalinimasis.

**Kapps** — nemokamas; bendruomenė pati „užlopė“ vėliavas pagal `FlairID` (kapps-country-flags).

## Bendruomenės nuomonė (santrauka)
- Patinka: tikslūs gap'ai, vėliavos ir licencijų spalvos (greitai matai, kas šalia), klasių spalvos, mažas dydis, galimybė dėti informaciją į header / footer, layout'ų dalinimasis.
- Nepatinka: prenumeratos kaina (RaceLab, iOverlay Pro), Electron programų CPU / RAM apetitas, per daug „triukšmo“ ekrane, šokinėjantys gap'ai, nepatogus nustatymas.
- Dažniausi prašymai: vėliavos, draugų žymos, Overtake / faster class alert, smooth track map ir input'ai, vairo vizualizacija, mygtukai pit komandoms (be black box).

## Techniniai radiniai
- iRacing sesijos YAML turi `FlairID` ir `FlairName` (šalis), `LicColor` (licencijos spalva), `CarScreenNameShort`, `ClubName`. Vėliavoms — FlairID → ISO kodas (irDashies lentelė, MIT) + flag-icons SVG (MIT).
- Pit komandos: `RegisterWindowMessageW("IRSDK_BROADCASTMSG")` + `SendNotifyMessageW(HWND_BROADCAST, msg, 9 | mode << 16, var)`; režimai: clear 0, ws 1, fuel 2, lf 3, rf 4, lr 5, rr 6, clear_tires 7, fr 8, clear_ws 9, clear_fr 10, clear_fuel 11 (pyirsdk).

## v0.6 planas
1. Relative / Standings: vėliavos, licencijos spalvos (pagal `LicColor`), mašinos stulpelis, pit / vairuotojo vėliavų ženkliukai, header + footer juostos su pasirenkamais elementais (SOF, oras, laikas...), vėliavos kontūras, tankis, perdarytas išvaizda (siauresni, tvarkingi stulpeliai).
2. Kontūras (stroke) visiems valdikliams: storis, spalva, permatomumas, globaliai ir valdikliui.
3. Inputs: greitis, pavara, besisukantis vairas, procentai.
4. Pit commands valdiklis su mygtukais (All tyres, Fuel to finish, Full, Fast repair, Windscreen, Clear).
5. Smooth track map (60 fps).
6. Šriftų pavyzdžių lapas ir nauji šriftai.
7. Papildomai: Rejoin indicator, Faster car alert, prognozuojamas rato laikas, sesijų matomumas, draugų žymos.

Šaltiniai: racelab.app/iracing, docs.racelab.app (feature news), garage.racelab.app (v7.6.0), github.com/tariknz/irdashies (README, MIT), ioverlay.app, github.com/ssg22/kapps-country-flags, github.com/kutu/pyirsdk.
