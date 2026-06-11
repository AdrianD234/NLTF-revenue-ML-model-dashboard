from __future__ import annotations

EXPECTED_FINALIST_MAPE = {
    ("PED VKT per capita", "Quarterly MAPE"): 3.131663,
    ("PED VKT per capita", "Annual MAPE"): 1.946846,
    ("Light RUC volume", "Quarterly MAPE"): 5.363207,
    ("Light RUC volume", "Annual MAPE"): 1.273774,
    ("Heavy RUC volume", "Quarterly MAPE"): 2.288716,
    ("Heavy RUC volume", "Annual MAPE"): 1.682721,
}

EXPECTED_ENSEMBLE_WEIGHT_PCT = {
    "PED VKT per capita": [58.4392, 41.5608],
    "Light RUC volume": [100.0],
    "Heavy RUC volume": [70.8904, 21.2188, 7.8908],
}

EXPECTED_STRESS_MAPE = {
    ("PED VKT per capita", "1-4 qtrs"): 1.785138,
    ("PED VKT per capita", "5-8 qtrs"): 2.33687,
    ("PED VKT per capita", "9-12 qtrs"): 4.972864,
    ("PED VKT per capita", "2024+"): float("nan"),
    ("PED VKT per capita", "2022-23"): 3.319361,
    ("PED VKT per capita", "Annual"): 1.946846,
    ("Light RUC volume", "1-4 qtrs"): 4.179904,
    ("Light RUC volume", "5-8 qtrs"): 3.780027,
    ("Light RUC volume", "9-12 qtrs"): 7.806239,
    ("Light RUC volume", "2024+"): float("nan"),
    ("Light RUC volume", "2022-23"): 9.100548,
    ("Light RUC volume", "Annual"): 1.273774,
    ("Heavy RUC volume", "1-4 qtrs"): 2.362473,
    ("Heavy RUC volume", "5-8 qtrs"): 2.372658,
    ("Heavy RUC volume", "9-12 qtrs"): 2.095835,
    ("Heavy RUC volume", "2024+"): float("nan"),
    ("Heavy RUC volume", "2022-23"): 2.438166,
    ("Heavy RUC volume", "Annual"): 1.682721,
}

EXPECTED_SCENARIO_COMPARISON = {
    "PED VKT per capita": {
        "scenario_a_quarterly_mape": 3.131663,
        "scenario_b_quarterly_mape": 4.674917,
        "full_sample_qtr_gain_pp": 1.543254,
        "scenario_a_annual_mape": 1.946846,
        "scenario_b_annual_mape": 3.585729,
        "full_sample_annual_gain_pp": 1.638883,
        "paired_gain_pp": 1.247232,
        "paired_win_rate_pct": 69.84127,
    },
    "Light RUC volume": {
        "scenario_a_quarterly_mape": 5.363207,
        "scenario_b_quarterly_mape": 8.521397,
        "full_sample_qtr_gain_pp": 3.15819,
        "scenario_a_annual_mape": 1.273774,
        "scenario_b_annual_mape": 2.702,
        "full_sample_annual_gain_pp": 1.428227,
        "paired_gain_pp": 2.932205,
        "paired_win_rate_pct": 62.698413,
    },
    "Heavy RUC volume": {
        "scenario_a_quarterly_mape": 2.288716,
        "scenario_b_quarterly_mape": 8.761652,
        "full_sample_qtr_gain_pp": 6.472936,
        "scenario_a_annual_mape": 1.682721,
        "scenario_b_annual_mape": 8.879508,
        "full_sample_annual_gain_pp": 7.196787,
        "paired_gain_pp": 5.929683,
        "paired_win_rate_pct": 65.079365,
    },
}

EXPECTED_LIGHT_PAIRED_GAIN_PP = 2.932205

EXPECTED_FIXTURE_FINALISTS = {
    "PED": {"quarterly_mape": 2.473245, "annual_mape": 2.385625},
    "LIGHT_RUC": {"quarterly_mape": 9.147545, "annual_mape": 5.999499},
    "HEAVY_RUC": {"quarterly_mape": 3.484368, "annual_mape": 3.019980},
}
