# LTH Overlays: atnaujinimai per GitHub

Kaip veikia: tu išleidi versiją GitHub'e, o visų žmonių programa (nuo 0.7.0) per kelias valandas parodo
„Update 0.7.x“. Žmogus paspaudžia **Update & restart**, programa parsisiunčia, patikrina (SHA-256) ir
persikrauna. Nustatymai (`%APPDATA%\LTH Overlays`) lieka.

## 1. Vienkartinis paruošimas (~10 min.)

1. Susikurk GitHub paskyrą (jei neturi) ir naują **viešą** repo, pvz. `lth-overlays`.
   Viešas reikalingas tam, kad programos galėtų parsisiųsti išleidimus be slaptažodžių.
   (Jei nenori rodyti kodo: kodą laikyk privačiame repo, o išleidimus - atskirame viešame. Parašyk, padėsiu.)
2. Atsidaryk `lth_overlays/data/update.json` ir įrašyk repo pavadinimą:
   ```json
   { "repo": "Djironix/lth-overlay" }
   ```
3. Įkelk kodą į repo (vieną kartą):
   ```
   git remote add origin https://github.com/Djironix/lth-overlay.git
   git push -u origin main
   ```
4. Repo puslapyje: **Settings > Actions > General > Workflow permissions** - pažymėk
   **Read and write permissions** ir išsaugok (kad Actions galėtų sukurti Release).
5. Išleisk 0.7.0 (žr. 2 žingsnį) ir išsiųsk žmonėms **pilną** zip paskutinį kartą ranka.
   Nuo jo atnaujinimai ateis patys.

## 2. Kiekvienas naujas išleidimas

1. `lth_timing/__init__.py` - padidink `VERSION` (pvz. `0.7.1`).
2. `packaging/README.txt` - parašyk skyrių `New in 0.7.1` (jis tampa Release aprašymu).
3. Commit ir push, tada vienas iš dviejų:
   - `git tag v0.7.1 && git push --tags`, arba
   - repo puslapyje **Actions > Release > Run workflow** (žymė v0.7.1 sukuriama pati).
4. GitHub Actions pats: paleidžia testus, subuildina
   `LTH-Overlays-0.7.1-win64.zip` (pilnas), `LTH-Overlays-0.7.1-update.zip` + `.sha256` ir sukuria Release.
   Eigą matai repo skiltyje **Actions** (~5-8 min.).

## 3. Ką mato žmonės

- Programa tikrina paleidus ir kas 6 val., **niekada važiuojant**.
- Control Center viršuje atsiranda auksinis mygtukas **Update 0.7.1**, varpelis ir pranešimas prie laikrodžio.
- General > Updates: „Check now“, „Release notes“, „Update & restart“.
- Jei naujai versijai reikia kito Python / Qt (retai), programa parašo, kad reikia pilno zip
  (mygtukas „Release notes“ atidaro GitHub puslapį su juo).
- Jei nauja versija kažkodėl nepasileidžia, grąžinama ankstesnė (`app\_prev`).
- Microsoft Store versija atsinaujina per Store, ten tikrinimas išjungtas.

## Saugumas

- Siunčiama tik iš `api.github.com` / `github.com`, HTTPS, tikrinama SHA-256.
- Atnaujinimas keičia tik `app\` aplanką (Python failai). `.exe` nekeičiamas - SmartScreen reputacija lieka.
