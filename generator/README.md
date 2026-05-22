# Tekst-TV generator

Denne mappen inneholder scriptet som lager `tekst-tv/pages.json`, altså feeden Apple TV-appen viser.

Foreløpig støtter generatoren:

- NRK siste nytt RSS som første ekte nyhetskilde.
- BBC World RSS for utenriks.
- Valgfri OpenAI-oversettelse/oppsummering av utenriksnyheter til norsk.
- TheSportsDB for Premier League/Eliteserien-tabeller og kommende kamper.
- Fallback-data hvis nettet/feed feiler.
- Samme JSON-format som appen allerede leser.

Kjør lokalt:

```bash
python3 generator/generate_pages.py --output tekst-tv/pages.json
```

Med norsk AI-oversettelse av utenriksnyheter:

```bash
export OPENAI_API_KEY="..."
python3 generator/generate_pages.py --output tekst-tv/pages.json
```

Valgfri modelloverstyring:

```bash
export OPENAI_MODEL="gpt-5.2"
```

Kjør uten nett:

```bash
python3 generator/generate_pages.py --offline --output tekst-tv/pages.json
```

Senere kan samme script kjøres fra GitHub Actions og publisere `pages.json` til GitHub Pages.

## Automatisk feed via GitHub Pages

Repoet har workflowen `.github/workflows/publish-feed.yml`.

Den gjør dette:

- kjører hvert 5. minutt, så ofte GitHub Actions tillater
- kjører `generator/generate_pages.py`
- publiserer `public/pages.json` til GitHub Pages
- lager en enkel `index.html` som viser siste oppdatering

Etter at repoet er pushet til GitHub:

1. Gå til repoet på GitHub.
2. Gå til `Settings` -> `Pages`.
3. Velg `Source: GitHub Actions`.
4. Gå til `Actions`.
5. Kjør `Publish Tekst-TV feed` manuelt første gang.
6. Åpne Pages-URL-en og sjekk at `/pages.json` finnes.

URL-en blir vanligvis:

```text
https://sveinungaxelsen.github.io/tekst-tv/pages.json
```

I Xcode må appens generated Info.plist få nøkkelen:

```text
TeletextFeedURL = https://sveinungaxelsen.github.io/tekst-tv/pages.json
```

Når den nøkkelen er satt, henter Apple TV-appen ny feed ved oppstart, når appen blir aktiv igjen, og hvert 5. minutt mens den står åpen.
