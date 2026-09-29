"""Reference catalog of supported livestock species (spec §11 - "extensible").

This is deliberately the ONE place new species get added. `schemas.py` derives
its validation pattern from `SPECIES_CODES` below, so adding a row here is
enough to make a species creatable via the API - no regex to hunt down
elsewhere. `breeding/service.py`'s CATEGORY_BY_SPECIES and `catalog` module's
platform-admin reference endpoints also read from this list.

Selection is centered on livestock that do well in the Kenyan smallholder and
commercial market: cattle and sheep were already supported; goats, pigs,
rabbits, and poultry are added here as the next tier of common enterprises,
plus camels and donkeys for arid/pastoral and draught-animal contexts. This
list is additive only - "cattle" and "sheep" keep their exact original codes,
so no existing data/queries change.
"""

# (code, display_label, suggested_category_values, typical_female_role, typical_male_role)
# `suggested_category_values` is advisory only (surfaced to the frontend for
# dropdowns) - the `category` column on Animal remains a free-text field, so
# this list can grow without a migration.
LIVESTOCK_SPECIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("cattle", "Cattle", ("calf", "heifer", "steer", "cow", "bull", "dairy", "beef")),
    ("sheep", "Sheep", ("lamb", "ewe", "ram")),
    ("goat", "Goat", ("kid", "doe", "buck", "dairy", "meat")),
    ("pig", "Pig", ("piglet", "gilt", "sow", "boar")),
    ("rabbit", "Rabbit", ("kit", "doe", "buck")),
    ("poultry", "Poultry (Chicken)", ("chick", "pullet", "layer", "broiler", "cockerel", "indigenous")),
    ("camel", "Camel", ("calf", "cow", "bull")),
    ("donkey", "Donkey", ("foal", "jenny", "jack")),
]

SPECIES_CODES: tuple[str, ...] = tuple(code for code, _, _ in LIVESTOCK_SPECIES)
SPECIES_LOOKUP: dict[str, dict] = {
    code: {"label": label, "suggested_categories": list(categories)}
    for code, label, categories in LIVESTOCK_SPECIES
}
