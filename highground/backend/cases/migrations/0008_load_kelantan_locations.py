"""Load Kelantan's controlled locations and link existing cases to them.

State and districts: OCHA P-codes and centre points from the HDX Malaysia
gazetteer (COD-AB v01, `mys_admin_boundaries.xlsx`, sheets mys_admin1/2 and
mys_adminpoints; CC BY-IGO), read on 23 Sep 2026.

Villages: a starter set for Pasir Mas and Kota Bharu. No official open list
exists below district, so each gets a project code extending its district's
P-code. Centre points are OpenStreetMap place nodes (© OpenStreetMap
contributors, ODbL), found through Nominatim on 23 Sep 2026; the node is noted
beside each row so it can be re-checked. Banggu had no village node, only the
hamlet "Kampung Surau Banggu", so it is marked approximate. More villages are
added through the admin, which issues the next code.

The rows are written out here rather than read from a file, so this migration
means the same thing every time it runs.
"""

from decimal import Decimal

from django.db import migrations

STATE = ("MY03", "Kelantan", "5.398030", "102.076559")

DISTRICTS = [
    ("MY0301", "Bachok", "6.021953", "102.373477"),
    ("MY0302", "Gua Musang", "4.974849", "101.971998"),
    ("MY0303", "Jeli", "5.577619", "101.818586"),
    ("MY0304", "Kota Bharu", "6.044814", "102.267973"),
    ("MY0305", "Kuala Krai", "5.425441", "102.175124"),
    ("MY0306", "Machang", "5.767481", "102.233688"),
    ("MY0307", "Pasir Mas", "6.017855", "102.066690"),
    ("MY0308", "Pasir Puteh", "5.838150", "102.407882"),
    ("MY0309", "Tanah Merah", "5.726456", "102.046400"),
    ("MY0310", "Tumpat", "6.165101", "102.166633"),
]

# (code, district code, name, lat, lng, source)
VILLAGES = [
    ("MY0307-V001", "MY0307", "Kampung Tendong", "6.070228", "102.209292", "osm"),  # node/3782968636
    ("MY0307-V002", "MY0307", "Rantau Panjang", "6.018119", "101.972820", "osm"),  # node/254073283
    ("MY0307-V003", "MY0307", "Meranti", "6.100037", "102.106141", "osm"),  # node/3294823122
    ("MY0307-V004", "MY0307", "Kampung Kangkong", "6.001099", "102.183921", "osm"),  # node/13641356368
    ("MY0307-V005", "MY0307", "Pasir Mas town", "6.041613", "102.142925", "osm"),  # node/369488104
    ("MY0307-V006", "MY0307", "Gual Periok", "6.025154", "102.026678", "osm"),  # node/254073300
    ("MY0307-V007", "MY0307", "Bunut Susu", "6.096257", "102.175953", "osm"),  # node/4590387592
    ("MY0304-V001", "MY0304", "Kubang Kerian", "6.094037", "102.284514", "osm"),  # node/369488298
    ("MY0304-V002", "MY0304", "Salor", "6.027927", "102.181562", "osm"),  # node/3294823128
    ("MY0304-V003", "MY0304", "Banggu", "6.062675", "102.324970", "approximate"),  # hamlet node/13672724243
    ("MY0304-V004", "MY0304", "Pengkalan Chepa", "6.172658", "102.293098", "osm"),  # node/254074445
    ("MY0304-V005", "MY0304", "Kadok", "5.994861", "102.245515", "osm"),  # node/8934948259
]


def _comparable(name):
    """Village names as households and older data wrote them, made comparable.

    "Kg. Tendong", "Kampung Tendong" and "Tendong" are the same place;
    "Pasir Mas town" and "Kampung Pasir Mas" both mean the town.
    """
    text = " ".join((name or "").lower().replace(".", " ").split())
    for prefix in ("kampung ", "kg "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.endswith(" town"):
        text = text[: -len(" town")]
    return text


def load(apps, schema_editor):
    LocationArea = apps.get_model("cases", "LocationArea")
    CaseRecord = apps.get_model("cases", "CaseRecord")

    code, name, lat, lng = STATE
    state = LocationArea.objects.create(
        code=code, name=name, level="state",
        latitude=Decimal(lat), longitude=Decimal(lng), centroid_source="official",
    )
    districts = {}
    for code, name, lat, lng in DISTRICTS:
        districts[code] = LocationArea.objects.create(
            code=code, name=name, level="district", parent=state,
            latitude=Decimal(lat), longitude=Decimal(lng), centroid_source="official",
        )
    villages = {}
    for code, district, name, lat, lng, source in VILLAGES:
        villages[_comparable(name)] = LocationArea.objects.create(
            code=code, name=name, level="village", parent=districts[district],
            latitude=Decimal(lat), longitude=Decimal(lng), centroid_source=source,
        )

    # Link what can be matched with confidence; anything else stays unlinked
    # and shows as unmapped rather than being guessed onto the wrong village.
    for case in CaseRecord.objects.filter(location_area__isnull=True).only("id", "village"):
        area = villages.get(_comparable(case.village))
        if area is not None:
            CaseRecord.objects.filter(pk=case.pk).update(location_area=area)


def unload(apps, schema_editor):
    LocationArea = apps.get_model("cases", "LocationArea")
    CaseRecord = apps.get_model("cases", "CaseRecord")
    CaseRecord.objects.update(location_area=None)
    for level in ("village", "district", "state"):
        LocationArea.objects.filter(level=level).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0007_locationarea_caserecord_location_area"),
    ]

    operations = [
        migrations.RunPython(load, unload),
    ]
