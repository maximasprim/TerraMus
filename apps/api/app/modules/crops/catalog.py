"""Reference catalog of supported crop types - the plant-production mirror of
livestock/catalog.py. New crop types are added here only; `schemas.py`
derives its validation from `CROP_TYPE_CODES`, and the platform-admin
reference endpoints (and tenant catalog visibility settings, see the
`catalog` module) read from this same list.

Selection targets crop enterprises that do well in the Kenyan market:
fodder (for on-farm livestock feed), the classic export/cash "bearing"
tree/perennial crops (tea, coffee, avocado, macadamia, mango, banana,
passion fruit), horticulture/export vegetables, staple cereals, legumes,
root & tuber crops, and cut flowers.
"""

CROP_CATEGORIES = ("fodder", "cash_crop", "horticulture", "cereal", "legume", "root_tuber", "flower")

# (code, display_label, category, is_perennial, typical_yield_unit)
# is_perennial marks "bearing plants" - tea, avocado, coffee, etc. - that are
# planted once and harvested repeatedly over years, as opposed to an annual
# crop that is planted and harvested once per season.
CROP_TYPES: list[tuple[str, str, str, bool, str]] = [
    # --- fodder (grown to feed livestock, not for direct sale) -----------
    ("napier_grass", "Napier Grass", "fodder", True, "kg"),
    ("rhodes_grass", "Rhodes Grass", "fodder", True, "bales"),
    ("lucerne", "Lucerne (Alfalfa)", "fodder", True, "kg"),
    ("desmodium", "Desmodium", "fodder", True, "kg"),
    ("boma_rhodes", "Boma Rhodes Grass", "fodder", True, "bales"),
    ("oat_hay", "Oat Hay", "fodder", False, "bales"),

    # --- cash / bearing (perennial tree & export cash crops) --------------
    ("tea", "Tea", "cash_crop", True, "kg"),
    ("coffee", "Coffee", "cash_crop", True, "kg"),
    ("avocado", "Avocado", "cash_crop", True, "kg"),
    ("macadamia", "Macadamia", "cash_crop", True, "kg"),
    ("mango", "Mango", "cash_crop", True, "kg"),
    ("banana", "Banana", "cash_crop", True, "bunches"),
    ("passion_fruit", "Passion Fruit", "cash_crop", True, "kg"),
    ("sugarcane", "Sugarcane", "cash_crop", False, "tonnes"),

    # --- horticulture (export & local-market vegetables) -------------------
    ("french_beans", "French Beans", "horticulture", False, "kg"),
    ("snow_peas", "Snow Peas", "horticulture", False, "kg"),
    ("tomatoes", "Tomatoes", "horticulture", False, "crates"),
    ("kale_sukuma_wiki", "Kale (Sukuma Wiki)", "horticulture", False, "kg"),
    ("onions", "Onions", "horticulture", False, "kg"),
    ("cabbage", "Cabbage", "horticulture", False, "kg"),
    ("capsicum", "Capsicum", "horticulture", False, "kg"),

    # --- cereals -------------------------------------------------------
    ("maize", "Maize", "cereal", False, "bags"),
    ("wheat", "Wheat", "cereal", False, "bags"),
    ("rice", "Rice", "cereal", False, "bags"),
    ("sorghum", "Sorghum", "cereal", False, "bags"),
    ("millet", "Millet", "cereal", False, "bags"),

    # --- legumes -------------------------------------------------------
    ("beans", "Beans (Common Beans)", "legume", False, "bags"),
    ("groundnuts", "Groundnuts", "legume", False, "bags"),
    ("soybeans", "Soybeans", "legume", False, "bags"),

    # --- roots & tubers --------------------------------------------------
    ("irish_potato", "Irish Potato", "root_tuber", False, "bags"),
    ("sweet_potato", "Sweet Potato", "root_tuber", False, "bags"),
    ("cassava", "Cassava", "root_tuber", False, "bags"),
    ("arrowroot", "Arrowroot", "root_tuber", False, "bags"),

    # --- flowers (major Kenyan export sector) -------------------------
    ("roses", "Roses", "flower", True, "stems"),
    ("other_cut_flowers", "Other Cut Flowers", "flower", True, "stems"),
]

CROP_TYPE_CODES: tuple[str, ...] = tuple(c[0] for c in CROP_TYPES)
CROP_TYPE_LOOKUP: dict[str, dict] = {
    code: {"label": label, "category": category, "is_perennial": is_perennial, "typical_yield_unit": unit}
    for code, label, category, is_perennial, unit in CROP_TYPES
}
