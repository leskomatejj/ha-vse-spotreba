# VSE spotreba — Home Assistant integrácia

Neoficiálna integrácia pre Home Assistant, ktorá sťahuje **spotrebu elektriny
z inteligentného merača** z portálu [www.vse.sk](https://www.vse.sk)
(Východoslovenská energetika).

> ⚠️ Neoficiálne, nie je spojené s VSE/VSD. Používa to isté interné API ako
> webový portál. Prihlásenie prebieha cez Azure AD B2C vaším e-mailom a heslom.

## Čo poskytuje

- **Denná spotreba** — kWh za posledný kompletný deň (senzor)
- **Spotreba za obdobie** — súhrn za sťahované obdobie (voliteľný senzor)
- Atribúty: denný rozpis za posledných N dní a **hodinový rozpis** posledného dňa
  (vhodné na graf napr. cez [ApexCharts card](https://github.com/RomRider/apexcharts-card))

Dáta z merača chodia **spätne s ~1-dňovým oneskorením**, preto sa sťahujú
raz za hodinu. Nejde o okamžité meranie v reálnom čase.

## Inštalácia cez HACS

1. HACS → ⋮ → **Custom repositories** → pridaj
   `https://github.com/leskomatejj/ha-vse-spotreba`, kategória **Integration**.
2. Nainštaluj **VSE spotreba** a reštartuj Home Assistant.
3. **Nastavenia → Zariadenia a služby → Pridať integráciu → „VSE spotreba"**.

### Manuálna inštalácia

Skopíruj priečinok `custom_components/vse_spotreba` do `/config/custom_components/`
a reštartuj Home Assistant.

## Nastavenie

Sprievodca má dva kroky:

1. **Prihlásenie** — e-mail a heslo do portálu VSE (overia sa prihlásením).
2. **Odberné miesto** — po prihlásení sa odberné miesta **načítajú automaticky**,
   stačí si jedno vybrať zo zoznamu (adresa + typ). Ak by sa nič nenašlo,
   sprievodca ponúkne ručné zadanie identifikátorov.

Rozsah histórie (7/30/90 dní, tento mesiac, 12 mesiacov) sa dá kedykoľvek
zmeniť cez **Nastaviť** pri integrácii.

## Senzory

| Entita | Popis | Jednotka |
|--------|-------|----------|
| `sensor.vse_odberne_miesto_<om>_denna_spotreba` | posledný kompletný deň | kWh |
| `sensor.vse_odberne_miesto_<om>_spotreba_za_obdobie` | súhrn obdobia (predvolene vypnutý) | kWh |

Príklad grafu dennej histórie (ApexCharts):

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: VSE denná spotreba
series:
  - entity: sensor.vse_odberne_miesto_906779_denna_spotreba
    data_generator: |
      return entity.attributes.dni.map(d => [new Date(d.datum).getTime(), d.kwh]);
    type: column
```

## Energy Dashboard

Integrácia zapisuje hodinovú spotrebu aj do **dlhodobých štatistík** Home
Assistantu (ako externú štatistiku `vse_spotreba:spotreba_<om>`), takže ju vieš
pridať do energetického panela:

**Nastavenia → Dashboardy → Energia → Pridať spotrebu → Použiť existujúcu
štatistiku** → vyber `VSE spotreba <om>`.

Dáta sú spätné (~1 deň), takže v paneli sa posledný deň doplní s oneskorením.

## Súkromie a bezpečnosť

- Heslo sa ukladá v konfigurácii Home Assistantu a posiela sa **len na vse.sk**
  (Azure AD B2C) pri prihlásení.
- Integrácia nepoužíva žiadne externé knižnice (len štandardný Python).

## Poznámky

- Portál môže login flow kedykoľvek zmeniť — vtedy bude treba integráciu upraviť.
- Nemá reálny čas; pre okamžitú spotrebu je potrebné zákaznícke rozhranie
  priamo na meradle (P1/HAN port).

## Licencia

MIT
