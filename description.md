# Kravspec: Ecowitt väderdata-pipeline

## Bakgrund

Väderstation Ecowitt WS90 (piezo-regnmätare, vind, sol/UV) ansluten till en
HP2564-display/konsol. Målet är att få ut mätdata för analys lokalt, utan
diagram eller extra processning i själva pipelinen — bara ett rent dataflöde
fram till ett arbetsformat som är redo för vidare analys i pandas/Jupyter.

**Viktig avgränsning som redan utretts:** HP2564:ans lokala HTTP-API
(`get_livedata_info`) ger bara aktuella/live-värden, inte historiskt
lagrad data. All historik måste därför hämtas via **Ecowitts molnbaserade
Cloud API** (kräver att stationen är kopplad till ett ecowitt.net-konto).

## Autentisering

Cloud API kräver tre värden i varje anrop:

- `application_key`
- `api_key`
- `mac` (stationens MAC-adress, finns i ecowitt.net-kontot eller WSView Plus)

Båda nycklarna skapas under ecowitt.net → kontoikon → User Profile /
Private Center → API Keys (en Application Key + en API Key, separata).

## API-endpoint och parametrar

```
GET https://api.ecowitt.net/api/v3/device/history
```

| Parameter           | Värde                          | Kommentar                                  |
| ------------------- | ------------------------------ | ------------------------------------------ |
| `application_key`   | din nyckel                     |                                            |
| `api_key`           | din nyckel                     |                                            |
| `mac`               | stationens MAC                 |                                            |
| `start_date`        | `YYYY-MM-DD HH:MM:SS`          |                                            |
| `end_date`          | `YYYY-MM-DD HH:MM:SS`          |                                            |
| `cycle_type`        | se tabell nedan                |                                            |
| `call_back`         | kommaseparerad lista, se nedan | `all` fungerar INTE — måste anges explicit |
| `temp_unitid`       | `1`                            | Celsius                                    |
| `pressure_unitid`   | `3`                            | hPa                                        |
| `wind_speed_unitid` | `6`                            | m/s                                        |
| `rainfall_unitid`   | `12`                           | mm                                         |

### call_back-grupper (för nuvarande sensoruppsättning)

```
outdoor,indoor,solar_and_uvi,rainfall_piezo,wind,pressure
```

- `rainfall_piezo`, **inte** `rainfall` — WS90 är piezo-baserad, inte
  tippande skopa.
- `soil_ch1`–`soil_ch4` (jordfuktssensorer) är **medvetet uteslutna tills
  vidare** — läggs till när de sensorerna är på plats. OBS: redan hämtade
  rå-JSON-filer (se steg 1) uppdateras inte automatiskt när gruppen läggs
  till efteråt; de dagarna måste hämtas om manuellt om man vill ha
  jordfukt bakåt i tiden också.
- Extra kanalgivare (t.ex. en framtida takmonterad vindgivare) hamnar
  sannolikt i den redan existerande `wind`-gruppen och kräver ingen
  ändring.

### cycle_type: upplösning, historikdjup och max spann per anrop

| `cycle_type` | Upplösning | Hur långt tillbaka | Max spann/anrop |
| ------------ | ---------- | ------------------ | --------------- |
| `5min`       | 5 minuter  | ~90 dagar          | 1 dygn          |
| `30min`      | 30 minuter | ~1 år              | 1 vecka         |
| `4hour`      | 4 timmar   | ~2 år              | 1 månad         |
| `1day`       | 1 dygn     | sedan 2019-01-01   | 1 år            |

**Viktigt om vad värdena betyder:** Vid `5min` är varje punkt en
ögonblicksavläsning. Vid grövre upplösning (`30min`/`4hour`/`1day`)
returneras istället tre varianter per mätvärde:

- huvudvärdet = **medelvärde** för perioden (bekräftat empiriskt)
- `..._high` = max under perioden
- `..._low` = min under perioden

**90-dagarsgränsen är den praktiska knuten**: 5-minutersdata äldre än
~90 dagar går inte att hämta i efterhand — måste samlas in _innan_ den
åldras ut. Arbetssättet är att hämta manuellt då och då (inte ett
schemalagt jobb just nu), så länge man inte väntar längre än ~90 dagar
mellan hämtningarna.

### Svarsformat (JSON)

Nästlat per grupp och mätvärde:

```json
{
  "code": 0,
  "data": {
    "outdoor": {
      "temperature": { "unit": "C", "list": { "<unix_ts>": "18.3", ... } },
      ...
    },
    "wind": { ... },
    ...
  }
}
```

Tidsstämplar i `list` är unix-sekunder, UTC. `code != 0` betyder fel —
avbryt och visa `msg`.

## Pipeline: tre steg

Designprincip: varje steg gör en sak. Diagram/visualisering är
**explicit utanför scope** för dessa tre steg — tänkt som ett eventuellt
separat steg 4 senare, som bara läser output från steg 3.

### Steg 1 (bash + curl + jq): hämta rådata

- Input: `start_date`, `end_date`, `cycle_type` som kommandoradsargument.
- Loopar i chunkar enligt max spann-tabellen ovan (t.ex. ett anrop per
  dygn för `5min`), med paus mellan anrop (rate limit: 1 anrop/sek med
  API key).
- Sparar **varje chunks rå, oförändrade JSON-svar** som en egen fil i en
  `raw/`-mapp, namngiven t.ex. `<cycle_type>_<datum>.json`.
- **Resumable**: hoppar över chunkar vars fil redan finns i `raw/`, så
  att man kan köra om med ett bredare intervall och bara nytt hämtas.
- Anledning till att spara rådata orört: 5-minutersdata går inte att
  hämta om efter 90 dagar, så rådatan är den enda permanenta
  källan — om omformningslogiken längre fram visar sig behöva ändras
  finns fortfarande allt kvar att bygga om ifrån.

### Steg 2 (bash + jq): rå JSON → långt CSV-format

- Input: `raw/`-mappen (alla `.json`-filer).
- Plattar ut till **långt format**: en rad per `(tidsstämpel, mätvärde,
värde)`, inte en kolumn per mätvärde.
- Kolumner: `Tidsstämpel,mätvärde,värde`. Tidsstämpel konverterad till
  lokal tid (inte UTC).
- Varför långt format: okänsligt för att sensorer tillkommer/försvinner
  mellan körningar (nya sensorer blir bara fler rader, inga nya
  kolumner som stör befintlig struktur). Går även att öppna direkt i
  Excel och pivotera manuellt (Infoga → Pivottabell) som en oberoende
  väg, utan Python.

### Steg 3 (Python + pandas): långt CSV → brett arbetsformat (JSON)

- Input: den långa CSV-filen från steg 2.
- Pivoterar med `pivot_table(index="Tidsstämpel", columns="mätvärde",
values="värde", aggfunc="first")` till brett format (en kolumn per
  mätvärde).
- Skriver ut som **records-orienterad JSON** (`orient="records"`): en
  lista med ett dict per tidsstämpel, t.ex.
  `[{"Tidsstämpel": "...", "outdoor_temperature": "18.3", ...}, ...]`.
  Valt eftersom det är direkt läsbart med `pd.read_json(..., 
orient="records")` eller `pd.DataFrame(json.load(...))` utan omvägar.
- Saknade mätvärden för en given tidpunkt (t.ex. sensor ännu inte
  påkopplad) blir `null`, raden tas inte bort.
- Detta är tänkt som **startpunkten för vidare analys** (Jupyter/pandas)
  — inget mer ska egentligen behöva göras i själva pipelinen härifrån.

## Redan byggda prototyper (utgångspunkt)

Tre fungerande skriptfiler finns redan som första implementation och kan
användas som grund att bygga vidare på/städa upp:

- `fetch_raw.sh`
- `flatten_csv.sh`
- `widen-json_json.py`

## Kända öppna punkter / framtida arbete (inte del av detta uppdrag nu)

- Lägga till `soil_ch1`–`soil_ch4` i `call_back` när jordsensorerna
  anländer, plus ta ställning till om gamla `raw/`-filer ska hämtas om.
- Eventuellt bygga in en varning i steg 1 om en befintlig rå-fil saknar
  en grupp som nu efterfrågas (istället för att tyst skippa den).
- Diagram/visualisering (separat steg 4, läser steg 3:s output).
- Möjlig framtida väg: låta HP2564 skicka data direkt till Azure
  (Blob Storage + Azure Functions, samma stack som redan används i ett
  annat pågående projekt) — antingen via konsolens ev. "Custom Server"-
  läge, eller en schemalagd Azure Function som gör samma jobb som steg 1
  fast i molnet. Inte påbörjat.
