# Paris Electro/Techno/Experimental Music Research

Session-specific detail for the weekly cron research on Paris' electro/techno/experimental music scene.

## Technical Challenges & Solutions

### 1. Anti-Bot Protection
- **Problem**: RA.co uses sophisticated Cloudflare DataDome
- **Result**: All blocked (curl, MCP reader, browser navigation)
- **Workaround**: Rely on Shotgun.live and venue direct sites

### 2. Cookie Walls
- **Problem**: Some sites (IRCAM, Petit Bain) require cookie consent
- **Solution**: In browser, click "Allow all cookies" or "Accept"
- **Note**: MCP reader may not handle JavaScript-based consent

### 3. SSL/Connection Issues
- **Problem**: Several venue sites had SSL errors or connection closed
- **Solution**: Browser navigation more reliable than curl
- **Fallback**: Use aggregator platforms (Shotgun) instead

### 4. HTTP 422/400 Errors
- **Problem**: La Fabrique (422), Le 106 (422), Graindor (400) return errors via MCP reader
- **Workaround**: Skip these sources; use Shotgun.live or Tavily search instead
- **Note**: These venues may have changed their server configuration

### 5. UI Interaction Complexity
- **Problem**: EtherREAL requires clicking [+] to expand event details
- **Solution**: MCP reader returns collapsed content; use date navigation params
- **Method**: `?rubrique10&date=YYYY-MM-DD` for specific dates

## Key Events Discovered (Late June – July 2026)

### Priority A: Major Festival
**Peacock Society Festival**
- Dates: Fri 10–Sat 11 July 2026
- Venue: Hippodrome Paris-Vincennes, 75012 Paris
- Headliners: Robert Hood, Satoshi Tomiie, Dax J (Live), Floating Points, Boys Noize, Channel Tres, MatheW Jonson (Live), U.R.TRAX (Live), Flowdan + Benga, Girls Don't Sync, Gяег, and 40+ more
- Access: peacocksociety.fr, RER A Joinville-le-Pont
- Found via: Tavily web search

**IRCAM ManiFeste 2026**
- Date: June 3–27, 2026
- Venues: IRCAM, Centre Pompidou, CENTQUATRE, others
- Focus: Contemporary multidisciplinary creation, electroacoustic
- Highlights: Ensemble intercontemporain, world premieres, academy concerts
- Website: https://manifeste.ircam.fr

### Priority A: Signature Venue Series
**Les Instants Chavirés, Montreuil**
- May 13: Orion Music Workshop / Thelma Cappello / Jeanne Gorisse
- May 19: Quasi 2026.5 - Sauges / Christi Denton / Offset.4
- May 29: The Dwarfs Of East Agouza (Alan Bishop, Maurice Louca & Sam Shalabi)
- June 7-8: Melt-Banana (SOLD OUT)
- June 12: Officine Bill Nace
- June 17: Collectif Coax - RISA TAKEDA / YANN JOUSSEIN / LINDA OLAH
- Full program on instantschavires.com

**La Gare / Le Gore, Paris 19th**
- Weekly techno nights with resident collectives
- Notable: Pygments Inv., 59 Bel Records (weekly Thu), Club 909 (weekly Sun)
- Price range: €5.99 - €15.99
- Daily programming, typically 23:30 start

**Mains d'Œuvres, Saint-Ouen**
- May 14: Pharmakon + Shantidas (Noise/Experimental/Industrial) - €25.50
- May 30: Bait X Traverse (live performance)
- Festival mofo 20th edition ongoing

**Petit Bain, Paris (floating)**
- May 9: Disco Arabesquo Night (Arabic House/Pop)
- May 15: RADØUX (pop/electropop/techno)
- June 2: MNNQNS
- June 3: Levitation Room
- June 25: phytocene

**Rex Club, Paris 18th**
- May 2: Zeds Dead, Holly, Mary Droppinz
- May 7: Bernadette all night long
- May 8: Orbi all night long
- July: Onur Özer (3 July), Miley Serious & Lu2k, X-Coast & MarcelDune, Florian Picasso (After Pride), Furtive, Olympe X Abstract., Bérou/Noise Mafia/Ke-Yen
- Open: Wed–Sun, midnight–7am. Tickets: €20–25

**La Machine du Moulin Rouge, Paris 18th**
- May 15: Multiple experimental/hyperpop events (Fæther X Perfectly Imperfect, Hyperbrat, Fotocrime)
- May 30: Tear Club + Annie-Claude Deschenes + Nox Novacula

**La Java, Paris 11th**
- May 8: Aeromix & Ponez Club
- May 9: Apérø Tech Invite: Shoshana, See Rose & Zelva
- Ongoing weekly electro/techno

**Point Éphémère, Paris 10th**
- May 7: rRoxymore + Cabale
- May 18: Phosphorescent (indie folk)
- June 15: hypnosis therapy

**Kilomètre25, Aubervilliers**
- June 27: Pygments — MIJA, HITMILØW, VCL, Britney Speed b2b Betïses (from €8)
- June 28: Timit — Paramida, Cherii, Gigi Safari b2b Gigi L'amour, Sylvio B (from €10)
- July 2: 2222 — Ultranouk, DJ Angel, The Muffin Man, Aymen (from €12)
- July 18: Jacidorex, Suave, Unfaced, Tape
- July 24: PARALICH, Kim Swim, KLING&KLANG, ANTONYM, 2much
- Primary source: kilometre25.fr

### Priority B: Club Nights & Special Events (July—August 2026)

**Wolfgang Voigt presents Gas Live** ⭐
- **23 September** 2026, 20:00 at La Gaîté Lyrique — €37.80
- Legendary ambient techno project. Lylo gig listing confirmed this date.
- NOTE: prev session listed May; this is the correct September date.

**Nathan Fake AV Live** ⭐
- 26 September 2026, 19:30 at La Gaîté Lyrique — €26.80
- UK electronic producer known for melodic, intricate IDM. AV show.

**Mount Kimbie + Tour-Maubourg + Cabaret Contemporain** ⭐
- 29 August 2026 at Virage, Paris
- Exceptional lineup: UK post-dubstep/electronic pioneers + French house/disco + electro-jazz ensemble.

**Apparat**
- 9 October 2026 at Élysée Montmartre, Paris 18e — €53.20
- Sascha Ring's Apparat project. Electronic/experimental.

**Autechre**
- 14 October 2026 at Le Bataclan, Paris 11e — SOLD OUT
- Legendary experimental electronic/IDM act. Check resale.

**Tommy Four Seven**
- 7 August 2026 at FVTVR, Paris
- Dark industrial techno.

**Chris Liebing & Sept**
- 28 August 2026 at FVTVR, Paris
- Major German techno figure.

**Dare, The Avalanches, ali rq**
- 8 August 2026 at Silencio Club, Paris
- The Avalanches — legendary sample-based electronic.

**The Whitest Boy Alive**
- 31 August 2026 at Cabaret Sauvage, Paris 19e
- Erlend Øye's electronic/indie project.

**La Riposte: 59 Bel Records** (weekly)
- Every Thursday in July at La Gare / Le Gore, 75019 — 15€
- Weekly techno residency. Confirmed continuing through summer.

**Club 909** (weekly)
- Sundays at La Gare / Le Gore, 75019
- Detroit techno / Chicago house / hardgroove — 5€

**Glimmer at Supersonic**
- July 21 at Supersonic
- Electronic/techno

**Festival Rhizomes 2026** (25th anniversary)
- July 5–26 across multiple Paris locations + Pantin
- Free outdoor concerts + musical strolls
- DJ La Louuve at Port de Pantin (25 July)

**IRCAM — "In Situ" Concerts**
- June 27, 15:00 at IRCAM, Espace de Projection
- June 27, 19:00 at Cent Quatre, Atelier 4
- New works by academy composers, Ensemble intercontemporain, BL!NDMAN ensemble, dance films

**6th AES Conference on Audio for VR/AR and Immersive Games**
- June 30 – July 3 at Sorbonne + IRCAM
- Spatial audio, VR/AR sound, immersive gaming

### Priority C: Notable Mentions
- **Terrine** at Parc des Guilands, Montreuil — June 28
- **Stress Positions** at Le Chinois, Montreuil — June 28
- **Cosimo Fiaschi** at Bleue, Paris — June 29
- **Siestes Électroniques 2026** at Jardin Compans-Caffarelli, Toulouse — June 27–28 (not Paris but quality lineup: Almond Butyl, Kim Khan, Brokenchord, Florence Sinclair, Tracey, Yuri Umemoto, Emily Wittbrodt, La Rat, DJ Travell)
- **Clair-Obscur** at Bourse de Commerce, Paris — ongoing (art exhibition with experimental audio component)
- **Cercle Festival** at Musée de l'Air et de l'Espace, Le Bourget — emerging festival, worth watching for future editions (cercle.io)
- **Open Air x Basses Fréquences** at Le Hasard Ludique, 14 July, Bastille Day (8€)
- **Bktherula** at La Bellevilloise, 5 July
- **Gotis** at La Gare / Le Gore, 5 July
- **Acid 87 / DJ 144P / Oïmacon / Stefan Vogelsinger** at Bicyclette, Montreuil, 8 July — underground techno staple
- **BAUGRUPPE90 / Accident Theory** at Kilomètre25, 3 July
- **Thunder open air** at Kilomètre25, 25 July
- **Archangel (Nene H, Mama Snake)** at Kilomètre25, 31 July
- **Paul Cut, Kazam, MĀOKĒ, Bakos, Larry Houl** at La Rotonde Stalingrad, 4 July

## Genre Matrix Coverage Achieved
- ✅ Free Improvisation
- ✅ Experimental Electronic
- ✅ Noise Music
- ✅ Contemporary Classical (IRCAM)
- ✅ Avant-Garde Jazz
- ✅ Electroacoustic Music
- ✅ Hyperpop/Techno fusion
- ✅ Arabic House
- ✅ Industrial/Minimal Synth
- ✅ Detroit Techno
- ✅ Drone/Minimal
- ✅ Abstract Hip-Hop influences

## Source Inventory & Success Rates

### Primary Sources (mcp_jina_reader_parallel_read_url works)
| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| Etherreal | etherreal.com/spip.php?rubrique10 | ✅ Works | Full agenda, date navigation |
| Lylo | lylo.fr/concerts-electro | ⚠️ Intermittent | Was HTTP 503 on 11 Jul, worked fine 18 Jul. Retry every session. |
| IRCAM | ircam.fr/fr/events | ⚠️ Cookie wall | Content accessible but blocked by JS consent; use Tavily fallback |
| RA.co | fr.ra.co/events/fr/paris/electro | ❌ Blocked | Empty content, Cloudflare |

### Secondary Sources (mixed results)
| Source | URL | Status | Notes |
|--------|-----|--------|-------|
| ParisMix | parismix.com/concerts-electro/ | ❌ HTTP 422 | Consistently broken via MCP reader |
| PAP | pap.fr/agenda/musique-electronique-paris | ❌ CAPTCHA | Cloudflare block |
| Les Arts Décoratifs | lesartsdecoratifs.fr/agenda/ | ❌ HTTP 422 | Consistently broken via MCP reader |
| Cent Quatre | centquatre.paris/agenda/ | ❌ HTTP 422 | Consistently broken via MCP reader |

### Failed Sources (do not retry)
| Source | URL | Error | Reason |
|--------|-----|-------|--------|
| La Fabrique | la-fabrique.org/agenda/ | HTTP 422 | Anti-bot protection |
| Le 106 | le-106.fr/agenda/ | HTTP 422 | Anti-bot protection |
| Graindor | graindor.fr/agenda/ | HTTP 400 | Server error |
| Les Tanneries | les-tanneries.com/agenda/ | Wrong content | Holiday rental, not music venue |
| Supersonic | supersonic-club.com/agenda/ | HTTP 422 | Consistently broken |
| Badaboum | badaboum.org/agenda/ | HTTP 422 | Consistently broken |
| Kilomètre25 | kilometre25.com/agenda | HTTP 400 | Direct scrape fails; use Shotgun/Shazam instead |

### Discovery Layer
| Source | Use Case | Reliability |
|--------|----------|-------------|
| Tavily web search | Festival discovery, artist queries | ✅ Excellent |
| Shotgun.live | Club event listings | ✅ Good |
| Kilomètre25 direct | Suburban venue programming | ✅ Good |
| Songkick | Date/venue verification | ✅ Good — best for August+ listings; syncs with Ticketmaster |
| Shazam venue pages | Quick date/artist verification | ✅ Good |
| Cercle Festival (cercle.io) | Emerging Paris electronic festival | ⚠️ Watch for future editions |

## Output Deliverables Produced

1. **Comprehensive Report**: Full analysis with venue/artist details (`outputs/paris_music_report_[DATE].txt`)
2. **Event Triage**: Prioritized selection with quality rationales (`outputs/discord_summary_[DATE].txt`)
3. **Source Documentation**: Inventory of attempted sources and success rates
4. **Technical Artifacts**: Access methods, challenges, solutions

## Lessons Learned (Actionable)

### Success Factors
1. **mcp_jina_reader_parallel_read_url** is the most efficient discovery tool for primary sources (Etherreal, Lylo, IRCAM)
2. **Tavily web search** is essential for festival discovery and filling gaps where scraping fails
3. **Venue direct sites** (Kilomètre25, Peacock Society) are essential for specialized programming
4. **Source hierarchy**: Start with primary sources → Tavily discovery → Shotgun.live → venue direct
5. **Shazam venue pages** are useful for quick date/artist verification at known venues

### Pitfalls
1. **Do not retry** HTTP 422/400 sources — they will continue to fail
2. **RA.co** is permanently blocked — remove from source list or mark as deprecated
3. **Les Tanneries** URL points to a holiday rental, not a music venue — source list may be stale
4. **30s timeout** is insufficient for secondary sources — use 60s or fall back to Tavily
5. **Fnac Music Festival was CANCELED for 2026** — the free Hôtel de Ville event (traditionally July 1–3) is gone due to budget cuts. Do NOT list it for 2026 unless confirmed back for 2027.
6. **IRCAM cookie consent** blocks the MCP reader — the site requires JavaScript consent interaction. For event info, use Tavily search as fallback.
7. **ParisMix, Les Arts Décoratifs, Cent Quatre** return HTTP 422 via MCP reader — consistently broken, do not retry

### Recommended Tool Stack for Similar Research
- **Discovery**: Tavily web search (broad, catches festivals and announcements)
- **Primary Sources**: mcp_jina_reader_parallel_read_url (Etherreal, Lylo, IRCAM)
- **Secondary/Verification**: Shotgun.live, venue direct sites, Kilomètre25 direct
- **Fallback**: Individual mcp reads with 60s timeout
- **Avoid**: RA.co (blocked), La Fabrique/Le 106 (HTTP 422), Graindor (HTTP 400), Les Tanneries (wrong venue)
- **Verification**: Venue Instagram accounts for last-minute changes

## Venue Contact Information (for verification)
- Les Instants Chavirés: +33 1 42 87 25 91, 7 rue Richard-Lenoir, 93100 Montreuil
- La Gare / Le Gore: 1 Av. Corentin Cariou, 75019 Paris, Corentin Cariou metro (Line 7)
- Mains d'Œuvres: 1 rue Charles Garnier, 93400 Saint-Ouen
- Petit Bain: Floating on Seine, quai François Mauriac, 75013 Paris
- Point Éphémère: 200 quai de Valmy, 75010 Paris
- Kilomètre25: kilome25.fr, Aubervilliers

## Source URLs Quick Reference
```
Primary Aggregator:
  https://shotgun.live/en/cities/paris/techno
  https://shotgun.live/en/cities/paris/experimental

Venue Direct:
  https://kilometre25.fr
  https://peacocksociety.fr
  https://www.kilometre25.fr

Festival:
  https://manifeste.ircam.fr
  https://www.ircam.fr/fr/events
  https://www.rizomes.com/en

Secondary:
  https://www.lylo.fr/concerts-electro
  https://www.etherreal.com/spip.php?rubrique10
```

---

## New Discoveries & Patterns (11 July 2026)

### FVTVR — Emerging as Primary Venue
FVTVR (34 quai d'Austerlitz, 75013) is now the most active club in Paris with nightly programming.
Key series: IMF, ENDZEIT, Primal Instinct, TOYZ, Lanna Showcase (Fri-Sat, 12€).
Weekly: Jeudi OK @ Wanderlust (Thu 19h30, 8.50€).
Source: Shotgun.live is the most reliable for FVTVR listings.

### Tokyo Waves @ Palais de Tokyo
Jen Cardini curates 5-date summer series (12, 18, 25 Jul / 22, 29 Aug, 17h-21h).
Artists: BASHKKA, upsammy, Beatrice M., Kim Ann Foxman, TTristana b2b RONI, Sensit1ve, Flore, Ehua, GLITTER55, Zaatar.
Ticket includes museum entry. Unique: electronic music in contemporary art context.
Source: RA.co news (ra.co/news/85543) — note that RA.co NEWS is accessible even though RA.co EVENTS is blocked.

### Arash Nassiri: Night Mode
Sound art / installation at Fondation Pernod Ricard until 18 July 2026.
Source: Fondation Pernod Ricard official site, Art Flaneur.

### Less Drama More Techno — 11th Season at Nouveau Casino
Aug 29, 23h55-06h00. Ben Hille, Petite Mort, Ben Manson.
Source: Queer Paris (queer.paris), Shotgun.live.

### Other Venues Confirmed Active
- **La Rotonde Stalingrad** (75010): Mez (Jul 11), Tamada (Jul 30), Groovebox (Aug 1)
- **Supersonic** (75011): Lacross Club (Aug 8), Going Forward + Altitude + Ellside (Aug 15)
- **Anna Lunoe & Monaco @ Sacré** (Aug 8)
- **22:22 & Christie @ Virage** (Jul 29)
- **OHLALA Summer Festival** at Le Kilowatt (Vitry-sur-Seine)

### Source Status Update (July 2026)
- **Lylo**: HTTP 503 this session — intermittent, worth retrying next week
- **RA.co news** works for announcements even though RA.co events is blocked
- **Kilomètre25 direct site** works well via MCP reader for summer programming
- **Shotgun.live** remains the most reliable aggregator for club events
- **Shazam venue pages** confirmed useful for quick date/artist lookup
- **Bandsintown** has good venue data (Nouveau Casino, etc.)

### Discord Delivery Blocker
The `.env` file exists in the project directory but contains no `DISCORD_WEBHOOK_URL`.
`execute_code` is blocked in cron mode (approvals.cron_mode prevents arbitrary Python).
Future sessions: check if the webhook URL is set in the Hermes cron job config
(`~/.hermes/hermes-agent/cron/jobs.json`) rather than in the project `.env`.
If no webhook is configured, the Discord delivery step should be cancelled with a note.

### Source List Staleness
The original source list in `music_sources.txt` has multiple dead entries:
- Les Tanneries → vacation rental (confirmed dead)
- ParisMix, PAP, Les Arts Décoratifs, Cent Quatre → HTTP 422 (confirmed dead via MCP)
- La Fabrique, Le 106 → HTTP 422 (confirmed dead via MCP)
- Graindor → HTTP 422 (confirmed dead this session, was 400 before)
**Recommendation**: Clean up `music_sources.txt` to remove dead sources and add active ones (FVTVR via Shotgun, Kilomètre25, Nouveau Casino).

---

*This reference captures concrete source inventory, access methods, technical details, and event discoveries from research sessions through August 2026.*

---

## Session: 22 August 2026

### Summary
Full weekly report + Discord summary delivered. August ending light on experimental (EtherREAL mostly exhibitions). September packed: PRÉSENCES électronique, Sonic Temple vol.8, Techno Parade return after 2 years, FIP 360 @ Monnaie de Paris, Paris Electronic Week, Outsiders Festival. Kilomètre25 open-air series extends through September. Lylo strong (53 electro concerts). Shotgun experimental page excellent for underground events. Added DICE data via web search.

### Source Status
- **EtherREAL**: ✅ Works but August music sparse — mostly exhibitions (Clair-Obscur). Free improv events at Chair de Poule (22-23, 28 Aug: Sir Richard Bishop).
- **Lylo**: ✅ Works. 53 electro concerts listed. Full pricing/dates for Wolfgan Voigt Gas, Nathan Fake, Lamb, Folamour, Apparat, etc.
- **IRCAM**: ✅ Works. Traversées du Marais (5 Sep, free), Patrimoine tours (19 Sep), Déambulations sonores (until 20 Sep).
- **Shotgun.live/techno**: ✅ Works. FVTVR, K25, La Gare, Mia Mao, La Rotonde all present with full listings.
- **Shotgun.live/experimental**: ✅ Excellent — became #2 source this session. Ron Morelli (L.I.E.S), Automatic (sold out), Pays P., Dürüm Records, Æsthesis.
- **Kilomètre25 direct** (`kilometre25.fr/agenda`): ✅ Works — full Sep open-air schedule with specific events and prices.
- **RA.co, HTTP 422 sources**: still dead, do not retry.

### New/Confirmed Events This Session
- **Musica 2026 — PRÉSENCES électronique**: Wed 23 Sep, Église St-Paul (€6-18). INA GRM Acousmonium: Jim O'Rourke, Jessica Ekomane, Maria W Horn, Philippe Gordiani, Eve Aboulkheir, François J. Bonnet.
- **Musica 2026 — Sonic Temple vol.8**: Thu 24 Sep, Église St-Paul (€6-13). Claire Rousay (world premiere 0 Intent 2026), Aho Ssan (Black Nectar French premiere), Mica Levi (Smoker 2026), Laurie Spiegel (The Expanding Universe 1980). ensemble 0 percussion.
- **Musica 2026 — Stitch 'n' Bitch**: Fri 25 Sep, 23:00, Karmen Camina: YARD, Zoë Mc Pherson, Lullahush, ELLLL, SARC, a~a~r~d~e~n~t.
- **Musica 2026 — Irish Rising**: Fri 25 Sep, Église St-Paul: Crash Ensemble + Michael Gallen.
- **Techno Parade 2026**: Confirmed 19 Sep, returns after 2-year hiatus. Free. Bastille→République route. ~400K expected.
- **FIP 360 @ Monnaie de Paris**: Tue 8 Sep, 18:30-midnight. Chloé (DJ set) + Kangding Ray (360° live) + Abs8lute. €22-28. L-ISA spatialized sound. Tickets via Shotgun.
- **Paris Electronic Week 2026**: 30 Sep-4 Oct. Point Éphémère (free opening night), La Station (Thu), Petit Bain (Fri), Mains d'Œuvres (convention + Sat). Kluster, Harey Izé, Jay Ahern, Pizza Noise Mafia, Hors Sol.
- **Outsiders Festival**: 25-26 Sep, Supersonic Records. Momus, Black Box Recorder, Perio, Scott McCloud.
- **Échelle Humaine Festival**: 17-20 Sep, Lafayette Anticipations. Tai Shani (M.I.A.S.M.A.), Catol Teixeira, Boglárka Börcsök.
- **Ron Morelli (L.I.E.S) + Lussuria + Siink + Electric Doom Synthesis**: 13 Sep, Le Zéralda (€12.10). Industrial/ambient/noise.
- **Pays P. + Helma + Margarita**: 11 Sep, Le Chinois (€5 solidarity). Pays P. reform after 4-year hiatus.
- **Automatic (US) @ Le Chinois**: 1 Sep. SOLD OUT. LA synth post-punk. Waiting list open.
- **Dürüm Records Release Party**: 4 Sep, Bal Chavaux (€10.99). Meli Mena EP. IDM/Bass/Techno.
- **Lolo & Sosaku @ Festival d'Automne**: 22 Oct, Gaîté Lyrique (€8-25). Extreme noise machine-art. World premiere.
- **Nosferatu Ciné-Concert (Erpan Hesher)**: 9 Oct, Médiathèque Musicale. FREE. Modular synthesis live score.
- **Holy Fuck**: 26 Sep, Badaboum (€20.40). Canadian electronic rock.
- **Tara Clerkin Trio**: 5 Sep, La Station — Gare des Mines (€16.54).
- **Ondes Plurielles**: 26 Sep, Église Saint-Marcel. Classical-electronic fusion in church acoustics.
- **Sir Richard Bishop (Sun City Girls)**: 28 Aug, Chair de Poule, Paris. Free improv.
- **Accident Theory Open Air @ K25**: Late Sep: Young Marco (Dekmantel), Bambounou (50Weapons), Axel Blanc, Vanroose, secret guest (from €8).
- **ARTBAT @ Château de Fontainebleau**: 12 Sep, 19:00-02:00. Ukrainian duo. Electro in historic monument.

### Kilomètre25 Confirmed Sep Open-Air Schedule
- 3 Sep: 2222 (Juan Evangelista, DDK, Charlotte Newman, Kama) — last Thursday open air, from €12
- Sep: Cookie Records (Sophie Lloyd, Kabylie Minogue, Un*Deux) — from €8
- Sep: 2much (Linds, Andata, Emilja) — from €8
- Sep: Organïk (Anxhela, Blnk, Lolalita) + Organïk Extended (Igda, Jo3y3t, Kirsty, Vido) — from €8
- Sep: Øxyl (Charlie Sparks, Durdenhauer, Barbara Lago, SZG) — Techno & Trance, from €8
- Sep: Pygments (Airod, Angèle Cressin, Terminal Trax) — Techno, from €8
- Sep: 23:59 (Eargasm God, DBBD, Paralich, Area Øne) — Hard Techno, from €8
- Late Sep: Accident Theory (Young Marco, Bambounou, Axel Blanc, Vanroose, secret guest) — from €8

### Notes
- August ending light; Sep-Oct is stacked with festivals and major concerts.
- Shotgun experimental page now a go-to source for underground events.
- DICE MCP provides useful data but wasn't directly loaded this session (data came via web search).
- Lylo remains the best primary aggregator for electro concert info.
- Kilomètre25 is the premier underground club/open-air venue for hard techno/hardcore/gabber in Paris.

---

## Session: 15 August 2026

### Summary
Produced full weekly report + Discord summary. Sources live: EtherREAL (agenda mostly exhibitions Aug — music sparse), Lylo (works, 52 electro concerts), IRCAM (works). Shotgun electro hit Vercel security checkpoint this session (techno still fine). Kilomètre25 direct agenda works fully (open-air series detail).

### Source Status
- **EtherREAL**: ✅ Works but August agenda dominated by exhibitions (Clair-Obscur, Calder). Rare music.
- **Lylo**: ✅ Works. Full electro listing with prices/dates.
- **IRCAM**: ✅ Works via Jina. Les Traversées du Marais 5 Sep confirmed.
- **Shotgun.live techno**: ✅ Works. electro: ❌ Vercel checkpoint 15 Aug — retry next session.
- **Kilomètre25 direct** (`kilometre25.fr/agenda`): ✅ Works, full open-air programming (House/Hard Trance/Hardcore/Gabber/Techno).
- **RA.co, HTTP 422 sources**: still dead, do not retry.

### New/Confirmed Events
- **Mount Kimbie + Tour-Maubourg + Astels + Mely + Cabaret Contemporain** — Sat 29 Aug, Virage (26 rue Hélène Missoffe, 75017), 17:00-23:00, €20. "Marathon" night. Confirmed via Shotgun/Bandsintown/Songkick/Spotify.
- **Chris Liebing & Sept** — Fri 28 Aug, FVTVR. Confirmed.
- **Techno Parade 2026 RETURNS 19 Sep** — after 2-year hiatus (parisjetaime.com). Major free parade.
- **Laurent Garnier takes over as Rex Club manager from Sep 2026.**
- **Lamb** — 2 Sep, Pop Up du Label, Paris 12e (24.60€).
- **Folamour @ Cabaret Sauvage** — 5 Sep, 45€.
- **THE OLLLAM** — 1 Oct, Le Bal Chavaux, Montreuil (30.10€).
- **Parra For Cuva@La Cigale** — 2 Oct (40€).
- **La P'tite Fumée@La Cigale** — 23 Oct.
- **Lane 8 @ Le Badaboum** — 28 Oct (sold out).

### Notes
- August is light season for Paris experimental (venues thin). Focus shifts to Sep-Oct bookings.
- Virage venue = 26 rue Hélène et François Missoffe, 75017 (near Porte Maillot).

---

## Session: 18 July 2026

### Summary
Produced full weekly report + Discord summary. Lylo back online (was 503 last session). Major discoveries: Mount Kimbie @ Virage (29 Aug), Wolfgang Voigt Gas Live confirmed for 23 Sep (not May), Nathan Fake AV Live 26 Sep, Autechre @ Bataclan 14 Oct (sold out). Added Songkick as reliable secondary for August+ listings.

### Source Status
- **Lylo**: ⚠️ Intermittent — worked this session after 503 last time. Always retry.
- **EtherREAL**: ✅ Works. Date param `?rubrique10&date=YYYY-MM-DD` for pagination.
- **RA.co**: ❌ Permanently blocked (DataDome). Do not retry.
- **Songkick**: ✅ Good — best for future months (August+). Syncs with Ticketmaster.
- **IRCAM**: ⚠️ Cookie wall but MCP reader returns enough content.
- **All HTTP 422/400 sources**: Confirmed dead again. Do not retry.

### New Events Added
- Mount Kimbie + Tour-Maubourg + Cabaret Contemporain (29 Aug, Virage) ⭐
- Nathan Fake AV Live (26 Sep, Gaîté Lyrique) ⭐
- Apparat (9 Oct, Élysée Montmartre)
- Autechre (14 Oct, Bataclan — sold out)
- Tommy Four Seven (7 Aug, FVTVR)
- Chris Liebing & Sept (28 Aug, FVTVR)
- The Avalanches (8 Aug, Silencio)
- The Whitest Boy Alive (31 Aug, Cabaret Sauvage)

### Data Correction
- **Wolfgang Voigt presents Gas Live**: Date corrected from May to **23 September 2026** at Gaîté Lyrique. Sprint-like event discovery from Lylo confirmed this.
