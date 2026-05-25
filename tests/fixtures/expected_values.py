from __future__ import annotations

EXPECTED_FINALIST_MAPE = {
    ("PED VKT per capita", "Quarterly MAPE"): 2.473245,
    ("PED VKT per capita", "Annual MAPE"): 2.385625,
    ("Light RUC volume", "Quarterly MAPE"): 9.147545,
    ("Light RUC volume", "Annual MAPE"): 5.999499,
    ("Heavy RUC volume", "Quarterly MAPE"): 3.484368,
    ("Heavy RUC volume", "Annual MAPE"): 3.019980,
}

EXPECTED_ENSEMBLE_WEIGHT_PCT = {
    "PED VKT per capita": [100.0],
    "Light RUC volume": [33.3333395, 33.3333312, 33.3333293],
    "Heavy RUC volume": [46.9332, 28.1844, 14.4373, 10.4451],
}

EXPECTED_STRESS_MAPE = {
    ("PED VKT per capita", "1-4 qtrs"): 1.555152,
    ("PED VKT per capita", "5-8 qtrs"): 2.504013,
    ("PED VKT per capita", "9-12 qtrs"): 3.515873,
    ("PED VKT per capita", "2024+"): 0.962366,
    ("PED VKT per capita", "2022-23"): 2.170776,
    ("PED VKT per capita", "Annual"): 2.385625,
    ("Light RUC volume", "1-4 qtrs"): 7.735819,
    ("Light RUC volume", "5-8 qtrs"): 9.486600,
    ("Light RUC volume", "9-12 qtrs"): 10.525990,
    ("Light RUC volume", "2024+"): 6.253350,
    ("Light RUC volume", "2022-23"): 18.785206,
    ("Light RUC volume", "Annual"): 5.999499,
    ("Heavy RUC volume", "1-4 qtrs"): 2.802065,
    ("Heavy RUC volume", "5-8 qtrs"): 3.543246,
    ("Heavy RUC volume", "9-12 qtrs"): 4.268496,
    ("Heavy RUC volume", "Annual"): 3.019980,
}

EXPECTED_SCENARIO_COMPARISON = {
    "PED VKT per capita": {
        "scenario_a_quarterly_mape": 2.473245,
        "scenario_b_quarterly_mape": 3.082117,
        "full_sample_qtr_gain_pp": 0.608873,
        "scenario_a_annual_mape": 2.385625,
        "scenario_b_annual_mape": 2.965758,
        "full_sample_annual_gain_pp": 0.580133,
        "paired_win_rate_pct": 63.201320,
    },
    "Light RUC volume": {
        "scenario_a_quarterly_mape": 9.147545,
        "scenario_b_quarterly_mape": 11.546786,
        "full_sample_qtr_gain_pp": 2.399241,
        "scenario_a_annual_mape": 5.999499,
        "scenario_b_annual_mape": 7.843683,
        "full_sample_annual_gain_pp": 1.844184,
        "paired_gain_pp": -1.159120,
        "paired_win_rate_pct": 50.555556,
    },
    "Heavy RUC volume": {
        "scenario_a_quarterly_mape": 3.484368,
        "scenario_b_quarterly_mape": 11.482643,
        "full_sample_qtr_gain_pp": 7.998276,
        "scenario_a_annual_mape": 3.019980,
        "scenario_b_annual_mape": 11.717804,
        "full_sample_annual_gain_pp": 8.697824,
        "paired_win_rate_pct": 64.155251,
    },
}

EXPECTED_LIGHT_PAIRED_GAIN_PP = -1.159120

EXPECTED_FIXTURE_FINALISTS = {
    "PED": {"quarterly_mape": 2.473245, "annual_mape": 2.385625},
    "LIGHT_RUC": {"quarterly_mape": 9.147545, "annual_mape": 5.999499},
    "HEAVY_RUC": {"quarterly_mape": 3.484368, "annual_mape": 3.019980},
}
