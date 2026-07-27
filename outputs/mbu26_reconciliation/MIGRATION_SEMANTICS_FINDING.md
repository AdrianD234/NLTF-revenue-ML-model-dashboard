# Migration semantics: a double-counting risk, not an EV-uptake difference

## The finding

The AR(1) PED dependent variable is **petrol-only VKT per capita**. Verified
against the committed history:

```
max | target  -  light_petrol_vkt_total_km / population |  =  0.0
```

Exactly zero across every observation. The historical target is
`light_petrol_vkt_total_km / population`, so it **already embodies whatever
EV/PHEV substitution occurred historically**. The model forecasts petrol
travel per capita directly, not all-light travel.

The production bridge then applies an **additional** prospective EV/PHEV
migration factor on top of that forecast, falling to 0.918 by FY2030.

MBU26's `light_petrol_vkt` and `ped_vkt_per_capita` are the same petrol-only
definition, which is precisely why its implied migration factor is 1: MBU26
does not apply a second migration layer.

## Why this changes the interpretation

The −$219.85m FY2030 term is **not** evidence that the current model assumes
faster EV uptake than MBU26. It is the mechanical effect of applying a
migration adjustment to a series that is already petrol-only, where the
comparator does not.

Of the three interpretations in the brief, the evidence points to **(2)**: both
VKT-per-capita series are post-migration petrol VKT, so the additional
migration layer risks double counting.

That is a candidate structural defect in the bridge, not a difference of view
about electrification.

## What is not yet established

Whether the migration layer is *documented* as incremental uptake beyond the
historical trend. If it is, the design may be deliberate and the double count
only apparent. If it is not, petrol travel is being removed twice.

This requires reading the migration layer's own contract, which is beyond the
bounded scope of Phase A2 and is recorded here as the open question.

## Correct labelling until resolved

The term must be described as:

> current explicit migration adjustment relative to the official
> output-implied baseline

with status `conditional_on_official_migration_normalisation_not_observed`.

It must **not** be described as a difference in EV uptake between the current
model and MBU26. The repository supports only that the current explicit factor
is 0.918 at FY2030; no independently observed MBU26 migration factor exists.

## Correction history

An earlier pass reported "population explains 44% of the FY2030 gap". That was
wrong: population had been derived by inverting light-petrol VKT, folding
migration into it. The identified quantity is the **composite**
population-and-migration effect of approximately −$246.45m. Its split into
−$26.6m population and −$219.8m migration is **conditional** on normalising the
official migration factor to 1, which is a decomposition choice, not an
observation.
