# SafeClock SOP (draft for faculty sign-off, R6)

How staff keep the one reserve vessel safe, and what the app does at each colour. The numbers are
constants in `app/rules/safeclock.py`: **60 °C, 2 h, 4 h, 30 min**.

## Staff steps

1. **Lid the reserve vessel** right after cooking, with a probe reading **above 60 °C** (plus the weight
   if a scale is handy). A lid reading at or below 60 °C is refused: reheat, then lid.
2. **Take a probe reading every 30 minutes** while the vessel is held (the app reminds you; a reading is
   overdue at 45 minutes).
3. A reading **at or below 60 °C** asks for a confirm tap (a typo would otherwise block the batch).
4. **At pickup:** take a final probe reading and weigh the vessel, then tap **Handover**.
5. The probe log is **append-only**: nobody can edit or delete a reading. A correction is a new reading
   with a note.

## The rule

- Readings are sorted by time. No reading at all -> **RED** ("no log, no offer").
- The **anchor** is the last reading above 60 °C before the first reading at or below 60 °C (or the
  latest reading if every reading is above 60 °C). If the very first reading was at or below 60 °C ->
  **RED**.
- Time since the anchor: **under 2 h = GREEN**, **2 h to under 4 h = AMBER**, **4 h or more = RED**.
- **Reheating after a cold reading does not restart the clock**, and the colour never improves.
- Boundaries: exactly 60.0 °C is *not* hot; exactly 2 h is AMBER; exactly 4 h is RED.

## What each colour allows

| Colour | Allowed |
|---|---|
| GREEN | May be offered to an NGO. Label: "Serve by HH:MM. If not served, refrigerate below 7 °C before HH:MM." |
| AMBER | No new offers. An already accepted batch may be handed over and served at once, never re-chilled. Label: "SERVE AT ONCE, by HH:MM. Do not refrigerate." |
| RED | "Food for Disposal": route to biogas or compost (landfill only with a reason). Never handed over. |

Label times: **refrigerate by = anchor + 2 h**, **latest serving time (consume by) = anchor + 4 h**.

Example: readings 11:45 72 °C, 12:15 68 °C, 12:45 58 °C, 13:15 75 °C -> anchor 12:15 -> GREEN until
14:15, AMBER until 16:15, then RED.

The batch record is "A record, not a safety certificate."
