# EtherREAL Venue Shorthand Decoder

EtherREAL (https://www.etherreal.com/spip.php?rubrique10=) uses abbreviated location
tags in its agenda. These are NOT always the venue name — they're neighbourhood or
district labels. When the Paris music research cron output shows a location in
parentheses as `(Tag, City)`, use this table to resolve the actual venue:

| EtherREAL tag        | Actual venue / location                                              |
|----------------------|----------------------------------------------------------------------|
| (Belles, Paris)      | Palais de Tokyo / Musée d'Art Moderne de la Ville de Paris (16e).    |
|                      | "Belles" refers to the Avenue des Belles-Feuilles neighbourhood.     |
| (Instants Chavirés, Montreuil) | The venue name IS Instants Chavirés — no disambiguation needed. |
| (Le 104, Paris)      | CENTQUATRE-Paris — major experimental/contemporary venue (19e).      |
| (Chinois, Montreuil) | Le Chinois — underground electronic venue in Montreuil.              |
| (Chair de Poule, Paris) | Chair de Poule — experimental/underground venue.                  |
| (Bourse de Commerce, Paris) | Bourse de Commerce — Pinault Collection (1er).                   |

## Multi-date listings

Recurring events (e.g. "Clair-Obscur" at Bourse de Commerce, a visual art
exhibition running Mar 4–Aug 24, 2026) appear on every relevant date in
EtherREAL's agenda. The cron report can list them per-day as EtherREAL does,
but the summary should clarify it's a run-of-show exhibition rather than
separate daily events.
