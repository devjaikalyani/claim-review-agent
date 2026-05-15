"""
Seed training DB with 10 real expense vouchers.
Run from the project root:  python scripts/seed_vouchers.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.training_db import save_voucher_decisions


def _item(desc, claimed, approved):
    return {"expense_head": desc, "claimed_amount": claimed, "amount": approved}


VOUCHERS = [

    # â”€â”€ Voucher 2607 â€” Kartik Dhobale, Dec 2025 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "2607",
        "categories": {
            "two_wheeler": {"items": [
                _item("1-Dec-25: vaijapur jategaon devgaon shani virgaon sites live",           336,  300),
                _item("2-Dec-25: vaijapur to sirsala scheme nanegaon janjala pangri sites live", 990,  900),
                _item("3-Dec-25: vaijapur to agar saigaon aghur bhhgaon sites live",            192,  150),
                _item("4-Dec-25: vaijapur to sirasgaon chorwaghalgaon shivrai parsoda sites",   267,  200),
                _item("8-Dec-25: vaijapur jambargaon mali ghoghargaon",                          51,   51),
                _item("9-Dec-25: vaijapur to ragunathpurwadi sudamwadi jarul sites live",       402,  350),
                _item("10-Dec-25: vaijapur to sakegaon pokhari babhulgaon kh bk sites live",   357,  300),
                _item("11-Dec-25: vaijapur to sirasgaon jambargaon sivrai sites live",         144,   44),
                _item("12-Dec-25: vaijapur to jategaon mahalgaon warkhed sites live",          186,  186),
                _item("13-Dec-25: vaijapur to aghur bhhgaon dawala sites live",                273,  250),
                _item("15-Dec-25: vaijapur to aurangabad jalna",                               822,  800),
                _item("16-Dec-25: vaijapur to babhulgaon kh garaj bahegaon gaga sites live",  252,  252),
                _item("17-Dec-25: vaijapur to loni bk bhivgaon sanjaypurwadi sites live",     240,    0),
                _item("18-Dec-25: vaijapur to sirsala sirsala tanda nanegaon janjala pangri", 1089, 1000),
                _item("19-Dec-25: vaijapur to mahalgaon warkhed mali ghoghargaon jabrgaon",   312,  300),
                _item("20-Dec-25: vaijapur to karajgaon hadas pipalgaon lasurgaon sawngi",    288,  200),
                _item("22-Dec-25: vaijapur to ch sambhaji nagar balapur zalta bakapur sites", 471,  350),
                _item("23-Dec-25: abdlmadi davlatabad kesapuri kesapuri tanda sites",         414,  350),
                _item("24-Dec-25: jarul narala khdalala aghur sites live",                    333,  300),
                _item("25-Dec-25: raypur babhulgaon palsad lasurgaon sites live",             411,  350),
                _item("26-Dec-25: sirasgaon chorwaghalgaon jambargaon sites live",            162,  162),
                _item("27-Dec-25: sudamwadi ragunadwadi belgaon sites live",                  345,  300),
                _item("29-Dec-25: goyegaon dawala jarul sites live",                         186,  186),
                _item("30-Dec-25: vaijapur ch sambhaji nagar silod",                         939,  939),
            ]},
            "other": {"items": [
                _item("19-Dec-25: mobile recharge",                         200,    200),
                _item("23-Dec-25: hotel stay",                             1300,   1000),
                _item("30-Dec-25: bag purchase",                            150,      0),
                _item("30-Dec-25: solid billing infection documents xerox", 240,    240),
                _item("31-Dec-25: hotel stay",                              680,    680),
                _item("31-Dec-25: 1-12-2025 to 31-12-2025 fooding expense",6000,  6000),
            ]},
            "bus_travel": {"items": [
                _item("30-Dec-25: aurangabad to belapur mumbai non AC bus", 1047, 1047),
                _item("31-Dec-25: yeola to vaijapur non AC bus",              51,   51),
                _item("31-Dec-25: mumbai to manmad sleeper class train",    1085, 1085),
            ]},
        },
    },

    # â”€â”€ Voucher 2098 â€” Vaibhav Puntambekar, Oct 2025 (full approval) â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "2098",
        "categories": {
            "bus_travel": {"items": [
                _item("8-Oct-25: 3 AC train",                                          40,   40),
                _item("9-Oct-25: 3 AC train",                                         130,  130),
                _item("9-Oct-25: autorickshaw fare for powertron",                    169,  169),
                _item("10-Oct-25: thane ZP autorickshaw fare cash paid",              110,  110),
                _item("14-Oct-25: 3 AC train",                                         15,   15),
                _item("27-Oct-25: 3 AC train",                                        130,  130),
                _item("27-Oct-25: autorickshaw fare for powertron",                   164,  164),
                _item("29-Oct-25: thane visit 3 AC train",                            130,  130),
                _item("29-Oct-25: autorickshaw fare JD finance home powertron 2 trips",292, 292),
                _item("29-Oct-25: autorickshaw fare in nerul cash paid",              230,  230),
                _item("30-Oct-25: HSBC visit 3 AC train",                             190,  190),
                _item("31-Oct-25: 3 AC train",                                         15,   15),
            ]},
            "other": {"items": [
                _item("9-Oct-25: belapur guesthouse electric bill september",          640,  640),
                _item("10-Oct-25: colour inks and A4 paper rim purchased for office", 3440, 3440),
                _item("15-Oct-25: colour printouts of IOT certificates",              3439, 3439),
                _item("16-Oct-25: colour and BW prints of IOT certificates",          6197, 6197),
                _item("30-Oct-25: A4 paper rim purchased for office",                  300,  300),
                _item("31-Oct-25: fooding expenses 250x21 days",                      5250, 5250),
            ]},
        },
    },

    # â”€â”€ Voucher 2126 â€” Jai Dutt Sharma, Oct-Nov 2025 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "2126",
        "categories": {
            "food": {"items": [
                _item("13-Oct-25: food allowance", 750, 750),
                _item("14-Oct-25: food allowance", 750, 750),
                _item("15-Oct-25: food allowance", 750, 750),
                _item("16-Oct-25: food allowance", 750, 750),
                _item("17-Oct-25: food allowance", 750, 750),
                _item("23-Oct-25: food allowance", 750, 750),
                _item("24-Oct-25: food allowance", 750, 750),
                _item("25-Oct-25: food allowance", 750, 750),
                _item("26-Oct-25: food allowance", 750, 750),
                _item("27-Oct-25: food allowance", 750, 750),
                _item("28-Oct-25: food allowance", 750, 750),
                _item("29-Oct-25: food allowance", 750, 750),
                _item("30-Oct-25: food allowance", 750, 750),
                _item("31-Oct-25: food allowance", 750, 750),
                _item("1-Nov-25: food allowance",  750, 750),
                _item("2-Nov-25: food allowance",  750, 750),
                _item("3-Nov-25: food allowance",  750, 750),
                _item("4-Nov-25: food allowance",  750, 750),
            ]},
            "other": {"items": [
                _item("15-Oct-25: local travel by shared auto",                    60,    60),
                _item("15-Oct-25: miscellaneous expense",                          82,    82),
                _item("16-Oct-25: local travel by shared auto",                    60,    60),
                _item("17-Oct-25: local travel by shared auto",                    40,    40),
                _item("17-Oct-25: hotel stay",                                   4200,  4000),
                _item("17-Oct-25: miscellaneous expense",                          66,    66),
                _item("17-Oct-25: miscellaneous expense",                         135,   135),
                _item("23-Oct-25: miscellaneous expense",                         107,   107),
                _item("23-Oct-25: miscellaneous expense",                          72,    72),
                _item("23-Oct-25: local travel by shared auto",                    40,    40),
                _item("24-Oct-25: local travel by shared auto",                    60,    60),
                _item("25-Oct-25: local travel by shared auto",                    60,    60),
                _item("26-Oct-25: local travel by shared auto",                    60,    60),
                _item("27-Oct-25: miscellaneous expense",                          38,    38),
                _item("27-Oct-25: local travel by shared auto",                    60,    60),
                _item("28-Oct-25: 3 days conference fees at IIT BHU",          15222, 15222),
                _item("28-Oct-25: local travel by shared auto",                    40,    40),
                _item("28-Oct-25: miscellaneous expense",                          29,    29),
                _item("28-Oct-25: miscellaneous expense",                          29,    29),
                _item("29-Oct-25: local travel by shared auto",                    60,    60),
                _item("1-Nov-25: miscellaneous expense",                           42,    42),
                _item("2-Nov-25: local travel by shared auto",                     40,    40),
                _item("3-Nov-25: local travel by shared auto",                     60,    60),
                _item("4-Nov-25: hotel stay varanasi BHU conference",          25200, 25200),
                _item("4-Nov-25: flex printing for BHU conference 3 days",     4920,  4920),
                _item("4-Nov-25: local travel by shared auto",                     60,    60),
            ]},
        },
    },

    # â”€â”€ Voucher 3122 â€” Arpit Pandit, Mar-Dec 2025 (FULL REJECTION) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "3122",
        "categories": {
            "bus_travel": {"items": [
                _item("22-Mar-25: nagpur to yavatmal 10 box parsal auto", 200, 0),
                _item("11-Dec-25: non AC bus ticket",                     213, 0),
                _item("11-Dec-25: bus ticket",                            198, 0),
            ]},
            "site_expenses": {"items": [
                _item("6-May-25: site expense no receipt",                 60, 0),
                _item("21-Jul-25: bill rejected not connected to bill copy",70, 0),
                _item("21-Oct-25: site expense no receipt",               250, 0),
            ]},
            "other": {"items": [
                _item("10-May-25: ferull transport by bus yavatmal to pusad",200, 0),
                _item("1-Oct-25: remaining payment 115 in cash",           315, 0),
            ]},
            "two_wheeler": {"items": [
                _item("30-May-25: 2 wheeler petrol no receipt",  396, 0),
                _item("26-Oct-25: 2 wheeler petrol no receipt",  693, 0),
                _item("26-Oct-25: 2 wheeler petrol no receipt",  240, 0),
            ]},
        },
    },

    # â”€â”€ Voucher 3410 â€” Sachin Patil, Mar 2026 (FULL REJECTION) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "3410",
        "categories": {
            "two_wheeler": {"items": [
                _item("2-Mar-26: petrol conveyance",   42, 0),
                _item("4-Mar-26: petrol conveyance",  117, 0),
                _item("5-Mar-26: petrol conveyance",   45, 0),
                _item("6-Mar-26: petrol conveyance",  132, 0),
                _item("7-Mar-26: petrol conveyance",   42, 0),
                _item("11-Mar-26: petrol conveyance", 129, 0),
                _item("12-Mar-26: petrol conveyance", 114, 0),
                _item("13-Mar-26: petrol conveyance", 207, 0),
                _item("14-Mar-26: petrol conveyance",  33, 0),
                _item("17-Mar-26: petrol conveyance", 351, 0),
                _item("18-Mar-26: petrol conveyance", 150, 0),
                _item("20-Mar-26: petrol conveyance", 240, 0),
                _item("23-Mar-26: petrol conveyance", 141, 0),
                _item("24-Mar-26: petrol conveyance", 177, 0),
                _item("25-Mar-26: petrol conveyance",  36, 0),
                _item("26-Mar-26: petrol conveyance", 300, 0),
                _item("27-Mar-26: petrol conveyance", 423, 0),
                _item("30-Mar-26: petrol conveyance",  75, 0),
            ]},
        },
    },

    # â”€â”€ Voucher 3315 â€” Jai Dutt Sharma, Feb-Mar 2026 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "3315",
        "categories": {
            "bus_travel": {"items": [
                _item("21-Feb-26: 2 AC train",  2000, 2000),
                _item("2-Mar-26: 2 AC train",   2000, 2000),
                _item("5-Mar-26: 2 AC train",   2000, 2000),
                _item("13-Mar-26: 2 AC train",  2000, 2000),
            ]},
            "food": {"items": [
                _item("9-Mar-26: food allowance",  750, 750),
                _item("10-Mar-26: food allowance", 750, 750),
                _item("11-Mar-26: food allowance", 750, 750),
                _item("12-Mar-26: food allowance", 750, 750),
                _item("13-Mar-26: food allowance", 750, 750),
            ]},
            "other": {"items": [
                _item("27-Feb-26: cruise booking varanasi BUDCO officials", 5000,  5000),
                _item("13-Mar-26: miscellaneous expense",                     62,    62),
                _item("13-Mar-26: miscellaneous expense",                    123,   123),
                _item("13-Mar-26: miscellaneous expense rejected",            62,     0),
                _item("13-Mar-26: hotel stay",                             15120, 15120),
                _item("15-Mar-26: miscellaneous expense",                    121,   121),
                _item("16-Mar-26: miscellaneous expense",                    160,   160),
            ]},
        },
    },

    # â”€â”€ Voucher 3071 â€” Kunal Sonawane, Feb 2026 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "3071",
        "categories": {
            "other": {"items": [
                _item("1-Feb-26: mobile recharge feb",                                      200,  200),
                _item("12-Feb-26: EMF display pickup hadgaon",                              200,  200),
                _item("13-Feb-26: axis display send nagpur by bus cash payment",            200,  200),
                _item("13-Feb-26: jalna to nanded general ticket",                           95,   95),
                _item("14-Feb-26: parsal pickup",                                           110,  110),
                _item("26-Feb-26: courier adept and mcom",                                  320,  320),
                _item("27-Feb-26: adept PT received",                                       170,  170),
                _item("27-Feb-26: pota bk solar plat",                                      500,  500),
                _item("28-Feb-26: feb month fooding",                                      6000, 6000),
            ]},
            "two_wheeler": {"items": [
                _item("2-Feb-26: unchada koli newarwadi site live",                         198,  198),
                _item("3-Feb-26: nanded pick pcb tamsa warehouse materials check",         402,  402),
                _item("4-Feb-26: hardaf umri daryabai ghogri site fota update",            228,  228),
                _item("5-Feb-26: khrbi umri hadsani loha site offline online",             279,  279),
                _item("6-Feb-26: talegaon talang baradshewala site live",                  198,  198),
                _item("7-Feb-26: mahatala dhanora hastara rui shivanai site fota update",  303,  303),
                _item("9-Feb-26: tamsa police station",                                    120,  120),
                _item("10-Feb-26: tamsa police station",                                   186,  186),
                _item("11-Feb-26: letter inword MJP nanded",                               417,  417),
                _item("12-Feb-26: tamsa police station",                                   195,  195),
                _item("13-Feb-26: sillod tour hadgaon to nanded railway station",         396,  396),
                _item("14-Feb-26: search 183 grid warehouse MBR list hadgaon himayatnagar",432, 432),
                _item("16-Feb-26: borgaon hastara kohli umri kh fota update",             270,  270),
                _item("17-Feb-26: manjram scheme osmannagar scheme site live",             693,  693),
                _item("18-Feb-26: searching warehouse in ardhapur",                        351,  351),
                _item("19-Feb-26: malzara pangri manatha bamni fota update",               297,  297),
                _item("20-Feb-26: sirphali potabk pota kh site fota update",              366,  366),
                _item("21-Feb-26: nanded",                                                 423,  423),
                _item("23-Feb-26: bhokar ardhapur nanded warehouse searching",            420,  420),
                _item("24-Feb-26: ardhapur nanded warehouse searching",                   474,  474),
                _item("25-Feb-26: nanded warehouse owner meeting",                         549,  549),
                _item("26-Feb-26: koli mahatala site live",                               144,  144),
                _item("27-Feb-26: nanded warehouse aggrement notri",                      270,  270),
            ]},
            "bus_travel": {"items": [
                _item("13-Feb-26: sillod tour nanded to manmad sleeper class train",       810,  810),
            ]},
            "site_expenses": {"items": [
                _item("6-Feb-26: pebbles at talegaon site",                                300,  300),
                _item("7-Feb-26: 10 sites battery welding",                              5000,    0),  # rejected
                _item("18-Feb-26: 10 sites battery welding hadgaon himayatnagar scheme", 5000,    0),  # rejected
                _item("27-Feb-26: 550 bond 400 bond typing 500 notri register total 1450",1450, 1450),
                _item("28-Feb-26: 14 sites battery welding",                             7000,    0),  # rejected
            ]},
        },
    },

    # â”€â”€ Voucher 3383 â€” Kunal Sonawane, Mar 2026 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "3383",
        "categories": {
            "two_wheeler": {"items": [
                _item("20-Mar-26: nanded search new guesthouse",                           378,  378),
                _item("21-Mar-26: ardhapur warehouse materials unloading",                 330,  330),
                _item("22-Mar-26: ardhapur warehouse materials unloading",                 333,  330),
                _item("23-Mar-26: ardhapur warehouse EMF arrange serial number wise",      396,  396),
                _item("24-Mar-26: ardhapur warehouse material unloading shiradon site",    615,  300),
                _item("25-Mar-26: ardhapur warehouse nanded",                              261,  261),
                _item("26-Mar-26: ardhapur warehouse hadgaon",                             216,  216),
                _item("27-Mar-26: nanded ardhapur warehouse materials inspection",         492,  492),
                _item("28-Mar-26: ardhapur warehouse 284 powertron box unloading",        345,  345),
                _item("30-Mar-26: ardhapur warehouse materials arrange nanded visit EE",  420,  420),
                _item("31-Mar-26: ardhapur warehouse battery unloading",                  360,  360),
            ]},
            "other": {"items": [
                _item("21-Mar-26: SBEM EMF unloading 900MM 2 labour payment",            3500, 3500),
                _item("22-Mar-26: nagpur materials vehicle SBEM EMF unloading labour",   5500,    0),  # rejected
                _item("24-Mar-26: lebour payment",                                       2500,    0),  # rejected
                _item("25-Mar-26: lebour payment",                                       3300,    0),  # rejected
                _item("25-Mar-26: MJP executive dinner after inspection",                 930,  930),
                _item("26-Mar-26: lebour payment",                                       2000,    0),  # rejected
                _item("27-Mar-26: lebour payment",                                        400,  400),
                _item("28-Mar-26: lebour payment",                                       2000,    0),  # rejected
                _item("30-Mar-26: lebour cash payment",                                  1600,    0),  # rejected
                _item("31-Mar-26: 15 days fooding",                                      3000, 3000),
                _item("31-Mar-26: 845 battery unloading",                                5000,    0),  # rejected
            ]},
        },
    },

    # â”€â”€ Voucher 2955 â€” Mithun Jibhkate, Dec 2025-Feb 2026 (full approval) â”€â”€â”€â”€
    {
        "voucher_no": "2955",
        "categories": {
            "bus_travel": {"items": [
                _item("30-Dec-25: traveling by bus dokesarsndi to nilaj share auto",  105,  105),
                _item("30-Dec-25: traveling by bus nilaj to mul non AC bus",           180,  180),
                _item("30-Dec-25: traveling by bus mul to gadchiroli non AC bus",      130,  130),
                _item("31-Dec-25: traveling by bus gadchiroli to mul non AC bus",      130,  130),
                _item("31-Dec-25: traveling by bus mul to nagbhid non AC bus",         130,  130),
                _item("31-Dec-25: traveling by bus nagbhid to pauni non AC bus",       100,  100),
                _item("31-Dec-25: traveling by bus pauni to dokesarsndi non AC bus",    70,   70),
                _item("1-Jan-26: traveling by bus nilaj to mul non AC bus",            170,  170),
                _item("1-Jan-26: traveling by bus dokesarsndi to nilaj non AC bus",    130,  130),
                _item("5-Jan-26: traveling by bus dokesarsndi to nilaj non AC bus",   160,  160),
                _item("5-Jan-26: traveling by bus nilaj to mul non AC bus",            189,  189),
                _item("7-Jan-26: traveling by bus dokesarsndi to nagpur non AC bus",  250,  250),
                _item("8-Jan-26: traveling by bus nagpur to dokesarsndi non AC bus",  250,  250),
                _item("9-Jan-26: traveling by bus dokesarsndi to pauni non AC bus",    70,   70),
                _item("9-Jan-26: traveling by bus pauni to bhandara non AC bus",       91,   91),
                _item("9-Jan-26: traveling by bus bhandara to ramtek non AC bus",      91,   91),
                _item("9-Jan-26: traveling by bus nagpur bus stand to dokesarsndi",   250,  250),
                _item("16-Jan-26: traveling by bus dokesarsndi to nagpur non AC bus", 250,  250),
                _item("16-Jan-26: traveling by bus nagpur to yavatmal non AC bus",    252,  252),
                _item("16-Jan-26: traveling by bus kalamb to nagpur non AC bus",      212,  212),
                _item("17-Jan-26: traveling by bus nagpur to dokesarsndi non AC bus", 250,  250),
                _item("19-Jan-26: traveling by bus dokesarsndi to nagpur non AC bus", 250,  250),
                _item("19-Jan-26: traveling by bus nagpur to yavatmal non AC bus",    250,  250),
                _item("24-Jan-26: traveling by bus yavatmal to nagpur non AC bus",    250,  250),
                _item("24-Jan-26: traveling by bus nagpur to dokesarsndi non AC bus", 250,  250),
                _item("28-Jan-26: traveling by bus dokesarsndi to nagpur non AC bus", 250,  250),
                _item("2-Feb-26: traveling by bus nagpur to karanja non AC bus",      252,  252),
                _item("2-Feb-26: traveling by auto karanja bus stand to substation",   70,   70),
                _item("2-Feb-26: traveling by auto karanja substation to busstand",    70,   70),
                _item("2-Feb-26: travelling by bus karanja to nagpur non AC bus",     259,  259),
                _item("2-Feb-26: traveling by bus nagpur to dokesarsndi non AC bus",  250,  250),
                _item("4-Feb-26: traveling by bus lakhandur to bhiwapur non AC bus",  180,  180),
            ]},
            "food": {"items": [
                _item("30-Dec-25: fooding at gadchiroli", 400, 400),
                _item("31-Dec-25: fooding at mul",        400, 400),
                _item("1-Jan-26: fooding at yavatmal",    400, 400),
                _item("7-Jan-26: fooding at nagpur",      400, 400),
                _item("8-Jan-26: fooding at nagpur",      400, 400),
                _item("9-Jan-26: fooding at ramtek",      400, 400),
                _item("16-Jan-26: fooding at yavatmal",   400, 400),
                _item("16-Jan-26: fooding at nagpur",     400, 400),
                _item("19-Jan-26: fooding at yavatmal",   400, 400),
                _item("20-Jan-26: fooding at yavatmal",   400, 400),
                _item("21-Jan-26: fooding at yavatmal",   400, 400),
                _item("22-Jan-26: fooding at yavatmal",   400, 400),
                _item("23-Jan-26: fooding at yavatmal",   400, 400),
                _item("24-Jan-26: fooding at yavatmal",   400, 400),
                _item("28-Jan-26: fooding at yavatmal",   400, 400),
                _item("29-Jan-26: fooding at yavatmal",   400, 400),
                _item("31-Jan-26: fooding at yavatmal",   400, 400),
                _item("1-Feb-26: fooding at yavatmal",    400, 400),
                _item("2-Feb-26: fooding at nagpur",      400, 400),
            ]},
            "other": {"items": [
                _item("30-Dec-25: hotel stay at gadchiroli",      800,  800),
                _item("16-Jan-26: hotel stay at nagpur",          800,  800),
                _item("24-Jan-26: hotel stay at yavatmal 5 days",4000, 4000),
            ]},
            "two_wheeler": {"items": [
                _item("6-Jan-26: petrol expense towards sirsi substation",       480, 480),
                _item("14-Jan-26: petrol expense towards palandur substation",   186, 186),
                _item("15-Jan-26: petrol expense towards palora substation",     258, 258),
            ]},
        },
    },

    # â”€â”€ Voucher 2610 â€” Mithun Jibhkate, Nov-Dec 2025 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    {
        "voucher_no": "2610",
        "categories": {
            "two_wheeler": {"items": [
                _item("26-Nov-25: petrol expense towards masal SS",                    513,  513),
                _item("28-Nov-25: petrol expense towards lakhandur substation",        111,  111),
                _item("28-Nov-25: petrol expense towards lakhandur substation dup",   111,    0),  # duplicate rejected
                _item("15-Dec-25: petrol expenses towards barwha ss",                 180,  180),
                _item("16-Dec-25: petrol expense towards parsodi and lakhandur ss",    69,   69),
                _item("17-Dec-25: petrol expense towards wadsa material dispatch",    237,  237),
                _item("19-Dec-25: petrol expenses towards lakhandur substation",       90,   90),
                _item("20-Dec-25: petrol expense towards lakhori substation",         372,  372),
                _item("22-Dec-25: petrol expense towards lakhandur subdivision office",93,   93),
                _item("24-Dec-25: petrol expense towards chimur ss",                  447,  447),
                _item("28-Dec-25: petrol expense towards pauni for sim card",         150,  150),
            ]},
            "bus_travel": {"items": [
                _item("29-Nov-25: traveling by bus dokesarsndi to lakhandur non AC bus",  50,  50),
                _item("29-Nov-25: traveling by bus lakhandur to gadchiroli non AC bus",  150, 150),
                _item("29-Nov-25: traveling by bus gadchiroli to armori non AC bus",      70,  70),
                _item("29-Nov-25: traveling by bus armori to dokesarsndi non AC bus",    130, 130),
                _item("10-Dec-25: traveling by bus dokesarsndi to gadchiroli non AC bus",200, 200),
                _item("10-Dec-25: traveling by bus gadchiroli to dokesarsndi non AC bus",200, 200),
                _item("26-Dec-25: bus expense dokesarsndi to nilaj non AC bus",          100, 100),
                _item("26-Dec-25: traveling by bus nilaj to warora non AC bus",          152, 152),
                _item("27-Dec-25: traveling by bus warora to nilaj non AC bus",          160, 160),
                _item("27-Dec-25: traveling by bus nilaj to dokesarsndi non AC bus",     100, 100),
            ]},
            "food": {"items": [
                _item("1-Dec-25: fooding at allapalli",   400,  400),
                _item("1-Dec-25: fooding at allapalli dup",400,    0),  # duplicate rejected
                _item("2-Dec-25: fooding at mulchera",    400,  400),
                _item("2-Dec-25: fooding at mulchera dup",400,    0),   # duplicate rejected
                _item("3-Dec-25: fooding at ettapalli",   400,  400),
                _item("3-Dec-25: fooding at ettapalli dup",400,   0),   # duplicate rejected
                _item("4-Dec-25: fooding at rajora",      400,  400),
                _item("4-Dec-25: fooding at rajura dup",  400,    0),   # duplicate rejected
                _item("5-Dec-25: fooding at chandrapur",  400,  400),
                _item("5-Dec-25: fooding at chandrapur dup",400,  0),   # duplicate rejected
                _item("26-Dec-25: fooding at warora",     400,  400),
                _item("27-Dec-25: fooding at warora",     400,  400),
            ]},
            "site_expenses": {"items": [
                _item("9-Dec-25: car rent towards padmapur sindewahi walni substation", 6000, 6000),
                _item("9-Dec-25: car rent towards gatta pendhari substation",           5100, 5100),
                _item("23-Dec-25: car rent towards solar power plant substation",       5200, 5200),
            ]},
            "other": {"items": [
                _item("10-Dec-25: mobile recharge towards configuration work",  351,  351),
                _item("17-Dec-25: mobile recharge towards configuration work",  301,  301),
                _item("27-Dec-25: hotel stay 2 person at bhadrawati",          1500, 1500),
            ]},
        },
    },

]


if __name__ == "__main__":
    total_rows = 0
    for v in VOUCHERS:
        vno = v["voucher_no"]
        n = save_voucher_decisions(v, employee_code="")
        if n:
            print(f"  Voucher {vno}: inserted {n} rows")
            total_rows += n
        else:
            print(f"  Voucher {vno}: already exists â€” skipped")
    print(f"\nDone. {total_rows} new training rows added.")

